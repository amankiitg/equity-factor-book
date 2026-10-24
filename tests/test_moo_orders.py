"""The market-on-open switch, and the orders it sends with the flag unset.

The morning submits at 22:30 UTC and the broker releases the legs into the next
pre-market session, where a `day` market order fills at the first quote after the
bell rather than in the opening auction. `EFB_ORDER_TIF=opg` asks for the auction
instead, and the three facts below are what makes that a flag rather than a
rewrite: unset, the orders are the ones the loop has always sent; set, every leg
is eligible only in the auction; and the leg the broker releases after 09:28 ET
falls back to `day` rather than being refused.

The Alpaca rules these tests pin are quoted in `docs/research/moo_orders.md`.
"""

from __future__ import annotations

from typing import Any

import pytest

from live import alpaca, guards

PRICES = {"AAA": 100.0, "BBB": 100.0, "CCC": 100.0, "DDD": 100.0}


class _Order:
    def __init__(self, order_id: str = "order-1", status: str = "accepted") -> None:
        self.id = order_id
        self.status = status
        self.filled_avg_price = None
        self.filled_qty = None


class _Client:
    """A paper client that records what was sent and holds nothing already."""

    def __init__(self, existing: dict[str, _Order] | None = None) -> None:
        self.requests: list[Any] = []
        # The broker's answer for a rerun's ticket lookup, by client_order_id.
        self.existing = existing or {}

    def get_asset(self, symbol: str) -> object:
        class _Asset:
            tradable = True
            shortable = True
            easy_to_borrow = True
            name = "an asset"

        return _Asset()

    def get_order_by_client_id(self, ticket: str) -> _Order:
        found = self.existing.get(ticket)
        if found is None:
            raise RuntimeError("order not found")
        return found

    def submit_order(self, order_data) -> _Order:
        self.requests.append(order_data)
        return _Order(f"order-{len(self.requests)}")


def _tifs(client: _Client) -> list[str]:
    return [
        str(getattr(request.time_in_force, "value", "")) for request in client.requests
    ]


def _book() -> list[guards.OrderSpec]:
    """One leg of each intent: open long, open short, close long, close short."""
    return [
        guards.OrderSpec("AAA", 50_000.0, 50_000.0),
        guards.OrderSpec("BBB", -50_000.0, -50_000.0),
        # A long decrease (held 50k, target 25k) and a short cover (held -50k):
        # `OrderSpec` is (ticker, target_notional, trade_notional).
        guards.OrderSpec("CCC", 25_000.0, -25_000.0),
        guards.OrderSpec("DDD", -25_000.0, 25_000.0),
    ]


BEFORE_CUTOFF = "2026-10-22T13:20:00Z"  # 09:20 ET, inside the opg window
AFTER_CUTOFF = "2026-10-22T13:29:00Z"  # 09:29 ET, past it


def test_the_flag_is_day_when_it_is_unset_and_when_it_is_empty(monkeypatch) -> None:
    monkeypatch.delenv(alpaca.ORDER_TIF_ENV, raising=False)
    assert alpaca.order_time_in_force() == "day"
    monkeypatch.setenv(alpaca.ORDER_TIF_ENV, "")
    assert alpaca.order_time_in_force() == "day"
    monkeypatch.setenv(alpaca.ORDER_TIF_ENV, "  ")
    assert alpaca.order_time_in_force() == "day"
    monkeypatch.setenv(alpaca.ORDER_TIF_ENV, "OPG")
    assert alpaca.order_time_in_force() == "opg"


def test_a_value_the_broker_does_not_understand_stops_the_run_first(
    monkeypatch,
) -> None:
    with pytest.raises(ValueError, match="EFB_ORDER_TIF"):
        alpaca.order_time_in_force({alpaca.ORDER_TIF_ENV: "moo"})
    # And it is read before the first leg, so nothing is sent under a typo.
    monkeypatch.setenv(alpaca.ORDER_TIF_ENV, "moo")
    client = _Client()
    with pytest.raises(ValueError, match="EFB_ORDER_TIF"):
        alpaca.submit_market_orders(
            _book(),
            client,
            PRICES,
            close="2026-10-22",
            throttle=alpaca.Throttle(0),
            now=BEFORE_CUTOFF,
        )
    assert client.requests == []


def test_the_flag_unset_sends_todays_orders_byte_for_byte(monkeypatch) -> None:
    """Unset is not "a different TIF": it is the same requests, field for field."""
    monkeypatch.delenv(alpaca.ORDER_TIF_ENV, raising=False)
    client = _Client()
    alpaca.submit_market_orders(
        _book(),
        client,
        PRICES,
        close="2026-10-22",
        throttle=alpaca.Throttle(0),
        now=BEFORE_CUTOFF,
    )
    assert _tifs(client) == ["day", "day", "day", "day"]
    # The open long is the notional leg the loop has always sent, and the three
    # quantity legs are unchanged: the flag touched nothing.
    open_long, open_short, close_long, close_short = client.requests
    assert open_long.notional == pytest.approx(50_000.0)
    assert open_long.qty is None
    assert open_short.notional is None
    assert open_short.qty == pytest.approx(500.0)
    assert close_long.qty == pytest.approx(250.0)
    assert close_short.qty == pytest.approx(250.0)
    # The same four tickets, pinned: unset must not move an id either, because the
    # id is what makes a rerun resolve instead of duplicate.
    assert [request.client_order_id for request in client.requests] == [
        "efb-2026-10-22-AAA-B-a1c8759a4698",
        "efb-2026-10-22-BBB-S-a55956eedf22",
        "efb-2026-10-22-CCC-S-383a0af727f1",
        "efb-2026-10-22-DDD-B-b6d4e56ebf48",
    ]


