"""Sprint E11: the continuous live clock, void and restart."""

from __future__ import annotations

from pathlib import Path

import pytest

from live import clock


def test_start_clock_records_day_1_and_the_end_date(tmp_path: Path) -> None:
    path = tmp_path / "clock.json"
    payload = clock.start_clock("2026-09-22", trading_days=30, path=path)
    assert payload["day_1"] == "2026-09-22"
    assert payload["trading_days"] == 30
    assert payload["started"] is True
    # 30 business days from 2026-09-22 inclusive lands on 2026-11-02
    assert payload["end_date"] == "2026-11-02"


def test_start_clock_records_the_open_ended_run_condition(tmp_path: Path) -> None:
    path = tmp_path / "clock.json"
    payload = clock.start_clock("2026-09-22", path=path)
    assert payload["run_condition"] == "open_ended"
    assert payload["reporting_window_days"] == 30
    # the window end is a reporting slice, not the life of the loop
    assert payload["end_date"] == "2026-11-02"
    assert payload["day_1"] == "2026-09-22"


def test_run_condition_is_open_ended() -> None:
    condition = clock.run_condition()
    assert condition["run_condition"] == "open_ended"
    assert "reporting window" in condition["reason"]
    assert condition["reporting_window_days"] == 30


def test_void_start_records_the_reason_and_leaves_the_clock_stopped(
    tmp_path: Path,
) -> None:
    path = tmp_path / "clock.json"
    clock.start_clock("2026-09-22", path=path)
    payload = clock.void_start("2026-09-22", "static days on a frozen close", path=path)
    assert payload["started"] is False
    assert payload["day_1"] is None
    assert len(payload["history"]) == 1
    entry = payload["history"][0]
    assert entry["status"] == "void"
    assert entry["day_1"] == "2026-09-22"
    assert entry["reason"] == "static days on a frozen close"


def test_restart_after_a_void_keeps_both_starts_on_the_record(tmp_path: Path) -> None:
    path = tmp_path / "clock.json"
    clock.start_clock("2026-09-22", path=path)
    clock.void_start("2026-09-22", "static days", path=path)
    payload = clock.start_clock("2026-09-23", path=path)
    assert payload["started"] is True
    assert payload["day_1"] == "2026-09-23"
    assert [entry["status"] for entry in payload["history"]] == ["void"]
    assert payload["history"][0]["day_1"] == "2026-09-22"


def test_load_clock_fails_before_it_has_started(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no clock"):
        clock.load_clock(tmp_path / "clock.json")
