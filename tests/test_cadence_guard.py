"""The hold day's two exceptions: a deferred reversal, and the drift guard.

A reversal that crosses zero cannot be one order: the morning closes the held side
and defers the other, and the next evening's delta opens it. On the daily loop that
is automatic, because the morning's target is the freshly built book and the account
is flat on the name. On a hold day the published book *is* the account's book, so the
deferred target has to be written back and the name has to be named, or the second
leg waits for the next rebalance while the book claims a position the account does
not have.

The drift guard is the same shape of problem from the other side: on a hold day the
book is not rebuilt, so its factor exposure drifts with the loadings. Past
`EFB_DRIFT_GUARD` the book takes the minimum-norm correction that makes it neutral,
and every name it moves must reach the morning's allow-list or the correction is
recorded and never traded.

Both run in the order the money does: the reversal is placed first, because a name
whose second leg is about to be sent must be measured at the side it will be held at.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from live import cadence, evening_job, morning_job

NAV = 1_000_000.0


def _book(weights: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"ticker": list(weights), "weight": list(weights.values())}
    ).sort_values("ticker")


def _nav(weights: dict[str, float]) -> dict[str, float]:
    return {name: weight * NAV for name, weight in weights.items()}


# ------------------------------------------------- the deferred reversal, on a hold


def test_the_deferred_target_is_written_back_into_the_held_book() -> None:
    """The account is flat; the book must not be.

    This is the whole defect: `_held_book_weights` reads the account, the account is
    flat because the first leg closed it, and the published book would carry the name
    at zero for every hold until the next rebalance.
    """
    held = np.array([0.5, 0.0])
    weights, applied = evening_job._with_deferred_targets(
        held, ["AAA", "BBB"], {"BBB": -0.10}, pd.Timestamp("2026-10-22")
    )
    assert applied == {"BBB": -0.10}
    assert weights is not None
    assert weights[1] == pytest.approx(-0.10)
    assert weights[0] == pytest.approx(0.5), "a name with no deferral was moved"


def test_a_deferral_the_universe_dropped_is_not_invented() -> None:
    """A name the model no longer prices cannot be published, and says so."""
    weights, applied = evening_job._with_deferred_targets(
        None, ["AAA"], {"ZZZ": 0.2}, pd.Timestamp("2026-10-22")
    )
    assert applied == {}
    assert weights is None


def test_a_pending_reversal_is_forced_so_its_second_leg_is_sent() -> None:
    """Rebalance day closes the long; the hold day's morning sends the short.

    The two halves are the two runs: the rebalance morning defers, and the hold
    morning - which the filter would otherwise leave alone, because the account and
    the book agree about nothing but sign - sends the leg the book is waiting for.
    """
    # The rebalance morning: long held, short target. One leg, closing, deferred.
    rebalance = morning_job.target_orders(
        _book({"AAA": -0.10}), nav=NAV, current=_nav({"AAA": 0.10}), forced=None
    )
    assert len(rebalance) == 1
    assert rebalance[0].trade_notional == pytest.approx(-0.10 * NAV)
    assert rebalance[0].deferred_target_notional == pytest.approx(-0.10 * NAV)

    # The hold evening: the account is flat, the book takes the deferred target.
    held, applied = evening_job._with_deferred_targets(
        np.array([0.0]), ["AAA"], {"AAA": -0.10}, pd.Timestamp("2026-10-22")
    )
    assert held is not None
    book = _book({"AAA": float(held[0])})
    manifest = {"reversal_targets": applied}
    forced = evening_job.forced_names_for_hold(manifest)
    assert forced == {"AAA"}

    # The hold morning sends the short leg, because the name is forced.
    hold = morning_job.target_orders(book, nav=NAV, current={}, forced=forced)
    assert [order.ticker for order in hold] == ["AAA"]
    assert hold[0].trade_notional == pytest.approx(-0.10 * NAV)


def test_the_same_leg_without_the_deferral_is_dropped_by_the_hold_filter() -> None:
    """The control: the filter is what strands the leg, and it still does."""
    hold = morning_job.target_orders(
        _book({"AAA": -0.10}), nav=NAV, current={}, forced=set()
    )
    assert hold == []


def test_a_completed_reversal_sends_nothing_on_a_hold_day() -> None:
    """The account holds the target: there is no second leg left to send."""
    held = np.array([-0.10])
    book = _book({"AAA": float(held[0])})
    hold = morning_job.target_orders(
        book, nav=NAV, current=_nav({"AAA": -0.10}), forced={"AAA"}
    )
    assert hold == []


def test_an_empty_deferral_list_changes_nothing() -> None:
    """A hold day after a day that deferred nothing is the plain hold day."""
    held, applied = evening_job._with_deferred_targets(
        np.array([0.5]), ["AAA"], {}, pd.Timestamp("2026-10-22")
    )
    assert applied == {}
    assert held is not None and held[0] == pytest.approx(0.5)


def test_the_daily_loop_still_sends_the_deferred_leg_the_next_morning() -> None:
    """`forced=None` is the daily path, and the leg is sent without any naming."""
    book = _book({"AAA": -0.10})
    daily = morning_job.target_orders(book, nav=NAV, current={}, forced=None)
    assert [order.ticker for order in daily] == ["AAA"]
    assert daily[0].trade_notional == pytest.approx(-0.10 * NAV)


# -------------------------------------------------------------- the drift guard


def _design() -> np.ndarray:
    """Two factors and a constant, so a book can be drifted by hand."""
    return np.array(
        [
            [1.0, 1.0, 0.0],
            [1.0, 0.0, 1.0],
            [1.0, -1.0, -1.0],
            [1.0, 0.5, 0.0],
        ]
    )


def test_the_guard_fires_past_the_threshold_and_forces_every_leg() -> None:
    design = _design()
    weights = np.array([0.30, 0.30, 0.20, 0.20])
    specific = np.full(len(weights), 0.02)
    threshold = 0.05
    before = evening_job.worst_exposure(weights, design)
    assert before > threshold
    block = evening_job._drift_guard_block(weights, list("ABCD"), design, specific, threshold)
    assert block is not None and block["fired"] is True
    corrected = np.asarray(block["weights"], dtype=float)
    assert evening_job.worst_exposure(corrected, design) < 1e-9
    assert block["exposure_before"] == pytest.approx(before)
    assert block["exposure_after"] < 1e-9
    # Every name the correction moved is on the manifest, so the hold filter passes it.
    manifest = {"drift_guard": {key: value for key, value in block.items() if key != "weights"}}
    forced = evening_job.forced_names_for_hold(manifest)
    moved = {leg["ticker"] for leg in block["legs"]}
    assert moved and moved <= forced
    assert {leg["ticker"] for leg in block["legs"]} == forced


def test_the_guard_does_not_fire_below_the_threshold() -> None:
    design = _design()
    weights = np.array([0.002, 0.001, -0.001, 0.0])
    assert evening_job.worst_exposure(weights, design) < 0.05
    block = evening_job._drift_guard_block(
        weights, list("ABCD"), design, np.full(4, 0.02), 0.05
    )
    assert block is None
    # And a manifest that never saw the guard forces nothing on its own.
    assert evening_job.forced_names_for_hold({"drift_guard": None}) == set()


def test_the_guard_measures_after_the_reversal_is_placed() -> None:
    """The order of the two: a pending reversal is measured at the side it will hold.

    The deferred side is what the guard has to neutralise, not the flat one the
    account still shows - otherwise the refresh would be computed against a book the
    loop is not going to hold.
    """
    design = _design()
    names = ["AAA", "BBB", "CCC", "DDD"]
    account = np.array([0.10, 0.10, 0.10, 0.0])
    before_reversal = evening_job.worst_exposure(account, design)
    placed, applied = evening_job._with_deferred_targets(
        account, names, {"DDD": -0.80}, pd.Timestamp("2026-10-22")
    )
    assert placed is not None
    after_reversal = evening_job.worst_exposure(placed, design)
    assert after_reversal > before_reversal, "the deferred side did not change the risk"
    block = evening_job._drift_guard_block(
        placed, names, design, np.full(4, 0.02), 0.05
    )
    assert block is not None
    assert block["exposure_before"] == pytest.approx(after_reversal)
    # The reversal name is in both lists, which is what "measured at the side it will
    # be held at" means for the morning: one leg per name, at the corrected weight.
    assert "DDD" in {leg["ticker"] for leg in block["legs"]}


def test_the_recorded_guard_legs_match_the_weights_it_publishes() -> None:
    """The manifest's legs and the book cannot disagree: the legs are the difference."""
    design = _design()
    names = list("ABCD")
    weights = np.array([0.30, 0.30, 0.20, 0.20])
    block = evening_job._drift_guard_block(weights, names, design, np.full(4, 0.02), 0.05)
    assert block is not None
    corrected = np.asarray(block["weights"], dtype=float)
    for index, name in enumerate(names):
        leg = next((item for item in block["legs"] if item["ticker"] == name), None)
        delta = corrected[index] - weights[index]
        if abs(delta) <= 1e-12:
            assert leg is None
        else:
            assert leg is not None
            assert leg["delta_notional_pct"] == pytest.approx(float(delta))
            assert leg["weight_after"] == pytest.approx(float(corrected[index]))


