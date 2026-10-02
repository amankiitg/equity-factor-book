"""Sprint E11: the morning after, against the broker's own order records.

The objects here are real `alpaca.trading.models.Order` instances, not stand-ins
with the same attribute names: a status is an `OrderStatus` enum and a filled
quantity arrives as a string, which is exactly what a hand-written double would
hide. The three states that matter are filled, partially filled and cancelled,
because they are the three the owner's message has to tell apart.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pandas as pd
import pytest

from live import alpaca, fills, store

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "live" / "supabase_schema.sql"
NAV = 998_580.38


def _order(
    status: str = "filled",
    *,
    order_id: str = "oid-aaa",
    ticker: str = "AAA",
    side: str = "buy",
    qty: str | None = "41",
    notional: str | None = None,
    filled_qty: str | None = "41",
    filled_avg_price: str | None = "12.62",
    canceled_at: str | None = None,
    updated_at: str = "2026-10-02T12:15:00Z",
    position_intent: str = "sell_to_open",
):
    """A real Order, the way `get_order_by_id` returns one."""
    from alpaca.trading.models import Order

    return Order(
        id=str(uuid.uuid5(uuid.NAMESPACE_DNS, order_id)),
        client_order_id=f"efb-2026-10-01-{ticker}-S-deadbeef",
        created_at="2026-10-01T22:30:00Z",
        updated_at=updated_at,
        submitted_at="2026-10-01T22:30:00Z",
        order_class="simple",
        time_in_force="day",
        status=status,
        extended_hours=False,
        symbol=ticker,
        side=side,
        qty=qty,
        notional=notional,
        filled_qty=filled_qty,
        filled_avg_price=filled_avg_price,
        canceled_at=canceled_at,
        position_intent=position_intent,
    )


class _Broker:
    """A client that can be asked about an order and can never be sent one."""

    def __init__(self, orders: dict[str, object], *, unreadable: tuple[str, ...] = ()):
        self._orders = orders
        self._unreadable = set(unreadable)
        self.asked: list[str] = []
        self.submitted: list[object] = []

    def get_order_by_id(self, order_id: object) -> object:
        self.asked.append(str(order_id))
        if str(order_id) in self._unreadable:
            raise LookupError("no order with that id")
        return self._orders[str(order_id)]

    def submit_order(self, request: object) -> object:  # pragma: no cover - a guard
        self.submitted.append(request)
        raise AssertionError("the fills reconciler must never submit an order")


def _orders(rows: list[dict[str, object]]) -> pd.DataFrame:
    base = {
        "trade_date": "2026-10-01",
        "intended_notional": 500.0,
        "status": "ACCEPTED",
        "reason_code": "",
        "client_order_id": "efb-2026-10-01-AAA-S-deadbeef",
        "position_intent": "sell_to_open",
        "broker_order_id": "oid-aaa",
    }
    return pd.DataFrame([{**base, **row} for row in rows])


def _closes(**pairs: float) -> pd.Series:
    return pd.Series(pairs, dtype=float)


def test_a_filled_order_carries_its_quantity_price_and_status() -> None:
    broker = _Broker({"oid-aaa": _order("filled")})

    report = fills.reconcile_day(
        _orders([{"ticker": "AAA", "broker_order_id": "oid-aaa"}]),
        broker,
        closes=_closes(AAA=12.5),
        nav=NAV,
    )

    frame = report["fills"]
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["status"] == "FILLED"
    assert row["filled_quantity"] == 41.0
    assert row["fill_price"] == 12.62
    assert row["filled_notional"] == pytest.approx(41 * 12.62)
    assert row["close_price"] == 12.5
    assert report["n_filled"] == 1
    assert report["unfilled"] == [], "a fill is not reported as a miss"
    assert broker.asked == ["oid-aaa"], "the read is by the broker's own id"
    assert broker.submitted == [], "no order is sent from here"


def test_a_sell_filled_below_the_close_is_a_cost_and_a_buy_above_it_too() -> None:
    """The sign convention the expected cost is written in: positive is a cost."""
    broker = _Broker(
        {
            "oid-sell": _order(
                "filled", order_id="oid-sell", side="sell", filled_avg_price="12.40"
            ),
            "oid-buy": _order(
                "filled", order_id="oid-buy", side="buy", filled_avg_price="12.60"
            ),
        }
    )

    report = fills.reconcile_day(
        _orders(
            [
                {"ticker": "SELL", "broker_order_id": "oid-sell"},
                {"ticker": "BUY", "broker_order_id": "oid-buy"},
            ]
        ),
        broker,
        closes=_closes(SELL=12.5, BUY=12.5),
        nav=NAV,
    )

    frame = report["fills"].set_index("ticker")
    # Both legs paid: the sell went off below the close and the buy above it.
    assert frame.loc["SELL", "slippage_bps"] == pytest.approx(
        1e4 * (12.5 - 12.4) / 12.5
    )
    assert frame.loc["BUY", "slippage_bps"] == pytest.approx(1e4 * (12.6 - 12.5) / 12.5)
    assert frame.loc["SELL", "slippage_bps"] > 0
    assert frame.loc["BUY", "slippage_bps"] > 0


def test_a_canceled_order_is_named_with_its_status_and_time() -> None:
    """The owner's own example, asserted as text.

    `DG sell_to_open 41 canceled 12:15 UTC`, character for character.
    """
    broker = _Broker(
        {
            "oid-dg": _order(
                "canceled",
                order_id="oid-dg",
                ticker="DG",
                side="sell",
                qty="41",
                filled_qty="0",
                filled_avg_price=None,
                canceled_at="2026-10-02T12:15:00Z",
                updated_at="2026-10-02T12:15:00Z",
                position_intent="sell_to_open",
            )
        }
    )

    report = fills.reconcile_day(
        _orders(
            [{"ticker": "DG", "broker_order_id": "oid-dg", "intended_notional": 500.0}]
        ),
        broker,
        closes=_closes(DG=12.5),
        nav=NAV,
    )

    assert report["unfilled"] == ["DG sell_to_open 41 canceled 12:15 UTC"]
    row = report["fills"].iloc[0]
    assert row["status"] == "CANCELED"
    assert row["filled_quantity"] == 0.0
    assert row["filled_notional"] == 0.0, "a canceled order filled nothing"
    assert row["cancel_time"] == "2026-10-02T12:15:00+00:00"
    assert report["n_unfilled"] == 1
    assert report["realized_cost_bps"] is None, "nothing traded, so a cost is a claim"


def test_a_partially_filled_order_is_reported_as_a_miss() -> None:
    broker = _Broker(
        {
            "oid-part": _order(
                "partially_filled",
                order_id="oid-part",
                ticker="NWSA",
                side="sell",
                qty="23",
                filled_qty="9",
                filled_avg_price="31.05",
                updated_at="2026-10-02T13:45:00Z",
                position_intent="sell_to_open",
            )
        }
    )

    report = fills.reconcile_day(
        _orders([{"ticker": "NWSA", "broker_order_id": "oid-part"}]),
        broker,
        closes=_closes(NWSA=31.0),
        nav=NAV,
    )

    assert report["unfilled"] == ["NWSA sell_to_open 23 partially filled 13:45 UTC"]
    row = report["fills"].iloc[0]
    assert row["filled_quantity"] == 9.0
    assert row["filled_notional"] == pytest.approx(9 * 31.05)
    assert report["n_filled"] == 0 and report["n_unfilled"] == 1


def test_a_leg_that_was_never_sent_is_not_asked_about() -> None:
    """A refused short has no broker id, so it is counted rather than looked up."""
    broker = _Broker({})

    report = fills.reconcile_day(
        _orders(
            [
                {
                    "ticker": "SOLV",
                    "broker_order_id": "",
                    "status": "SKIPPED",
                    "reason_code": "NOT_EASY_TO_BORROW",
                }
            ]
        ),
        broker,
        closes=_closes(SOLV=40.0),
        nav=NAV,
    )

    assert broker.asked == []
    assert report["fills"].empty
    assert report["not_sent"] == 1
    assert report["n_orders"] == 0
    assert report["unfilled"] == []


def test_an_order_the_broker_will_not_answer_about_is_not_called_unfilled() -> None:
    """A read that failed is a question to answer, not a leg that did not happen."""
    broker = _Broker({}, unreadable=("oid-lost",))

    report = fills.reconcile_day(
        _orders([{"ticker": "AAA", "broker_order_id": "oid-lost"}]),
        broker,
        closes=_closes(AAA=12.5),
        nav=NAV,
    )

    assert report["unread"] == [
        {"ticker": "AAA", "order_id": "oid-lost", "error": "LookupError"}
    ]
    assert report["fills"].empty
    assert report["unfilled"] == [], "unread is not the same statement as unfilled"


def test_the_realized_cost_is_the_slippage_in_dollars_over_the_nav() -> None:
    broker = _Broker(
        {
            "oid-a": _order(
                "filled", order_id="oid-a", side="buy", filled_avg_price="12.60"
            ),
            "oid-b": _order(
                "filled", order_id="oid-b", side="buy", filled_avg_price="12.40"
            ),
        }
    )

    report = fills.reconcile_day(
        _orders(
            [
                {"ticker": "AAA", "broker_order_id": "oid-a"},
                {"ticker": "BBB", "broker_order_id": "oid-b"},
            ]
        ),
        broker,
        closes=_closes(AAA=12.5, BBB=12.5),
        nav=NAV,
    )

    # 41 shares at +0.10 and 41 at -0.10 against a $998,580.38 book: a wash.
    assert report["realized_cost_bps"] == pytest.approx(0.0, abs=1e-9)
    frame = report["fills"].set_index("ticker")
    assert frame.loc["AAA", "slippage_bps"] == pytest.approx(80.0)
    assert frame.loc["BBB", "slippage_bps"] == pytest.approx(-80.0)


def test_the_frames_columns_are_the_tables_columns() -> None:
    """What is written must fit the table, including the columns added for this.

    Read from the table's OWN definition rather than from the file: searching the
    whole schema for a column name passes on a column that only `efb.orders` has,
    which is exactly how `position_intent` went missing from `efb.fills` while
    this test was green -- and the writer's INSERT names every column in
    `FILL_COLUMNS`, so the live table would have refused the first morning.
    """
    keys = store.TABLE_KEYS["fills"]
    assert keys == ("trade_date", "ticker", "order_id")
    for column in ("filled_quantity", "fill_price", "cancel_time", "slippage_bps"):
        assert column in fills.FILL_COLUMNS

    schema = SCHEMA.read_text()
    create = schema.split("create table if not exists efb.fills (")[1].split("\n);")[0]
    added = set(
        re.findall(r"alter table efb\.fills\s+add column if not exists (\w+)", schema)
    )
    # The seven columns the table was created with, which the live table already
    # has: only the rest need an additive statement for a table that exists.
    original = keys + (
        "intended_notional",
        "filled_notional",
        "fill_price",
        "status",
    )
    for column in fills.FILL_COLUMNS:
        assert f"{column} " in create, f"{column} is not in efb.fills' create block"
        if column not in original:
            assert column in added, f"{column} has no additive statement for efb.fills"


def test_the_module_cannot_be_asked_for_an_order_to_send() -> None:
    """The one property the cron depends on: there is no sizing or submit path.

    Read off the syntax tree rather than off the text, so the docstring that
    explains this very guarantee is not what fails the test.
    """
    import ast

    tree = ast.parse((ROOT / "live" / "fills.py").read_text())
    called = {
        getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    forbidden = {
        "submit_order",
        "submit_market_orders",
        "build_proposal",
        "target_orders",
        "apply_guards",
        "run_morning",
    }
    assert not (called & forbidden), f"live/fills.py calls {called & forbidden}"
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported == {"__future__", "typing", "pandas", "live"}, (
        "the reconciler reads the broker layer and nothing else it could trade "
        f"through: {sorted(imported)}"
    )
    from_live = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "live"
        for alias in node.names
    }
    assert from_live == {
        "alpaca"
    }, f"live/fills.py imports {sorted(from_live)} from live"
    assert alpaca.read_order.__doc__, "the read is documented where it lives"
