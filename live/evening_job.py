"""Sprint E11: the evening proposal job.

Previous-close data only. Build tomorrow's target book: `idio_momentum`
as alpha, Procedure 6.3 sizing under the champion XS-v1, the exact FMP
hedge, the E8 constraint set, E9 costs and the E10 vol target capped by
the gross cap. The universe comes from the SPY archive, never the frozen
history. Nothing executes here; the job writes one dated proposal.

The seam is documented, never bridged: the risk model is frozen on the
pinned Wikipedia history (through its last close), while the universe is
the live SPY archive from 2026-09-18 forward. SPY names the frozen model
does not know are excluded and counted, not imputed.
"""

from __future__ import annotations

import json
import math
import subprocess
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from efb import alpha as alpha_mod
from efb import costs as costs_mod
from efb import eval_risk, registry, size
from efb.build import hash_file
from live import alpaca, sizing

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
PROPOSAL_DIR = ROOT / "live" / "proposals"

SIGNAL = "idio_momentum"
MODEL_VERSION = "XS-v1"  # the champion the book is built and run under
SPY_UNIVERSE_MIN_AS_OF = date(2026, 9, 18)  # the live-universe seam
TARGET_ANNUAL_VOL = 0.10  # the E10 target
GROSS_CAP = 1.0  # the E8 gross cap, a hard ceiling
PAPER_NAV = 1_000_000.0  # the paper notional the morning job runs
REFERENCE_AUM = 1e8  # the capacity-curve reference, kept for the E6 finding
TRADING_DAYS = 252
HORIZON = 21  # the rebalance horizon, the E6 and E9 convention
MIN_NAMES = 50

# the frozen model inputs whose content the proposal is pinned to
INPUT_ARTIFACTS = (
    "models/XS-v1/descriptors.parquet",
    "models/XS-v1/factor_returns.parquet",
    "models/XS-v1/specific_var.parquet",
    "models/XS-v1/specific_returns.parquet",
    "alpha/summary.parquet",
    "processed/sectors.parquet",
)


def _git_commit() -> str:
    """The HEAD the proposal was built from, or a marker when git is absent.

    The proposal records the code commit so the page can say which build
    produced the book; on a deployment without git the field is honest about
    being unknown rather than guessed.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def load_spy_universe(data_root: Path = DATA_ROOT) -> tuple[pd.DataFrame, Path]:
    """The live universe from the SPY archive, asserted rather than assumed.

    The latest dated SPY holdings file is the universe. The seam is
    enforced: a file dated before the live-universe seam fails loudly
    instead of silently falling back to the frozen history.
    """
    root = Path(data_root)
    archive_dir = root / "raw" / "spy_holdings"
    files = sorted(archive_dir.glob("spy_holdings_*.parquet"))
    if not files:
        raise FileNotFoundError(f"no SPY archive files under {archive_dir}")
    path = files[-1]
    frame = pd.read_parquet(path)
    as_of = pd.to_datetime(frame["as_of"].iloc[0]).date()
    if as_of < SPY_UNIVERSE_MIN_AS_OF:
        raise ValueError(
            f"SPY archive {path.name} is dated {as_of}, before the live "
            f"universe seam {SPY_UNIVERSE_MIN_AS_OF}"
        )
    return frame, path


def _stored_ic(signal: str, data_root: Path) -> float:
    """The stored horizon-1 IC of the signal, read, never typed by hand."""
    summary = pd.read_parquet(data_root / "alpha" / "summary.parquet")
    rows = summary.loc[summary["signal"] == signal]
    if rows.empty:
        raise ValueError(f"no stored alpha summary row for signal {signal!r}")
    return float(rows["ic_h1_mean"].iloc[0])


def _stored_neutral_ic(signal: str, data_root: Path) -> dict[str, float]:
    """The stored horizon-21 factor-neutral IC and its t, read, never typed."""
    summary = pd.read_parquet(data_root / "alpha" / "summary.parquet")
    rows = summary.loc[summary["signal"] == signal]
    if rows.empty:
        raise ValueError(f"no stored alpha summary row for signal {signal!r}")
    return {
        "factor_neutral_ic_h21": float(rows["neutral_ic_h21_mean"].iloc[0]),
        "factor_neutral_t_h21": float(rows["neutral_ic_h21_t"].iloc[0]),
    }


def _decomposition(
    weights: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
) -> dict[str, float]:
    """The book's risk split and its factor-neutrality after the hedge."""
    factor_var = float(weights @ design @ factor_covariance @ design.T @ weights)
    idio_var = float(weights @ (specific * weights))
    total = factor_var + idio_var
    return {
        "factor_variance": factor_var,
        "idio_variance": idio_var,
        "idio_share": idio_var / total if total > 0 else float("nan"),
        "max_abs_exposure": float(np.abs(design.T @ weights).max()),
        "gross": float(np.abs(weights).sum()),
        "net": float(weights.sum()),
        "n_eff": (
            float(np.abs(weights).sum() ** 2 / (weights**2).sum())
            if (weights**2).sum() > 0
            else 0.0
        ),
        "n_nonzero": int((np.abs(weights) > 1e-12).sum()),
    }


