"""Sprint E5 Task 6: F5.1 to F5.5 into RESULTS.json.

Every criterion carries a stored number and a verdict; F5.0 is absent because
its condition did not arise; the revisions block carries the data hash.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "sprints" / "E5" / "RESULTS.json"


@pytest.mark.integration
def test_every_criterion_is_stored_with_a_number_and_a_verdict() -> None:
    if not RESULTS.exists():
        pytest.skip("RESULTS.json has not been written yet")
    payload = json.loads(RESULTS.read_text())
    assert payload["sprint"] == "E5"
    for key in ("F5.1", "F5.2", "F5.3", "F5.4", "F5.5"):
        block = payload["criteria"][key]
        assert block["verdict"] in ("pass", "fail"), key
        assert block["stored_numbers"], key
        assert block["criterion"], key
        assert block["threshold"], key
    assert "F5.0" not in payload["criteria"], "F5.0 is conditional and was not earned"
    assert payload["data_hash"]
    assert isinstance(payload["revisions"], dict)


@pytest.mark.integration
def test_the_f52_number_names_the_sample_baseline() -> None:
    if not RESULTS.exists():
        pytest.skip("RESULTS.json has not been written yet")
    payload = json.loads(RESULTS.read_text())
    numbers = payload["criteria"]["F5.2"]["stored_numbers"]
    assert "sample_long_short_abs_bias_minus_1" in numbers
    assert "long_short_abs_bias_minus_1" in numbers


@pytest.mark.integration
def test_the_f54_champion_numbers_are_present() -> None:
    if not RESULTS.exists():
        pytest.skip("RESULTS.json has not been written yet")
    payload = json.loads(RESULTS.read_text())
    numbers = payload["criteria"]["F5.4"]["stored_numbers"]
    assert numbers["champion"] is not None
    assert isinstance(numbers["champion_stress_bias_vix_high"], float)
    assert isinstance(numbers["champion_recovery_trading_days_2020_q1"], float)


@pytest.mark.integration
def test_the_f55_xs_v2_against_xs_v1_is_stored_both_ways() -> None:
    if not RESULTS.exists():
        pytest.skip("RESULTS.json has not been written yet")
    payload = json.loads(RESULTS.read_text())
    numbers = payload["criteria"]["F5.5"]["stored_numbers"]
    assert set(numbers["bias_xs_v2"]) == set(numbers["bias_xs_v1"])
    assert numbers["ratio_xs_v2_over_xs_v1"]
