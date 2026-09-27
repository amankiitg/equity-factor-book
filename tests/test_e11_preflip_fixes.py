"""The pre-flip review fixes, tested where each one lives.

An order is the signed change to a name, not the target: the union of the target
book and the book the account holds, each leg `trade = target - held`, the side
from the sign, the size from the absolute value, and a held name absent from the
target closed to zero. A rerun looks every leg's deterministic `client_order_id`
up at the broker and resolves the orders it already holds before submitting
anything. Any leg that is halted, left in an unknown state, refused or rejected
makes the run incomplete, so the day is not filed and the next tick retries.
"""

from __future__ import annotations

import pandas as pd
import pytest

from live import alpaca, guards, morning_job

NAV = 1_000_000.0
PRICES = {"AAA": 100.0, "BBB": 100.0}


def _proposal(weights: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"ticker": list(weights), "weight": [weights[name] for name in weights]}
    )


@pytest.mark.parametrize(
    ("held", "target", "expected_trade"),
    [
        pytest.param({"AAA": 60_000.0}, 0.10, 40_000.0, id="increase"),
        pytest.param({"AAA": 140_000.0}, 0.10, -40_000.0, id="decrease"),
        pytest.param({"AAA": -100_000.0}, 0.05, 150_000.0, id="cover-a-short"),
        pytest.param({"AAA": 100_000.0}, -0.05, -150_000.0, id="long-to-short"),
        pytest.param({"AAA": 80_000.0}, None, -80_000.0, id="removal"),
    ],
)
def test_an_order_is_the_signed_change_over_the_union(
    held: dict[str, float], target: float | None, expected_trade: float
) -> None:
    """Every case the target-as-order bug got wrong, one row each."""
    weights = {} if target is None else {"AAA": target}
    orders = morning_job.target_orders(_proposal(weights), NAV, held)

    assert [order.ticker for order in orders] == ["AAA"], "the union was not built"
    order = orders[0]
    assert order.trade_notional == pytest.approx(expected_trade)
    assert order.traded_notional == pytest.approx(abs(expected_trade))
    # Guard 1 still caps the destination, which is why the target is kept.
    assert order.target_notional == pytest.approx((target or 0.0) * NAV)


def test_holding_the_target_trades_nothing() -> None:
    """A rerun of an unchanged book has no leg to send."""
    orders = morning_job.target_orders(
        _proposal({"AAA": 0.10}), NAV, {"AAA": 100_000.0}
    )
    assert orders == []


def test_a_held_name_absent_from_the_target_is_always_closed() -> None:
    """Even below the usual minimum, a leftover cannot survive the evening."""
    orders = morning_job.target_orders(_proposal({"BBB": 0.10}), NAV, {"AAA": 100.0})
    assert [order.ticker for order in orders] == ["AAA", "BBB"]
    close = {order.ticker: order for order in orders}["AAA"]
    assert close.trade_notional == pytest.approx(-100.0)
    assert close.target_notional == 0.0


class _Asset:
    def __init__(self) -> None:
        self.tradable = True
        self.shortable = True
        self.easy_to_borrow = True


class _Submitted:
    def __init__(self, order_id: str) -> None:
        self.id = order_id
        self.status = "filled"
        self.filled_avg_price = 100.0
        self.filled_qty = 1.0


class _RecordingClient:
    """A broker that records what it was asked to submit."""

    def __init__(self) -> None:
        self.requests: list[object] = []

    def get_account(self) -> object:
        class _Account:
            equity = "1000000"
            buying_power = "1000000"
            id = "paper-account"

        return _Account()

    def get_asset(self, symbol: str) -> _Asset:
        return _Asset()

    def submit_order(self, order_data: object) -> _Submitted:
        self.requests.append(order_data)
        return _Submitted(f"order-{len(self.requests)}")

    def get_order(self, order_id: str) -> _Submitted:
        return _Submitted(order_id)


def _side(request: object) -> str:
    return str(getattr(getattr(request, "side", None), "value", ""))


def test_a_reversal_sells_the_whole_change_and_a_cover_buys_it() -> None:
    """Side from the sign, size from the absolute value of the change."""
    client = _RecordingClient()
    alpaca.submit_market_orders(
        [guards.OrderSpec("AAA", -50_000.0, -150_000.0)],
        client,
        PRICES,
        close="2026-09-25",
        throttle=alpaca.Throttle(0),
    )
    reversal = client.requests[0]
    assert _side(reversal) == "sell"
    assert int(reversal.qty) == 1500  # 150,000 at 100, the change, not the target

    client = _RecordingClient()
    alpaca.submit_market_orders(
        [guards.OrderSpec("AAA", 50_000.0, 150_000.0)],
        client,
        PRICES,
        close="2026-09-25",
        throttle=alpaca.Throttle(0),
    )
    cover = client.requests[0]
    assert _side(cover) == "buy"
    assert float(cover.notional) == pytest.approx(150_000.0)


