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


def _filed_close_seed() -> pd.DataFrame:
    """One non-empty table that reads as an already-filed 2026-10-29 close."""
    return pd.DataFrame(
        {
            "run_date": pd.to_datetime(["2026-10-29"]),
            "job": ["live_daily"],
            "status": ["traded"],
        }
    )


def test_a_filed_close_reruns_instead_of_short_circuiting() -> None:
    """(a) already_ran is defeated: a filed close still runs the evening.

    The runner's idempotence guard answers True for a close that was already
    filed and returns before a line of the evening runs, which proves nothing.
    The rehearsal must re-run that close, so the guard has to answer False inside
    it - safe because the writes go to the sandbox, never the live store.
    """
    seen: dict[str, object] = {"main": False, "guard": None}

    def fake_main() -> int:
        seen["main"] = True
        seen["guard"] = run_live_daily.already_ran("live_daily", "2026-10-29")
        return 0

    # The unpatched guard really does answer True for this seed, so the test
    # proves the rehearsal defeats it rather than that the close never ran.
    with patch.object(store, "select", lambda table: _filed_close_seed()):
        assert run_live_daily.already_ran("live_daily", "2026-10-29") is True

    with (
        patch.object(store, "select", lambda table: _filed_close_seed()),
        patch.object(run_live_daily, "main", fake_main),
    ):
        code = rehearse_evening.rehearse("2026-10-29")

    assert seen["main"] is True, "the evening must run, not short-circuit"
    assert seen["guard"] is False, "already_ran must answer False inside the rehearsal"
    assert code == 0


def test_the_clock_pin_reaches_main() -> None:
    """(d) main() reads the close asked for, not today's.

    The first attempt pinned only the runner's clock; `staleness.check()` reads
    its own module clock, so rehearsing 10-29 produced an 11-05 subject. Both
    modules are pinned now, and the rehearsal refuses to start if either is not.
    """
    from datetime import UTC

    from live import staleness

    seen: dict[str, object] = {}

    def fake_main() -> int:
        seen["runner"] = run_live_daily.datetime.now(UTC)
        seen["staleness"] = staleness.datetime.now(UTC)
        return 0

    with (
        patch.object(store, "select", lambda table: _filed_close_seed()),
        patch.object(run_live_daily, "main", fake_main),
    ):
        rehearse_evening.rehearse("2026-10-29")

    fixed = rehearse_evening.pinned_now("2026-10-29")
    assert fixed.date().isoformat() == "2026-10-29"
    assert seen["runner"] == fixed
    assert seen["staleness"] == fixed


def test_legitimate_writes_file_into_the_sandbox_not_a_wall() -> None:
    """(b) The evening's own writes land in the copy, not a fail-closed wall.

    The first harness patched every store write to raise `RehearsalWrite`, so a
    real close died at its first legitimate write. The sandbox lets the run file
    for real into the copy, which is what makes "ok and filed" checkable - and
    the write the run makes is the one that appends to the copy, which is the
    fifth round-trip the local writer now casts for.
    """
    from pathlib import Path

    sandbox: dict[str, object] = {}

    def fake_main() -> int:
        sandbox["dir"] = store.LOCAL_DIR
        store.upsert(
            "cron_runs",
            [{"run_date": "2026-10-29", "job": "live_daily", "status": "traded"}],
        )
        return 0

    with (
        patch.object(store, "select", lambda table: _filed_close_seed()),
        patch.object(run_live_daily, "main", fake_main),
    ):
        assert rehearse_evening.rehearse("2026-10-29") == 0

    frame = pd.read_parquet(Path(sandbox["dir"]) / "cron_runs.parquet")
    assert frame["run_date"].astype(str).str.slice(0, 10).tolist() == [
        "2026-10-29",
    ]
    assert pd.api.types.is_datetime64_any_dtype(frame["run_date"])


