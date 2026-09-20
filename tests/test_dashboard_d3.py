"""Sprint E4 Task 5: registry v1 and the dashboard version selector.

The registry tests check the schema and the champion flag; nothing here
declares a champion, because that is E5's decision. The D3 tests check that
every panel builder refuses an empty read, which is how a panel that lost its
artifact fails loudly instead of drawing an empty chart.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from dashboard.tabs import d03_covariance as d3
from efb import cov, registry

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "models" / "registry.json"


@pytest.mark.integration
def test_registry_v1_schema_validates_and_the_rule_is_untouched() -> None:
    payload = registry.load(REGISTRY)
    problems = registry.validate(payload)
    assert problems == [], problems
    assert payload["champion_rule"] == registry.DEFAULT_CHAMPION_RULE
    assert payload["family_notes"] == registry.DEFAULT_FAMILY_NOTES


@pytest.mark.integration
def test_every_registered_version_is_known_and_no_champion_is_declared() -> None:
    payload = registry.load(REGISTRY)
    names = registry.versions(payload)
    for expected in ("TS-v1", "XS-v1", "PCA-v1", "PCA-v1c", "XS-v2"):
        assert expected in names, expected
    assert registry.champion(payload) is None, "no champion is declared before Task 5"
    assert registry.eligible(payload) == ["XS-v1", "PCA-v1", "PCA-v1c", "XS-v2"]
    assert registry.family_of(payload, "PCA-v1c") == "statistical"
    assert registry.family_of(payload, "XS-v1") == "fundamental"
    assert registry.family_of(payload, "XS-v2") == "fundamental"


def test_validate_reports_a_missing_key_and_a_family_typo() -> None:
    payload = {
        "note": "x",
        "champion_rule": "r",
        "family_notes": "n",
        "models": {
            "A-v1": {
                "version": "A-v1",
                "family": "statistical",
                "parameters": {},
                "universe_hash": "u",
                "data_hash": "d",
                "built_at": "t",
                "champion": False,
                "eligible_for_champion": True,
            },
            "B-v1": {
                "version": "B-v1",
                "family": "statisical",
                "parameters": {},
                "universe_hash": "u",
                "data_hash": "d",
                "built_at": "t",
                "champion": True,
                "eligible_for_champion": True,
            },
        },
    }
    problems = registry.validate(payload)
    assert any("statisical" in problem for problem in problems)
    del payload["models"]["A-v1"]["data_hash"]
    assert any("missing data_hash" in problem for problem in registry.validate(payload))


def test_champion_flag_is_reported_and_two_champions_are_a_problem() -> None:
    base = {"note": "x", "champion_rule": "r", "family_notes": "n", "models": {}}
    for name in ("A-v1", "B-v1"):
        base["models"][name] = {
            "version": name,
            "family": "statistical",
            "parameters": {},
            "universe_hash": "u",
            "data_hash": "d",
            "built_at": "t",
            "champion": name == "A-v1",
            "eligible_for_champion": True,
        }
    assert registry.champion(base) == "A-v1"
    base["models"]["B-v1"]["champion"] = True
    problems = registry.validate(base)
    assert any("more than one champion" in problem for problem in problems)


@pytest.mark.integration
def test_every_estimator_in_the_dispatch_has_a_parameter_count() -> None:
    for name in cov.ESTIMATORS:
        assert cov.parameter_count(name, 10, 3) > 0, name
    assert "pca_v1c" in cov.ESTIMATORS


@pytest.mark.integration
def test_d3_panel_builders_read_real_artifacts() -> None:
    assert not d3.eigenvalue_panel().empty
    assert not d3.explained_variance_panel().empty
    assert not d3.estimator_table_panel().empty
    assert not d3.halflife_panel().empty
    assert not d3.residual_direction_panel().empty
    correlations = d3.factor_correlation_panel()
    assert correlations.shape[0] >= 1 and correlations.shape[1] >= 1


@pytest.mark.parametrize(
    "builder",
    [
        "eigenvalue_panel",
        "explained_variance_panel",
        "factor_correlation_panel",
        "estimator_table_panel",
        "halflife_panel",
        "residual_direction_panel",
    ],
)
def test_every_d3_panel_raises_on_an_empty_read(
    monkeypatch: pytest.MonkeyPatch, builder: str
) -> None:
    """Every artifact load is stubbed empty, so each builder's guard must fire."""
    empty = pd.DataFrame()
    for loader in (
        "load_spectrum",
        "load_panel_spectrum",
        "load_residual_spectrum",
        "load_horse_race",
        "load_halflife_sweep",
        "load_residual_projection",
        "load_pca_factor_returns",
        "load_xs_factor_returns",
    ):
        monkeypatch.setattr(d3, loader, lambda *args, **kwargs: empty)
    with pytest.raises(ValueError):
        getattr(d3, builder)()


def test_the_version_selector_reads_the_registry() -> None:
    from dashboard import version as version_module

    options = version_module.available_versions()
    assert options[0] == "XS-v1", "the incumbent renders first by default"
    for name in options:
        assert isinstance(version_module.artifacts_for(name), dict)
        assert isinstance(version_module.spectrum_path(name), Path)
