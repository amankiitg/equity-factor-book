"""Sprint E8 Task 7: the stored results file for F8.1 to F8.6."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from efb import evaluate

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "sprints" / "E8" / "RESULTS.json"

CRITERIA = ["F8.1", "F8.2", "F8.3", "F8.4", "F8.5", "F8.6"]


def _results() -> dict:
    if not RESULTS.exists():
        pytest.skip("E8 results not written yet")
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
    assert evaluate.e8_data_hash() == payload["data_hash"]


@pytest.mark.integration
def test_the_stored_criteria_equal_the_recomputed_ones() -> None:
    payload = _results()
    fresh = evaluate.evaluate_e8_criteria(**evaluate.compute_e8_from_artifacts())
    for name in CRITERIA:
        assert (
            fresh[name]["stored_numbers"] == payload["criteria"][name]["stored_numbers"]
        ), name
        assert fresh[name]["verdict"] == payload["criteria"][name]["verdict"], name


@pytest.mark.integration
def test_the_criterion_text_is_never_reworded() -> None:
    payload = _results()
    for name in CRITERIA:
        assert payload["criteria"][name]["criterion"] == evaluate.E8_CRITERIA_TEXT[name]


@pytest.mark.integration
def test_the_transfer_coefficient_table_is_stored() -> None:
    payload = _results()
    stored = payload["criteria"]["F8.5"]["stored_numbers"]
    assert stored
    for _construction, block in stored.items():
        for _rho, numbers in block.items():
            assert {
                "realized_ir",
                "realized_ic",
                "n_eff",
                "n_names",
                "predicted_ir_neff",
                "transfer_coefficient_neff",
                "transfer_coefficient_n",
            } <= set(numbers)
