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


def test_the_day_states_both_books_risk_figures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The traded book's risk figures and the full book's, by their own names.

    One set of names for both books would make the page's volatility read as the
    traded book's when it is the full book's. The manifest is the only source, so
    the row, the run_status row and the snapshot cannot disagree either.
    """
    proposal_dir = tmp_path / "proposals"
    log_dir = tmp_path / "logs"
    state_dir = tmp_path / "state"
    _write_manifest(proposal_dir, "2026-09-22")
    path = proposal_dir / "proposal_2026-09-22.json"
    manifest = json.loads(path.read_text())
    # The two books genuinely differ: the floor dropped names, so the traded
    # book's gross is below the full book's and the two vols are two numbers.
    manifest.update(
        {
            "kept_achieved_annual_vol": 0.0459,
            "kept_idio_share": 0.981,
            "kept_max_abs_exposure": 0.0334,
            "kept_gross": 0.94,
            "kept_net": 0.0,
            "max_kept_weight": 0.033448,
            "n_eff_full_book": 149.9,
            "n_names": 158,
            "variance_share_cap": 0.10,
            "variance_share_cap_binds": False,
            "top_variance_shares": [{"ticker": "AAA", "variance_share": 0.031}],
        }
    )
    path.write_text(json.dumps(manifest))
    _write_execution(log_dir, "2026-09-22")
    monkeypatch.setattr(reconcile, "PROPOSAL_DIR", proposal_dir)
    monkeypatch.setattr(reconcile, "EXECUTION_LOG_DIR", log_dir)

    row = reconcile.daily_record("2026-09-22", state_dir=state_dir, dry_run=True)

    traded = json.loads(row["traded_risk"])
    full = json.loads(row["full_risk"])
    assert traded["forecast_annual_vol"] == pytest.approx(0.0459)
    assert full["forecast_annual_vol"] == pytest.approx(0.0423)
    assert traded["forecast_annual_vol"] != full["forecast_annual_vol"]
    assert traded["gross"] == pytest.approx(0.94)
    assert full["gross"] == pytest.approx(1.0)
    assert traded["n_eff"] == pytest.approx(158.9)
    assert traded["variance_share_cap_binds"] is False
    assert traded["top_variance_shares"] == [{"ticker": "AAA", "variance_share": 0.031}]
    assert full["n_names"] == 158
    assert "traded_risk" in reconcile.RECONCILIATION_COLUMNS
    assert "full_risk" in reconcile.RECONCILIATION_COLUMNS


def test_a_manifest_without_the_figures_records_none_not_zero() -> None:
    """A manifest written before a field existed records it as unrecorded.

    A zero would read as a measured volatility of nothing, and a month of zeros
    would average into the book's history as if the evening had produced one.
    """
    risk = reconcile.risk_figures({"achieved_annual_vol": 0.0423})

    assert risk["traded"]["forecast_annual_vol"] is None
    assert risk["full"]["forecast_annual_vol"] == pytest.approx(0.0423)
    # and a run with no manifest at all returns nulls rather than raising
    assert reconcile.risk_figures(None)["traded"]["n_eff"] is None
    assert reconcile.risk_figures(None)["full"]["gross"] is None
