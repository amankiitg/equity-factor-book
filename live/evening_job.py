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
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from efb import alpha as alpha_mod
from efb import costs as costs_mod
from efb import eval_risk, race, registry, size
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
# The floor a name with no usable close has to fall through before the run stops.
# A kept name the vendor did not answer for is dropped from the book and named in
# the email (`dropped_for_no_price`), because one missing print is not a reason to
# send no orders at all. Below this many priced names the book cannot be built, and
# a stub is worse than a stopped evening, so the run refuses instead.
MIN_PRICED_NAMES = 100

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


def _archive_date(path: Path) -> pd.Timestamp:
    """The date in an archive's file name, `spy_holdings_<yyyy-mm-dd>.parquet`.

    The name is the snapshot date by construction: `spy.archive_snapshot` stamps
    the file with the `as_of` it just fetched. A name that will not parse is a
    failed read, not a file to skip quietly.
    """
    stamp = pd.to_datetime(path.stem.rsplit("_", 1)[-1], errors="coerce")
    if pd.isna(stamp):
        raise ValueError(f"SPY archive {path.name} does not carry a date")
    return pd.Timestamp(stamp).normalize()


def load_spy_universe(
    data_root: Path | None = None, as_of: pd.Timestamp | None = None
) -> tuple[pd.DataFrame, Path]:
    """The live universe from the SPY archive, asserted rather than assumed.

    The universe is the **newest archive dated on or before the close being
    priced**, so the book cannot read a holdings snapshot filed after the close
    it claims to price. With no close given the newest archive is used, which is
    the live path's own answer (`as_of` defaults to the latest data date).

    Two refusals, both loud. A file dated before the live-universe seam fails
    instead of silently falling back to the frozen history, and a close with no
    archive on or before it is refused rather than served a later one: a look-ahead
    universe is a wrong book, not a parse to be patched.
    """
    root = Path(data_root) if data_root is not None else DATA_ROOT
    archive_dir = root / "raw" / "spy_holdings"
    files = sorted(archive_dir.glob("spy_holdings_*.parquet"))
    if not files:
        raise FileNotFoundError(f"no SPY archive files under {archive_dir}")
    if as_of is not None:
        close = pd.Timestamp(as_of).normalize()
        allowed = [file for file in files if _archive_date(file) <= close]
        if not allowed:
            raise ValueError(
                f"no SPY archive dated on or before {close.date()}: the newest is "
                f"{files[-1].name} and it postdates the close being priced"
            )
        files = allowed
    path = files[-1]
    frame = pd.read_parquet(path)
    as_of_date = pd.to_datetime(frame["as_of"].iloc[0]).date()
    if as_of_date < SPY_UNIVERSE_MIN_AS_OF:
        raise ValueError(
            f"SPY archive {path.name} is dated {as_of_date}, before the live "
            f"universe seam {SPY_UNIVERSE_MIN_AS_OF}"
        )
    return frame, path


def universe_without_prices(
    data_root: Path | None = None, as_of: pd.Timestamp | None = None
) -> list[str]:
    """Current universe members with no price for the session being priced.

    A takeover, a halt or a stale archive can leave a name in the index with no
    print. It drops out of the book by construction, because the model needs its
    return, and that is the right answer: the run must not stop for it. What must
    not happen is the drop going unmentioned, because a book quietly smaller than
    the index is a book nobody can check. The names travel to the email.
    """
    root = Path(data_root) if data_root is not None else DATA_ROOT
    frame, _ = load_spy_universe(root, as_of=as_of)
    members = {str(name).upper().strip() for name in frame["ticker"]}
    prices = pd.read_parquet(root / "raw" / "prices.parquet", columns=["close"])
    dates = prices.index.get_level_values("date")
    if len(dates) == 0:
        return sorted(members)
    tonight = dates == pd.Timestamp(dates.max())
    priced = prices.index.get_level_values("ticker")[tonight]
    return sorted(members - {str(name).upper().strip() for name in priced})


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


