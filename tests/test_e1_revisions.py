"""Tests for close-out task C2: re-storing E1 on the corrected data.

E1's criteria were first stored before the reused-symbol exclusions
existed. Re-running E1 changes some of them, and the rule for this sprint
is that no stored number is quietly overwritten: the old and the new value
are kept side by side with the data hash that produced each.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from efb import evaluate

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "sprints" / "E1" / "RESULTS.json"


def _old_payload() -> dict:
    return {
        "sprint": "E1",
        "evaluated_at": "2026-09-04T00:00:00+00:00",
        "criteria": {
            "F1.1": {
                "criterion": "original text",
                "threshold": "95%",
                "stored_numbers": {"share": 0.90},
                "verdict": "fail",
            },
            "F1.3": {
                "criterion": "original text",
                "threshold": "0.9",
                "stored_number": 0.9557,
                "verdict": "pass",
            },
        },
    }


def _new_criteria() -> dict:
    return {
        "F1.1": {
            "criterion": "original text",
            "threshold": "95%",
            "stored_numbers": {"share": 0.88},
            "verdict": "fail",
        },
        "F1.3": {
            "criterion": "original text",
            "threshold": "0.9",
            "stored_number": 0.9557,
            "verdict": "pass",
        },
    }


def test_revisions_record_old_and_new_per_criterion(tmp_path: Path) -> None:
    path = tmp_path / "RESULTS.json"
    path.write_text(json.dumps(_old_payload()))
    evaluate.write_results(
        _new_criteria(),
        path,
        sprint="E1",
        data_hash="newhash000",
        previous_data_hash="oldhash000",
    )
    payload = json.loads(path.read_text())
    revisions = payload["revisions"]
    assert revisions["previous_data_hash"] == "oldhash000"
    assert revisions["data_hash"] == "newhash000"
    assert set(revisions["changed"]) == {"F1.1", "F1.3"}

    moved = revisions["changed"]["F1.1"]
    assert moved["changed"] is True
    assert moved["old"]["stored_numbers"] == {"share": 0.90}
    assert moved["new"]["stored_numbers"] == {"share": 0.88}
    assert moved["old"]["verdict"] == "fail"

    same = revisions["changed"]["F1.3"]
    assert same["changed"] is False
    assert same["old"]["stored_number"] == same["new"]["stored_number"] == 0.9557


def test_revisions_count_what_moved(tmp_path: Path) -> None:
    path = tmp_path / "RESULTS.json"
    path.write_text(json.dumps(_old_payload()))
    evaluate.write_results(
        _new_criteria(),
        path,
        sprint="E1",
        data_hash="newhash000",
        previous_data_hash="oldhash000",
    )
    revisions = json.loads(path.read_text())["revisions"]
    assert revisions["n_changed"] == 1
    assert revisions["changed_tickers_or_criteria"] == ["F1.1"]


def test_the_criteria_themselves_are_not_rewritten(tmp_path: Path) -> None:
    # the rule for the sprint: a stored criterion is never reworded or
    # re-scored, only re-measured, and the old value stays on the record
    path = tmp_path / "RESULTS.json"
    path.write_text(json.dumps(_old_payload()))
    evaluate.write_results(
        _new_criteria(),
        path,
        sprint="E1",
        data_hash="newhash000",
        previous_data_hash="oldhash000",
    )
    payload = json.loads(path.read_text())
    assert payload["criteria"]["F1.1"]["criterion"] == "original text"
    assert payload["criteria"]["F1.1"]["threshold"] == "95%"


def test_first_run_has_no_previous_values(tmp_path: Path) -> None:
    path = tmp_path / "RESULTS.json"
    evaluate.write_results(
        _new_criteria(), path, sprint="E1", data_hash="hash1", previous_data_hash=None
    )
    revisions = json.loads(path.read_text())["revisions"]
    assert revisions["previous_data_hash"] is None
    assert revisions["n_changed"] == 0
    # every criterion still records its measurement, with nothing to compare
    assert set(revisions["changed"]) == {"F1.1", "F1.3"}
    for key, block in revisions["changed"].items():
        assert block["old"] is None, key
        assert block["new"]["verdict"] in {"pass", "fail"}, key
        assert block["changed"] is False, key


def test_real_e1_results_carry_revisions_if_present() -> None:
    if not RESULTS.exists():
        pytest.skip("E1 results not built yet")
    payload = json.loads(RESULTS.read_text())
    if "revisions" not in payload:
        pytest.skip("E1 has not been re-stored yet")
    revisions = payload["revisions"]
    assert "data_hash" in revisions
    assert "previous_data_hash" in revisions
    for key, block in revisions["changed"].items():
        assert block["changed"] in {True, False}, key
        assert isinstance(block["old"], dict) or block["old"] is None, key
        assert isinstance(block["new"], dict), key
