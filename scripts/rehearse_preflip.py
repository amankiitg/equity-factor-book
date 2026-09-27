"""Rehearse two trading days against a fake broker that holds positions.

Day one establishes the book from flat. Day two rebalances it: some names
increased, some decreased, one reversed from long to short, one removed and one
short covered. The transcript shows that each order is exactly the signed change
(`target - held`), that the removed name is closed to zero, and that rerunning day
two, with the broker already holding the new book, submits nothing new.

Run it with `.venv/bin/python scripts/rehearse_preflip.py`. Nothing here touches a
network, a key or a store: the broker is an in-process object and the proposal,
the close prices, the state writer and the execution log are all replaced.
"""

from __future__ import annotations

import os
import sys
from typing import Any
from unittest.mock import patch

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# No pacing between fake submissions; the real interval is a rate limit for a
# network that is not here.
os.environ.setdefault("EFB_MIN_SUBMIT_INTERVAL_SECS", "0")

from live import alpaca, morning_job  # noqa: E402 - after the env line above

NAV = 1_000_000.0
PRICES = {"AAA": 100.0, "BBB": 50.0, "CCC": 200.0, "DDD": 25.0, "FFF": 40.0}

# Day one: from flat, five names, four long and one short.
DAY_ONE = {"AAA": 0.08, "BBB": 0.08, "CCC": 0.08, "DDD": 0.08, "FFF": -0.08}
# Day two: AAA up, BBB down, CCC reversed, DDD removed, FFF half covered.
DAY_TWO = {"AAA": 0.10, "BBB": 0.04, "CCC": -0.06, "FFF": -0.02}


class _FakeOrder:
    def __init__(self, record: dict) -> None:
        self.id = record["id"]
        self.status = record["status"]
        self.filled_qty = record["filled_qty"]
        self.filled_avg_price = record["filled_avg_price"]


class FakeBroker:
    """A broker that holds positions, fills every order and refuses a repeat id."""

    def __init__(self, prices: dict[str, float], nav: float = NAV) -> None:
        self.prices = dict(prices)
        self.holdings: dict[str, float] = {}
        self.orders: dict[str, dict] = {}
        self.submitted: list[dict] = []
        self.equity = nav
        self.buying_power = nav

    def get_account(self) -> object:
        broker = self

        class _Account:
            equity = broker.equity
            buying_power = broker.buying_power
            id = "fake-paper-account"

        return _Account()

    def get_asset(self, symbol: str) -> object:
        class _Asset:
            tradable = True
            shortable = True
            easy_to_borrow = True

        return _Asset()

    def get_all_positions(self) -> list[object]:
        class _Position:
            def __init__(self, symbol: str, value: float) -> None:
                self.symbol = symbol
                self.market_value = str(abs(value))
                self.side = "long" if value >= 0 else "short"

        return [
            _Position(symbol, value)
            for symbol, value in sorted(self.holdings.items())
            if abs(value) > 1e-9
        ]

    def get_order_by_client_id(self, ticket: str) -> _FakeOrder | None:
        record = self.orders.get(ticket)
        return None if record is None else _FakeOrder(record)

    def get_order(self, order_id: str) -> _FakeOrder:
        for record in self.orders.values():
            if record["id"] == order_id:
                return _FakeOrder(record)
        raise KeyError(order_id)

    def submit_order(self, order_data: Any) -> _FakeOrder:
        ticket = str(getattr(order_data, "client_order_id", ""))
        if ticket in self.orders:
            raise RuntimeError(f"the broker already holds client_order_id {ticket}")
        symbol = str(order_data.symbol)
        price = self.prices[symbol]
        side = str(getattr(getattr(order_data, "side", None), "value", ""))
        notional = getattr(order_data, "notional", None)
        if notional is not None:
            amount = float(notional)
            qty = amount / price
        else:
            qty = float(order_data.qty)
            amount = qty * price
        signed = amount if side == "buy" else -amount
        self.holdings[symbol] = self.holdings.get(symbol, 0.0) + signed
        record = {
            "id": f"fake-{len(self.orders) + 1}",
            "client_order_id": ticket,
            "status": "filled",
            "filled_qty": qty,
            "filled_avg_price": price,
            "symbol": symbol,
            "side": side,
            "signed_notional": signed,
        }
        self.orders[ticket] = record
        self.submitted.append(record)
        return _FakeOrder(record)


def _proposal(weights: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": list(weights),
            "weight": [weights[name] for name in weights],
            "alpha": 0.0,
        }
    )


