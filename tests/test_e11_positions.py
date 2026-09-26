"""Sprint E11 pre-flip, item 6: read the account before sizing, report the difference.

The traded leg of every order is the difference between the target and the book
the account actually holds. Measuring it against the store's own position row
instead meant the loop was reading back its own intentions: in dry run every leg
was computed from a book that was never sent, so on the evening of the flip every
leg would have been wrong in the same direction, silently.

So the account is read every evening, before the orders are built, and the read
happens in dry run too, because reading is free and read-only and the question has
a real answer before the flip. Where the two books disagree the disagreement is
reported, not resolved: `missing_at_broker` is the dangerous direction, the loop
believing it holds something the account does not.
"""

from __future__ import annotations

from typing import Any

import pytest

from live import alpaca, notify, positions, store


class _FakeBroker:
    def __init__(self, holdings: list[tuple[str, float]]) -> None:
        self.holdings = holdings

    def get_account(self) -> Any:
        class _Account:
            id = "paper-account"

        return _Account()

    def get_all_positions(self) -> list[Any]:
        class _Position:
            def __init__(self, symbol: str, value: float, side: str) -> None:
                self.symbol = symbol
                self.market_value = str(abs(value))
                self.side = side

        return [
            _Position(symbol, value, "long" if value >= 0 else "short")
            for symbol, value in self.holdings
        ]


def test_an_account_that_could_not_be_read_is_not_an_empty_account() -> None:
    """The two are different answers and the note says which one it has."""
    monkeypatch_env = None
    result = positions.compare(None, {"AAA": 100.0})
    assert result["matches"] is None
    assert result["n_broker"] is None
    assert result["n_store"] == 1
    note = positions.describe({**result, "broker_source": "not read: no keys"})
    assert "not read" in note
    assert "no comparison was made" in note
    assert monkeypatch_env is None


def test_the_two_books_are_compared_name_by_name() -> None:
    broker = {"AAA": 100.0, "BBB": -50.0}
    believed = {"AAA": 100.0, "CCC": 25.0}
    result = positions.compare(broker, believed)
    assert result["matches"] is False
    assert result["missing_at_broker"] == ["CCC"]
    assert result["missing_in_store"] == ["BBB"]
    assert result["drift"] == {}
    assert result["max_abs_drift"] == 0.0

    # A difference inside one dollar is arithmetic noise, not a mismatch.
    assert positions.compare({"AAA": 100.0}, {"AAA": 100.4})["matches"] is True
    drifted = positions.compare({"AAA": 900.0}, {"AAA": 100.0})
    assert drifted["matches"] is False
    assert drifted["max_abs_drift"] == 800.0
    assert drifted["drift"] == {"AAA": 800.0}