def test_the_local_writer_casts_a_string_run_date_to_the_timestamp_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The cron row's own write: a string `run_date` appends to a timestamp column.

    `coerce_for_parquet` seeds `run_date` as a timestamp, and `record_run` appends
    the date as a string. `pd.concat` used to raise "object of type str cannot be
    converted to int"; the local writer now casts the incoming column to the
    file's schema first.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path)
    monkeypatch.setenv("EFB_STORE", "local")
    seed = pd.DataFrame(
        {
            "run_date": pd.to_datetime(["2026-10-28"]),
            "job": ["live_daily"],
            "status": ["traded"],
        }
    )
    seed.to_parquet(tmp_path / "cron_runs.parquet", index=False)

    store.upsert(
        "cron_runs",
        [{"run_date": "2026-10-29", "job": "live_daily", "status": "traded"}],
    )

    frame = store.select("cron_runs")
    assert pd.api.types.is_datetime64_any_dtype(frame["run_date"])
    assert frame["run_date"].astype(str).str.slice(0, 10).tolist() == [
        "2026-10-28",
        "2026-10-29",
    ]


def test_the_local_writer_casts_a_string_weight_to_the_float_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A numeric column's own write: a text weight appends to a float column.

    `coerce_for_parquet` seeds `weight` as a float and the run writes a number. A
    copy written before the normalisation holds text, and `pd.concat` used to
    raise "could not convert '7.917391' with type str". The local writer now
    casts the incoming column to the file's schema first.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path)
    monkeypatch.setenv("EFB_STORE", "local")
    seed = pd.DataFrame(
        {"trade_date": ["2026-10-28"], "ticker": ["AAA"], "weight": [0.01]}
    )
    seed.to_parquet(tmp_path / "positions.parquet", index=False)

    store.replace_by_date(
        "positions",
        "2026-10-29",
        [{"trade_date": "2026-10-29", "ticker": "AAA", "weight": "0.0123"}],
    )

    frame = store.select("positions")
    assert frame["ticker"].tolist() == ["AAA", "AAA"]
    assert frame["weight"].tolist() == pytest.approx([0.01, 0.0123])


# --- the pinned close reaches the pricing, and the traded guard is defeated -----

# A past close with no legs at the broker, and one that really traded (2026-11-04,
# the close the 2026-11-11 check found the rehearsal refusing outright).
PAST_CLOSE = "2026-10-29"
TRADED_CLOSE = "2026-11-04"


def _evening_harness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> dict[str, dict[str, object]]:
    """The stubs test_e11_positions drives `run_live_daily.main` with, offline."""
    from tests.test_e11_notify import _no_work, _patch_gate
    from tests.test_e11_positions import ACCOUNT_NUMBER, _FakeBroker

    from live import alpaca, extend, morning_job, reconcile, seed

    _no_work(monkeypatch)
    # The seed's own preflight reads the repository's data tree for files this
    # checkout does not carry; it is not what these tests are about.
    monkeypatch.setattr(seed, "preflight_inputs", lambda root: [])
    _patch_gate(monkeypatch, tmp_path)
    # The evening reads which account the keys reach; the fakes below report it.
    monkeypatch.setenv(alpaca.ACCOUNT_ID_ENV, ACCOUNT_NUMBER)
    monkeypatch.setattr(alpaca, "read_client", lambda: _FakeBroker([]))
    monkeypatch.setattr(
        morning_job,
        "run_morning",
        lambda *a, **k: {
            "orders": 0,
            "intended_notional": 0.0,
            "establishment": False,
        },
    )
    monkeypatch.setattr(reconcile, "daily_record", lambda *a, **k: {"dry_run": True})
    seen: dict[str, dict[str, object]] = {}

    def _prices(*args: object, **kwargs: object) -> int:
        seen["prices"] = kwargs
        return 0

    def _shares(*args: object, **kwargs: object) -> int:
        seen["shares"] = kwargs
        return 0

    monkeypatch.setattr(extend, "extend_prices", _prices)
    monkeypatch.setattr(extend, "extend_shares", _shares)
    return seen


def test_with_no_pin_the_evening_prices_its_own_clock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    """The production answer: no pin, so every pricing call takes its default.

    This is the negative control for the pin. It asserts the call the run makes
    when no rehearsal installed one - `end=None` and `as_of=None`, which is the
    clock-reading path the live book has always used - rather than assuming it.
    """
    from live import evening_job

    seen = _evening_harness(monkeypatch, tmp_path)

    def _build(*args: object, **kwargs: object) -> dict[str, object]:
        seen["proposal"] = kwargs
        return {"as_of": "2026-11-11"}

    monkeypatch.setattr(evening_job, "build_proposal", _build)
    monkeypatch.setattr(run_live_daily, "store_proposal", lambda *a, **k: None)

    assert run_live_daily.PINNED_CLOSE is None
    run_live_daily.main()

    assert seen["prices"]["end"] is None
    assert seen["shares"]["end"] is None
    assert seen["proposal"]["as_of"] is None


