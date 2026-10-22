"""Sprint EFB-CADENCE: the rebalance calendar, the hold day, and the band's own check.

The calendar is `live.cadence`, the flag is `EFB_CADENCE` (unset or `1` is the
daily loop), and the anchor is `EFB_CADENCE_ANCHOR`. Three things are proven here:

- **B1, the calendar**: a close is a rebalance when the sessions since the anchor
  are a multiple of `k`, and a hold otherwise.
- **B2, the hold day**: the evening still prices a book, but it is the held one, and
  the order path sends only the legs a hold cannot avoid.
- **B3, the missed rebalance**: the completion record is what says a scheduled
  rebalance did not run, and the next successful evening takes it.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest

from live import cadence, evening_job, morning_job

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _sessions(start: str, n: int) -> list[pd.Timestamp]:
    return list(pd.bdate_range(start, periods=n))


# ------------------------------------------------------------------ B1: the calendar


def test_the_default_is_the_daily_loop() -> None:
    assert cadence.resolve_cadence(None) == 1
    assert cadence.resolve_cadence("") == 1
    assert cadence.resolve_cadence("1") == 1
    assert cadence.resolve_cadence("21") == 21


@pytest.mark.parametrize("value", ["0", "-3", "monthly", "2.5"])
def test_a_value_that_is_not_a_positive_whole_number_is_the_default(value: str) -> None:
    """Refused loudly and treated as unset, never guessed at.

    A book that silently rebalances on the wrong calendar is worse than one that
    rebalances daily, and the default is what a deployment that sets nothing gets.
    """
    assert cadence.resolve_cadence(value) == 1


def test_a_cadence_of_one_rebalances_every_close() -> None:
    days = _sessions("2026-10-01", 10)
    for day in days:
        plan = cadence.plan(days, day, 1, anchor=days[0], completed=[])
        assert plan["day"] == cadence.REBALANCE
        assert plan["scheduled"] is True
        assert plan["pending"] is False


def test_every_kth_session_is_a_rebalance_and_the_rest_are_holds() -> None:
    days = _sessions("2026-09-01", 46)
    anchor = days[0]
    # The record holds every scheduled rebalance that has already happened, which
    # is what the run's own row for the close would give it.
    plans = [
        cadence.plan(
            days,
            day,
            21,
            anchor=anchor,
            completed=[str(days[i].date()) for i in range(0, index + 1, 21)],
        )
        for index, day in enumerate(days)
    ]
    rebalances = [
        day
        for day, plan in zip(days, plans, strict=True)
        if plan["day"] == cadence.REBALANCE
    ]
    assert rebalances == [days[0], days[21], days[42]]
    hold = plans[5]
    assert hold["day"] == cadence.HOLD
    assert hold["scheduled"] is False
    assert hold["next_rebalance"] == str(days[21].date())
    assert hold["label"] == f"hold day, next rebalance {days[21].date()}"
    assert plans[0]["label"] == "rebalance day"


def test_the_anchor_is_session_zero() -> None:
    days = _sessions("2026-09-01", 30)
    anchor = days[4]
    done = [str(days[4].date()), str(days[11].date())]
    plan = cadence.plan(days, days[4], 7, anchor=anchor, completed=[])
    assert plan["day"] == cadence.REBALANCE
    assert plan["offset"] == 0
    assert (
        cadence.plan(days, days[11], 7, anchor=anchor, completed=[done[0]])["day"]
        == cadence.REBALANCE
    )
    assert (
        cadence.plan(days, days[12], 7, anchor=anchor, completed=done)["day"]
        == cadence.HOLD
    )


def test_an_anchor_that_is_not_a_session_snaps_back_to_the_session_before_it() -> None:
    days = _sessions("2026-09-01", 30)
    # a Saturday: the calendar counts from the Friday before it
    assert pd.Timestamp("2026-09-05").day_name() == "Saturday"
    anchor_day = pd.Timestamp("2026-09-05").normalize()
    expected = max(day for day in days if day <= anchor_day)
    # The session on or before the anchor is session zero, and the anchor it reports
    # is that session - so the calendar never counts from a day the exchange was shut.
    plan = cadence.plan(
        days, expected, 5, anchor="2026-09-05", completed=[str(expected.date())]
    )
    assert plan["anchor"] == "2026-09-05"
    assert plan["anchor_session"] == str(expected.date())
    assert plan["offset"] == 0
    assert plan["day"] == cadence.REBALANCE


def test_a_close_that_is_not_a_session_is_refused() -> None:
    days = _sessions("2026-09-01", 10)
    with pytest.raises(ValueError, match="not a session"):
        cadence.plan(days, "2026-09-06", 5, anchor=days[0], completed=[])


# ------------------------------------------------- B3: the missed rebalance


def test_a_missed_rebalance_makes_the_next_evening_a_rebalance() -> None:
    """The completion record is the calendar's memory, and a gap promotes today.

    The record is the row the run already files for the close it priced, so nothing
    new is stored: 2026-10-01 was a scheduled rebalance and has no completed row,
    and the next evening - a hold by the calendar - takes it instead.
    """
    days = _sessions("2026-10-01", 12)
    anchor = days[0]
    completed = ["2026-09-30"]  # nothing since the anchor
    plan = cadence.plan(days, days[1], 21, anchor=anchor, completed=completed)
    assert plan["scheduled"] is False
    assert plan["pending"] is True
    assert plan["missed"] == [str(days[0].date())]
    assert plan["day"] == cadence.REBALANCE
    assert "missed rebalance" in plan["label"]


def test_a_rebalance_that_ran_is_not_taken_twice() -> None:
    days = _sessions("2026-10-01", 12)
    plan = cadence.plan(
        days, days[1], 21, anchor=days[0], completed=[str(days[0].date())]
    )
    assert plan["day"] == cadence.HOLD
    assert plan["pending"] is False


def test_an_unreadable_record_promotes_nothing() -> None:
    """`None` is "cannot say", not "nothing ran".

    A store that cannot be read must not turn every hold day into a rebalance; the
    calendar still says which day this is, and the promotion is skipped with a
    warning rather than guessed.
    """
    days = _sessions("2026-10-01", 12)
    plan = cadence.plan(days, days[1], 21, anchor=days[0], completed=None)
    assert plan["day"] == cadence.HOLD
    assert plan["pending"] is False


def test_a_stale_stopped_rebalance_is_not_a_completed_one() -> None:
    assert "stale_stopped" not in cadence.COMPLETED_STATUSES
    assert "error" not in cadence.COMPLETED_STATUSES
    assert "ok" in cadence.COMPLETED_STATUSES
    assert "incomplete" in cadence.COMPLETED_STATUSES


# --------------------------------------------------------- B2: the hold day


def test_the_held_book_is_the_previous_book_and_never_renormalized() -> None:
    """A name that left drops out; the rest keep their sizes exactly."""
    previous = pd.Series({"AAA": 0.02, "BBB": -0.015, "GONE": 0.004})
    names = ["AAA", "BBB", "CCC"]
    vector = evening_job._held_book_weights(previous, names)
    assert vector is not None
    assert vector.tolist() == [0.02, -0.015, 0.0]
    # 0.035, not 1.0: renormalizing would trade every other name on a hold day.
    assert float(np.abs(vector).sum()) == pytest.approx(0.035)


def test_nothing_held_is_not_a_hold_day() -> None:
    assert evening_job._held_book_weights(None, ["AAA"]) is None
    assert evening_job._held_book_weights(pd.Series(dtype=float), ["AAA"]) is None
    assert evening_job._held_book_weights(pd.Series({"ZZZ": 0.0}), ["AAA"]) is None


def test_the_forced_list_names_every_reason_a_hold_day_trades() -> None:
    manifest = {
        "dropped_no_risk": [{"ticker": "AAA", "reason": "short history"}],
        "dropped_no_price": ["BBB"],
        "dropped_no_short": [{"ticker": "CCC"}],
    }
    forced = evening_job.forced_names_for_hold(manifest, ["DDD"], ["EEE"])
    assert forced == {"AAA", "BBB", "CCC", "DDD", "EEE"}


def test_a_hold_day_sends_only_forced_legs_and_closes() -> None:
    """The proposal is the held book; only what the book cannot keep may trade.

    `AAA` is held and still in the book - nothing to do. `BBB` left the universe -
    a close, always allowed. `CCC` is named forced (a corporate action). `DDD` is a
    new name the proposal carries and the hold did not authorise - not traded.
    """
    proposal = pd.DataFrame(
        {"ticker": ["AAA", "CCC", "DDD"], "weight": [0.10, 0.05, 0.02]}
    )
    held = {"AAA": 100_000.0, "BBB": 50_000.0, "CCC": 40_000.0}
    orders = morning_job.target_orders(
        proposal, nav=1_000_000.0, current=held, forced={"CCC"}
    )
    tickers = sorted(order.ticker for order in orders)
    assert tickers == ["BBB", "CCC"]
    assert {order.ticker: order.trade_notional for order in orders} == {
        "BBB": -50_000.0,
        "CCC": 10_000.0,
    }


def test_the_daily_path_sends_every_leg_when_no_hold_is_named() -> None:
    proposal = pd.DataFrame(
        {"ticker": ["AAA", "CCC", "DDD"], "weight": [0.10, 0.05, 0.02]}
    )
    held = {"AAA": 100_000.0, "BBB": 50_000.0, "CCC": 40_000.0}
    orders = morning_job.target_orders(proposal, nav=1_000_000.0, current=held)
    assert sorted(order.ticker for order in orders) == ["BBB", "CCC", "DDD"]


def test_a_reversal_is_allowed_through_the_hold_filter() -> None:
    """A position the account and the book disagree about cannot be held."""
    proposal = pd.DataFrame({"ticker": ["AAA"], "weight": [-0.10]})
    orders = morning_job.target_orders(
        proposal, nav=1_000_000.0, current={"AAA": 100_000.0}, forced=set()
    )
    assert [order.ticker for order in orders] == ["AAA"]
    assert orders[0].trade_notional == -100_000.0


# ------------------------------------- B2/B6: whole proposal builds, flag on


@pytest.mark.slow
def test_a_whole_proposal_builds_on_a_hold_day_with_the_flag_on() -> None:
    """The monthly flag and the floor band together: a whole book, not a raise.

    `EFB_CADENCE=21` with an anchor before the close makes the close a hold, and
    `EFB_FLOOR_RELEASE=0.5` is the band the churn study found cannot run: the
    below-floor check tested held names against the full floor and
    `build_proposal` raised on every rebalance where the band bound. Both are on
    here, on the real tree, and the book comes out as the one that was held.
    """
    data = ROOT / "data"
    as_of = pd.Timestamp("2026-09-21")
    previous = pd.Series({"AAPL": 0.01, "MSFT": -0.01, "KO": 0.005})
    manifest = evening_job.build_proposal(
        data_root=data,
        as_of=as_of,
        store=False,
        previous=previous,
        floor_release=0.5,
        cadence_mode=21,
        cadence_anchor="2026-09-18",
        # The anchor's own rebalance ran; without this row the calendar would read
        # the anchor as a missed rebalance and take it on 09-21 - which is the B3
        # rule, proven separately.
        completed_rebalances=["2026-09-18"],
    )
    assert manifest["held_book"] is True
    assert manifest["cadence"]["day"] == cadence.HOLD
    assert manifest["cadence"]["k"] == 21
    book = pd.DataFrame(manifest["kept_book"]).set_index("ticker")["weight"]
    # The held names that the model still carries keep their weights exactly; the
    # rest of the universe is not entered on a hold day.
    assert float(book.get("AAPL", 0.0)) == pytest.approx(0.01)
    assert float(book.get("MSFT", 0.0)) == pytest.approx(-0.01)
    # Nothing else was entered: the rest of the universe has no weight at all.
    assert float(book.abs().sum()) <= 0.025 + 1e-12
    assert set(book.index) <= {"AAPL", "MSFT", "KO"} | set(manifest["excluded"])


@pytest.mark.slow
def test_a_whole_rebalance_proposal_still_builds_with_the_band_on() -> None:
    """B6: the band no longer raises `floor_book_violations` on a real rebalance.

    Before the fix, `EFB_FLOOR_RELEASE=0.5` failed the below-floor check on the
    first rebalance where the band kept a held name under its full floor, and the
    evening produced no book at all. The check is the band's own now.
    """
    data = ROOT / "data"
    as_of = pd.Timestamp("2026-09-21")
    previous = pd.Series({"AAPL": 0.02, "MSFT": -0.02})
    manifest = evening_job.build_proposal(
        data_root=data,
        as_of=as_of,
        store=False,
        previous=previous,
        floor_release=0.5,
    )
    # With no calendar asked for, the manifest is `main`'s: no `held_book`, no
    # `cadence`, no guard keys. The floor band is the only thing this run changed, and
    # it has to be possible to prove that key for key (see
    # `tests/test_cadence_manifest_identity.py`).
    assert "held_book" not in manifest
    assert "cadence" not in manifest
    assert manifest["floor_release"] == 0.5
    assert manifest["n_kept"] > 0
