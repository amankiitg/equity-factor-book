"""Tests for Task 8: dashboard D0 panel builders (parquet in, numbers out)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dashboard.tabs import d00_data


def _prices(tmp_path: Path) -> pd.DataFrame:
    dates = pd.bdate_range("2026-07-01", periods=4)
    idx = pd.MultiIndex.from_product([dates, ["AAA", "BBB"]], names=["date", "ticker"])
    frame = pd.DataFrame(
        {
            "close": 1.0,
            "adj_close": [1.0, 2.0, 3.0, 4.0, 1.0, np.nan, 2.0, 3.0],
            "volume": 100,
            "dividend": 0.0,
            "split_factor": 0.0,
        },
        index=idx,
    )
    frame.to_parquet(tmp_path / "prices.parquet")
    return frame


def _returns(tmp_path: Path) -> pd.DataFrame:
    dates = pd.bdate_range("2026-07-01", periods=4)
    idx = pd.MultiIndex.from_product([dates, ["AAA", "BBB"]], names=["date", "ticker"])
    frame = pd.DataFrame(
        {
            "r": [0.01, 0.0, 0.0, 0.0, 0.01, 0.0, 0.0, 0.0],
            "g": 0.0,
            "excess": 0.0,
            "stale": [False, True, True, True, False, True, True, True],
            "outlier": False,
        },
        index=idx,
    )
    frame.to_parquet(tmp_path / "returns.parquet")
    return frame


def test_coverage_matrix_shape_and_values(tmp_path: Path) -> None:
    prices = _prices(tmp_path)
    matrix = d00_data.coverage_matrix(prices)
    assert matrix.shape == (1, 2)
    assert matrix.loc["2026-07", "AAA"] == pytest.approx(1.0)
    assert matrix.loc["2026-07", "BBB"] == pytest.approx(0.75)


def test_missing_tickers(tmp_path: Path) -> None:
    _returns(tmp_path)
    ret = pd.read_parquet(tmp_path / "returns.parquet")
    missing = d00_data.missing_tickers(ret, as_of="2026-07-07")
    assert missing == []


def test_stale_counts(tmp_path: Path) -> None:
    ret = _returns(tmp_path)
    counts = d00_data.stale_counts(ret)
    assert counts["AAA"] == 2
    assert counts["BBB"] == 4


def test_universe_size_and_changes(tmp_path: Path) -> None:
    members = pd.DataFrame(
        {
            "AAA": [True, True, True, False],
            "BBB": [False, True, True, True],
            "CCC": [True, True, True, True],
        },
        index=pd.bdate_range("2026-07-01", periods=4),
    )
    members.to_parquet(tmp_path / "universe_membership.parquet")
    size = d00_data.universe_size(members)
    assert size.iloc[0] == 2
    assert size.iloc[-1] == 2
    changes = d00_data.membership_change_summary(members)
    assert changes["added"].sum() == 1
    assert changes["removed"].sum() == 1


def test_event_counts(tmp_path: Path) -> None:
    events = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-07-01", "2026-07-02"]),
            "ticker": ["AAA", "BBB"],
            "event_type": ["outlier", "split"],
            "detail": ["", ""],
        }
    )
    events.to_parquet(tmp_path / "events.parquet")
    counts = d00_data.event_counts(events)
    assert counts["outlier"] == 1
    assert counts["split"] == 1


def test_modules_import() -> None:
    import dashboard.app  # noqa: F401
    import dashboard.tabs.methodology  # noqa: F401

    assert callable(d00_data.render)
