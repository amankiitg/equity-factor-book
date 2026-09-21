"""Sprint E6 Task 6: dashboard D5 hedging panels.

Every panel builder raises on an empty read, the panels read real artifacts,
and the methodology links cover the sprint's own records.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dashboard.tabs import d05_hedging as d5

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_d5_panel_builders_read_real_artifacts() -> None:
    assert not d5.headline_panel().empty
    assert not d5.positions_panel().empty
    assert not d5.residual_exposure_panel().empty
    assert not d5.realized_panel().empty
    assert not d5.decay_panel().empty


@pytest.mark.integration
def test_d5_headline_panel_covers_both_models_and_methods() -> None:
    headline = d5.headline_panel()
    for model in ("xs_v1", "xs_v2"):
        assert (headline["model"] == model).any(), model
    for method in ("beta", "fmp", "min_variance"):
        assert (headline["method"] == method).any(), method


@pytest.mark.parametrize(
    "loader",
    [
        d5.load_metrics,
        d5.load_positions,
        d5.load_exposures,
        d5.load_efficacy,
        d5.load_decay,
    ],
)
def test_d5_loaders_raise_on_missing_artifact(loader, tmp_path) -> None:
    import dashboard.tabs.d05_hedging as module

    original = module.HEDGE
    module.HEDGE = tmp_path
    try:
        with pytest.raises((FileNotFoundError, ValueError)):
            loader()
    finally:
        module.HEDGE = original


@pytest.mark.integration
def test_methodology_links_exist() -> None:
    from dashboard.tabs import methodology

    for _label, rel in methodology.LINKS:
        if rel.startswith(("http://", "https://")):
            continue
        assert (ROOT / rel).exists(), rel
    assert any("E6" in rel for _label, rel in methodology.LINKS)
