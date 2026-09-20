"""Sprint E4 Task 1: the statistical factor model.

The algebra is tested on a synthetic block with a known factor structure, so a
failure points at the estimator rather than at the data. One integration test
runs the real panel and asserts the stored counts against the Marchenko-Pastur
arithmetic.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb.models import statistical as st

ROOT = Path(__file__).resolve().parents[1]


def synthetic_block(
    n_days: int = 400, n_names: int = 120, seed: int = 11
) -> pd.DataFrame:
    """Two common factors plus noise, on a business-day index."""
    rng = np.random.default_rng(seed)
    factors = rng.normal(0.0, 1.0, size=(n_days, 2))
    loadings = rng.normal(0.0, 0.6, size=(n_names, 2))
    noise = rng.normal(0.0, 0.5, size=(n_days, n_names))
    values = factors @ loadings.T + noise
    index = pd.bdate_range("2020-01-01", periods=n_days)
    return pd.DataFrame(
        values, index=index, columns=[f"N{i:03d}" for i in range(n_names)]
    )


def test_standardize_gives_zero_mean_and_unit_variance() -> None:
    block = synthetic_block()
    z, mean, std = st.standardize(block)
    assert np.allclose(z.mean(axis=0), 0.0, atol=1e-12)
    assert np.allclose(z.var(axis=0, ddof=1), 1.0, atol=1e-10)
    assert len(mean) == block.shape[1] and len(std) == block.shape[1]


def test_eigendecomposition_reproduces_the_correlation_matrix() -> None:
    block = synthetic_block()
    fit = st.fit(block)
    z, _, _ = st.standardize(block)
    sample = z.T @ z / len(block)
    rebuilt = fit.eigenvectors @ np.diag(fit.eigenvalues) @ fit.eigenvectors.T
    assert np.max(np.abs(sample - rebuilt)) < 1e-10
    assert fit.eigenvalues[0] > fit.eigenvalues[-1], "the spectrum is sorted descending"


def test_mp_edge_follows_the_formula() -> None:
    block = synthetic_block()
    fit = st.fit(block)
    expected = (1.0 + np.sqrt(fit.n_names / fit.n_days)) ** 2
    assert fit.mp_edge == pytest.approx(expected, rel=1e-12)
    assert st.mp_edge(473, 504) == pytest.approx(3.876, abs=5e-4)


def test_factor_returns_have_unit_exposure_and_the_eigenvalue_variance() -> None:
    block = synthetic_block()
    fit = st.fit(block)
    z, _, _ = st.standardize(block)
    values = fit.factor_returns(z, 3)
    assert np.allclose(
        values.T @ values / len(block), np.diag(fit.eigenvalues[:3]), atol=1e-10
    )
    loadings = fit.loadings(3)
    assert np.allclose(loadings.T @ loadings, np.eye(3), atol=1e-10)


def test_the_factor_covariance_has_the_right_trace_and_positive_residuals() -> None:
    block = synthetic_block()
    fit = st.fit(block)
    sigma = fit.covariance(5)
    residual = fit.residual_variance(5)
    assert (residual > 0).all()
    assert np.trace(sigma) == pytest.approx(fit.n_names, rel=1e-9)
    assert np.allclose(sigma, sigma.T, atol=1e-12)
    assert (
        np.linalg.eigvalsh(sigma).min() > 0
    ), "the covariance must be positive definite"


def test_scree_finds_the_elbow_after_the_leading_gap() -> None:
    # a spectrum with a clear elbow at four factors
    eigenvalues = np.array([50.0, 40.0, 30.0, 20.0, 2.0, 1.8, 1.5, 1.2, 1.0])
    block = synthetic_block(n_days=100, n_names=9)
    fit = st.fit(block)
    fit.eigenvalues = eigenvalues
    assert st.count_scree(fit) == 4


def test_cross_validated_likelihood_selects_the_best_of_its_grid() -> None:
    block = synthetic_block(n_days=300, n_names=60)
    best, scores = st.count_cv(block, ks=(1, 2, 3, 4, 6, 8), n_folds=3)
    assert best in scores
    assert scores[best] == max(scores.values())
    assert len(scores) == 6


def test_complete_block_keeps_whole_names_and_the_window_length() -> None:
    block = synthetic_block(n_days=600, n_names=10)
    block.iloc[-10, 0] = np.nan  # the hole is inside the 504-day window
    out = st.complete_block(block, as_of=block.index[-1], window=504)
    assert len(out) == 504
    assert out.shape[1] == 9, "the name with a hole is dropped, not imputed"
    assert out.notna().all().all()


@pytest.mark.integration
def test_the_real_panel_counts_match_the_stored_probe_arithmetic() -> None:
    returns = pd.read_parquet(ROOT / "data" / "processed" / "returns.parquet")
    sectors = pd.read_parquet(ROOT / "data" / "processed" / "sectors.parquet")
    mapped = set(sectors["ticker"])
    wide = st.clean_wide(returns)
    block = st.complete_block(
        wide[[c for c in wide.columns if c in mapped]], as_of=pd.Timestamp("2026-09-03")
    )
    fit = st.fit(block)
    assert fit.n_names == 494 and fit.n_days == 504
    assert fit.n_over_t == pytest.approx(0.9802, abs=5e-4)
    assert fit.mp_edge == pytest.approx(3.9602, abs=5e-4)
    assert st.count_mp(fit) == 13, "the model universe count must stay inside 3 to 15"


@pytest.mark.integration
def test_residual_pca_reports_a_factor_above_its_own_edge() -> None:
    returns = pd.read_parquet(ROOT / "data" / "processed" / "returns.parquet")
    specific = pd.read_parquet(
        ROOT / "data" / "models" / "XS-v1" / "specific_returns.parquet"
    )
    sectors = pd.read_parquet(ROOT / "data" / "processed" / "sectors.parquet")
    frames = st.run(
        returns,
        specific,
        as_of=pd.Timestamp("2026-09-03"),
        tickers=list(sectors["ticker"]),
        label="model",
    )
    audit = frames["residual_diagnostics"]
    assert audit["above_edge"] is True, "XS-v1 residuals carry common structure"
    assert audit["largest_eigenvalue"] > audit["edge"]
    assert audit["largest_eigenvalue"] == pytest.approx(22.3031, abs=1e-3)
    counts = audit["counts"]
    assert counts.marchenko_pastur > 15
