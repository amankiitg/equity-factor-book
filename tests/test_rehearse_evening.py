"""The rehearsal pins the clock, sandboxes the store, and refuses to run blind."""

from __future__ import annotations

import os
from unittest.mock import patch

import pandas as pd
import pytest

from live import store
from scripts import rehearse_evening, run_live_daily


def test_pinned_now_is_the_close_s_evening() -> None:
    fixed = rehearse_evening.pinned_now("2026-10-29")
    assert fixed.date().isoformat() == "2026-10-29"
    assert fixed.hour == rehearse_evening.EVENING_HOUR_UTC
    assert fixed.minute == rehearse_evening.EVENING_MINUTE_UTC


def test_rehearse_refuses_when_the_clock_is_not_pinned() -> None:
    """A rehearsal that priced today's close proves nothing about the one asked for.

    The first attempt did exactly that: `staleness.check()` takes no target, so
    pinning only the runner produced an 11-05 subject for a 10-29 request.
    """
    ran = {"main": False}

    class Brake:
        def now(self, tz: object = None) -> object:
            raise AssertionError("the clock is pinned by the test")

    def fake_main() -> int:
        ran["main"] = True
        return 0

    with (
        patch.object(rehearse_evening, "_FixedClock", lambda fixed: Brake()),
        patch.object(store, "select", lambda table: pd.DataFrame()),
        patch.object(run_live_daily, "main", fake_main),
    ):
        with pytest.raises(rehearse_evening.RehearsalWrite):
            rehearse_evening.rehearse("2026-10-29")
    assert ran["main"] is False, "the evening must not start unless the clock is pinned"


def test_the_sandbox_switches_the_store_and_removes_the_dsn(monkeypatch) -> None:
    monkeypatch.delenv(store.LOCAL_MODE_ENV, raising=False)
    monkeypatch.setenv(store.URL_ENV, "postgresql://production.example/efb")
    one_row = pd.DataFrame(
        {"trade_date": [pd.Timestamp("2026-10-29")], "job": ["live_daily"]}
    )
    with (
        patch.object(store, "select", lambda table: one_row),
        rehearse_evening.RehearsalSandbox("2026-10-29"),
    ):
        assert store.store_mode() == store.LOCAL_MODE_VALUE
        assert os.environ.get(store.URL_ENV) is None, "the production DSN must be gone"
        assert "efb-rehearsal-store-2026-10-29-" in str(store.LOCAL_DIR)
    # and the environment is put back
    assert os.environ.get(store.URL_ENV) == "postgresql://production.example/efb"


def test_the_sandbox_refuses_when_a_table_cannot_be_copied() -> None:
    ran = {"copied": False}

    def no_read(table: str) -> pd.DataFrame:
        raise RuntimeError("the live table cannot be read")

    with patch.object(store, "select", no_read):
        with pytest.raises(rehearse_evening.RehearsalWrite):
            with rehearse_evening.RehearsalSandbox("2026-10-29"):
                ran["copied"] = True
    assert ran["copied"] is False


def test_the_sandbox_refuses_an_empty_copy() -> None:
    with patch.object(store, "select", lambda table: pd.DataFrame()):
        with pytest.raises(rehearse_evening.RehearsalWrite):
            with rehearse_evening.RehearsalSandbox("2026-10-29"):
                pass


def test_delivery_is_captured_not_sent() -> None:
    from live import notify

    rehearse_evening.DELIVERED.clear()
    with rehearse_evening.RehearsalDelivery():
        result = notify.send("subject", "body")
        assert result["status"] == notify.STATUS_SENT
        assert result["detail"].startswith("rehearsal")
    assert len(rehearse_evening.DELIVERED) == 1


def test_read_only_client_fails_closed_without_keys(monkeypatch) -> None:
    from live import alpaca

    monkeypatch.delenv("EFB_ALPACA_PAPER_API_KEY", raising=False)
    monkeypatch.delenv("EFB_ALPACA_PAPER_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="keys are required"):
        alpaca.read_only_client()


def test_a_date_column_is_written_so_the_run_can_append_to_it() -> None:
    """The copy must look like the database: a date as a timestamp, a number as a float.

    pyarrow stores a `date` object as date32, which pandas reads back as an integer
    width, and the run's own `run_date` then fails to append ("object of type str cannot
    be converted to int"). A `numeric` column arrives as `Decimal`, which pyarrow takes
    as text and then refuses floats. Both are normalised on the way in.
    """
    from datetime import date
    from decimal import Decimal

    frame = pd.DataFrame(
        {
            "trade_date": [date(2026, 10, 29), date(2026, 10, 30)],
            "weight": [Decimal("0.0123"), Decimal("-0.0456")],
            "manifest": [{"a": 1}, {"b": [1, 2]}],
        }
    )
    coerced = rehearse_evening.coerce_for_parquet(frame)
    assert pd.api.types.is_datetime64_any_dtype(coerced["trade_date"])
    assert coerced["weight"].dtype.kind == "f"
    assert isinstance(coerced["manifest"].iloc[0], str)
