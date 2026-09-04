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
