"""The order-time quote: captured at submission, stored only when the schema has it.

`realized_cost_bps` measures a fill against the close the book was *sized* from, and
the loop submits about two hours later, so the market's move between the two is inside
that number. These columns record what the order actually saw - bid, ask, mid and when
they were read - so the measured cost can be split into the overnight move, the drift
to submission, and the execution.

Two properties are pinned here. The capture is best effort and can never stop the book:
a quote read that fails records an absent quote, not a zero. And the columns are
written only when the database has them, because a write that named a column a
database does not have would fail the whole order log - which is why the migration is
prepared and applied by hand rather than assumed.
"""

from __future__ import annotations

import pandas as pd
import pytest

from live import alpaca, guards, morning_job, store


class _Quote:
    def __init__(self, bid: float, ask: float) -> None:
        self.bid_price = bid
        self.ask_price = ask


class _Reader:
    def __init__(self, quotes: dict[str, _Quote]) -> None:
        self.quotes = quotes
        self.requests = 0

    def get_stock_latest_quote(self, request: object) -> dict[str, _Quote]:
        self.requests += 1
        return self.quotes


def test_the_mid_is_computed_from_the_two_sides_not_read_from_the_vendor() -> None:
    reader = _Reader({"AAA": _Quote(99.98, 100.02), "BBB": _Quote(50.0, 50.10)})

    quotes = alpaca.latest_quotes(["AAA", "BBB", "AAA"], client=reader)

    # One request for the whole book, and the duplicates collapse.
    assert reader.requests == 1
    assert quotes["AAA"]["mid"] == pytest.approx(100.0)
    assert quotes["BBB"]["mid"] == pytest.approx(50.05)
    assert quotes["AAA"]["bid"] == pytest.approx(99.98)
    assert quotes["AAA"]["quoted_at"]


def test_a_symbol_with_no_usable_quote_is_absent_rather_than_zero() -> None:
    reader = _Reader({"AAA": _Quote(99.98, 100.02), "BBB": _Quote(0.0, 0.0)})

    quotes = alpaca.latest_quotes(["AAA", "BBB", "CCC"], client=reader)

    assert set(quotes) == {"AAA"}


def _submit(client, quotes=None):
    order = guards.OrderSpec("AAA", 1_000.0, 1_000.0)
    return alpaca.submit_market_orders(
        [order],
        client,
        {"AAA": 100.0},
        close="2026-10-22",
        throttle=alpaca.Throttle(0),
        quote_client=_Reader(quotes) if quotes is not None else False,
    )


def test_the_submission_records_the_quote_it_saw() -> None:
    """The leg carries the mid, and the caller decides whether it is writable."""
    fills = _submit(_FakeClient(), {"AAA": _Quote(99.98, 100.02)})

    assert len(fills) == 1
    assert fills[0].submitted_bid == pytest.approx(99.98)
    assert fills[0].submitted_ask == pytest.approx(100.02)
    assert fills[0].submitted_mid == pytest.approx(100.0)
    assert fills[0].quoted_at


def test_a_failed_quote_read_leaves_the_leg_with_no_quote_and_still_trades() -> None:
    class Broken:
        def get_stock_latest_quote(self, request: object) -> dict[str, _Quote]:
            raise RuntimeError("the quote endpoint is down")

    order = guards.OrderSpec("AAA", 1_000.0, 1_000.0)
    fills = alpaca.submit_market_orders(
        [order],
        _FakeClient(),
        {"AAA": 100.0},
        close="2026-10-22",
        throttle=alpaca.Throttle(0),
        quote_client=Broken(),
    )

    assert len(fills) == 1
    assert fills[0].status
    assert fills[0].submitted_mid is None


def test_no_quote_client_reads_no_quotes() -> None:
    """Passing `False` is how a caller says "do not read a quote at all"."""
    fills = _submit(_FakeClient())

    assert len(fills) == 1
    assert fills[0].submitted_mid is None


def test_the_quote_columns_are_written_only_when_the_schema_has_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The migration is prepared, not applied.

    The log must not name a column the database does not have, or one reporting field
    would fail the whole order write.
    """
    catalog = pd.DataFrame(
        {
            "table_name": ["orders", "orders"],
            "column_name": ["ticker", "broker_order_id"],
        }
    )
    monkeypatch.setattr(store, "select_catalog", lambda: catalog)
    assert morning_job.order_quote_columns() == ()

    catalog = pd.DataFrame(
        {
            "table_name": ["orders"] * 5,
            "column_name": ["ticker", *morning_job.QUOTE_COLUMNS],
        }
    )
    monkeypatch.setattr(store, "select_catalog", lambda: catalog)
    assert morning_job.order_quote_columns() == morning_job.QUOTE_COLUMNS


def test_a_local_store_reports_no_quote_columns() -> None:
    """No catalogue means no columns: the local parquet store is not a database."""
    assert morning_job.order_quote_columns() == ()


class _FakeClient:
    """The smallest broker that accepts an order and reports it accepted."""

    def __init__(self) -> None:
        self.sent: list[object] = []

    def get_order(self, order_id: str) -> object:  # pragma: no cover - never called
        raise AssertionError("submit_market_orders must not poll for a fill")

    def get_orders(self, request: object) -> list[object]:
        return []

    def get_asset(self, symbol: str) -> object:
        class _Asset:
            shortable = True
            easy_to_borrow = True
            tradable = True
            fractionable = True

        return _Asset()

    def submit_order(self, order_data: object) -> object:
        self.sent.append(order_data)

        class _Submitted:
            id = "order-1"
            status = "ACCEPTED"
            filled_avg_price = None
            filled_qty = None

        return _Submitted()
