"""Rehearse three days against a broker that behaves like Alpaca after the close.

Day one establishes the book from flat. Day two rebalances it: a long increased, a
long decreased, a long removed, a short covered, and a long reversed. The reversal
cannot cross zero in one order, so tonight only closes the long and the short side
opens on day three. The transcript shows the position intent and size of every leg,
that each order is the signed change, that the removed name is closed to zero, and
that a reversal is a close tonight and an open tomorrow.

Every day also goes through the account guard the live evening runs: the number the
broker reports is checked against `EFB_ALPACA_ACCOUNT_ID`, and an evening that would
establish the whole book is refused unless the account is flat and has nothing
working at the broker. The prior book the cost and the turnover are measured against
is the account's own holdings over its own equity, so the transcript prints it each
day, and an establishment evening prints that there is none.

The fake broker is deliberately strict, the three ways Alpaca is:
  * an order that would cross zero is rejected;
  * a sell beyond the held quantity is rejected unless it is SELL_TO_OPEN;
  * a DAY order submitted after the close is **accepted**, not filled, and fills
    at the next open, which `settle_open` performs between days.

Run it with `.venv/bin/python scripts/rehearse_preflip.py`. Nothing here touches a
network, a key or a store.
"""

from __future__ import annotations

import os
import sys
import uuid
from typing import Any
from unittest.mock import patch

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# No pacing between fake submissions; the real interval is a rate limit for a
# network that is not here.
os.environ.setdefault("EFB_MIN_SUBMIT_INTERVAL_SECS", "0")

from live import alpaca, morning_job, positions  # noqa: E402 - after the env line

NAV = 1_000_000.0
# The account the fake broker reports, and the number the guard is told to expect:
# they are the same string, which is what the live run checks before it sizes.
ACCOUNT_NUMBER = "PA3A50WIU0O0"
os.environ.setdefault(alpaca.ACCOUNT_ID_ENV, ACCOUNT_NUMBER)
PRICES = {"AAA": 100.0, "BBB": 50.0, "CCC": 200.0, "DDD": 25.0, "FFF": 40.0}

# Day one: from flat, four long and one short.
DAY_ONE = {"AAA": 0.08, "BBB": 0.08, "CCC": 0.08, "DDD": 0.08, "FFF": -0.08}
# Day two: AAA up, BBB down, CCC reversed (long to short), DDD removed, FFF covered.
DAY_TWO = {"AAA": 0.10, "BBB": 0.04, "CCC": -0.06, "FFF": -0.02}
# Day three: the same targets, so CCC's deferred short opens in the normal delta.
DAY_THREE = dict(DAY_TWO)

_OPEN_INTENTS = frozenset({alpaca.INTENT_BUY_TO_OPEN, alpaca.INTENT_SELL_TO_OPEN})
_CLOSE_INTENTS = frozenset({alpaca.INTENT_BUY_TO_CLOSE, alpaca.INTENT_SELL_TO_CLOSE})


class BrokerRejection(RuntimeError):
    """The broker evaluated the order and declined it."""


SUBMITTED_AT = "2026-09-25T22:30:00Z"


def _position_model(symbol: str, shares: float, price: float) -> Any:
    """A real alpaca-py Position, as `get_all_positions` returns it."""
    from alpaca.trading.enums import AssetClass, AssetExchange, PositionSide
    from alpaca.trading.models import Position

    value = abs(shares) * price
    return Position(
        asset_id=uuid.uuid5(uuid.NAMESPACE_DNS, symbol),
        symbol=symbol,
        exchange=AssetExchange.NASDAQ,
        asset_class=AssetClass.US_EQUITY,
        avg_entry_price=str(price),
        qty=str(shares),
        side=PositionSide.LONG if shares >= 0 else PositionSide.SHORT,
        market_value=str(value),
        cost_basis=str(value),
    )


