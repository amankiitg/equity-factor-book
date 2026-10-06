"""The morning after: what the broker did with last evening's orders.

The evening job sends market orders after the close and does not wait for them.
A DAY order submitted at 18:30 New York fills at the next open, so the evening's
record of a leg says `ACCEPTED` and nothing more, and the question "what does the
account actually hold" has no answer until the next morning. This job answers it:
it reads the account, reads last evening's orders back from the broker by the id
the evening recorded, writes `efb.fills`, republishes the snapshot with an
"actual holdings" section beside the target book, and sends a message only when
an order did not fill.

It runs as the morning half of the one cron service, at 15:30 UTC on weekdays, after
the open the orders fill at, and deliberately not inside the evening run. It cannot
size a book and it cannot send an order: it reads the broker through `live.fills`,
which has no submit path, and its own test drives this script against a client whose
`submit_order` raises and against a morning job patched to raise as well. A
reconciliation that could trade would be one more thing that can trade.

**Why 15:30 UTC and not 14:00.** The order of the morning matters: a market DAY
order from the previous evening fills at the 09:30 New York open, and until then
`live.fills` counts it as working rather than filled, so a run before the open
would write `filled_quantity = 0` for the whole book and email a did-not-fill line
for every leg. 14:00 UTC is after that open in the half of the year when New York
is on daylight time (10:00 EDT) and half an hour before it when it is not (09:00
EST), so it is wrong for four months of the year. 15:30 UTC is 11:30 EDT or 10:30
EST, after the open on both sides of the change, before noon in New York (which is
how `scripts/run_cron.py` routes a start to this job), and still seven hours before
that evening's run. `RUN_SLOT_UTC` below is the slot the blueprint schedules, and
the test holds the two together and against the exchange's calendar.

It writes exactly one table, `efb.fills`, replacing the date it reconciles rather
than merging into it, so a re-run of the same morning converges instead of
doubling. Its `run_status` and `cron_runs` rows carry the job name
`fills_reconcile`, because both tables are keyed by job as well as date and a
second writer under the evening's name would overwrite the evening's record.

**Which date each row carries, and why they differ.** `run_status` is keyed by
`(target_close, job)` and this job's row carries **the evening whose orders it
reconciles**, because that evening is what the row is about: `efb.fills` is written
under that close, the republished snapshot is keyed by it, and the notification
names it, so the fills, the page, the message and this row are all one evening's.
It cannot collide with that evening's `live_daily` row, because the job name is
part of the key, and a morning that runs late or is retried the next day still
lands on the same evening's row rather than inventing a second one. `cron_runs` is
keyed by `(run_date, job)` and carries **the day the job ran**, because that
table's question is whether the cron fired today, and `already_ran` reads that key
to make a second fire on the same morning a no-op. The day the job ran is on the
`run_status` row as well, in its own `run_date` field, so keying the row to the
evening loses nothing.
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
# both EST and EDT, and before the evening run. It is one slot in the one service's
# schedule (`scripts/run_cron.py::SCHEDULE`), whose hour field lists both hours and
# whose router decides between them on the New York clock; `weekdays` is the
# blueprint's `1-5`. See the module docstring for why 14:00 was wrong.
RUN_SLOT_UTC = (15, 30)
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


def closes_for(tickers: list[str], close: str, *, fetch: Any = None) -> pd.Series:
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
    frame = (fetch or prices_module.download_prices)(
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
    block: dict[str, Any],
    *,
    notify_status: str | None = None,
    getter: Any = None,
    poster: Any = None,
) -> list[str]:
    """Republish the snapshot with the actual holdings added, and little else.

    The document that is already up is the one republished, with one key added,
    rather than a payload rebuilt from the store. The target book, its close, its
    hedge and its breadth on that document are the evening's own bytes, and a
    second writer that rebuilds them is a second chance to publish a book the run
    that traded never produced. `generated_at` is left as it is for the same
    reason: the book was generated then, and this morning only added to it.

    `notify_status` is the one field the evening's own bytes cannot be trusted
    for: the snapshot was written *before* the message went out, so it carries
    `pending` however the send went. This morning has since read the evening's
    row, which holds what actually happened, and writes it back so the page can
    say the owner was never told rather than showing a pending forever. None
    leaves the document's own value alone, which is what a morning with no
    evening row to read must do rather than inventing a status.
    """
    from live import snapshot

    published = json.loads(snapshot.get_object_text(snapshot.LATEST_KEY, getter=getter))
    published["actual_holdings"] = block
    run_status = published.get("run_status")
    if notify_status is not None and isinstance(run_status, dict):
        run_status["notify_status"] = notify_status
    text = snapshot.payload_text(published)
    keys = snapshot.keys_for(published.get("target_close"))
    for key in keys:
        snapshot.put_object(key, text, poster=poster)
    return keys


def evening_notify_status(close: str) -> str | None:
    """The evening run's actual notify_status for one close, or None.

    The evening's snapshot is written before its message is sent, so its own
    `notify_status` is `pending` even on an evening whose email went out; the
    `run_status` row is updated afterwards with what the send did. This is the
    read that puts the truth back on the page, and it is deliberately a read of
    the row rather than of the snapshot: the snapshot is exactly the artifact
    that cannot know.
    """
    from live import staleness, store

    try:
        frame = store.select(staleness.TABLE)
    except Exception as exc:  # noqa: BLE001 - the page keeps the pending status
        logger.warning(
            "could not read the evening's run status: %s", type(exc).__name__
        )
        return None
    if frame.empty or not {"job", "target_close"} <= set(frame.columns):
        return None
    day = str(close)[:10]
    rows = frame.loc[
        (frame["job"].astype(str) == staleness.JOB)
        & (frame["target_close"].astype(str).str.slice(0, 10) == day)
    ]
    if rows.empty:
        return None
    value = rows.iloc[-1].get("notify_status")
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    return str(value)


def _notionals(orders: pd.DataFrame) -> tuple[float, float]:
    """(sent, never-sent) intended notional for one evening's order rows.

    A leg with a `broker_order_id` was sent and is one the broker could have
    filled; a leg without one is one the evening decided against, and its notional
    is what the evening's own `gross` counted in as though it had traded. The two
    are the pair the morning message labels.

    Zero for a frame that cannot answer rather than a raised error: the count is
    the morning's job and a notional line is not worth failing the run over.
    """
    if orders.empty or "intended_notional" not in orders.columns:
        return 0.0, 0.0
    if "broker_order_id" not in orders.columns:
        return float(orders["intended_notional"].abs().sum()), 0.0
    sent = orders["broker_order_id"].astype(str).str.len() > 0
    values = orders["intended_notional"].abs()
    return float(values[sent].sum()), float(values[~sent].sum())


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
        logger.info(
            "no NYSE session on %s: nothing settled, nothing to reconcile", today
        )
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
    # The evening's actual notification outcome, read from its own row rather
    # than from the snapshot it wrote before it sent. The page carries `pending`
    # otherwise, forever, which is the one status it must never show.
    notify_status = evening_notify_status(close)
    # What the evening sent, and what it left unsent under the minimum. The legs
    # are the evening's own rows: the two notionals are the pair the morning
    # message labels so a `gross` figure cannot be read as the wrong one.
    sent_notional, unsent_notional = _notionals(orders)
    # The page write is the one step here that can fail without the reconciliation
    # being wrong, and a page that did not go up is a failed morning rather than a
    # footnote on a healthy one. None means it went up.
    snapshot_failure: str | None = None
    try:
        # The account, not the store: this job exists to say what the account
        # holds, and `dry_run=False` is what makes a failed broker read raise
        # instead of falling back to the book the loop believed it held.
        holdings = positions.check(dry_run=False, before=close, include_close=True)
        nav = float(holdings["nav"])
        client = alpaca.connect(dry_run=False)
        closes = closes_for([str(ticker) for ticker in orders["ticker"]], close)
        report = fills.reconcile_day(orders, client, closes=closes, nav=nav)
        frame = report["fills"]
        if len(frame):
            store.replace_by_date("fills", close, frame.to_dict("records"))
            filled_notional = float(frame["filled_notional"].abs().sum())
        # What left the account since the evening last read it, and what explains
        # it: a filled close from this very reconciliation, or an activity of the
        # broker's own. Read here because this is where the account is read and
        # where a silent removal has to be caught - the departure is invisible in
        # every other number this job writes, and the fills above are the only
        # record of a close that could explain it.
        exits = positions.unexplained_since_last_read(
            close,
            holdings.get("broker"),
            closed=positions.closed_shares(frame),
        )
        if exits["exits"]:
            detail_tail = "; ".join(
                f"{item['ticker']} {abs(float(item['quantity'])):,.2f} shares "
                f"(${abs(float(item['notional'])):,.2f}) left with no order"
                for item in exits["exits"]
            )
            logger.warning(
                "%d position(s) left the account: %s", len(exits["exits"]), detail_tail
            )
        detail = (
            f"fills: {report['n_filled']} of {report['n_orders']} order(s) filled"
            f", {report['n_unfilled']} did not, {report['not_sent']} never sent"
            f", realized {_bps(report['realized_cost_bps'])}"
        )
        if exits["exits"]:
            detail += f"; {len(exits['exits'])} position(s) left with no order"

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
            # This run is the morning: the book it read is what the evening's
            # orders left behind, which is why the fills travel with it and why
            # `close` is the evening they settled for.
            read_by=fills.READ_MORNING,
            # The names that left the account with nothing behind them, drawn with
            # the holdings because that is where a reader looks for a name that is
            # no longer there.
            exits=exits,
        )
        try:
            keys = publish(block, notify_status=notify_status)
        except Exception as exc:  # noqa: BLE001 - named below, never swallowed
            snapshot_failure = (
                f"the snapshot was not published: {type(exc).__name__}: {exc}"
            )
            logger.error("%s", notify.scrub(snapshot_failure))

        message_detail = detail
        if snapshot_failure is not None:
            # The published object is the book the next evening reads and the page
            # the owner looks at, so a write that failed has left the loop on the
            # previous evening's page. That is this morning's failure rather than a
            # footnote on a healthy one: the run is marked failed, the process
            # exits nonzero so the cron shows it and the retry is allowed to fire,
            # and the owner is told. The fills above stay written, because they are
            # the morning's own record and a rerun converges on them instead of
            # needing them back.
            status = "error"
            detail = notify.scrub(f"{snapshot_failure}; {detail}")
            # The message's own reason is the write that failed: the realised cost
            # and the count of filled legs are the fill lines' business.
            message_detail = notify.scrub(snapshot_failure)

        if (
            report["unfilled"]
            or report["not_sent_lines"]
            or report["unread"]
            or exits["exits"]
            or snapshot_failure is not None
        ):
            message = notify.notify_fills(
                status=status,
                target_close=close,
                fills={**report, "expected_cost_bps": expected},
                detail=message_detail,
                store=store.store_label(),
                snapshot=", ".join(keys) if keys else None,
                sent_notional=sent_notional,
                unsent_notional=unsent_notional,
                filled_notional=filled_notional,
                # A position that left the account with nothing behind it is the
                # one thing this message must never lose to a condition: it is
                # part of what triggers the send above for exactly that reason.
                exits=exits,
            )
            if message["status"] != notify.STATUS_SENT:
                status, detail = "error", f"the message could not be sent: {detail}"
    except Exception as exc:  # noqa: BLE001 - recorded and retried, never silent
        status = "error"
        detail = notify.scrub(
            f"fills reconciliation failed: {type(exc).__name__}: {exc}"
        )
        logger.error("%s", detail)

    row = staleness.run_status_row(
        # Keyed to the evening it reconciled, not to this morning: the fills, the
        # snapshot and the message all belong to that close. The morning is on the
        # row as `run_date` below.
        {"job": JOB, "target_close": close, "status": status},
        run_date=run_date,
        status=status,
        dry_run=False,
        detail=detail,
        notify_status=(
            "not needed"
            if message is None
            else ("sent" if message["status"] == notify.STATUS_SENT else "failed")
        ),
        # Keyed to the message's own outcome rather than to the run's status: a
        # morning can fail its page write and still have told the owner about it,
        # and a row that read that as a failed notification would send the reader
        # looking at the messenger instead of at the bucket.
        notify_failed=bool(
            message is not None and message["status"] != notify.STATUS_SENT
        ),
        n_orders=int(report.get("n_orders") or 0),
        gross_notional=filled_notional,
        snapshot=(", ".join(keys) if keys else None),
        positions_check=holdings or None,
    )
    store.upsert(staleness.TABLE, [row])
    # `cron_runs` answers whether the cron fired today, so this record keeps the day
    # the job ran; the row above is keyed to the evening it reconciled.
    run_live_daily.record_run(JOB, today.isoformat(), status, detail)
    logger.info("%s %s: %s", JOB, status, detail)
    return 0 if status in COMPLETED_STATUSES else 1


def _bps(value: Any) -> str:
    """A bp figure for the log line, or a word when the day had no fills."""
    return "no fills priced" if value is None else f"{float(value):.2f} bps of NAV"


if __name__ == "__main__":
    raise SystemExit(main())