def run_day(
    as_of: str, weights: dict[str, float], broker: FakeBroker
) -> tuple[dict[str, float], dict, pd.DataFrame]:
    """One morning: read the broker, build and submit the deltas, return the log."""
    captured: dict[str, pd.DataFrame] = {}

    def _capture(day: str, records: pd.DataFrame) -> None:
        captured[day] = records

    proposal = _proposal(weights)
    with (
        patch.object(morning_job, "load_proposal", lambda *a, **k: proposal),
        patch.object(morning_job, "connect", lambda dry_run: broker),
        patch.object(morning_job, "_close_prices", lambda *a, **k: dict(PRICES)),
        patch.object(morning_job.state, "write_positions", lambda *a, **k: None),
        patch.object(morning_job, "_write_execution_log", _capture),
    ):
        held = alpaca.get_positions(broker, dry_run=False)
        summary = morning_job.run_morning(
            as_of,
            nav=NAV,
            dry_run=False,
            positions=held,
            establishment=not held,
        )
    return held, summary, captured[as_of]


def _nonzero(holdings: dict[str, float]) -> dict[str, float]:
    """The broker's book with flat names dropped, for a readable line."""
    return {
        name: value for name, value in sorted(holdings.items()) if abs(value) > 1e-9
    }


def main() -> int:
    broker = FakeBroker(PRICES)
    print("=== EFB pre-flip rehearsal: two trading days, fake broker ===")
    print(f"NAV {NAV:,.0f}; prices {PRICES}")

    print("\n--- DAY 1 (2026-09-25): account flat, establishes from zero ---")
    held, summary, records = run_day("2026-09-25", DAY_ONE, broker)
    print(
        f"  held {len(held)} name(s); establishment={summary['establishment']}; "
        f"cost label {summary['cost_label']}"
    )
    print("  orders (the whole target, since held is zero):")
    for row in records.itertuples(index=False):
        delta = float(row.intended_notional)
        print(
            f"    {str(row.ticker):<5} {'buy ' if delta >= 0 else 'sell'} "
            f"{delta:>+12,.0f}  target {DAY_ONE[str(row.ticker)] * NAV:>+12,.0f}"
            f"  {row.status}"
        )
    day_one_book = {name: weight * NAV for name, weight in DAY_ONE.items()}
    assert summary["complete"] and summary["orders"] == len(DAY_ONE)
    assert sorted(broker.holdings) == sorted(day_one_book)
    print(
        f"  broker now holds {len(_nonzero(broker.holdings))} name(s): "
        f"{_nonzero(broker.holdings)}"
    )

    print("\n--- DAY 2 (2026-09-28): rebalances the held book ---")
    held, summary, records = run_day("2026-09-28", DAY_TWO, broker)
    print(f"  held {len(held)} name(s); establishment={summary['establishment']}")
    expected = {
        name: DAY_TWO.get(name, 0.0) * NAV - held.get(name, 0.0)
        for name in sorted(set(DAY_TWO) | set(held))
    }
    print(
        f"  {'ticker':<7}{'held':>12}{'target':>12}{'delta':>12}"
        f"{'order':>12}  side  equal"
    )
    ok = True
    for name, delta in expected.items():
        order = records.loc[records["ticker"] == name]
        got = float(order["intended_notional"].iloc[0]) if len(order) else 0.0
        equal = abs(got - delta) < 0.01
        ok = ok and equal
        print(
            f"  {name:<7}{held.get(name, 0.0):>+12,.0f}"
            f"{DAY_TWO.get(name, 0.0) * NAV:>+12,.0f}{delta:>+12,.0f}{got:>+12,.0f}"
            f"  {'buy ' if delta >= 0 else 'sell'} {'yes' if equal else 'NO'}"
        )
    assert ok, "an order was not exactly the delta"
    assert summary["complete"], summary["incomplete_legs"]
    # The removed name is closed: DDD is in the held book and not in the target.
    ddd = records.loc[records["ticker"] == "DDD"]
    assert len(ddd) == 1
    assert float(ddd["intended_notional"].iloc[0]) == -DAY_ONE["DDD"] * NAV
    # The short is covered: FFF goes from -80,000 to -20,000 with a buy.
    fff = float(records.loc[records["ticker"] == "FFF", "intended_notional"].iloc[0])
    assert fff == 60_000.0, fff
    print("  removal: DDD closed to zero; cover: FFF bought back 60,000")
    print(
        f"  broker now holds {len(_nonzero(broker.holdings))} name(s): "
        f"{_nonzero(broker.holdings)}"
    )

    print("\n--- DAY 2 RERUN: the broker already holds the day-2 book ---")
    submitted_before = len(broker.submitted)
    held, summary, records = run_day("2026-09-28", DAY_TWO, broker)
    assert summary["orders"] == 0, summary["orders"]
    assert len(broker.submitted) == submitted_before, "a rerun submitted an order"
    assert summary["complete"]
    print("  orders 0 (nothing new submitted); complete=True")
    print(f"  broker submitted {len(broker.submitted)} order(s) across all three runs")

    print("\nAll checks passed: orders are the deltas, the removed name is closed,")
    print("and rerunning day two submits nothing new.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
