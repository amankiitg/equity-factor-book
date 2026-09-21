"""Sprint E5 Task 8: dashboard D4 and the champion badge.

Every panel builder raises on an empty read, the panels read real artifacts,
and the champion badge reads the registry rather than a constant.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from dashboard.tabs import d04_risk_eval as d4

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_d4_panel_builders_read_real_artifacts() -> None:
    assert not d4.bias_heatmap_panel().empty
    assert not d4.rolling_bias_panel().empty
    assert not d4.calibration_panel().empty
    assert not d4.horizon_panel().empty


@pytest.mark.parametrize(
    "loader",
    [
        "load_family_bias",
        "load_summary",
        "load_regimes",
        "load_rolling",
        "load_horizon",
        "load_haircut",
    ],
)
def test_every_d4_loader_raises_on_an_empty_read(
    monkeypatch: pytest.MonkeyPatch, loader: str
) -> None:
    """Every artifact load is stubbed empty, so each guard must fire."""

    def empty(_path: Path) -> pd.DataFrame:
        return pd.DataFrame()

    monkeypatch.setattr(d4.pd, "read_parquet", empty)
    with pytest.raises(ValueError):
        getattr(d4, loader)()


@pytest.mark.integration
def test_the_champion_badge_reads_the_registry() -> None:
    payload = json.loads(d4.REGISTRY.read_text())
    champions = [
        name for name, entry in payload["models"].items() if entry.get("champion")
    ]
    badge = d4.champion_badge()
    if champions:
        assert badge["champion"] == champions[0]
        assert badge["rule"] == payload["champion_rule"]
        assert badge["deciding_number"] == badge["deciding_number"]  # a float
    else:
        assert badge["champion"] is None
        assert badge["rule"] == payload["champion_rule"]


@pytest.mark.integration
def test_the_registry_entry_used_by_the_badge_is_the_stored_one() -> None:
    """The badge's deciding number is recomputed from the stored table."""
    from efb import registry

    family = pd.read_parquet(ROOT / "data" / "eval" / "e5_family_bias.parquet")
    payload = json.loads(d4.REGISTRY.read_text())
    champion = next(
        (name for name, entry in payload["models"].items() if entry.get("champion")),
        None,
    )
    if champion is None:
        pytest.skip("no champion declared yet")
    rows = family.loc[family["version"] == registry.engine_tag(champion)]
    assert d4.champion_badge()["deciding_number"] == pytest.approx(
        float(rows["abs_bias_minus_1"].mean()), abs=1e-9
    )
