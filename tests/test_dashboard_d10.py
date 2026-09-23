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
        "min_position_dollars": 5000.0,
        "n_kept": 27,
        "n_dropped": 472,
        "kept_gross": 0.2734,
    }
    (proposal_dir / "proposal_2026-09-03.json").write_text(json.dumps(manifest))
    weights = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "weight": [0.01, -0.02],
            "side": ["long", "short"],
            "z": [1.5, -2.0],
            "alpha": [1e-6, -2e-6],
        }
    )
    weights.to_parquet(proposal_dir / "proposal_2026-09-03.parquet", index=False)
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    reconciliation = pd.DataFrame({"dry_run": [True, True]})
    reconciliation.to_parquet(state_dir / "reconciliation.parquet", index=False)


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
    assert panel["reporting window days"].iloc[0] == 30
    assert panel["run condition"].iloc[0] == "open_ended"


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


def test_construction_label_names_the_construction_and_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _proposal(tmp_path)
    monkeypatch.setattr(d10, "PROPOSAL_DIR", tmp_path / "proposals")
    monkeypatch.setattr(d10, "STATE_DIR", tmp_path / "state")
    label = d10.construction_label()
    assert label["construction on disk"] == "min position $5,000"
    assert label["n names kept"] == 27
    assert label["n names dropped"] == 472
    assert label["run state"] == "dry run (the clock has not started)"


def test_proposal_names_panel_reads_weights_and_reasons(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _proposal(tmp_path)
    monkeypatch.setattr(d10, "PROPOSAL_DIR", tmp_path / "proposals")
    panel = d10.proposal_names_panel()
    assert len(panel) == 2
    assert set(panel["side"]) == {"long", "short"}
    # largest absolute weight first
    assert panel["ticker"].iloc[0] == "BBB"


def test_construction_table_and_weights_raise_on_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(d10, "CONSTRUCTION_TABLE_PATH", tmp_path / "missing.parquet")
    monkeypatch.setattr(d10, "CONSTRUCTION_WEIGHTS_PATH", tmp_path / "missing2.parquet")
    with pytest.raises(ValueError, match="construction table"):
        d10.load_construction_table()
    with pytest.raises(ValueError, match="construction weights"):
        d10.load_construction_weights()


def test_construction_table_and_weights_read_the_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = pd.DataFrame(
        {
            "construction": ["min_position_5000"],
            "n_kept": [99],
            "n_effective": [99],
        }
    )
    weights = pd.DataFrame(
        {"construction": ["min_position_5000"], "ticker": ["AAA"], "weight": [0.01]}
    )
    table_path = tmp_path / "construction_table.parquet"
    weights_path = tmp_path / "construction_weights.parquet"
    table.to_parquet(table_path, index=False)
    weights.to_parquet(weights_path, index=False)
    monkeypatch.setattr(d10, "CONSTRUCTION_TABLE_PATH", table_path)
    monkeypatch.setattr(d10, "CONSTRUCTION_WEIGHTS_PATH", weights_path)
    assert len(d10.load_construction_table()) == 1
    assert len(d10.load_construction_weights()) == 1