def test_a_read_account_is_the_book_the_orders_are_measured_against(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    store.upsert(
        "positions",
        [{"trade_date": "2026-09-25", "ticker": "AAA", "signed_notional": 500.0}],
    )
    broker = _FakeBroker([("AAA", 500.0)])
    monkeypatch.setattr(alpaca, "read_client", lambda: broker)

    result = positions.check(dry_run=True)

    assert result["n_broker"] == 1 and result["n_store"] == 1
    assert result["matches"] is True
    assert result["held"] == {"AAA": 500.0}
    assert result["source"] == positions.BROKER_SOURCE
    assert "matches the store" in result["note"]


def test_a_flat_account_against_a_held_store_is_the_dry_run_state(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    store.upsert(
        "positions",
        [
            {"trade_date": "2026-09-25", "ticker": "AAA", "signed_notional": 500.0},
            {"trade_date": "2026-09-25", "ticker": "BBB", "signed_notional": -250.0},
        ],
    )
    monkeypatch.setattr(alpaca, "read_client", lambda: _FakeBroker([]))

    result = positions.check(dry_run=True)
    assert result["matches"] is False
    assert result["held"] == {}, "an empty account is the book to trade from"
    assert result["missing_at_broker"] == ["AAA", "BBB"]
    assert "2 name(s) the store holds and the account does not" in result["note"]
    assert "Expected in dry run" in result["note"]

    # The same state on a live evening is a real warning, and the note does not
    # pretend otherwise.
    live_note = positions.describe(result, dry_run=False)
    assert "Expected in dry run" not in live_note


def test_the_message_carries_the_comparison() -> None:
    check = {
        "matches": False,
        "n_broker": 0,
        "n_store": 2,
        "source": "alpaca paper account",
        "note": "mismatch: the account holds 0 name(s) and the store 2",
    }
    message = notify.compose(
        status="ok",
        target_close="2026-09-25",
        orders=2,
        gross=750.0,
        dry_run=True,
        positions_check=check,
        store="postgres/efb",
    )
    assert (
        "Positions: mismatch: the account holds 0 name(s) and the store 2." in message
    )
    # And a run with no check at all says nothing rather than implying a match.
    without = notify.compose(
        status="ok", target_close="2026-09-25", orders=2, dry_run=True
    )
    assert "Positions:" not in without


def test_the_first_live_day_is_establishment_even_with_a_dry_run_store(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store says 150 names, the account says none, and the day establishes.

    This is the state the flip starts from and the case a store-based answer gets
    wrong: every dry-run evening has written a 150-name intention into the store
    while the paper account has never held anything. Asking the store would call
    the first live evening a rebalance, measure every traded leg against a book
    that does not exist, and trade nothing at all.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    store.upsert(
        "positions",
        [
            {
                "trade_date": "2026-09-25",
                "ticker": f"T{index:03d}",
                "signed_notional": 1000.0,
                "kind": "intention",
            }
            for index in range(150)
        ],
    )
    monkeypatch.setattr(alpaca, "read_client", lambda: _FakeBroker([]))

    result = positions.check(dry_run=False)

    assert result["account_read"] is True
    assert result["n_store"] == 150 and result["n_broker"] == 0
    assert result["establishment"] is True
    # The negative control: the store is emphatically not empty, so the store
    # cannot be the thing that answers "is there a book".
    assert bool(result["store"]) is True
    assert result["held"] == {}, "the intentions were measured as holdings"


def test_an_unreadable_account_is_not_an_empty_one(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case the store-based answer got wrong.

    `held` falls back to the store's book when the account cannot be read, so
    asking the run's own book "is it empty" answers "yes" whenever the store is,
    and the evening would be treated as an establishment day on the strength of a
    missing credential: the whole book bought against an account whose state is
    unknown. The store's emptiness is not evidence about the account.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(alpaca, "read_client", lambda: None)

    result = positions.check(dry_run=False)

    assert result["account_read"] is False and result["broker"] is None
    assert result["establishment"] is False
    # The negative control, at the level of the old expression: the book the run
    # holds is the empty store, so `not held` would have said True.
    assert result["held"] == {} and not result["held"]


def test_the_run_passes_the_accounts_answer_to_the_morning_job(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wiring: establishment is derived from the account, not from the store.

    The store holds 150 dry-run intentions and the account holds none, which is
    exactly the state the first live evening starts from: the morning job must be
    told to establish, and must be handed the account's (empty) book rather than
    the store's 150 names to trade the difference from.
    """
    from live import morning_job
    from tests.test_e11_notify import _no_work, _patch_gate

    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "live.evening_job.build_proposal", lambda *a, **k: {"as_of": "2026-09-22"}
    )
    monkeypatch.setattr("scripts.run_live_daily.store_proposal", lambda *a, **k: None)
    store.upsert(
        "positions",
        [
            {
                "trade_date": "2026-09-25",
                "ticker": f"T{index:03d}",
                "signed_notional": 1000.0,
                "kind": "intention",
            }
            for index in range(150)
        ],
    )
    monkeypatch.setattr(alpaca, "read_client", lambda: _FakeBroker([]))
    seen: dict[str, Any] = {}

    def _capture(as_of: str, **kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        seen["as_of"] = as_of
        return {"orders": 0, "intended_notional": 0.0, "establishment": True}

    monkeypatch.setattr(morning_job, "run_morning", _capture)
    monkeypatch.setattr("scripts.run_live_daily.store_orders", lambda *a, **k: None)
    monkeypatch.setattr(
        "scripts.run_live_daily.store_reconciliation", lambda *a, **k: None
    )
    from live import reconcile

    monkeypatch.setattr(reconcile, "daily_record", lambda *a, **k: {"dry_run": True})

    from scripts import run_live_daily

    run_live_daily.main()

    assert seen["establishment"] is True, "the store's 150 names decided the day"
    assert seen["positions"] == {}, "the orders were not measured from the account"


def test_the_run_refuses_to_establish_when_the_account_cannot_be_read(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An unreadable account is not an establishment day, and the run says so.

    Nothing is written to the store here, so the book the run holds is empty and
    the old expression (`not held`) called this an establishment day: a missing
    key would have bought the whole book against an account nobody had looked at.
    """
    from live import morning_job
    from tests.test_e11_notify import _no_work, _patch_gate

    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "live.evening_job.build_proposal", lambda *a, **k: {"as_of": "2026-09-22"}
    )
    monkeypatch.setattr("scripts.run_live_daily.store_proposal", lambda *a, **k: None)
    monkeypatch.setattr(alpaca, "read_client", lambda: None)
    seen: dict[str, Any] = {}

    def _capture(as_of: str, **kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        seen["as_of"] = as_of
        return {"orders": 0, "intended_notional": 0.0, "establishment": False}

    monkeypatch.setattr(morning_job, "run_morning", _capture)
    monkeypatch.setattr("scripts.run_live_daily.store_orders", lambda *a, **k: None)
    monkeypatch.setattr(
        "scripts.run_live_daily.store_reconciliation", lambda *a, **k: None
    )
    from live import reconcile

    monkeypatch.setattr(reconcile, "daily_record", lambda *a, **k: {"dry_run": True})

    from scripts import run_live_daily

    with caplog.at_level("WARNING"):
        run_live_daily.main()

    assert seen["establishment"] is False
    assert "not an establishment day" in caplog.text


def test_a_dry_run_position_row_is_labelled_an_intention() -> None:
    """The store must say that a dry-run book was never a book.

    Every evening before the flip writes 150 rows into `efb.positions` that no
    order ever created. They are the loop's intention, and the row says so, so
    E12's attribution cannot attribute P&L to a book that never existed.
    """
    import pandas as pd

    from live import morning_job

    records = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "intended_notional": [1000.0, -500.0],
        }
    )
    proposal = pd.DataFrame({"ticker": ["AAA", "BBB"], "weight": [0.01, -0.005]})

    dry = morning_job._positions_from_records(records, proposal, dry_run=True)
    live_rows = morning_job._positions_from_records(records, proposal, dry_run=False)

    assert set(dry["kind"]) == {"intention"}
    assert set(live_rows["kind"]) == {"holding"}


def test_the_intention_label_survives_the_round_trip(tmp_path: Any) -> None:
    """A label the state writer drops is not a label."""
    from live import state

    rows = [
        {
            "trade_date": "2026-09-25",
            "ticker": "AAA",
            "signed_notional": 1000.0,
            "weight": 0.01,
            "side": "long",
            "kind": "intention",
        }
    ]
    state.write_positions("2026-09-25", rows, state_dir=tmp_path)

    read = state.fetch_positions("2026-09-25", state_dir=tmp_path)

    assert list(read["kind"]) == ["intention"]


def test_the_row_records_the_check_without_the_name_maps() -> None:
    from live import staleness

    check = {
        **positions.compare({"AAA": 1.0}, {"BBB": 1.0}),
        "source": "alpaca paper account",
        "broker": {"AAA": 1.0},
        "store": {"BBB": 1.0},
        "held": {"AAA": 1.0},
        "note": "mismatch",
    }
    row = staleness.run_status_row(
        {"target_close": "2026-09-25", "job": "live_daily", "status": "ok"},
        run_date="2026-09-25",
        positions_check=check,
    )
    assert '"missing_at_broker": ["BBB"]' in row["positions_check"].replace("'", '"')
    # The maps themselves are dropped: the summary is the evidence and the row is
    # read on every page load.
    assert '"held"' not in row["positions_check"]
    assert '"broker": {' not in row["positions_check"]
