"""Sprint E11, Task 9: the thirty-trading-day clock is pre-registered."""

from __future__ import annotations

from pathlib import Path

import pytest

from live import clock


def test_start_clock_records_day_1_and_the_end_date(tmp_path: Path) -> None:
    path = tmp_path / "clock.json"
    payload = clock.start_clock("2026-09-22", trading_days=30, path=path)
    assert payload["day_1"] == "2026-09-22"
    assert payload["trading_days"] == 30
    # 30 business days from 2026-09-22 lands on the last business day of the window
    assert payload["end_date"] == "2026-11-02"


def test_clock_is_never_restarted_with_a_different_day(tmp_path: Path) -> None:
    path = tmp_path / "clock.json"
    clock.start_clock("2026-09-22", path=path)
    with pytest.raises(ValueError, match="never restarted"):
        clock.start_clock("2026-09-23", path=path)
    # the same day is idempotent and keeps the original record
    same = clock.start_clock("2026-09-22", path=path)
    assert same["day_1"] == "2026-09-22"


def test_load_clock_fails_before_it_has_started(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no clock"):
        clock.load_clock(tmp_path / "clock.json")