def exposures(weights: np.ndarray, design: np.ndarray) -> np.ndarray:
    """A book's exposure to every design column: `X'w`, one value per column.

    The same arithmetic `_decomposition` uses to measure the worst exposure and
    the same design the hedge subtracts against, so the number the page shows is
    the number the hedge acts on rather than a second reconstruction of it.

    The design's column order is `fx.ESTIMATED_NAMES` (see
    `efb/race.py::_descriptor_design`), so the labels are that constant and the
    lengths have to agree; a mismatch would put the wrong name on a number, so it
    raises instead.
    """
    from efb.models import fundamental as fx

    vector = np.asarray(design.T @ weights, dtype=float)
    expected = len(fx.ESTIMATED_NAMES)
    if design.shape[1] != expected:
        raise ValueError(
            f"the design has {design.shape[1]} columns and the factor names "
            f"{expected}, so the exposures cannot be labelled"
        )
    return vector


def label_exposures(vector: np.ndarray) -> dict[str, float]:
    """One value per design column, keyed by `fx.ESTIMATED_NAMES`.

    Shared by both sides of the hedge: the vector either comes from
    `exposures(weights, design)` or straight from the hedge's own `X'w`, and the
    labels are the same either way.
    """
    from efb.models import fundamental as fx

    values = np.asarray(vector, dtype=float)
    if len(values) != len(fx.ESTIMATED_NAMES):
        raise ValueError(
            f"the exposure vector has {len(values)} entries and the factor names "
            f"{len(fx.ESTIMATED_NAMES)}, so they cannot be labelled"
        )
    return {
        str(name): float(value)
        for name, value in zip(fx.ESTIMATED_NAMES, values, strict=True)
    }


def labelled_exposures(weights: np.ndarray, design: np.ndarray) -> dict[str, float]:
    """`X'w` as a dict keyed by factor name, which is what the page shows."""
    return label_exposures(exposures(weights, design))


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
        "effective_breadth": (
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
) -> tuple[
    np.ndarray, list[str], np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray
]:
    """Procedure 6.3 on the kept subset, hedged and renormalized to gross 1.0.

    One implementation for the whole module: `finalize_kept_set` builds its
    report from this, and the floor search reads the same vector so a set that
    the search accepts is the set that trades.
    """
    del nav  # the renorm is to gross 1.0; the share counts take the NAV
    idx = np.where(keep)[0]
    names_sub = [names[i] for i in idx]
    # Size, cap the variance share, renormalize, then hedge and renormalize: the
    # cap has to sit before the hedge, because the hedge is a projection of the
    # sized vector and capping after it would undo the neutrality instead.
    sized = size.proportional(alpha_vec[idx], specific[idx])
    sized = sizing.cap_variance_shares(sized, specific[idx])
    sized = sizing.renormalize(sized, gross=1.0)
    w_sub, pre_hedge = sizing.procedure_6_3_hedged_with_exposures(
        alpha_vec[idx], design[idx], factor_covariance, specific[idx], sized=sized
    )
    w_sub = sizing.renormalize(w_sub, gross=1.0)
    prices = usable_prices(names_sub, close)
    return idx, names_sub, w_sub, prices, design[idx], specific[idx], pre_hedge


def close_prices_for(names: list[str], close: dict[str, float]) -> np.ndarray:
    """The names' closes at the proposal close, a name the map lacks read as 0.0."""
    return np.array([close.get(name, 0.0) for name in names], dtype=float)


def usable_close_prices(prices: np.ndarray) -> np.ndarray:
    """Which close prices a whole-share count can be built from.

    A NaN close cannot be divided into anything and a non-positive one makes the
    floor division in `kept_shares` unbounded, so neither is a price the book can
    be quantized on. One predicate, so the drop at the book and the refusal in the
    sizing cannot disagree about what "usable" means.
    """
    values = np.asarray(prices, dtype=float)
    return np.isfinite(values) & (values > 0.0)


