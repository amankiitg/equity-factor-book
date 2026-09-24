"""Sprint E11: the daily cron script's run bookkeeping.

The loop is idempotent through the cron_runs table, so the first-ever run
(empty table) must still record without raising, and a re-run for the same
date must replace the row rather than duplicate it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from live import store
from scripts import run_live_daily

ROOT = Path(__file__).resolve().parents[1]


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


def test_the_cron_script_makes_live_importable_from_any_cwd() -> None:
    """Render runs `python scripts/run_live_daily.py`, which puts scripts/ on
    sys.path, not the repo root; the module must add the root itself so the
    `live` package is reachable."""
    path = ROOT / "scripts" / "run_live_daily.py"
    spec = importlib.util.spec_from_file_location("_run_live_daily_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # executing the module body runs the sys.path fix without running main
    spec.loader.exec_module(module)
    from live import evening_job  # noqa: PLC0415 - imported after the fix

    assert evening_job.DATA_ROOT.name == "data"
