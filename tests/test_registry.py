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


def test_write_registry_keeps_the_live_construction(tmp_path: Path) -> None:
    """A rebuild upserts its own fields and must not drop the live decision.

    Measured on the backport branch: `efb.build.rebuild_e3` replaced the whole
    XS-v1 entry, dropped `live`, and every rebuild after that sized the book
    with no floor, so the "kept" book came back as all 502 names.
    """
    path = tmp_path / "registry.json"
    universe, data_paths = _inputs(tmp_path)
    entry = registry.model_entry(
        "XS-v1", "statistical", {}, universe, data_paths, "w", "d", "r"
    )
    entry["live"] = {
        "construction": "share_only",
        "share_floor": 20,
        "dollar_floor": 0,
        "floor_iterated": True,
    }
    registry.write_registry(path, entry)
    assert registry.live_construction(registry.load(path), "XS-v1")["share_floor"] == 20
    # the rebuild registers the same version again and does not set `live`
    rebuilt = registry.model_entry(
        "XS-v1", "statistical", {"window": 504}, universe, data_paths, "w", "d", "r"
    )
    assert "live" not in rebuilt
    registry.write_registry(path, rebuilt)
    reloaded = registry.load(path)
    assert (
        registry.live_construction(reloaded, "XS-v1")["share_floor"] == 20
    ), "a rebuild dropped the owner's construction and would size with no floor"
    # the rebuild's own fields still win
    assert reloaded["models"]["XS-v1"]["parameters"] == {"window": 504}
    assert reloaded["models"]["XS-v1"]["champion"] is False


def test_min_position_dollars_reads_the_registry_and_defaults_to_zero() -> None:
    payload = {
        "models": {
            "XS-v1": {"live": {"min_position_dollars": 5000}},
            "XS-v2": {},
        }
    }
    assert registry.min_position_dollars(payload, "XS-v1") == 5000.0
    assert registry.min_position_dollars(payload, "XS-v2") == 0.0


def test_live_construction_reads_the_share_only_choice() -> None:
    payload = {
        "models": {
            "XS-v1": {
                "live": {
                    "construction": "share_only",
                    "share_floor": 20,
                    "dollar_floor": 0,
                    "floor_iterated": True,
                }
            }
        }
    }
    assert registry.live_construction(payload, "XS-v1") == {
        "construction": "share_only",
        "share_floor": 20,
        "dollar_floor": 0.0,
        "floor_iterated": True,
    }


def test_live_construction_defaults_to_an_empty_construction() -> None:
    assert registry.live_construction({"models": {"XS-v2": {}}}, "XS-v1") == {
        "construction": "",
        "share_floor": 0,
        "dollar_floor": 0.0,
        "floor_iterated": False,
    }
