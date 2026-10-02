"""The morning after: what the broker did with last evening's orders.

The evening job sends market orders after the close and does not wait for them.
A DAY order submitted at 18:30 New York fills at the next open, so the evening's
record of a leg says `ACCEPTED` and nothing more, and the question "what does the
account actually hold" has no answer until the next morning. This job answers it:
it reads the account, reads last evening's orders back from the broker by the id
the evening recorded, writes `efb.fills`, republishes the snapshot with an
"actual holdings" section beside the target book, and sends a message only when
an order did not fill.

It runs as its own cron at 15:00 UTC on weekdays, after the open the orders fill
at, and deliberately not inside the evening job. It cannot size a book and it
cannot send an order: it reads the broker through `live.fills`, which has no
submit path, and its own test drives this script against a client whose
`submit_order` raises and against a morning job patched to raise as well. A
reconciliation that could trade would be one more thing that can trade.

**Why 15:00 UTC and not 14:00.** The order of the morning matters: a market DAY
order from the previous evening fills at the 09:30 New York open, and until then
`live.fills` counts it as working rather than filled, so a run before the open
would write `filled_quantity = 0` for the whole book and email a did-not-fill line
for every leg. 14:00 UTC is after that open in the half of the year when New York
is on daylight time (10:00 EDT) and half an hour before it when it is not (09:00
EST), so it is wrong for four months of the year. 15:00 UTC is 11:00 EDT or 10:00
EST, after the open on both sides of the change, and still seven and a half hours
before that evening's run. `RUN_SLOT_UTC` below is the slot the blueprint
schedules, and the test holds the two together and against the exchange's
calendar.

It writes exactly one table, `efb.fills`, replacing the date it reconciles rather
than merging into it, so a re-run of the same morning converges instead of
doubling. Its `run_status` and `cron_runs` rows carry the job name
`fills_reconcile`, because both tables are keyed by job as well as date and a
second writer under the evening's name would overwrite the evening's record.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
# Render runs this file as `python scripts/reconcile_fills.py`, which puts
# scripts/ on sys.path and not the repository root.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_live_daily  # noqa: E402 - after the path is set

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("reconcile_fills")

# The job name is load-bearing: `run_status` is keyed by (target_close, job) and
# `cron_runs` by (run_date, job), so this name is what keeps the morning's rows
# from overwriting the evening's.
JOB = "fills_reconcile"
# The hour and minute the blueprint schedules this job for, UTC, in code so the
# arithmetic can be tested rather than described: after the 09:30 New York open in
# both EST and EDT, and before the evening run. `weekdays` is the blueprint's
# `1-5`. See the module docstring for why 14:00 was wrong.
RUN_SLOT_UTC = (15, 0)
COMPLETED_STATUSES = frozenset({"ok"})


def previous_orders(as_of: str | None = None) -> tuple[str, pd.DataFrame] | None:
    """Last evening's order rows and the close they were priced for, or None.

    Strictly before today, for the same reason the evening's own previous book is
    strict: tonight's orders do not exist yet, and a re-run of this morning must
    find the orders it reconciled rather than a book priced since.
    """
    from live import store

    frame = store.select("orders")
    if frame.empty or "trade_date" not in frame.columns:
        return None
    dates = frame["trade_date"].astype(str).str.slice(0, 10)
    cutoff = as_of or datetime.now(UTC).date().isoformat()
    earlier = frame.loc[dates < cutoff]
    if earlier.empty:
        return None
    close = str(earlier["trade_date"].astype(str).str.slice(0, 10).max())
    return close, earlier.loc[dates == close].reset_index(drop=True)


def closes_for(
    tickers: list[str], close: str, *, fetch: Any = None
) -> pd.Series:
    """The close each leg was sized from, read from the vendor for one session.

    The orders themselves carry no price, only a notional, so the close has to be
    fetched to say what a fill cost against it. One request for the names that
    traded rather than the whole universe: this job has no tree, no seed and no
    model, and it should not acquire them to price a hundred and eighty legs.
    """
    names = sorted({str(ticker) for ticker in tickers if str(ticker)})
    if not names:
        return pd.Series(dtype=float)
    from efb import prices as prices_module

    day = pd.Timestamp(close)
    frame = (
        fetch or prices_module.download_prices
    )(
        names,
        start=(day - pd.Timedelta(days=10)).date().isoformat(),
        end=(day + pd.Timedelta(days=1)).date().isoformat(),
        prewarm=True,
    )
    frame = frame.reset_index()
    frame["date"] = pd.to_datetime(frame["date"])
    session = frame.loc[frame["date"] == day]
    if session.empty:
        return pd.Series(dtype=float)
    return session.set_index("ticker")["close"].astype(float)


def publish(
    block: dict[str, Any], *, getter: Any = None, poster: Any = None
) -> list[str]:
    """Republish the snapshot with the actual holdings added, and nothing else.

    The document that is already up is the one republished, with one key added,
    rather than a payload rebuilt from the store. The target book, its close, its
    hedge and its breadth on that document are the evening's own bytes, and a
    second writer that rebuilds them is a second chance to publish a book the run
    that traded never produced. `generated_at` is left as it is for the same
    reason: the book was generated then, and this morning only added to it.
    """
    from live import snapshot

    published = json.loads(
        snapshot.get_object_text(snapshot.LATEST_KEY, getter=getter)
    )
    published["actual_holdings"] = block
    text = snapshot.payload_text(published)
    keys = snapshot.keys_for(published.get("target_close"))
    for key in keys:
        snapshot.put_object(key, text, poster=poster)
    return keys


def main(argv: list[str] | None = None) -> int:
    """Reconcile one morning. Returns the process exit code."""
    from live import (
        alpaca,
        fills,
        notify,
        positions,
        snapshot,
        staleness,
        store,
    )

    run_date = datetime.now(UTC).isoformat()
    today = datetime.now(UTC).date()
    if not staleness.is_session(today):
        # A closed day settles nothing: the orders are still working at the
        # broker, waiting for the next open, and an evening that reported them as
        # unfilled would be reporting the calendar.
        logger.info("no NYSE session on %s: nothing settled, nothing to reconcile", today)
        return 0
    if run_live_daily.already_ran(JOB, today.isoformat()):
        logger.info("%s already ran for %s", JOB, today.isoformat())
        return 0

    found = previous_orders(today.isoformat())
    if found is None:
        logger.info("no orders are stored before %s: nothing to reconcile", today)
        run_live_daily.record_run(
            JOB, today.isoformat(), "ok", "no orders to reconcile"
        )
        return 0
    close, orders = found

    detail = ""
    status = "ok"
    filled_notional = 0.0
    report: dict[str, Any] = {}
    keys: list[str] = []
    message = None
    holdings: dict[str, Any] = {}
    try:
        # The account, not the store: this job exists to say what the account
        # holds, and `dry_run=False` is what makes a failed broker read raise
        # instead of falling back to the book the loop believed it held.
        holdings = positions.check(dry_run=False, before=close)
        nav = float(holdings["nav"])
        client = alpaca.connect(dry_run=False)
        closes = closes_for(
            [str(ticker) for ticker in orders["ticker"]], close
        )
        report = fills.reconcile_day(orders, client, closes=closes, nav=nav)
        frame = report["fills"]
        if len(frame):
            store.replace_by_date("fills", close, frame.to_dict("records"))
            filled_notional = float(frame["filled_notional"].abs().sum())
        detail = (
            f"fills: {report['n_filled']} of {report['n_orders']} order(s) filled"
            f", {report['n_unfilled']} did not, {report['not_sent']} never sent"
            f", realized {_bps(report['realized_cost_bps'])}"
        )

        expected = None
        try:
            published = json.loads(snapshot.get_object_text(snapshot.LATEST_KEY))
            expected = (published.get("book") or {}).get("expected_cost_bps")
        except Exception as exc:  # noqa: BLE001 - the cost pair is not the job
            logger.warning("could not read the published book: %s", type(exc).__name__)
        block = fills.actual_holdings(
            holdings.get("held") or {},
            nav,
            as_of=run_date,
            close=close,
            report=report,
            expected_cost_bps=expected,
        )
        try:
            keys = publish(block)
        except Exception as exc:  # noqa: BLE001 - the reconciliation stands alone
            # A snapshot that cannot be published is reported and does not fail
            # the job: what the owner needs from this morning is the fills and,
            # when something did not fill, the message. The page section is the
            # third thing, not the first.
            logger.warning("could not publish the snapshot: %s", type(exc).__name__)
            detail += f"; snapshot not published ({type(exc).__name__})"

        if report["unfilled"] or report["unread"]:
            message = notify.notify_run(
                status="ok",
                target_close=close,
                dry_run=False,
                orders=report["n_orders"],
                gross=filled_notional,
                detail=detail,
                store=store.store_label(),
                fills={**report, "expected_cost_bps": expected},
            )
            if message["status"] != notify.STATUS_SENT:
                status, detail = "error", f"the message could not be sent: {detail}"
    except Exception as exc:  # noqa: BLE001 - recorded and retried, never silent
        status = "error"
        detail = notify.scrub(f"fills reconciliation failed: {type(exc).__name__}: {exc}")
        logger.error("%s", detail)

    row = staleness.run_status_row(
        {"job": JOB, "target_close": close, "status": status},
        run_date=run_date,
        status=status,
        dry_run=False,
        detail=detail,
        notify_status=(
            "not needed"
            if message is None
            else ("sent" if status == "ok" else "failed")
        ),
        notify_failed=bool(message is not None and status != "ok"),
        n_orders=int(report.get("n_orders") or 0),
        gross_notional=filled_notional,
        snapshot=(", ".join(keys) if keys else None),
        positions_check=holdings or None,
    )
    store.upsert(staleness.TABLE, [row])
    run_live_daily.record_run(JOB, today.isoformat(), status, detail)
    logger.info("%s %s: %s", JOB, status, detail)
    return 0 if status in COMPLETED_STATUSES else 1


def _bps(value: Any) -> str:
    """A bp figure for the log line, or a word when the day had no fills."""
    return "no fills priced" if value is None else f"{float(value):.2f} bps of NAV"


if __name__ == "__main__":
    raise SystemExit(main())
