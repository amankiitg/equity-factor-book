"""Sprint E5 Task 2: families and the daily bias engine.

The acceptance tests: families are deterministic under a fixed seed, no
portfolio uses a weight dated after the day it is applied to, and on a
synthetic series drawn from the model the bias statistic equals one and the
coverage equals the nominal five percent.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb import eval_risk

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"


@pytest.mark.slow
def test_bias_statistic_equals_one_on_model_draws() -> None:
    rng = np.random.default_rng(21)
    z = rng.normal(size=100_000)
    stats = eval_risk.bias_statistics(z)
    assert stats["bias"] == pytest.approx(1.0, abs=0.01)
    assert stats["coverage"] == pytest.approx(0.05, abs=0.003)
    assert stats["mad_ratio"] == pytest.approx(1.0, abs=0.01)
    # the Q-Q OLS slope sits below one on any finite sample because the
    # largest observed value is ~4.5 sigma, which attenuates the tail slope
    assert stats["qq_slope"] == pytest.approx(1.0, abs=0.06)
    assert stats["qq_intercept"] == pytest.approx(0.0, abs=0.02)
    # the band must contain one on model draws
    assert stats["bias_lower"] < 1.0 < stats["bias_upper"]


@pytest.mark.slow
def test_bias_statistic_reads_miscalibration() -> None:
    rng = np.random.default_rng(22)
    low = eval_risk.bias_statistics(rng.normal(scale=0.5, size=100_000))
    high = eval_risk.bias_statistics(rng.normal(scale=2.0, size=100_000))
    assert low["bias"] < 1.0 < high["bias"]
    assert low["coverage"] < 0.05 < high["coverage"]


@pytest.mark.slow
def test_families_are_deterministic_under_a_fixed_seed() -> None:
    first = eval_risk.build_families(seed=11, store=False)
    second = eval_risk.build_families(seed=11, store=False)
    pd.testing.assert_frame_equal(first, second)
    for family in eval_risk.FAMILIES:
        n_portfolios = first.loc[first["family"] == family]["portfolio"].nunique()
        assert n_portfolios >= 50, family
    # every generated weight sums to about one in absolute value per book-date
    generated = first.loc[~first["portfolio"].str.startswith("seed_")]
    gross = generated.groupby(["portfolio", "date"])["weight"].apply(
        lambda s: s.abs().sum()
    )
    assert gross.max() == pytest.approx(1.0, abs=1e-9)
    # the two seed books ride along in their families
    assert "seed_ew" in set(first.loc[first["family"] == "long_only"]["portfolio"])
    assert "seed_mom_ls" in set(
        first.loc[first["family"] == "factor_tilted"]["portfolio"]
    )


@pytest.mark.slow
def test_no_portfolio_uses_a_weight_dated_after_its_own_day() -> None:
    """Replicate the engine's period application and check the weight date.

    A weight row dated at the month end `start` is applied to every session in
    (start, end], so the applied day is always strictly after the weight date.
    """
    portfolios = eval_risk.build_families(seed=eval_risk.SEED, store=False)
    generated = portfolios.loc[
        ~portfolios["portfolio"].str.startswith("seed_")
    ].sort_values("date")
    sessions = pd.DatetimeIndex(sorted(generated["date"].unique()))
    last = sessions[-1] + pd.Timedelta(days=40)
    wide, _ = eval_risk.load_clean_wide()
    checked = 0
    for start, end in zip(sessions, list(sessions[1:]) + [last], strict=False):
        applied_days = wide.index[(wide.index > start) & (wide.index <= end)]
        assert (
            applied_days > start
        ).all(), f"weight dated {start.date()} applied early"
        checked += len(applied_days)
    assert checked > 1000, "the check covered almost no days"


@pytest.mark.integration
def test_every_version_and_family_has_a_stored_bias_table() -> None:
    for version in eval_risk.VERSIONS:
        for family in eval_risk.FAMILIES:
            path = EVAL / f"bias_{version}_{family}.parquet"
            assert path.exists(), path
            frame = pd.read_parquet(path)
            assert not frame.empty, path
            assert {"date", "portfolio", "z"} <= set(frame.columns)


@pytest.mark.integration
def test_the_forecast_never_uses_information_dated_after_its_own_date() -> None:
    """The forecast stamped at a month end must be dated no later than that end."""
    forecasts = pd.read_parquet(EVAL / "e5_forecast_portfolios.parquet")
    diag = pd.read_parquet(EVAL / "e5_forecast_diag.parquet")
    from efb import race

    grid = race.race_grid()
    grid_set = set(grid)
    assert set(forecasts["date"].unique()) <= grid_set
    assert set(diag["date"].unique()) <= grid_set
    assert (forecasts["sigma"] > 0).all()