@pytest.mark.parametrize("close", [PAST_CLOSE, TRADED_CLOSE])
def test_the_pinned_close_is_the_one_priced_and_filed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object, close: str
) -> None:
    """One pinned "now": the extensions and the proposal are the requested close.

    The 2026-11-11 check found the subject right and the book dated today, because
    the clock was pinned and the three pricing calls were not. The proposal's
    `as_of` and the `trade_date` every row is keyed on are asserted here against
    the close that was asked for, for a past close and for one that traded.
    """
    from live import evening_job

    seen = _evening_harness(monkeypatch, tmp_path)

    def _build(*args: object, **kwargs: object) -> dict[str, object]:
        seen["proposal"] = kwargs
        return {"as_of": str(pd.Timestamp(kwargs["as_of"]).date())}

    def _store_proposal(as_of: str, *args: object, **kwargs: object) -> None:
        seen["trade_date"] = as_of
        return None

    monkeypatch.setattr(evening_job, "build_proposal", _build)
    monkeypatch.setattr(run_live_daily, "store_proposal", _store_proposal)
    monkeypatch.setattr(run_live_daily, "PINNED_CLOSE", close)

    run_live_daily.main()

    assert seen["prices"]["end"] == close
    assert seen["shares"]["end"] == close
    assert str(pd.Timestamp(seen["proposal"]["as_of"]).date()) == close
    assert seen["trade_date"] == close, "the proposal rows must carry the requested close"


@pytest.mark.parametrize("close", [PAST_CLOSE, TRADED_CLOSE])
def test_the_rehearsal_pins_the_close_and_reruns_a_traded_one(close: str) -> None:
    """A close with its legs at the broker is rehearsed, not reported traded.

    `traded_close` is real for 2026-11-04: the seed is what it answers from, which
    is asserted before the rehearsal runs as the negative control. Inside, the
    guard is defeated exactly as `already_ran` is, and the pin names the close.
    """
    seen: dict[str, object] = {}

    def _select(table: str) -> pd.DataFrame:
        if table == "orders":
            if close == TRADED_CLOSE:
                return pd.DataFrame(
                    {
                        "trade_date": [close],
                        "broker_order_id": ["oid-1"],
                        "status": ["filled"],
                        "reason_code": [""],
                    }
                )
            return pd.DataFrame(
                columns=["trade_date", "broker_order_id", "status", "reason_code"]
            )
        return _filed_close_seed()

    def fake_main() -> int:
        seen["pin"] = run_live_daily.pricing_close()
        seen["traded"] = run_live_daily.traded_close(close)
        return 0

    with patch.object(store, "select", _select):
        # The unpatched guard is real for the traded close (and silent for the
        # other), so the test proves the defeat rather than a close that never ran.
        assert (run_live_daily.traded_close(close) is not None) is (
            close == TRADED_CLOSE
        )
        with patch.object(run_live_daily, "main", fake_main):
            assert rehearse_evening.rehearse(close) == 0

    assert seen["pin"] == close
    assert seen["traded"] is None, "traded_close must be defeated inside the rehearsal"


def test_rehearse_refuses_when_the_pricing_close_is_not_pinned() -> None:
    """A run pinned only on the clock would price today under the close's name."""
    ran = {"main": False}

    def fake_main() -> int:
        ran["main"] = True
        return 0

    with (
        patch.object(store, "select", lambda table: _filed_close_seed()),
        patch.object(run_live_daily, "pricing_close", lambda: None),
        patch.object(run_live_daily, "main", fake_main),
    ):
        with pytest.raises(rehearse_evening.RehearsalWrite):
            rehearse_evening.rehearse(PAST_CLOSE)
    assert ran["main"] is False, "the evening must not start with the pricing unpinned"
