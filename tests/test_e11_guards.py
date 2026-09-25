"""Sprint E11, Task 5: the two fail-safe guards, each proven to fire.

Guard 1, the position-size cap, is NAV-relative. Guard 2, the
traded-notional brake, is absolute. A guard that cannot fire is not a
guard, so each test trips one and asserts the rejection reason.
"""

from __future__ import annotations

import pytest

from live import guards
from live.guards import OrderSpec


def test_position_cap_rejects_an_oversized_destination() -> None:
    nav = 100_000.0
    order = OrderSpec("AAA", 0.5 * nav, 0.5 * nav)
    result = guards.apply_guards([order], nav)
    assert result[0].status == guards.REJECTED_CAP


def test_position_cap_accepts_the_boundary() -> None:
    nav = 100_000.0
    assert guards.position_cap(0.10 * nav, nav) is False
    assert guards.position_cap(0.1001 * nav, nav) is True


def test_position_cap_scales_with_nav() -> None:
    # the same dollar position is oversized at a small NAV and fine at a large one
    assert guards.position_cap(50_000.0, nav=100_000.0) is True  # 0.5 > 0.10
    assert guards.position_cap(50_000.0, nav=1_000_000.0) is False  # 0.05 < 0.10


def test_a_ten_times_order_on_the_largest_target_trips_the_cap() -> None:
    """Guard 1 re-derived in Part 5 against the 150-name book's final weights.

    The largest final position across the closes the loop can re-price is
    2026-09-18 MRNA at $62,615 of the $1,000,000 paper NAV, read from
    `live/proposals/proposal_2026-09-18.parquet`. The 2026-09-03 close is not in
    the set: the panel has no close price for APH that day, and the run now
    refuses to size a book on such a name.
    """
    nav = 1_000_000.0
    largest = 0.062615
    assert guards.position_cap(largest * nav, nav) is False
    assert guards.position_cap(10 * largest * nav, nav) is True
    # 1.597x headroom, and the cap clears the book's own close-to-close movement
    # of that weight (0.915 pp) with room to spare
    assert guards.MAX_POSITION_PCT_OF_NAV / largest == pytest.approx(1.5971, abs=1e-4)
    movement = abs(0.053463 - 0.062615)
    assert movement == pytest.approx(0.009152, abs=1e-6)
    assert guards.MAX_POSITION_PCT_OF_NAV - largest > movement


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
