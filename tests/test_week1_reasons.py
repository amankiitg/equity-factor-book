"""Week one, item 3: the reason classifier's two thresholds and two new labels.

The classifier used to decide "did the score move" and "did the position move" with
one constant, `ALPHA_EPS = 1e-9`, which is a test for float noise rather than for
materiality. A daily cross-sectional z is re-standardised every session, so it
always moves (measured on the 2026-10-01 rebalance: the smallest of 153 shared
names' day-to-day moves was 5.0e-4, five hundred thousand times the epsilon), and
every name whose weight moved was therefore called an alpha move. The two questions
now have their own scales:

  * the weight test is `$250` of NAV, the same floor the order path refuses to send
    a leg under, so "no trade" means "the order path would not have sent this
    either";
  * the score test is 0.05 of a z-score, a fifth of a standard deviation of the
    cross-section, and the risk test is 1% relative on the specific volatility.

And the book's own life gets its two missing words: a name entering on a rebalance
is a "new name", and a name the book leaves is "exited".

**Labels only.** Nothing here can move a weight, a hedge or an order: the reason is
merged onto tonight's rows after the book is built and sized, and the tests below
pin that the classifier returns its inputs' own weights and z untouched.
"""

from __future__ import annotations

import pandas as pd
import pytest

from live import alpaca, trade_reasons


def _today() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC"],
            "weight": [0.02, -0.03, 0.01],
            "z": [1.0, -1.5, 0.5],
        }
    )


def _specific(sigma: float = 0.02) -> pd.Series:
    return pd.Series({"AAA": sigma, "BBB": sigma, "CCC": sigma})


def _previous() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC", "DDD"],
            "weight": [0.02, -0.01, 0.01, 0.015],
            "z": [1.0, -1.5, 0.5, 0.2],
        }
    )


def test_the_weight_threshold_is_the_orders_own_floor_in_dollars() -> None:
    """One number, two users: the classifier must not claim a leg the orders skip.

    A $250 difference on a $1M book is 2.5e-4 of NAV, and that is the boundary the
    two sides of this test sit on. It used to be 1e-9 of a weight, i.e. $0.001, so
    any real move counted and the threshold did nothing.
    """
    assert trade_reasons.WEIGHT_DOLLARS == alpaca.DELTA_MIN_NOTIONAL

    previous = _previous()
    # BBB is held at -0.01, which is $10,000 of the $1M book. Moving it to -0.0102
    # is $200: under the floor, so nothing would be sent and the reason says so
    # even though the score moved materially (z -1.5 to -1.0).
    small = _today()
    small.loc[small["ticker"] == "BBB", "weight"] = -0.0102
    small.loc[small["ticker"] == "BBB", "z"] = -1.0
    reasons = trade_reasons.assign_trade_reasons(
        small, previous, _specific(), _specific(), nav=1_000_000.0
    ).set_index("ticker")["reason"]
    assert reasons["BBB"] == "no trade"

    # the same name moving by $300 is over it, and its score moved: an alpha move
    big = _today()
    big.loc[big["ticker"] == "BBB", "weight"] = -0.0097
    big.loc[big["ticker"] == "BBB", "z"] = -1.0
    reasons = trade_reasons.assign_trade_reasons(
        big, previous, _specific(), _specific(), nav=1_000_000.0
    ).set_index("ticker")["reason"]
    assert reasons["BBB"] == "alpha moved"


def test_the_threshold_follows_the_nav_it_is_quoted_against() -> None:
    """The same $250 is a larger share of a smaller book, and the test follows it."""
    previous = _previous()
    moved = _today()
    # A $400 weight difference on the $1M book, which is $200 of a $500,000 one:
    # the same difference, on either side of the same $250 depending on the book it
    # is a share of. Quoting the threshold as a fraction would get this wrong.
    moved.loc[moved["ticker"] == "BBB", "weight"] = -0.0096
    moved.loc[moved["ticker"] == "BBB", "z"] = -1.0
    assert (
        trade_reasons.assign_trade_reasons(
            moved, previous, _specific(), _specific(), nav=1_000_000.0
        ).set_index("ticker")["reason"]["BBB"]
        == "alpha moved"
    )
    assert (
        trade_reasons.assign_trade_reasons(
            moved, previous, _specific(), _specific(), nav=500_000.0
        ).set_index("ticker")["reason"]["BBB"]
        == "no trade"
    )
    # and with no NAV at all the design NAV stands in rather than a zero threshold
    assert trade_reasons.weight_eps_for(None) == pytest.approx(250.0 / 1_000_000.0)


def test_the_score_threshold_is_material_not_numerical() -> None:
    """0.04 of a z does not make an alpha move; 0.06 does. The old epsilon was 1e-9."""
    previous = _previous()
    under = _today()
    under.loc[under["ticker"] == "AAA", "weight"] = 0.03
    under.loc[under["ticker"] == "AAA", "z"] = 1.04
    reasons = trade_reasons.assign_trade_reasons(
        under, previous, _specific(), _specific(), nav=1_000_000.0
    ).set_index("ticker")["reason"]
    assert reasons["AAA"] != "alpha moved"

    over = _today()
    over.loc[over["ticker"] == "AAA", "weight"] = 0.03
    over.loc[over["ticker"] == "AAA", "z"] = 1.06
    reasons = trade_reasons.assign_trade_reasons(
        over, previous, _specific(), _specific(), nav=1_000_000.0
    ).set_index("ticker")["reason"]
    assert reasons["AAA"] == "alpha moved"


