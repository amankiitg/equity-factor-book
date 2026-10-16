"""A close that already traded is not priced again; an unconfirmed leg still retries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from live import store
from scripts import run_live_daily
from tests.test_e11_notify import SESSION, _no_work, _patch_gate, _patch_success


def _orders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    store.upsert("orders", rows)


def test_a_close_with_all_its_legs_at_the_broker_is_already_traded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 2026-10-08's shape: every leg went out, none is unconfirmed, and the day's own
    # row says nothing about it. `already_ran` cannot see it; this can.
    _orders(
        tmp_path,
        monkeypatch,
        [
            {
                "trade_date": SESSION,
                "ticker": "AAA",
                "intended_notional": 1_000.0,
                "filled_notional": 1_000.0,
                "status": "FILLED",
                "reason": "",
                "reason_code": "",
                "client_order_id": "efb-1",
                "position_intent": "buy_to_open",
                "broker_order_id": "order-1",
            },
            {
                "trade_date": SESSION,
                "ticker": "BBB",
                "intended_notional": -1_000.0,
                "filled_notional": -1_000.0,
                "status": "FILLED",
                "reason": "",
                "reason_code": "",
                "client_order_id": "efb-2",
                "position_intent": "sell_to_open",
                "broker_order_id": "order-2",
            },
        ],
    )
    assert run_live_daily.traded_close(SESSION) == {
        "legs": 2,
        "sent": 2,
        "unconfirmed": 0,
    }


def test_a_close_with_a_leg_lost_at_the_broker_is_not_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A halted leg has something left to try, so the guard must not fire: refusing it
    # would leave the leg unsent forever, which is the retry's whole point.
    _orders(
        tmp_path,
        monkeypatch,
        [
            {
                "trade_date": SESSION,
                "ticker": "AAA",
                "intended_notional": 1_000.0,
                "filled_notional": 0.0,
                "status": "SKIPPED",
                "reason": "",
                "reason_code": "SKIPPED_AFTER_HALT",
                "client_order_id": "efb-1",
                "position_intent": "buy_to_open",
                "broker_order_id": "order-1",
            }
        ],
    )
    traded = run_live_daily.traded_close(SESSION)
    assert traded is not None
    assert traded["unconfirmed"] == 1


def test_a_close_whose_legs_never_left_is_not_a_traded_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The ordinary failure: the run died before anything was sent, so the retry is
    # the whole point and there is nothing to refuse.
    _orders(
        tmp_path,
        monkeypatch,
        [
            {
                "trade_date": SESSION,
                "ticker": "AAA",
                "intended_notional": 1_000.0,
                "filled_notional": 0.0,
                "status": "ACCEPTED",
                "reason": "",
                "reason_code": "",
                "client_order_id": "efb-1",
                "position_intent": "buy_to_open",
                "broker_order_id": "",
            }
        ],
    )
    assert run_live_daily.traded_close(SESSION) is None


def test_the_guard_runs_before_anything_is_priced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setattr(
        run_live_daily,
        "traded_close",
        lambda day: {"legs": 3, "sent": 3, "unconfirmed": 0},
    )
    refused: list[dict[str, int]] = []
    monkeypatch.setattr(
        run_live_daily, "traded_run", lambda day, counts: refused.append(counts) or 0
    )

    assert run_live_daily.main() == 0
    assert refused == [{"legs": 3, "sent": 3, "unconfirmed": 0}]


def test_a_partly_unconfirmed_close_is_repriced_as_it_always_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setattr(
        run_live_daily,
        "traded_close",
        lambda day: {"legs": 3, "sent": 3, "unconfirmed": 1},
    )

    def refuse_to_refuse(day: str, counts: dict[str, int]) -> int:
        raise AssertionError("the guard refused a close with a leg left to try")

    monkeypatch.setattr(run_live_daily, "traded_run", refuse_to_refuse)
    # The run goes on to the gate, which these helpers pass; the point of the test is
    # that it did not stop at the guard.
    assert run_live_daily.main() in (0, 1)


def test_traded_run_publishes_nothing_and_keeps_the_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FIX 2: a second start on a traded close must not replace the page.

    The document for that close is the first attempt's, and it is the one carrying the
    book, the bridge and the attribution. A snapshot built by a run that did nothing
    would have none of them, so the publish path is patched to fail the test if it is
    reached at all - the writer and the uploader both - and the two rows the guard
    needs are asserted instead.
    """
    from live import notify as notify_module
    from live import snapshot

    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setattr(
        snapshot,
        "write_snapshot",
        lambda **kwargs: pytest.fail("a traded run published a snapshot"),
    )
    monkeypatch.setattr(
        snapshot,
        "put_object",
        lambda *args, **kwargs: pytest.fail("a traded run wrote to R2"),
    )
    sent: list[dict[str, Any]] = []
    monkeypatch.setenv(notify_module.API_KEY_ENV, "re_" + "test-key-value")
    monkeypatch.setenv(notify_module.TO_ENV, "owner@example.com")
    monkeypatch.setattr(
        notify_module,
        "post",
        lambda url, payload, headers=None: sent.append(payload),
    )

    counts = {"legs": 3, "sent": 3, "unconfirmed": 0}
    assert run_live_daily.traded_run(SESSION, counts) == 0

    # The message: TRADED, no orders from this run, and the page untouched.
    assert str(sent[0]["subject"]).startswith("EFB TRADED 2026-09-22")
    body = str(sent[0]["text"])
    assert "Orders: none from this run" in body
    assert "The page was left as it was" in body
    assert "3 of 3 leg(s) at the broker" in body
    assert "none proposed" in str(sent[0]["subject"])

    # The two rows the guard and the reader need, both written.
    status = store.select("run_status")
    assert len(status) == 1
    row = status.iloc[0]
    assert row["status"] == "traded"
    assert str(row["target_close"])[:10] == SESSION
    assert "left as it was" in str(row["snapshot"])
    runs = store.select("cron_runs")
    assert len(runs) == 1
    assert str(runs.iloc[0]["status"]) == "traded"
    assert str(runs.iloc[0]["run_date"])[:10] == SESSION


