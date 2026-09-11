"""Tests for Task 7: dashboard D1 panel builders (parquet in, tables out)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dashboard.tabs import d01_exposures


def _loadings() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "alpha": [0.0001, 0.0002],
            "mkt_rf": [1.1, 0.7],
            "smb": [0.2, -0.1],
            "hml": [0.0, 0.1],
            "rmw": [0.1, 0.0],
            "cma": [-0.2, 0.05],
            "mom": [0.05, -0.02],
            "r_squared": [0.45, 0.30],
        },
        index=["AAA", "BBB"],
    )


def _se() -> pd.DataFrame:
    cols = pd.MultiIndex.from_product(
        [["ols", "nw_l5"], ["mkt_rf", "smb"]], names=["method", "statistic"]
    )
    return pd.DataFrame(
        [[0.02, 0.03, 0.04, 0.05], [0.02, 0.04, 0.025, 0.045]],
        index=["AAA", "BBB"],
        columns=cols,
    )


def test_loadings_table_merges_betas_and_nw_se() -> None:
    table = d01_exposures.loadings_table(_loadings(), _se())
    assert list(table.index) == ["AAA", "BBB"]
    assert table.loc["AAA", "mkt_rf"] == pytest.approx(1.1)
    assert table.loc["AAA", "mkt_rf_nw_se"] == pytest.approx(0.04)
    assert table.loc["BBB", "smb_nw_se"] == pytest.approx(0.045)
    assert "r_squared" in table.columns


def test_beta_overlay_pivots_methods_for_one_ticker() -> None:
    dates = pd.bdate_range("2024-01-31", periods=3)
    history = pd.DataFrame(
        {
            ("raw", "AAA"): [1.0, 1.1, 1.2],
            ("vasicek", "AAA"): [0.9, 1.0, 1.1],
            ("blume", "AAA"): [1.0, 1.06, 1.13],
            ("raw", "BBB"): [0.5, 0.5, 0.5],
        },
        index=dates,
    )
    history.columns.names = ["method", "ticker"]
    out = d01_exposures.beta_overlay(history, "AAA")
    assert list(out.columns) == ["raw", "vasicek", "blume"]
    assert out["raw"].iloc[-1] == pytest.approx(1.2)


def test_r2_distribution_and_idio_vs_total() -> None:
    r2 = d01_exposures.r2_distribution(_loadings())
    assert len(r2) == 2
    dates = pd.bdate_range("2024-01-02", periods=300)
    rng = np.random.default_rng(0)
    returns = pd.DataFrame(
        {"AAA": rng.normal(0, 0.01, 300), "BBB": rng.normal(0, 0.02, 300)}, index=dates
    )
    idio = pd.DataFrame(
        {"idio_vol": [0.008, 0.015], "idio_vol_ann": [0.127, 0.238]},
        index=["AAA", "BBB"],
    )
    out = d01_exposures.idio_vs_total(idio, returns)
    assert {"ticker", "idio_vol_ann", "total_vol_ann"} <= set(out.columns)
    assert out.loc[out["ticker"] == "AAA", "total_vol_ann"].iloc[0] == pytest.approx(
        float(returns["AAA"].std(ddof=1) * np.sqrt(252)), rel=1e-9
    )


def test_vol_and_beta_horse_race_tables() -> None:
    vol_table = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA", "BBB", "BBB"],
            "method": ["ewma_094", "trailing_252", "ewma_094", "trailing_252"],
            "qlike": [-9.0, -8.0, -7.0, -7.5],
            "n_obs": [400, 400, 400, 400],
        }
    )
    summary = d01_exposures.vol_summary(vol_table)
    assert set(summary.index) >= {"ewma_094", "trailing_252"}
    assert "win_share" in summary.columns

    race = pd.DataFrame(
        {
            "method": ["raw", "vasicek", "blume"],
            "rmse": [0.43, 0.42, 0.44],
            "mean_bias": [0.02, 0.01, 0.02],
            "n_obs": [1000, 1000, 1000],
            "n_dates": [100, 100, 100],
        }
    )
    table = d01_exposures.beta_race_table(race)
    assert table["rmse"].is_monotonic_increasing
    assert table["method"].iloc[0] == "vasicek"


def test_portfolio_exposure_panel() -> None:
    weights = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-09-03", "2026-09-03", "2026-09-03"]),
            "ticker": ["AAA", "BBB", "CCC"],
            "weight": [0.5, -0.5, 0.0],
            "survivorship_caveat": [False, False, False],
        }
    )
    panel = d01_exposures.portfolio_exposure(weights, _loadings(), "2026-09-03")
    assert {"ticker", "weight", "mkt_rf", "smb"} <= set(panel.columns)
    assert panel["weight"].abs().sum() == pytest.approx(1.0)


def test_modules_import() -> None:
    import dashboard.app  # noqa: F401

    assert callable(d01_exposures.render)


def test_beta_overlay_reads_the_long_artifact_the_build_writes() -> None:
    """The build writes beta_history.parquet long, not with column levels.

    Reading it as wide found no columns and drew an empty chart on D1.
    """
    dates = pd.bdate_range("2024-01-31", periods=3)
    rows = [
        {"date": d, "method": m, "ticker": "AAA", "beta": v}
        for d, values in zip(
            dates,
            [(1.0, 0.9, 1.0), (1.1, 1.0, 1.06), (1.2, 1.1, 1.13)],
            strict=True,
        )
        for m, v in zip(("raw", "vasicek", "blume"), values, strict=True)
    ]
    rows.append({"date": dates[-1], "method": "raw", "ticker": "BBB", "beta": 0.5})
    history = pd.DataFrame(rows)
    out = d01_exposures.beta_overlay(history, "AAA")
    assert list(out.columns) == ["raw", "vasicek", "blume"]
    assert len(out) == 3
    assert out["raw"].iloc[-1] == pytest.approx(1.2)
    assert out["vasicek"].iloc[-1] == pytest.approx(1.1)
    assert "BBB" not in out.columns


def test_beta_overlay_on_the_stored_artifact_returns_rows() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "data" / "models" / "TS-v1" / "beta_history.parquet"
    if not path.exists():
        pytest.skip("E2 artifacts not built yet")
    history = pd.read_parquet(path)
    out = d01_exposures.beta_overlay(history, "JPM")
    assert list(out.columns) == ["raw", "vasicek", "blume"]
    assert len(out) > 100
    assert out["raw"].notna().sum() > 100
