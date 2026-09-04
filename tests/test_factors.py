"""Tests for Task 3: French factor loading, merging and RF cross-check."""

import numpy as np
import pandas as pd
import pytest

from efb import factors


def _frame(
    columns: list[str], periods: int = 10, start: str = "2020-01-02"
) -> pd.DataFrame:
    idx = pd.bdate_range(start=start, periods=periods, name="date")
    rng = np.random.default_rng(1)
    return pd.DataFrame(
        rng.normal(0.0005, 0.01, (periods, len(columns))), index=idx, columns=columns
    )


def test_merge_factors_aligns_union_of_dates() -> None:
    ff5 = _frame(["mkt_rf", "smb", "hml", "rmw", "cma", "rf"], periods=10)
    mom = _frame(["mom"], periods=8, start="2020-01-06")
    merged = factors.merge_factors(
        {
            "ff5": ff5,
            "mom": mom,
            "strev": _frame(["st_rev"]),
            "ind12": _frame([f"ind{i}" for i in range(1, 13)]),
        }
    )
    assert set(merged.columns) == {
        "mkt_rf",
        "smb",
        "hml",
        "rmw",
        "cma",
        "rf",
        "mom",
        "st_rev",
        "ind1",
        "ind2",
        "ind3",
        "ind4",
        "ind5",
        "ind6",
        "ind7",
        "ind8",
        "ind9",
        "ind10",
        "ind11",
        "ind12",
    }
    assert len(merged) == 10
    assert merged.index.is_monotonic_increasing
    assert np.isnan(merged.loc[merged.index < pd.Timestamp("2020-01-06"), "mom"]).all()


def test_cross_check_rf() -> None:
    rng = np.random.default_rng(2)
    idx = pd.bdate_range("2020-01-02", periods=500)
    dtb3 = pd.Series(rng.normal(1.0, 0.1, 500) / 252.0, index=idx)
    rf = dtb3 * 0.98 + 0.00001  # daily decimals
    result = factors.cross_check_rf(rf, dtb3)
    assert result["correlation"] == pytest.approx(1.0, abs=0.01)
    assert abs(result["mean_diff_bp"]) < 5.0


def test_cross_check_rf_returns_none_when_fred_missing() -> None:
    result = factors.cross_check_rf(pd.Series(dtype=float), pd.Series(dtype=float))
    assert result is None


def test_download_dtb3_failure_is_none(monkeypatch) -> None:
    import requests

    def _timeout(*args, **kwargs):
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr(factors.requests, "get", _timeout)
    assert factors.download_dtb3() is None
