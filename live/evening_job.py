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
import logging
import math
import os
import subprocess
import time
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from efb import alpha as alpha_mod
from efb import costs as costs_mod
from efb import eval_risk, race, registry, size
from efb.build import hash_file
from live import alpaca, cadence, sizing

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
PROPOSAL_DIR = ROOT / "live" / "proposals"

logger = logging.getLogger(__name__)

SIGNAL = "idio_momentum"
MODEL_VERSION = "XS-v1"  # the champion the book is built and run under
SPY_UNIVERSE_MIN_AS_OF = date(2026, 9, 18)  # the live-universe seam
TARGET_ANNUAL_VOL = 0.10  # the E10 target
GROSS_CAP = 1.0  # the E8 gross cap, a hard ceiling
PAPER_NAV = 1_000_000.0  # the paper notional the morning job runs
# Which hedge the loop builds: the exact FMP hedge it has always built, or the
# research construction that caps the variance shares and re-projects onto the
# factor-neutral space until both hold (docs/flag_cap_then_rehedge.md). Unset and
# `exact` are the same thing and produce the book byte for byte; anything else is
# a typo and falls back to `exact` with a warning, because a typo must never change
# the book. The mode is recorded on the manifest so a later reader can tell which
# hedge built a book.
HEDGE_MODE_ENV = "EFB_HEDGE_MODE"
HEDGE_MODE_EXACT = "exact"
HEDGE_MODE_CAP_THEN_REHEDGE = "cap_then_rehedge"
REFERENCE_AUM = 1e8  # the capacity-curve reference, kept for the E6 finding
TRADING_DAYS = 252
logger = logging.getLogger(__name__)

HORIZON = 21  # the rebalance horizon, the E6 and E9 convention
MIN_NAMES = 50

# The floor's release band, off by default (`1.0` is "release at the floor", which is
# the rule the book has always used).
#
# The kept set is the drop-then-admit fixed point on tonight's own weights, so a name
# sitting on the floor line flips in and out as its weight moves a few dollars: of the
# 39 names that left on 2026-10-07, 16 had been admitted on 10-06, and 5 of the 24
# that arrived had been dropped the day before (item 12). Each round trip is two
# crossings of the spread and the impact on a leg that was already at its target size.
# With the band on, a name the book *holds* is released only below `release` of its
# floor, and a name being admitted still has to clear the whole floor: entry at the
# floor, exit below it.
#
# Item 12's measurement (docs/research/nov11_turnover.md) is that the floor's own churn
# was 147 round trips in nine closes, 84 of which returned the next session, costing
# 6.6 bp of NAV against a 0.67 bp per-session gross edge - so the band is worth
# building, and its width is the owner's to set rather than this module's.
#
# Measured before shipping, on the live construction of 2026-09-21 with the previous
# book its own default book (`tests/test_nov11_floor_band.py` builds it): switching the
# band on at 0.75 does **not** hold the same book with fewer legs. Keeping the names
# inside the band changes the kept set - 200 kept against 204, 14 names in and 18 out -
# and the renormalization that follows pushes other names below their own floor, so the
# book trades 15.6% of gross where the default trades none at all. The band therefore
# is not by itself the churn cut the item expects; the shape that is (a no-trade band at
# the *leg* stage, which leaves the target alone and suppresses the closing leg of a
# position inside the band) is a decision for the owner, recorded in the report and in
# the research note. It stays off until then, and the identity proof is that off the
# book is identical weight for weight.
FLOOR_RELEASE_ENV = "EFB_FLOOR_RELEASE"
FLOOR_RELEASE_OFF = 1.0
# Below half the floor a "held" name is not a position, it is a rounding error: the
# band exists to stop trading a name that is at its size, not to keep a stub forever.
FLOOR_RELEASE_MIN = 0.5


# Item 18's precheck, off by default: with it on, the run reads the broker's own
# `shortable` flag for the universe *before* the sizing and leaves out the names the
# broker will not lend, so the book it publishes is one it can hold. Off, the flags are
# read where they always were - as each short leg is built - and the book can carry a
# name whose short will be refused.
#
# It changes the book, so it is a flag and not a fix: with it on, a name the broker
# will not lend leaves the book before the hedge and the floor, which moves the
# published book, its breadth and its forecast. Everything else about the run is
# unchanged, and `/tests/test_nov11_shortability.py` proves the off direction is
# identity: no source injected, no name dropped, the book identical weight for weight.
SHORTABILITY_ENV = "EFB_SHORTABILITY_PRECHECK"


def resolve_shortability_precheck(value: str | None) -> bool:
    """Whether the run checks the broker's lending flags before it sizes.

    Opens only on the exact string "true", the same convention as the trading
    window's override and for the same reason: a missing, empty or mistyped variable
    must leave the book exactly as it is rather than silently change which names it
    holds.
    """
    return value == "true"


def drop_not_shortable(
    names: list[str], weights: np.ndarray, shortable: dict[str, bool]
) -> tuple[np.ndarray, list[dict[str, object]]]:
    """Which names to keep, and the ones the broker will not lend, to be dropped.

    A name is dropped when the sizing puts it on the **short** side and the broker's
    own flag says it cannot be shorted. Three cases are kept, and each matters:

    - a name the sizing puts *long*: its own shortability is irrelevant tonight;
    - a ticker **absent** from the mapping: the feed did not answer for it, and an
      unanswered read is not a refusal - the leg-time check still guards it;
    - a flag of `True` that is wrong by tomorrow: the flags are a point-in-time read,
      which is why the leg-time check stays where it is.
    """
    keep = np.ones(len(names), dtype=bool)
    dropped: list[dict[str, object]] = []
    for index, name in enumerate(names):
        ticker = str(name)
        if weights[index] >= 0:
            continue
        if shortable.get(ticker, True):
            continue
        keep[index] = False
        dropped.append(
            {
                "ticker": ticker,
                "reason": "the broker's feed reports shortable=false",
                "weight": float(weights[index]),
            }
        )
    return keep, dropped


