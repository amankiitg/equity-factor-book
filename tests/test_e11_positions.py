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

from live import alpaca, evening_job, notify, positions, store


class _FakeBroker:
    def __init__(
        self,
        holdings: list[tuple[str, float]],
        equity: str | None = "1234567.89",
        cash: str | None = "23456.78",
    ) -> None:
        self.holdings = holdings
        self.equity = equity
        self.cash = cash

    def get_account(self) -> Any:
        broker = self

        class _Account:
            id = "paper-account"
            equity = broker.equity
            cash = broker.cash

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


def test_the_run_is_sized_from_the_accounts_own_equity(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The NAV is the account's own equity, read with the positions.

    A book sized from a constant is the same size on an account that has grown and
    on one that has halved, and the guards are fractions of NAV, so the number the
    book is sized from and the number the guards divide by have to be the same
    account's. The read reports the equity and the cash beside the book, and says
    where the number came from rather than leaving it to be assumed.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(alpaca, "read_client", lambda: _FakeBroker([("AAA", 500.0)]))

    result = positions.check(dry_run=True)

    assert result["equity"] == pytest.approx(1_234_567.89)
    assert result["cash"] == pytest.approx(23_456.78)
    assert result["nav"] == pytest.approx(1_234_567.89)
    assert result["nav"] != evening_job.PAPER_NAV
    assert "the account's own equity" in result["nav_source"]


def test_an_account_with_no_equity_states_the_default_it_used(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dry run with no equity read sizes from the paper default and says so.

    The default is a fallback, not a measurement: the sentence names it and says
    what it means on a live evening, so a book priced from a constant is visible
    in the row rather than indistinguishable from one priced from the account.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(
        alpaca,
        "read_client",
        lambda: _FakeBroker([("AAA", 500.0)], equity=None),
    )

    result = positions.check(dry_run=True)

    assert result["equity"] is None
    assert result["nav"] == pytest.approx(evening_job.PAPER_NAV)
    assert "the paper default" in result["nav_source"]
    assert "stops the run" in result["nav_source"]


def test_an_account_with_no_equity_stops_a_live_run(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live evening that cannot size its book must not build one.

    The same rule as an unreadable positions read: the guards are fractions of
    NAV, so an evening that fell back to a constant would guard the wrong book
    with the wrong denominator and trade it.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(
        alpaca,
        "read_client",
        lambda: _FakeBroker([("AAA", 500.0)], equity=None),
    )

    with pytest.raises(RuntimeError, match="equity could not be read"):
        positions.check(dry_run=False)


@pytest.mark.parametrize("equity", ["0.00", "-5.00"])
def test_an_equity_of_zero_or_below_raises_rather_than_sizing_from_the_default(
    equity: str, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reported equity of nothing is an answer, not a failed read.

    An account that says it is worth zero or less is telling the run something
    true: there is nothing to size a book from. Falling back to the paper default
    on it would buy a million dollars' worth of book against an account holding
    nothing, and the guards - all of them fractions of NAV - would then be
    guarding the wrong book. The fallback is for a read that never happened, which
    the negative control at the end pins.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(
        alpaca, "read_client", lambda: _FakeBroker([("AAA", 500.0)], equity=equity)
    )

    with pytest.raises(RuntimeError, match="reports an equity of"):
        positions.check(dry_run=True)

    # the negative control: no read at all is the case the default is for
    monkeypatch.setattr(alpaca, "read_client", lambda: None)
    unresolved = positions.check(dry_run=True)
    assert unresolved["equity"] is None
    assert unresolved["nav"] == pytest.approx(evening_job.PAPER_NAV)


def test_the_comparison_is_against_the_last_book_before_tonight(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not against tonight's target, which no order has been sent for yet.

    The store holds the book the loop meant to hold tonight, written by the
    proposal step before any order leaves the process. Comparing the account
    against it reports every one of tonight's names as missing at the broker on
    the evening the run is about to buy them, which is what the first live
    evening would have said about all 150 of them.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    store.upsert(
        "positions",
        [
            {"trade_date": "2026-09-21", "ticker": "AAA", "signed_notional": 500.0},
            {"trade_date": "2026-09-22", "ticker": "BBB", "signed_notional": 700.0},
            {"trade_date": "2026-09-22", "ticker": "CCC", "signed_notional": 300.0},
        ],
    )
    monkeypatch.setattr(alpaca, "read_client", lambda: _FakeBroker([("AAA", 500.0)]))

    result = positions.check(dry_run=True, before="2026-09-22")

    assert result["n_store"] == 1
    assert result["matches"] is True
    assert result["store_source"] == "the 2026-09-21 position row"
    # The negative control, on the same store and the same account: without the
    # date the latest row is tonight's target, and the account "misses" a book
    # that was never sent.
    unfiltered = positions.check(dry_run=True)
    assert unfiltered["n_store"] == 2
    assert unfiltered["matches"] is False
    assert unfiltered["missing_at_broker"] == ["BBB", "CCC"]
    assert unfiltered["store_source"] == "the 2026-09-22 position row"


def test_a_store_with_nothing_before_tonight_says_so(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first evening has one row, its own, and the sentence says which.

    An empty book and a book that could not be found are different answers, and
    the note names the date it looked before rather than leaving an empty account
    to be read as a flat one.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    store.upsert(
        "positions",
        [
            {"trade_date": "2026-09-22", "ticker": "AAA", "signed_notional": 500.0},
        ],
    )
    monkeypatch.setattr(alpaca, "read_client", lambda: _FakeBroker([]))

    result = positions.check(dry_run=True, before="2026-09-22")

    assert result["store"] == {}
    assert result["store_source"] == "the store holds no position row before 2026-09-22"
    assert result["establishment"] is True


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


def test_an_unreadable_account_stops_a_live_run_but_not_a_dry_one(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store-book fallback is allowed only in dry run.

    The case the store-based answer got wrong: with no account read, `held` fell
    back to the store's own book, so asking it "is it empty" answered "yes"
    whenever the store was, and the evening would be treated as an establishment
    day on the strength of a missing credential. In live mode a failed read must
    stop the run, not fall back; in dry run it is reported.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(alpaca, "read_client", lambda: None)

    with pytest.raises(RuntimeError, match="positions could not be read"):
        positions.check(dry_run=False)

    # Dry run: the read is still attempted, and its failure is stated rather than
    # fatal. `establishment` is False and `held` is the (empty) store book.
    result = positions.check(dry_run=True)
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


def test_a_position_row_is_a_holding_only_from_confirmed_broker_state() -> None:
    """A row is a holding only when the broker confirmed it after execution.

    Every evening before the flip writes 150 rows into `efb.positions` that no
    order ever created. They are the loop's intention, and the row says so, so
    E12's attribution cannot attribute P&L to a book that never existed. Even on
    a live evening a row is an intention until the broker confirms that name.
    """
    import pandas as pd

    from live import morning_job

    proposal = pd.DataFrame({"ticker": ["AAA", "BBB"], "weight": [0.01, -0.005]})

    dry = morning_job._positions_from_records(proposal, 100_000.0, dry_run=True)
    live_unconfirmed = morning_job._positions_from_records(
        proposal, 100_000.0, dry_run=False
    )
    live_confirmed = morning_job._positions_from_records(
        proposal, 100_000.0, dry_run=False, confirmed={"AAA"}
    )

    assert set(dry["kind"]) == {"intention"}
    assert set(live_unconfirmed["kind"]) == {"intention"}
    confirmed_kinds = dict(
        zip(live_confirmed["ticker"], live_confirmed["kind"], strict=True)
    )
    assert confirmed_kinds == {"AAA": "holding", "BBB": "intention"}


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