def dropped_for_no_price(
    names: list[str], close: dict[str, float]
) -> tuple[np.ndarray, list[str]]:
    """The priced mask, and the names the book loses for having no usable close.

    A kept name with no usable close at the proposal close is dropped from the
    book rather than stopping the run, and the remaining names are priced,
    quantized and renormalized to gross 1.0 exactly as they are after the share
    floor. That is the rule the universe already follows one step upstream, where a
    member with no print tonight drops out of the book by construction: a book
    quietly smaller than the index is a book nobody can check, so the names travel
    to the email instead (`merged_no_price`).

    Tonight is why this exists: the price fetch answers for one symbol with a
    yfinance cache lock instead of a price, the model still knows the name from its
    history, and the whole evening used to stop on that single name.
    """
    priced = usable_close_prices(close_prices_for(names, close))
    dropped = [name for name, good in zip(names, priced, strict=True) if not good]
    return priced, dropped


def priced_names_or_stop(
    names: list[str],
    close: dict[str, float],
    min_priced: int = MIN_PRICED_NAMES,
) -> tuple[np.ndarray, list[str]]:
    """The drop for no price, and the floor that makes it a stop instead.

    The drop alone would build a book out of whatever the vendor answered for, and
    a stub of the universe is worse than an evening with no orders: the run would
    trade a book that is not the model's. So the drop is bounded, and falling
    through the bound names what went missing rather than reporting a count.
    """
    priced, dropped = dropped_for_no_price(names, close)
    n_priced = int(priced.sum())
    if n_priced < min_priced:
        shown = ", ".join(sorted(dropped)[:10])
        rest = "" if len(dropped) <= 10 else f" and {len(dropped) - 10} more"
        raise ValueError(
            f"only {n_priced} of {len(names)} names have a usable close at the "
            f"proposal close, below the {min_priced} name floor the book is built "
            f"from, so it cannot be built: no usable close price for {shown}{rest}"
        )
    return priced, dropped


def merged_no_price(
    reported: list[str] | None, manifest: Mapping[str, Any]
) -> list[str]:
    """The "dropped for no price" names: the universe's report plus the book's.

    Two rules reach the same email line and they are the same fact, that the index
    had no print for the name tonight: `universe_without_prices` finds the archive
    members the panel does not price, and `build_proposal` drops the kept names it
    cannot quantize. Naming them once, sorted and deduplicated, is what keeps the
    line readable as one statement about tonight.
    """
    names = {str(name) for name in (reported or [])}
    dropped = manifest.get("dropped_no_price")
    if isinstance(dropped, list):
        names |= {str(name) for name in dropped}
    return sorted(names)


