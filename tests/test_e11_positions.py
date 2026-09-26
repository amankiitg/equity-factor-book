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
