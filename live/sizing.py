"""Shared robust sizing for the live path.

Procedure 6.3 sizes on D^-1 alpha and hedges with the exact in-model FMPs.
The exact hedge solves X'X, which is singular when the kept subset is too
small to span the factor space; the robust variant falls back to the
pseudoinverse, which still recovers the exact hedge when the exposure lies
in the column space of X'X and reports the best achievable hedge otherwise.
"""

from __future__ import annotations

import numpy as np

from efb import size

# No name may carry more than this share of the book's predicted specific
# variance. The alpha/variance rule already divides by variance, but a single
# name with a violent one-day move in its history can still take a share of the
# book's residual risk that no hedge removes - MRNA at 40%+ on 2026-09-25 - and
# the owner's rule is 10%.
VARIANCE_SHARE_CAP = 0.10


def hedge_exact_robust(design: np.ndarray, exposures: np.ndarray) -> np.ndarray:
    """The exact in-model FMP hedge, pseudoinverse fallback for rank-deficient
    subsets. The achieved exposure is the caller's to report."""
    try:
        loadings = np.linalg.solve(design.T @ design, exposures)
    except np.linalg.LinAlgError:
        loadings = np.linalg.pinv(design.T @ design) @ exposures
    return -(design @ loadings)


def procedure_6_3_hedged_with_exposures(
    alpha: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
    sized: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """The hedged book, and the pre-hedge exposure the hedge acted on.

    `X'w` of the pre-hedge book is what the hedge itself computes to decide what
    to subtract, so it is returned here rather than reconstructed by a caller: two
    constructions of the same vector could disagree, and the page shows this one.

    `sized` is the pre-hedge book when the caller has already sized it (a
    variance-share cap, say). The hedge is the same either way, and it must be:
    the cap belongs before the hedge, so it cannot be applied afterwards.
    """
    del factor_covariance  # the hedge does not read it, matching procedure_6_3
    unhedged = (
        size.proportional(alpha, specific) if sized is None else np.asarray(sized)
    )
    exposures = design.T @ unhedged
    return unhedged + hedge_exact_robust(design, exposures), exposures


def variance_shares(weights: np.ndarray, specific: np.ndarray) -> np.ndarray:
    """Each name's share of the book's predicted specific variance.

    The book's variance is `sum(w_i^2 s_i^2)` over the specific diagonal, which
    is the part of the risk no factor hedge can take out. This is the share of
    that sum each name carries, and it is scale invariant: renormalizing the book
    does not move it.
    """
    variance = np.asarray(weights, dtype=float) ** 2 * np.asarray(specific, dtype=float)
    total = float(variance.sum())
    if total <= 0:
        return np.zeros_like(variance)
    return variance / total


def cap_variance_shares(
    weights: np.ndarray,
    specific: np.ndarray,
    cap: float = VARIANCE_SHARE_CAP,
) -> np.ndarray:
    """Scale down every name above `cap` of the variance, and only those.

    One name's variance share is `w^2 s^2 / sum(w^2 s^2)`, so the capped book has
    every clamped name sitting at exactly the cap and every other name untouched.
    Solving that directly is water-filling: find the level `L` with
    `sum(min(c_i, L)) = L / cap`, where `c_i = w_i^2 s_i^2`. A clamped name's
    contribution is then `L`, so its share is `L / (L/cap)` = the cap exactly, and
    an untouched name has `c_i <= L`, so its share is at most the cap too.

    The reason it is solved rather than iterated: rescaling a violator to the cap
    changes the total, which re-violates the names just clamped, and the sequence
    crawls without converging (measured: 100 passes and still moving). The closed
    form is the fixed point by construction, and it is exact where a bisection on
    the level is not: at a cap of exactly 1/n the root sits on the boundary and
    rounding it down scales the whole book away.

    Applied to the sized book *before* the hedge, which is the only order that
    works: the hedge is a projection of the sized vector, so capping afterwards
    would undo one of the two. Names are only ever scaled down, so the direction
    of the tilt never reverses.
    """
    weights = np.asarray(weights, dtype=float)
    variance = weights**2 * np.asarray(specific, dtype=float)
    total = float(variance.sum())
    live = int((variance > 0).sum())
    if total <= 0 or live == 0:
        return weights.copy()
    # A book of fewer than 1/cap names cannot meet the cap: the shares have to sum
    # to one, so the most even book there is puts 1/n of the variance on every
    # name. The effective cap is therefore the tighter of the owner's and that
    # floor, which leaves a full book on exactly the owner's number and keeps a
    # candidate subset in the floor search small enough to be rejected rather than
    # crashing the search that has to consider it.
    cap = max(cap, 1.0 / live)
    # Solved directly rather than iterated. Every clamped name sits at the same
    # level, so if the top `count` are clamped the level is
    # `cap * S / (1 - count * cap)`, where `S` is the variance of the names below
    # them, and the right `count` is the first whose level is at or below the next
    # contribution down. Rescaling violators one at a time changes the total and
    # re-violates the names just clamped, so it crawls without converging
    # (measured: 100 passes and still moving), and a bisection on the level lands
    # a few ulps below its own fixed point when the cap is exactly 1/n, which
    # scales the whole book away.
    order = np.argsort(-variance)
    ordered = variance[order]
    tail = np.concatenate([np.cumsum(ordered[::-1])[::-1][1:], np.zeros(1)])
    level = float(ordered[-1])
    for count in range(1, live + 1):
        if count * cap >= 1.0:
            break
        candidate = cap * float(tail[count - 1]) / (1.0 - count * cap)
        if count == live or ordered[count] <= candidate:
            level = candidate
            break
    target = np.where(
        variance > 0, np.minimum(1.0, level / np.maximum(variance, 1e-300)), 1.0
    )
    return weights * np.sqrt(target)


def procedure_6_3_robust(
    alpha: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
) -> np.ndarray:
    """Procedure 6.3 on a subset, with the least-squares hedge fallback.

    One implementation: this delegates to `procedure_6_3_hedged_with_exposures`, so
    a caller that wants both halves and a caller that wants the book alone cannot
    drift apart.
    """
    hedged, _exposures = procedure_6_3_hedged_with_exposures(
        alpha, design, factor_covariance, specific
    )
    return hedged


def renormalize(weights: np.ndarray, gross: float = 1.0) -> np.ndarray:
    """Scale weights to a target gross, preserving sign and factor neutrality."""
    total = float(np.abs(weights).sum())
    if total <= 0:
        return weights
    return weights * (gross / total)
