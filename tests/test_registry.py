"""Tests for Task 6: the model registry."""

import json
from pathlib import Path

from efb import registry


def _inputs(tmp_path: Path) -> tuple[Path, list[Path]]:
    universe = tmp_path / "universe_membership.parquet"
    universe.write_bytes(b"universe")
    data_a = tmp_path / "returns.parquet"
    data_a.write_bytes(b"returns")
    return universe, [data_a]


def test_model_entry_has_required_fields_and_hashes(tmp_path: Path) -> None:
    universe, data_paths = _inputs(tmp_path)
    entry = registry.model_entry(
        version="TS-v1",
        family="timeseries",
        parameters={"window": 252},
        universe_path=universe,
        data_paths=data_paths,
        walkthrough="notebooks/E2_walkthrough.ipynb",
        deliverable="docs/research/E2_exposure_study.md",
        results="sprints/E2/RESULTS.json",
    )
    expected = {
        "version",
        "family",
        "parameters",
        "universe_hash",
        "data_hash",
        "built_at",
        "champion",
        "eligible_for_champion",
        "walkthrough",
        "deliverable",
        "results",
    }
    assert set(entry) == expected
    assert entry["version"] == "TS-v1"
    assert entry["champion"] is False
    assert entry["eligible_for_champion"] is False
    assert entry["universe_hash"] == registry.file_hash(universe)
    assert entry["data_hash"] == registry.file_hash(data_paths[0])


def test_write_registry_preserves_rules_and_upserts(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "champion_rule": "min mean |bias-1| across portfolio families",
                "family_notes": (
                    "timeseries models on external factors are diagnostic only"
                ),
                "models": {},
            }
        )
    )
    universe, data_paths = _inputs(tmp_path)
    entry = registry.model_entry(
        "TS-v1", "timeseries", {}, universe, data_paths, "w", "d", "r"
    )
    payload = registry.write_registry(path, entry)
    assert payload["champion_rule"] == "min mean |bias-1| across portfolio families"
    assert (
        payload["family_notes"]
        == "timeseries models on external factors are diagnostic only"
    )
    assert set(payload["models"]) == {"TS-v1"}
    # updating the same version keeps one entry
    registry.write_registry(path, {**entry, "parameters": {"window": 252}})
    reloaded = json.loads(path.read_text())
    assert set(reloaded["models"]) == {"TS-v1"}
    assert reloaded["models"]["TS-v1"]["parameters"] == {"window": 252}
