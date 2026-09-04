"""Tests for Task 6: hygiene detection rules and the event log."""

import numpy as np
import pandas as pd

from efb import hygiene


def _returns_frame(ticker: str, r: list[float]) -> pd.DataFrame:
    idx = pd.MultiIndex.from_product(
        [pd.bdate_range("2026-07-01", periods=len(r)), [ticker]], names=["date", "ticker"]
    )
    arr = np.asarray(r, dtype=float)
    return pd.DataFrame({"r": arr, "g": arr, "excess": arr}, index=idx)


def test_detect_stale_flags_zero_runs() -> None:
    r = [0.001, 0.0, 0.0, 0.0, 0.0, 0.0, 0.002, 0.0, 0.001, 0.0, 0.0]
    frame = _returns_frame("AAA", r)
    stale = hygiene.detect_stale(frame, min_run=5)
    by_date = stale.droplevel("ticker")
    # days 2..6 (index 1..5) are inside a run of 5 zeros
    assert by_date.iloc[1:6].all()
    assert not by_date.iloc[0]
    assert not by_date.iloc[6]
    # a run of 2 zeros is not stale
    assert not by_date.iloc[9]
    assert not by_date.iloc[10]


def test_detect_outliers_threshold() -> None:
    assert hygiene.is_outlier(0.60) is True
    assert hygiene.is_outlier(-0.51) is True
    assert hygiene.is_outlier(0.49) is False
    assert hygiene.is_outlier(np.nan) is False


def test_apply_flags_adds_columns() -> None:
    frame = _returns_frame("AAA", [0.001, 0.6, 0.0, 0.0, 0.0, 0.0, 0.0])
    out = hygiene.apply_flags(frame, min_run=5)
    assert {"stale", "outlier"} <= set(out.columns)
    assert bool(out.loc[(pd.Timestamp("2026-07-02"), "AAA"), "outlier"])
    assert bool(out.loc[(pd.Timestamp("2026-07-03"), "AAA"), "stale"])


def test_build_events_corporate_actions_and_flags() -> None:
    idx = pd.MultiIndex.from_product(
        [pd.bdate_range("2026-07-01", periods=4), ["AAA"]], names=["date", "ticker"]
    )
    prices = pd.DataFrame(
        {
            "close": [100.0, 102.0, 101.0, 50.0],
            "adj_close": [100.0, 102.0, 101.0, 50.0],
            "dividend": [0.0, 0.0, 1.5, 0.0],
            "split_factor": [0.0, 0.0, 0.0, 2.0],
        },
        index=idx,
    )
    ret = _returns_frame("AAA", [0.001, 0.02, 0.6, -0.0099])
    ret = hygiene.apply_flags(ret)
    events = hygiene.build_events(prices, ret, pd.DataFrame(columns=["date", "ticker", "event_type"]))
    types = events["event_type"].tolist()
    assert "dividend_large" in types  # 1.5 / 101.0 > 1%
    assert "split" in types  # split factor 2.0 on the last day
    assert "outlier" in types  # |r| = 0.6
