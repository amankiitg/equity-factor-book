"""Sprint E11, Task 7: daily reconciliation, forecast against outcome.

The forecast is stored every day from the proposal manifest; the realized
columns stay NaN in dry run, and the comparison is pending rather than
faked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from live import reconcile


def _write_manifest(proposal_dir: Path, as_of: str) -> None:
    proposal_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "achieved_annual_vol": 0.0423,
        "idio_share_after_fmp": 1.0,
        "max_abs_exposure_after_fmp": 2.5e-15,
        "gross": 1.0,
        "net": 0.0,
        "n_eff_kept": 158.9,
        "expected_establishment_cost_bps": 75.3,
        # The four parts, summing to the total by construction:
        # live/evening_job.py adds exactly these.
        "cost_breakdown_bps": {
            "spread": 12.3,
            "impact": 55.0,
            "commission": 2.0,
            "borrow": 6.0,
            "total": 75.3,
        },
    }
    (proposal_dir / f"proposal_{as_of}.json").write_text(json.dumps(manifest))


def _write_execution(log_dir: Path, as_of: str) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "intended_notional": [1000.0, -500.0],
            "filled_notional": [0.0, 0.0],
            "status": ["DRY_RUN", "DRY_RUN"],
            "reason": ["dry run: no order sent"] * 2,
        }
    )
    frame.to_parquet(log_dir / f"execution_{as_of}.parquet", index=False)


def test_daily_record_stores_forecast_with_nan_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal_dir = tmp_path / "proposals"
    log_dir = tmp_path / "logs"
    state_dir = tmp_path / "state"
    _write_manifest(proposal_dir, "2026-09-22")
    _write_execution(log_dir, "2026-09-22")
    monkeypatch.setattr(reconcile, "PROPOSAL_DIR", proposal_dir)
    monkeypatch.setattr(reconcile, "EXECUTION_LOG_DIR", log_dir)

    row = reconcile.daily_record("2026-09-22", state_dir=state_dir, dry_run=True)
    assert row["forecast_annual_vol"] == pytest.approx(0.0423)
    assert pd.isna(row["realized_annual_vol"])
    assert row["dry_run"] is True
    assert row["intended_notional"] == pytest.approx(1500.0)
    assert row["filled_notional"] == pytest.approx(0.0)

    # idempotent on the trade date
    reconcile.daily_record("2026-09-22", state_dir=state_dir, dry_run=True)
    stored = pd.read_parquet(state_dir / "reconciliation.parquet")
    assert len(stored) == 1


def test_reconcile_is_pending_in_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal_dir = tmp_path / "proposals"
    log_dir = tmp_path / "logs"
    state_dir = tmp_path / "state"
    _write_manifest(proposal_dir, "2026-09-22")
    _write_execution(log_dir, "2026-09-22")
    monkeypatch.setattr(reconcile, "PROPOSAL_DIR", proposal_dir)
    monkeypatch.setattr(reconcile, "EXECUTION_LOG_DIR", log_dir)
    reconcile.daily_record("2026-09-22", state_dir=state_dir, dry_run=True)

    result = reconcile.reconcile_forecast_vs_outcome("2026-09-22", state_dir=state_dir)
    assert result["status"] == "pending"
    assert result["realized_annual_vol"] is None


def test_reconcile_reports_ratio_when_realized_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal_dir = tmp_path / "proposals"
    log_dir = tmp_path / "logs"
    state_dir = tmp_path / "state"
    _write_manifest(proposal_dir, "2026-09-22")
    _write_execution(log_dir, "2026-09-22")
    monkeypatch.setattr(reconcile, "PROPOSAL_DIR", proposal_dir)
    monkeypatch.setattr(reconcile, "EXECUTION_LOG_DIR", log_dir)
    reconcile.daily_record("2026-09-22", state_dir=state_dir, dry_run=False)
    stored = pd.read_parquet(state_dir / "reconciliation.parquet")
    stored.loc[stored["trade_date"] == "2026-09-22", "realized_annual_vol"] = 0.05
    stored.to_parquet(state_dir / "reconciliation.parquet", index=False)

    result = reconcile.reconcile_forecast_vs_outcome("2026-09-22", state_dir=state_dir)
    assert result["status"] == "reconciled"
    assert result["ratio"] == pytest.approx(0.05 / 0.0423)


def test_daily_record_states_the_cost_breakdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The day's cost, split into the four parts it is made of.

    A total alone is one number to trust. The parts are the same total as four
    numbers that have to add up, in the store and in the message, so a cost that
    is wrong in one component is visible rather than averaged away.
    """
    proposal_dir = tmp_path / "proposals"
    log_dir = tmp_path / "logs"
    state_dir = tmp_path / "state"
    _write_manifest(proposal_dir, "2026-09-22")
    _write_execution(log_dir, "2026-09-22")
    monkeypatch.setattr(reconcile, "PROPOSAL_DIR", proposal_dir)
    monkeypatch.setattr(reconcile, "EXECUTION_LOG_DIR", log_dir)

    row = reconcile.daily_record("2026-09-22", state_dir=state_dir, dry_run=True)

    parts = [row[f"expected_{part}_bps"] for part in reconcile.COST_PARTS]
    assert parts == [12.3, 55.0, 2.0, 6.0]
    assert sum(parts) == pytest.approx(row["expected_cost_bps"])
    assert "expected_borrow_bps" in reconcile.RECONCILIATION_COLUMNS


def test_a_manifest_without_a_breakdown_keeps_the_total(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A proposal written before the breakdown existed still records its day.

    The parts are absent, not zero: a zero would read as a free day, and this day
    was not free. The evening must not fail over a missing detail either.
    """
    proposal_dir = tmp_path / "proposals"
    log_dir = tmp_path / "logs"
    state_dir = tmp_path / "state"
    _write_manifest(proposal_dir, "2026-09-22")
    manifest = json.loads((proposal_dir / "proposal_2026-09-22.json").read_text())
    del manifest["cost_breakdown_bps"]
    (proposal_dir / "proposal_2026-09-22.json").write_text(json.dumps(manifest))
    _write_execution(log_dir, "2026-09-22")
    monkeypatch.setattr(reconcile, "PROPOSAL_DIR", proposal_dir)
    monkeypatch.setattr(reconcile, "EXECUTION_LOG_DIR", log_dir)

    row = reconcile.daily_record("2026-09-22", state_dir=state_dir, dry_run=True)

    assert row["expected_cost_bps"] == pytest.approx(75.3)
    assert row["expected_borrow_bps"] is None
