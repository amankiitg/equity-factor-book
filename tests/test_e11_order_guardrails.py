"""Sprint E11 pre-flip, item 5: a rerun cannot double-submit, and the run paces itself.

Three guardrails, each with one job.

`client_order_id` is deterministic from the close, the ticker and the side. Alpaca
requires it to be unique per account and refuses a repeat, so a rerun of the same
evening is rejected by the broker rather than sent twice. The id is recomputed
from the proposal instead of stored, so a wiped container changes nothing.

Submissions are spaced by a `Throttle`. The trading API allows 200 requests a
minute and this loop also reads assets and polls fills, so the interval is on the
submissions and the ceiling is what it is derived from.

Buying power is checked for the whole run before the first order. Alpaca checks
leg by leg and reduces available buying power by every open order, so a book that
does not fit ends half-built; a failure raises with nothing sent.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from live import alpaca, guards, morning_job

NAV = 1_000_000.0
PRICES = {"AAA": 100.0, "BBB": 100.0}


class _Order:
    def __init__(self, order_id: str) -> None:
        self.id = order_id
        self.status = "accepted"
        self.filled_avg_price = None
        self.filled_qty = None


class _Client:
    def __init__(self, buying_power: str = "1000000", fail: Exception | None = None):
        self.buying_power = buying_power
        self.fail = fail
        self.requests: list[object] = []

    def get_account(self) -> object:
        client = self

        class _Account:
            equity = "1000000"
            id = "paper-account"
            buying_power = client.buying_power

        return _Account()

    def get_asset(self, symbol: str) -> object:
        class _Asset:
            tradable = True
            shortable = True
            easy_to_borrow = True

        return _Asset()

    def submit_order(self, order_data) -> _Order:
        if self.fail is not None:
            raise self.fail
        self.requests.append(order_data)
        return _Order(f"order-{len(self.requests)}")

    def get_order(self, order_id: str) -> _Order:
        order = _Order(order_id)
        order.status = "filled"
        order.filled_avg_price = 100.0
        order.filled_qty = 1.0
        return order


def _specs() -> list[guards.OrderSpec]:
    return [
        guards.OrderSpec("AAA", 50_000.0, 50_000.0),
        guards.OrderSpec("BBB", -50_000.0, -50_000.0),
    ]


def test_the_client_order_id_is_deterministic_from_three_things() -> None:
    first = alpaca.client_order_id("2026-09-25", "AAA", "buy")
    assert first == alpaca.client_order_id("2026-09-25", "AAA", "buy")
    assert first != alpaca.client_order_id("2026-09-28", "AAA", "buy")
    assert first != alpaca.client_order_id("2026-09-25", "BBB", "buy")
    assert first != alpaca.client_order_id("2026-09-25", "AAA", "sell")
    # Readable at a glance in the broker's order list, and inside the 128
    # character maximum for a very long symbol.
    assert first.startswith("efb-2026-09-25-AAA-B-")
    assert len(alpaca.client_order_id("2026-09-25", "X" * 60, "buy")) <= 128


def test_every_submitted_order_carries_its_deterministic_id() -> None:
    client = _Client()
    alpaca.submit_market_orders(
        _specs(), client, PRICES, close="2026-09-25", throttle=alpaca.Throttle(0)
    )
    tickets = [str(request.client_order_id) for request in client.requests]
    assert tickets == [
        alpaca.client_order_id("2026-09-25", "AAA", "buy"),
        alpaca.client_order_id("2026-09-25", "BBB", "sell"),
    ]
    assert len(set(tickets)) == 2


def test_the_throttle_spaces_the_submissions() -> None:
    ticks = iter([10.0, 10.05, 10.4])
    slept: list[float] = []
    throttle = alpaca.Throttle(
        interval=0.35, clock=lambda: next(ticks), sleep=slept.append
    )
    assert throttle.wait() == 0.0  # nothing sent yet, so nothing to wait for
    assert slept == []
    assert throttle.wait() == pytest.approx(0.30, abs=1e-9)
    assert throttle.wait() == pytest.approx(0.30, abs=1e-9)
    assert slept == pytest.approx([0.30, 0.30], abs=1e-9)
    # And the default interval is under the documented rate limit.
    assert 60.0 / alpaca.MIN_SUBMIT_INTERVAL_SECS <= alpaca.RATE_LIMIT_PER_MINUTE


def test_buying_power_is_read_and_never_faked() -> None:
    assert alpaca.get_buying_power(_Client(buying_power="250000.5")) == 250_000.5
    for bad in ("nan", "-1"):
        with pytest.raises(RuntimeError, match="buying power"):
            alpaca.get_buying_power(_Client(buying_power=bad))


def test_the_run_is_refused_when_the_book_does_not_fit() -> None:
    specs = _specs()  # 100,000 of traded notional
    assert alpaca.check_buying_power(_Client(buying_power="100000"), specs) == 100_000.0
    with pytest.raises(RuntimeError) as err:
        alpaca.check_buying_power(_Client(buying_power="99999"), specs)
    assert "100,000 of traded notional" in str(err.value)
    assert "99,999 of buying power" in str(err.value)


@pytest.fixture
def _no_state_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(morning_job.state, "write_positions", lambda *a, **k: None)
    monkeypatch.setattr(morning_job, "_write_execution_log", lambda *a, **k: None)


def test_a_live_run_with_too_little_buying_power_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, _no_state_writes: None
) -> None:
    proposal = pd.DataFrame(
        {"ticker": ["AAA", "BBB"], "weight": [0.05, -0.05], "alpha": [0.0, 0.0]}
    )
    client = _Client(buying_power="1000")
    monkeypatch.setattr(morning_job, "load_proposal", lambda *a, **k: proposal)
    monkeypatch.setattr(morning_job, "connect", lambda dry_run: client)
    monkeypatch.setattr(morning_job, "_close_prices", lambda *a, **k: PRICES)

    with pytest.raises(RuntimeError, match="buying power"):
        morning_job.run_morning("2026-09-25", nav=NAV, dry_run=False)

    assert client.requests == [], "an order was sent despite the refusal"


def test_a_dry_run_records_the_ticket_the_live_evening_will_send(
    monkeypatch: pytest.MonkeyPatch, _no_state_writes: None
) -> None:
    """The rerun-proof id is visible before anything is ever sent."""
    proposal = pd.DataFrame(
        {"ticker": ["AAA", "BBB"], "weight": [0.05, -0.05], "alpha": [0.0, 0.0]}
    )
    monkeypatch.setattr(morning_job, "load_proposal", lambda *a, **k: proposal)
    monkeypatch.setattr(morning_job, "_close_prices", lambda *a, **k: PRICES)

    records = morning_job.submit_orders(
        [
            guards.OrderSpec("AAA", 50_000.0, 50_000.0),
            guards.OrderSpec("BBB", -50_000.0, -50_000.0),
        ],
        client=None,
        dry_run=True,
        close="2026-09-25",
    )
    assert list(records["client_order_id"]) == [
        alpaca.client_order_id("2026-09-25", "AAA", "buy"),
        alpaca.client_order_id("2026-09-25", "BBB", "sell"),
    ]
    assert math.isfinite(float(records["intended_notional"].abs().sum()))
