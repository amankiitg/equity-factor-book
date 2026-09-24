"""The daily live cron: extend, propose, execute, reconcile.

One Render cron runs this after the US close. It extends every model
input by one session, builds the evening proposal, runs the morning
execution (dry run unless EFB live keys are present), and stores the
day's forecast beside its outcome. The live series goes to Supabase
through live.store, which falls back to local files when Supabase is not
configured. Every run is recorded in cron_runs, so a re-fire is a no-op
rather than a duplicate.

Nothing executes real money. The morning path is dry run by default and
the live path needs EFB_ALPACA_PAPER_API_KEY and
EFB_ALPACA_PAPER_SECRET_KEY, which are never committed.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
# Render runs this file as `python scripts/run_live_daily.py`, which puts
# scripts/ on sys.path, not the repository root; make the live package
# importable from any working directory.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PROPOSAL_DIR = ROOT / "live" / "proposals"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("run_live_daily")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def already_ran(job: str, run_date: str) -> bool:
    """Whether this job already completed for this date."""
    from live import store

    frame = store.select("cron_runs")
    if frame.empty:
        return False
    rows = frame.loc[(frame["run_date"] == run_date) & (frame["job"] == job)]
    return bool(len(rows))


def record_run(job: str, run_date: str, status: str, detail: str = "") -> None:
    """Record one cron run, keyed by date and job."""
    from live import store

    frame = store.select("cron_runs")
    # The first run sees an empty, columnless frame; guard the filter so the
    # very first cron record does not raise on the missing column.
    if not frame.empty:
        frame = frame.loc[~((frame["run_date"] == run_date) & (frame["job"] == job))]
    rows = frame.to_dict("records")
    rows.append(
        {
            "run_date": run_date,
            "job": job,
            "status": status,
            "detail": detail,
            "started_at": _now(),
            "finished_at": _now(),
        }
    )
    store.upsert("cron_runs", rows)


def store_proposal(as_of: str) -> None:
    """Write the proposal manifest, positions and trade reasons to the store."""
    from live import store, trade_reasons

    manifest = json.loads((PROPOSAL_DIR / f"proposal_{as_of}.json").read_text())
    rows = pd.read_parquet(PROPOSAL_DIR / f"proposal_{as_of}.parquet")
    proposal_paths = sorted(PROPOSAL_DIR.glob("proposal_*.parquet"))
    previous = None
    if len(proposal_paths) > 1 and proposal_paths[-1].stem == f"proposal_{as_of}":
        previous = pd.read_parquet(proposal_paths[-2])

    specific = pd.read_parquet(
        ROOT / "data" / "models" / "XS-v1" / "specific_var.parquet"
    )
    as_of_ts = pd.Timestamp(as_of)
    today_std = trade_reasons.specific_std(specific, as_of=as_of_ts)
    prev_std = trade_reasons.specific_std(specific, as_of=as_of_ts)

    reasons = trade_reasons.assign_trade_reasons(rows, previous, today_std, prev_std)
    rows = rows.merge(reasons[["ticker", "reason"]], on="ticker", how="left")
    rows["reason"] = rows["reason"].fillna("alpha moved")

    previous_weights = (
        previous.set_index("ticker")["weight"]
        if previous is not None
        else pd.Series(dtype=float)
    )
    ranked = rows["alpha"].abs().rank(ascending=False, method="first").astype(int)

    store.upsert(
        "proposals",
        [
            {
                "trade_date": as_of,
                "signal": manifest["signal"],
                "as_of": as_of,
                "n_names": manifest["n_names"],
                "n_excluded": manifest["n_excluded"],
                "gross": manifest["gross"],
                "net": manifest["net"],
                "n_eff": manifest["n_eff"],
                "target_annual_vol": manifest["target_annual_vol"],
                "achieved_annual_vol": manifest["achieved_annual_vol"],
                "idio_share_after_fmp": manifest["idio_share_after_fmp"],
                "max_abs_exposure_after_fmp": manifest["max_abs_exposure_after_fmp"],
                "gross_cap_bound": manifest["gross_cap_bound"],
                "nav": manifest["nav"],
                "expected_establishment_cost_bps": manifest[
                    "expected_establishment_cost_bps"
                ],
                "cost_breakdown_bps": json.dumps(manifest["cost_breakdown_bps"]),
                "notional": manifest["notional"],
                "avg_trade_size": manifest["avg_trade_size"],
                "input_as_of": json.dumps(manifest["input_as_of"]),
                "max_input_staleness_days": manifest["max_input_staleness_days"],
                "universe_source": manifest["universe_source"],
                "universe_as_of": manifest["universe_as_of"],
                "manifest": json.dumps(manifest),
            }
        ],
    )
    position_rows: list[dict[str, object]] = []
    for index, row in enumerate(rows.itertuples(index=False)):
        ticker = str(row.ticker)
        weight = float(row.weight)
        previous_weight = float(previous_weights.get(ticker, 0.0))
        position_rows.append(
            {
                "trade_date": as_of,
                "ticker": ticker,
                "weight": weight,
                "signed_notional": weight * manifest["nav"],
                "side": row.side,
                "z": float(row.z),
                "alpha": float(row.alpha),
                "rank": int(ranked.iloc[index]),
                "idio_vol": float(today_std.get(ticker, float("nan"))),
                "previous_weight": previous_weight,
                "trade": weight - previous_weight,
                "reason": row.reason,
            }
        )
    store.upsert("positions", position_rows)


def store_orders(as_of: str, dry_run: bool) -> None:
    """Write the day's order records to the store."""
    from live import store

    path = ROOT / "live" / "logs" / f"execution_{as_of}.parquet"
    if not path.exists():
        return
    execution = pd.read_parquet(path)
    orders = [
        {
            "trade_date": as_of,
            "ticker": row.ticker,
            "intended_notional": row.intended_notional,
            "filled_notional": row.filled_notional,
            "status": row.status,
            "reason": row.reason,
        }
        for row in execution.itertuples(index=False)
    ]
    store.upsert("orders", orders)


