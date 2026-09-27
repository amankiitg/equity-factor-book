"""Sprint E11: the variance-share rule, and where it sits in the sizing.

The owner's rule, set 2026-09-26: no name may carry more than 10% of the book's
predicted specific variance, a name above it is scaled down to 10%, and the book
is renormalized to gross 1.0 before the hedge. The cap therefore has to be part
of the sizing every caller shares, not a step after it.
"""

from __future__ import annotations

import numpy as np
import pytest

from live import evening_job as ev
from live import sizing


def _book(size: int = 20, biggest: float = 40.0) -> tuple[np.ndarray, np.ndarray]:
    weights = np.linspace(1.0, 0.5, size)
    weights[0] = biggest
    specific = np.linspace(1e-4, 2e-4, size)
    return weights, specific


def test_a_name_above_the_cap_is_taken_to_exactly_the_cap() -> None:
    weights, specific = _book()
    before = sizing.variance_shares(weights, specific)
    assert before.max() > 0.10, "the fixture must start above the cap"

    capped = sizing.cap_variance_shares(weights, specific)
    after = sizing.variance_shares(capped, specific)

    assert after.max() == pytest.approx(0.10, abs=1e-12)
    # Only the names above the cap move, and only downwards.
    assert np.all(np.abs(capped) <= np.abs(weights) + 1e-12)
    assert np.all(np.sign(capped) == np.sign(weights))
    untouched = before <= 0.10
    assert np.allclose(capped[untouched], weights[untouched])
    # More than one name can be clamped, and every clamped name sits at the cap.
    clamped = after > 0.10 - 1e-9
    assert clamped.sum() >= 1
    assert np.allclose(after[clamped], 0.10, atol=1e-9)


def test_the_cap_is_scale_invariant() -> None:
    """Renormalizing the book cannot change which names are over the cap."""
    weights, specific = _book()
    capped = sizing.cap_variance_shares(weights, specific)
    renormed = sizing.renormalize(capped, gross=1.0)

    assert np.allclose(
        sizing.variance_shares(renormed, specific),
        sizing.variance_shares(capped, specific),
    )


def test_a_book_too_small_for_the_cap_is_made_as_even_as_it_can_be() -> None:
    """Six names cannot each hold 10%: the shares have to sum to one.

    The search evaluates candidate subsets, so this case has to be answered rather
    than raised on: the tightest cap a six-name book can meet is one sixth, which
    is what the most even book there is holds.
    """
    weights = np.array([5.0, -5.0, 4.0, -4.0, 3.0, -3.0])
    specific = np.ones(6)

    capped = sizing.cap_variance_shares(weights, specific)
    shares = sizing.variance_shares(capped, specific)

    assert shares.max() == pytest.approx(1 / 6, abs=1e-12)
    assert np.allclose(np.abs(capped), np.abs(capped[0])), "not even"
    # Evened in variance, not in nothing: the signs and the dollar neutrality of
    # the fixture survive.
    assert abs(float(capped.sum())) < 1e-9
    assert np.allclose(np.sign(capped), np.sign(weights))


def _traded_fixture() -> (
    tuple[list[str], np.ndarray, np.ndarray, np.ndarray, dict[str, float]]
):
    """Twelve names and three factors, so the hedge has room to depend on the cap.

    A book with only one more name than factors is degenerate here: the hedge's
    image is then one-dimensional, so every candidate vector lands on the same
    direction and renormalizes to the same book whatever the cap does. Twelve
    names and three columns leaves the hedge nine dimensions to work in, which is
    where the order of the two operations can be told apart.
    """
    names = [f"T{index:02d}" for index in range(12)]
    alpha = np.linspace(9.0, -9.0, 12)
    specific = np.linspace(1e-4, 1e-3, 12)
    design = np.ones((12, 3))
    design[:, 1] = np.linspace(-1.0, 1.0, 12)
    design[:, 2] = np.sin(np.arange(12, dtype=float))
    close = {name: 50.0 for name in names}
    return names, alpha, specific, design, close


