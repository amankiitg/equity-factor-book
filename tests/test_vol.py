"""Tests for Task 4: volatility estimators, QLIKE and Mincer-Zarnowitz."""

import numpy as np
import pandas as pd
import pytest

from efb import vol


def _series(values, start="2020-01-02") -> pd.Series:
    return pd.Series(
        values, index=pd.bdate_range(start, periods=len(values)), dtype=float
    )


def test_ewma_recursion_matches_manual() -> None:
    r = _series([0.01, -0.02, 0.015, -0.005, 0.02, -0.01, 0.005, 0.001] * 20)
    lam = 0.94
    out = vol.ewma_vol(r, lam=lam, min_obs=10)
    t = 20
    manual = float(np.var(r.iloc[:10]))  # implementation seeds with ddof=0
    # sigma2_t = lam sigma2_{t-1} + (1 - lam) r_{t-1}^2, so from sigma2_10
    # to sigma2_20 the recursion consumes r_10 through r_19
    for i in range(11, t + 1):
        manual = lam * manual + (1 - lam) * float(r.iloc[i - 1]) ** 2
    assert out.iloc[t] == pytest.approx(manual, rel=1e-10)


def test_ewma_uses_only_past_observations() -> None:
    r = _series([0.01, -0.02, 0.015, -0.005, 0.02, -0.01, 0.005, 0.001] * 20)
    out = vol.ewma_vol(r, lam=0.94, min_obs=10)
    shocked = r.copy()
    t = 100
    shocked.iloc[t] = 0.5
    out_shocked = vol.ewma_vol(shocked, lam=0.94, min_obs=10)
    assert out.iloc[t] == pytest.approx(out_shocked.iloc[t])
    assert out.iloc[t + 1] != pytest.approx(out_shocked.iloc[t + 1])


def test_realized_vol_trailing_window() -> None:
    r = _series(np.random.default_rng(0).normal(0, 0.01, 100))
    out = vol.realized_vol(r, window=21, annualize=False)
    t = 50
    expected = r.iloc[t - 21 : t].std(ddof=1)
    assert out.iloc[t] == pytest.approx(expected, rel=1e-12)


def test_qlike_known_value() -> None:
    sigma2 = _series([0.0004, 0.0001])
    r = _series([0.02, 0.01])
    out = vol.qlike(sigma2, r)
    assert out.iloc[0] == pytest.approx(np.log(0.0004) + 0.0004 / 0.0004)
    assert out.iloc[1] == pytest.approx(np.log(0.0001) + 0.0001 / 0.0001)


def test_qlike_series_with_different_names_is_elementwise() -> None:
    # regression: a Series named "garch" against a Series named "AAPL" used
    # to align on the column name and return all NaN
    sigma2 = _series([0.0004, 0.0001]).rename("garch")
    r = _series([0.02, 0.01]).rename("AAPL")
    out = vol.qlike(sigma2, r)
    assert len(out) == 2
    assert not out.isna().any()


def test_realized_var_is_squared_std() -> None:
    rng = np.random.default_rng(7)
    r = _series(rng.normal(0, 0.01, 100))
    var = vol.realized_var(r, window=21)
    std = vol.realized_vol(r, window=21, annualize=False)
    assert float(var.iloc[50]) == pytest.approx(float(std.iloc[50]) ** 2)


def test_mincer_zarnowitz_recovers_known_line() -> None:
    rng = np.random.default_rng(1)
    n = 500
    sigma2 = _series(np.exp(rng.normal(-9.0, 0.5, n)))
    r2 = 0.2 * sigma2.to_numpy() + 1e-5 + rng.normal(0, 0.5e-4, n)
    r2 = np.clip(r2, 1e-10, None)
    result = vol.mincer_zarnowitz(_series(r2), sigma2)
    assert result.beta == pytest.approx(0.2, rel=0.15)
    assert result.n_obs == n


def test_ewma_vol_beats_constant_on_garch_data() -> None:
    # synthetic GARCH(1,1) with strong clustering: a constant vol forecast
    # loses on QLIKE, the EWMA forecast should not
    rng = np.random.default_rng(2)
    n = 3000
    omega, a, b = 2e-6, 0.1, 0.85
    eps = np.zeros(n)
    sig2 = np.full(n, omega / (1 - a - b))
    for t in range(1, n):
        sig2[t] = omega + a * eps[t - 1] ** 2 + b * sig2[t - 1]
        eps[t] = np.sqrt(sig2[t]) * rng.normal()
    r = _series(eps)
    ewma = vol.ewma_vol(r, lam=0.94, min_obs=100)
    constant = _series(np.full(n, eps[:200].var()))
    oos = slice(1500, n)
    ewma_loss = vol.qlike(ewma, r).iloc[oos].mean()
    constant_loss = vol.qlike(constant, r).iloc[oos].mean()
    assert ewma_loss < constant_loss


def test_garch_fit_recovers_parameters_on_synthetic_data() -> None:
    pytest.importorskip("arch")
    rng = np.random.default_rng(3)
    n = 4000
    omega, a, b = 2e-6, 0.12, 0.8
    eps = np.zeros(n)
    sig2 = np.full(n, omega / (1 - a - b))
    for t in range(1, n):
        sig2[t] = omega + a * eps[t - 1] ** 2 + b * sig2[t - 1]
        eps[t] = np.sqrt(sig2[t]) * rng.normal()
    r = _series(eps)
    params = vol.fit_garch(r)
    assert params is not None
    assert params["alpha"] == pytest.approx(a, abs=0.06)
    assert params["beta"] == pytest.approx(b, abs=0.1)
    assert params["persistence"] < 1.0


def test_vol_horse_race_table_shape() -> None:
    rng = np.random.default_rng(4)
    n = 900
    r = pd.DataFrame(
        {
            "AAA": rng.normal(0, 0.01, n),
            "BBB": rng.normal(0, 0.02, n),
        },
        index=pd.bdate_range("2022-01-03", periods=n),
    )
    table = vol.vol_horse_race(r, oos_start="2025-01-01", include_garch=False)
    assert {"ticker", "method", "qlike"} <= set(table.columns)
    assert set(table["method"]) >= {
        "ewma_094",
        "ewma_097",
        "realized_21",
        "realized_63",
        "trailing_252",
    }
    wins = vol.beats_baseline(table, baseline="trailing_252")
    assert set(wins["method"]) >= {"ewma_094", "ewma_097"}
    assert wins["win_share"].between(0, 1).all()