def _scale_to_target(
    weights: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
) -> tuple[np.ndarray, bool]:
    """Scale raw weights to the E10 vol target, capped by the E8 gross cap.

    Returns the scaled weights and whether the gross cap bound instead of
    the vol target. A null alpha cannot reach the 10% target inside gross 1,
    so the cap binds and the achieved vol is stored beside the target.
    """
    daily_var = float(
        weights @ design @ factor_covariance @ design.T @ weights
        + weights @ (specific * weights)
    )
    daily_vol = math.sqrt(daily_var) if daily_var > 0 else 0.0
    target_daily_vol = TARGET_ANNUAL_VOL / math.sqrt(TRADING_DAYS)
    gross = float(np.abs(weights).sum())
    scale = target_daily_vol / daily_vol if daily_vol > 0 else 1.0
    gross_cap_bound = False
    if scale * gross > GROSS_CAP:
        scale = GROSS_CAP / gross
        gross_cap_bound = True
    return weights * scale, gross_cap_bound


SHARE_FLOOR = 20  # the owner's chosen share-only floor, in whole shares


def sized_kept_weights(
    keep: np.ndarray,
    names: list[str],
    alpha_vec: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
    close: dict[str, float],
    nav: float,
) -> tuple[np.ndarray, list[str], np.ndarray, np.ndarray, np.ndarray]:
    """Procedure 6.3 on the kept subset, hedged and renormalized to gross 1.0.

    One implementation for the whole module: `finalize_kept_set` builds its
    report from this, and the floor search reads the same vector so a set that
    the search accepts is the set that trades.
    """
    del nav  # the renorm is to gross 1.0; the share counts take the NAV
    idx = np.where(keep)[0]
    names_sub = [names[i] for i in idx]
    w_sub = sizing.procedure_6_3_robust(
        alpha_vec[idx], design[idx], factor_covariance, specific[idx]
    )
    w_sub = sizing.renormalize(w_sub, gross=1.0)
    prices = np.array([close.get(t, 0.0) for t in names_sub], dtype=float)
    return idx, names_sub, w_sub, prices, design[idx], specific[idx]


def kept_shares(w_sub: np.ndarray, prices: np.ndarray, nav: float) -> np.ndarray:
    """The whole-share count of each kept name at the close."""
    return np.floor(np.abs(w_sub) * nav / np.maximum(prices, 1e-12)).astype(int)


def finalize_kept_set(
    keep: np.ndarray,
    names: list[str],
    alpha_vec: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
    close: dict[str, float],
    nav: float,
) -> dict[str, Any]:
    """Size, hedge, renormalize and quantize one kept set to final weights.

    This is the final, tradable vector: Procedure 6.3 on the kept subset,
    the exact FMP hedge, renormalized to gross 1.0, then quantized to whole
    shares at the close. Nothing downstream re-weights it, so the floor must
    be checked against this vector, not the full-book weights.
    """
    idx, names_sub, w_sub, prices, design_sub, specific_sub = sized_kept_weights(
        keep, names, alpha_vec, design, factor_covariance, specific, close, nav
    )
    decomp = _decomposition(w_sub, design_sub, factor_covariance, specific_sub)
    quant = alpaca.whole_share_quantization(
        pd.DataFrame({"ticker": names_sub, "weight": w_sub}), close, nav
    )
    shares = kept_shares(w_sub, prices, nav)
    q_notional = shares * prices * np.sign(w_sub)
    gross_q = float(np.abs(q_notional).sum())
    return {
        "idx": idx,
        "names_sub": names_sub,
        "w_sub": w_sub,
        "decomp": decomp,
        "quant": quant,
        "prices": prices,
        "shares": shares,
        "q_notional": q_notional,
        "gross_q": gross_q,
    }


def kept_set_clears_floor(
    keep: np.ndarray,
    names: list[str],
    alpha_vec: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
    close: dict[str, float],
    nav: float,
    dollar_floor: float,
    share_floor: int,
) -> bool:
    """Whether every kept name clears its floor in the final weights.

    The floor search runs this hundreds of times per row, so it takes the
    sizing and share math without the report payload `finalize_kept_set`
    builds. The vector it checks is the same one, from the same function.
    """
    _idx, _names_sub, w_sub, prices, _design_sub, _specific_sub = sized_kept_weights(
        keep, names, alpha_vec, design, factor_covariance, specific, close, nav
    )
    shares = kept_shares(w_sub, prices, nav)
    return not below_floor(shares, prices, dollar_floor, share_floor).any()


