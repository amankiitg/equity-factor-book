"""Sprint E11, Task 4: Option A governance and append-only state.

The loop proposes and the rules decide, nothing discretionary. The four
gate branches are pinned, and the state store is append-only and
idempotent on the trade date.
"""

from __future__ import annotations

from pathlib import Path

from live import morning_job, state


def test_gate_executes_on_approve() -> None:
    assert morning_job.should_execute("approve", auto_approve=False) is True


def test_gate_skips_on_reject_even_with_auto_approve() -> None:
    assert morning_job.should_execute("reject", auto_approve=True) is False


def test_gate_executes_with_auto_approve_when_not_rejected() -> None:
    assert morning_job.should_execute(None, auto_approve=True) is True
    assert morning_job.should_execute("proposed", auto_approve=True) is True


def test_gate_skips_without_approve_when_auto_approve_off() -> None:
    assert morning_job.should_execute(None, auto_approve=False) is False
    assert morning_job.should_execute("proposed", auto_approve=False) is False


def test_decision_upsert_is_idempotent(tmp_path: Path) -> None:
    state.write_decision("2026-09-22", "proposed", state_dir=tmp_path)
    state.write_decision("2026-09-22", "approve", state_dir=tmp_path)
    frame = state._load_frame(tmp_path / "decisions.parquet", state.DECISION_COLUMNS)
    assert len(frame) == 1
    assert state.fetch_decision("2026-09-22", state_dir=tmp_path) == "approve"


def test_positions_upsert_is_idempotent(tmp_path: Path) -> None:
    day = [
        {
            "trade_date": "2026-09-22",
            "ticker": "AAA",
            "signed_notional": 100.0,
            "weight": 0.01,
            "side": "long",
        }
    ]
    state.write_positions("2026-09-22", day, state_dir=tmp_path)
    state.write_positions("2026-09-22", day, state_dir=tmp_path)
    stored = state.fetch_positions("2026-09-22", state_dir=tmp_path)
    assert len(stored) == 1
    assert stored["ticker"].iloc[0] == "AAA"


def test_auto_approve_defaults_off_and_round_trips(tmp_path: Path) -> None:
    assert state.get_auto_approve(state_dir=tmp_path) is False
    state.set_auto_approve(True, state_dir=tmp_path)
    assert state.get_auto_approve(state_dir=tmp_path) is True