def _order_model(record: dict[str, Any]) -> Any:
    """A real alpaca-py Order, as submit and the lookups return it."""
    from alpaca.trading.models import Order

    return Order(
        id=str(uuid.uuid5(uuid.NAMESPACE_DNS, record["client_order_id"])),
        client_order_id=record["client_order_id"],
        created_at=SUBMITTED_AT,
        updated_at=SUBMITTED_AT,
        submitted_at=SUBMITTED_AT,
        order_class="simple",
        time_in_force="day",
        status=record["status"],
        extended_hours=False,
        symbol=record["symbol"],
        side=record["side"],
        qty=record["qty"],
        filled_qty=record.get("filled_qty"),
        filled_avg_price=record.get("filled_avg_price"),
        position_intent=record["intent"],
    )


def _intent_of(order_data: Any) -> str:
    return str(alpaca.enum_value(getattr(order_data, "position_intent", "")) or "")


class FakeBroker:
    """Holds positions, accepts after-close DAY orders, settles at the open."""

    def __init__(self, prices: dict[str, float], nav: float = NAV) -> None:
        self.prices = dict(prices)
        self.holdings: dict[str, float] = {}  # signed shares
        self.orders: dict[str, dict[str, Any]] = {}
        self.pending: list[dict[str, Any]] = []
        self.submitted: list[dict[str, Any]] = []
        self.equity = nav
        self.buying_power = nav

    # --- reads ---------------------------------------------------------------
    def get_account(self) -> object:
        broker = self

        class _Account:
            equity = broker.equity
            buying_power = broker.buying_power
            account_number = ACCOUNT_NUMBER
            id = "fake-paper-account"

        return _Account()

    def get_orders(self, filter: Any = None) -> list[object]:
        """The orders the broker is still working, as Alpaca's list read returns."""
        return [
            _order_model(record) for record in self.pending if record["status"] == "accepted"
        ]

    def get_asset(self, symbol: str) -> object:
        class _Asset:
            tradable = True
            shortable = True
            easy_to_borrow = True

        return _Asset()

    def get_all_positions(self) -> list[object]:
        return [
            _position_model(symbol, shares, self.prices[symbol])
            for symbol, shares in sorted(self.holdings.items())
            if abs(shares) > 1e-9
        ]

    def get_order_by_client_id(self, ticket: str) -> Any | None:
        record = self.orders.get(ticket)
        return None if record is None else _order_model(record)

    def get_order(self, order_id: str) -> Any:
        for record in self.orders.values():
            if str(uuid.uuid5(uuid.NAMESPACE_DNS, record["client_order_id"])) == str(
                order_id
            ):
                return _order_model(record)
        raise KeyError(order_id)

    # --- writes --------------------------------------------------------------
    def submit_order(self, order_data: Any) -> Any:
        ticket = str(getattr(order_data, "client_order_id", ""))
        if ticket in self.orders:
            raise BrokerRejection(f"duplicate client_order_id {ticket}")
        symbol = str(order_data.symbol)
        price = self.prices[symbol]
        intent = _intent_of(order_data)
        # Read the side by value: alpaca-py gives an OrderSide enum, whose str()
        # is "OrderSide.SELL".
        side = str(alpaca.enum_value(getattr(order_data, "side", ""))).lower()
        notional = getattr(order_data, "notional", None)
        qty = float(notional) / price if notional is not None else float(order_data.qty)
        delta = qty if side == "buy" else -qty
        self._validate(symbol, intent, qty, delta)
        record: dict[str, Any] = {
            "client_order_id": ticket,
            # After the close a DAY order is accepted, not filled.
            "status": "accepted",
            "symbol": symbol,
            "side": side,
            "intent": intent,
            "qty": qty,
            "delta": delta,
            "price": price,
        }
        self.orders[ticket] = record
        self.pending.append(record)
        self.submitted.append(record)
        return _order_model(record)

    def _validate(self, symbol: str, intent: str, qty: float, delta: float) -> None:
        held = self.holdings.get(symbol, 0.0)
        after = held + delta
        if intent not in _OPEN_INTENTS | _CLOSE_INTENTS:
            raise BrokerRejection(f"{symbol}: missing position_intent")
        if intent in _CLOSE_INTENTS and abs(held) <= 1e-9:
            raise BrokerRejection(f"{symbol}: nothing to close")
        if held > 0 and after < -1e-9:
            raise BrokerRejection(f"{symbol}: order crosses zero ({held} -> {after})")
        if held < 0 and after > 1e-9:
            raise BrokerRejection(f"{symbol}: order crosses zero ({held} -> {after})")
        if intent == alpaca.INTENT_SELL_TO_CLOSE and qty > abs(held) + 1e-9:
            raise BrokerRejection(f"{symbol}: sell {qty} beyond held {abs(held)}")
        if intent == alpaca.INTENT_BUY_TO_CLOSE and qty > abs(held) + 1e-9:
            raise BrokerRejection(f"{symbol}: buy {qty} beyond held {abs(held)}")
        if intent == alpaca.INTENT_SELL_TO_OPEN and held > 1e-9:
            raise BrokerRejection(f"{symbol}: sell-to-open would cross a long")

    def settle_open(self) -> list[str]:
        """Fill every accepted order at the next open and report the tickers."""
        filled: list[str] = []
        for record in self.pending:
            symbol = record["symbol"]
            self.holdings[symbol] = self.holdings.get(symbol, 0.0) + record["delta"]
            record["status"] = "filled"
            record["filled_qty"] = abs(record["qty"])
            record["filled_avg_price"] = record["price"]
            filled.append(symbol)
        self.pending = []
        return filled


