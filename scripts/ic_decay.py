"""How fast does the live signal's edge decay? The IC term structure, not the P&L.

Research only: nothing here trades, sets a flag, writes a store or touches `data/`.
It reads a copy of the tree and writes one JSON beside the note.

The signal is the one the live construction actually trades: `efb.alpha.idio_momentum`
(the manifest's `signal`), whose momentum window is 252 sessions ending 21 sessions
before the close the book is built at. The book is factor-neutral, so the return that
matters is the model's **specific** return; the total-return IC is computed beside it as
the naive number a reader will expect to see.

    python scripts/ic_decay.py run --root /tmp/icdecay/data \
        --out docs/research/ic_decay.json

Cross-sectional Spearman rank IC per day, then averaged across days. Point-in-time
universe membership (`processed/universe_membership.parquet`) is applied to every
cross-section, so a name enters only on the days it was a member: no survivorship.

Two things this is careful about, because they decide the answer:

* Overlap. A lagged one-day IC at lag L is a series of daily numbers whose *signal* is
  roughly the same for 232 sessions, so the series is autocorrelated even though the
  returns do not overlap; a cumulative h-day IC's returns overlap by h-1 by
  construction. Both t-stats are Newey-West with a Bartlett kernel whose bandwidth is
  stated with each number, and the naive t is beside it so the difference is visible.
* The cadence translation. Rebalancing every k days means the book trades on a signal
  that is 1..k days old, so what it captures is the average of IC(1..k). The gross
  anchor is the design backtest's monthly 169 bp/yr, multiplied by
  `capture(k) = mean(IC(1..k)) / mean(IC(1..21))`.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import pathlib
import sys
from typing import Any

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ic_decay")

LAGS = list(range(1, 22))
CUMULATIVE = [1, 2, 5, 10, 21]
AUTOCORR_LAGS = [1, 5, 10, 21]
MIN_NAMES = 30
# The cadence study's V1 (25% resize band) trading cost and its borrow, bp/yr, on
# origin/research-cadence (docs/research/cadence_study.json). Borrow is pinned at the
# brief's 100 bp/yr rather than each row's own 98.2-101.4, so the four cadences are
# compared on one number.
CADENCE_COST_BP = {1: 434.60, 5: 174.09, 10: 117.60, 21: 66.30}
BORROW_BP = 100.0
MONTHLY_GROSS_BP = 169.0
BLOCK = 21
BOOTSTRAP = 2000
SEED = 20261017


# ------------------------------------------------------------------ the inputs


def load_signal(root: pathlib.Path) -> pd.DataFrame:
    """The live signal, wide: `efb.alpha.idio_momentum`, the manifest's `signal`."""
    from efb import alpha

    frame = alpha.idio_momentum(root)
    frame["date"] = pd.to_datetime(frame["date"])
    wide = frame.pivot(index="date", columns="ticker", values="signal")
    logger.info(
        "signal %s: %d sessions %s..%s, %d tickers",
        alpha.SIGNAL_NAME if hasattr(alpha, "SIGNAL_NAME") else "idio_momentum",
        len(wide),
        wide.index.min().date(),
        wide.index.max().date(),
        wide.shape[1],
    )
    return wide.sort_index()


