"""Daily returns and stylized facts (Sprint E1, Task 4).

Returns are computed from adjusted close. Simple, log and excess
definitions follow the PRD: r = P/P(-1) - 1, g = ln(1 + r),
excess = r - rf. Log returns add over time; simple returns add across a
portfolio. No return is computed when either price leg is missing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_returns(frame: pd.DataFrame, rf: pd.Series) -> pd.DataFrame:
    """Compute simple, log and excess returns per ticker.

    frame: long prices with an adj_close column and a (date, ticker)
    MultiIndex. rf: daily risk-free rate in decimals indexed by date.
    Returns a long DataFrame with columns r, g, excess.
    """
    adj = frame["adj_close"]
    r = adj.groupby(level="ticker").transform(lambda s: s.pct_change(fill_method=None))
    g = np.log1p(r)
    rf_aligned = rf.reindex(adj.index.get_level_values("date").unique())
    rf_map = rf_aligned.reindex(adj.index.get_level_values("date")).to_numpy()
    excess = r - rf_map
    out = pd.DataFrame({"r": r, "g": g, "excess": excess}, index=frame.index)
    return out.sort_index()


def equal_weight_universe_return(
    returns_frame: pd.DataFrame, membership: pd.DataFrame
) -> pd.Series:
    """Daily equal-weight universe return from point-in-time membership.

    On each date, average the simple returns of every member with a
    non-NaN return. Members not traded on that date are skipped.
    """
    wide = returns_frame["r"].unstack("ticker")
    wide = wide.reindex(index=membership.index, columns=membership.columns)
    masked = wide.where(membership.astype(bool))
    return masked.mean(axis=1).rename("ew_universe")


def stylized_facts(series: pd.Series) -> dict[str, float]:
    """Kurtosis of daily returns and autocorrelations of r and r^2.

    series: a daily return series, NaNs dropped. Returns kurtosis (raw,
    normal is 3), ACF of r at lag 1, and ACF of r^2 at lags 1, 5, 21.
    """
    x = series.dropna()
    r2 = x**2
    return {
        "kurtosis": float(x.kurtosis() + 3.0),
        "acf_r_lag1": float(x.autocorr(lag=1)),
        "acf_r2_lag1": float(r2.autocorr(lag=1)),
        "acf_r2_lag5": float(r2.autocorr(lag=5)),
        "acf_r2_lag21": float(r2.autocorr(lag=21)),
    }


def index_alignment_report(frame: pd.DataFrame) -> dict[str, int]:
    """Checks the returns frame: duplicates, infs, non-business days."""
    dates = frame.index.get_level_values("date")
    return {
        "rows": len(frame),
        "duplicate_rows": int(frame.index.duplicated().sum()),
        "infs": int(
            np.isinf(frame.select_dtypes(include=[np.number]).to_numpy()).sum()
        ),
        "non_business_days": int((dates.dayofweek >= 5).sum()),
        "nans": int(frame["r"].isna().sum()),
    }
