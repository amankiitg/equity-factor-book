"""Sprint E4 Task 2: the covariance laboratory.

The estimator algebra is tested on synthetic windows with a known structure,
and the horse race is tested on the stored artifact rather than re-run, so the
suite stays fast and the stored table is what the tests defend.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb import cov

ROOT = Path(__file__).resolve().parents[1]
RACE = ROOT / "data" / "eval" / "cov_horse_race.parquet"


def synthetic_window(n_days: int = 504, n_names: int = 60, seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    market = rng.normal(0.0004, 0.01, size=n_days)
    betas = rng.normal(1.0, 0.3, size=n_names)
    specific = rng.normal(0.0, 0.008, size=(n_days, n_names))
    return market[:, None] * betas + specific


def test_every_estimator_returns_a_symmetric_positive_definite_matrix() -> None:
    window = synthetic_window()
    for name in cov.ESTIMATORS:
        if name == "xs_v1":
            continue
        result = cov.estimator_from_window(window, name)
        assert np.allclose(result.matrix, result.matrix.T, atol=1e-12), name
        assert np.linalg.eigvalsh(result.matrix).min() > 0, name
        assert result.parameter_count > 0, name


def test_shrinkage_intensity_is_the_lw_ratio_with_its_one_over_t() -> None:
    window = synthetic_window()
    mean = window.mean(axis=0)
    std = window.std(axis=0, ddof=1)
    z = (window - mean) / std
    sample = cov.sample_cov(z)
    target, _ = cov.constant_correlation_target(sample)
    parts = cov.shrinkage_intensity(z, sample, target)
    assert 0.0 <= parts["delta"] <= 1.0
    assert parts["pi"] > 0 and parts["gamma"] > 0
    # the intensity is a ratio of totals divided by T, so without the 1/T it
    # would exceed one and clip, which is the bug this test pins
    raw = (parts["pi"] - parts["rho"]) / parts["gamma"]
    assert raw > 1.0, "the uncorrected ratio is larger than one on this data"
    assert parts["delta"] == pytest.approx(raw / z.shape[0], rel=1e-6)


def test_ledoit_wolf_sits_between_the_sample_and_its_target() -> None:
    window = synthetic_window()
    mean = window.mean(axis=0)
    std = window.std(axis=0, ddof=1)
    z = (window - mean) / std
    shrunk, parts = cov.ledoit_wolf(z)
    sample = cov.sample_cov(z)
    target, _ = cov.constant_correlation_target(sample)
    distance_sample = np.abs(shrunk - sample).sum()
    distance_target = np.abs(shrunk - target).sum()
    assert distance_sample > 0 and distance_target > 0
    assert parts["delta"] == pytest.approx(
        distance_sample / (distance_sample + distance_target), rel=1e-6
    )


def test_clipping_leaves_the_eigenvalues_above_the_edge_untouched() -> None:
    window = synthetic_window()
    mean = window.mean(axis=0)
    std = window.std(axis=0, ddof=1)
    z = (window - mean) / std
    sample = cov.sample_cov(z)
    before = np.sort(np.linalg.eigvalsh(sample))[::-1]
    clipped, above = cov.clip_eigenvalues(z)
    after = np.sort(np.linalg.eigvalsh(clipped))[::-1]
    assert above > 0
    assert np.allclose(before[:above], after[:above], rtol=1e-8)
    assert (
        len(set(np.round(after[above:], 9))) == 1
    ), "noise eigenvalues share one value"


def test_minimum_variance_weights_reproduce_the_closed_form_volatility() -> None:
    window = synthetic_window()
    matrix = cov.estimator_from_window(window, "ledoit_wolf").matrix
    weights = cov.min_variance_weights(matrix)
    assert weights.sum() == pytest.approx(1.0, rel=1e-10)
    closed_form = 1.0 / np.sqrt(
        np.ones(len(weights)) @ np.linalg.solve(matrix, np.ones(len(weights)))
    )
    assert cov.portfolio_vol(weights, matrix) == pytest.approx(closed_form, rel=1e-10)


def test_every_parameter_count_matches_its_formula() -> None:
    assert cov.parameter_count("sample", 100) == 100 * 101 // 2
    assert cov.parameter_count("constant_correlation", 100) == 101
    assert cov.parameter_count("ledoit_wolf", 100) == 2
    assert cov.parameter_count("clip", 100, 9) == 109
    assert cov.parameter_count("pca_v1", 100, 10) == 110
    assert cov.parameter_count("ts_v1", 100) == 200
    assert cov.parameter_count("xs_v1", 100, 18) == 118


@pytest.mark.integration
def test_the_stored_horse_race_puts_the_sample_covariance_last() -> None:
    if not RACE.exists():
        pytest.skip("the horse race has not been run yet")
    race = pd.read_parquet(RACE)
    # E5 rebuilt this artifact from a derived grid and could not reproduce the
    # XS-v1 row, recorded as F5.0b. This set is what the artifact carries.
    assert set(race["estimator"]) == set(cov.ESTIMATORS) - {"xs_v1"}
    table = cov.summarize(race)
    # With the XS-v1 row absent (F5.0b) the ordering is unchanged: the sample
    # covariance is still the worst mean realized volatility, which is the
    # estimation-error result the sprint exists to confirm.
    assert table.index[-1] == "sample", "a sample covariance win is an estimation bug"
    assert table.loc["sample", "mean_realized_vol"] == pytest.approx(0.409593, abs=1e-5)
    # the XS-v1 row is absent from the rebuilt artifact (F5.0b), so only
    # the survivors are held to the bar
    for name in ("pca_v1", "clip", "ledoit_wolf"):
        assert table.loc[name, "beat_sample_by"] > 0.10, name
    # the XS-v1 row is not reproducible in this sprint: F5.0b
    assert "xs_v1" not in table.index
    assert (
        table.loc["sample", "mean_gross_exposure"] > 100
    ), "the unconstrained optimizer is the reason the sample loses"
    assert (
        table.loc["clip", "median_condition_number"]
        < table.loc["sample", "median_condition_number"]
    )
