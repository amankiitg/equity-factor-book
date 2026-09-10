"""Tests for Task 1: OLS market model and Newey-West standard errors."""

import numpy as np
import pandas as pd
import pytest

from efb.models import timeseries as ts


def _synthetic(n: int = 2000, beta: float = 1.3, alpha: float = 0.0002, seed: int = 0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-02", periods=n)
    x = pd.Series(rng.normal(0.0004, 0.01, n), index=idx, name="mkt_rf")
    eps = pd.Series(rng.normal(0.0, 0.01, n), index=idx, name="eps")
    y = alpha + beta * x + eps
    return y, x.to_frame(), eps


def test_ols_recovers_known_parameters() -> None:
    y, X, eps = _synthetic()
    fit = ts.ols_fit(y, X)
    assert fit.params["alpha"] == pytest.approx(0.0002, abs=1e-3)
    assert fit.params["mkt_rf"] == pytest.approx(1.3, abs=0.07)
    assert fit.sigma_eps == pytest.approx(float(eps.std(ddof=2)), abs=5e-4)
    assert fit.n_obs == 2000


def test_ols_se_matches_closed_form() -> None:
    y, X, _ = _synthetic()
    fit = ts.ols_fit(y, X)
    x = X["mkt_rf"]
    resid = fit.residuals
    dof = len(y) - 2
    sigma2 = float((resid**2).sum()) / dof
    sxx = float(((x - x.mean()) ** 2).sum())
    assert fit.ols_se["mkt_rf"] == pytest.approx(np.sqrt(sigma2 / sxx), rel=1e-10)
    assert fit.ols_se["alpha"] == pytest.approx(
        np.sqrt(sigma2 * (1 / len(y) + x.mean() ** 2 / sxx)), rel=1e-10
    )


def test_newey_west_widens_se_with_autocorrelated_residuals() -> None:
    # NW widens the SE when the score x_t u_t is autocorrelated. That needs
    # a persistent regressor and an autocorrelated residual, since with a
    # white-noise regressor the cross-products vanish in expectation.
    n = 2000
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2015-01-02", periods=n)
    x = np.zeros(n)
    e = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.6 * x[t - 1] + rng.normal(0.0, 0.01)
        e[t] = 0.5 * e[t - 1] + rng.normal(0.0, 0.01)
    x_series = pd.Series(x, index=idx, name="mkt_rf")
    y = 0.0002 + 1.3 * x_series + pd.Series(e, index=idx)
    fit = ts.ols_fit(y, x_series.to_frame(), nw_lag=5)
    assert fit.nw_se["mkt_rf"] > fit.ols_se["mkt_rf"] * 1.2


def test_nan_rows_are_dropped_not_imputed() -> None:
    y, X, _ = _synthetic(n=200)
    holes = y.index[[10, 50, 120]]
    y_holey = y.copy()
    y_holey.loc[holes] = np.nan
    fit = ts.ols_fit(y_holey, X)
    assert fit.n_obs == 197
    assert fit.n_dropped_nan == 3
    for d in holes:
        assert d not in fit.residuals.index
    # the fit equals the same regression on the manually dropped sample
    manual = ts.ols_fit(y.drop(index=holes), X.drop(index=holes))
    assert fit.params["mkt_rf"] == pytest.approx(manual.params["mkt_rf"], abs=1e-12)


def test_flagged_rows_are_excluded_and_counted() -> None:
    y, X, _ = _synthetic(n=200)
    flags = pd.DataFrame(False, index=y.index, columns=["stale", "outlier"])
    flags.iloc[5, 0] = True
    flags.iloc[6, 1] = True
    y_masked, counts = ts.apply_exclusions(y, flags)
    assert int(y_masked.isna().sum()) == 2
    assert counts == {"stale": 1, "outlier": 1, "nan": 0}
    fit = ts.ols_fit(y_masked, X)
    assert fit.n_obs == 198


def test_short_history_returns_nan() -> None:
    y, X, _ = _synthetic(n=40)
    fit = ts.ols_fit(y, X, min_obs=60)
    assert np.isnan(fit.params["mkt_rf"])
    assert fit.n_obs == 40


def test_singular_design_is_handled() -> None:
    y, X, _ = _synthetic(n=100)
    X_const = X.copy()
    X_const["dup"] = X_const["mkt_rf"]
    fit = ts.ols_fit(y, X_const[["mkt_rf", "dup"]].assign(mkt_rf=X_const["mkt_rf"] * 2))
    # perfectly collinear columns: parameters are NaN, not a crash
    assert np.isnan(fit.params["dup"]) or np.isnan(fit.params["mkt_rf"])


def test_fit_factor_model_recovers_known_loadings() -> None:
    rng = np.random.default_rng(11)
    idx = pd.bdate_range("2015-01-02", periods=800)
    f1 = pd.Series(rng.normal(0.0004, 0.01, len(idx)), index=idx)
    f2 = pd.Series(rng.normal(0.0001, 0.005, len(idx)), index=idx)
    factors = pd.DataFrame({"mkt_rf": f1, "smb": f2})
    y = pd.DataFrame(
        {
            "AAA": 0.0001 + 1.2 * f1 - 0.3 * f2 + rng.normal(0, 0.01, len(idx)),
            "BBB": -0.0001 + 0.8 * f1 + 0.5 * f2 + rng.normal(0, 0.01, len(idx)),
        },
        index=idx,
    )
    out = ts.fit_factor_model(y, factors)
    loadings = out["loadings"]
    assert loadings.loc["AAA", "mkt_rf"] == pytest.approx(1.2, abs=0.1)
    assert loadings.loc["AAA", "smb"] == pytest.approx(-0.3, abs=0.1)
    assert loadings.loc["BBB", "mkt_rf"] == pytest.approx(0.8, abs=0.1)
    assert loadings.loc["BBB", "smb"] == pytest.approx(0.5, abs=0.1)
    assert set(loadings.columns) == {"alpha", "mkt_rf", "smb"}
    assert set(out["residuals"].index.names) == {"date", "ticker"}


def test_panel_from_artifacts_masks_flagged_rows() -> None:
    dates = pd.bdate_range("2010-01-04", periods=4)
    idx = pd.MultiIndex.from_product([dates, ["AAA", "BBB"]], names=["date", "ticker"])
    returns_frame = pd.DataFrame(
        {
            "r": 0.01,
            "g": 0.01,
            "excess": [0.01, 0.02, 0.03, 0.04, 0.01, 0.02, 0.03, 0.04],
            "stale": [False, False, True, False, False, False, False, False],
            "outlier": [False, False, False, False, False, True, False, False],
        },
        index=idx,
    )
    factors = pd.DataFrame({"mkt_rf": 0.005}, index=dates)
    y, fac, flags = ts.panel_from_artifacts(returns_frame, factors, start=2010)
    assert np.isnan(y.loc[dates[1], "AAA"])  # stale row masked
    assert np.isnan(y.loc[dates[2], "BBB"])  # outlier row masked
    assert y.loc[dates[0], "AAA"] == pytest.approx(0.01)
    assert fac.index.equals(y.index)
    assert flags["stale"].loc[dates[1], "AAA"]


def test_short_history_ticker_is_nan() -> None:
    rng = np.random.default_rng(5)
    idx = pd.bdate_range("2015-01-02", periods=100)
    factors = pd.DataFrame({"mkt_rf": rng.normal(0, 0.01, len(idx))}, index=idx)
    y = pd.DataFrame(
        {
            "LONG": 1.0 * factors["mkt_rf"] + rng.normal(0, 0.01, len(idx)),
            "SHORT": 1.0 * factors["mkt_rf"] + rng.normal(0, 0.01, len(idx)),
        },
        index=idx,
    )
    y.loc[idx[:50], "SHORT"] = np.nan
    out = ts.fit_factor_model(y, factors, min_obs=60)
    assert np.isnan(out["loadings"].loc["SHORT", "mkt_rf"])
    assert not np.isnan(out["loadings"].loc["LONG", "mkt_rf"])