def _proposal(weights: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": list(weights),
            "weight": [weights[name] for name in weights],
            "alpha": 0.0,
        }
    )


def _guard_the_account(broker: FakeBroker, *, establishing: bool) -> None:
    """Run the live evening's account guard against the fake, and print it.

    The guard reads the account, checks the number against `EFB_ALPACA_ACCOUNT_ID`,
    and then, on an evening that would establish the whole book, reads the account's
    working orders and refuses if there are any. The store is not consulted: an
    empty frame stands in for it, which is what the guard needs of it here.
    """
    empty = pd.DataFrame()
    with (
        patch.object(alpaca, "read_client", lambda: broker),
        patch.object(positions.store, "select", lambda *a, **k: empty),
    ):
        result = positions.check(dry_run=True)
    assert result["account_number"] == ACCOUNT_NUMBER, result["account_number"]
    assert result["establishment"] is establishing, (
        result["establishment"],
        establishing,
    )
    prior = positions.prior_weights(
        result, establishment=bool(result["establishment"])
    )
    if establishing:
        assert prior is None, "an establishment evening must have no prior book"
        print(
            "  account guard: "
            f"{ACCOUNT_NUMBER} matches, {len(result['open_orders'])} working "
            "order(s), so the whole book may be established"
        )
        print("  prior book: none (the account holds nothing, so zero is the book)")
        return
    assert prior is not None
    gross = float(prior.abs().sum())
    print(
        "  account guard: "
        f"{ACCOUNT_NUMBER} matches, {len(result['broker'])} name(s) held, so this "
        "is a rebalance"
    )
    print(
        "  prior book: "
        + ", ".join(
            f"{name} {value:+.4f}" for name, value in sorted(prior.items())
        )
        + f" (gross {gross:.4f} of NAV)"
    )
    assert gross > 0.0


