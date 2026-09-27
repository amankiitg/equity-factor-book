"""Sprint E11: daily reconciliation, forecast against outcome.

Every day the loop stores the ex-ante forecast beside the realized
outcome so the two can be compared, which is what F11.2 and F11.3 score.
In dry run there are no fills, so the realized columns stay NaN and the
record is labeled dry run rather than filled with a fake outcome.

State lives on EFB artifacts under `live/state/`, never Supabase.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from live import state, store

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
PROPOSAL_DIR = ROOT / "live" / "proposals"
EXECUTION_LOG_DIR = ROOT / "live" / "logs"

RECONCILIATION_COLUMNS = [
    "trade_date",
    "forecast_annual_vol",
    "realized_annual_vol",
    "idio_share_after_fmp",
    "max_abs_exposure_after_fmp",
    "gross",
    "net",
    "n_eff_kept",
    "intended_notional",
    "filled_notional",
    "expected_cost_bps",
    # The establishment cost, split the way efb/costs.py computes it. They sum to
    # `expected_cost_bps` by construction, and the row states them so the total is
    # an arithmetic claim rather than one number nobody can decompose.
    "expected_spread_bps",
    "expected_impact_bps",
    "expected_commission_bps",
    "expected_borrow_bps",
    "dry_run",
    # The traded book's risk figures and the full book's, each under its own
    # names, as JSON text. They come from the proposal manifest, so the row, the
    # run_status row and the snapshot cannot disagree about the book.
    "traded_risk",
    "full_risk",
]

# The manifest keys behind each risk figure. The traded book is the kept book,
# and the full book is every name the model sized before the floor dropped any.
TRADED_RISK_FIELDS: dict[str, str] = {
    "forecast_annual_vol": "kept_achieved_annual_vol",
    "idio_share": "kept_idio_share",
    "max_abs_exposure": "kept_max_abs_exposure",
    "gross": "kept_gross",
    "net": "kept_net",
    "n_eff": "n_eff_kept",
    "max_weight": "max_kept_weight",
    "variance_share_cap_binds": "variance_share_cap_binds",
    "top_variance_shares": "top_variance_shares",
}
FULL_RISK_FIELDS: dict[str, str] = {
    "forecast_annual_vol": "achieved_annual_vol",
    "idio_share": "idio_share_after_fmp",
    "max_abs_exposure": "max_abs_exposure_after_fmp",
    "gross": "gross",
    "net": "net",
    "n_eff": "n_eff_full_book",
    "n_names": "n_names",
}


def risk_figures(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """The day's risk figures, traded book and full book, under their own names.

    The manifest is the source; nothing is recomputed here, so the reconciliation
    row, the run_status row and the snapshot cannot disagree about the book. A
    manifest written before a field existed returns None for it rather than a
    zero that reads as a measurement.
    """
    data = manifest or {}
    return {
        "traded": {name: data.get(key) for name, key in TRADED_RISK_FIELDS.items()},
        "full": {name: data.get(key) for name, key in FULL_RISK_FIELDS.items()},
        "variance_share_cap": data.get("variance_share_cap"),
    }


# The parts of the establishment cost, in the order the message states them.
COST_PARTS = ("spread", "impact", "commission", "borrow")


def cost_breakdown(manifest: dict[str, Any]) -> dict[str, float]:
    """The establishment cost and its four parts, in basis points of NAV.

    The parts come from the proposal's own `cost_breakdown_bps`, which
    `evening_job._cost_decomposition` builds as spread + impact + commission +
    borrow, so the four always sum to the total. Borrow is the short leg's annual
    rate over one 21-session horizon, not a year: the first trading day pays
    three weeks of borrow, not twelve months of it.

    A manifest written before the breakdown existed has the total and no parts;
    then only the total is returned, because a missing part must not be invented.
    A manifest with neither (a stored one read back on a failed evening) returns
    nothing at all, and the message simply leaves the cost out.
    """
    raw = manifest.get("cost_breakdown_bps") or {}
    breakdown: dict[str, float] = {}
    total = manifest.get("expected_establishment_cost_bps")
    if total is not None:
        breakdown["total"] = float(total)
    for part in COST_PARTS:
        value = raw.get(part)
        if value is not None:
            breakdown[part] = float(value)
    return breakdown


def _load_manifest(as_of: str) -> dict[str, Any]:
    path = PROPOSAL_DIR / f"proposal_{as_of}.json"
    if not path.exists():
        raise FileNotFoundError(f"no proposal manifest for {as_of} at {path}")
    return json.loads(path.read_text())


def _load_execution(as_of: str) -> pd.DataFrame:
    path = EXECUTION_LOG_DIR / f"execution_{as_of}.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def daily_record(
    as_of: str,
    data_root: Path | None = None,
    state_dir: Path = state.STATE_DIR,
    dry_run: bool = True,
) -> dict[str, object]:
    """One day's forecast beside its outcome, stored append-only.

    The forecast comes from the proposal manifest (the champion model's
    ex-ante decomposition); the realized columns come from the execution
    log and are NaN in dry run. The row is idempotent on the trade date.
    """
    manifest = _load_manifest(as_of)
    execution = _load_execution(as_of)
    breakdown = cost_breakdown(manifest)
    risk = risk_figures(manifest)
    intended = (
        float(execution["intended_notional"].abs().sum()) if len(execution) else 0.0
    )
    filled = float(execution["filled_notional"].abs().sum()) if len(execution) else 0.0
    row = {
        "trade_date": as_of,
        "forecast_annual_vol": float(manifest["achieved_annual_vol"]),
        "realized_annual_vol": float("nan"),
        "idio_share_after_fmp": float(manifest["idio_share_after_fmp"]),
        "max_abs_exposure_after_fmp": float(manifest["max_abs_exposure_after_fmp"]),
        "gross": float(manifest["gross"]),
        "net": float(manifest["net"]),
        "n_eff_kept": float(manifest["n_eff_kept"]),
        "intended_notional": intended,
        "filled_notional": filled,
        "expected_cost_bps": breakdown["total"],
        # None where the manifest carries no breakdown, so the column says "not
        # recorded" rather than a zero that reads as a free day.
        "expected_spread_bps": breakdown.get("spread"),
        "expected_impact_bps": breakdown.get("impact"),
        "expected_commission_bps": breakdown.get("commission"),
        "expected_borrow_bps": breakdown.get("borrow"),
        "dry_run": dry_run,
        "traded_risk": store.json_text(risk["traded"]),
        "full_risk": store.json_text(risk["full"]),
    }
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "reconciliation.parquet"
    frame = (
        pd.read_parquet(path)
        if path.exists()
        else pd.DataFrame(columns=RECONCILIATION_COLUMNS)
    )
    frame = frame.loc[frame["trade_date"] != as_of]
    pd.concat([frame, pd.DataFrame([row])], ignore_index=True).to_parquet(
        path, index=False
    )
    return row


def reconcile_forecast_vs_outcome(
    as_of: str, state_dir: Path = state.STATE_DIR
) -> dict:
    """Compare the stored forecast to the stored outcome for one date.

    Returns the two numbers and the verdict; in dry run there is no
    outcome yet, so the comparison is recorded as pending rather than
    faked.
    """
    path = state_dir / "reconciliation.parquet"
    if not path.exists():
        raise FileNotFoundError(f"no reconciliation records at {path}")
    frame = pd.read_parquet(path)
    rows = frame.loc[frame["trade_date"] == as_of]
    if rows.empty:
        raise ValueError(f"no reconciliation record for {as_of}")
    row = rows.iloc[0]
    realized = row["realized_annual_vol"]
    forecast = row["forecast_annual_vol"]
    if pd.isna(realized):
        return {
            "as_of": as_of,
            "forecast_annual_vol": float(forecast),
            "realized_annual_vol": None,
            "status": "pending",
            "reason": "dry run: no fills, no realized outcome",
        }
    return {
        "as_of": as_of,
        "forecast_annual_vol": float(forecast),
        "realized_annual_vol": float(realized),
        "ratio": float(realized) / float(forecast) if forecast else float("nan"),
        "status": "reconciled",
    }


def main() -> int:
    """The cron entrypoint: store today's forecast beside the outcome."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    row = daily_record(args.as_of, dry_run=not args.live)
    print(json.dumps(row, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
