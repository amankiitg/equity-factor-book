"""Sprint E11: the daily cron script's run bookkeeping.

The loop is idempotent through the cron_runs table, so the first-ever run
(empty table) must still record without raising, and a re-run for the same
date must replace the row rather than duplicate it.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest

from live import staleness, store
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


def test_the_window_override_opens_only_on_the_exact_word() -> None:
    """The opposite default from the dry-run flag, and for the same reason.

    A dry-run flag left unset costs a rehearsal. A window left open costs an
    order at an hour the broker's DAY semantics do not hold for.
    """
    assert run_live_daily.resolve_force_hour("true") is True
    for value in (None, "", "TRUE ", " yes", "1", "false"):
        assert run_live_daily.resolve_force_hour(value) is False, value


def test_the_run_refuses_outside_the_window_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An evening at the wrong hour is not the evening.

    The refusal is before the day's bookkeeping, so the day stays un-run and the
    in-window cron later that day still has its evening. Writing a row here would
    either mark the day done or need a status the page then has to explain.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(run_live_daily, "datetime", _clock("2026-09-22T09:00:00+00:00"))
    monkeypatch.setattr(staleness, "is_session", lambda day: True)
    monkeypatch.delenv(run_live_daily.FORCE_HOUR_ENV, raising=False)

    assert run_live_daily.main() == 1

    assert store.select("cron_runs").empty
    assert store.select("run_status").empty


def _clock(instant: str):
    """A `datetime` pinned to one instant, for the run's own window check."""

    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206 - the stdlib signature
            return datetime.fromisoformat(instant)

    return _Fixed


def test_a_failed_row_still_allows_a_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a completed status marks the day done.

    A row left by a failed or incomplete attempt is exactly what the next tick has
    to retry. Counting any row as "already ran" would file a day nothing was
    produced on as finished; the earlier `already_ran` did exactly that.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path)
    for status in ("failed", "error", "incomplete", "stale_stopped"):
        store.upsert(
            "cron_runs",
            [
                {
                    "run_date": "2026-09-23",
                    "job": "live_daily",
                    "status": status,
                    "detail": "boom",
                    "started_at": "",
                    "finished_at": "",
                }
            ],
        )
        assert run_live_daily.already_ran("live_daily", "2026-09-23") is False, status

    store.upsert(
        "cron_runs",
        [
            {
                "run_date": "2026-09-23",
                "job": "live_daily",
                "status": "ok",
                "detail": "",
                "started_at": "",
                "finished_at": "",
            }
        ],
    )
    assert run_live_daily.already_ran("live_daily", "2026-09-23") is True


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