def test_the_risk_threshold_is_relative_and_material() -> None:
    """A score that did not move and a volatility that did: risk, not hedge or alpha.

    AAA's weight moves $10,000 on $1M while its z moves 0.01 (under the z floor) and
    its specific volatility moves 5% (over the 1% floor), so the only input of its
    own that moved is its risk.
    """
    previous = _previous()
    today = _today()
    today.loc[today["ticker"] == "AAA", "weight"] = 0.03
    today.loc[today["ticker"] == "AAA", "z"] = 1.01
    reasons = trade_reasons.assign_trade_reasons(
        today,
        previous,
        _specific(0.021),
        _specific(0.02),
        nav=1_000_000.0,
    ).set_index("ticker")["reason"]
    assert reasons["AAA"] == "risk moved"

    # 0.1% of volatility is not a material risk move, so the hedge is what is left
    reasons = trade_reasons.assign_trade_reasons(
        today,
        previous,
        _specific(0.02002),
        _specific(0.02),
        nav=1_000_000.0,
    ).set_index("ticker")["reason"]
    assert reasons["AAA"] == "the hedge moved"


def test_a_name_entering_on_a_rebalance_is_a_new_name() -> None:
    """Entering is not a move, and on a rebalance the vocabulary now says so."""
    previous = _previous()
    today = pd.DataFrame(
        {"ticker": ["AAA", "NEW"], "weight": [0.02, 0.01], "z": [1.0, 0.9]}
    )
    frame = trade_reasons.assign_trade_reasons(
        today, previous, _specific(), _specific(), nav=1_000_000.0
    )
    reasons = frame.set_index("ticker")["reason"]
    assert reasons["NEW"] == "new name"
    assert reasons["AAA"] == "no trade"


def test_a_name_the_book_leaves_is_exited_and_carries_a_zero_weight() -> None:
    """The exit is a trade, so it gets a reason like any other, at target zero.

    The row is appended to the returned frame rather than to tonight's book, which
    is what keeps the stored positions, the snapshot's book and the orders exactly
    as they were: the classifier accounts for the name, it does not add it back.
    """
    previous = _previous()
    frame = trade_reasons.assign_trade_reasons(
        _today(), previous, _specific(), _specific(), nav=1_000_000.0
    )
    exits = frame.loc[frame["reason"] == "exited"]
    assert list(exits["ticker"]) == ["DDD"]
    assert list(exits["weight"]) == [0.0]
    assert bool(exits["z"].isna().all())

    # tonight's own names are untouched, weights and z included
    tonight = frame.loc[frame["reason"] != "exited"].reset_index(drop=True)
    assert list(tonight["ticker"]) == ["AAA", "BBB", "CCC"]
    assert list(tonight["weight"]) == list(_today()["weight"])
    assert list(tonight["z"]) == list(_today()["z"])


def test_the_establishment_day_has_neither_new_names_nor_exits() -> None:
    """Nothing was held and nothing was there, so nothing entered or left."""
    frame = trade_reasons.assign_trade_reasons(
        _today(), None, _specific(), None, nav=1_000_000.0
    )
    assert set(frame["reason"]) == {"new position"}
    assert len(frame) == len(_today())


def test_the_vocabulary_is_the_vocabulary_the_page_reads() -> None:
    """Every label the classifier can return is declared, and nothing else is."""
    assert set(trade_reasons.REASONS) == {
        "new position",
        "new name",
        "exited",
        "alpha moved",
        "risk moved",
        "the hedge moved",
        "drifted past a band",
        "no trade",
    }
    frame = trade_reasons.assign_trade_reasons(
        _today(), _previous(), _specific(), _specific(), nav=1_000_000.0
    )
    assert set(frame["reason"]) <= set(trade_reasons.REASONS)


def test_a_label_cannot_move_an_order_a_weight_or_a_hedge() -> None:
    """Why this change is labels only, in two pieces of evidence.

    The store takes the classifier's `reason` column and nothing else: the weights
    the book was sized on and the hedge that came out of it are decided by
    `build_proposal` before the reason is computed, and the merge that attaches it
    is on tonight's rows by ticker. Read off the file rather than asserted in prose.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "run_live_daily.py").read_text()
    assert 'reasons[["ticker", "reason"]]' in source
    # and the classifier hands back the very weights and z it was given
    frame = trade_reasons.assign_trade_reasons(
        _today(), _previous(), _specific(), _specific(), nav=1_000_000.0
    )
    tonight = frame.loc[frame["reason"] != trade_reasons.EXITED].reset_index(drop=True)
    assert list(tonight["ticker"]) == list(_today()["ticker"])
    assert list(tonight["weight"]) == list(_today()["weight"])
    assert list(tonight["z"]) == list(_today()["z"])