def test_the_flag_set_sends_every_leg_at_the_open(monkeypatch) -> None:
    """`opg` on every leg, and the notional open becomes a whole-share quantity.

    Alpaca refuses `notional` with any TIF but `day` ("notional ... Can only work
    for market order types and day for time in force"), so the open leg has to be
    sized in shares. It is rounded down at the reference price, so the flag can
    only ever buy less than the notional the run sized.
    """
    monkeypatch.setenv(alpaca.ORDER_TIF_ENV, "opg")
    client = _Client()
    fills = alpaca.submit_market_orders(
        _book(),
        client,
        PRICES,
        close="2026-10-22",
        throttle=alpaca.Throttle(0),
        now=BEFORE_CUTOFF,
    )
    assert _tifs(client) == ["opg", "opg", "opg", "opg"]
    open_long = client.requests[0]
    assert open_long.notional is None
    assert open_long.qty == pytest.approx(500.0)
    assert [fill.detail for fill in fills] == [""] * 4


def test_an_open_that_rounds_to_no_whole_share_is_skipped_not_resent(
    monkeypatch,
) -> None:
    """A $40 open at $100 cannot be sent as shares, and must not go out notional."""
    monkeypatch.setenv(alpaca.ORDER_TIF_ENV, "opg")
    client = _Client()
    fills = alpaca.submit_market_orders(
        [guards.OrderSpec("AAA", 40.0, 40.0)],
        client,
        PRICES,
        close="2026-10-22",
        throttle=alpaca.Throttle(0),
        now=BEFORE_CUTOFF,
    )
    assert client.requests == []
    assert [fill.reason_code for fill in fills] == [alpaca.REASON_QTY_ROUNDS_TO_ZERO]


def test_a_leg_released_past_the_cutoff_falls_back_to_day(monkeypatch) -> None:
    """After 09:28 ET an `opg` submission is refused outright, so it is sent `day`.

    Measured: the broker released RDDT's leg at 09:23 ET on 2026-10-22, so a
    release can land inside the last five minutes of the window. A leg after it is
    a trade taken later in the session rather than a leg the broker throws away,
    and the record says which one happened.
    """
    monkeypatch.setenv(alpaca.ORDER_TIF_ENV, "opg")
    client = _Client()
    fills = alpaca.submit_market_orders(
        _book(),
        client,
        PRICES,
        close="2026-10-22",
        throttle=alpaca.Throttle(0),
        now=AFTER_CUTOFF,
    )
    assert _tifs(client) == ["day", "day", "day", "day"]
    assert all("09:28 ET" in fill.detail for fill in fills)
    # And the notional open is back: the fallback leg is the loop's own order.
    assert client.requests[0].notional == pytest.approx(50_000.0)


def test_the_cutoff_is_on_the_new_york_clock_not_the_utc_one(monkeypatch) -> None:
    """13:20 UTC is 09:20 ET in summer and 08:20 ET in winter: both inside."""
    monkeypatch.setenv(alpaca.ORDER_TIF_ENV, "opg")
    for stamp in ("2026-10-22T13:20:00Z", "2026-12-03T13:20:00Z"):
        client = _Client()
        alpaca.submit_market_orders(
            [guards.OrderSpec("CCC", 25_000.0, -25_000.0)],
            client,
            PRICES,
            close="2026-10-22",
            throttle=alpaca.Throttle(0),
            now=stamp,
        )
        assert _tifs(client) == ["opg"], stamp
    # 13:35 UTC is 09:35 ET in summer and 08:35 ET in winter, so the same UTC
    # minute is on both sides of the cutoff in the two halves of the year.
    for stamp, expected in (
        ("2026-10-22T13:35:00Z", "day"),
        ("2026-12-03T13:35:00Z", "opg"),
    ):
        client = _Client()
        alpaca.submit_market_orders(
            [guards.OrderSpec("CCC", 25_000.0, -25_000.0)],
            client,
            PRICES,
            close="2026-10-22",
            throttle=alpaca.Throttle(0),
            now=stamp,
        )
        assert _tifs(client) == [expected], stamp


def test_a_rerun_resolves_the_brokers_orders_and_sends_nothing(monkeypatch) -> None:
    """The retry path: a leg the broker already holds is resolved, never re-sent.

    The flag decides the TIF of a *new* submission only. A rerun looks every ticket
    up first, so it neither changes nor duplicates an order the broker accepted.
    """
    monkeypatch.setenv(alpaca.ORDER_TIF_ENV, "opg")
    book = _book()
    # The first attempt's tickets, as the broker would hold them.
    first = _Client()
    alpaca.submit_market_orders(
        book,
        first,
        PRICES,
        close="2026-10-22",
        throttle=alpaca.Throttle(0),
        now=BEFORE_CUTOFF,
    )
    existing = {
        request.client_order_id: _Order(f"held-{request.symbol}")
        for request in first.requests
    }
    client = _Client(existing=existing)
    fills = alpaca.submit_market_orders(
        book,
        client,
        PRICES,
        close="2026-10-22",
        throttle=alpaca.Throttle(0),
        now=BEFORE_CUTOFF,
    )
    assert client.requests == []
    assert [fill.resolved for fill in fills] == [True, True, True, True]
    assert [fill.order_id for fill in fills] == [
        "held-AAA",
        "held-BBB",
        "held-CCC",
        "held-DDD",
    ]


def test_the_morning_leaves_the_flag_to_the_environment(monkeypatch) -> None:
    """The morning job passes no TIF of its own: one switch, one place."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "live" / "morning_job.py").read_text()
    assert "time_in_force" not in source
    assert "EFB_ORDER_TIF" not in source
