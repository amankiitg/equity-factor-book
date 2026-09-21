"""Sprint E8 Task 9: dashboard D7 Sizing and Optimizer panels."""

from __future__ import annotations

from pathlib import Path

import pytest

from dashboard.tabs import d07_sizing as d7

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_d7_panel_builders_read_real_artifacts() -> None:
    summary_path = d7.PORTFOLIOS / "e8_summary.parquet"
    if not summary_path.exists():
        pytest.skip("the E8 run has not completed")
    assert not d7.load_summary().empty
    for name in d7.CONSTRUCTIONS:
        path = d7.PORTFOLIOS / f"{name}.parquet"
        if path.exists():
            assert not d7.load_construction(name).empty


@pytest.mark.integration
def test_d7_empty_reads_raise() -> None:
    import pandas as pd

    with pytest.raises(ValueError):
        d7._require(pd.DataFrame(), "an empty panel")
