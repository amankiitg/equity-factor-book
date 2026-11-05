"""The evening rehearsal pins the clock and fails closed on any store write."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from scripts import rehearse_evening, run_live_daily


def test_pinned_now_is_the_close_s_evening() -> None:
    fixed = rehearse_evening.pinned_now("2026-10-29")
    assert fixed.date().isoformat() == "2026-10-29"
    assert fixed.hour == rehearse_evening.EVENING_HOUR_UTC
    assert fixed.minute == rehearse_evening.EVENING_MINUTE_UTC


def test_store_writes_fail_closed_and_are_restored() -> None:
    from live import store

    with rehearse_evening._block_store_writes():
        with pytest.raises(rehearse_evening.RehearsalWrite):
            store.upsert("cron_runs", [])
        with pytest.raises(rehearse_evening.RehearsalWrite):
            store.replace_by_date("positions", "2026-10-29", [])
    # Restored after the context: the real callable is back.
    assert callable(store.upsert)


def test_rehearse_pins_the_clock_sets_flags_and_runs_main() -> None:
    seen: dict[str, str] = {}

    def fake_main() -> int:
        seen["run_date"] = run_live_daily.datetime.now().date().isoformat()
        seen["dry_run"] = os.environ.get("EFB_DRY_RUN", "")
        seen["force_hour"] = os.environ.get("EFB_FORCE_HOUR", "")
        return 0

    with patch.object(run_live_daily, "main", fake_main):
        code = rehearse_evening.rehearse("2026-10-29")

    assert code == 0
    assert seen["run_date"] == "2026-10-29"
    assert seen["dry_run"] == "true"
    assert seen["force_hour"] == "true"


def test_rehearse_blocks_writes_during_the_run() -> None:
    from live import store

    seen: dict[str, bool] = {}

    def fake_main() -> int:
        try:
            store.upsert("cron_runs", [])
        except rehearse_evening.RehearsalWrite:
            seen["write_raised"] = True
        return 0

    with patch.object(run_live_daily, "main", fake_main):
        rehearse_evening.rehearse("2026-10-29")

    assert seen["write_raised"] is True
