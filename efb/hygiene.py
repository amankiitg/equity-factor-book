"""Hygiene detection rules and the event log (Sprint E1, Task 6).

Policies, mirrored in docs/hygiene_ledger.md:

- Stale prices: a zero-return run of 5 or more consecutive business days
  is flagged stale. The raw return is never overwritten.
- Outliers: |r| > 0.50 is flagged for review and never silently
  winsorized in the raw artifact.
- Delistings: rows after a ticker's last price stay NaN and are recorded
  as documented delisting rows by the events log (membership removals).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

STALE_MIN_RUN = 5
OUTLIER_THRESHOLD = 0.50
LARGE_DIVIDEND_FRACTION = 0.01  # dividend larger than 1% of the close


def zero_run_lengths(series: pd.Series) -> pd.Series:
    """Length of the zero-run each day belongs to (0 for non-zero days)."""
    zero = (series == 0).astype(int)
    groups = (zero.diff() != 0).cumsum()
    return zero.groupby(groups).transform("sum").where(zero == 1, 0)


def detect_stale(
    returns_frame: pd.DataFrame, min_run: int = STALE_MIN_RUN
) -> pd.Series:
    """Boolean Series (date, ticker): day belongs to a long zero-return run."""
    r = returns_frame["r"]
    lengths = r.groupby(level="ticker").transform(zero_run_lengths)
    return lengths >= min_run


def is_outlier(value: float) -> bool:
    """|r| > 50% flag; NaN is not an outlier."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    return bool(abs(float(value)) > OUTLIER_THRESHOLD)


def _stale_run_starts(stale: pd.Series) -> pd.Series:
    """Boolean: True on the first day of each consecutive stale run."""
    shifted = stale.groupby(level="ticker").shift(1, fill_value=False)
    return (stale & ~shifted).astype(bool)


def apply_flags(
    returns_frame: pd.DataFrame, min_run: int = STALE_MIN_RUN
) -> pd.DataFrame:
    """Add stale and outlier boolean columns to the returns frame."""
    out = returns_frame.copy()
    out["stale"] = detect_stale(out, min_run=min_run)
    out["outlier"] = out["r"].map(is_outlier).astype(bool)
    return out