def below_floor(
    shares: np.ndarray,
    prices: np.ndarray,
    dollar_floor: float,
    share_floor: int,
) -> np.ndarray:
    """Which kept names end below their floor in the final, quantized weights.

    A name clears the floor when its whole-share notional is at least the
    dollar floor and it holds at least share_floor whole shares. The two legs
    are independent; failing either is below the floor.
    """
    below = np.zeros(len(shares), dtype=bool)
    if share_floor > 0:
        below |= shares < share_floor
    if dollar_floor > 0:
        below |= shares * prices < dollar_floor
    return below


def floor_shortfalls(
    shares: np.ndarray,
    prices: np.ndarray,
    dollar_floor: float,
    share_floor: int,
) -> tuple[float, float]:
    """The worst shortfall in whole shares and in dollars, across below-floor names."""
    below = below_floor(shares, prices, dollar_floor, share_floor)
    if not below.any():
        return 0.0, 0.0
    short_shares = (
        float((share_floor - shares[below]).max()) if share_floor > 0 else 0.0
    )
    short_dollars = (
        float((dollar_floor - shares[below] * prices[below]).max())
        if dollar_floor > 0
        else 0.0
    )
    return short_shares, short_dollars


def enforce_floor_on_final_weights(
    keep: np.ndarray,
    names: list[str],
    alpha_vec: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
    close: dict[str, float],
    nav: float,
    dollar_floor: float,
    share_floor: int,
    max_passes: int = 30,
) -> tuple[np.ndarray, dict[str, Any], int, bool]:
    """Enforce the floor on the final weights, iterated to a fixed point.

    Drop, re-size, re-hedge, renormalize, quantize, check, repeat until no
    kept name is below its floor. The kept set only shrinks, so the loop
    terminates; the pass cap guards a degenerate run and returns converged
    False rather than silently picking a pass.

    E11-F13: because it only drops, it lands at or below the one-pass count
    and gives up the breadth the E11-F6 iteration buys back (119 against 188
    on the share-only book). It is still the last valid enforced book; the
    corrected rule is being re-specified, and its candidate,
    `enforce_floor_by_prefix`, is measured beside this one rather than
    installed.
    """
    keep = keep.copy()
    finalize: dict[str, Any] = {}
    for passes in range(1, max_passes + 1):
        finalize = finalize_kept_set(
            keep, names, alpha_vec, design, factor_covariance, specific, close, nav
        )
        shares = np.asarray(finalize["shares"], dtype=int)
        prices = np.asarray(finalize["prices"], dtype=float)
        below = below_floor(shares, prices, dollar_floor, share_floor)
        if not below.any():
            return keep, finalize, passes, True
        idx = np.asarray(finalize["idx"], dtype=int)
        keep[idx[below]] = False
        if not keep.any():
            return keep, finalize, passes, False
    return keep, finalize, max_passes, False


def floor_thresholds(
    close: dict[str, float],
    names: list[str],
    dollar_floor: float,
    share_floor: int,
) -> np.ndarray:
    """Per-name notional threshold a name must clear to be kept.

    Name i is kept when |w_i| * nav is at least max(dollar_floor, share_floor *
    price_i) times the kept gross, so the threshold is the larger of the two
    legs at that name's own close, on the same prices the sizing and the
    quantization use.
    """
    prices = np.array([close.get(ticker, 0.0) for ticker in names], dtype=float)
    return np.maximum(dollar_floor, share_floor * prices)


def enforce_floor_by_prefix(
    names: list[str],
    alpha_vec: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
    close: dict[str, float],
    nav: float,
    full_weights: np.ndarray,
    dollar_floor: float,
    share_floor: int,
) -> tuple[np.ndarray, dict[str, Any], int]:
    """The largest valid prefix, checked on the final weights (E11-F13).

    Order names by |w_i| / max(dollar_floor, share_floor * price_i) on the
    full-book weights, the ordering the E11-F9 prefix method uses, so the kept
    set is a prefix of that order. For k from the full book down, finalize the
    prefix-k set (size, hedge, renormalize, quantize) and check every kept name
    against its floor in those final weights. The first k that passes is the
    largest valid prefix.

    The pass set is not monotone in k, so the scan is linear and is never
    bisected. E11-F13R replaced this rule with drop-then-admit, because a
    prefix of an ordering is still a dropping rule and this one keeps far fewer
    names than the drop-only loop on every floor row. It is kept so the table
    can report its result beside the book.
    """
    thresholds = floor_thresholds(close, names, dollar_floor, share_floor)
    order = np.argsort(-(np.abs(full_weights) / thresholds), kind="stable")
    n_names = len(names)
    for k in range(n_names, 0, -1):
        keep = np.zeros(n_names, dtype=bool)
        keep[order[:k]] = True
        finalize = finalize_kept_set(
            keep, names, alpha_vec, design, factor_covariance, specific, close, nav
        )
        shares = np.asarray(finalize["shares"], dtype=int)
        prices = np.asarray(finalize["prices"], dtype=float)
        if not below_floor(shares, prices, dollar_floor, share_floor).any():
            return keep, finalize, k
    raise ValueError(
        "no prefix of the book clears the floor in its final weights; the "
        "floor cannot be satisfied on this book"
    )