def _refuse_a_wrong_account(broker: FakeBroker) -> None:
    """The negative control: another account number refuses before anything else.

    Both are paper accounts under one login, so a key pasted from the other project
    reads a real book: the guard has to stop the run and say which account it
    reached.
    """
    empty = pd.DataFrame()
    with (
        patch.object(alpaca, "read_client", lambda: broker),
        patch.object(positions.store, "select", lambda *a, **k: empty),
        patch.dict(os.environ, {alpaca.ACCOUNT_ID_ENV: "PAOTHER0001"}),
    ):
        try:
            positions.check(dry_run=True)
        except alpaca.AccountMismatch as exc:
            message = str(exc)
        else:  # pragma: no cover - the refusal is the result
            raise AssertionError("a wrong account number did not refuse")
    assert ACCOUNT_NUMBER in message and "PAOTHER0001" in message, message
    print("  guard control: a wrong account number refuses, naming both accounts")


def run_day(
    as_of: str, weights: dict[str, float], broker: FakeBroker
) -> tuple[dict[str, float], dict[str, float], dict, pd.DataFrame]:
    """One evening: read the broker, build and submit the deltas, return the log."""
    captured: dict[str, pd.DataFrame] = {}

    def _capture(day: str, records: pd.DataFrame) -> None:
        captured[day] = records

    proposal = _proposal(weights)
    held, quantities = alpaca.position_book(broker, dry_run=False)
    _guard_the_account(broker, establishing=not held)
    with (
        patch.object(morning_job, "load_proposal", lambda *a, **k: proposal),
        patch.object(morning_job, "connect", lambda dry_run: broker),
        patch.object(morning_job, "_close_prices", lambda *a, **k: dict(PRICES)),
        patch.object(morning_job.state, "write_positions", lambda *a, **k: None),
        patch.object(morning_job, "_write_execution_log", _capture),
    ):
        summary = morning_job.run_morning(
            as_of,
            nav=NAV,
            dry_run=False,
            positions=held,
            quantities=quantities,
            establishment=not held,
        )
    return held, quantities, summary, captured[as_of]


def _show(records: pd.DataFrame, held: dict[str, float]) -> None:
    print(f"  {'ticker':<7}{'held':>12}{'delta':>12}{'intent':>16}  status")
    for row in records.itertuples(index=False):
        name = str(row.ticker)
        print(
            f"  {name:<7}{held.get(name, 0.0):>+12,.0f}"
            f"{float(row.intended_notional):>+12,.0f}"
            f"{str(row.position_intent):>16}  {row.status}"
        )


def _shares(quantities: dict[str, float]) -> str:
    return ", ".join(
        f"{name} {value:+.4g}" for name, value in sorted(quantities.items())
    )


