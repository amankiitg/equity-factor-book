"""The broker-read paths against real alpaca-py model objects.

alpaca-py returns pydantic enums: `PositionSide.SHORT`, `OrderSide.SELL`,
`OrderStatus.ACCEPTED`, `PositionIntent.BUY_TO_OPEN`. Their `str()` is the class
name, not the API value ("PositionSide.SHORT", not "short"), so any comparison
built on `str(x).lower()` silently fails and a short reads as a long or an
accepted order reads as unknown. These tests build the real `Position(**json)` and
`Order(**json)` objects the client returns, a long and a short, an accepted and a
rejected order, and check every read site: `position_book`, the submitted result,
`_leg_incomplete`, and both smoke scripts.
"""

from __future__ import annotations

import uuid

import pandas as pd
import pytest

from live import alpaca, guards, morning_job
from scripts import smoke_order_timing, smoke_position_intents

NAV = 1_000_000.0


def _position(symbol: str, qty: float, market_value: float, side: str):
    """A real Position, the way `get_all_positions` returns one."""
    from alpaca.trading.models import Position

    return Position(
        asset_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, symbol)),
        symbol=symbol,
        exchange="NASDAQ",
        asset_class="us_equity",
        avg_entry_price="100",
        qty=str(qty),
        side=side,
        market_value=str(market_value),
        cost_basis=str(market_value),
    )


def _order(
    status: str = "accepted",
    *,
    symbol: str = "AAA",
    side: str = "buy",
    qty: str = "5",
    client_order_id: str = "efb-2026-09-25-AAA-B-deadbeef",
    position_intent: str = "buy_to_open",
):
    """A real Order, the way submit and the lookups return one."""
    from alpaca.trading.models import Order

    return Order(
        id=str(uuid.uuid5(uuid.NAMESPACE_DNS, client_order_id)),
        client_order_id=client_order_id,
        created_at="2026-09-25T22:30:00Z",
        updated_at="2026-09-25T22:30:00Z",
        submitted_at="2026-09-25T22:30:00Z",
        order_class="simple",
        time_in_force="day",
        status=status,
        extended_hours=False,
        symbol=symbol,
        side=side,
        qty=qty,
        position_intent=position_intent,
    )


class _Asset:
    tradable = True
    shortable = True
    easy_to_borrow = True


class _ModelClient:
    """A client whose reads and submits return real alpaca-py objects."""

    def __init__(
        self,
        positions: list[object] | None = None,
        order: object | None = None,
    ) -> None:
        self._positions = positions or []
        self._order = order
        self.requests: list[object] = []

    def get_all_positions(self) -> list[object]:
        return list(self._positions)

    def get_asset(self, symbol: str) -> _Asset:
        return _Asset()

    def submit_order(self, order_data: object) -> object:
        self.requests.append(order_data)
        assert self._order is not None, "a submit was not expected"
        return self._order


def test_position_book_reads_real_positions_including_a_short() -> None:
    client = _ModelClient(
        positions=[
            _position("AAA", 10, 1000, "long"),
            _position("BBB", -5, -500, "short"),
        ]
    )

    notional, quantity = alpaca.position_book(client, dry_run=False)

    assert notional == {"AAA": 1000.0, "BBB": -500.0}
    # The sign comes from the signed quantity, so a short is negative even if the
    # side enum were misread.
    assert quantity == {"AAA": 10.0, "BBB": -5.0}


def test_position_book_falls_back_to_the_side_enum_for_a_missing_qty() -> None:
    class _NoQty:
        symbol = "CCC"
        qty = None
        market_value = "250"
        side = "short"

    client = _ModelClient(positions=[_NoQty()])
    notional, quantity = alpaca.position_book(client, dry_run=False)

    assert notional == {"CCC": -250.0}
    assert quantity == {"CCC": 0.0}


def test_a_submitted_real_order_is_recorded_by_its_status_value() -> None:
    client = _ModelClient(order=_order(status="accepted"))
    fills = alpaca.submit_market_orders(
        [guards.OrderSpec("AAA", 5_000.0, 5_000.0)],
        client,
        {"AAA": 100.0},
        close="2026-09-25",
        throttle=alpaca.Throttle(0),
    )
    assert fills[0].status == "ACCEPTED"
    assert fills[0].intent == "buy_to_open"