def floor_order(
    close: dict[str, float],
    names: list[str],
    full_weights: np.ndarray,
    dollar_floor: float,
    share_floor: int,
) -> np.ndarray:
    """The kept-set ordering the floor rule searches: |w_i| / floor_i, stable.

    Both the drop-then-admit rule and the prefix scan use this order, so a
    caller that wants to reuse it computes it once.
    """
    thresholds = floor_thresholds(close, names, dollar_floor, share_floor)
    return np.argsort(-(np.abs(full_weights) / thresholds), kind="stable")


def admit_clearing_names(
    keep: np.ndarray,
    names: list[str],
    alpha_vec: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
    close: dict[str, float],
    nav: float,
    order: np.ndarray,
    dollar_floor: float,
    share_floor: int,
) -> tuple[np.ndarray, int]:
    """One admission pass: walk the excluded names in order and admit them.

    A name is admitted only when the final weights of the enlarged set still
    clear every kept name's floor, so the pass only ever adds names. Walking
    the whole order is the point: an earlier name can be blocked by a name
    admitted later, and the pass does not revisit it, which is why the rule
    repeats until a pass admits nothing.
    """
    admitted = 0
    for position in order:
        if keep[position]:
            continue
        trial = keep.copy()
        trial[position] = True
        if kept_set_clears_floor(
            trial,
            names,
            alpha_vec,
            design,
            factor_covariance,
            specific,
            close,
            nav,
            dollar_floor,
            share_floor,
        ):
            keep = trial
            admitted += 1
    return keep, admitted


def enforce_floor_by_drop_then_admit(
    names: list[str],
    alpha_vec: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
    close: dict[str, float],
    nav: float,
    full_weights: np.ndarray,
    dollar_floor: float,
    share_floor: int,
    order: np.ndarray | None = None,
    max_cycles: int = 10,
) -> tuple[np.ndarray, dict[str, Any], dict[str, Any]]:
    """Drop, then admit, repeated until a full cycle changes nothing (E11-F13R).

    The rule the reviewer re-specified after E11-F13: start from the drop-only
    fixed point, admit names in the |w_i| / floor_i order while the enlarged
    set's final weights still clear every kept name's floor, repeat the
    admission pass until a pass admits nothing, then run the drop step once
    more as a check. If the check drops anything the cycle repeats.

    The result is a local maximum under single-name moves: every kept name
    clears its floor in the final weights, and no single excluded name can be
    added without breaking one. It is not claimed to be the global maximum.

    Returns the kept set, its final finalize, and a report of the search:
    the drop-only count, the count after the first admission pass, the cycles
    and passes run, how many names were admitted, and whether it converged
    inside the cycle cap. At the cap the caller must stop and report rather
    than pick a cycle, which is what `converged` false means.
    """
    if order is None:
        order = floor_order(close, names, full_weights, dollar_floor, share_floor)
    all_names = np.ones(len(names), dtype=bool)
    drop_keep, drop_finalize, _drop_passes, _drop_converged = (
        enforce_floor_on_final_weights(
            all_names,
            names,
            alpha_vec,
            design,
            factor_covariance,
            specific,
            close,
            nav,
            dollar_floor,
            share_floor,
        )
    )
    keep = drop_keep.copy()
    finalize = drop_finalize
    one_pass: np.ndarray | None = None
    passes = 0
    admitted_total = 0
    cycles = 0
    converged = False
    while cycles < max_cycles:
        cycles += 1
        while True:
            keep, admitted = admit_clearing_names(
                keep,
                names,
                alpha_vec,
                design,
                factor_covariance,
                specific,
                close,
                nav,
                order,
                dollar_floor,
                share_floor,
            )
            passes += 1
            admitted_total += admitted
            if one_pass is None:
                one_pass = keep.copy()
            if admitted == 0:
                break
        checked, finalize, _passes, _converged = enforce_floor_on_final_weights(
            keep,
            names,
            alpha_vec,
            design,
            factor_covariance,
            specific,
            close,
            nav,
            dollar_floor,
            share_floor,
        )
        if int(checked.sum()) == int(keep.sum()):
            converged = True
            break
        keep = checked
    if one_pass is None:
        one_pass = keep.copy()
    info = {
        "n_drop_only": int(drop_keep.sum()),
        "n_one_pass_admission": int(one_pass.sum()),
        "cycles": cycles,
        "admit_passes": passes,
        "admitted": admitted_total,
        "converged": converged,
    }
    return keep, finalize, info


