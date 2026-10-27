"""The cost split separates the overnight move from the execution.

`realized_cost_bps` measures a fill against the close the book was *sized* from, so the
gap between that close and the next open is inside the number. On 2026-10-22 the live
days averaged 10-24 bp of NAV against a research model predicting ~2.5 bp: a comparison
that treats the market's own overnight move as a trading cost, and that this split takes
apart. The arithmetic is small enough to pin exactly.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.cost_split import split

# Both names open 1% above their prior close. Equal dollars each way, one bought and
# one sold: the book is neutral, so the overnight move nets out and a split that
# reported a cost here would be charging the market's drift to the execution.
OPENS = pd.DataFrame(
    {
        "date": ["2026-10-15", "2026-10-15"],
        "ticker": ["AAA", "BBB"],
        "open": [101.0, 101.0],
    }
)
FILLS = pd.DataFrame(
    {
        "trade_date": ["2026-10-15", "2026-10-15"],
        "ticker": ["AAA", "BBB"],
        "intended_notional": [101_000.0, -101_000.0],
        "filled_quantity": [1_000.0, 1_000.0],
        "fill_price": [101.0, 101.0],
        "close_price": [100.0, 100.0],
    }
)


def test_a_fill_at_the_open_is_all_overnight_and_no_execution() -> None:
    rows, unpriced = split(FILLS, OPENS, {"2026-10-15": 1_000_000.0})

    assert unpriced == []
    (row,) = rows
    assert row["n_legs"] == 2
    # Filled exactly at the open, so no leg has any execution: the whole of the gap
    # from the close is the overnight move, and being one buy and one sell of equal
    # dollars it cancels.
    assert row["execution_bp_traded"] == pytest.approx(0.0, abs=1e-9)
    assert row["overnight_bp_traded"] == pytest.approx(0.0, abs=1e-9)
    assert row["total_bp_traded"] == pytest.approx(0.0, abs=1e-9)


def test_the_execution_is_what_the_fill_did_after_the_open() -> None:
    """A buy that pays 10 bp above the open costs 10 bp on the leg, 5 on the day."""
    fills = FILLS.copy()
    fills.loc[0, "fill_price"] = 101.0 * (1 + 0.001)
    rows, _unpriced = split(fills, OPENS, {"2026-10-15": 1_000_000.0})

    (row,) = rows
    # Half the day's dollars are in the leg that paid up, so the day's execution is
    # half the leg's 10 bp.
    # (0.50025 of the dollars, because the leg that paid up is the larger one)
    assert row["execution_bp_traded"] == pytest.approx(5.0, abs=1e-2)
    # The overnight legs no longer cancel exactly either, for the same reason.
    assert row["overnight_bp_traded"] == pytest.approx(0.0, abs=0.1)
    # Total = overnight + execution + (overnight x execution / 1e4): the two are
    # compounding ratios, so the sum is exact only to the cross term - 0.05 bp here,
    # which is why this tolerance is 0.1 and not 1e-9.
    assert row["total_bp_traded"] == pytest.approx(
        row["execution_bp_traded"] + row["overnight_bp_traded"], abs=0.1
    )


def test_the_nav_columns_scale_by_what_traded() -> None:
    rows, _unpriced = split(FILLS, OPENS, {"2026-10-15": 1_000_000.0})

    (row,) = rows
    # $202,000 traded against $1,000,000 of NAV, so a basis point of traded notional is
    # 0.202 of a basis point of NAV.
    assert row["traded_notional"] == pytest.approx(202_000.0)
    assert row["execution_bp_nav"] == pytest.approx(0.0, abs=1e-9)


def test_a_leg_with_no_open_is_named_not_priced_at_zero() -> None:
    opens = OPENS.iloc[[0]]
    rows, unpriced = split(FILLS, opens, {"2026-10-15": 1_000_000.0})

    assert unpriced == ["BBB 2026-10-15"]
    (row,) = rows
    assert row["n_legs"] == 1
    # One leg, one direction: the 1% overnight move is now the day's whole number.
    assert row["overnight_bp_traded"] == pytest.approx(100.0, abs=1e-6)


def test_no_fills_is_no_rows() -> None:
    rows, unpriced = split(pd.DataFrame(), OPENS, {})
    assert rows == []
    assert unpriced == []


def test_a_quoted_leg_splits_into_three_parts_at_the_mid() -> None:
    """With a submission quote the day is four numbers: overnight, drift, execution."""
    quotes = pd.DataFrame(
        {
            "trade_date": ["2026-10-15", "2026-10-15"],
            "ticker": ["AAA", "BBB"],
            "submitted_mid": [102.0, 101.0],
            "quoted_at": ["2026-10-15T14:00:00Z"] * 2,
        }
    )
    fills = FILLS.copy()
    fills.loc[0, "fill_price"] = 102.51  # 50 bp above the mid
    rows, unpriced = split(fills, OPENS, {"2026-10-15": 1_000_000.0}, quotes)

    assert unpriced == []
    (row,) = rows
    assert row["n_quoted"] == 2
    # Both names open at 101 against a 100 close. AAA (bought) saw a mid of 102 and
    # paid 102.51, so it carries all of the drift and all of the execution; BBB's mid
    # is its open, so neither.
    # The two legs' dollars are no longer equal once AAA pays up, so the overnight
    # legs do not cancel exactly: 0.74 bp is what is left of the +/-100 bp pair.
    assert row["overnight_bp_traded"] == pytest.approx(0.74, abs=0.05)
    assert row["drift_bp_traded"] == pytest.approx(49.9, abs=0.5)
    assert row["execution_bp_traded"] == pytest.approx(25.2, abs=0.5)
    # The three compose to the total the store's own column reports, to the cross
    # terms of compounding ratios (overnight x drift x execution / 1e4 each): 1.0 bp
    # on a day whose legs move 2.5% between them.
    assert row["total_bp_traded"] == pytest.approx(
        row["overnight_bp_traded"]
        + row["drift_bp_traded"]
        + row["execution_bp_traded"],
        abs=2.0,
    )


def test_without_a_quote_the_open_is_the_reference_and_the_row_says_so() -> None:
    rows, _unpriced = split(FILLS, OPENS, {"2026-10-15": 1_000_000.0})

    (row,) = rows
    assert row["n_quoted"] == 0
    assert row["drift_bp_traded"] == pytest.approx(0.0, abs=1e-9)
    assert row["basis"] == "open (no submission quote recorded)"


def test_a_leg_with_no_quote_falls_back_to_the_open_on_its_own() -> None:
    """One quoted leg and one not: the quoted one splits, the other does not."""
    quotes = pd.DataFrame(
        {
            "trade_date": ["2026-10-15"],
            "ticker": ["AAA"],
            "submitted_mid": [102.0],
            "quoted_at": ["2026-10-15T14:00:00Z"],
        }
    )
    rows, _unpriced = split(FILLS, OPENS, {"2026-10-15": 1_000_000.0}, quotes)

    (row,) = rows
    assert row["n_quoted"] == 1
    # Half the dollars are quoted, so the day's drift is half of AAA's 99.0 bp
    # (101 -> 102 on a book whose opens are 101).
    assert row["drift_bp_traded"] == pytest.approx(49.5, abs=0.2)
