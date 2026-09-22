"""Sprint E11 Task 8: the D10 panels raise on empty and read the artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from dashboard.tabs import d10_book as d10


def _proposal(tmp_path: Path) -> None:
    proposal_dir = tmp_path / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "signal": "idio_momentum",
        "as_of": "2026-09-03",
        "n_names": 499,
        "n_excluded": 4,
        "idio_share_after_fmp": 1.0,
        "gross": 1.0,
        "net": 0.0,
        "n_eff": 158.9,
        "target_annual_vol": 0.10,
        "achieved_annual_vol": 0.0423,
        "gross_cap_bound": True,
        "expected_establishment_cost_bps": 75.3,
    }
    (proposal_dir / "proposal_2026-09-03.json").write_text(json.dumps(manifest))
    weights = pd.DataFrame({"ticker": ["AAA"], "weight": [0.01]})
    weights.to_parquet(proposal_dir / "proposal_2026-09-03.parquet", index=False)


def test_latest_proposal_raises_on_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(d10, "PROPOSAL_DIR", tmp_path / "proposals")
    with pytest.raises(ValueError, match="empty proposal directory"):
        d10.load_latest_proposal()


def test_book_panel_reads_the_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _proposal(tmp_path)
    monkeypatch.setattr(d10, "PROPOSAL_DIR", tmp_path / "proposals")
    panel = d10.book_panel()
    assert not panel.empty
    assert panel["n names"].iloc[0] == 499
    assert panel["idio share after FMP (unitless)"].iloc[0] == 1.0
    assert panel["achieved annual vol (%)"].iloc[0] == pytest.approx(4.23)


def test_reconciliation_panel_raises_on_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(d10, "STATE_DIR", tmp_path / "state")
    with pytest.raises(ValueError, match="empty artifact"):
        d10.load_reconciliation()


def test_reconciliation_panel_reads_the_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [
            {
                "trade_date": "2026-09-22",
                "forecast_annual_vol": 0.0423,
                "realized_annual_vol": float("nan"),
                "idio_share_after_fmp": 1.0,
                "gross": 1.0,
                "net": 0.0,
                "intended_notional": 100_000.0,
                "filled_notional": 0.0,
                "dry_run": True,
            }
        ]
    )
    frame.to_parquet(state_dir / "reconciliation.parquet", index=False)
    monkeypatch.setattr(d10, "STATE_DIR", state_dir)
    panel = d10.reconciliation_panel()
    assert len(panel) == 1
    assert bool(panel["dry_run"].iloc[0]) is True


def test_guards_panel_reads_the_execution_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "status": ["PASSED", "REJECTED_CAP"],
            "intended_notional": [100.0, 500.0],
            "filled_notional": [0.0, 0.0],
            "reason": ["", "guard rejected the order"],
        }
    )
    frame.to_parquet(log_dir / "execution_2026-09-22.parquet", index=False)
    monkeypatch.setattr(d10, "EXECUTION_LOG_DIR", log_dir)
    panel = d10.guards_panel()
    assert not panel.empty
    assert set(panel["status"]) == {"PASSED", "REJECTED_CAP"}


def test_clock_panel_raises_on_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(d10, "CLOCK_PATH", tmp_path / "clock.json")
    with pytest.raises(ValueError, match="empty artifact"):
        d10.load_clock()


def test_clock_panel_reads_the_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock_path = tmp_path / "clock.json"
    clock_path.write_text(
        json.dumps(
            {
                "day_1": "2026-09-22",
                "end_date": "2026-11-03",
                "trading_days": 30,
                "started": True,
            }
        )
    )
    monkeypatch.setattr(d10, "CLOCK_PATH", clock_path)
    panel = d10.clock_panel()
    assert panel["day 1"].iloc[0] == "2026-09-22"
    assert panel["trading days"].iloc[0] == 30


def test_answer_panel_is_the_null_book_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _proposal(tmp_path)
    monkeypatch.setattr(d10, "PROPOSAL_DIR", tmp_path / "proposals")
    summary = pd.DataFrame(
        {
            "signal": ["idio_momentum"],
            "neutral_ic_h21_mean": [-0.003094],
            "neutral_ic_h21_t": [-0.511503],
            "ic_h1_mean": [0.012102],
            "ic_h1_t": [5.043550],
        }
    )
    data_dir = tmp_path / "data"
    (data_dir / "alpha").mkdir(parents=True, exist_ok=True)
    summary.to_parquet(data_dir / "alpha" / "summary.parquet", index=False)
    monkeypatch.setattr(d10, "DATA", data_dir)
    answer = d10.answer_panel()
    assert answer["what this book is"] == "null book"
    assert answer["expected E12 verdict (pre-written)"] == "luck"
    assert answer["factor-neutral IC, horizon 21"] == pytest.approx(-0.003094)
