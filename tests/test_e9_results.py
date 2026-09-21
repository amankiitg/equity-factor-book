"""Sprint E9 Task 6: the stored results file for F9.1 to F9.4."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from efb import evaluate

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "sprints" / "E9" / "RESULTS.json"

CRITERIA = ["F9.1", "F9.2", "F9.3", "F9.4"]


def _results() -> dict:
    if not RESULTS.exists():
        pytest.skip("E9 results not written yet")
    return json.loads(RESULTS.read_text())


@pytest.mark.integration
def test_every_criterion_is_present_with_a_verdict() -> None:
    payload = _results()
    assert set(CRITERIA) <= set(payload["criteria"])
    for name in CRITERIA:
        assert payload["criteria"][name]["verdict"] in ("pass", "fail")
        assert payload["criteria"][name]["stored_numbers"]


@pytest.mark.integration
def test_the_stored_hash_reproduces_from_the_artifacts() -> None:
    payload = _results()
    assert evaluate.e9_data_hash() == payload["data_hash"]


@pytest.mark.integration
def test_the_stored_criteria_equal_the_recomputed_ones() -> None:
    payload = _results()
    fresh = evaluate.evaluate_e9_criteria(**evaluate.compute_e9_from_artifacts())
    for name in CRITERIA:
        assert json.dumps(fresh[name]["stored_numbers"], sort_keys=True) == json.dumps(
            payload["criteria"][name]["stored_numbers"], sort_keys=True
        ), name
        assert fresh[name]["verdict"] == payload["criteria"][name]["verdict"], name


@pytest.mark.integration
def test_the_criterion_text_is_never_reworded() -> None:
    payload = _results()
    for name in CRITERIA:
        assert payload["criteria"][name]["criterion"] == evaluate.E9_CRITERIA_TEXT[name]
