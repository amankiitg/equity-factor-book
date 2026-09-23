"""Sprint E8 Task 1 to 6: the synthetic alpha and the sizing rules.

The synthetic input is a controlled experiment, never a backtest: every
assertion here is about the machinery, not about a tradable edge.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb import size

ROOT = Path(__file__).resolve().parents[1]


def _small_pieces() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """A tiny factor model the unit tests exercise."""
    rng = np.random.default_rng(0)
    n = 50
    design = np.column_stack([np.ones(n), rng.normal(size=(n, 2))])
    factor_covariance = np.eye(3) * 0.04
    specific = np.full(n, 0.02)
    alpha = rng.normal(size=n)
    return design, factor_covariance, specific, alpha


def test_proportional_and_sharpe_coincide_under_the_diagonal_model() -> None:
    design, factor_covariance, specific, alpha = _small_pieces()
    proportional = size.proportional(alpha, specific)
    sharpe = size.sharpe_rule(alpha, specific)
    assert np.allclose(proportional, sharpe)


def test_vol_target_hits_the_target() -> None:
    design, factor_covariance, specific, alpha = _small_pieces()
    weights = size._vol_target(
        size.proportional(alpha, specific), design, factor_covariance, specific
    )
    variance = float(
        weights @ design @ factor_covariance @ design.T @ weights
        + weights @ (specific * weights)
    )
    assert np.isclose(np.sqrt(variance), size.TARGET_VOL, rtol=1e-9)


def test_procedure_6_3_removes_factor_exposure() -> None:
    design, factor_covariance, specific, alpha = _small_pieces()
    weights = size.procedure_6_3(alpha, design, factor_covariance, specific)
    exposure = design.T @ weights
    assert np.abs(exposure).max() < 1e-9


def test_mv_unconstrained_equals_proportional_when_alpha_is_factor_free() -> None:
    design, factor_covariance, specific, alpha = _small_pieces()
    # a scalar-D model: orthogonalize alpha against the design so the
    # identity Sigma^-1 alpha = D^-1 alpha holds exactly
    residual = alpha - design @ np.linalg.solve(design.T @ design, design.T @ alpha)
    mv = size._sigma_inverse_alpha(residual, design, factor_covariance, specific)
    proportional = size.proportional(residual, specific)
    a = mv / np.abs(mv).sum()
    b = proportional / np.abs(proportional).sum()
    assert np.abs(a - b).max() < 1e-6


@pytest.mark.integration
@pytest.mark.slow
def test_synthetic_alpha_ic_is_close_to_rho() -> None:
    frame = size.synthetic_alpha(size.DATA_ROOT, rho=0.05, seed=0)
    assert not frame.empty
    measured = float(frame.groupby("date")["ic"].mean().mean())
    assert abs(measured - 0.05) < 0.05
    assert (frame["source"] == "synthetic controlled experiment").all()


@pytest.mark.integration
def test_the_construction_artifacts_are_written() -> None:
    summary_path = ROOT / "data" / "portfolios" / "e8_summary.parquet"
    if not summary_path.exists():
        pytest.skip("the E8 run has not completed")
    summary = pd.read_parquet(summary_path)
    assert {"construction", "rho", "seed", "realized_ir", "mean_n_eff"} <= set(
        summary.columns
    )
    assert set(summary["construction"]) == set(size.CONSTRUCTIONS)
