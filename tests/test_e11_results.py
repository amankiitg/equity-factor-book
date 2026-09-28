"""Sprint E11 Task 10: the pre-registered results file.

The window has not closed, so every verdict is pending and the stored
numbers are empty. What must already be exact is the criterion text,
copied verbatim from the roadmap, and the recorded clock, which is not
started: day 1 is the first session whose orders filled after the flip,
and registration refuses until the records agree on that date.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from live import clock as clock_module
from sprints.E11 import register_results

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "sprints" / "E11" / "RESULTS.json"
ROADMAP = ROOT / "docs" / "roadmap_v2.md"

CRITERIA = ["F11.1", "F11.2", "F11.3"]

AGREED = {"run": ["2026-09-30"], "proposal": ["2026-09-30"], "filled": []}


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


def test_the_clock_is_recorded_and_not_started() -> None:
    """The reset state, and the one the file stays in until a session fills."""
    payload = _results()
    recorded = payload["clock"]
    assert recorded["started"] is False
    assert recorded["day_1"] is None and recorded["end_date"] is None
    assert recorded["trading_days"] == 30
    assert recorded["run_condition"] == "open_ended"
    # The voided start stays on the record rather than being deleted.
    assert [entry["status"] for entry in recorded["history"]] == ["void"] * len(
        recorded["history"]
    )
    assert recorded["history"], "the voided start is not on the record"


def test_the_day_1_proposal_is_not_registered_yet() -> None:
    """A dry-run proposal from a frozen close is not a day-1 proposal."""
    payload = _results()
    assert payload["day_1_proposal"] is None
    assert payload["registered_at"] is None
    assert "not started" in payload["note"]


def test_registration_waits_for_a_session_that_traded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No live run, no day 1, and nothing written."""
    monkeypatch.setattr(register_results, "RESULTS", tmp_path / "RESULTS.json")
    monkeypatch.setattr(register_results, "CLOCK", tmp_path / "clock.json")
    with pytest.raises(clock_module.RegistrationRefused, match="no live run"):
        register_results.register(
            records={"run": [], "proposal": ["2026-09-30"], "filled": []}
        )
    assert not (tmp_path / "RESULTS.json").exists()
    assert not (tmp_path / "clock.json").exists()


def _manifest(as_of: str, signal: str = "idio_momentum") -> str:
    """One stored proposal manifest, with the fields the results file records."""
    fields = {field: 1 for field in register_results.PROPOSAL_FIELDS}
    return json.dumps(
        {
            **fields,
            "signal": signal,
            "as_of": as_of,
            "universe_source": f"raw/spy_holdings/spy_holdings_{as_of}.parquet",
        }
    )


def _store_with(*proposals: tuple[str, str]) -> pd.DataFrame:
    """A proposals table holding these (close, manifest) pairs."""
    return pd.DataFrame(
        {
            "trade_date": [close for close, _ in proposals],
            "manifest": [manifest for _, manifest in proposals],
        }
    )


def test_registration_records_the_proposal_priced_from_day_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The day-1 numbers come from the store, for that close, not from the newest
    file on disk, which before the flip is a rehearsal from a frozen close."""
    from live import store

    frame = _store_with(
        ("2026-09-30", _manifest("2026-09-30")),
        ("2026-10-01", _manifest("2026-10-01", "a later rehearsal")),
    )
    monkeypatch.setattr(store, "select", lambda table: frame)
    monkeypatch.setattr(register_results, "RESULTS", tmp_path / "RESULTS.json")
    monkeypatch.setattr(register_results, "CLOCK", tmp_path / "clock.json")

    payload = register_results.register(records=AGREED)

    assert payload["clock"]["day_1"] == "2026-09-30"
    assert payload["day_1_proposal"]["as_of"] == "2026-09-30"
    assert payload["day_1_proposal"]["signal"] == "idio_momentum"
    assert payload["registered_at"]
    # the clock on disk is started on the same day the results file names
    started = json.loads((tmp_path / "clock.json").read_text())
    assert started["started"] is True and started["day_1"] == "2026-09-30"


def test_registration_refuses_a_second_start_after_a_void(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A restart is registered the same way: the records decide the date."""
    from live import store

    frame = _store_with(
        ("2026-09-30", _manifest("2026-09-30")),
        ("2026-10-02", _manifest("2026-10-02")),
    )
    monkeypatch.setattr(store, "select", lambda table: frame)
    monkeypatch.setattr(register_results, "RESULTS", tmp_path / "RESULTS.json")
    monkeypatch.setattr(register_results, "CLOCK", tmp_path / "clock.json")
    disagreements = {
        "run": ["2026-10-02"],
        "proposal": ["2026-09-30"],
        "filled": [],
    }
    with pytest.raises(clock_module.RegistrationRefused, match="is not the first"):
        register_results.register(records=disagreements)
    assert not (tmp_path / "clock.json").exists()

    payload = register_results.register(
        records={"run": ["2026-10-02"], "proposal": ["2026-10-02"], "filled": []}
    )
    assert payload["clock"]["day_1"] == "2026-10-02"
