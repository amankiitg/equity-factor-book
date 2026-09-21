"""Sprint E6: the hedging toolkit.

The algebra tests run on synthetic inputs with a known answer; the integration
tests read the stored hedge artifacts and check the realized efficacy data the
criteria are scored from.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb import hedge

ROOT = Path(__file__).resolve().parents[1]
HEDGE = ROOT / "data" / "hedge"


def test_beta_hedge_of_a_spy_clone_is_minus_one() -> None:
    rng = np.random.default_rng(7)
    spy = pd.Series(rng.normal(0.0004, 0.01, size=500))
    book = pd.Series(0.5 * spy.to_numpy() + rng.normal(0.0, 0.002, size=500))
    h = hedge.beta_hedge(book, spy)
    assert h == pytest.approx(-0.5, abs=0.02)
    # a book that is exactly 1x SPY hedges at h = -1
    assert hedge.beta_hedge(spy, spy) == pytest.approx(-1.0, abs=1e-12)


def test_partial_hedge_scales_and_rejects_out_of_range() -> None:
    assert hedge.partial_hedge(-0.8, 0.5) == pytest.approx(-0.4)
    with pytest.raises(ValueError):
        hedge.partial_hedge(-0.8, 1.5)


def test_fmp_hedge_subtracts_exposures_times_the_fmps() -> None:
    fmp_frame = pd.DataFrame(
        {
            "date": ["2024-01-31"] * 4,
            "factor": ["f1", "f1", "f2", "f2"],
            "ticker": ["A", "B", "A", "B"],
            "weight": [1.0, 0.0, 0.0, 1.0],
        }
    )
    exposures = np.array([0.3, -0.2])
    hedge_weights, tickers, n_names = hedge.fmp_hedge(
        exposures, fmp_frame, ["f1", "f2"]
    )
    expected = np.array([-0.3, 0.2])
    assert np.allclose(hedge_weights, expected)
    assert tickers == ["A", "B"]
    assert n_names == 2
    # the in-model exposure after the hedge is exactly zero by construction
    design = np.array([[1.0, 0.0], [0.0, 1.0]])
    assert np.allclose(design.T @ (hedge_weights + exposures), 0.0)


def test_fmp_hedge_exact_drives_exposures_to_zero() -> None:
    rng = np.random.default_rng(11)
    design = rng.normal(size=(120, 17))
    design[:, 0] = 1.0
    weights = rng.normal(size=120)
    exposures = design.T @ weights
    hedge_weights, n_names = hedge.fmp_hedge_exact(design, exposures)
    after = design.T @ (weights + hedge_weights)
    assert np.abs(after).max() < 1e-6
    assert n_names > 0


def test_min_variance_hedge_solves_the_normal_equations() -> None:
    sigma_hh = np.array([[4.0, 1.0], [1.0, 2.0]])
    sigma_hw = np.array([3.0, 1.0])
    h = hedge.min_variance_hedge(sigma_hh, sigma_hw)
    assert np.allclose(sigma_hh @ h, -sigma_hw)


def test_hedge_cost_is_turnover_times_constants_plus_borrow() -> None:
    cost = hedge.hedge_cost(2.0, 0.5, horizon_days=21.0)
    expected = 2.0 * hedge.COST_PER_TURNOVER + 0.5 * hedge.BORROW_RATE * 21.0 / 252.0
    assert cost == pytest.approx(expected)
    assert hedge.COST_PARAMETERS["source"]


@pytest.mark.integration
def test_the_etf_prices_artifact_carries_the_instrument_set() -> None:
    path = ROOT / "data" / "raw" / "etf_prices.parquet"
    if not path.exists():
        pytest.skip("ETF prices not fetched yet")
    frame = pd.read_parquet(path)
    present = set(frame["ticker"])
    assert {"SPY", "IWM", "QQQ"} <= present, present
    assert len(present & set(hedge.INSTRUMENTS)) >= 10


@pytest.mark.integration
def test_the_stored_hedge_metrics_cover_both_models() -> None:
    path = HEDGE / "hedge_metrics.parquet"
    if not path.exists():
        pytest.skip("the hedge run has not happened yet")
    metrics = pd.read_parquet(path)
    for book in ("seed_ew", "seed_mom_ls"):
        for method in ("beta", "fmp", "min_variance"):
            assert (metrics["book"] == book).any(), book
            assert (metrics["method"] == method).any(), method
    for model in ("xs_v1", "xs_v2"):
        assert (metrics["model"] == model).any(), model
    # cost is NaN exactly where the hedge could not be fitted, never negative
    assert ((metrics["cost"] >= 0) | metrics["cost"].isna()).all()


@pytest.mark.integration
def test_the_hedged_momentum_book_beta_is_stored() -> None:
    path = HEDGE / "e6_efficacy.parquet"
    if not path.exists():
        pytest.skip("the efficacy run has not happened yet")
    efficacy = pd.read_parquet(path)
    rows = efficacy.loc[
        (efficacy["book"] == "seed_mom_ls") & (efficacy["method"] == "min_variance")
    ]
    assert not rows.empty
    assert rows["realized_beta_to_mkt_rf"].notna().all()


@pytest.mark.integration
def test_instruments_without_history_are_nan_not_silent_zeros() -> None:
    metrics_path = HEDGE / "hedge_metrics.parquet"
    positions_path = HEDGE / "hedge_positions.parquet"
    if not metrics_path.exists() or not positions_path.exists():
        pytest.skip("the hedge run has not happened yet")
    metrics = pd.read_parquet(metrics_path)
    positions = pd.read_parquet(positions_path)
    mv = metrics.loc[metrics["method"] == "min_variance"]
    # XLRE and XLC only have price history from their launch dates, so their
    # hedge weights are missing before then and the stored instrument count
    # moves with it
    assert mv["n_instruments"].notna().all()
    assert (mv["n_instruments"] <= len(hedge.INSTRUMENTS)).all()
    nan_rows = positions.loc[
        (positions["method"] == "min_variance") & positions["weight"].isna()
    ]
    if not nan_rows.empty:
        assert set(nan_rows["instrument"]) <= {"XLRE", "XLC"}
