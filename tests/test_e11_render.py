"""Sprint E11 Part B: Render, Supabase, Alpaca and the live dashboard."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from live import alpaca, store, trade_reasons

ROOT = Path(__file__).resolve().parents[1]


def test_alpaca_dry_run_connect_returns_none() -> None:
    assert alpaca.connect(dry_run=True) is None


def test_alpaca_live_connect_names_the_missing_dependency() -> None:
    if importlib.util.find_spec("alpaca") is not None:
        pytest.skip("alpaca-py is installed")
    with pytest.raises(RuntimeError, match="alpaca-py"):
        alpaca.connect(dry_run=False)


def test_store_unknown_table_raises() -> None:
    with pytest.raises(ValueError, match="unknown live-series table"):
        store.upsert("not_a_table", [{"a": 1}])


def test_store_local_fallback_is_disjoint_from_state_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EFB_SUPABASE_URL", raising=False)
    monkeypatch.delenv("EFB_SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path)
    store.upsert(
        "nav", [{"trade_date": "2026-09-22", "nav": 100000.0, "realized_pnl": 0.0}]
    )
    frame = store.select("nav")
    assert len(frame) == 1
    assert float(frame["nav"].iloc[0]) == 100000.0
    assert (tmp_path / "nav.parquet").exists()


def test_store_is_supabase_false_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EFB_SUPABASE_URL", raising=False)
    monkeypatch.delenv("EFB_SUPABASE_SECRET_KEY", raising=False)
    assert store.is_supabase() is False


def test_trade_reasons_classify_each_bucket() -> None:
    today = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D"],
            "weight": [0.02, 0.02, 0.02, 0.01],
            "z": [1.5, 1.0, 1.0, 1.0],
        }
    )
    previous = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D"],
            "weight": [0.01, 0.01, 0.01, 0.01],
            "z": [1.0, 1.0, 1.0, 1.0],
        }
    )
    today_specific = pd.Series({"A": 0.3, "B": 0.5, "C": 0.3, "D": 0.3})
    previous_specific = pd.Series({"A": 0.3, "B": 0.3, "C": 0.3, "D": 0.3})
    reasons = trade_reasons.assign_trade_reasons(
        today, previous, today_specific, previous_specific
    ).set_index("ticker")["reason"]
    assert reasons["A"] == "alpha moved"
    assert reasons["B"] == "risk moved"
    assert reasons["C"] == "the hedge moved"
    assert reasons["D"] == "no trade"


def test_trade_reasons_new_name_is_alpha() -> None:
    today = pd.DataFrame({"ticker": ["X"], "weight": [0.03], "z": [0.9]})
    reasons = trade_reasons.assign_trade_reasons(
        today, None, pd.Series(dtype=float), None
    )
    assert reasons["reason"].iloc[0] == "alpha moved"


def test_render_dashboard_reads_no_research_parquet() -> None:
    """The Render app reads the live series and two tiny files, never a
    research parquet, so acceptance 7 holds by construction."""
    source = (ROOT / "live" / "dashboard_app.py").read_text()
    assert "read_parquet" not in source
    assert "data/" not in source


def test_render_yaml_commits_key_names_not_values() -> None:
    render = (ROOT / "render.yaml").read_text()
    assert "EFB_ALPACA_PAPER_API_KEY" in render
    assert "EFB_ALPACA_PAPER_SECRET_KEY" in render
    assert "sync: false" in render
    assert "AKIA" not in render
    assert "-----BEGIN" not in render
