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
    returns = (
        pd.concat(rows)
        .set_index("ticker", append=True)
        .reorder_levels(["date", "ticker"])
    )
    returns.to_parquet(data_root / "processed" / "returns.parquet")

    members = pd.DataFrame(True, index=dates, columns=TICKERS)
    members.to_parquet(data_root / "processed" / "universe_membership.parquet")
    sectors = pd.DataFrame(
        {"ticker": TICKERS, "gics_sector": [SECTORS[t] for t in TICKERS]}
    )
    sectors.to_parquet(data_root / "processed" / "sectors.parquet", index=False)

    prices = []
    for ticker in TICKERS:
        level = pd.Series(50.0, index=dates)
        prices.append(
            pd.DataFrame(
                {
                    "close": level,
                    "adj_close": level,
                    "split_factor": 0.0,
                    "ticker": ticker,
                },
                index=dates,
            )
        )
    price_frame = (
        pd.concat(prices)
        .set_index("ticker", append=True)
        .reorder_levels(["date", "ticker"])
    )
    price_frame.index.name = "date"
    price_frame.to_parquet(data_root / "raw" / "prices.parquet")


def _splice(data_root: Path, ticker: str) -> None:
    """Make `ticker`'s adjusted close jump 100x, the reused-symbol pattern."""
    path = data_root / "raw" / "prices.parquet"
    frame = pd.read_parquet(path)
    dates = frame.index.get_level_values("date")
    rows = (frame.index.get_level_values("ticker") == ticker) & (
        dates > dates.unique()[200]
    )
    frame.loc[rows, "adj_close"] = frame.loc[rows, "adj_close"] * 100.0
    frame.to_parquet(path)


def test_build_e2_artifacts_writes_everything_and_registers_ts_v1(
    tmp_path: Path,
) -> None:
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


def test_the_build_applies_the_identity_exclusions(tmp_path: Path) -> None:
    # C1: with a changes table and a name cache present, the build runs the
    # identity check itself and drops what it flags. No step is manual.
    data_root = tmp_path / "data"
    _write_inputs(data_root)
    _splice(data_root, "T05")
    changes = pd.DataFrame(
        {
            "effective_date": pd.to_datetime(["2024-06-03"]),
            "added_ticker": [None],
            "added_security": [None],
            "removed_ticker": ["T05"],
            "removed_security": ["Old Member Corp"],
            "reason": ["test"],
        }
    )
    changes.to_parquet(
        data_root / "processed" / "universe_changes.parquet", index=False
    )
    pd.DataFrame(
        {
            "ticker": ["T05"],
            "symbol": ["T05"],
            "long_name": ["Brand New Listing Inc"],
            "short_name": ["Brand New"],
        }
    ).to_parquet(data_root / "raw" / "yf_names.parquet", index=False)

    summary = build.build_e2_artifacts(
        data_root=data_root, start=2024, include_garch=False, garch_tickers=0
    )
    assert summary["identity_check"] == "applied"
    assert summary["identity_dropped"] == ["T05"]

    table = pd.read_parquet(data_root / "processed" / "ticker_identity.parquet")
    assert set(table["ticker"]) == {"T05"}
    assert bool(table.iloc[0]["reused"]) is True

    loadings = pd.read_parquet(data_root / "models/TS-v1/loadings.parquet")
    assert "T05" not in set(loadings.index)


def test_the_build_records_when_the_identity_check_cannot_run(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_inputs(data_root)  # no changes table on disk
    summary = build.build_e2_artifacts(
        data_root=data_root, start=2024, include_garch=False, garch_tickers=0
    )
    assert summary["identity_check"].startswith("skipped")
    assert summary["identity_dropped"] == []


def test_build_e2_artifact_list_includes_registry() -> None:
    assert "models/registry.json" in build.E2_ARTIFACTS
    assert "portfolios/seed_mom_ls.parquet" in build.E2_ARTIFACTS


def test_a_reused_symbol_leaves_the_panel(tmp_path: Path) -> None:
    # CPWR, EP, MI and POM are real members whose symbols were later taken by
    # unrelated listings. Masking the break date is not enough: every earlier
    # date would still carry the wrong company's returns.
    data_root = tmp_path / "data"
    _write_inputs(data_root)
    _splice(data_root, "T05")
    summary = build.build_e2_artifacts(
        data_root=data_root, start=2024, include_garch=False, garch_tickers=0
    )
    assert summary["n_names"] == len(TICKERS) - 1

    loadings = pd.read_parquet(data_root / "models/TS-v1/loadings.parquet")
    assert "T05" not in set(loadings.index)

    registry = json.loads((data_root / "models/registry.json").read_text())
    dropped = registry["models"]["TS-v1"]["parameters"]["series_break_tickers_dropped"]
    assert dropped == ["T05"]

    ew = pd.read_parquet(data_root / "portfolios/seed_ew.parquet")
    assert "T05" not in set(ew["ticker"])
