"""Tests for Task 6: the E2 artifact build and registry wiring."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from efb import build

TICKERS = [f"T{i:02d}" for i in range(12)]
SECTORS = {t: ["Tech", "Energy", "Financials"][i % 3] for i, t in enumerate(TICKERS)}


def _write_inputs(data_root: Path, periods: int = 420) -> None:
    (data_root / "raw").mkdir(parents=True, exist_ok=True)
    (data_root / "processed").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2024-01-01", periods=periods)
    factors = pd.DataFrame(
        {
            "mkt_rf": rng.normal(0.0004, 0.01, periods),
            "smb": rng.normal(0.0, 0.004, periods),
            "hml": rng.normal(0.0, 0.004, periods),
            "rmw": rng.normal(0.0, 0.003, periods),
            "cma": rng.normal(0.0, 0.003, periods),
            "mom": rng.normal(0.0, 0.004, periods),
            "rf": 0.0001,
        },
        index=dates,
    )
    factors.to_parquet(data_root / "raw" / "factors_ff.parquet")

    rows = []
    for i, ticker in enumerate(TICKERS):
        beta = 0.5 + 0.1 * i
        excess = beta * factors["mkt_rf"] + rng.normal(0.0, 0.01, periods)
        frame = pd.DataFrame(
            {
                "r": excess,
                "g": np.log1p(excess),
                "excess": excess,
                "stale": False,
                "outlier": False,
                "ticker": ticker,
            },
            index=dates,
        )
        frame.index.name = "date"
        rows.append(frame)
    returns = pd.concat(rows).set_index("ticker", append=True).reorder_levels(["date", "ticker"])
    returns.to_parquet(data_root / "processed" / "returns.parquet")

    members = pd.DataFrame(True, index=dates, columns=TICKERS)
    members.to_parquet(data_root / "processed" / "universe_membership.parquet")
    sectors = pd.DataFrame(
        {"ticker": TICKERS, "gics_sector": [SECTORS[t] for t in TICKERS]}
    )
    sectors.to_parquet(data_root / "processed" / "sectors.parquet", index=False)


def test_build_e2_artifacts_writes_everything_and_registers_ts_v1(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_inputs(data_root)
    summary = build.build_e2_artifacts(
        data_root=data_root, start=2024, include_garch=False, garch_tickers=0
    )
    expected = [
        "models/TS-v1/loadings.parquet",
        "models/TS-v1/loadings_se.parquet",
        "models/TS-v1/residuals.parquet",
        "models/TS-v1/idio_vol.parquet",
        "models/TS-v1/factor_cov.parquet",
        "models/TS-v1/beta_history.parquet",
        "models/registry.json",
        "eval/beta_horse_race.parquet",
        "eval/vol_horse_race.parquet",
        "eval/portfolio_risk_snapshot.parquet",
        "portfolios/seed_ew.parquet",
        "portfolios/seed_mom_ls.parquet",
        "portfolios/seed_ew_risk.parquet",
        "portfolios/seed_mom_ls_risk.parquet",
    ]
    for rel in expected:
        assert (data_root / rel).is_file(), f"missing artifact {rel}"
    assert summary["n_names"] == len(TICKERS)

    se = pd.read_parquet(data_root / "models/TS-v1/loadings_se.parquet")
    assert list(se.columns.names) == ["method", "statistic"]
    assert set(se.columns.get_level_values("method")) == {"ols", "nw_l5"}

    loadings = pd.read_parquet(data_root / "models/TS-v1/loadings.parquet")
    assert {"alpha", "mkt_rf", "mom", "r_squared", "n_obs"} <= set(loadings.columns)

    registry = json.loads((data_root / "models/registry.json").read_text())
    assert "champion_rule" in registry and "family_notes" in registry
    entry = registry["models"]["TS-v1"]
    assert entry["family"] == "timeseries"
    assert entry["champion"] is False
    assert entry["eligible_for_champion"] is False
    assert entry["universe_hash"]
    assert entry["parameters"]["factors"][0] == "mkt_rf"

    ew = pd.read_parquet(data_root / "portfolios/seed_ew.parquet")
    ls = pd.read_parquet(data_root / "portfolios/seed_mom_ls.parquet")
    assert bool(ew["survivorship_caveat"].iloc[0]) is True
    assert bool(ls["survivorship_caveat"].iloc[0]) is False


def test_build_e2_artifact_list_includes_registry() -> None:
    assert "models/registry.json" in build.E2_ARTIFACTS
    assert "portfolios/seed_mom_ls.parquet" in build.E2_ARTIFACTS
