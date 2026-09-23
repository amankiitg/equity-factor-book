"""Sprint E11: the daily cron script's run bookkeeping.

The loop is idempotent through the cron_runs table, so the first-ever run
(empty table) must still record without raising, and a re-run for the same
date must replace the row rather than duplicate it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from live import store
from scripts import run_live_daily


def test_record_run_handles_an_empty_cron_runs_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path)
    run_live_daily.record_run("live_daily", "2026-09-23", "ok")
    frame = store.select("cron_runs")
    assert len(frame) == 1
    assert frame.iloc[0]["run_date"] == "2026-09-23"
    assert frame.iloc[0]["job"] == "live_daily"
    assert frame.iloc[0]["status"] == "ok"


def test_record_run_replaces_the_same_date_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path)
    run_live_daily.record_run("live_daily", "2026-09-23", "ok")
    run_live_daily.record_run("live_daily", "2026-09-23", "failed", "boom")
    frame = store.select("cron_runs")
    assert len(frame) == 1
    assert frame.iloc[0]["status"] == "failed"
    assert frame.iloc[0]["detail"] == "boom"