def resolve_floor_release(value: str | None) -> float:
    """The band's release fraction from the environment, or `1.0` when unset.

    Unset is off, and so is any value that cannot be read as a fraction in
    `[0.5, 1.0)` - the safe direction for a switch that changes which names the book
    holds: a mistyped variable must leave the book exactly as it is, not silently pick
    a band. A value of exactly `1.0` is off as well, and is the same as unset.
    """
    if value is None or not str(value).strip():
        return FLOOR_RELEASE_OFF
    try:
        parsed = float(str(value).strip())
    except ValueError:
        logger.warning("ignoring %s=%r: not a number", FLOOR_RELEASE_ENV, value)
        return FLOOR_RELEASE_OFF
    if not math.isfinite(parsed) or parsed < FLOOR_RELEASE_MIN or parsed > 1.0:
        logger.warning(
            "ignoring %s=%r: outside [%s, 1.0]",
            FLOOR_RELEASE_ENV,
            value,
            FLOOR_RELEASE_MIN,
        )
        return FLOOR_RELEASE_OFF
    return parsed


# How many names one evening may lose for having no usable close before the run
# stops and emails instead of pricing the rest. One or a few is normal: a name can
# halt, delist or be missed by the vendor on the night, and the book drops it and
# prices the others. Ten at once is not that, it is the fetch having broken, and a
# book built from whatever the fetch did answer for would be a different, more
# concentrated book than the model's, not a slightly smaller one. A floor on the
# priced count would be the wrong instrument: the book targets roughly 180 names
# and needs its rank margin, so 100 priced names is not a diminished book but
# another one.
MAX_PRICE_DROPS = 10
# How many names one evening may lose for having no risk estimate before the run
# stops and emails instead of sizing the rest. A name with a short history has no
# estimate until it does: Q, FDXF and HONA were the three on 2026-10-07, all
# recently listed or spun off, and dropping them is the right answer rather than a
# failure. A dozen at once is not that, it is the specific-variance artifact having
# gone missing, stale or truncated, and a book sized from whatever the diagonal did
# answer for would be a different book, not a smaller one.
MAX_RISK_DROPS = 10

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


def forced_names_for_hold(
    manifest: Mapping[str, Any],
    splits: Iterable[Any] | None = None,
    spinoffs: Iterable[Any] | None = None,
) -> set[str]:
    """Every name a hold day may still trade, and nothing else.

    A hold day publishes the book it already holds, so the only legs that may be
    sent are the ones the book cannot avoid keeping:

    - **left universe** - a held name the proposal no longer carries. The order
      path emits it as a close, and it is not in this set because it is not in the
      proposal at all; it is named here only if the manifest says so.
    - **corporate action** - a split or a spin-off that moved the day's cash or
      share count. `splits` and `spinoffs` are the run's own record of what it
      applied tonight.
    - **not shortable** - a name the broker's lending feed refused, which the
      precheck dropped before the sizing (`dropped_no_short`).
    - **no risk estimate** - a name the model cannot measure, dropped before the
      sizing (`dropped_no_risk`); the book cannot state its risk, so it cannot be
      held on purpose.
    - **no usable close** - a name with no price to quantize on
      (`dropped_no_price`).
    - **reversal** - a position the account and the book disagree about in sign.
      The order path closes it and defers the other side; the filter lets a sign
      flip through without needing a name here.

    The list is what the run's record states as `hold_forced_names`, so a quiet
    evening can be told from an evening whose hold was quietly skipped.
    """
    forced = {str(name) for name in (splits or [])}
    forced |= {str(name) for name in (spinoffs or [])}
    for key in ("dropped_no_short", "dropped_no_risk"):
        entries: list[Any] = list(cast(list[Any], manifest.get(key) or []))
        for row in entries:
            ticker = row.get("ticker") if isinstance(row, Mapping) else row
            if ticker:
                forced.add(str(ticker))
    for key in ("dropped_no_price", "left_universe"):
        values: list[Any] = list(cast(list[Any], manifest.get(key) or []))
        for name in values:
            forced.add(str(name))
    return forced


def _completed_rebalances(data_root: Path) -> list[str] | None:
    """The closes this job's own completion record says were rebalanced, or None.

    The calendar's "a missed rebalance makes the next evening a rebalance" rule
    reads the record the run already writes rather than keeping a second one:
    `efb.run_status` has a row per close it priced, and the row's status says
    whether the evening produced a book. A scheduled rebalance with no completed
    row is the gap.

    The store is asked and never written to. A tree with no store behind it - a
    test, a fresh container - gets `None`, which means "cannot say": no gap is
    inferred from a record that could not be read, because promoting every hold
    day to a rebalance on a store failure would quietly undo the calendar.
    """
    from live import staleness, store

    try:
        frame = store.select(staleness.TABLE)
    except Exception as exc:  # noqa: BLE001 - the calendar goes on without it
        logger.warning(
            "the completion record could not be read, so a missed rebalance "
            "cannot be proven: %s: %s",
            type(exc).__name__,
            exc,
        )
        return None
    columns = {"job", "target_close", "status"}
    if frame is None or not len(frame) or not columns <= set(frame.columns):
        return None
    done = frame.loc[
        frame["job"].astype(str).eq("live_daily")
        & frame["status"].astype(str).isin(cadence.COMPLETED_STATUSES)
    ]
    return sorted({str(value)[:10] for value in done["target_close"]})


