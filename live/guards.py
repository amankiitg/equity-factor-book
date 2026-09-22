"""Sprint E11: the two fail-safe guards of the morning job.

Ported from the v8.x loop and named. Guard 1, the position-size cap, is
NAV-relative: it scales with the book. Guard 2, the traded-notional
brake, is absolute: it does not. They use different units on purpose, so
a book that outgrows the cap's reach is still caught by the brake.

An order must pass both guards or it is rejected and never submitted. A
guard that cannot fire is not a guard, so each one has a test that trips
it and asserts the rejection.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

MAX_POSITION_PCT_OF_NAV: float = 0.40
# The absolute throughput brake, re-derived for the $1,000,000 paper book.
# One full flip of the gross-1 book is 2 x NAV = 2,000,000, so the brake
# admits a full flip while still catching a fat-finger order at ten times
# the book (10,000,000). At the previous 100k book the same arithmetic gave
# 200,000; NAV is now a 1,000,000 design parameter, so the brake is 2,000,000.
MAX_TRADED_NOTIONAL_PER_RUN: float = float(
    os.environ.get("MAX_TRADED_NOTIONAL_PER_RUN", "2000000")
)

PASSED = "PASSED"
REJECTED_CAP = "REJECTED_CAP"
REJECTED_TRADED_NOTIONAL = "REJECTED_TRADED_NOTIONAL"


@dataclass(frozen=True)
class OrderSpec:
    """One target position and the notional its trade would move.

    `target_notional` is signed: positive long, negative short. `traded`
    is the absolute dollar notional the run would trade to reach it.
    """

    ticker: str
    target_notional: float
    traded_notional: float
    status: str = PASSED


def position_cap(target_notional: float, nav: float) -> bool:
    """Guard 1 trips when a destination position exceeds the NAV-relative cap."""
    cap_notional = MAX_POSITION_PCT_OF_NAV * nav
    return abs(target_notional) > cap_notional


def traded_notional_brake(
    traded_so_far: float, leg_traded: float, limit: float = MAX_TRADED_NOTIONAL_PER_RUN
) -> bool:
    """Guard 2 trips when a leg would push the run total over the absolute brake."""
    return traded_so_far + leg_traded > limit


def apply_guards(
    orders: list[OrderSpec],
    nav: float,
    max_traded: float | None = None,
) -> list[OrderSpec]:
    """Apply both guards in order; a rejected order is never submitted.

    Guard 1 checks the destination position against the cap; Guard 2
    accumulates the run's traded notional against the brake. The brake is
    absolute and independent of NAV, so a large book is still caught.
    """
    limit = MAX_TRADED_NOTIONAL_PER_RUN if max_traded is None else max_traded
    results: list[OrderSpec] = []
    traded_so_far = 0.0
    for order in orders:
        if order.status != PASSED:
            results.append(order)
            continue
        if position_cap(order.target_notional, nav):
            results.append(
                OrderSpec(
                    order.ticker,
                    order.target_notional,
                    order.traded_notional,
                    REJECTED_CAP,
                )
            )
            continue
        if traded_notional_brake(traded_so_far, order.traded_notional, limit):
            results.append(
                OrderSpec(
                    order.ticker,
                    order.target_notional,
                    order.traded_notional,
                    REJECTED_TRADED_NOTIONAL,
                )
            )
            continue
        traded_so_far += order.traded_notional
        results.append(order)
    return results