@pytest.mark.parametrize("value", ["", "off", "none", "0", "false"])
def test_the_guard_is_off_when_it_is_not_asked_for(value: str) -> None:
    assert evening_job.resolve_drift_guard(value) is None


def test_the_guard_reads_a_fraction_and_refuses_anything_else() -> None:
    assert evening_job.resolve_drift_guard("0.05") == pytest.approx(0.05)
    assert evening_job.resolve_drift_guard("0.5") == pytest.approx(0.5)
    # A typo, a percentage and an out-of-range number are all "off", and never a
    # threshold the owner did not type.
    assert evening_job.resolve_drift_guard("5%") is None
    assert evening_job.resolve_drift_guard("5") is None
    assert evening_job.resolve_drift_guard("-0.05") is None


def test_the_guard_runs_only_on_a_hold_day(monkeypatch: pytest.MonkeyPatch) -> None:
    """A rebalance day rebuilds the book, so there is nothing for the guard to do."""
    assert cadence.HOLD == "hold"
    # The block is only reachable from the held branch; at `k = 1` every close is a
    # rebalance, which is the default and the daily loop.
    days = list(pd.bdate_range("2026-10-01", periods=6))
    for day in days:
        assert cadence.plan(days, day, 1, anchor=days[0], completed=[])["day"] == (
            cadence.REBALANCE
        )