def test_a_traded_second_start_keeps_the_first_attempts_story(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FIX 2, second half: the row is replaced by key, so the detail is carried over.

    2026-10-06 sent 192 orders and then died on a missing column, and the failure path
    filed that close's `run_status` row with the traceback. A second start on the same
    close finds the legs at the broker and writes its own row for the same
    `(target_close, job)` key, so without reading the first one the only record of why
    the evening is incomplete is gone and the day reads as an ordinary traded close.
    """
    from live import notify as notify_module
    from live import staleness

    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setenv(notify_module.API_KEY_ENV, "re_" + "test-key-value")
    monkeypatch.setenv(notify_module.TO_ENV, "owner@example.com")
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(
        notify_module, "post", lambda url, payload, headers=None: sent.append(payload)
    )
    failure = 'DatatypeMismatch: column "traded_notional" does not exist'
    store.upsert(
        staleness.TABLE,
        [
            {
                "target_close": SESSION,
                "job": staleness.JOB,
                "run_date": SESSION,
                "status": run_live_daily.ERROR_STATUS,
                "detail": failure,
            }
        ],
    )

    assert (
        run_live_daily.traded_run(SESSION, {"legs": 3, "sent": 3, "unconfirmed": 0})
        == 0
    )

    stored = store.select(staleness.TABLE)
    assert len(stored) == 1, "one row per close and job"
    row = stored.iloc[0]
    assert row["status"] == "traded"
    assert failure in str(row["detail"])
    assert "the day traded, so it was not re-priced" in str(row["detail"])
    assert failure in str(sent[0]["text"])


def test_a_traded_second_start_carries_nothing_over_from_an_ordinary_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a failed attempt's row is a story to keep."""
    from live import notify as notify_module
    from live import staleness

    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setenv(notify_module.API_KEY_ENV, "re_" + "test-key-value")
    monkeypatch.setenv(notify_module.TO_ENV, "owner@example.com")
    monkeypatch.setattr(notify_module, "post", lambda url, payload, headers=None: None)
    store.upsert(
        staleness.TABLE,
        [
            {
                "target_close": SESSION,
                "job": staleness.JOB,
                "run_date": SESSION,
                "status": "ok",
                "detail": "an ordinary evening, already reported",
            }
        ],
    )

    assert (
        run_live_daily.traded_run(SESSION, {"legs": 3, "sent": 3, "unconfirmed": 0})
        == 0
    )

    detail = str(store.select(staleness.TABLE).iloc[0]["detail"])
    assert "an ordinary evening" not in detail
