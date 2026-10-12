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
