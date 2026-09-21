"""Sprint E7 Task 4 and 7: the stored results file and the RG-Signal gate.

The criteria are re-evaluated from the artifacts on disk, so any drift
between the artifacts and the stored numbers fails here before it can reach
the walkthrough or the signal reports.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from efb import evaluate

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "sprints" / "E7" / "RESULTS.json"
GATE = ROOT / "sprints" / "E7" / "RG_SIGNAL.json"
LEDGER = ROOT / "docs" / "multiple_testing_ledger.md"

CRITERIA = ["F7.1", "F7.1b", "F7.1c", "F7.2", "F7.3", "F7.4"]


def _results() -> dict:
    if not RESULTS.exists():
        pytest.skip("E7 results not written yet")
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
    assert evaluate.e7_data_hash() == payload["data_hash"]


@pytest.mark.integration
def test_the_stored_criteria_equal_the_recomputed_ones() -> None:
    payload = _results()
    fresh = evaluate.evaluate_e7_criteria(**evaluate.compute_e7_from_artifacts())
    for name in CRITERIA:
        assert (
            fresh[name]["stored_numbers"] == payload["criteria"][name]["stored_numbers"]
        ), name
        assert fresh[name]["verdict"] == payload["criteria"][name]["verdict"], name


@pytest.mark.integration
def test_the_criterion_text_is_never_reworded() -> None:
    payload = _results()
    for name in CRITERIA:
        assert payload["criteria"][name]["criterion"] == evaluate.E7_CRITERIA_TEXT[name]


@pytest.mark.integration
def test_the_ledger_row_count_matches_the_runs() -> None:
    payload = _results()
    n_runs = payload["criteria"]["F7.3"]["stored_numbers"]["ledger_rows"]
    lines = [
        line
        for line in LEDGER.read_text().splitlines()
        if line.startswith("| ") and not line.startswith("| run_id")
    ]
    assert len(lines) == n_runs


@pytest.mark.integration
def test_the_rg_signal_gate_labels_every_signal() -> None:
    if not GATE.exists():
        pytest.skip("the RG-Signal gate has not run yet")
    gate = json.loads(GATE.read_text())
    for name, block in gate.items():
        assert block["verdict"] in ("PASS", "NULL"), name
        assert block["deciding_number"] is not None, name
        assert len(block["answers"]) == 7, name


@pytest.mark.integration
def test_f71b_records_the_empirical_shift_audit() -> None:
    payload = _results()
    f71b = payload["criteria"]["F7.1b"]["stored_numbers"]
    assert payload["criteria"]["F7.1b"]["verdict"] == "fail"
    assert f71b["post_earnings_drift"]["survives"] is True
    assert f71b["post_earnings_drift"]["ic_after_mean"] > (
        f71b["post_earnings_drift"]["ic_before_mean"]
    )
    assert f71b["short_term_reversal"]["flipped"] is True
    assert f71b["low_residual_volatility"]["killed"] is True
