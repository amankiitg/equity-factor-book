"""Sprint E10 Task 9: the D9 dashboard panels read the allocation artifacts."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from dashboard.tabs import d09_risk_allocation as d9

ROOT = Path(__file__).resolve().parents[1]
ALLOC = ROOT / "data" / "allocation"


@pytest.fixture(scope="module", autouse=True)
def _require_artifacts() -> None:
    if not (ALLOC / "kelly.parquet").exists():
        pytest.skip("the E10 run has not completed", allow_module_level=True)


def test_kelly_panel_is_labeled() -> None:
    panel = d9.kelly_panel()
    assert not panel.empty
    assert "full Kelly leverage" in panel.columns
    assert "half Kelly leverage" in panel.columns


def test_drawdown_panel_reads_the_artifact() -> None:
    panel = d9.drawdown_panel()
    assert not panel.empty
    assert "simulated_median_drawdown" in panel.columns


def test_voltarget_panel_reads_the_artifact() -> None:
    panel = d9.voltarget_panel()
    assert not panel.empty
    assert "dispersion_reduction" in panel.columns


def test_stoploss_panel_reads_the_artifact() -> None:
    panel = d9.stoploss_panel()
    assert not panel.empty
    assert {"book", "base_sharpe", "real_book_sharpe_diff"} <= set(panel.columns)


def test_regime_panel_reads_the_artifact() -> None:
    panel = d9.regime_panel()
    assert not panel.empty
    assert "vix_tercile" in panel.columns


def test_empty_read_raises() -> None:
    with pytest.raises(ValueError):
        d9._require(pd.DataFrame(), "empty")
