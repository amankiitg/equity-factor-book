"""Sprint E11, Task 5: the two fail-safe guards, each proven to fire.

Guard 1, the position-size cap, is NAV-relative. Guard 2, the
traded-notional brake, is absolute. A guard that cannot fire is not a
guard, so each test trips one and asserts the rejection reason.
"""

from __future__ import annotations

from live import guards
from live.guards import OrderSpec


def test_position_cap_rejects_an_oversized_destination() -> None:
    nav = 100_000.0
    order = OrderSpec("AAA", 0.5 * nav, 0.5 * nav)
    result = guards.apply_guards([order], nav)
    assert result[0].status == guards.REJECTED_CAP


def test_position_cap_accepts_the_boundary() -> None:
    nav = 100_000.0
    assert guards.position_cap(0.40 * nav, nav) is False
    assert guards.position_cap(0.4001 * nav, nav) is True


def test_position_cap_scales_with_nav() -> None:
    # the same dollar position is oversized at a small NAV and fine at a large one
    assert guards.position_cap(50_000.0, nav=100_000.0) is True
    assert guards.position_cap(50_000.0, nav=200_000.0) is False


def test_brake_accumulates_across_orders() -> None:
    nav = 100_000.0
    limit = 16_000.0
    orders = [
        OrderSpec("AAA", 10_000.0, 10_000.0),
        OrderSpec("BBB", 10_000.0, 10_000.0),
    ]
    result = guards.apply_guards(orders, nav, max_traded=limit)
    assert result[0].status == guards.PASSED
    assert result[1].status == guards.REJECTED_TRADED_NOTIONAL


def test_brake_is_absolute_and_independent_of_nav() -> None:
    # the brake constant itself does not move with NAV; for the 1,000,000
    # book it is one full flip, 2 x NAV = 2,000,000
    assert guards.MAX_TRADED_NOTIONAL_PER_RUN == 2_000_000.0
    # at any NAV, a single leg under the brake passes the brake guard
    assert guards.traded_notional_brake(0.0, 900_000.0) is False
    assert guards.traded_notional_brake(1_900_000.0, 200_000.0) is True


def test_a_rejected_order_never_reaches_submit() -> None:
    nav = 100_000.0
    orders = [
        OrderSpec("AAA", 0.5 * nav, 0.5 * nav),  # cap rejects
        OrderSpec("BBB", 100.0, 100.0),  # fine
    ]
    result = guards.apply_guards(orders, nav)
    assert [order.status for order in result] == [
        guards.REJECTED_CAP,
        guards.PASSED,
    ]