def _capped_sized(alpha: np.ndarray, specific: np.ndarray) -> np.ndarray:
    sized = alpha / specific
    capped = sizing.cap_variance_shares(sized, specific)
    assert not np.allclose(capped, sized), "the fixture must bind the cap"
    return sizing.renormalize(capped, gross=1.0)


def test_the_cap_lands_before_the_hedge_and_the_traded_book_uses_it() -> None:
    """The order is the rule: capping after the hedge would undo the hedge.

    The traded vector is rebuilt from the two halves - cap, renormalize, hedge,
    renormalize - and has to be the vector the shared sizing returns, so the floor
    search and the book that trades cannot disagree about which book it is.
    """
    names, alpha, specific, design, close = _traded_fixture()
    factor_covariance = np.eye(3)
    keep = np.ones(12, dtype=bool)

    idx, names_sub, w_sub, _prices, _d, _s, pre_hedge = ev.sized_kept_weights(
        keep, names, alpha, design, factor_covariance, specific, close, 100_000.0
    )

    pre = _capped_sized(alpha, specific)
    assert sizing.variance_shares(pre, specific).max() == pytest.approx(0.10, abs=1e-12)
    # The hedge acted on that capped vector, not on the uncapped one.
    assert np.allclose(pre_hedge, design.T @ pre)
    expected, _pre = sizing.procedure_6_3_hedged_with_exposures(
        alpha, design, factor_covariance, specific, sized=pre
    )
    assert np.allclose(w_sub, sizing.renormalize(expected, gross=1.0))
    assert list(names_sub) == names
    assert idx.tolist() == list(range(12))


def test_the_hedge_can_lift_a_capped_name_back_above_the_cap() -> None:
    """The rule is the sized vector's, and the hedge is allowed to move it after.

    Measured rather than assumed: on this fixture the sized vector sits exactly on
    the cap and the traded book has a name above it. The owner's rule puts the cap
    before the hedge, and clamping the post-hedge vector instead would break the
    exact projection that makes the book dollar-neutral, so this is the rule's
    stated boundary rather than a defect. It is pinned here so that changing the
    order is a deliberate act, and it is reported with its real numbers in
    `handoff/REPORT.md` - on the 2026-09-21 close, one name of 169 (TER 11.72%).
    """
    names, alpha, specific, design, close = _traded_fixture()
    pre = _capped_sized(alpha, specific)
    _idx, _names, w_sub, *_rest = ev.sized_kept_weights(
        np.ones(12, dtype=bool),
        names,
        alpha,
        design,
        np.eye(3),
        specific,
        close,
        100_000.0,
    )

    before = sizing.variance_shares(pre, specific)
    after = sizing.variance_shares(w_sub, specific)
    assert before.max() == pytest.approx(0.10, abs=1e-12)
    assert after.max() > 0.10, "the fixture must show the hedge lifting a share"
    # What the cap gives up is what the hedge buys: the traded vector has no
    # factor exposure to the 1e-15, and the sized vector it was made from has a
    # lot of it, which is why the two cannot be capped in the same place.
    assert np.abs(design.T @ w_sub).max() < 1e-12
    assert np.abs(design.T @ pre).max() > 1e-3


def test_the_uncapped_hedge_is_not_what_trades() -> None:
    """The negative control: without the cap the book differs, so the test bites."""
    names, alpha, specific, design, close = _traded_fixture()
    _idx, _names, w_sub, *_rest = ev.sized_kept_weights(
        np.ones(12, dtype=bool),
        names,
        alpha,
        design,
        np.eye(3),
        specific,
        close,
        100_000.0,
    )
    hedged, _pre = sizing.procedure_6_3_hedged_with_exposures(
        alpha, design, np.eye(3), specific
    )

    assert not np.allclose(w_sub, sizing.renormalize(hedged, gross=1.0))
