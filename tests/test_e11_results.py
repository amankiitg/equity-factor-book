"""Sprint E11 Task 10: the pre-registered results file.

The window has not closed, so every verdict is pending and the stored
numbers are empty. What must already be exact is the criterion text,
copied verbatim from the roadmap, and the recorded clock.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "sprints" / "E11" / "RESULTS.json"
ROADMAP = ROOT / "docs" / "roadmap_v2.md"

CRITERIA = ["F11.1", "F11.2", "F11.3"]


def _results() -> dict:
    if not RESULTS.exists():
        pytest.skip("E11 results not registered yet")
    return json.loads(RESULTS.read_text())


def test_every_criterion_is_registered_pending() -> None:
    payload = _results()
    assert set(CRITERIA) <= set(payload["criteria"])
    for name in CRITERIA:
        assert payload["criteria"][name]["verdict"] == "pending"
        assert payload["criteria"][name]["stored_numbers"] == []


def test_the_criteria_are_byte_identical_to_the_roadmap() -> None:
    payload = _results()
    roadmap_lines = ROADMAP.read_text().splitlines()
    for name in CRITERIA:
        for index, line in enumerate(roadmap_lines):
            if line.strip() == name:
                expected = roadmap_lines[index + 1].strip()
                assert payload["criteria"][name]["criterion"] == expected, name
                break
        else:
            pytest.fail(f"{name} not found in the roadmap")


def test_the_clock_is_recorded() -> None:
    payload = _results()
    clock = payload["clock"]
    assert clock["day_1"]
    assert clock["end_date"]
    assert clock["trading_days"] == 30
    assert clock["started"] is True


def test_the_day_1_proposal_is_recorded_with_the_null_book_numbers() -> None:
    payload = _results()
    proposal = payload["day_1_proposal"]
    assert proposal["signal"] == "idio_momentum"
    assert proposal["n_names"] >= 490
    assert proposal["idio_share_after_fmp"] == pytest.approx(1.0, abs=1e-9)
    assert proposal["gross"] == pytest.approx(1.0)