RANK_MARGIN_FACTORS = 17  # the XS-v1 design width
MIN_FLOOR_BOOK_NAMES = 3 * RANK_MARGIN_FACTORS  # the owner's rank margin: 51


def floor_book_violations(
    keep: np.ndarray,
    names: list[str],
    alpha_vec: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
    close: dict[str, float],
    nav: float,
    dollar_floor: float,
    share_floor: int,
    min_names: int = MIN_FLOOR_BOOK_NAMES,
) -> list[str]:
    """Every check an enforced floor book must pass, as a list of violations.

    Empty means the book passes. The checks are the ones E11-F13R registered:
    dollar neutrality, an exact hedge, a full idio share, no name below its
    floor in the final weights, and at least three times the design width in
    kept names so the exact FMP hedge keeps its rank margin.
    """
    violations: list[str] = []
    finalize = finalize_kept_set(
        keep, names, alpha_vec, design, factor_covariance, specific, close, nav
    )
    idx = np.asarray(finalize["idx"], dtype=int)
    w_sub = np.asarray(finalize["w_sub"], dtype=float)
    shares = np.asarray(finalize["shares"], dtype=int)
    prices = np.asarray(finalize["prices"], dtype=float)
    decomp = _decomposition(w_sub, design[idx], factor_covariance, specific[idx])
    gross = float(np.abs(w_sub).sum())
    net_share = abs(float(w_sub.sum())) / gross if gross > 0 else 0.0
    if net_share > 0.01:
        violations.append(f"net dollar is {net_share:.6f} of gross, above 0.01")
    if float(decomp["max_abs_exposure"]) > 1e-12:
        violations.append(
            f"worst post-hedge exposure is {decomp['max_abs_exposure']:.3e}, "
            f"above 1e-12"
        )
    if abs(float(decomp["idio_share"]) - 1.0) > 1e-9:
        violations.append(f"idio share is {decomp['idio_share']:.6f}, not 1.0")
    below = int(below_floor(shares, prices, dollar_floor, share_floor).sum())
    if below:
        violations.append(f"{below} kept names are below their floor")
    if int(keep.sum()) < min_names:
        violations.append(
            f"{int(keep.sum())} kept names, below the {min_names} name rank margin"
        )
    return violations


def _expected_establishment_cost(
    weights: np.ndarray,
    names: list[str],
    specific: np.ndarray,
    aum: float,
    root: Path,
) -> float:
    """The E9 transaction cost of building the book from flat, in bps of AUM."""
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    spread = costs_mod.spread_schedule(prices, root)
    adv = costs_mod._adv_per_ticker(prices)
    sigma = np.sqrt(np.maximum(specific, 1e-12))
    spread_map = spread.reindex(names).fillna(spread.median()).to_numpy(dtype=float)
    adv_map = adv.reindex(names).fillna(adv.median()).to_numpy(dtype=float)
    fraction = costs_mod._trade_cost(
        weights, spread_map, sigma, adv_map, aum, costs_mod.IMPACT_K
    )
    return float(fraction) * 1e4


def _shares_as_of(shares: pd.DataFrame, as_of: pd.Timestamp) -> pd.Timestamp:
    """The latest share count dated on or before the close.

    A count filed the day after the close it prices is look-ahead, so the
    reported as-of is clamped to the close and never the global maximum.
    """
    dates = pd.to_datetime(shares["date"])
    valid = dates[dates <= as_of]
    if valid.empty:
        raise ValueError(f"no share count on or before the close {as_of.date()}")
    return pd.Timestamp(valid.max())


def _latest_on_or_before(dates: pd.DatetimeIndex, as_of: pd.Timestamp) -> str:
    """The latest date on or before the close, as an ISO date string.

    A model input dated after the close it prices is look-ahead, so every
    input's as-of is clamped to the close rather than reported at the global
    maximum, which would claim data the proposal does not read.
    """
    valid = dates[dates <= as_of]
    stamp = pd.Timestamp(valid.max()) if len(valid) else as_of
    return str(stamp.date())