def test_leg_incomplete_reads_order_status_enums_not_reprs() -> None:
    from alpaca.trading.enums import OrderStatus

    # Passing the raw enum is the case that would fail on `str(x).upper()`.
    assert morning_job._leg_incomplete(OrderStatus.ACCEPTED, "") is False
    assert morning_job._leg_incomplete(OrderStatus.NEW, "") is False
    assert morning_job._leg_incomplete(OrderStatus.REJECTED, "") is True
    assert morning_job._leg_incomplete(OrderStatus.CANCELED, "") is True


def test_a_real_rejected_order_makes_the_run_incomplete() -> None:
    client = _ModelClient(
        order=_order(
            status="rejected",
            side="sell",
            qty="1",
            position_intent="sell_to_open",
        )
    )
    fills = alpaca.submit_market_orders(
        [guards.OrderSpec("AAA", -5_000.0, -5_000.0)],
        client,
        {"AAA": 100.0},
        close="2026-09-25",
        throttle=alpaca.Throttle(0),
    )
    assert fills[0].status == "REJECTED"

    records = pd.DataFrame(
        {
            "ticker": [fill.ticker for fill in fills],
            "status": [fill.status for fill in fills],
            "reason_code": [fill.reason_code for fill in fills],
        }
    )
    legs = morning_job.incomplete_legs(records)
    assert [leg["ticker"] for leg in legs] == ["AAA"]


def test_both_smoke_scripts_read_a_real_order_status() -> None:
    accepted = _order(status="accepted", position_intent="sell_to_open")
    assert smoke_order_timing._status_of(accepted) == "accepted"
    assert smoke_order_timing._status_of(_order(status="rejected")) == "rejected"

    fill = alpaca.Fill(
        ticker="AAA",
        order_id="order-1",
        intended_notional=100.0,
        filled_notional=0.0,
        fill_price=0.0,
        status=accepted.status,
        intent=accepted.position_intent,
    )
    report = smoke_position_intents._fill_report(fill)
    assert report["accepted"] is True
    assert report["status"] == "accepted"
    assert report["position_intent"] == "sell_to_open"


def test_a_short_real_position_sizes_a_full_close() -> None:
    """The quantity read from a real short is what a cover sends."""
    client = _ModelClient(positions=[_position("BBB", -5, -500, "short")])
    notional, quantity = alpaca.position_book(client, dry_run=False)
    client._order = _order(
        status="accepted",
        symbol="BBB",
        side="buy",
        qty="5",
        position_intent="buy_to_close",
    )
    fills = alpaca.submit_market_orders(
        [
            guards.OrderSpec(
                "BBB",
                target_notional=0.0,
                trade_notional=-notional["BBB"],
                intent=alpaca.INTENT_BUY_TO_CLOSE,
                held_quantity=quantity["BBB"],
            )
        ],
        client,
        {},
        close="2026-09-28",
        throttle=alpaca.Throttle(0),
    )
    assert fills[0].status == "ACCEPTED"
    assert float(client.requests[0].qty) == pytest.approx(5.0)


def test_the_rehearsal_broker_returns_real_models() -> None:
    """The fake broker in the rehearsal hands back what Alpaca hands back."""
    from alpaca.trading.models import Order, Position

    from scripts import rehearse_preflip

    broker = rehearse_preflip.FakeBroker({"AAA": 100.0})
    broker.holdings["AAA"] = 7.0
    positions = broker.get_all_positions()
    assert positions and isinstance(positions[0], Position)
    assert float(positions[0].qty) == pytest.approx(7.0)

    order = broker.submit_order(_request("AAA", "buy", qty="1", intent="buy_to_open"))
    assert isinstance(order, Order)
    assert alpaca.enum_value(order.status) == "accepted"


def _request(symbol: str, side: str, *, qty: str, intent: str):
    from alpaca.trading.requests import MarketOrderRequest

    return MarketOrderRequest(
        symbol=symbol,
        qty=float(qty),
        side=side,
        time_in_force="day",
        client_order_id=f"efb-broker-model-{symbol}",
        position_intent=intent,
    )
