"""The daily live cron: hydrate, extend, gate, propose, execute, reconcile.

One Render cron runs this after the US close. It hydrates every model input
from the git seed plus the Postgres appendix (live.appendix), extends each by
one session, checks that no input is stale (live.staleness), writes the new
sessions back to the appendix, builds the evening proposal, runs the morning
execution (dry run unless EFB live keys are present), and stores the day's
forecast beside its outcome. The live series goes to Supabase through
live.store, which falls back to local files when Supabase is not configured.
Every run is recorded in cron_runs and in run_status, so a re-fire is a no-op
rather than a duplicate.

The gate sits after the extension, because the extension is what makes the
inputs fresh, and before any sizing. A stale input stops the run there: no
proposal row, no order, a `run_status` row naming the input and its distance in
NYSE sessions, and a nonzero exit so Render marks the cron run failed.

Every run then notifies the owner, clean ones included (live.notify, Part 3b),
so the absence of the evening message is the alarm. The message goes out after
the proposal and the orders, never before, so a failed send cannot block or
roll back a run; a run whose message was not delivered exits nonzero.

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
from typing import Any

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
    return rows


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


def store_proposal(as_of: str, data_root: Path | None = None) -> pd.DataFrame:
    """Write the proposal manifest, positions and trade reasons to the store.

    Returns the rows it wrote, reasons attached, because the snapshot carries the
    same book the store does and re-deriving it would let the two disagree.
    """
    from live import store, trade_reasons

    root = Path(data_root) if data_root is not None else ROOT / "data"
    manifest = json.loads((PROPOSAL_DIR / f"proposal_{as_of}.json").read_text())
    rows = pd.read_parquet(PROPOSAL_DIR / f"proposal_{as_of}.parquet")
    proposal_paths = sorted(PROPOSAL_DIR.glob("proposal_*.parquet"))
    previous = None
    if len(proposal_paths) > 1 and proposal_paths[-1].stem == f"proposal_{as_of}":
        previous = pd.read_parquet(proposal_paths[-2])

    specific = pd.read_parquet(root / "models" / "XS-v1" / "specific_var.parquet")
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
                "n_eff_kept": manifest["n_eff_kept"],
                "n_eff_full_book": manifest["n_eff_full_book"],
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


def _catch_up_sessions(before: pd.Timestamp | None) -> list[str]:
    """The sessions this run appended, as ISO dates.

    A normal evening appends one session and the first run on a fresh container
    appends several. Reading the panel before and after the extension makes that
    a measurement rather than an assumption, and the run has to be able to say
    which sessions it caught up: a gate close is a run whose target close is the
    only session it appended, so a catch-up run can never be one.
    """
    from live import extend, staleness

    after = extend.last_price_session()
    if before is None or after is None or after <= before:
        return []
    start = before + pd.Timedelta(days=1)
    return [day.date().isoformat() for day in staleness.sessions(start, after)]


def finish_run(
    *,
    run_date: str,
    result: dict[str, Any],
    status: str,
    dry_run: bool,
    detail: str = "",
    orders: int | None = None,
    gross: float | None = None,
    error_type: str | None = None,
    catch_up_sessions: list[str] | None = None,
    splits: list[str] | None = None,
    flags: list[dict[str, Any]] | None = None,
    started_at: str | None = None,
    cross_checks_capped: str | None = None,
    manifest: dict[str, Any] | None = None,
    book: pd.DataFrame | None = None,
    reconciliation: dict[str, Any] | None = None,
    init: bool = False,
    poster: Any = None,
    snapshot_poster: Any = None,
) -> int:
    """Snapshot the run, notify the owner, record it, and return the exit code.

    Order matters three ways. The snapshot is written first, so the page shows the
    run even when the run failed and even when the message could not go out. The
    message goes second, after the proposal and the orders and never before, so a
    failed send can neither block nor roll back the run. The row goes third,
    carrying what the message said and what the snapshot is. A run whose message
    was not delivered, or whose snapshot could not be uploaded, exits nonzero:
    the owner was not told, or the page cannot show it, and either way the run did
    not do its job.
    """
    from live import notify, staleness, store
    from live import snapshot as snapshot_module
    from live.store import store_label

    store_name = store_label()
    row = staleness.run_status_row(
        result,
        run_date=run_date,
        status=status,
        dry_run=dry_run,
        detail=detail,
        n_orders=orders,
        gross_notional=gross,
        catch_up=len(catch_up_sessions or []) > 1,
        catch_up_sessions=catch_up_sessions,
        splits=splits,
        flags=flags,
        started_at=started_at,
        cross_checks_capped=cross_checks_capped,
        init=init,
    )
    book_reason: str | None = None
    if manifest is None:
        # A stopped run still has a book to show: the last one the loop proposed,
        # read from the store rather than from the deploy image's disk. The page
        # must not blank on the evening the loop refused to price another, and it
        # must not show a committed file as the book the owner holds either. When
        # the store holds none, the book is empty and `book_reason` says why.
        manifest, book, book_reason = snapshot_module.previous_proposal()
    if reconciliation is None:
        reconciliation = result.get("reconciliation") or {}
    snapshot_detail, snapshot_failed = "", False
    try:
        written = snapshot_module.write_snapshot(
            run={**row, "store": store_name},
            manifest=manifest,
            book=book,
            reconciliation=reconciliation,
            construction=snapshot_module.chosen_row(manifest),
            book_reason=book_reason,
            dry_run=dry_run,
            poster=snapshot_poster,
        )
        snapshot_detail = str(written["detail"])
        row["snapshot"] = snapshot_detail
    except Exception as exc:  # noqa: BLE001 - recorded, and it fails the run
        snapshot_failed = True
        snapshot_detail = notify.scrub(f"snapshot failed: {type(exc).__name__}: {exc}")
        row["snapshot"] = snapshot_detail
        logger.error("%s", snapshot_detail)
        if status == "ok":
            # With the switch on, a snapshot that cannot be uploaded is a failure
            # of the run, exactly as a message that cannot be sent is.
            status, detail = "error", snapshot_detail
            row["status"], row["detail"] = status, detail
    notified = notify.notify_run(
        status=status,
        target_close=result.get("target_close"),
        dry_run=dry_run,
        orders=orders,
        gross=gross,
        worst_input=result.get("worst_input"),
        worst_sessions_behind=result.get("worst_sessions_behind"),
        failures=result.get("failures") or [],
        detail=detail,
        error_type=error_type,
        catch_up_sessions=catch_up_sessions,
        splits=splits,
        flags=flags,
        store=store_name,
        snapshot=snapshot_detail,
        cross_checks_capped=cross_checks_capped,
        init=init,
        poster=poster,
    )
    delivered = notified["status"] == notify.STATUS_SENT
    store_failed = False
    row["notify_status"] = notified["status"]
    row["notify_failed"] = not delivered
    try:
        store.upsert(staleness.TABLE, [row])
    except Exception as exc:  # noqa: BLE001 - the message already went out
        # The store is what failed, so there is nowhere to record it: the
        # message the owner already has is the report, and the exit code
        # below is nonzero.
        store_failed = True
        logger.error(
            "could not record the run status: %s",
            notify.scrub(f"{type(exc).__name__}: {exc}"),
        )
    cron_detail = detail
    if notified["status"] == notify.STATUS_FAILED:
        cron_detail = f"{detail} | notification failed: {notified['detail']}"
        logger.error("notification failed: %s", notified["detail"])
    elif notified["status"] == notify.STATUS_SKIPPED:
        # On the row and on the dashboard; not noise in the cron's own line.
        logger.warning("no notification channel: %s", notified["detail"])
    try:
        record_run("live_daily", run_date, status, cron_detail.strip(" |"))
    except Exception as exc:  # noqa: BLE001 - the message already went out
        store_failed = True
        logger.error(
            "could not record the cron run: %s",
            notify.scrub(f"{type(exc).__name__}: {exc}"),
        )
    logger.info("run recorded as %s, notification %s", status, notified["status"])
    if not delivered or store_failed or snapshot_failed:
        return 1
    return 0 if status == "ok" else 1


def main() -> int:
    from live import (
        corporate_actions,
        evening_job,
        extend,
        morning_job,
        notify,
        reconcile,
        staleness,
        store,
    )

    run_date = datetime.now(UTC).date().isoformat()
    if already_ran("live_daily", run_date):
        logger.info("already ran for %s, exit 0 (idempotent)", run_date)
        return 0

    dry_run = resolve_dry_run(os.environ.get("EFB_DRY_RUN"))
    from live import appendix as appendix_mod
    from live import runroot, seed

    gate: dict[str, Any] | None = None
    catch_up_sessions: list[str] = []
    splits: list[str] = []
    flags: list[dict[str, Any]] = []
    capped: str = ""
    # Whether this run seeded the store. False on every path that is not the
    # explicit first run, including a run that fails before the guard decides.
    first_run = False
    # The instant the run began, recorded so the gate can tell an evening of the
    # close from a run that was delayed into the next morning.
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    # Filled on the success path; a stopped or failed run writes the snapshot
    # without them, and it falls back to the last proposal on disk.
    snapshot_inputs: dict[str, Any] = {}
    try:
        # The model inputs are the git seed plus the Postgres appendix, so a
        # fresh container starts from seed plus every session the loop has
        # appended, not from the deploy date.
        # The store, before anything is read or written. A missing connection
        # string on Render would otherwise send the evening to a disk the next
        # container never sees while the run still reported ok, so the mode is
        # decided here and a misconfiguration stops the run as an error.
        logger.info("store: %s", store.store_label())
        store.store_mode()
        # The run's own tree, built before anything is read. Every live module's
        # default resolves to it from here, so nothing under the repository's
        # data/ is written even though the run appends sessions and refits
        # models, and a container that has only the deploy image still has
        # artifacts to read. A seed that cannot be supplied raises inside this
        # try, so the failure is a run with an email rather than a traceback.
        run_tree = runroot.prepare()
        runroot.adopt(run_tree)
        # From here the run may read nothing under the tree that the seed did not
        # supply. The seed is the bucket's manifest on the deploy path and the
        # copied tree on the local one, and either way a read outside it is a file
        # the loop needs and the seed does not hold. Better a refusal that names
        # the path here than a crash on Render the message cannot explain.
        logger.info("seed allowlist: %s path(s) allowed", seed.guard(run_tree))
        # The proposal files move with the tree, so a local run does not add a
        # proposal to the repository either.
        global PROPOSAL_DIR
        PROPOSAL_DIR = run_tree.parent / "proposals"
        logger.info("run tree: %s", run_tree)
        # First-run detection is explicit, never inferred from what the tables
        # happen to hold: an empty appendix refuses to run unless
        # EFB_INIT_STORE=true says so, and that flag seeds the store once, writes
        # the marker and is removed afterwards. A flag left set on a seeded store
        # fails the evening loudly, and a marker with an empty appendix is an
        # error whatever the flag says, because data was lost after the seed and
        # it is never re-seeded automatically.
        first_run = appendix_mod.open_store()
        if first_run:
            logger.info(
                "first run: seeded the appendix from the git artifacts through %s",
                appendix_mod.SEED_FROM.date(),
            )
        # The sessions this run appends are measured, not assumed: the first run
        # on a fresh container finds the panel sessions behind and catches them
        # up in one go, and a catch-up run may not be one of the gate's closes.
        before_last = extend.last_price_session()
        # Extend the data and model layers by one session.
        extend.extend_archives()
        extend.extend_prices()
        extend.extend_shares()
        extend.extend_returns()
        # The corporate-actions rule, in the append path and before anything reads
        # the returns. The vendor back-adjusts history on a split, this pipeline
        # only appends, and a raw halving would slip under the 50% outlier flag.
        # The appended session's return is computed from the raw closes and the
        # factor, so no stored row is restated. A back-adjustment no record
        # explains raises here, before the gate and before any sizing.
        outcome = corporate_actions.apply_to_artifact(run_tree, since=before_last)
        if outcome.splits:
            splits = [corporate_actions.describe([split]) for split in outcome.splits]
            store.upsert(
                corporate_actions.TABLE,
                corporate_actions.rows(
                    outcome.splits,
                    outcome.sessions[-1] if outcome.sessions else before_last,
                    outcome.ratios,
                ),
            )
            logger.info("corporate actions applied: %s", "; ".join(splits))
        capped = corporate_actions.cap_note(outcome.unchecked)
        if capped:
            logger.warning("%s", capped)
        flags = outcome.flags
        if flags:
            logger.warning("large moves in the appended session: %s", flags)
        extend.extend_model()
        # `data/VERSION.json` is not rehashed here, and nothing in the live loop
        # writes it. It belongs to the research pipeline, which is what E1 to E10
        # were scored on, and a loop that rewrote it would replace that record
        # with its own extended artifacts. The loop's integrity is the seed
        # manifest's hashes instead: every seed file is verified before the run
        # does anything, so a changed input fails there rather than being
        # rehashed into a version file nobody can place.
        catch_up_sessions = _catch_up_sessions(before_last)
        if len(catch_up_sessions) > 1:
            logger.info(
                "catch-up run: appended %s sessions (%s)",
                len(catch_up_sessions),
                ", ".join(catch_up_sessions),
            )
        # Write the sessions the run created back to the appendix, then name
        # the appendix state the proposal is priced from.
        appendix_mod.persist_new_sessions()
        appendix_identity = appendix_mod.appendix_manifest()
        # No evidence snapshot here, deliberately. `efb.evidence.snapshot` rewrites
        # the tracked, LFS-committed evidence tree, and it is a local sprint-close
        # step: a cron calling it would replace the frozen record of what E1 to E10
        # were scored on with the loop's own extended artifacts.

        # The gate, before any sizing: a book priced on an input older than the
        # close it claims to price must not be built and must not trade. The
        # evidence goes in the store as well as on the exit code, because the
        # dashboard reads run_status and never the latest proposal.
        gate = staleness.check()
        if gate["status"] != "ok":
            stopped = staleness.describe_failures(gate["failures"])
            logger.error(
                "stale stop for the %s close: %s", gate["target_close"], stopped
            )
            return finish_run(
                run_date=run_date,
                result=gate,
                status="stale_stopped",
                dry_run=dry_run,
                detail=stopped,
                catch_up_sessions=catch_up_sessions,
                init=first_run,
            )

        # Evening: propose tomorrow's book from the latest close.
        manifest = evening_job.build_proposal(appendix=appendix_identity)
        as_of = str(manifest["as_of"])
        book = store_proposal(as_of, run_tree)

        # Morning: gate, guard, submit (dry run by default), reconcile.
        morning = morning_job.run_morning(as_of, dry_run=dry_run)
        store_orders(as_of, dry_run)

        row = reconcile.daily_record(as_of, dry_run=dry_run)
        store_reconciliation(as_of, row)
        snapshot_inputs = {
            "manifest": manifest,
            "book": book,
            "reconciliation": row,
        }
    except Exception as exc:  # noqa: BLE001 - recorded, never silent
        # The reason is scrubbed before it goes anywhere: a connection string,
        # a key or the webhook URL must not reach the message or the store.
        detail = notify.scrub(f"{type(exc).__name__}: {exc}")[:200]
        logger.exception("live daily failed")
        return finish_run(
            run_date=run_date,
            result=gate if gate is not None else staleness.error_result(detail),
            status="error",
            dry_run=dry_run,
            detail=detail,
            error_type=type(exc).__name__,
            catch_up_sessions=catch_up_sessions,
            init=first_run,
        )

    return finish_run(
        run_date=run_date,
        result=gate,
        status="ok",
        dry_run=dry_run,
        orders=int(morning.get("orders") or 0),
        gross=float(morning.get("intended_notional") or 0.0),
        catch_up_sessions=catch_up_sessions,
        splits=splits,
        flags=flags,
        started_at=started_at,
        cross_checks_capped=capped,
        init=first_run,
        **snapshot_inputs,
    )


if __name__ == "__main__":
    raise SystemExit(main())
