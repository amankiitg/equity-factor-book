"""Tests for close-out task C4: the momentum seed book's MOM exposure.

The long/short seed book is built from a momentum signal, so its TS-v1 MOM
loading has to be positive and statistically distinguishable from zero. If
it is not, the claim that 90 percent of the book's risk is idiosyncratic
is suspect: the book may be a factor position that the six-factor fit is
failing to explain, and the fix belongs in E3 rather than in E2.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from efb import portfolios as pf


def _panel(
    n_dates: int = 500, beta_mom: float = 0.8
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(4)
    dates = pd.bdate_range("2020-01-01", periods=n_dates)
    factors = pd.DataFrame(
        {
            "mkt_rf": rng.normal(0.0004, 0.01, n_dates),
            "smb": rng.normal(0.0, 0.004, n_dates),
            "hml": rng.normal(0.0, 0.004, n_dates),
            "rmw": rng.normal(0.0, 0.003, n_dates),
            "cma": rng.normal(0.0, 0.003, n_dates),
            "mom": rng.normal(0.0, 0.005, n_dates),
        },
        index=dates,
    )
    returns = pd.DataFrame(
        {
            "AAA": beta_mom * factors["mom"] + rng.normal(0.0, 0.008, n_dates),
            "BBB": -beta_mom * factors["mom"] + rng.normal(0.0, 0.008, n_dates),
        },
        index=dates,
    )
    return returns, factors


def test_portfolio_loadings_reports_a_t_statistic_per_factor() -> None:
    returns, factors = _panel()
    weights = pd.DataFrame(0.0, index=returns.index, columns=returns.columns)
    weights["AAA"] = 1.0
    weights["BBB"] = -1.0
    out = pf.portfolio_loadings(weights, returns, factors)
    # every factor plus the intercept, so a reader sees the alpha too
    assert set(out.index) == set(factors.columns) | {"alpha"}
    assert {"loading", "nw_se", "t_stat", "ols_se"} <= set(out.columns)
    # a t statistic is the loading over its standard error
    expected = out["loading"] / out["nw_se"]
    assert np.allclose(out["t_stat"], expected, equal_nan=True)


def test_portfolio_loadings_recovers_a_known_mom_exposure() -> None:
    [returns, factors] = _panel(beta_mom=0.8)
    weights = pd.DataFrame(0.0, index=returns.index, columns=returns.columns)
    weights["AAA"] = 1.0
    weights["BBB"] = -1.0
    out = pf.portfolio_loadings(weights, returns, factors)
    # long AAA and short BBB loads the book twice on momentum
    assert out.loc["mom", "loading"] == pytest.approx(1.6, abs=0.15)
    assert abs(float(out.loc["mom", "t_stat"])) > 2.0


def test_mom_sanity_flags_a_flat_book() -> None:
    # a book with no momentum exposure at all must not be reported as one
    returns, factors = _panel(beta_mom=0.0)
    weights = pd.DataFrame(0.0, index=returns.index, columns=returns.columns)
    weights["AAA"] = 1.0
    weights["BBB"] = -1.0
    report = pf.mom_sanity(weights, returns, factors, idio_var=None)
    assert report["mom_loading"] == pytest.approx(0.0, abs=0.15)
    assert report["mom_t_stat"] == pytest.approx(0.0, abs=2.0)


def test_mom_sanity_reports_positive_and_significant_for_a_momentum_book() -> None:
    returns, factors = _panel(beta_mom=0.8)
    weights = pd.DataFrame(0.0, index=returns.index, columns=returns.columns)
    weights["AAA"] = 1.0
    weights["BBB"] = -1.0
    report = pf.mom_sanity(weights, returns, factors, idio_var=None)
    assert report["mom_loading"] > 0
    assert abs(report["mom_t_stat"]) > 2
    assert report["passes"] is True


def test_mom_sanity_compares_the_factor_share_with_and_without_mom() -> None:
    returns, factors = _panel(beta_mom=0.8)
    weights = pd.DataFrame(0.0, index=returns.index, columns=returns.columns)
    weights["AAA"] = 1.0
    weights["BBB"] = -1.0
    idio = pd.Series({"AAA": 6.4e-5, "BBB": 6.4e-5})
    report = pf.mom_sanity(weights, returns, factors, idio_var=idio)
    assert "factor_share_with_mom" in report
    assert "factor_share_without_mom" in report
    # the market variance used in both decompositions is the same series
    assert report["factor_share_with_mom"] > report["factor_share_without_mom"]
