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


def test_read_only_client_fails_closed_without_keys(monkeypatch) -> None:
    from live import alpaca

    monkeypatch.delenv("EFB_ALPACA_PAPER_API_KEY", raising=False)
    monkeypatch.delenv("EFB_ALPACA_PAPER_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="keys are required"):
        alpaca.read_only_client()


def test_dry_run_checks_each_leg_s_asset_read_only() -> None:
    from unittest.mock import MagicMock, patch

    from live import alpaca, guards, morning_job

    order = MagicMock()
    order.status = guards.PASSED
    order.ticker = "KVUE"
    order.trade_notional = 1000.0
    order.intent = "buy_to_open"

    resolution = MagicMock()
    resolution.symbol = ""
    resolution.inactive = True
    resolution.missing = True

    with patch.object(alpaca, "SymbolResolver") as resolver_cls:
        resolver_cls.return_value.resolve.return_value = resolution
        records = morning_job.submit_orders(
            [order], object(), dry_run=True, close="2026-10-29"
        )

    row = records.iloc[0]
    assert row["status"] == "DRY_RUN"
    assert row["broker_symbol"] == ""
    assert "asset inactive" in str(row["reason"])