def load_returns(root: pathlib.Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Total returns and the model's specific returns, both wide and on one calendar."""
    total = pd.read_parquet(root / "processed" / "returns.parquet", columns=["r"])
    total = total["r"].unstack("ticker").sort_index()
    specific = pd.read_parquet(root / "models" / "XS-v1" / "specific_returns.parquet")
    specific["date"] = pd.to_datetime(specific["date"])
    specific = specific.pivot(
        index="date", columns="ticker", values="specific_return"
    ).sort_index()
    return total, specific


def load_membership(root: pathlib.Path, calendar: pd.Index) -> pd.DataFrame:
    frame = pd.read_parquet(root / "processed" / "universe_membership.parquet")
    frame.index = pd.to_datetime(frame.index)
    frame = frame.reindex(calendar)
    # A day the file does not cover is not a day with no members: forward-fill so a
    # gap in the index does not silently empty the cross-section.
    frame = frame.ffill().fillna(False).astype(bool)
    return frame


def forward_compounded(logret: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """`prod(1+r)` over t+1..t+h, NaN when any of the h sessions is missing."""
    reversed_sums = logret.iloc[::-1].rolling(horizon, min_periods=horizon).sum()
    suffix = reversed_sums.iloc[::-1]
    return np.expm1(suffix.shift(-1))


# ------------------------------------------------------------------- the maths


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Rank correlation of two aligned cross-sections."""
    n = len(a)
    if n < MIN_NAMES:
        return float("nan")
    ra = pd.Series(a).rank(method="average").to_numpy()
    rb = pd.Series(b).rank(method="average").to_numpy()
    sa = ra.std(ddof=0)
    sb = rb.std(ddof=0)
    if not np.isfinite(sa) or not np.isfinite(sb) or sa <= 0 or sb <= 0:
        return float("nan")
    return float(((ra - ra.mean()) * (rb - rb.mean())).mean() / (sa * sb))


def cross_sectional_ic(
    signal: pd.DataFrame,
    returns: pd.DataFrame,
    membership: pd.DataFrame,
    min_names: int = MIN_NAMES,
) -> pd.Series:
    """Spearman IC per day, over members only, NaN where the day cannot be measured."""
    dates = signal.index.intersection(returns.index)
    names = signal.columns.intersection(returns.columns)
    sig = signal.reindex(index=dates, columns=names).to_numpy(dtype=float)
    ret = returns.reindex(index=dates, columns=names).to_numpy(dtype=float)
    member = membership.reindex(index=dates, columns=names).to_numpy(dtype=bool)
    usable = np.isfinite(sig) & np.isfinite(ret)
    out = np.full(len(dates), np.nan)
    for row in range(len(dates)):
        mask = usable[row] & member[row]
        count = int(mask.sum())
        if count < min_names:
            continue
        out[row] = _spearman(sig[row][mask], ret[row][mask])
    return pd.Series(out, index=dates)


def last_of(series: pd.Series, lag: int) -> pd.Series:
    """`x[t] = series[t+lag]` — the return a signal at t is predicting."""
    return series.shift(-lag)


def newey_west(values: np.ndarray, bandwidth: int) -> dict[str, float]:
    """Mean, naive t, and Newey-West t with a Bartlett kernel of `bandwidth`."""
    x = values[np.isfinite(values)]
    n = len(x)
    if n < 3:
        return {"n": n, "mean": float("nan"), "t": float("nan"), "t_nw": float("nan")}
    mean = float(x.mean())
    deviations = x - mean
    gamma0 = float((deviations**2).mean())
    variance = gamma0
    for lag in range(1, min(bandwidth, n - 1) + 1):
        cov = float((deviations[lag:] * deviations[:-lag]).mean())
        variance += 2.0 * (1.0 - lag / (bandwidth + 1.0)) * cov
    variance = max(variance, 1e-30)
    naive = gamma0 / n
    return {
        "n": n,
        "mean": mean,
        "t": mean / math.sqrt(naive) if naive > 0 else float("nan"),
        "t_nw": mean / math.sqrt(variance / n),
        "bandwidth": bandwidth,
        "std": math.sqrt(gamma0),
    }


def acf(values: pd.Series, lag: int) -> float | None:
    """Autocorrelation of a series at one lag (NaN-tolerant, demeaned)."""
    x = values.dropna().to_numpy(dtype=float)
    if len(x) <= lag + 2:
        return None
    d = x - x.mean()
    denominator = float((d**2).mean())
    if denominator <= 0:
        return None
    return float((d[lag:] * d[:-lag]).mean() / denominator)


def bandwidth_stress(values: pd.Series) -> dict[str, float]:
    """The same mean at four Newey-West bandwidths, so the t is not a choice."""
    return {
        str(bandwidth): newey_west(values.to_numpy(dtype=float), bandwidth)["t_nw"]
        for bandwidth in (21, 63, 126, 252)
    }


def capture_by_period(
    daily: dict[int, pd.Series], pieces: dict[str, pd.Index], cadences: list[int]
) -> dict[str, Any]:
    """capture(k) inside each period, to see whether the ranking is period-specific."""
    out: dict[str, Any] = {}
    for label, window in pieces.items():
        means = {lag: float(daily[lag].reindex(window).mean()) for lag in sorted(daily)}
        base = float(np.mean(list(means.values())))
        if not np.isfinite(base) or abs(base) < 1e-12:
            out[label] = {
                "mean_ic_1_21": base,
                "capture": None,
                "note": "no level to ratio",
            }
            continue
        out[label] = {
            "mean_ic_1_21": base,
            "capture": {
                str(cadence): float(
                    np.mean([means[lag] for lag in sorted(daily)[:cadence]])
                )
                / base
                for cadence in cadences
            },
        }
    return out


def anchor_sensitivity(
    capture: dict[int, float], cadences: list[int], alt_anchor: float
) -> dict[str, Any]:
    """net(k) under a second anchor, and the band a +/-25% anchor error implies."""
    rows = {
        str(cadence): alt_anchor * capture[cadence]
        - CADENCE_COST_BP[cadence]
        - BORROW_BP
        for cadence in cadences
    }
    band = {
        "monthly_anchor_low": MONTHLY_GROSS_BP * 0.75,
        "monthly_anchor_high": MONTHLY_GROSS_BP * 1.25,
        "net_21_low": MONTHLY_GROSS_BP * 0.75 - CADENCE_COST_BP[21] - BORROW_BP,
        "net_21_high": MONTHLY_GROSS_BP * 1.25 - CADENCE_COST_BP[21] - BORROW_BP,
    }
    return {"alt_anchor_bp": alt_anchor, "net_bp": rows, "anchor_band": band}


def half_life(curve: dict[int, float]) -> dict[str, Any]:
    """Fit `IC(L) = A * exp(-lambda * L)` by OLS on the lags whose IC is positive."""
    lags = [lag for lag in sorted(curve) if np.isfinite(curve[lag]) and curve[lag] > 0]
    if len(lags) < 5:
        return {
            "half_life_days": None,
            "fit_lags": lags,
            "note": "too few positive lags",
        }
    x = np.asarray(lags, dtype=float)
    y = np.log(np.asarray([curve[lag] for lag in lags], dtype=float))
    slope, intercept = np.polyfit(x, y, 1)
    if slope >= 0:
        return {
            "half_life_days": None,
            "fit_lags": lags,
            "decay_per_day": float(slope),
            "note": "the fitted curve does not decay inside 21 sessions",
        }
    fitted = float(np.exp(intercept + slope * 1.0))
    return {
        "half_life_days": float(math.log(2) / -slope),
        "decay_per_day": float(slope),
        "fit_lags": lags,
        "implied_ic_at_lag1": fitted,
        "r_squared": float(
            1.0
            - ((y - (intercept + slope * x)) ** 2).sum()
            / max(((y - y.mean()) ** 2).sum(), 1e-30)
        ),
    }


# --------------------------------------------------------------- the analysis


def lagged_curve(
    signal: pd.DataFrame,
    returns: pd.DataFrame,
    membership: pd.DataFrame,
    lags: list[int],
    bandwidth: int = 21,
) -> dict[str, Any]:
    """IC(L) for each lag, with its t-stats and the number of days behind it."""
    curve: dict[int, float] = {}
    stats: dict[str, Any] = {}
    daily: dict[int, pd.Series] = {}
    for lag in lags:
        shifted = last_of(returns, lag)
        series = cross_sectional_ic(signal, shifted, membership)
        daily[lag] = series
        curve[lag] = float(series.mean())
        stats[str(lag)] = newey_west(series.to_numpy(), bandwidth)
    return {"curve": curve, "stats": stats, "daily": daily}


def cumulative_curve(
    signal: pd.DataFrame,
    logret: pd.DataFrame,
    membership: pd.DataFrame,
    horizons: list[int],
) -> dict[str, Any]:
    """IC of the signal against the compounded return over t+1..t+h."""
    curve: dict[int, float] = {}
    stats: dict[str, Any] = {}
    for horizon in horizons:
        forward = forward_compounded(logret, horizon)
        series = cross_sectional_ic(signal, forward, membership)
        # The overlap is h-1 by construction, and the signal's own persistence adds
        # to it; the bandwidth is the larger of the two plus a session.
        stats[str(horizon)] = newey_west(series.to_numpy(), max(horizon - 1, 21) + 1)
        curve[horizon] = float(series.mean())
    return {"curve": curve, "stats": stats}


def signal_autocorrelation(
    signal: pd.DataFrame, membership: pd.DataFrame, lags: list[int]
) -> dict[str, Any]:
    """Mean cross-sectional rank autocorrelation of the signal at each lag."""
    out: dict[str, Any] = {}
    for lag in lags:
        series = cross_sectional_ic(signal, signal.shift(-lag), membership)
        out[str(lag)] = {
            "mean": float(series.mean()),
            "n": int(series.notna().sum()),
        }
    return out


def stability(
    signal: pd.DataFrame,
    returns: pd.DataFrame,
    membership: pd.DataFrame,
    lags: list[int],
) -> dict[str, Any]:
    """The decay curve by third of the history, and over the last two years."""
    dates = signal.index
    pieces = {
        "first third": dates[: len(dates) // 3],
        "second third": dates[len(dates) // 3 : 2 * len(dates) // 3],
        "last third": dates[2 * len(dates) // 3 :],
        "last two years": dates[dates >= dates.max() - pd.Timedelta(days=730)],
    }
    out: dict[str, Any] = {}
    for label, window in pieces.items():
        if len(window) < 60:
            continue
        piece = lagged_curve(
            signal.loc[window], returns, membership, lags, bandwidth=21
        )
        out[label] = {
            "start": str(pd.Timestamp(window.min()).date()),
            "end": str(pd.Timestamp(window.max()).date()),
            "sessions": len(window),
            "curve": {str(lag): value for lag, value in piece["curve"].items()},
            "mean_ic_1_21": float(np.mean([piece["curve"][lag] for lag in lags])),
        }
    return out


def capture_and_net(
    curve: dict[int, float],
    days: pd.DataFrame,
    cadences: list[int],
) -> dict[str, Any]:
    """capture(k), gross(k), net(k) and an 80% block bootstrap on the IC days."""
    lags = sorted(curve)
    full = float(np.mean([curve[lag] for lag in lags]))

    def one(sample: pd.DataFrame) -> dict[int, float]:
        means = {lag: float(sample[lag].mean()) for lag in lags}
        base = float(np.mean([means[lag] for lag in lags]))
        out = {}
        for cadence in cadences:
            capture = (
                float(np.mean([means[lag] for lag in lags[:cadence]])) / base
                if base != 0
                else float("nan")
            )
            gross = MONTHLY_GROSS_BP * capture
            out[cadence] = gross - CADENCE_COST_BP[cadence] - BORROW_BP
        return out

    point: dict[int, Any] = {}
    for cadence in cadences:
        capture = (
            float(np.mean([curve[lag] for lag in lags[:cadence]])) / full
            if full != 0
            else float("nan")
        )
        gross = MONTHLY_GROSS_BP * capture
        point[cadence] = {
            "capture": capture,
            "gross_bp": gross,
            "cost_bp": CADENCE_COST_BP[cadence],
            "borrow_bp": BORROW_BP,
            "net_bp": gross - CADENCE_COST_BP[cadence] - BORROW_BP,
        }

    # The bootstrap treats each day's whole 21-lag vector as one observation, so a
    # resample keeps every lag's cross-correlation intact; 21-day blocks keep the
    # signal's own persistence inside a block.
    rng = np.random.default_rng(SEED)
    n_days = len(days)
    starts = np.arange(0, n_days - BLOCK + 1)
    samples: dict[int, list[float]] = {cadence: [] for cadence in cadences}
    values = days.to_numpy()
    for _ in range(BOOTSTRAP):
        picks = rng.choice(starts, size=max(n_days // BLOCK, 1), replace=True)
        rows = np.concatenate([np.arange(start, start + BLOCK) for start in picks])
        sample = pd.DataFrame(values[rows], columns=days.columns)
        result = one(sample)
        for cadence in cadences:
            samples[cadence].append(result[cadence])
    for cadence in cadences:
        draws = np.asarray(samples[cadence], dtype=float)
        draws = draws[np.isfinite(draws)]
        point[cadence]["net_p10"] = float(np.percentile(draws, 10))
        point[cadence]["net_p50"] = float(np.percentile(draws, 50))
        point[cadence]["net_p90"] = float(np.percentile(draws, 90))
        point[cadence]["p_net_positive"] = float((draws > 0).mean())
    return {"rows": point, "days": n_days, "block": BLOCK, "reps": BOOTSTRAP}


def decide(rows: dict[int, Any], cadences: list[int]) -> dict[str, Any]:
    """Highest estimated net; a >50% interval overlap picks the slower cadence."""
    best = max(cadences, key=lambda cadence: rows[cadence]["net_p50"])
    overlaps = {}
    for cadence in cadences:
        if cadence == best:
            continue
        low = max(rows[cadence]["net_p10"], rows[best]["net_p10"])
        high = min(rows[cadence]["net_p90"], rows[best]["net_p90"])
        width = min(
            rows[cadence]["net_p90"] - rows[cadence]["net_p10"],
            rows[best]["net_p90"] - rows[best]["net_p10"],
        )
        share = max(0.0, high - low) / width if width > 0 else 0.0
        overlaps[str(cadence)] = float(share)
    contested = [int(c) for c, share in overlaps.items() if share > 0.5]
    chosen = best
    reason = "the highest estimated net"
    if contested:
        slower = max([best, *contested])
        if slower != best:
            chosen = slower
            share = max(overlaps[str(cadence)] for cadence in contested)
            reason = (
                f"its 80% interval overlaps {share:.0%} of the widest competing "
                f"interval, which is more than half, so the less frequent cadence wins"
            )
    clearly_above = [cadence for cadence in cadences if rows[cadence]["net_p10"] > 0.0]
    return {
        "best_point": best,
        "chosen": chosen,
        "reason": reason,
        "overlap_shares": overlaps,
        "cadences_clearly_above_zero": clearly_above,
        "any_clearly_above_zero": bool(clearly_above),
    }


def run(root: pathlib.Path, out: pathlib.Path) -> int:
    signal = load_signal(root)
    total, specific = load_returns(root)
    calendar = total.index
    membership = load_membership(root, calendar)

    # The signal's own calendar is the model's; align everything to it, and keep the
    # membership on that calendar too.
    signal = signal.reindex(signal.index.intersection(calendar))
    membership = membership.reindex(signal.index).ffill().fillna(False).astype(bool)

    members = membership.reindex(columns=signal.columns).fillna(False)
    names_per_day = members.sum(axis=1).astype(float)
    measurable = (signal.notna() & members).sum(axis=1)
    # The frame starts at the model's first session, but the momentum window needs
    # 231 of them before a signal exists, so the studied period starts later and the
    # breadth is measured where there is something to measure.
    live = measurable[measurable > 0]
    first_measurable = live.index.min()
    window = {
        "start": str(signal.index.min().date()),
        "end": str(signal.index.max().date()),
        "sessions": int(len(signal)),
        "measurable_start": str(first_measurable.date()),
        "measurable_sessions": int(len(live)),
        "measurable_years": round(len(live) / 252, 2),
        "names_per_day_members": float(names_per_day.mean()),
        "names_per_day_with_signal": float(live.mean()),
        "names_per_day_with_signal_min": int(live.min()),
        "names_per_day_with_signal_max": int(live.max()),
        "signal": "idio_momentum",
        "signal_definition": (
            "compounded XS-v1 specific return over t-252..t-21 "
            "(efb.alpha.idio_momentum, MOMENTUM_LOOKBACK 252, MOMENTUM_SKIP 21)"
        ),
        "specific_returns_file": "models/XS-v1/specific_returns.parquet",
        "total_returns_file": "processed/returns.parquet, column r",
        "membership_file": "processed/universe_membership.parquet",
    }
    logger.info(
        "window %s..%s, %d sessions, %.0f members/day, %.0f with signal",
        window["start"],
        window["end"],
        window["sessions"],
        window["names_per_day_members"],
        window["names_per_day_with_signal"],
    )

    logret_specific = np.log1p(specific.reindex(index=calendar))
    logret_total = np.log1p(total)

    specific_lagged = lagged_curve(signal, specific, membership, LAGS)
    total_lagged = lagged_curve(signal, total, membership, LAGS)
    specific_cumulative = cumulative_curve(
        signal, logret_specific, membership, CUMULATIVE
    )
    total_cumulative = cumulative_curve(signal, logret_total, membership, CUMULATIVE)
    autocorrelation = signal_autocorrelation(signal, membership, AUTOCORR_LAGS)
    stability_specific = stability(signal, specific, membership, LAGS)

    days = pd.DataFrame({lag: specific_lagged["daily"][lag] for lag in LAGS}).dropna(
        how="all"
    )
    mean_ic = days.mean(axis=1)
    periods = {
        "full": signal.index,
        "first third": signal.index[: len(signal.index) // 3],
        "second third": signal.index[
            len(signal.index) // 3 : 2 * len(signal.index) // 3
        ],
        "last third": signal.index[2 * len(signal.index) // 3 :],
        "last two years": signal.index[
            signal.index >= signal.index.max() - pd.Timedelta(days=730)
        ],
    }
    persistence = {
        "ic_at_lag_1": {
            "acf": {
                str(lag): acf(days[1], lag) for lag in (1, 5, 10, 21, 63, 126, 252)
            },
            "mean": float(days[1].mean()),
            "t_nw_by_bandwidth": bandwidth_stress(days[1]),
        },
        "mean_ic_1_21": {
            "acf": {
                str(lag): acf(mean_ic, lag) for lag in (1, 5, 10, 21, 63, 126, 252)
            },
            "mean": float(mean_ic.mean()),
            "t_nw_by_bandwidth": bandwidth_stress(mean_ic),
        },
        "note": (
            "A lagged one-day IC at lag L uses one return per day, so its series is "
            "close to serially uncorrelated and its daily t is real. The mean of "
            "IC(1..21) shares twenty of its twenty-one returns with its neighbour, so "
            "it is one long bet: the bandwidths are given so the t is not a choice."
        ),
    }
    by_period = capture_by_period(specific_lagged["daily"], periods, [1, 5, 10, 21])
    cadence = capture_and_net(specific_lagged["curve"], days, [1, 5, 10, 21])
    decision = decide(cadence["rows"], [1, 5, 10, 21])

    payload = {
        "window": window,
        "specific_lagged_ic": {
            "curve": {str(k): v for k, v in specific_lagged["curve"].items()},
            "stats": specific_lagged["stats"],
            "half_life": half_life(specific_lagged["curve"]),
        },
        "total_lagged_ic": {
            "curve": {str(k): v for k, v in total_lagged["curve"].items()},
            "stats": total_lagged["stats"],
            "half_life": half_life(total_lagged["curve"]),
        },
        "specific_cumulative_ic": {
            "curve": {str(k): v for k, v in specific_cumulative["curve"].items()},
            "stats": specific_cumulative["stats"],
        },
        "total_cumulative_ic": {
            "curve": {str(k): v for k, v in total_cumulative["curve"].items()},
            "stats": total_cumulative["stats"],
        },
        "signal_autocorrelation": autocorrelation,
        "stability": stability_specific,
        "persistence": persistence,
        "capture_by_period": by_period,
        "cadence": cadence,
        "anchor_sensitivity": anchor_sensitivity(
            {k: cadence["rows"][k]["capture"] for k in (1, 5, 10, 21)},
            [1, 5, 10, 21],
            218.9,
        ),
        "decision": decision,
        "inputs": {
            "cost_bp_by_cadence": CADENCE_COST_BP,
            "borrow_bp": BORROW_BP,
            "monthly_gross_bp": MONTHLY_GROSS_BP,
            "cost_source": (
                "origin/research-cadence docs/research/cadence_study.json, V1 rows"
            ),
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    logger.info("wrote %s", out)
    print(
        json.dumps(
            {
                "window": window,
                "half_life": payload["specific_lagged_ic"]["half_life"],
                "ic_1_21": [round(specific_lagged["curve"][lag], 5) for lag in LAGS],
                "cadence": cadence["rows"],
                "decision": decision,
            },
            indent=2,
            default=str,
        )[:2600]
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IC decay of the live signal")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--root", required=True)
    run_parser.add_argument("--out", required=True)
    run_parser.set_defaults(
        func=lambda args: run(pathlib.Path(args.root).resolve(), pathlib.Path(args.out))
    )
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
