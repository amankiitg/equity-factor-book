"""Tests for close-out task C3: the horizon-aligned volatility evaluation.

F2.3 compared one-step forecasts with a next-day squared return, which is
aligned, so its failure is not obviously a horizon mismatch. The brief
asks for the target and the horizon of each estimator to be printed, and
for a second evaluation where the 21-day horizon is matched on both sides:
a 21-day forecast against 21-day realized variance.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from efb import vol

DATES = pd.bdate_range("2020-01-01", periods=300)


def _series(values: np.ndarray, name: str = "AAA") -> pd.DataFrame:
    return pd.DataFrame({name: values}, index=DATES)


def test_forward_realized_variance_sums_the_next_h_days() -> None:
    values = np.arange(1.0, 301.0) / 1000.0
    frame = _series(values)
    out = vol.forward_realized_variance(frame, horizon=5)
    # at index i the sum covers i to i+4, so the last four rows are NaN
    assert out.iloc[0, 0] == pytest.approx(float((values[0:5] ** 2).sum()))
    assert out.iloc[10, 0] == pytest.approx(float((values[10:15] ** 2).sum()))
    # the last h-1 rows have no future to measure
    assert out.iloc[-4:].isna().all().all()
    assert pd.notna(out.iloc[-5, 0])
    # it looks forward, never back
    assert out.iloc[0, 0] != pytest.approx(float((values[0:4] ** 2).sum()))


def test_forward_realized_variance_horizon_one_is_the_same_day_squared_return() -> None:
    # the module convention: a value indexed at t forecasts the return
    # realized at t, so the one-day target is r_t squared
    values = np.arange(1.0, 301.0) / 100.0
    frame = _series(values)
    out = vol.forward_realized_variance(frame, horizon=1)
    assert out.iloc[7, 0] == pytest.approx(float(values[7] ** 2))
    assert out.notna().all().all()


def test_ewma_flat_forecast_scales_the_one_step_by_the_horizon() -> None:
    rng = np.random.default_rng(0)
    frame = _series(rng.normal(0.0, 0.01, 300))
    one_step = vol.ewma_vol(frame, lam=0.94, min_obs=60)
    flat = vol.horizon_forecast(one_step, horizon=21)
    assert flat.iloc[-1, 0] == pytest.approx(21.0 * one_step.iloc[-1, 0])


def test_trailing_flat_forecast_scales_the_trailing_variance() -> None:
    rng = np.random.default_rng(1)
    frame = _series(rng.normal(0.0, 0.01, 300))
    trailing = vol.realized_var(frame, window=252)
    flat = vol.horizon_forecast(trailing, horizon=21)
    assert flat.iloc[-1, 0] == pytest.approx(21.0 * trailing.iloc[-1, 0])


def test_garch_multi_step_at_the_unconditional_variance_is_h_times_it() -> None:
    # when the current variance sits at its unconditional level, the
    # expected sum of the next h variances is exactly h times that level
    params = {"omega": 1e-6, "alpha": 0.08, "beta": 0.9, "persistence": 0.98}
    uncond = params["omega"] / (1.0 - params["persistence"])
    out = vol.garch_horizon_sum(params, sigma2_next=uncond, horizon=21)
    assert out == pytest.approx(21.0 * uncond, rel=1e-9)


def test_garch_multi_step_reverts_toward_the_unconditional_variance() -> None:
    params = {"omega": 1e-6, "alpha": 0.08, "beta": 0.9, "persistence": 0.98}
    uncond = params["omega"] / (1.0 - params["persistence"])
    hot = vol.garch_horizon_sum(params, sigma2_next=4.0 * uncond, horizon=21)
    cold = vol.garch_horizon_sum(params, sigma2_next=0.25 * uncond, horizon=21)
    assert hot > 21.0 * uncond > cold
    # a hot state gives a bigger sum than simply repeating the hot level
    assert hot < 21.0 * 4.0 * uncond


def test_garch_multi_step_refuses_a_non_stationary_fit() -> None:
    params = {"omega": 1e-6, "alpha": 0.5, "beta": 0.6, "persistence": 1.1}
    assert vol.garch_horizon_sum(params, sigma2_next=1e-4, horizon=21) is None


def test_garch_horizon_forecast_tracks_the_recursion() -> None:
    rng = np.random.default_rng(7)
    returns = np.zeros(500)
    variance = np.zeros(500)
    variance[0] = 1e-4
    omega, alpha, beta = 2e-6, 0.08, 0.9
    for i in range(1, 500):
        variance[i] = omega + alpha * returns[i - 1] ** 2 + beta * variance[i - 1]
        returns[i] = np.sqrt(variance[i]) * rng.normal()
    dates = pd.bdate_range("2018-01-01", periods=500)
    frame = pd.DataFrame({"AAA": returns}, index=dates)
    params = {"omega": omega, "alpha": alpha, "beta": beta, "persistence": alpha + beta}
    oos_start = str(dates[400].date())
    out = vol.garch_horizon_forecast(
        frame, params=params, oos_start=oos_start, horizon=21
    )
    assert out is not None
    assert out.index.min() >= pd.Timestamp(oos_start)
    # the 21-day sum sits above a single day and below 21 hot days
    last = float(out.iloc[-1, 0])
    uncond = omega / (1.0 - alpha - beta)
    assert 21.0 * uncond * 0.2 < last < 21.0 * float(variance[-1]) + 1e-6


def test_one_step_variance_target_matches_the_return_target() -> None:
    # the aligned h=1 evaluation has to reproduce F2.3's target exactly,
    # otherwise the two are not comparable: qlike squares the return, and
    # qlike_variance takes the already-squared next-day value
    rng = np.random.default_rng(11)
    frame = pd.DataFrame(
        {"AAA": rng.normal(0.0, 0.01, 400)},
        index=pd.bdate_range("2021-01-01", periods=400),
    )
    sigma2 = vol.ewma_vol(frame, lam=0.94, min_obs=60)
    target = vol.forward_realized_variance(frame, horizon=1)
    by_return = vol.qlike(sigma2, frame)
    by_variance = vol.qlike_variance(sigma2, target)
    pd.testing.assert_frame_equal(
        by_return.rename(columns=lambda c: c), by_variance, check_exact=False
    )


def test_aligned_win_shares_covers_every_horizon() -> None:
    rng = np.random.default_rng(5)
    frame = pd.DataFrame(
        {
            "AAA": rng.normal(0.0, 0.012, 900),
            "BBB": rng.normal(0.0, 0.009, 900),
        },
        index=pd.bdate_range("2019-01-01", periods=900),
    )
    oos_start = str(frame.index[-250].date())
    table = vol.aligned_horse_race(
        frame, oos_start=oos_start, horizons=(1, 21), include_garch=False
    )
    shares = vol.aligned_win_shares(table)
    assert set(shares["horizon"]) == {1, 21}
    assert shares["win_share"].between(0.0, 1.0).all()
    assert (shares["n_names"] >= 2).all()


def test_aligned_horse_race_returns_both_horizons_on_the_same_window() -> None:
    rng = np.random.default_rng(3)
    frame = pd.DataFrame(
        {
            "AAA": rng.normal(0.0, 0.012, 1200),
            "BBB": rng.normal(0.0, 0.008, 1200),
        },
        index=pd.bdate_range("2018-01-01", periods=1200),
    )
    oos_start = str(frame.index[-300].date())
    table = vol.aligned_horse_race(
        frame, oos_start=oos_start, horizons=(1, 21), include_garch=False
    )
    assert set(table["horizon"]) == {1, 21}
    assert set(table["method"]) >= {"ewma_094", "trailing_252"}
    one = table[table["horizon"] == 1]
    twenty_one = table[table["horizon"] == 21]
    assert not one.empty and not twenty_one.empty
    # the same window for every method: QLIKE only uses rows in the window
    assert (table["n_obs"] > 0).all()
    assert one["n_obs"].max() <= len(frame) - frame.index.get_loc(oos_start)