def usable_prices(names_sub: list[str], close: dict[str, float]) -> np.ndarray:
    """The kept names' close prices, refusing any the book cannot be sized on.

    This is an invariant check now, not the run's own answer to a missing price:
    `build_proposal` drops the names with no usable close before it sizes the book
    (`dropped_for_no_price`), so a set reaching here with one of them did not come
    through that path. It still refuses rather than pricing the name on a
    placeholder, because `kept_shares` floors a division by the price.
    """
    prices = close_prices_for(names_sub, close)
    usable = usable_close_prices(prices)
    if not usable.all():
        unusable = [
            name for name, good in zip(names_sub, usable, strict=True) if not good
        ]
        shown = ", ".join(sorted(unusable)[:5])
        rest = "" if len(unusable) <= 5 else f" and {len(unusable) - 5} more"
        raise ValueError(
            f"no usable close price for {shown}{rest} at the proposal close: a "
            "kept name with no price cannot be quantized to whole shares, so "
            "the run stops instead of pricing it"
        )
    return prices


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
    idx, names_sub, w_sub, prices, design_sub, specific_sub, pre_hedge = (
        sized_kept_weights(
            keep, names, alpha_vec, design, factor_covariance, specific, close, nav
        )
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
        # The pre-hedge exposure the hedge acted on, straight from the sizing
        # step's own `X'w`, so the page and the hedge cannot disagree.
        "pre_hedge_exposures": pre_hedge,
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
    (
        _idx,
        _names_sub,
        w_sub,
        prices,
        _design_sub,
        _specific_sub,
        _pre_hedge,
    ) = sized_kept_weights(
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


def floor_order_within(
    close: dict[str, float],
    names: list[str],
    full_weights: np.ndarray,
    dollar_floor: float,
    share_floor: int,
    within: np.ndarray,
) -> np.ndarray:
    """`floor_order` over a subset of the book, as indices into the whole book.

    A name outside the subset has no close, so it has no floor of its own: with a
    zero dollar floor its threshold is zero and `|w_i| / floor_i` is a division by
    zero rather than a rank. The order this returns is the order the whole-book
    call gives that same subset, so it is the ordering the floor rule searches,
    restricted to the names the rule may keep.
    """
    subset = np.where(np.asarray(within, dtype=bool))[0]
    ordered = floor_order(
        close,
        [names[index] for index in subset],
        np.asarray(full_weights, dtype=float)[subset],
        dollar_floor,
        share_floor,
    )
    return subset[np.asarray(ordered, dtype=int)]


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
    start: np.ndarray | None = None,
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

    `start` is the set the book may be built from: the whole universe by default,
    and tonight's priced names in the live path. A name outside it is never kept
    and never admitted, because the run drops a name it cannot quantize before it
    sizes anything and the search cannot even finalize a set holding one.
    """
    if start is None:
        all_names = np.ones(len(names), dtype=bool)
    else:
        all_names = np.asarray(start, dtype=bool).copy()
        if all_names.shape != (len(names),):
            raise ValueError(
                f"the start set has {all_names.size} entries and the book "
                f"{len(names)} names, so they cannot be aligned"
            )
    if order is None:
        order = floor_order_within(
            close, names, full_weights, dollar_floor, share_floor, all_names
        )
    else:
        ordered = np.asarray(order, dtype=int)
        order = ordered[all_names[ordered]]
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


def _adv_maps(
    names: list[str], root: Path
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """The ADV to price each name on, and the names whose ADV is not known.

    The trailing quarter's median dollar volume, with a zero or absent value
    filled from the panel's median - the same treatment for both, because a
    name with no trade data and a name with no volume are the same missing
    input, and `np.maximum(adv, 1.0)` used to turn the second into a dollar of
    ADV, which is the most expensive liquidity a name can have.

    Returns the map, the raw trailing ADV (NaN where unknown), and the kept
    names whose own liquidity is unknown or thin, so the owner is told which
    cost in the book is a median rather than a measurement.
    """
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    raw = costs_mod.trailing_adv(prices).reindex(names)
    filled = raw.fillna(raw.median()).to_numpy(dtype=float)
    thin = [
        {"ticker": name, "adv_usd": None if pd.isna(value) else float(value)}
        for name, value in raw.items()
        if pd.isna(value) or float(value) < THIN_ADV_USD
    ]
    return filled, raw.to_numpy(dtype=float), thin


# A name whose trailing dollar volume is below this is named in the email even
# when the median stands in for it: a $1M ADV name is not a name this book can
# trade a 5% position in without moving it.
THIN_ADV_USD = 1_000_000.0


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
    adv_map, _raw, _thin = _adv_maps(names, root)
    sigma = np.sqrt(np.maximum(specific, 1e-12))
    spread_map = spread.reindex(names).fillna(spread.median()).to_numpy(dtype=float)
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
    previous: np.ndarray | None = None,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """The establishment cost split into spread, impact, commission and borrow.

    Each component is in basis points of the paper NAV. Borrow is the
    annualized rate on the short leg over one rebalance horizon, the same
    horizon E6's per-rebalance number uses.

    The impact is the cost of the *trade*, so its dollar amount is the change in
    weight - from flat on the establishment day, which is why the number is
    unchanged there, and the difference from the last book afterwards. The other
    three components still scale with the book that is held: they are the cost of
    owning the position for the horizon, not of establishing it, and they are
    named as such until the owner says otherwise.

    Returns the components and the names whose own ADV is unknown or thin.
    """
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    spread = costs_mod.spread_schedule(prices, root)
    adv_map, _raw, thin = _adv_maps(names, root)
    sigma = np.sqrt(np.maximum(specific, 1e-12))
    spread_map = spread.reindex(names).fillna(spread.median()).to_numpy(dtype=float)
    held = (
        np.asarray(previous, dtype=float)
        if previous is not None
        else np.zeros_like(weights)
    )
    dollar_trade = np.abs(weights - held) * nav
    impact = (
        costs_mod.IMPACT_K
        * sigma
        * np.sqrt(np.maximum(dollar_trade, 0.0) / np.maximum(adv_map, 1.0))
    )
    spread_bps = float(np.sum(spread_map * np.abs(weights))) * 1e4
    commission_bps = float(np.sum(costs_mod.COMMISSION * np.abs(weights))) * 1e4
    impact_bps = float(np.sum(impact * np.abs(weights - held))) * 1e4
    short_gross = float(np.maximum(-weights, 0.0).sum())
    borrow_bps = costs_mod.BORROW_RATE * short_gross * (HORIZON / TRADING_DAYS) * 1e4
    total = spread_bps + commission_bps + impact_bps + borrow_bps
    notional = float(np.abs(weights).sum()) * nav
    traded_notional = float(np.abs(weights - held).sum()) * nav
    n_traded = int((np.abs(weights - held) > 1e-12).sum())
    return (
        {
            "spread_bps": spread_bps,
            "impact_bps": impact_bps,
            "commission_bps": commission_bps,
            "borrow_bps": borrow_bps,
            "total_bps": total,
            # The book's own gross notional, which is what the page shows as the
            # book's size, beside the amount that actually trades.
            "notional": notional,
            "traded_notional": traded_notional,
            # The average trade size divides by the number of names that actually
            # trade, not by the full name list: a book with a dropped tail must not
            # understate the average position (E11-F2).
            "avg_trade_size": traded_notional / n_traded if n_traded else 0.0,
        },
        thin,
    )


def previous_book_exposure(
    as_of_ts: pd.Timestamp, previous: pd.Series | None, data_root: Path
) -> dict[str, object] | None:
    """The previous book's exposure under the row the model published for this close.

    The book written at the previous close was hedged against the design for
    *this* session, and that design had to be built at that close because the
    model had not published the row yet. The row it dates this session is in the
    artifact now, so this close is the first moment the number is knowable, and
    it is the real post-hedge exposure rather than the zero the run reports
    against the design it hedged with. E12 reads it from the stored manifest.

    That book is the one that traded, quantised to whole shares, so this number
    carries the quantisation too; it is the realized book's exposure, not the
    hedge's own vector. None on an establishment day, when no earlier book was
    held and there is nothing to measure.
    """
    if previous is None or len(previous) == 0:
        return None
    root = Path(data_root)
    names = [str(ticker) for ticker in previous.index]
    weights = np.asarray(previous.to_numpy(dtype=float), dtype=float)
    stamp = race.descriptor_stamp(as_of_ts, root)
    published = race._descriptor_design(as_of_ts, names, root)
    exposures = published.T @ weights
    return {
        "as_of": str(as_of_ts.date()),
        "published_row": None if stamp is None else str(pd.Timestamp(stamp).date()),
        "n_names": len(names),
        "max_abs_exposure": float(np.abs(exposures).max()),
        "exposures": label_exposures(exposures),
    }


def build_proposal(
    data_root: Path | None = None,
    as_of: pd.Timestamp | None = None,
    nav: float = PAPER_NAV,
    store: bool = True,
    appendix: dict[str, Any] | None = None,
    previous: pd.Series | None = None,
    nav_source: str | None = None,
) -> dict[str, object]:
    """Build tomorrow's target book and write the dated proposal artifacts.

    Returns the proposal manifest: the universe source and seam, the as-of
    date of every model input and the max staleness, the decomposition
    after the hedge, the achieved vol against the E10 target, the four-way
    E9 cost split, and the hashes of every frozen input. `appendix` is the
    per-input state of the Postgres appendix the run was priced from, so a
    proposal always names the appendix rows behind it (E11-F15).

    `previous` is the last book the loop held, keyed by ticker. The impact term
    is the cost of trading to this book rather than of owning it, so it needs
    that book; from flat (the establishment day) every previous weight is zero.
    """
    if nav is None or not math.isfinite(nav) or nav <= 0:
        raise ValueError(
            "nav must be a finite positive number; a proposal with a null "
            "nav is a failed run"
        )
    root = Path(data_root) if data_root is not None else DATA_ROOT
    # The close comes first, because the universe is clamped to it: a holdings
    # snapshot filed after the close must not inform the book priced on it.
    wide, _counts = eval_risk.load_clean_wide(root)
    as_of_ts = pd.Timestamp(as_of) if as_of is not None else wide.index.max()
    universe, spy_path = load_spy_universe(root, as_of=as_of_ts)
    universe_as_of = str(pd.to_datetime(universe["as_of"].iloc[0]).date())
    spy_tickers = sorted(universe["ticker"].astype(str).str.upper().str.strip())
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
    # The contract, from the one place it lives: alpha_i = IC x sigma_i x
    # z_i x kappa, with sigma the specific volatility, the square root of the
    # specific variance the model stores.
    alpha_vec = alpha_mod.alpha_from_contract(ic, specific, z, kappa)

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
    # A name the book cannot be quantized on is dropped, not fatal: the rest are
    # priced, hedged, quantized and renormalized to gross 1.0 without it, and the
    # names travel to the email on the same "dropped for no price" line as the
    # universe members with no print tonight. Only a book that cannot be built at
    # all stops the run, which is the floor below.
    priced, dropped_no_price = priced_names_or_stop(names, close)
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
        start=priced,
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

    # The traded book, name by name, with each name's specific variance and its
    # share of the book's predicted specific variance. S1's alpha-contract
    # comparison reads these rather than re-deriving the book, and the page's
    # risk block is built from the same numbers.
    variance_shares = sizing.variance_shares(weights, specific)
    kept_indices = np.where(np.abs(weights) > 1e-12)[0]
    by_share = sorted(
        ((str(names[index]), float(variance_shares[index])) for index in kept_indices),
        key=lambda pair: -pair[1],
    )
    top_variance_shares = [
        {"ticker": ticker, "variance_share": share} for ticker, share in by_share[:5]
    ]
    max_variance_share = float(variance_shares.max()) if len(names) else 0.0
    variance_share_cap_binds = bool(
        max_variance_share >= sizing.VARIANCE_SHARE_CAP - 1e-12
    )

    previous_weights = (
        previous.reindex(names).fillna(0.0).to_numpy(dtype=float)
        if previous is not None
        else None
    )
    cost, thin_adv = _cost_decomposition(
        weights, names, specific, nav, root, previous_weights
    )

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
        # The names tonight's book lost for having no usable close, and the floor
        # they would have to fall through to stop the run. They are named in the
        # email beside the universe members with no print, because both are the
        # same fact about tonight and a book quietly smaller than the index is a
        # book nobody can check.
        "n_dropped_no_price": len(dropped_no_price),
        "dropped_no_price": dropped_no_price,
        "min_priced_names": MIN_PRICED_NAMES,
        "ic": ic,
        "kappa": kappa,
        "factor_neutral_ic_h21": neutral_ic["factor_neutral_ic_h21"],
        "factor_neutral_t_h21": neutral_ic["factor_neutral_t_h21"],
        "idio_share_after_fmp": full_decomposition["idio_share"],
        "max_abs_exposure_after_fmp": full_decomposition["max_abs_exposure"],
        # Which design row the hedge was built against. The exposures the book
        # earns are the ones the session after this close carries, so the hedge
        # uses the row the model will date with that session, built here when the
        # model has not published it yet. Recording the vintage is what lets a
        # reader tell the two apart, and it is the only place the difference is
        # visible: `exposures_after_hedge` below is zero against whichever design
        # was used, by construction.
        "hedge_design_vintage": str(pieces["design_vintage"]),
        # The previous book's exposure under the row the model has now published
        # for this session: the real number for the hedge built last night, one
        # session later, since nothing earlier can know it.
        "previous_book_exposure_vs_published": previous_book_exposure(
            as_of_ts, previous, root
        ),
        "gross": full_decomposition["gross"],
        "net": full_decomposition["net"],
        # X'w after the hedge, one value per design column, named by
        # fx.ESTIMATED_NAMES: the hedge neutralizes every factor, so these are zero
        # to within floating point, which the test pins below 1e-10. The BEFORE
        # vector is the hedge's own pre-hedge `X'w`, taken from the sizing step
        # rather than reconstructed here, and it is clearly nonzero.
        "exposures_before_hedge": label_exposures(finalize["pre_hedge_exposures"]),
        "exposures_after_hedge": labelled_exposures(weights, design),
        "n_eff_kept": kept_decomposition["effective_breadth"],
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
        "n_eff_full_book": full_decomposition["effective_breadth"],
        "kept_gross": kept_decomposition["gross"],
        "kept_net": kept_decomposition["net"],
        "kept_idio_share": kept_decomposition["idio_share"],
        "kept_max_abs_exposure": kept_decomposition["max_abs_exposure"],
        "max_kept_weight": float(np.max(np.abs(weights))),
        # The traded book, name by name, so a reader (or the S1 comparison) does
        # not have to re-derive it, plus its concentration reading: the cap binds
        # when a name sits at or above VARIANCE_SHARE_CAP of the book's predicted
        # specific variance.
        "kept_book": [
            {
                "ticker": str(names[index]),
                "weight": float(weights[index]),
                "specific_variance": float(specific[index]),
                "variance_share": float(variance_shares[index]),
            }
            for index in kept_indices
        ],
        "variance_share_cap": float(sizing.VARIANCE_SHARE_CAP),
        "max_variance_share": max_variance_share,
        "variance_share_cap_binds": variance_share_cap_binds,
        "top_variance_shares": top_variance_shares,
        "kept_achieved_annual_vol": float(
            math.sqrt(
                kept_decomposition["idio_variance"]
                + kept_decomposition["factor_variance"]
            )
            * math.sqrt(TRADING_DAYS)
        ),
        "breadth_naive_bound": math.sqrt(460.0 / max(n_selected, 1)),
        "breadth_governing": math.sqrt(
            full_decomposition["effective_breadth"]
            / max(kept_decomposition["effective_breadth"], 1e-12)
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
        # Which number `nav` is. The evening sizes the book from the account's
        # own equity now, and the design's paper default stands in only when the
        # account could not be read at all; the manifest states which of the two
        # it priced from rather than leaving it to be assumed.
        "nav_source": nav_source
        or f"the paper default ${PAPER_NAV:,.0f}, passed in rather than read",
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
        "traded_notional": cost["traded_notional"],
        "avg_trade_size": cost["avg_trade_size"],
        # The kept names whose own trailing ADV is unknown or below $1M, so the
        # owner can see which part of the cost above is a median standing in for
        # a measurement. An empty list is a book whose liquidity was measured.
        "thin_adv": thin_adv,
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