def store_reconciliation(as_of: str, row: dict) -> None:
    """Write the day's reconciliation and NAV rows to the store."""
    from live import store

    store.upsert("reconciliation", [row])
    store.upsert(
        "nav",
        [
            {
                "trade_date": as_of,
                "nav": 1_000_000.0,
                "realized_pnl": (
                    0.0 if row.get("dry_run") else float(row.get("realized_pnl") or 0.0)
                ),
                "gross_pnl": None,
                "cash": None,
            }
        ],
    )


def resolve_dry_run(value: str | None) -> bool:
    """The clock starts only on the literal string "false", any case.

    Unset, empty, unparseable, or any spelling other than an explicit false
    resolves to dry run. A missing variable must never start the clock by
    accident; that is the failure this function guards.
    """
    return (value or "").strip().lower() != "false"


def main() -> int:
    from live import evening_job, extend, morning_job, reconcile

    run_date = datetime.now(UTC).date().isoformat()
    if already_ran("live_daily", run_date):
        logger.info("already ran for %s, exit 0 (idempotent)", run_date)
        return 0

    dry_run = resolve_dry_run(os.environ.get("EFB_DRY_RUN"))
    try:
        # Extend the data and model layers by one session, then rehash.
        extend.extend_archives()
        extend.extend_prices()
        extend.extend_shares()
        extend.extend_returns()
        extend.extend_model()
        extend.refresh_version()
        from efb import evidence

        evidence.snapshot()

        # Evening: propose tomorrow's book from the latest close.
        manifest = evening_job.build_proposal()
        as_of = str(manifest["as_of"])
        store_proposal(as_of)

        # Morning: gate, guard, submit (dry run by default), reconcile.
        morning_job.run_morning(as_of, dry_run=dry_run)
        store_orders(as_of, dry_run)

        row = reconcile.daily_record(as_of, dry_run=dry_run)
        store_reconciliation(as_of, row)
    except Exception as exc:  # noqa: BLE001 - recorded, never silent
        record_run("live_daily", run_date, "failed", str(exc)[:200])
        logger.exception("live daily failed")
        return 1

    record_run("live_daily", run_date, "ok")
    logger.info("live daily completed for %s", run_date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
