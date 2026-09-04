"""Tests for Task 7: artifact versioning and the one-command rebuild."""

import hashlib
import json
from pathlib import Path

import pandas as pd

from efb import build


def test_hash_file_matches_sha256(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_bytes(b"efb")
    assert build.hash_file(p) == hashlib.sha256(b"efb").hexdigest()


def test_write_version_records_every_artifact(tmp_path: Path) -> None:
    a = tmp_path / "a.parquet"
    b = tmp_path / "b.parquet"
    pd.DataFrame({"x": [1]}).to_parquet(a)
    pd.DataFrame({"y": [2]}).to_parquet(b)
    out = tmp_path / "VERSION.json"
    build.write_version([a, b], out, note="test")
    data = json.loads(out.read_text())
    assert set(data["artifacts"]) == {"a.parquet", "b.parquet"}
    assert data["artifacts"]["a.parquet"]["sha256"] == build.hash_file(a)


def test_rebuild_runs_end_to_end_offline(tmp_path: Path, monkeypatch) -> None:
    # Patch network fetchers with synthetic fixtures so the rebuild is
    # deterministic and offline. Prices come from a small synthetic cache.
    changes = pd.DataFrame(
        {
            "effective_date": pd.to_datetime(["2015-01-02"]),
            "added_ticker": ["C"],
            "removed_ticker": ["A"],
            "reason": ["merger"],
        }
    )
    constituents = pd.DataFrame(
        {
            "symbol": ["B", "C"],
            "security": ["Bee", "Cee"],
            "gics_sector": ["Financials", "Tech"],
            "gics_sub_industry": ["Banks", "Software"],
            "date_added": pd.to_datetime(["2000-01-03", "2015-01-02"]),
        }
    )
    monkeypatch.setattr(build.universe, "fetch_constituents", lambda: constituents)
    monkeypatch.setattr(build.universe, "fetch_changes", lambda: changes)
    monkeypatch.setattr(
        build.factors,
        "load_french_factors",
        lambda: {
            "ff5": pd.DataFrame(
                {
                    "mkt_rf": [0.001],
                    "smb": [0.0],
                    "hml": [0.0],
                    "rmw": [0.0],
                    "cma": [0.0],
                    "rf": [0.0001],
                },
                index=pd.bdate_range("2015-01-02", periods=1, name="date"),
            ),
            "mom": pd.DataFrame(
                {"mom": [0.0]},
                index=pd.bdate_range("2015-01-02", periods=1, name="date"),
            ),
            "strev": pd.DataFrame(
                {"st_rev": [0.0]},
                index=pd.bdate_range("2015-01-02", periods=1, name="date"),
            ),
            "ind12": pd.DataFrame(
                {f"ind{i}": [0.0] for i in range(1, 13)},
                index=pd.bdate_range("2015-01-02", periods=1, name="date"),
            ),
        },
    )
    dates = pd.bdate_range("2015-01-01", periods=6)
    cache = pd.DataFrame(
        {
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": [1.0, 1.01, 1.02, 1.03, 1.04, 1.05] * 3,
            "adj_close": [1.0, 1.01, 1.02, 1.03, 1.04, 1.05] * 3,
            "volume": 100,
            "dividend": 0.0,
            "split_factor": 0.0,
        },
        index=pd.MultiIndex.from_product(
            [dates, ["A", "B", "C"]], names=["date", "ticker"]
        ),
    )
    data_root = tmp_path / "data"
    (data_root / "raw").mkdir(parents=True)
    cache.to_parquet(data_root / "raw" / "yf_cache.parquet")

    summary = build.rebuild(data_root=data_root, start="2015-01-01", end="2015-01-08")
    assert (data_root / "raw" / "prices.parquet").exists()
    assert (data_root / "processed" / "returns.parquet").exists()
    assert (data_root / "processed" / "universe_membership.parquet").exists()
    assert (data_root / "processed" / "sectors.parquet").exists()
    assert (data_root / "processed" / "events.parquet").exists()
    version = json.loads((data_root / "VERSION.json").read_text())
    assert len(version["artifacts"]) == 6
    assert "n_steps" in summary
