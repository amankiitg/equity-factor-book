"""Tests for Task 5: the performance-metrics library efb/perf.py."""

import numpy as np
import pandas as pd
import pytest

from efb import perf


def test_sharpe_ratio_daily_and_annualized() -> None:
    rng = np.random.default_rng(0)
    x = pd.Series(rng.normal(0.0005, 0.01, 10_000))
    daily = perf.sharpe_ratio(x)
    assert daily == pytest.approx(x.mean() / x.std(ddof=1), abs=1e-12)
    assert perf.annualized_sharpe(x) == pytest.approx(daily * np.sqrt(252), abs=1e-10)


def test_sharpe_se_iid_matches_closed_form() -> None:
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(0.0005, 0.01, 20_000))
    sr = perf.sharpe_ratio(x)
    expected = np.sqrt((1 + sr**2 / 2) / len(x))
    assert perf.sharpe_se_iid(x) == pytest.approx(expected, abs=1e-12)


def test_sharpe_se_lo_reduces_to_iid_without_autocorrelation() -> None:
    rng = np.random.default_rng(2)
    x = pd.Series(rng.normal(0.0005, 0.01, 50_000))
    lo = perf.sharpe_se_lo2002(x, q=5)
    iid = perf.sharpe_se_iid(x)
    assert lo == pytest.approx(iid, rel=0.05)


def test_sharpe_se_lo_grows_with_positive_autocorrelation() -> None:
    rng = np.random.default_rng(3)
    noise = rng.normal(0.0, 0.01, 50_000)
    x = pd.Series(0.0004 + 0.2 * pd.Series(noise).shift(1).fillna(0.0) + noise)
    lo = perf.sharpe_se_lo2002(x, q=5)
    iid = perf.sharpe_se_iid(x)
    assert lo > iid * 1.05  # positive lag-1 autocorrelation widens the SE


def test_max_drawdown_known_path() -> None:
    wealth = pd.Series([100.0, 110.0, 99.0, 105.0, 95.0, 120.0])
    dd = perf.drawdown_series(wealth)
    assert dd.iloc[2] == pytest.approx(99.0 / 110.0 - 1.0)
    assert perf.max_drawdown(wealth) == pytest.approx(95.0 / 110.0 - 1.0)


def test_hit_rate_and_slugging() -> None:
    x = pd.Series([0.01, -0.005, 0.02, -0.01, 0.03])
    assert perf.hit_rate(x) == pytest.approx(0.6)
    wins = (0.01 + 0.02 + 0.03) / 3
    losses = (0.005 + 0.01) / 2
    assert perf.slugging_ratio(x) == pytest.approx(wins / losses)
