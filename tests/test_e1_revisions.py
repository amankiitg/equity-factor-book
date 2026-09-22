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


def _store(path: Path, data_hash: str, value: float) -> dict:
    criteria = {
        "F1.1": {
            "criterion": "original text",
            "threshold": "95%",
            "stored_numbers": {"share": value},
            "verdict": "fail",
        }
    }
    evaluate.write_results(
        criteria,
        path,
        sprint="E1",
        data_hash=data_hash,
        previous_data_hash="prev",
    )
    return json.loads(path.read_text())["revisions"]


def test_a_second_correction_appends_to_the_history(tmp_path: Path) -> None:
    """C6 rebuilds E1 twice, so one revisions block is not enough.

    The first store has no earlier file, so its comparison is the first
    history entry. The second store, on a different data hash, appends
    rather than replacing, which keeps the first correction on the record.
    """
    path = tmp_path / "RESULTS.json"
    first = _store(path, "hash1", 0.90)
    second = _store(path, "hash2", 0.88)
    assert [entry["data_hash"] for entry in second["history"]] == ["hash1", "hash2"]
    # the top level still describes the newest comparison, as before; the
    # criterion and threshold ride along in every measurement since the
    # F10.1b re-registration recorded them with the verdict and numbers
    assert second["data_hash"] == "hash2"
    assert second["changed"]["F1.1"]["old"] == {
        "verdict": "fail",
        "criterion": "original text",
        "threshold": "95%",
        "stored_numbers": {"share": 0.90},
    }
    assert second["changed"]["F1.1"]["new"] == {
        "verdict": "fail",
        "criterion": "original text",
        "threshold": "95%",
        "stored_numbers": {"share": 0.88},
    }
    # the first entry keeps the values as they were when it was written
    assert first["history"][0]["changed"]["F1.1"]["old"] is None


def test_a_repeated_run_on_the_same_hash_does_not_append(tmp_path: Path) -> None:
    path = tmp_path / "RESULTS.json"
    _store(path, "hash1", 0.90)
    again = _store(path, "hash1", 0.90)
    assert len(again["history"]) == 1


def test_a_nan_value_is_not_a_change(tmp_path: Path) -> None:
    """A NaN per empty calendar year must not read as a moved number.

    NaN is not equal to itself, so a direct dict comparison reports the
    whole criterion as changed on every rebuild, which would put a fresh
    history entry in the file for a change that did not happen.
    """
    path = tmp_path / "RESULTS.json"
    payload = {
        "sprint": "E2",
        "criteria": {
            "F2.4": {
                "criterion": "text",
                "threshold": "0.8 to 1.2",
                "stored_numbers": {"bias_by_year": {"2026": float("nan")}},
                "verdict": "pass",
            }
        },
    }
    path.write_text(json.dumps(payload))
    evaluate.write_results(
        {
            "F2.4": {
                "criterion": "text",
                "threshold": "0.8 to 1.2",
                "stored_numbers": {"bias_by_year": {"2026": float("nan")}},
                "verdict": "pass",
            }
        },
        path,
        sprint="E2",
        data_hash="hash2",
        previous_data_hash="hash1",
    )
    revisions = json.loads(path.read_text())["revisions"]
    assert revisions["changed"]["F2.4"]["changed"] is False
    assert revisions["n_changed"] == 0