def _held_back_block(
    target: np.ndarray | None, held: np.ndarray
) -> dict[str, float | int] | None:
    """The target a hold day did not trade to, or None when nothing was held back."""
    if target is None:
        return None
    return {
        "n_names": int(np.sum(np.abs(target) > 1e-12)),
        "gross": float(np.abs(target).sum()),
        "turnover": float(np.abs(target - held).sum()),
    }


def _held_book_weights(
    previous: pd.Series | None, names: list[str]
) -> np.ndarray | None:
    """The held book as a vector over `names`, or None when there is nothing held.

    A name in `previous` that `names` does not carry is absent here, which is
    exactly the close the order path should send: the universe or the model no
    longer has it. The weights are never renormalized - gross falling a little
    below 1.0 because a name left is the truth about the book, and renormalizing
    would trade every other name to make up the difference on a day that is
    supposed to trade nothing.
    """
    if previous is None or len(previous) == 0:
        return None
    held = {str(key): float(value) for key, value in previous.items()}
    vector = np.asarray([held.get(str(name), 0.0) for name in names], dtype=float)
    if not np.any(np.abs(vector) > 1e-12):
        return None
    return vector


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


# The resolved mode, cached for the process: the floor search calls the sizing
# hundreds of times per row, and a typo has to be reported once rather than
# hundreds of times. Tests reset it with `monkeypatch.setattr`.
_HEDGE_MODE_CACHE: str | None = None


def hedge_mode() -> str:
    """Which hedge the loop builds, from `EFB_HEDGE_MODE`.

    `exact` for unset, empty, `exact` (any case) and for anything unrecognised, so
    the default path is the hedge that has always run and a typo cannot move a
    book. `cap_then_rehedge` is the one other value the loop reacts to. The
    requested string is read once per process and the decision is logged, because
    the value that built a book is the thing a later reader has to know.
    """
    global _HEDGE_MODE_CACHE
    if _HEDGE_MODE_CACHE is None:
        requested = os.environ.get(HEDGE_MODE_ENV, "").strip().lower()
        if not requested or requested == HEDGE_MODE_EXACT:
            _HEDGE_MODE_CACHE = HEDGE_MODE_EXACT
        elif requested == HEDGE_MODE_CAP_THEN_REHEDGE:
            _HEDGE_MODE_CACHE = HEDGE_MODE_CAP_THEN_REHEDGE
            logger.warning(
                "%s=%s: the book is built with the cap-then-rehedge hedge, which is "
                "not the default",
                HEDGE_MODE_ENV,
                HEDGE_MODE_CAP_THEN_REHEDGE,
            )
        else:
            logger.warning(
                "%s=%r is not a hedge mode: the exact hedge is used, because a typo "
                "must never change the book",
                HEDGE_MODE_ENV,
                os.environ.get(HEDGE_MODE_ENV, ""),
            )
            _HEDGE_MODE_CACHE = HEDGE_MODE_EXACT
    return _HEDGE_MODE_CACHE