def main() -> int:
    broker = FakeBroker(PRICES)
    print("=== EFB broker rehearsal: three trading days, strict fake broker ===")
    print(f"NAV {NAV:,.0f}; prices {PRICES}")

    print("\n--- DAY 1 (2026-09-25): account flat, establishes from zero ---")
    _refuse_a_wrong_account(broker)
    held, quantities, summary, records = run_day("2026-09-25", DAY_ONE, broker)
    print(f"  held {len(held)}; establishment={summary['establishment']}")
    for row in records.itertuples(index=False):
        print(
            f"    {str(row.ticker):<5}{str(row.position_intent):>16}"
            f"{float(row.intended_notional):>+12,.0f}  {row.status}"
        )
    assert summary["complete"] and summary["orders"] == len(DAY_ONE)
    assert set(records["status"]) == {"ACCEPTED"}, list(records["status"])
    assert broker.holdings == {}, "an accepted order changed holdings before the open"
    applied = broker.settle_open()
    print(f"  next open: filled {len(applied)}: {', '.join(sorted(applied))}")
    print(
        "  broker holds (shares): "
        f"{_shares(alpaca.position_book(broker, dry_run=False)[1])}"
    )

    print("\n--- DAY 2 (2026-09-28): rebalances; CCC reverses ---")
    held, quantities, summary, records = run_day("2026-09-28", DAY_TWO, broker)
    print(f"  held {len(held)}; establishment={summary['establishment']}")
    print(f"  held (shares): {_shares(quantities)}")
    _show(records, held)
    assert summary["complete"], summary["incomplete_legs"]
    assert set(records["status"]) == {"ACCEPTED"}, list(records["status"])
    ccc = records.loc[records["ticker"] == "CCC"].iloc[0]
    assert ccc["position_intent"] == "sell_to_close", ccc["position_intent"]
    assert float(ccc["intended_notional"]) == -DAY_ONE["CCC"] * NAV
    deferred = summary["deferred_reversals"]
    assert [item["ticker"] for item in deferred] == ["CCC"]
    assert float(deferred[0]["target_notional"]) == DAY_TWO["CCC"] * NAV
    print(
        "  deferred reversal: "
        f"{deferred[0]['ticker']} closed tonight, "
        f"{float(deferred[0]['target_notional']):+,.0f} opens next evening"
    )
    ddd = records.loc[records["ticker"] == "DDD"].iloc[0]
    assert ddd["position_intent"] == "sell_to_close", "the removal was not a close"
    assert float(ddd["intended_notional"]) == -DAY_ONE["DDD"] * NAV
    fff = records.loc[records["ticker"] == "FFF"].iloc[0]
    assert fff["position_intent"] == "buy_to_close", "the cover was not a close"
    applied = broker.settle_open()
    print(f"  next open: filled {len(applied)}: {', '.join(sorted(applied))}")
    print(
        "  broker holds (shares): "
        f"{_shares(alpaca.position_book(broker, dry_run=False)[1])}"
    )

    print("\n--- DAY 3 (2026-09-29): the deferred short opens ---")
    held, quantities, summary, records = run_day("2026-09-29", DAY_THREE, broker)
    print(f"  held {len(held)}; establishment={summary['establishment']}")
    print(f"  held (shares): {_shares(quantities)}")
    _show(records, held)
    assert summary["complete"], summary["incomplete_legs"]
    assert list(records["ticker"]) == ["CCC"], list(records["ticker"])
    ccc = records.iloc[0]
    assert ccc["position_intent"] == "sell_to_open", ccc["position_intent"]
    assert float(ccc["intended_notional"]) == DAY_THREE["CCC"] * NAV
    assert summary["deferred_reversals"] == []
    applied = broker.settle_open()
    print(f"  next open: filled {len(applied)}: {', '.join(sorted(applied))}")
    print(
        "  broker holds (shares): "
        f"{_shares(alpaca.position_book(broker, dry_run=False)[1])}"
    )

    print("\n--- DAY 3 RERUN: the broker holds the day-3 book ---")
    before = len(broker.submitted)
    _held, _quantities, summary, _rerun_records = run_day(
        "2026-09-29", DAY_THREE, broker
    )
    assert summary["orders"] == 0, summary["orders"]
    assert len(broker.submitted) == before, "a rerun submitted an order"
    assert summary["complete"]
    print("  orders 0 (nothing new submitted); complete=True")

    print("\n--- ORDER RECORDS: the broker's id for every leg that became one ---")
    # The day-3 log, whose one leg was accepted: the rerun above submitted nothing,
    # so its log is empty by construction.
    assert _rerun_records.empty, _rerun_records
    ids = {
        str(row.ticker): str(row.broker_order_id)
        for row in records.itertuples(index=False)
        if str(row.status) == "ACCEPTED"
    }
    assert ids and all(value for value in ids.values()), ids
    print(
        "  accepted legs carry the broker's order id: "
        + ", ".join(f"{name} {value[:8]}" for name, value in sorted(ids.items()))
    )
    assert str(records.iloc[0]["client_order_id"]).startswith("efb-"), (
        "the deterministic ticket is still recorded beside the broker id"
    )

    print("\nAll checks passed: every leg carried a position intent, the reversal")
    print("closed tonight and opened tomorrow, the removed name was closed, and an")
    print("accepted after-close DAY order changed nothing until the next open.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
