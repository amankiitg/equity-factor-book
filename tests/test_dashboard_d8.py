"""Sprint E9 Task 8: dashboard D8 Cost and Capacity panels."""

from __future__ import annotations

from pathlib import Path

import pytest

from dashboard.tabs import d08_costs as d8

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_d8_panel_builders_read_real_artifacts() -> None:
    capacity_path = d8.COSTS / "capacity.parquet"
    if not capacity_path.exists():
        pytest.skip("the E9 run has not completed")
    assert not d8.load_cost_curves().empty
    assert not d8.load_capacity().empty
    assert not d8.load_halving().empty
    assert not d8.load_tradeoff().empty


@pytest.mark.integration
def test_d8_empty_reads_raise() -> None:
    import pandas as pd

    with pytest.raises(ValueError):
        d8._require(pd.DataFrame(), "an empty panel")
