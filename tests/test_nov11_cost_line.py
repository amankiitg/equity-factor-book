"""The morning compares the fills against the half of the expectation they can pay."""

from __future__ import annotations

from live import notify


def message(**overrides: object) -> str:
    fills = {
        "trade_date": "2026-10-07",
        "n_orders": 199,
        "n_filled": 197,
        "n_unfilled": 2,
        "not_sent": 0,
        "realized_cost_bps": 10.23,
        "expected_cost_bps": 14.22,
        "expected_trading_bps": 5.89,
        "expected_borrow_bps": 8.33,
        "unfilled": [],
        "not_sent_lines": [],
        "unread": [],
    }
    fills.update(overrides)
    return notify.fills_message(target_close="2026-10-07", fills=fills, store="x")


def test_the_realized_figure_is_compared_against_the_trading_half():
    text = message()
    # 2026-10-07 as it was sent: "against 14.22 bps expected", where 14.22 was the
    # trading half plus a borrow no fill price pays.
    assert "Realized cost: 10.23 bps of NAV against 5.89 bps of trading cost" in text
    assert "for the same one session" in text
    assert "14.22 bps total adds 8.33 bps of borrow" in text
    assert "against 14.22 bps expected" not in text


def test_the_borrow_is_stated_rather_than_dropped():
    text = message()
    assert "8.33 bps of borrow" in text
    assert "no fill price pays" in text


def test_a_document_without_the_split_keeps_the_old_sentence():
    # A snapshot published before the split existed still gets a line, and it says
    # which figure it is rather than inventing a half.
    text = message(expected_trading_bps=None, expected_borrow_bps=None)
    assert "against 14.22 bps expected" in text


def test_no_expectation_at_all_prints_no_comparison():
    text = message(
        expected_cost_bps=None, expected_trading_bps=None, expected_borrow_bps=None
    )
    assert "Realized cost: 10.23 bps of NAV." in text