def _input_as_of(root: Path, as_of: pd.Timestamp) -> dict[str, str]:
    """The as-of date of every model input the proposal reads, one field each.

    Every input is dated at the latest value on or before the close, never
    the day after it, because a value filed after the close it prices is
    look-ahead against the standing no-look-ahead rule.
    """
    prices_frame = pd.read_parquet(root / "raw" / "prices.parquet")
    price_dates = pd.DatetimeIndex(prices_frame.index.get_level_values("date").unique())
    shares = pd.read_parquet(root / "raw" / "shares_history.parquet")
    shares_as_of = _shares_as_of(shares, as_of)
    sectors = pd.read_parquet(root / "processed" / "sectors.parquet")
    sector_dates = pd.DatetimeIndex(pd.to_datetime(sectors["as_of"]).unique())
    descriptors = pd.read_parquet(root / "models" / "XS-v1" / "descriptors.parquet")
    descriptor_dates = pd.DatetimeIndex(pd.to_datetime(descriptors["date"]).unique())
    factor_returns = pd.read_parquet(
        root / "models" / "XS-v1" / "factor_returns.parquet"
    )
    factor_dates = pd.DatetimeIndex(pd.to_datetime(factor_returns["date"]).unique())
    specific_returns = pd.read_parquet(
        root / "models" / "XS-v1" / "specific_returns.parquet"
    )
    specific_return_dates = pd.DatetimeIndex(
        pd.to_datetime(specific_returns["date"]).unique()
    )
    specific_var = pd.read_parquet(root / "models" / "XS-v1" / "specific_var.parquet")
    specific_var_dates = pd.DatetimeIndex(pd.to_datetime(specific_var["date"]).unique())
    factor_last = _latest_on_or_before(factor_dates, as_of)
    return {
        "prices": _latest_on_or_before(price_dates, as_of),
        "shares": str(shares_as_of.date()),
        "sectors": _latest_on_or_before(sector_dates, as_of),
        "descriptors": _latest_on_or_before(descriptor_dates, as_of),
        "factor_returns": factor_last,
        "specific_returns": _latest_on_or_before(specific_return_dates, as_of),
        "factor_cov": factor_last,
        "specific_var": _latest_on_or_before(specific_var_dates, as_of),
    }


def _close_prices(as_of: pd.Timestamp, root: Path) -> dict[str, float]:
    """{ticker: close} at the proposal close, for the quantization report."""
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    day = prices[prices.index.get_level_values("date") == as_of]
    close = day["close"].droplevel("date") if not day.empty else pd.Series(dtype=float)
    return {str(ticker): float(value) for ticker, value in close.items()}


def _cost_decomposition(
    weights: np.ndarray,
    names: list[str],
    specific: np.ndarray,
    nav: float,
    root: Path,
) -> dict[str, float]:
    """The establishment cost split into spread, impact, commission and borrow.

    Each component is in basis points of the paper NAV. Borrow is the
    annualized rate on the short leg over one rebalance horizon, the same
    horizon E6's per-rebalance number uses.
    """
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    spread = costs_mod.spread_schedule(prices, root)
    adv = costs_mod._adv_per_ticker(prices)
    sigma = np.sqrt(np.maximum(specific, 1e-12))
    spread_map = spread.reindex(names).fillna(spread.median()).to_numpy(dtype=float)
    adv_map = adv.reindex(names).fillna(adv.median()).to_numpy(dtype=float)
    dollar_trade = np.abs(weights) * nav
    impact = (
        costs_mod.IMPACT_K
        * sigma
        * np.sqrt(np.maximum(dollar_trade, 0.0) / np.maximum(adv_map, 1.0))
    )
    spread_bps = float(np.sum(spread_map * np.abs(weights))) * 1e4
    commission_bps = float(np.sum(costs_mod.COMMISSION * np.abs(weights))) * 1e4
    impact_bps = float(np.sum(impact * np.abs(weights))) * 1e4
    short_gross = float(np.maximum(-weights, 0.0).sum())
    borrow_bps = costs_mod.BORROW_RATE * short_gross * (HORIZON / TRADING_DAYS) * 1e4
    total = spread_bps + commission_bps + impact_bps + borrow_bps
    notional = float(np.abs(weights).sum()) * nav
    n_traded = int((np.abs(weights) > 1e-12).sum())
    return {
        "spread_bps": spread_bps,
        "impact_bps": impact_bps,
        "commission_bps": commission_bps,
        "borrow_bps": borrow_bps,
        "total_bps": total,
        "notional": notional,
        # The average trade size divides by the number of names that actually
        # trade, not by the full name list: a book with a dropped tail must not
        # understate the average position (E11-F2).
        "avg_trade_size": notional / n_traded if n_traded else 0.0,
    }


