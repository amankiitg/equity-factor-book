"""Sprint E7 Task 6: dashboard D6 Alpha Lab panels.

Every panel builder raises on an empty read, the panels read real artifacts,
and the ledger panel parses the engine-written markdown.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dashboard.tabs import d06_alpha_lab as d6

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_d6_panel_builders_read_real_artifacts() -> None:
    assert not d6.load_summary().empty
    for name in d6.SIGNALS:
        path = d6.ALPHA / name / "ic.parquet"
        if path.exists():
            assert not d6.ic_panel(name).empty
            assert not d6.decay_panel(name).empty
            assert not d6.neutral_panel(name).empty
            assert not d6.quantile_panel(name).empty
            assert not d6.regime_panel(name).empty
    assert not d6.ledger_panel().empty


@pytest.mark.integration
def test_d6_ledger_panel_has_the_engine_columns() -> None:
    ledger = d6.ledger_panel()
    assert list(ledger.columns) == [
        "run_id",
        "signal",
        "variant",
        "horizon",
        "ic_mean",
        "t_stat",
        "deflated_sharpe",
        "hlz_t_hurdle",
        "bonferroni_t",
        "verdict",
        "note",
    ]


@pytest.mark.integration
def test_d6_quantile_panel_carries_the_spread_and_hit_rate() -> None:
    panel = d6.quantile_panel("momentum_12_1")
    keys = set(panel["quantile"].dropna())
    assert {"hit_rate", "spread_mean_daily"} <= keys


@pytest.mark.parametrize(
    "loader",
    [d6.load_summary, d6.ledger_panel],
)
def test_d6_loaders_raise_on_missing_artifact(loader, tmp_path) -> None:
    import dashboard.tabs.d06_alpha_lab as module

    original = (module.ALPHA, module.LEDGER_PATH)
    module.ALPHA = tmp_path / "alpha"
    module.LEDGER_PATH = tmp_path / "ledger.md"
    try:
        with pytest.raises((FileNotFoundError, ValueError)):
            loader()
    finally:
        module.ALPHA, module.LEDGER_PATH = original
