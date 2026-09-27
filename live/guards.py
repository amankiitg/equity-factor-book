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

MAX_POSITION_PCT_OF_NAV: float = 0.10
# Guard 1, re-derived against the chosen share-only construction's final
# (quantized) weights, sized from the largest final position across every close
# the loop can re-price, not one close, because the book rebalances daily:
# 2026-09-18 MRNA $62,615 (6.2615% of NAV) and 2026-09-21 MU $53,463 (5.3463%).
# The 2026-09-03 close cannot be re-priced: the panel has no close for APH that
# day (NaN on 2026-08-28, 09-01, 09-02 and 09-03, and its price halves on
# 09-04), and `usable_prices` now refuses to size a book on such a name. The
# largest legitimate target is therefore 6.2615% of NAV, and ten times it is
# 62.6%. A cap of 0.10 ($100,000 at the $1,000,000 NAV) clears that target with
# 1.597x headroom (0.0626 -> 0.10) and still trips a 10x order on the largest
# name (0.626 > 0.10). It is NAV-relative, so it scales with the book.
#
# Headroom against the book's own movement: the largest final weight moved
# 0.915 pp ($9,152) from the 2026-09-18 close to the 2026-09-21 close, while the
# cap clears the largest weight by 3.74 pp, so the cap is not inside the daily
# movement. Re-checked against the live distribution before each run.
#
# The absolute throughput brake, re-derived for the $1,000,000 paper book.
# One full flip of the gross-1 book is 2 x NAV = 2,000,000, so the brake
# admits a full flip while still catching a fat-finger order at ten times
# the book (10,000,000). At the previous 100k book the same arithmetic gave
# 200,000; NAV is now a 1,000,000 design parameter, so the brake is 2,000,000.
MAX_TRADED_NOTIONAL_PER_RUN: float = float(
    os.environ.get("MAX_TRADED_NOTIONAL_PER_RUN", "2000000")
)

# The establishment day's ceiling, in units of NAV of gross.
#
# The book is renormalized to gross 1.0 after names are dropped, so building it
# from flat trades exactly one book's gross. Day one is not a rebalance: it is the
# creation of the book, and the throughput brake is the wrong instrument for it.
# The ceiling is the book itself, which is a real bound (a corrupted order set
# ten times the book still trips it) and exactly what the owner's rule says:
# "allowed to trade up to the full book, the daily brake applies from the second
# trading day". Guard 1, the position cap, applies on every day including this
# one, so no single name can run away on day one either.
ESTABLISHMENT_GROSS: float = 1.0

PASSED = "PASSED"
REJECTED_CAP = "REJECTED_CAP"
REJECTED_TRADED_NOTIONAL = "REJECTED_TRADED_NOTIONAL"


@dataclass(frozen=True)
class OrderSpec:
    """One order: the position it targets and the signed change it submits.

    `target_notional` is the signed destination position, which is what guard 1
    caps; a name being closed has a target of zero. `trade_notional` is the
    signed change the order submits, `target - held`: positive buys, negative
    sells, and it is what the broker is actually sent. `traded_notional` is its
    absolute value, which is what the throughput brake accumulates, kept as a
    property so the sign and the size can never disagree.

    Both numbers are needed. Sizing the order from the target would, from a held
    book, buy the whole position again on an increase and turn a cut into a
    same-direction order on a decrease.
    """

    ticker: str
    target_notional: float
    trade_notional: float
    status: str = PASSED

    @property
    def traded_notional(self) -> float:
        """The absolute dollars this order moves, for the throughput brake."""
        return abs(self.trade_notional)


def position_cap(target_notional: float, nav: float) -> bool:
    """Guard 1 trips when a destination position exceeds the NAV-relative cap."""
    cap_notional = MAX_POSITION_PCT_OF_NAV * nav
    return abs(target_notional) > cap_notional


def traded_notional_brake(
    traded_so_far: float, leg_traded: float, limit: float = MAX_TRADED_NOTIONAL_PER_RUN
) -> bool:
    """Guard 2 trips when a leg would push the run total over the absolute brake."""
    return traded_so_far + leg_traded > limit


def traded_notional_limit(
    nav: float,
    *,
    establishment: bool,
    max_traded: float | None = None,
) -> tuple[float, str]:
    """The brake's limit for this run, and the basis it was chosen on.

    Two days, two instruments. On the establishment day the ceiling is the book's
    own gross, because the run is creating the book rather than rebalancing one,
    and the basis says so. From the second trading day the absolute brake applies:
    the account already holds a book, so the question is how much a single evening
    may move, which is what a fat-finger limit is for.
    """
    if establishment:
        return establishment_limit(nav), (
            "establishment: the first trading day, so the run may trade up to the "
            f"full book ({ESTABLISHMENT_GROSS:g} NAV of gross); the daily brake of "
            f"{MAX_TRADED_NOTIONAL_PER_RUN:,.0f} starts on the second trading day"
        )
    limit = MAX_TRADED_NOTIONAL_PER_RUN if max_traded is None else max_traded
    return limit, (
        f"daily brake {limit:,.0f}: the account already holds a book, so this is "
        "a rebalance and the absolute throughput limit applies"
    )


def establishment_limit(nav: float, gross: float = ESTABLISHMENT_GROSS) -> float:
    """The most an establishment run may trade: the book itself, in dollars."""
    return abs(float(gross)) * float(nav)


def apply_guards(
    orders: list[OrderSpec],
    nav: float,
    max_traded: float | None = None,
    establishment: bool = False,
) -> list[OrderSpec]:
    """Apply both guards in order; a rejected order is never submitted.

    Guard 1 checks the destination position against the cap; Guard 2
    accumulates the run's traded notional against the brake. The brake is
    absolute and independent of NAV, so a large book is still caught — except on
    the establishment day, where its place is taken by the book's own gross
    (`traded_notional_limit`), because that day creates the book rather than
    rebalancing it.
    """
    limit, _basis = traded_notional_limit(
        nav, establishment=establishment, max_traded=max_traded
    )
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
                    order.trade_notional,
                    REJECTED_CAP,
                )
            )
            continue
        if traded_notional_brake(traded_so_far, order.traded_notional, limit):
            results.append(
                OrderSpec(
                    order.ticker,
                    order.target_notional,
                    order.trade_notional,
                    REJECTED_TRADED_NOTIONAL,
                )
            )
            continue
        traded_so_far += order.traded_notional
        results.append(order)
    return results