def build_proposal(
    data_root: Path = DATA_ROOT,
    as_of: pd.Timestamp | None = None,
    nav: float = PAPER_NAV,
    store: bool = True,
    appendix: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Build tomorrow's target book and write the dated proposal artifacts.

    Returns the proposal manifest: the universe source and seam, the as-of
    date of every model input and the max staleness, the decomposition
    after the hedge, the achieved vol against the E10 target, the four-way
    E9 cost split, and the hashes of every frozen input. `appendix` is the
    per-input state of the Postgres appendix the run was priced from, so a
    proposal always names the appendix rows behind it (E11-F15).
    """
    if nav is None or not math.isfinite(nav) or nav <= 0:
        raise ValueError(
            "nav must be a finite positive number; a proposal with a null "
            "nav is a failed run"
        )
    root = Path(data_root)
    universe, spy_path = load_spy_universe(root)
    universe_as_of = str(pd.to_datetime(universe["as_of"].iloc[0]).date())
    spy_tickers = sorted(universe["ticker"].astype(str).str.upper().str.strip())

    wide, _counts = eval_risk.load_clean_wide(root)
    as_of_ts = pd.Timestamp(as_of) if as_of is not None else wide.index.max()
    wide_names = [str(column) for column in wide.columns]
    names = [ticker for ticker in spy_tickers if ticker in wide_names]
    excluded = [ticker for ticker in spy_tickers if ticker not in wide_names]
    if len(names) < MIN_NAMES:
        raise ValueError(
            f"the SPY universe overlaps the frozen model on only {len(names)} "
            f"names, below the {MIN_NAMES} floor"
        )

    pieces = eval_risk._xs_pieces(as_of_ts, names, root)
    if pieces is None:
        raise ValueError(f"no XS-v1 pieces available at {as_of_ts.date()}")
    design = pieces["design"]
    factor_covariance = pieces["factor_covariance"]
    specific = pieces["specific"]

    ic = _stored_ic(SIGNAL, root)
    neutral_ic = _stored_neutral_ic(SIGNAL, root)
    kappa = alpha_mod.KAPPA
    signal = alpha_mod.idio_momentum(root)
    day = signal.loc[pd.to_datetime(signal["date"]) == as_of_ts]
    if day.empty:
        raise ValueError(f"no {SIGNAL} signal row on {as_of_ts.date()}")
    raw = day.set_index("ticker")["signal"].reindex(names)
    z = (raw - raw.mean()) / raw.std(ddof=1)
    z = z.fillna(0.0).to_numpy(dtype=float)
    alpha_vec = np.where(
        np.isfinite(specific),
        ic * specific * z * kappa,
        ic * float(np.nanmedian(specific)) * z * kappa,
    )

    # Procedure 6.3: size on D^-1 alpha, then hedge factors with the exact
    # in-model FMPs. The hedge drives every factor exposure, styles and
    # sectors included, to zero to machine precision.
    weights = size.procedure_6_3(alpha_vec, design, factor_covariance, specific)
    weights, gross_cap_bound = _scale_to_target(
        weights, design, factor_covariance, specific
    )
    full_decomposition = _decomposition(weights, design, factor_covariance, specific)

    # The chosen construction, read from the registry rather than hardcoded:
    # share-only, a minimum of 20 whole shares per name, no dollar floor,
    # enforced on the final weights (E11-F13R). The kept set is the drop-only
    # fixed point, then names are admitted in the |w_i| / floor_i order while
    # the enlarged set's final weights still clear every kept name's floor,
    # repeated until a full cycle changes nothing. So the floor holds on the
    # vector that actually trades, not the pre-drop full-book weights.
    reg = registry.load(root / "models" / "registry.json")
    construction = registry.live_construction(reg, MODEL_VERSION)
    close = _close_prices(as_of_ts, root)
    started = time.perf_counter()
    enforced_keep, finalize, search = enforce_floor_by_drop_then_admit(
        names,
        alpha_vec,
        design,
        factor_covariance,
        specific,
        close,
        nav,
        weights,
        dollar_floor=construction["dollar_floor"],
        share_floor=construction["share_floor"],
    )
    floor_search_seconds = time.perf_counter() - started
    violations = floor_book_violations(
        enforced_keep,
        names,
        alpha_vec,
        design,
        factor_covariance,
        specific,
        close,
        nav,
        dollar_floor=construction["dollar_floor"],
        share_floor=construction["share_floor"],
    )
    if violations:
        raise ValueError(
            "the enforced floor book fails its checks and must not trade: "
            + "; ".join(violations)
        )
    n_dropped = len(names) - int(enforced_keep.sum())
    n_selected = int(enforced_keep.sum())
    kept_gross_before_renorm = float(np.abs(weights[enforced_keep]).sum())
    weights = np.zeros(len(names), dtype=float)
    weights[np.asarray(finalize["idx"], dtype=int)] = np.asarray(
        finalize["w_sub"], dtype=float
    )

    kept_decomposition = _decomposition(weights, design, factor_covariance, specific)

    cost = _cost_decomposition(weights, names, specific, nav, root)

    kept_rows = pd.DataFrame({"ticker": names, "weight": weights})
    kept_rows = kept_rows.loc[kept_rows["weight"].abs() > 1e-12].reset_index(drop=True)
    quantization = alpaca.whole_share_quantization(
        kept_rows, _close_prices(as_of_ts, root), nav
    )

    input_as_of = _input_as_of(root, as_of_ts)
    input_as_of["universe"] = universe_as_of
    staleness = max(
        (as_of_ts - pd.Timestamp(value)).days for value in input_as_of.values()
    )

    manifest: dict[str, object] = {
        "signal": SIGNAL,
        "as_of": str(as_of_ts.date()),
        "appendix": appendix or {},
        "universe_source": str(spy_path.relative_to(root)),
        "universe_as_of": universe_as_of,
        "n_names": len(names),
        "n_excluded": len(excluded),
        "excluded": excluded,
        "ic": ic,
        "kappa": kappa,
        "factor_neutral_ic_h21": neutral_ic["factor_neutral_ic_h21"],
        "factor_neutral_t_h21": neutral_ic["factor_neutral_t_h21"],
        "idio_share_after_fmp": full_decomposition["idio_share"],
        "max_abs_exposure_after_fmp": full_decomposition["max_abs_exposure"],
        "gross": full_decomposition["gross"],
        "net": full_decomposition["net"],
        "n_eff": full_decomposition["n_eff"],
        "n_nonzero": full_decomposition["n_nonzero"],
        "n_kept": n_selected,
        "n_effective": kept_decomposition["n_nonzero"],
        "n_dropped": n_dropped,
        "min_position_dollars": construction["dollar_floor"],
        "min_position_pct_of_nav": construction["dollar_floor"] / nav if nav else 0.0,
        "construction": construction["construction"],
        "construction_floor_dollars": (
            construction["dollar_floor"] if construction["dollar_floor"] > 0 else None
        ),
        "construction_floor_shares": (
            construction["share_floor"] if construction["share_floor"] > 0 else None
        ),
        "construction_top_n": None,
        "floor_iterated": construction["floor_iterated"],
        "floor_rule": "drop_then_admit",
        "n_kept_drop_only": search["n_drop_only"],
        "n_kept_one_pass_admission": search["n_one_pass_admission"],
        "floor_search_cycles": search["cycles"],
        "floor_search_passes": search["admit_passes"],
        "floor_search_admitted": search["admitted"],
        "floor_search_converged": search["converged"],
        "floor_search_seconds": floor_search_seconds,
        "code_commit": _git_commit(),
        "kept_gross_before_renorm": kept_gross_before_renorm,
        "n_eff_full": full_decomposition["n_eff"],
        "n_eff_kept": kept_decomposition["n_eff"],
        "kept_gross": kept_decomposition["gross"],
        "kept_net": kept_decomposition["net"],
        "kept_idio_share": kept_decomposition["idio_share"],
        "kept_max_abs_exposure": kept_decomposition["max_abs_exposure"],
        "max_kept_weight": float(np.max(np.abs(weights))),
        "kept_achieved_annual_vol": float(
            math.sqrt(
                kept_decomposition["idio_variance"]
                + kept_decomposition["factor_variance"]
            )
            * math.sqrt(TRADING_DAYS)
        ),
        "breadth_naive_bound": math.sqrt(460.0 / max(n_selected, 1)),
        "breadth_governing": math.sqrt(
            full_decomposition["n_eff"] / max(kept_decomposition["n_eff"], 1e-12)
        ),
        "quantization": quantization,
        "target_annual_vol": TARGET_ANNUAL_VOL,
        "achieved_annual_vol": float(
            math.sqrt(
                full_decomposition["idio_variance"]
                + full_decomposition["factor_variance"]
            )
            * math.sqrt(TRADING_DAYS)
        ),
        "gross_cap_bound": gross_cap_bound,
        "nav": nav,
        "expected_establishment_cost_bps": cost["total_bps"],
        "expected_establishment_cost_usd": cost["total_bps"] / 1e4 * nav,
        "cost_breakdown_bps": {
            "spread": cost["spread_bps"],
            "impact": cost["impact_bps"],
            "commission": cost["commission_bps"],
            "borrow": cost["borrow_bps"],
            "total": cost["total_bps"],
        },
        "notional": cost["notional"],
        "avg_trade_size": cost["avg_trade_size"],
        "input_as_of": input_as_of,
        "max_input_staleness_days": staleness,
        "input_hashes": {
            artifact: hash_file(root / artifact) for artifact in INPUT_ARTIFACTS
        },
    }

    if store:
        PROPOSAL_DIR.mkdir(parents=True, exist_ok=True)
        stamp = str(as_of_ts.date())
        rows = pd.DataFrame(
            {
                "ticker": names,
                "weight": weights,
                "side": np.where(weights >= 0, "long", "short"),
                "z": z,
                "alpha": alpha_vec,
            }
        )
        rows = rows.loc[rows["weight"].abs() > 1e-12].reset_index(drop=True)
        rows.to_parquet(PROPOSAL_DIR / f"proposal_{stamp}.parquet", index=False)
        manifest_path = PROPOSAL_DIR / f"proposal_{stamp}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    return manifest


def main() -> int:
    """The cron entrypoint: build the proposal, nothing executes."""
    manifest = build_proposal()
    print(
        f"proposal {manifest['as_of']}: {manifest['n_names']} names, "
        f"idio share after FMP {manifest['idio_share_after_fmp']:.4f}, "
        f"gross {manifest['gross']:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
