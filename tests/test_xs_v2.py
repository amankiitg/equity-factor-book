"""Sprint E5 Task 1: XS-v2, the residual-covariance version.

Four acceptance tests: the residual block is positive definite, it reproduces
XS-v1's diagonal when k is zero, it captures at least as much specific variance
as the diagonal on the same window, and the stored k matches the
Marchenko-Pastur count the project already uses.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb.models import statistical as st

ROOT = Path(__file__).resolve().parents[1]
XS_V2 = ROOT / "data" / "models" / "XS-v2"


def synthetic_specific(
    n_days: int = 504, n_names: int = 60, seed: int = 11
) -> pd.DataFrame:
    """Specific returns with a common component strong enough to clear the
    Marchenko-Pastur edge at this N and T, and a known diagonal target."""
    rng = np.random.default_rng(seed)
    factor = rng.normal(0.0, 0.04, size=n_days)
    loadings = rng.normal(0.0, 0.02, size=n_names)
    noise = rng.normal(0.0, 0.004, size=(n_days, n_names))
    values = factor[:, None] * loadings + noise
    frame = pd.DataFrame(
        values,
        index=pd.date_range("2023-01-03", periods=n_days, freq="B"),
        columns=[f"N{i}" for i in range(n_names)],
    )
    return frame


def test_the_residual_block_is_positive_definite() -> None:
    block = synthetic_specific()
    diagonal = pd.Series(0.0001, index=block.columns)
    fitted = st.residual_covariance(block, diagonal)
    assert fitted.k >= 1, "a one-factor specific block must keep at least one factor"
    matrix = fitted.matrix()
    assert np.linalg.eigvalsh(matrix).min() > 0
    assert np.allclose(matrix, matrix.T, atol=1e-14)
    # the diagonal never falls below D: the remainder only ever shrinks
    assert np.all(np.diag(matrix) >= fitted.diagonal - 1e-14)


def test_k_zero_reproduces_the_diagonal() -> None:
    block = synthetic_specific()
    diagonal = pd.Series(np.linspace(0.5e-4, 2e-4, block.shape[1]), index=block.columns)
    fitted = st.residual_covariance(block, diagonal, k=0)
    assert fitted.k == 0
    assert np.allclose(fitted.matrix(), np.diag(diagonal.to_numpy()), atol=1e-14)


def test_the_residual_block_captures_at_least_as_much_specific_variance() -> None:
    block = synthetic_specific()
    diagonal = pd.Series(0.0001, index=block.columns)
    fitted = st.residual_covariance(block, diagonal)
    values = block.to_numpy(dtype=float)
    demeaned = values - values.mean(axis=0)
    realized = demeaned.T @ demeaned / len(demeaned)
    diagonal_model = np.diag(diagonal.to_numpy())
    miss_diagonal = float(np.linalg.norm(realized - diagonal_model, ord="fro"))
    miss_residual = float(np.linalg.norm(realized - fitted.matrix(), ord="fro"))
    assert miss_residual < miss_diagonal, (
        "the low-rank block must sit closer to the realized specific covariance "
        "than the diagonal does"
    )
    assert fitted.trace_total >= fitted.trace_diagonal - 1e-14


@pytest.mark.integration
def test_the_stored_k_matches_the_mp_count() -> None:
    if not (XS_V2 / "residual_factors.parquet").exists():
        pytest.skip("XS-v2 has not been built yet")
    summary = pd.read_parquet(XS_V2 / "residual_factors.parquet")
    specific = pd.read_parquet(
        ROOT / "data" / "models" / "XS-v1" / "specific_returns.parquet"
    )
    specific_var = pd.read_parquet(
        ROOT / "data" / "models" / "XS-v1" / "specific_var.parquet"
    )
    wide = specific.pivot(index="date", columns="ticker", values="specific_return")
    diagonal_by_date = {
        date: group.set_index("ticker")["specific_var"]
        for date, group in specific_var.groupby("date")
    }
    sample = summary.sample(n=5, random_state=5)
    for row in sample.itertuples():
        block = st.complete_block(wide, as_of=row.date, window=504)
        diagonal = diagonal_by_date[row.date].reindex(block.columns)
        assert not diagonal.isna().any()
        fitted = st.residual_covariance(block, diagonal)
        assert fitted.k == row.k, (
            f"stored k {row.k} differs from the recomputed MP count {fitted.k} "
            f"at {row.date.date()}"
        )


@pytest.mark.integration
def test_the_stored_blocks_rebuild_positive_definite_covariances() -> None:
    if not (XS_V2 / "residual_loadings.parquet").exists():
        pytest.skip("XS-v2 has not been built yet")
    loadings = pd.read_parquet(XS_V2 / "residual_loadings.parquet")
    remainder = pd.read_parquet(XS_V2 / "residual_remainder.parquet")
    dates = loadings["date"].unique()
    for date in dates[:3]:
        block = loadings.loc[loadings["date"] == date]
        rest = remainder.loc[remainder["date"] == date].set_index("ticker")["remainder"]
        tickers = list(block["ticker"].unique())
        scaled = block.pivot(index="ticker", columns="factor", values="scaled_loading")
        values = block.groupby("factor")["eigenvalue"].first()
        low = scaled.to_numpy() @ np.diag(values.to_numpy()) @ scaled.to_numpy().T
        matrix = low + np.diag(rest.reindex(tickers).to_numpy())
        assert np.linalg.eigvalsh(matrix).min() > 0, f"block at {date.date()} is not PD"