def series_break_tickers(prices: pd.DataFrame, ratio: float = 5.0) -> list[str]:
    """Tickers whose history splices two companies together.

    Adjusting for splits and dividends leaves genuine corporate actions
    smoothed out, so a ratio between consecutive adjusted closes above
    `ratio` (or below its reciprocal) is a series break: the symbol was
    reused by a later listing and the vendor spliced both histories. Every
    date before the break then carries a different company's returns, so
    the name has to leave the estimation panel rather than lose one row.
    """
    frame = prices.sort_index()
    adjusted = frame["adj_close"].astype(float)
    previous = adjusted.groupby(level="ticker").shift(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio_series = adjusted.div(previous)
    split = frame["split_factor"].astype(float)
    suspects = (
        ((ratio_series > ratio) | (ratio_series < 1.0 / ratio))
        & (split == 0.0)
        & ratio_series.notna()
    )
    return sorted(frame.loc[suspects].index.get_level_values("ticker").unique())


def clean_returns(returns_frame: pd.DataFrame) -> pd.Series:
    """Return the r column with stale and outlier rows set to NaN.

    The flag columns say which rows are unusable; nothing downstream should
    consume raw r without consulting them. A 95x day for one name is enough
    to dominate a mean QLIKE, a momentum signal and a realized volatility,
    so volatility, beta and portfolio code all read returns through here.
    The flags themselves are never rewritten; the raw r column stays intact
    in returns.parquet.
    """
    r = _frame_r(returns_frame)
    for flag in ("stale", "outlier"):
        if flag in returns_frame.columns:
            r = r.mask(returns_frame[flag].astype(bool))
    return r


def _frame_r(returns_frame: pd.DataFrame) -> pd.Series:
    """The r column as a Series on the (date, ticker) index."""
    r = returns_frame["r"]
    if isinstance(r, pd.DataFrame):
        raise TypeError("clean_returns expects a single r column")
    return r.astype(float)


def build_events(
    prices: pd.DataFrame,
    returns_frame: pd.DataFrame,
    membership_events: pd.DataFrame,
) -> pd.DataFrame:
    """Assemble events.parquet rows from corporate actions and flags.

    membership_events: DataFrame with date, ticker, event_type columns
    holding added and removed rows from the universe matrix.
    """
    rows: list[dict[str, object]] = []
    for _, row in membership_events.iterrows():
        rows.append(
            {
                "date": row["date"],
                "ticker": row["ticker"],
                "event_type": row["event_type"],
                "detail": "membership change from the Wikipedia changes table",
            }
        )
    splits = prices[prices["split_factor"].fillna(0.0) > 0]
    for (date, ticker), row in splits.iterrows():
        rows.append(
            {
                "date": date,
                "ticker": ticker,
                "event_type": "split",
                "detail": f"split factor {row['split_factor']:.4g}",
            }
        )
    prices_with_close = prices.dropna(subset=["close"])
    big_div = prices_with_close[
        prices_with_close["dividend"].fillna(0.0)
        > LARGE_DIVIDEND_FRACTION * prices_with_close["close"]
    ]
    for (date, ticker), row in big_div.iterrows():
        rows.append(
            {
                "date": date,
                "ticker": ticker,
                "event_type": "dividend_large",
                "detail": f"dividend {row['dividend']:.4f} on close {row['close']:.2f}",
            }
        )
    if "outlier" in returns_frame.columns:
        outliers = returns_frame[returns_frame["outlier"]]
        for (date, ticker), row in outliers.iterrows():
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "event_type": "outlier",
                    "detail": f"return {row['r']:.4f} flagged, never winsorized in raw",
                }
            )
    if "stale" in returns_frame.columns:
        stale = returns_frame[returns_frame["stale"]]
        starts = _stale_run_starts(returns_frame["stale"])
        for (date, ticker), _row in stale.loc[starts].iterrows():
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "event_type": "stale_start",
                    "detail": "first day of a zero-return run of 5 or more days",
                }
            )
    if not rows:
        return pd.DataFrame(columns=["date", "ticker", "event_type", "detail"])
    out = pd.DataFrame(rows)
    out["date"] = pd.to_datetime(out["date"])
    return out.sort_values(["date", "ticker"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# Sprint E7: the alpha evaluation harness and the multiple-testing ledger.
# The E1 hygiene rules above detect bad data; this section measures whether
# a signal survives hygiene: the shift audit, the IC and its decay, factor
# neutralization, quantile portfolios, the fundamental-law check, and the
# multiple-testing corrections.
# --------------------------------------------------------------------------

NEWEY_WEST_LAGS = 5
HLZ_T_HURDLE = 3.0
LEAK_T_SIGNIFICANCE = 1.96  # two-sided 5 percent for the leakage test


def _signal_wide(signal_frame: pd.DataFrame) -> pd.DataFrame:
    """The signal as dates down, tickers across, NaN kept."""
    wide = signal_frame.pivot(index="date", columns="ticker", values="signal")
    return wide.sort_index()


def spearman_ic(
    signal_frame: pd.DataFrame, wide: pd.DataFrame, horizon: int = 1
) -> pd.Series:
    """IC_t = rank-correlation(s_t, r_{t..t+horizon-1}), per date.

    INPUT: the signal long frame and the returns panel.
    OUTPUT: the daily IC series, NaN where fewer than 10 pairs exist.
    """
    s_wide = _signal_wide(signal_frame)
    forward = (1.0 + wide).rolling(horizon).apply(lambda x: x.prod(), raw=True).shift(
        -(horizon - 1)
    ) - 1.0
    common_dates = s_wide.index.intersection(forward.index)
    values: list[float] = []
    dates: list[pd.Timestamp] = []
    for date in common_dates:
        s = s_wide.loc[date]
        r = forward.loc[date]
        both = pd.concat([s, r], axis=1).dropna()
        if len(both) < 10:
            values.append(float("nan"))
        else:
            values.append(float(both.iloc[:, 0].rank().corr(both.iloc[:, 1].rank())))
        dates.append(date)
    return pd.Series(values, index=pd.DatetimeIndex(dates), name="ic")


def newey_west_t(series: pd.Series) -> float:
    """The Newey-West t-statistic of a series against zero."""
    values = series.dropna().to_numpy(dtype=float)
    n = len(values)
    if n < 10:
        return float("nan")
    mean = float(values.mean())
    centered = values - mean
    variance = float(np.sum(centered**2)) / n
    lag_sum = 0.0
    for lag in range(1, NEWEY_WEST_LAGS + 1):
        if n <= lag:
            break
        weight = 1.0 - lag / (NEWEY_WEST_LAGS + 1)
        lag_sum += weight * float(np.sum(centered[lag:] * centered[:-lag])) / n
    variance = max(variance + 2.0 * lag_sum, 1e-12)
    return float(mean / np.sqrt(variance / n))


def shift_audit(
    signal_frame: pd.DataFrame,
    lagged_signal_frame: pd.DataFrame,
    wide: pd.DataFrame,
) -> pd.DataFrame:
    """F7.1: does the signal lose its edge when its inputs are lagged?

    The lagged signal is rebuilt on the same construction with every input
    moved one day back, simulating data available one day earlier. A clean
    signal keeps its IC against r_t: the information was already in the
    lagged data. A leaked signal flips or dies, because the extra day's
    data carried the edge. The reverse probe pairs s_t with r_{t+1}: a
    signal that predicts tomorrow but not today carries future data.
    """
    ic_now = spearman_ic(signal_frame, wide, horizon=1)
    ic_lagged = spearman_ic(lagged_signal_frame, wide, horizon=1)
    ic_forward = spearman_ic(signal_frame, wide.shift(-1), horizon=1)
    joined = pd.concat(
        [
            ic_now.rename("ic"),
            ic_lagged.rename("ic_back"),
            ic_forward.rename("ic_next"),
        ],
        axis=1,
    )
    mean_now = float(ic_now.mean())
    mean_lagged = float(ic_lagged.mean())
    t_now = newey_west_t(ic_now)
    t_lagged = newey_west_t(ic_lagged)
    t_forward = newey_west_t(ic_forward)
    flipped = bool(
        (mean_now > 0 and mean_lagged < 0) or (mean_now < 0 and mean_lagged > 0)
    )
    killed = bool(abs(t_lagged) < LEAK_T_SIGNIFICANCE or not np.isfinite(t_lagged))
    significant_now = bool(abs(t_now) >= LEAK_T_SIGNIFICANCE and np.isfinite(t_now))
    significant_forward = bool(
        abs(t_forward) >= LEAK_T_SIGNIFICANCE and np.isfinite(t_forward)
    )
    same_day_leak = bool(significant_now and (flipped or killed))
    # the reverse direction: the signal predicts tomorrow but not today,
    # which means it carries information from the future
    future_leak = bool(significant_forward and not significant_now)
    joined["leak_flag"] = bool(same_day_leak or future_leak)
    joined["flipped"] = flipped
    joined["killed"] = killed
    joined["significant_now"] = significant_now
    joined["mean_ic"] = mean_now
    joined["mean_ic_next"] = float(ic_forward.mean())
    joined["t_ic"] = t_now
    joined["t_ic_next"] = t_forward
    joined["t_ic_lagged"] = t_lagged
    return joined


def empirical_shift_audit(
    signal_frame: pd.DataFrame,
    forward_signal_frame: pd.DataFrame,
    wide: pd.DataFrame,
) -> dict[str, float | bool]:
    """F7.1b: the empirical shift audit.

    The signal is rebuilt with every input advanced one day and paired with
    the same-day return. An honest signal that predicts r_t from data
    through t-1 flips or dies once the extra day enters its window. A
    signal whose IC survives the shift is carrying the shifted window's
    edge: announcement-day information for a lagged publication, or edge
    persistence for a construction whose window still skips the same-day
    return. Which one it is, the caller records, never this function.
    """
    ic_before = spearman_ic(signal_frame, wide, horizon=1)
    ic_after = spearman_ic(forward_signal_frame, wide, horizon=1)
    mean_before = float(ic_before.mean())
    mean_after = float(ic_after.mean())
    t_before = newey_west_t(ic_before)
    t_after = newey_west_t(ic_after)
    flipped = bool(
        (mean_before > 0 and mean_after < 0) or (mean_before < 0 and mean_after > 0)
    )
    killed = bool(not np.isfinite(t_after) or abs(t_after) < LEAK_T_SIGNIFICANCE)
    survives = bool(
        not flipped and not killed and np.isfinite(t_before) and np.isfinite(t_after)
    )
    return {
        "ic_before_mean": mean_before,
        "t_before": t_before,
        "ic_after_mean": mean_after,
        "t_after": t_after,
        "flipped": flipped,
        "killed": killed,
        "survives": survives,
    }


def neutralize(
    signal_frame: pd.DataFrame,
    wide: pd.DataFrame,
    date: pd.Timestamp,
    root: Path,
) -> pd.DataFrame:
    """s_perp = s - X (X'X)^-1 X' s on one rebalance date.

    INPUT: the signal long frame, the returns panel, the date, the data
    root. OUTPUT: the neutralized signal for that date, NaN kept.
    """
    from efb import eval_risk, race

    names = eval_risk._window_names(wide, date)
    if len(names) < 50:
        return pd.DataFrame(columns=["date", "ticker", "signal"])
    design = race._descriptor_design(date, names, root)
    design = np.nan_to_num(design, nan=0.0, posinf=0.0, neginf=0.0)
    rows = signal_frame.loc[pd.to_datetime(signal_frame["date"]) == date]
    if rows.empty:
        return pd.DataFrame(columns=["date", "ticker", "signal"])
    s = rows.set_index("ticker")["signal"].reindex(names).to_numpy(dtype=float)
    s = np.where(np.isnan(s), np.nanmedian(s), s)
    factor_loadings = np.linalg.solve(design.T @ design, design.T @ s)
    residual = s - design @ factor_loadings
    return pd.DataFrame({"date": date, "ticker": names, "signal": residual})


def neutralized_ic(
    signal_frame: pd.DataFrame,
    wide: pd.DataFrame,
    grid: list[pd.Timestamp],
    root: Path,
    horizon: int = 21,
) -> pd.Series:
    """The factor-neutral IC measured at each rebalance date.

    The signal is neutralized on the rebalance date's design and correlated
    with the forward return from that date. NaN kept.
    """
    forward = (1.0 + wide).rolling(horizon).apply(lambda x: x.prod(), raw=True).shift(
        -(horizon - 1)
    ) - 1.0
    values: list[float] = []
    dates: list[pd.Timestamp] = []
    for date in grid:
        s_perp = neutralize(signal_frame, wide, date, root)
        if s_perp.empty:
            continue
        returns = forward.loc[date].reindex(s_perp["ticker"])
        both = pd.concat(
            [s_perp.set_index("ticker")["signal"], returns], axis=1
        ).dropna()
        if len(both) < 10:
            values.append(float("nan"))
        else:
            values.append(float(both.iloc[:, 0].rank().corr(both.iloc[:, 1].rank())))
        dates.append(date)
    return pd.Series(values, index=pd.DatetimeIndex(dates), name="ic_neutralized")


def quantile_portfolios(
    signal_frame: pd.DataFrame,
    wide: pd.DataFrame,
    grid: list[pd.Timestamp],
    n_quantiles: int = 5,
) -> pd.DataFrame:
    """Equal-weight quintile portfolios of the signal, rebalanced monthly.

    OUTPUT: one row per portfolio-day with the portfolio return under the
    E5 missing-data semantics. The spread is Q5 minus Q1.
    """
    from efb import eval_risk

    s_wide = _signal_wide(signal_frame)
    rows: list[dict[str, object]] = []
    last = grid[-1] + pd.Timedelta(days=40)
    for start, end in zip(grid, grid[1:] + [last], strict=True):
        s = s_wide.loc[s_wide.index <= start].iloc[-1]
        valid = s.dropna()
        if len(valid) < n_quantiles * 5:
            continue
        buckets = pd.qcut(valid.rank(method="first"), n_quantiles, labels=False)
        window = wide.loc[(wide.index > start) & (wide.index <= end)]
        for bucket in range(n_quantiles):
            names = valid.index[buckets == bucket]
            weights = pd.Series(1.0 / len(names), index=names)
            weight_row = weights.reindex(wide.columns).fillna(0.0).to_numpy(dtype=float)
            returns = eval_risk._portfolio_returns(
                weight_row[None, :], window.to_numpy(dtype=float)
            )[0]
            rows.extend(
                {
                    "date": date,
                    "quantile": int(bucket + 1),
                    "return": float(value),
                }
                for date, value in zip(window.index, returns, strict=True)
            )
    return pd.DataFrame(rows, columns=["date", "quantile", "return"])


def fundamental_law(ic: pd.Series, breadth: int) -> dict[str, float]:
    """IR = IC x sqrt(breadth) against the realized IR of the IC stream."""
    mean_ic = float(ic.mean())
    realized_ir = (
        float(ic.mean() / ic.std(ddof=1)) if ic.std(ddof=1) > 0 else float("nan")
    )
    implied_ir = mean_ic * float(np.sqrt(breadth))
    return {
        "mean_ic": mean_ic,
        "std_ic": float(ic.std(ddof=1)),
        "breadth": float(breadth),
        "implied_ir": implied_ir,
        "realized_ir": realized_ir,
    }


def _norm_ppf(probability: float) -> float:
    """The standard normal quantile, from scipy's ndtri."""
    from scipy.special import ndtri  # type: ignore[import-untyped]

    return float(ndtri(probability))


def deflated_sharpe(sharpe: float, n_trials: int, n_obs: int) -> dict[str, float]:
    """Bailey and Lopez de Prado's deflated Sharpe with normal returns."""
    import math

    if n_obs <= 1 or not np.isfinite(sharpe):
        return {
            "sharpe": float(sharpe),
            "deflated_sharpe": float("nan"),
            "expected_max_sharpe": float("nan"),
            "n_trials": float(n_trials),
            "n_obs": float(n_obs),
        }
    variance = (1.0 + 0.5 * sharpe**2) / (n_obs - 1)
    gamma = 0.5772156649
    expected_max = math.sqrt(variance) * (
        (1.0 - gamma) * _norm_ppf(1.0 - 1.0 / max(n_trials, 1))
        + gamma * _norm_ppf(1.0 - 1.0 / (max(n_trials, 1) * math.e))
    )
    return {
        "sharpe": float(sharpe),
        "deflated_sharpe": float(sharpe - expected_max),
        "expected_max_sharpe": float(expected_max),
        "n_trials": float(n_trials),
        "n_obs": float(n_obs),
    }


def bonferroni_t_threshold(n_trials: int) -> float:
    """The Bonferroni t-threshold for M variants at 5 percent, two-sided."""
    return float(_norm_ppf(1.0 - 0.025 / max(n_trials, 1)))


def regime_ic(ic: pd.Series, vix: pd.Series) -> pd.DataFrame:
    """The IC within VIX terciles, with the pooled mean for comparison."""
    aligned = pd.concat(
        [ic.rename("ic"), vix.reindex(ic.index).rename("vix")], axis=1
    ).dropna()
    if aligned.empty:
        return pd.DataFrame(columns=["regime", "mean_ic", "n_days"])
    aligned["regime"] = pd.qcut(
        aligned["vix"], 3, labels=["vix_low", "vix_mid", "vix_high"]
    )
    table = (
        aligned.groupby("regime", observed=False)["ic"]
        .agg(mean_ic="mean", n_days="count")
        .reset_index()
    )
    pooled = pd.DataFrame(
        {
            "regime": ["pooled"],
            "mean_ic": [float(ic.mean())],
            "n_days": [int(ic.notna().sum())],
        }
    )
    return pd.concat([pooled, table], ignore_index=True)


def write_ledger(rows: list[dict[str, object]], path: Path) -> None:
    """Append signal runs to the multiple-testing ledger, never rewrite it."""
    if not rows:
        return
    header = (
        "| run_id | signal | variant | horizon | ic_mean | t_stat | "
        "deflated_sharpe | hlz_t_hurdle | bonferroni_t | verdict | note |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# Multiple-Testing Ledger\n\n"
            "Append-only. One row per signal run, including every failed "
            "variant. Written by the engine in `efb/hygiene.py`, never edited "
            "by hand. The row count is a stored number in sprints/E7.\n\n"
            + header
            + "\n"
        )
    lines: list[str] = []
    for row in rows:
        template = (
            "| {run_id} | {signal} | {variant} | {horizon} | {ic_mean} | "
            "{t_stat} | {deflated_sharpe} | {hlz_t_hurdle} | {bonferroni_t} | "
            "{verdict} | {note} |"
        )
        lines.append(
            template.format(
                run_id=row["run_id"],
                signal=row["signal"],
                variant=row["variant"],
                horizon=row["horizon"],
                ic_mean=row["ic_mean"],
                t_stat=row["t_stat"],
                deflated_sharpe=row["deflated_sharpe"],
                hlz_t_hurdle=row["hlz_t_hurdle"],
                bonferroni_t=row["bonferroni_t"],
                verdict=row["verdict"],
                note=row["note"],
            )
        )
    with path.open("a") as handle:
        handle.write("\n".join(lines) + "\n")