class _ExistingOrder:
    def __init__(self, status: str = "filled") -> None:
        self.id = "order-existing"
        self.status = status
        self.filled_avg_price = 100.0
        self.filled_qty = 500.0


class _ExistingClient(_RecordingClient):
    """A broker that already holds an order under some deterministic ids."""

    def __init__(self, existing: dict[str, _ExistingOrder]) -> None:
        super().__init__()
        self.existing = existing

    def get_order_by_client_id(self, ticket: str) -> _ExistingOrder | None:
        return self.existing.get(ticket)


def test_a_rerun_resolves_existing_orders_before_submitting_anything() -> None:
    """The id the first attempt sent is looked up, not sent again."""
    first = alpaca.client_order_id("2026-09-25", "AAA", "buy")
    second = alpaca.client_order_id("2026-09-25", "BBB", "buy")
    client = _ExistingClient({first: _ExistingOrder()})

    fills = alpaca.submit_market_orders(
        [
            guards.OrderSpec("AAA", 50_000.0, 50_000.0),
            guards.OrderSpec("BBB", 50_000.0, 50_000.0),
        ],
        client,
        PRICES,
        close="2026-09-25",
        throttle=alpaca.Throttle(0),
    )
    by_ticker = {fill.ticker: fill for fill in fills}
    assert by_ticker["AAA"].resolved is True
    assert by_ticker["AAA"].client_order_id == first
    assert by_ticker["BBB"].resolved is False
    # Only the leg the broker did not hold was submitted.
    assert [request.symbol for request in client.requests] == ["BBB"]

    # A second rerun, with the first leg resolved and the second now filled, has
    # nothing left to send: the lookup covers both.
    client.existing[second] = _ExistingOrder()
    again = alpaca.submit_market_orders(
        [
            guards.OrderSpec("AAA", 50_000.0, 50_000.0),
            guards.OrderSpec("BBB", 50_000.0, 50_000.0),
        ],
        client,
        PRICES,
        close="2026-09-25",
        throttle=alpaca.Throttle(0),
    )
    assert all(fill.resolved for fill in again)
    assert [request.symbol for request in client.requests] == ["BBB"]


def test_a_dry_run_is_complete_and_a_refusal_is_not() -> None:
    dry = pd.DataFrame(
        {"ticker": ["AAA"], "status": ["DRY_RUN"], "reason_code": ["DRY_RUN"]}
    )
    assert morning_job.incomplete_legs(dry) == []

    live = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC", "DDD"],
            "status": ["FILLED", "SKIPPED", "REJECTED_CAP", "TIMEOUT"],
            "reason_code": ["", "ASSET_NOT_SHORTABLE", "REJECTED_CAP", ""],
        }
    )
    legs = morning_job.incomplete_legs(live)
    assert [leg["ticker"] for leg in legs] == ["BBB", "CCC", "DDD"]
    assert {leg["reason_code"] for leg in legs} == {
        "ASSET_NOT_SHORTABLE",
        "REJECTED_CAP",
        "",
    }


def test_a_live_run_with_a_refused_short_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end: the summary says the run is not done, with the leg named."""
    proposal = pd.DataFrame(
        {"ticker": ["AAA", "BBB"], "weight": [0.05, -0.05], "alpha": [0.0, 0.0]}
    )

    class _Refusing(_RecordingClient):
        def get_asset(self, symbol: str) -> _Asset:
            asset = _Asset()
            if symbol == "BBB":
                asset.easy_to_borrow = False
            return asset

    client = _Refusing()
    monkeypatch.setattr(morning_job, "load_proposal", lambda *a, **k: proposal)
    monkeypatch.setattr(morning_job, "connect", lambda dry_run: client)
    monkeypatch.setattr(morning_job, "_close_prices", lambda *a, **k: PRICES)
    monkeypatch.setattr(morning_job.state, "write_positions", lambda *a, **k: None)
    monkeypatch.setattr(morning_job, "_write_execution_log", lambda *a, **k: None)

    summary = morning_job.run_morning("2026-09-25", nav=NAV, dry_run=False)

    assert summary["complete"] is False
    assert [leg["ticker"] for leg in summary["incomplete_legs"]] == ["BBB"]
    assert (
        summary["incomplete_legs"][0]["reason_code"] == alpaca.REASON_NOT_EASY_TO_BORROW
    )