def apply_hedge_mode(
    hedged: np.ndarray, design: np.ndarray, specific: np.ndarray
) -> np.ndarray:
    """The hedged book as the requested mode wants it: unchanged, or re-capped.

    The exact hedge is returned untouched in the default mode, so every downstream
    number is the one the loop has always produced; in `cap_then_rehedge` the cap is
    applied to the hedged book and the neutrality is restored after it, to a fixed
    point (`sizing.cap_then_rehedge`).
    """
    if hedge_mode() == HEDGE_MODE_CAP_THEN_REHEDGE:
        return sizing.cap_then_rehedge(hedged, design, specific)
    return hedged


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
    report from this, `kept_set_clears_floor` checks this, and the floor search
    reads the same vector so a set that the search accepts is the set that
    trades. The hedge itself is whichever `EFB_HEDGE_MODE` names: the exact FMP
    hedge by default, and with the flag on the capped-and-re-projected one, so the
    cap holds on the vector that trades and not only on the one before the floor.
    """
    del nav  # the renorm is to gross 1.0; the share counts take the NAV
    idx = np.where(keep)[0]
    names_sub = [names[i] for i in idx]
    # Size, cap the variance share, renormalize, then hedge and renormalize: the
    # cap has to sit before the hedge, because the hedge is a projection of the
    # sized vector and capping after it would undo the neutrality instead. The one
    # exception is the cap-then-rehedge mode, which caps after the hedge and pays
    # for it with the re-projections, in `apply_hedge_mode`.
    sized = size.proportional(alpha_vec[idx], specific[idx])
    sized = sizing.cap_variance_shares(sized, specific[idx])
    sized = sizing.renormalize(sized, gross=1.0)
    w_sub, pre_hedge = sizing.procedure_6_3_hedged_with_exposures(
        alpha_vec[idx], design[idx], factor_covariance, specific[idx], sized=sized
    )
    w_sub = apply_hedge_mode(w_sub, design[idx], specific[idx])
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
    max_drops: int = MAX_PRICE_DROPS,
) -> tuple[np.ndarray, list[str]]:
    """The drop for no price, and the count that makes it a stop instead.

    The drop alone would build a book out of whatever the vendor answered for. One
    name missing is a name the book loses and the email names; ten at once is the
    fetch having broken, and then the run stops and says so rather than trading a
    book the model did not ask for. The refusal names the drops it is refusing over,
    because "too many" without them is a count nobody can act on.
    """
    priced, dropped = dropped_for_no_price(names, close)
    if len(dropped) > max_drops:
        shown = ", ".join(sorted(dropped)[:10])
        rest = "" if len(dropped) <= 10 else f" and {len(dropped) - 10} more"
        raise ValueError(
            f"{len(dropped)} of {len(names)} names have no usable close at the "
            f"proposal close, more than the {max_drops} the evening accepts before "
            f"it stops: no usable close price for {shown}{rest}"
        )
    return priced, dropped


def dropped_for_no_risk(
    names: list[str], variances: np.ndarray
) -> tuple[list[str], list[dict[str, str]]]:
    """The risk-covered names, and the ones the risk model cannot measure.

    A name enters the book through the alpha contract, `alpha_i = IC x sigma_i x
    z_i x kappa`, so a name with no specific variance has no risk to size it on
    and a name whose variance is zero has none either. Both are dropped here,
    before anything is priced, which is what makes the sizing universe the risk
    universe.

    2026-10-07 is why this exists. `efb.eval_risk._xs_pieces` fills every gap in
    the diagonal with the cross-sectional median, on purpose and for the research
    engine, so Q - a name the model has never estimated - was sized on EQT's own
    specific variance, to the last bit, kept by the share floor at $3,623, and
    then refused by `efb.positions.idio_vol`, which is `not null`, after the whole
    book had been priced. The name is the right thing to drop; the median is the
    wrong thing to size it on. The fill in `efb/` stays as it is.

    The reasons are recorded per name rather than as one list, so the manifest
    says which of the two rules fired.
    """
    covered: list[str] = []
    dropped: list[dict[str, str]] = []
    for name, value in zip(names, np.asarray(variances, dtype=float), strict=True):
        if not math.isfinite(value):
            dropped.append({"ticker": name, "reason": "no specific variance"})
        elif value <= 0.0:
            dropped.append(
                {
                    "ticker": name,
                    "reason": f"specific variance {value:.3g} is not positive",
                }
            )
        else:
            covered.append(name)
    return covered, dropped


def risk_names_or_stop(
    names: list[str],
    variances: np.ndarray,
    max_drops: int = MAX_RISK_DROPS,
) -> tuple[list[str], list[dict[str, str]]]:
    """The drop for no risk estimate, and the count that makes it a stop instead.

    The drop alone would size a book from whatever the diagonal answered for, one
    name at a time, and a risk artifact that arrived empty or truncated would do it
    silently: a hundred dropped names leave a book of two. The refusal names the
    drops it is refusing over, because "too many" without them is a count nobody
    can act on.
    """
    covered, dropped = dropped_for_no_risk(names, variances)
    if len(dropped) > max_drops:
        shown = ", ".join(str(entry["ticker"]) for entry in dropped[:10])
        rest = "" if len(dropped) <= 10 else f" and {len(dropped) - 10} more"
        raise ValueError(
            f"{len(dropped)} of {len(names)} names have no specific variance at the "
            f"proposal close, more than the {max_drops} the evening accepts before "
            f"it stops: the risk model cannot measure {shown}{rest}, which is the "
            "diagonal having gone missing rather than a few short histories"
        )
    return covered, dropped


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
    sticky: np.ndarray | None = None,
    release: float = 1.0,
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
        idx = np.asarray(finalize["idx"], dtype=int)
        below = below_floor(shares, prices, dollar_floor, share_floor)
        below = _releasable(
            below, idx, shares, prices, sticky, release, dollar_floor, share_floor
        )
        if not below.any():
            return keep, finalize, passes, True
        keep[idx[below]] = False
        if not keep.any():
            return keep, finalize, passes, False
    return keep, finalize, max_passes, False


def _releasable(
    below: np.ndarray,
    idx: np.ndarray,
    shares: np.ndarray,
    prices: np.ndarray,
    sticky: np.ndarray | None,
    release: float,
    dollar_floor: float,
    share_floor: int,
) -> np.ndarray:
    """Which below-floor names are released, under the band.

    `release` at or above 1.0 is the rule the book has always used, and the mask
    comes back untouched: the band changes what trades by nothing unless it is on.
    With it on, a name the book already *holds* (`sticky`, over the full name list)
    is released only if it is below `release` of its own floor, so a name inside the
    band stays at its size instead of being traded out and back.
    """
    if sticky is None or release >= FLOOR_RELEASE_OFF:
        return below
    held = np.asarray(sticky, dtype=bool)
    if held.size <= int(idx.max()):
        raise ValueError(
            f"the held-position mask has {held.size} entries and the book's last "
            f"kept index is {int(idx.max())}, so they cannot be aligned"
        )
    inside = below_floor(
        shares,
        prices,
        dollar_floor * release,
        max(1, int(share_floor * release)),
    )
    return below & ~(held[idx] & ~inside)


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
    sticky: np.ndarray | None = None,
    release: float = 1.0,
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
            sticky=sticky,
            release=release,
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
            sticky=sticky,
            release=release,
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
    sticky: np.ndarray | None = None,
    release: float = 1.0,
) -> list[str]:
    """Every check an enforced floor book must pass, as a list of violations.

    Empty means the book passes. The checks are the ones E11-F13R registered:
    dollar neutrality, an exact hedge, a full idio share, no name below its
    floor in the final weights, and at least three times the design width in
    kept names so the exact FMP hedge keeps its rank margin.

    `release` and `sticky` are the band, and the below-floor test has to be the
    band's own. `EFB_FLOOR_RELEASE` exists to keep a *held* name that has fallen
    below its floor but is still above `release x floor`; testing those same names
    against the full floor contradicts the flag by construction, and `build_proposal`
    raises on the result. That is the defect the churn study found on 2026-10-17: a
    release of 0.75 or 0.5 fired this check on the first rebalance where the band
    bound and the evening produced no book at all. The mask is the same one the
    floor search uses (`_releasable`), so the search and the check cannot disagree
    about which kept names are inside the band.
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
    below_mask = below_floor(shares, prices, dollar_floor, share_floor)
    below_mask = _releasable(
        below_mask, idx, shares, prices, sticky, release, dollar_floor, share_floor
    )
    below = int(below_mask.sum())
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
    horizon: int | None = None,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """The establishment cost split into spread, impact, commission and borrow.

    Each component is in basis points of the paper NAV. Borrow is the
    annualized rate on the short leg over one holding horizon, the same
    horizon E6's per-rebalance number uses.

    `horizon` is that holding period in sessions and defaults to `HORIZON` (21,
    the E6/E9 convention), which is what every call made before `EFB_CADENCE`
    existed used. Spread, commission and impact are the cost of a *trade* and do
    not amortize; the borrow is the one term charged for the time the book is
    held, so it is the one term the cadence changes: at `EFB_CADENCE=k` the book
    is held k sessions between rebalances and the short leg is borrowed for
    exactly that long.

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
    horizon_sessions = HORIZON if horizon is None else int(horizon)
    borrow_bps = (
        costs_mod.BORROW_RATE * short_gross * (horizon_sessions / TRADING_DAYS) * 1e4
    )
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


# Why a name in the SPY universe is not in the book. The three are collapsed into
# one list today and are three different things to go and fix: a GICS row that the
# vendor's file does not carry, a price history that stops, and a name that is
# priced and mapped but absent from the processed returns panel (DD, item 10). The
# reader of an `excluded` entry is the owner, and "excluded" with no reason is a
# name they cannot act on.
EXCLUDED_NO_GICS = "no GICS row"
EXCLUDED_NO_GICS_NO_PRICES = "no GICS row and no price rows"
EXCLUDED_NO_RETURNS = "in the sectors file but absent from the processed returns panel"
# What the detail says when the artifacts behind the reasons could not be read. The
# *names* are the run's own (`excluded`, off the universe and the wide panel), and the
# reason is the only part that needs the files, so this is the field that degrades.
EXCLUDED_NOT_DETERMINED = "not determined"


def exclusion_reason(
    ticker: str,
    *,
    in_sectors: bool,
    in_returns: bool,
    in_prices: bool,
) -> str:
    """Which of the three causes kept this name out of the sized universe."""
    if in_returns:
        # In `wide` at all means it was sized; this function is only called on the
        # names that are not.
        return "in the universe"
    if in_sectors:
        return EXCLUDED_NO_RETURNS
    return EXCLUDED_NO_GICS if in_prices else EXCLUDED_NO_GICS_NO_PRICES


def excluded_history(as_of: str) -> dict[str, dict[str, object]] | None:
    """How long each excluded name has been excluded, from the stored manifests.

    The loop's own manifests are the record, not the artifacts: the list has only
    ever grown (4 entries on 2026-09-25, 5 on 2026-10-01, 7 on 2026-10-06) because
    nothing rebuilds the files the exclusion rule reads, so the trailing run of
    stored sessions a name appears in *is* its age. A name that left the list and
    came back starts again, which is why the run is counted backwards from the
    newest stored manifest rather than from the first date the name ever appeared.

    Each entry is `stored_sessions` (how many of the stored manifests ending with
    the newest carry it), `since` (the first day of that run) and `current`
    (whether the newest stored manifest carries it, which is what tells the caller
    whether tonight continues the run or starts one).

    `None` when the store cannot be read at all, which is a different answer from an
    empty dict: an empty dict is a history that was read and holds no exclusions, and
    a name absent from it was excluded for the first time tonight. The caller
    publishes no age at all off a `None`, because a nought would read as "since
    today" on a name that has been out for a fortnight.
    """
    from live import store

    try:
        frame = store.select("proposals")
    except Exception as exc:  # noqa: BLE001 - the age is detail, not the book
        logger.warning("could not read the stored proposals: %s", type(exc).__name__)
        return None
    if frame.empty or "manifest" not in frame.columns:
        return {}
    order = "trade_date" if "trade_date" in frame.columns else None
    if order is not None:
        frame = frame.sort_values(order)
    days: list[str] = []
    listed: dict[str, set[str]] = {}
    for row in frame.itertuples(index=False):
        manifest = row.manifest
        if isinstance(manifest, str):
            try:
                manifest = json.loads(manifest)
            except ValueError:
                continue
        if not isinstance(manifest, dict):
            continue
        day = str(manifest.get("as_of") or getattr(row, "trade_date", "") or "")[:10]
        if not day or (days and day <= days[-1]):
            # One manifest per close, and only forward: a row out of order would
            # make a trailing run of nothing.
            if days and day == days[-1]:
                continue
        days.append(day)
        for ticker in manifest.get("excluded") or []:
            listed.setdefault(str(ticker), set()).add(day)
    history: dict[str, dict[str, object]] = {}
    for ticker, appeared in listed.items():
        sessions = 0
        since = ""
        for day in reversed(days):
            if day not in appeared:
                break
            sessions += 1
            since = day
        history[ticker] = {
            "stored_sessions": sessions,
            "since": since,
            "current": bool(days and days[-1] in appeared),
        }
    return history


def exclusion_details(
    excluded: list[str],
    *,
    in_sectors: set[str],
    in_returns: set[str],
    in_prices: set[str],
    history: dict[str, dict[str, object]] | None,
    as_of: str,
) -> list[dict[str, object]]:
    """One row per excluded name: its ticker, why, and how long it has been out.

    The age counts tonight: the name is excluded on the manifest this run is
    writing, so a name first excluded tonight reads one session, and a name the
    newest stored manifest also carries reads its stored run plus tonight.

    `None` for the age when the store could not be read - the message renders that
    as an absence rather than as a nought, which would read as "since today" on a
    name that has been out for a fortnight. A history that *was* read and does not
    carry the name is the name's first exclusion, which reads one session.
    """
    details: list[dict[str, object]] = []
    for ticker in sorted(excluded):
        name = str(ticker)
        entry = (history or {}).get(name) or {}
        stored = entry.get("stored_sessions")
        current = bool(entry.get("current"))
        sessions: int | None = None
        since: str | None = None
        if history is not None:
            sessions = (int(stored) if isinstance(stored, int) and current else 0) + 1
            since = str(entry.get("since")) if current and entry.get("since") else as_of
        details.append(
            {
                "ticker": name,
                "reason": exclusion_reason(
                    name,
                    in_sectors=name in in_sectors,
                    in_returns=name in in_returns,
                    in_prices=name in in_prices,
                ),
                "sessions": sessions,
                "since": since,
                "as_of": as_of,
            }
        )
    return details


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
    floor_release: float | None = None,
    shortable: dict[str, bool] | None = None,
    cadence_mode: int | None = None,
    cadence_anchor: object | None = None,
    completed_rebalances: Iterable[Any] | None = None,
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

    `shortable` is item 18's precheck: the broker's own lending flag per ticker,
    injected by the caller that read it (so this module never calls the broker and a
    test can pass a recorded fixture). `None` is off - the default - and then no name
    is dropped and the leg-time check remains the only guard. With a mapping, a name
    the sizing puts on the short side whose flag is `False` is dropped before the
    hedge and the floor, with the reason on the manifest and in the message. A ticker
    absent from the mapping is *not* dropped: an unanswered read is not a refusal.

    `floor_release` is item 12's band, and `None` reads it from the environment
    (`EFB_FLOOR_RELEASE`), where unset is off: at `1.0` the floor is released exactly
    where it always was, and a fraction below it keeps a name the book already holds
    until its size falls below that fraction of its own floor. A name being *admitted*
    always clears the whole floor, so the band can only ever hold a position that is
    already there. The default book is therefore unchanged, weight for weight, and
    `tests/test_nov11_floor_band.py` proves it on the live construction.

    `cadence_mode` is `EFB_CADENCE` and `cadence_anchor` is `EFB_CADENCE_ANCHOR`
    (`live/cadence.py`). `1` - the default - is the daily rebalance this job has
    always built. Above that, a hold day publishes the **held book**: the previous
    proposal's weights, unchanged, on the names tonight's universe still has. Nothing
    is sized, hedged or floor-enforced on a hold day, because none of it is being
    traded; the risk figures on the manifest describe the book that is actually held,
    and the names the universe no longer has simply drop out, which the order path
    reads as a close. `completed_rebalances` is the completion record the calendar
    reads for a missed rebalance; `None` means it could not be read, and then no gap
    is inferred (see `live.cadence.plan`).
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
    # A duplicated universe row would size the name twice, count it twice in
    # `n_kept`, hedge it against itself and write it to `efb.positions` twice, where
    # the natural key would collapse the two rows and leave the row count
    # disagreeing with every count taken off the manifest. Nothing has ever seen
    # one (the 2026-09-21 archive: 503 rows, 499 unique), so this is a guard rather
    # than a fix, and it names what it dropped instead of absorbing it silently.
    raw_tickers = universe["ticker"].astype(str).str.upper().str.strip()
    spy_tickers = sorted(set(raw_tickers))
    duplicates = sorted(
        {ticker for ticker in raw_tickers if int((raw_tickers == ticker).sum()) > 1}
    )
    if duplicates:
        logger.warning(
            "the SPY universe lists %d ticker(s) more than once and they are kept "
            "once: %s",
            len(duplicates),
            ", ".join(duplicates),
        )
    wide_names = [str(column) for column in wide.columns]
    names = [ticker for ticker in spy_tickers if ticker in wide_names]
    excluded = [ticker for ticker in spy_tickers if ticker not in wide_names]
    # Why each one is out, and for how long: the three causes are three different
    # things to go and fix, and a name that has been outside the book for a
    # fortnight is not the same fact as one excluded tonight (item 9). The three
    # memberships are read from the same artifacts the rule reads, so the reason
    # cannot disagree with the exclusion: `in_returns` is membership in `wide`,
    # which is what the rule itself uses.
    excluded_detail: list[dict[str, object]] = []
    if excluded:
        # The reason and the age are a note about a name that is already out of the
        # book: the drop itself happened above, off the universe and `wide`. So this
        # block cannot be allowed to stop the evening - a fetch that broke, a panel
        # that moved or a store that will not answer is a reason string, not a failed
        # run - and every failure here degrades the *reasons* while `excluded` and
        # `n_excluded` stay exactly what the rule computed.
        try:
            sectors_names = {
                str(name)
                for name in pd.read_parquet(root / "processed" / "sectors.parquet")[
                    "ticker"
                ].astype(str)
            }
            # The index alone: the panel is 3.6M rows and the question is only which
            # tickers it carries. `index.names` is `['date', 'ticker']`, so `ticker`
            # is a level of the frame's index and not a column.
            price_names = {
                str(name)
                for name in pd.read_parquet(root / "raw" / "prices.parquet", columns=[])
                .index.get_level_values("ticker")
                .unique()
            }
            excluded_detail = exclusion_details(
                excluded,
                in_sectors=sectors_names,
                in_returns=set(wide_names),
                in_prices=price_names,
                history=excluded_history(str(as_of_ts.date())),
                as_of=str(as_of_ts.date()),
            )
        except Exception as exc:  # noqa: BLE001 - a note, never the book
            logger.warning(
                "the excluded names' reasons could not be determined (%s: %s), so "
                "they are published as %r with no age: %s",
                type(exc).__name__,
                exc,
                EXCLUDED_NOT_DETERMINED,
                ", ".join(str(name) for name in excluded),
            )
            excluded_detail = [
                {
                    "ticker": str(name),
                    "reason": EXCLUDED_NOT_DETERMINED,
                    # No age and no date: `history` is what carries them, and this
                    # path did not get that far.
                    "sessions": None,
                    "since": None,
                    "as_of": str(as_of_ts.date()),
                }
                for name in sorted(excluded)
            ]
    if len(names) < MIN_NAMES:
        raise ValueError(
            f"the SPY universe overlaps the frozen model on only {len(names)} "
            f"names, below the {MIN_NAMES} floor"
        )

    # The calendar, before anything is sized: which close this is decides whether
    # the book is rebuilt or held. `k = 1` - the default - is the daily rebalance
    # the loop has always run, and `cadence.plan` says so without consulting a
    # calendar at all.
    k = (
        max(1, int(cadence_mode))
        if cadence_mode is not None
        else cadence.resolve_cadence()
    )
    anchor = (
        pd.Timestamp(cadence_anchor)
        if cadence_anchor is not None
        else cadence.resolve_anchor()
    )
    completed = completed_rebalances
    if completed is None and k > 1:
        completed = _completed_rebalances(root)
    calendar = cadence.plan(wide.index, as_of_ts, k, anchor, completed)

    # The risk universe, before anything is priced: a name the model has no
    # specific variance for cannot be sized on one, and the reader here is the
    # same one `_xs_pieces` uses, so the check and the diagonal cannot disagree
    # about which names have an estimate. `n_names` below is what is left, so the
    # counts add up as universe = excluded + dropped_no_risk + n_names.
    variances, n_missing_var = race._specific_for(as_of_ts, names, root)
    names, dropped_no_risk = risk_names_or_stop(names, variances)

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
    # sectors included, to zero to machine precision. This is the full-book
    # construction, before the floor's kept set exists: the hedge the traded book
    # is finally built with is the one in `sized_kept_weights`, and `EFB_HEDGE_MODE`
    # is applied here as well so the two agree and the full-book risk numbers on
    # the manifest are the numbers of the mode the run was asked for.
    weights = size.procedure_6_3(alpha_vec, design, factor_covariance, specific)
    # A hold day does not size: the book it publishes is the one it holds. The
    # sizing above still runs so the manifest can say what the target would have
    # been - that difference is what a rebalance would trade, and it is the
    # number the owner will want when the next rebalance is due - but the weights
    # that leave this function are the held ones, unchanged, with a name the
    # universe or the model no longer carries simply absent (which the order path
    # reads as a close).
    held_weights = (
        _held_book_weights(previous, names) if calendar["day"] == cadence.HOLD else None
    )
    holding = held_weights is not None
    target_weights: np.ndarray | None = None
    if held_weights is not None:
        target_weights = np.array(weights, dtype=float)
        logger.info(
            "%s: %s - the book is held, not rebuilt (%d name(s), gross %.4f)",
            as_of_ts.date(),
            calendar["label"],
            int(np.sum(np.abs(held_weights) > 1e-12)),
            float(np.abs(held_weights).sum()),
        )
        weights = held_weights
    # Item 18, when the caller injected the broker's lending flags: a name the sizing
    # puts short and the broker will not lend leaves the book *here*, before the hedge
    # and the floor, so the published book, its breadth and its forecast are the book
    # the loop can actually hold rather than one it will report a refused leg for. The
    # aligned arrays are filtered together, because a name dropped from `names` and
    # left in `design` would size the wrong row against the wrong name.
    dropped_no_short: list[dict[str, object]] = []
    if shortable is not None:
        keep_names, dropped_no_short = drop_not_shortable(names, weights, shortable)
        if not keep_names.all():
            if int(keep_names.sum()) < MIN_NAMES:
                raise ValueError(
                    f"the broker's lending flags leave only "
                    f"{int(keep_names.sum())} name(s), below the {MIN_NAMES} floor: "
                    "the feed's answer is the fetch having broken, not a market "
                    "with nothing to short"
                )
            names = [name for name, keep in zip(names, keep_names, strict=True) if keep]
            design = design[keep_names]
            specific = specific[keep_names]
            z = z[keep_names]
            alpha_vec = alpha_vec[keep_names]
            weights = weights[keep_names]
            logger.warning(
                "%d name(s) left the book before sizing because the broker's feed "
                "will not lend them: %s",
                len(dropped_no_short),
                ", ".join(str(row["ticker"]) for row in dropped_no_short),
            )
    weights = apply_hedge_mode(weights, design, specific)
    weights, gross_cap_bound = _scale_to_target(
        weights, design, factor_covariance, specific
    )
    full_decomposition = _decomposition(weights, design, factor_covariance, specific)
    if held_weights is not None:
        # The published book is the held one, and so is every number that
        # describes it. The sizing above produced the *target* book; it is kept on
        # the manifest as the rebalance the calendar did not take today.
        weights = held_weights
        gross_cap_bound = False
        full_decomposition = _decomposition(
            weights, design, factor_covariance, specific
        )

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
    # universe members with no print tonight. Too many of them at once is the fetch
    # having broken rather than names delisting, and that stops the run.
    priced, dropped_no_price = priced_names_or_stop(names, close)
    started = time.perf_counter()
    release = (
        resolve_floor_release(os.environ.get(FLOOR_RELEASE_ENV))
        if floor_release is None
        else float(floor_release)
    )
    # The names the book already holds with a real position, which are the only ones
    # the band can hold: a name not held has nothing to keep, and a zero weight is
    # not a position.
    sticky: np.ndarray | None = None
    if release < FLOOR_RELEASE_OFF and previous is not None and len(previous):
        held = {
            str(ticker): float(weight)
            for ticker, weight in previous.items()
            if float(weight) != 0.0
        }
        sticky = np.array(
            [held.get(str(name), 0.0) != 0.0 for name in names], dtype=bool
        )
    if holding:
        # Nothing is enforced on a book that is not being traded: the floor is a
        # rule about which names a *rebalance* keeps, and applying it here would
        # trade the book back to a target the calendar said not to take today.
        # The held names keep their sizes exactly, so `finalize` is assembled from
        # the held vector itself and the search reports what it did - nothing.
        idx = np.where(np.abs(weights) > 1e-12)[0]
        enforced_keep = np.abs(weights) > 1e-12
        finalize = {
            "idx": idx,
            "w_sub": weights[idx],
            "shares": np.zeros(len(idx), dtype=int),
            "prices": np.asarray(
                [close.get(str(names[i]), 0.0) for i in idx], dtype=float
            ),
            # No hedge ran on a hold day, so the "before" and "after" vectors are
            # the same one: the held book's own exposures.
            "pre_hedge_exposures": (
                design[idx].T @ weights[idx] if len(idx) else np.zeros(design.shape[1])
            ),
        }
        search = {
            "n_drop_only": int(enforced_keep.sum()),
            "n_one_pass_admission": int(enforced_keep.sum()),
            "cycles": 0,
            "admit_passes": 0,
            "admitted": [],
            "converged": True,
        }
        floor_search_seconds = 0.0
        # The band is not consulted on a hold day, so the manifest states the rule
        # the book was actually built under rather than the one it would have used.
        release = FLOOR_RELEASE_OFF
    else:
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
            sticky=sticky,
            release=release,
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
            sticky=sticky,
            release=release,
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
        weights,
        names,
        specific,
        nav,
        root,
        previous_weights,
        # The holding horizon the borrow is charged over. `k` above 1 is the
        # cadence the book is actually held for; 1 keeps the E6/E9 convention.
        horizon=k if k > 1 else None,
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
        # The names the broker will not lend, dropped before the sizing when the
        # precheck is on, and the count beside them so the two cannot disagree.
        "n_dropped_no_short": len(dropped_no_short),
        "dropped_no_short": dropped_no_short,
        # Which floor rule built this book: `1.0` is the release-at-the-floor rule the
        # loop has always used, and a fraction below it is item 12's band. A row read
        # back months later has to say which of the two its book came from.
        "floor_release": float(release),
        # Which close this was, on the calendar `EFB_CADENCE` describes: a rebalance
        # or a hold, the next rebalance date, and whether today's is a rebalance an
        # earlier evening missed. `held` is the fact the order path reads - the book
        # below is the held book, so only its forced legs may trade. At the default
        # `k = 1` this block says "rebalance" every day and changes nothing.
        "cadence": dict(calendar, held=bool(holding)),
        "held_book": bool(holding),
        # The held names tonight's universe or model no longer carries, which are
        # the closes a hold day sends. Named on the manifest so the run's record
        # says which names the hold could not keep rather than leaving it to be
        # inferred from an order list.
        "left_universe": (
            sorted({str(name) for name in previous.index} - set(names))
            if holding and previous is not None
            else []
        ),
        # What a hold day did not take: the target the construction would have
        # traded to. `None` on a rebalance day, where the published book *is* it.
        "target_book_held_back": _held_back_block(target_weights, weights),
        # The same names with their reason and their age: the list itself is what
        # downstream reads, and this is what the message and the owner read.
        "excluded_detail": excluded_detail,
        # The names tonight's book lost for having no usable close, and the count
        # that would have stopped the run: one or a few is a name the vendor did not
        # answer for, ten at once is the fetch having broken. They are named in the
        # email beside the universe members with no print, because both are the
        # same fact about tonight and a book quietly smaller than the index is a
        # book nobody can check.
        "n_dropped_no_price": len(dropped_no_price),
        "dropped_no_price": dropped_no_price,
        "max_price_drops": MAX_PRICE_DROPS,
        # The names the risk model cannot measure, and why, dropped before the
        # sizing rather than priced on the cross-sectional median. The count is
        # what the evening can lose without stopping, and the names are said out
        # loud on the email beside the ones with no price: a book narrower than
        # the universe is a book nobody can check, and a name sized on a median
        # that is not its own is a risk nobody chose.
        "n_dropped_no_risk": len(dropped_no_risk),
        "dropped_no_risk": dropped_no_risk,
        "max_risk_drops": MAX_RISK_DROPS,
        # How many names the risk block had no estimate for at all, before the drop
        # removed them. `_specific_for` has always computed this count and the
        # caller has always thrown it away, so a reader could see the names that
        # left the book and not how many the diagonal could not measure. It is the
        # same number as `n_dropped_no_risk` on a night the drop is what removed
        # them, and it is smaller when a name is excluded first, which is why both
        # are recorded rather than one being derived from the other.
        "n_specific_var_missing": int(n_missing_var),
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
        # Which panel the design row behind this book was built from: `raw` for the
        # loop's own history and the default, `clean` when EFB_DESIGN_RETURNS asked
        # for the cleaned one. Recorded rather than inferred, because two books that
        # differ only in their design panel are otherwise indistinguishable.
        "design_returns": race.design_returns(),
        # Which hedge built this book: `exact` for the loop's own hedge and the
        # default, `cap_then_rehedge` when EFB_HEDGE_MODE asked for the research
        # construction. Recorded rather than inferred, because two books that differ
        # only in their hedge are otherwise indistinguishable afterwards.
        "hedge_mode": hedge_mode(),
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
