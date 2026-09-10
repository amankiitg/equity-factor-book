"""Tests for Task 3: beta shrinkage, rolling and EWMA betas, shift audit."""

import numpy as np
import pandas as pd
import pytest

from efb.models import timeseries as ts


def _market(n: int = 800, beta: float = 1.2, seed: int = 0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-02", periods=n)
    x = pd.Series(rng.normal(0.0003, 0.01, n), index=idx, name="mkt_rf")
    y = beta * x + pd.Series(rng.normal(0.0, 0.005, n), index=idx)
    return y, x


def test_blume_shrink_known_value() -> None:
    beta = pd.Series([1.3, 0.5])
    shrunk = ts.blume_shrink(beta)
    assert shrunk.iloc[0] == pytest.approx(0.67 * 1.3 + 0.33)
    assert shrunk.iloc[1] == pytest.approx(0.67 * 0.5 + 0.33)


def test_vasicek_shrinks_high_se_more() -> None:
    beta = pd.Series({"A": 0.5, "B": 1.5})
    se = pd.Series({"A": 0.05, "B": 1.0})
    shrunk = ts.vasicek_shrink(beta, se)
    # the low-SE name barely moves, the high-SE name is pulled to the mean
    assert shrunk["A"] == pytest.approx(0.5, abs=0.02)
    assert shrunk["B"] == pytest.approx(1.0, abs=0.35)
    assert abs(shrunk["B"] - 1.0) > abs(shrunk["A"] - 0.5)


def test_vasicek_respects_custom_mean() -> None:
    beta = pd.Series({"A": 1.0, "B": 3.0})
    se = pd.Series({"A": 1.0, "B": 1.0})
    shrunk = ts.vasicek_shrink(beta, se, beta_bar=0.5)
    assert 0.5 < shrunk["A"] < 1.0
    assert 1.0 < shrunk["B"] < 3.0


def test_ewma_weights_half_life() -> None:
    w = ts.ewma_weights(200, half_life=63)
    assert w[0] == pytest.approx(1.0)
    assert w[126] == pytest.approx(0.25, rel=1e-6)
    assert w[63] == pytest.approx(0.5, rel=1e-6)


def test_rolling_beta_uses_data_through_t_minus_1() -> None:
    y, x = _market(n=500)
    betas = ts.rolling_beta(y, x, window=252, min_obs=200)
    t = y.index[400]
    future_shocked = y.copy()
    future_shocked.loc[t:] = future_shocked.loc[t:] * 3.0
    betas_shocked = ts.rolling_beta(future_shocked, x, window=252, min_obs=200)
    # a shock on and after t must not change the beta dated t
    assert betas.loc[t] == pytest.approx(betas_shocked.loc[t], abs=1e-12)
    # but it does change the beta dated t+1
    assert abs(betas.iloc[401] - betas_shocked.iloc[401]) > 1e-6


def test_rolling_beta_recovers_known_beta() -> None:
    y, x = _market(n=800, beta=1.2)
    betas = ts.rolling_beta(y, x, window=252, min_obs=200)
    assert betas.dropna().mean() == pytest.approx(1.2, abs=0.05)


def test_rolling_beta_se_recovers_known_se() -> None:
    y, x = _market(n=800, beta=1.2)  # residual sigma is 0.005
    se = ts.rolling_beta_se(y, x, window=252, min_obs=200)
    expected = 0.005 / (x.std() * np.sqrt(252))
    assert se.dropna().mean() == pytest.approx(expected, rel=0.1)
    assert se.notna().any()


def test_vasicek_differs_from_raw_when_se_is_used() -> None:
    rng = np.random.default_rng(4)
    idx = pd.bdate_range("2015-01-02", periods=600)
    x = pd.Series(rng.normal(0.0003, 0.01, len(idx)), index=idx, name="mkt_rf")
    y = pd.DataFrame(
        {
            "AAA": 1.5 * x + rng.normal(0, 0.01, len(idx)),
            "BBB": 0.5 * x + rng.normal(0, 0.01, len(idx)),
        },
        index=idx,
    )
    history = ts.beta_history(y, x, window=252, half_lives=(63,), min_obs=200)
    raw = history[("raw", "AAA")].dropna()
    vas = history[("vasicek", "AAA")].dropna()
    assert len(raw) > 0
    assert (raw - vas).abs().max() > 1e-6


def test_ewma_beta_recovers_known_beta_and_is_shifted() -> None:
    y, x = _market(n=800, beta=0.8)
    betas = ts.ewma_beta(y, x, half_life=63, min_obs=200)
    assert betas.dropna().mean() == pytest.approx(0.8, abs=0.05)
    t = y.index[500]
    shocked = y.copy()
    shocked.loc[t:] = shocked.loc[t:] + 10.0 * x.loc[t:]
    betas_shocked = ts.ewma_beta(shocked, x, half_life=63, min_obs=200)
    assert betas.loc[t] == pytest.approx(betas_shocked.loc[t], abs=1e-12)


def test_rolling_beta_handles_factor_series_shorter_than_panel() -> None:
    # the French factor files lag the return panel by about a month; the
    # estimator must reindex to the panel and still use every observation
    y, x = _market(n=400, beta=1.0)
    aligned = ts.rolling_beta(y, x, window=252, min_obs=200)
    truncated = x.iloc[:-30]
    out = ts.rolling_beta(y, truncated, window=252, min_obs=200)
    assert len(out) == len(y)
    # the tail beta is finite: the window still holds enough factor rows
    assert np.isfinite(out.iloc[-1])
    # and it uses the same observations as an explicitly reindexed factor
    manual = ts.rolling_beta(y, truncated.reindex(y.index), window=252, min_obs=200)
    assert out.iloc[-1] == pytest.approx(manual.iloc[-1], rel=1e-12)
    # the value is close to the fully aligned estimate, not identical
    assert out.iloc[-1] == pytest.approx(aligned.iloc[-1], rel=0.1)


def test_ewma_beta_handles_factor_series_shorter_than_panel() -> None:
    y, x = _market(n=400, beta=1.0)
    out = ts.ewma_beta(y, x.iloc[:-30], half_life=63, min_obs=200)
    assert np.isfinite(out.iloc[-1])


def test_beta_history_frames_shapes() -> None:
    rng = np.random.default_rng(9)
    idx = pd.bdate_range("2015-01-02", periods=600)
    x = pd.Series(rng.normal(0.0003, 0.01, len(idx)), index=idx, name="mkt_rf")
    y = pd.DataFrame(
        {
            "AAA": 1.1 * x + rng.normal(0, 0.005, len(idx)),
            "BBB": 0.6 * x + rng.normal(0, 0.005, len(idx)),
        },
        index=idx,
    )
    history = ts.beta_history(y, x, window=252, half_lives=(63, 126), min_obs=200)
    methods = history.columns.get_level_values(0).unique()
    assert set(methods) >= {"raw", "ewma_63", "ewma_126", "vasicek", "blume"}
    assert history.shape[1] == 2 * len(methods)
    # shrinkage happens cross-sectionally at each date
    assert "vasicek" in methods
    assert "blume" in methods
