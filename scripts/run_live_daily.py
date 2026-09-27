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

Two guards stand in front of the sizing. The account is read every evening, dry
run included, and the number Alpaca reports must be the one `EFB_ALPACA_ACCOUNT_ID`
names, because EFB's paper keys and the credit lab's sit under one login and a key
pasted from the wrong project would trade the wrong book; an evening that would
establish the whole book is refused unless the account is flat and has nothing
working at the broker. And a failure logs its traceback, formatted and scrubbed:
the frames are what say where it broke, and a credential inside one of them must
not leave the process.

Nothing executes real money. The morning path is dry run by default and
the live path needs EFB_ALPACA_PAPER_API_KEY and
EFB_ALPACA_PAPER_SECRET_KEY, which are never committed.
"""

from __future__ import annotations

import json
import logging
import math
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


# The status a run carries when it finished its work and told the owner. Only that
# marks the day done, so a failure retries on the next tick instead of being told
# it already ran on a day nothing was produced.
COMPLETED_STATUSES = frozenset({"ok", "market_closed"})


def already_ran(job: str, run_date: str) -> bool:
    """Whether this job already completed for this date.

    Only a completed status counts. A row left by a failed or incomplete attempt
    is exactly what the next tick has to retry, so treating any row as "already
    ran" would file a day nothing was produced on as finished.
    """
    from live import store

    frame = store.select("cron_runs")
    if frame.empty or "status" not in frame.columns:
        return False
    rows = frame.loc[
        (frame["run_date"] == run_date)
        & (frame["job"] == job)
        & (frame["status"].isin(COMPLETED_STATUSES))
    ]
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


def previous_book(as_of: str, proposal_paths: list[Path]) -> pd.DataFrame | None:
    """The book the loop held before this close, or None on the first evening.

    A fresh run tree carries no earlier proposal: the run root is the seed plus
    this session, so `previous` read from the tree's own proposals directory was
    always None, and every evening's reason column fell through to "alpha moved" -
    including the rows of a book that no previous close had ever held. The store
    is where the loop records what it meant to hold, so the last book strictly
    before this close comes from there, and the tree's own files stay as the
    fallback for a tree that carries them.

    Strictly before: a re-run of tonight must compare against last night, not
    against the rows it wrote earlier tonight.
    """
    from live import store

    frame = store.select("positions")
    needed = {"trade_date", "ticker", "weight", "z"}
    if not frame.empty and needed.issubset(frame.columns):
        dates = frame["trade_date"].astype(str).str.slice(0, 10)
        earlier = frame.loc[dates < as_of]
        if not earlier.empty:
            latest = earlier["trade_date"].max()
            return earlier.loc[earlier["trade_date"] == latest].reset_index(drop=True)
    if len(proposal_paths) > 1 and proposal_paths[-1].stem == f"proposal_{as_of}":
        return pd.read_parquet(proposal_paths[-2])
    return None


def previous_close(
    previous: pd.DataFrame | None, fallback: pd.Timestamp
) -> pd.Timestamp:
    """The close the previous book was held at, or the caller's close.

    The previous book's own trade date is the close its risk was measured at. A
    book without one cannot date the comparison, so the caller's close stands in
    and the answer degrades to what it was before rather than failing the run.
    """
    if previous is not None and len(previous) and "trade_date" in previous.columns:
        dates = pd.to_datetime(previous["trade_date"])
        if not dates.isna().all():
            return pd.Timestamp(dates.max())
    return fallback


def prior_book(
    holdings: dict[str, Any], intentions: pd.DataFrame | None
) -> pd.DataFrame | None:
    """The book the loop actually held, for the cost, the turnover and the reasons.

    The weights are the account's own holdings divided by the account's own equity,
    and `None` on an establishment evening, where the loop holds nothing: from flat
    the whole target trades and every previous weight is zero, which is what a
    missing book means to the callers.

    `intentions` is the store's previous proposal row, and it is read for two things
    and never for a weight. The first is the z-score each name carried at the
    previous close: z is a model input rather than a position, and it is what the
    reason classifier compares to decide whether the score moved. The second is the
    previous close's own date, which is the close the previous risk is measured at.
    A name the account holds that the previous proposal did not carry gets a z of
    zero, which reads as "the score is new here" and is the honest answer for a
    position the loop has no score for. A name the account holds at a weight the
    store never recorded is exactly the case this replaces.
    """
    from live import positions as positions_module

    prior = positions_module.prior_weights(
        holdings, establishment=bool(holdings.get("establishment"))
    )
    if prior is None or prior.empty:
        return None
    frame = pd.DataFrame(
        {
            "ticker": [str(ticker) for ticker in prior.index],
            "weight": prior.to_numpy(dtype=float),
        }
    )
    if intentions is not None and len(intentions) and "z" in intentions.columns:
        scores = intentions.loc[:, ["ticker", "z"]].drop_duplicates("ticker")
        frame = frame.merge(scores, on="ticker", how="left")
        if "trade_date" in intentions.columns and len(intentions["trade_date"]):
            frame["trade_date"] = str(intentions["trade_date"].max())
    else:
        frame["z"] = 0.0
    frame["z"] = pd.to_numeric(frame["z"], errors="coerce").fillna(0.0)
    return frame


def specific_std_or_refuse(ticker: str, today_std: pd.Series, as_of: str) -> float:
    """The name's specific standard deviation, or a refusal that names the name.

    `ebf.positions.idio_vol` is `not null`, and a NaN *satisfies* it on Postgres
    (`select float8 'NaN' is not null` is true), so until 2026-10-08 this line
    wrote `float("nan")` for a name with no estimate and let the database decide -
    which is why 2026-10-07 died here, after the whole book had been priced and
    with no orders sent. The default is a refusal now, and it names the ticker,
    because "null value in column idio_vol" without a name is a message nobody can
    act on.

    In the normal run this is unreachable: the evening drops a name the risk model
    cannot measure before it sizes anything (`live.evening_job.risk_names_or_stop`),
    so the two agree by construction. It is kept as a refusal because this function
    is also called on its own, from the day's own artifacts, and a book cannot be
    stored against a risk that was invented on the way in.
    """
    value = today_std.get(ticker)
    if value is None or not math.isfinite(float(value)):
        raise ValueError(
            f"no specific variance for {ticker} at {as_of}: the store cannot be "
            "written with a fabricated idio_vol, and the evening drops a name with "
            "no risk estimate before it sizes the book"
        )
    return float(value)


def store_proposal(
    as_of: str,
    data_root: Path | None = None,
    dry_run: bool = True,
    previous: pd.DataFrame | None = None,
    *,
    prior_settled: bool = False,
) -> pd.DataFrame:
    """Write the proposal manifest, positions and trade reasons to the store.

    Returns the rows it wrote, reasons attached, because the snapshot carries the
    same book the store does and re-deriving it would let the two disagree.

    `previous` is the book the account actually held, passed in by the caller that
    read the account, because the proposal build needs the same book for its trade
    impact. `None` with `prior_settled` true means there is no previous book at
    all, which is an establishment evening: the trade is the whole target, every
    previous weight is zero, and every row is a new position. `None` without it
    means the caller has not read a book and the store's own row is the fallback,
    which is what a caller holding only artifacts wants.
    """
    from live import reconcile as reconcile_module
    from live import store, trade_reasons

    root = Path(data_root) if data_root is not None else ROOT / "data"
    manifest = json.loads((PROPOSAL_DIR / f"proposal_{as_of}.json").read_text())
    rows = pd.read_parquet(PROPOSAL_DIR / f"proposal_{as_of}.parquet")
    proposal_paths = sorted(PROPOSAL_DIR.glob("proposal_*.parquet"))
    if previous is None and not prior_settled:
        previous = previous_book(as_of, proposal_paths)

    specific = pd.read_parquet(root / "models" / "XS-v1" / "specific_var.parquet")
    as_of_ts = pd.Timestamp(as_of)
    today_std = trade_reasons.specific_std(specific, as_of=as_of_ts)
    # The previous close's own specific standard deviation, which is what makes
    # the "risk moved" reason reachable: passing today's for both closes made the
    # comparison `abs(sigma_today - sigma_prev) > RISK_EPS * sigma_prev` false by
    # construction, so a name whose weight moved while its score did not could only
    # ever be labelled "the hedge moved". The previous book's own trade date is the
    # close to take it at, and with no previous book the argument is today's, which
    # is what an establishment day wants: every row is a new position anyway.
    prev_std = trade_reasons.specific_std(
        specific, as_of=previous_close(previous, as_of_ts)
    )

    reasons = trade_reasons.assign_trade_reasons(
        rows,
        previous,
        today_std,
        prev_std,
        # The weight materiality threshold is a dollar figure, and this is the
        # equity the book was sized on, so `$250` is the same $250 the order path
        # refuses a leg under rather than a fraction of some other book.
        nav=float(manifest.get("nav") or 0.0) or None,
    )
    # Only tonight's own rows are given a reason: the classifier's frame also
    # accounts for the names the book leaves tonight (they are a trade, and their
    # reason is "exited"), and a left join on tonight's rows is what keeps them out
    # of the stored book. Nothing here touches a weight: the reason column is the
    # only thing this merge adds, which is why the book, its hedge and its orders
    # cannot move with it.
    rows = rows.merge(reasons[["ticker", "reason"]], on="ticker", how="left")
    # Unreachable (the classifier returns a row per name in `rows`), kept because a
    # blank reason is forbidden and this column is presentation: it must not be the
    # thing that fails an evening whose orders are already sent.
    rows["reason"] = rows["reason"].fillna(trade_reasons.ALPHA_MOVED)

    previous_weights = (
        previous.set_index("ticker")["weight"]
        if previous is not None
        else pd.Series(dtype=float)
    )
    ranked = rows["alpha"].abs().rank(ascending=False, method="first").astype(int)

    # The rows are built before either write, and the refusal inside them
    # (`specific_std_or_refuse`) is why: a proposal row written first would leave
    # the day half-stored when a name has no risk estimate, and the page reads the
    # proposal. Both writes go out together or neither does.
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
                "idio_vol": specific_std_or_refuse(ticker, today_std, as_of),
                "previous_weight": previous_weight,
                "trade": weight - previous_weight,
                "reason": row.reason,
                # The proposal is the loop's intention, never a holding: a
                # holding label needs the broker to confirm a fill after
                # execution, and nothing has executed when this row is written.
                "kind": "intention",
            }
        )
    store.upsert(
        "proposals",
        [
            {
                "trade_date": as_of,
                "signal": manifest["signal"],
                "as_of": as_of,
                "n_names": manifest["n_names"],
                "n_excluded": manifest["n_excluded"],
                # The book that trades: the kept set after the hedge. The
                # 499-name book the model sized before the floor dropped any is
                # beside them under `full_book_*` names, rather than as "the
                # gross" of a book the owner does not hold.
                "gross": reconcile_module.traded_figure(manifest, "gross"),
                "net": reconcile_module.traded_figure(manifest, "net"),
                "full_book_gross": manifest["gross"],
                "full_book_net": manifest["net"],
                "n_eff_kept": manifest["n_eff_kept"],
                "n_eff_full_book": manifest["n_eff_full_book"],
                "target_annual_vol": manifest["target_annual_vol"],
                "achieved_annual_vol": reconcile_module.traded_figure(
                    manifest, "forecast_annual_vol"
                ),
                "full_book_achieved_annual_vol": manifest["achieved_annual_vol"],
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
    store.replace_by_date("positions", as_of, position_rows)
    # The rows, back to the caller, because the snapshot publishes the same book
    # and re-deriving it would let the page and the store disagree. The return was
    # missing while the docstring promised it, so the caller's `book` was None and
    # the page listed no names on every evening the loop priced its own proposal:
    # the manifest supplied the counts, the gross and the hedge, and only the
    # per-name list was empty.
    return rows


def execution_log(as_of: str) -> pd.DataFrame:
    """The day's own order rows, as the morning job wrote them, or an empty frame.

    The evening's own record of every leg it built, which is the only place the
    page's traded dollars come from: the manifest carries the book it ended up with
    and no notionals per name, and the fills of those legs do not exist until the
    next morning. An evening with no log has no orders, which is an empty frame
    rather than an error - a run that priced a book and sent nothing is a day.
    """
    path = ROOT / "live" / "logs" / f"execution_{as_of}.parquet"
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def stored_legs(as_of: str) -> pd.DataFrame | None:
    """The day's legs from `efb.orders`, or None when the store could not be read.

    The same rows `execution_log` reads from the container's own file, in the
    store instead. The file is the evening's record of the evening; the store's
    rows are the record that outlives it, and the caller here is the evening's own
    failure path - the one place the file may be missing because the container
    that wrote it is gone. `None` is not "no legs": it says the legs are unknown,
    so a caller can leave a figure off rather than publish a zero for a day whose
    orders nobody could read.
    """
    from live import store

    try:
        frame = store.select("orders")
    except Exception as exc:  # noqa: BLE001 - reported, never silent, never fatal
        logger.warning("could not read the day's legs: %s", type(exc).__name__)
        return None
    if frame.empty or not {"trade_date", "ticker", "intended_notional"} <= set(
        frame.columns
    ):
        return pd.DataFrame()
    days = frame["trade_date"].astype(str).str.slice(0, 10)
    return frame.loc[days == str(as_of)[:10]]


def sent_orders(as_of: str) -> tuple[int, float, float]:
    """(legs sent, their dollars, every leg's dollars) from the store's own rows.

    Read from `efb.orders` rather than from the run's in-memory summary, because the
    caller is the failure path: what the run thinks it did is exactly what is in
    doubt when it has just raised, and the store's leg rows are what the submission
    wrote before the failure. A leg with a broker id was sent; one without it is a
    leg the evening decided against, and its notional belongs in the sized figure
    only. Zeroes when the store holds no row for the close - a run that failed before
    it built anything - so the caller can say "none sent" rather than invent one.
    """
    from live import store

    try:
        frame = store.select("orders")
    except Exception as exc:  # noqa: BLE001 - the message is what matters here
        logger.warning("could not read the day's orders: %s", type(exc).__name__)
        return 0, 0.0, 0.0
    if frame.empty or not {"trade_date", "intended_notional"} <= set(frame.columns):
        return 0, 0.0, 0.0
    days = frame["trade_date"].astype(str).str.slice(0, 10)
    day = frame.loc[days == str(as_of)[:10]]
    if day.empty:
        return 0, 0.0, 0.0
    values = day["intended_notional"].abs()
    sent = day["broker_order_id"].astype(str).str.len() > 0
    return int(sent.sum()), float(values[sent].sum()), float(values.sum())


def traded_by_name(execution: pd.DataFrame) -> dict[str, float]:
    """{ticker: dollars traded tonight}, the leg's own absolute notional.

    Absolute, not signed: this is turnover, and the question it answers is where
    the day's trading came from - how much of it the hedge drove, how much of it a
    name that merely moved. A bucket signed the way the book's weights are would
    net a trimmed long against a bought short within one reason and report the
    trading as smaller than it was. A guard rejection and a leg under the minimum
    are both in here: they are legs of the day whose dollars did not move, which is
    exactly the fact the two columns separate.
    """
    if execution.empty or not {"ticker", "intended_notional"} <= set(execution.columns):
        return {}
    out: dict[str, float] = {}
    for row in execution.itertuples(index=False):
        ticker = str(row.ticker)
        notional = abs(float(getattr(row, "intended_notional", 0.0) or 0.0))
        out[ticker] = out.get(ticker, 0.0) + notional
    return out


def with_traded(
    book: pd.DataFrame | None, traded: dict[str, float]
) -> pd.DataFrame | None:
    """The book's rows carrying the dollars this run traded in each name.

    A name with no leg tonight is a zero, not an absent column: "the hedge moved
    this name and the run built nothing for it" is a fact about the evening, and a
    blank would read as a number nobody measured.

    A run with no book in hand keeps having none: None is the caller's way of
    saying the store holds no proposal to show, and a frame invented here would
    publish a book nobody wrote.
    """
    if book is None:
        return None
    rows = book.copy()
    rows["traded_notional"] = [
        float(traded.get(str(ticker), 0.0)) for ticker in rows["ticker"]
    ]
    return rows


def store_orders(as_of: str, dry_run: bool) -> None:
    """Write the day's order records to the store, replacing the day's old ones.

    A missing execution log is not a reason to leave the day as it was: the day
    has no orders, so the day's orders are cleared. That is the same replacement
    the rows themselves get.

    Two columns exist for the evening that reconciles fills rather than for this
    one. `position_intent` is the broker's own open-or-close decision on the leg,
    so a later reconciler can tell a close from a short without re-deriving it
    from the sign of a notional. `broker_order_id` is the broker's id for the
    order, which is what a fill has to be matched against: a fill arrives as an
    activity against an order id, and without it the only key would be the
    deterministic ticket, which the broker keeps for accepted orders only.
    """
    from live import store

    if not (ROOT / "live" / "logs" / f"execution_{as_of}.parquet").exists():
        store.replace_by_date("orders", as_of, [])
        return
    execution = execution_log(as_of)
    orders = [
        {
            "trade_date": as_of,
            "ticker": row.ticker,
            "intended_notional": row.intended_notional,
            "filled_notional": row.filled_notional,
            "status": row.status,
            "reason": row.reason,
            # The stable code for a refused or unattempted leg. Alpaca does not
            # persist a submit-time rejection, so this is the only durable
            # record that the leg was intended at all.
            "reason_code": getattr(row, "reason_code", ""),
            "client_order_id": getattr(row, "client_order_id", ""),
            "position_intent": getattr(row, "position_intent", ""),
            "broker_order_id": getattr(row, "broker_order_id", ""),
        }
        for row in execution.itertuples(index=False)
    ]
    store.replace_by_date("orders", as_of, orders)


def previous_fills(before: str) -> pd.DataFrame:
    """The fills of the last close before this one, from the store.

    The legs that could have closed a position between two account reads are the
    ones the evening before last sent: they settled at the open in between, and
    their fills are the record. The newest close strictly before `before` is that
    evening, so the rows come back keyed to it.

    An empty frame is the honest answer for a close whose morning reconciler never
    ran, and it is not the same as "nothing closed": the caller reports the
    departure with that in mind rather than reading the gap as evidence.
    """
    from live import store

    frame = store.select("fills")
    if frame.empty or "trade_date" not in frame.columns:
        return frame
    days = frame["trade_date"].astype(str).str.slice(0, 10)
    earlier = frame.loc[days < str(before)[:10]]
    if earlier.empty:
        return frame.iloc[0:0]
    close = str(earlier["trade_date"].astype(str).str.slice(0, 10).max())
    return earlier.loc[days == close].reset_index(drop=True)


def departures_since_last_read(before: str, holdings: dict[str, Any]) -> dict[str, Any]:
    """What left the account since it was last read, and what explains it.

    Both runs ask this, and both have to: the evening writes the day's
    reconciliation row and the day's P&L, and a position that walked out of the
    account with no order behind it is an adjustment to that P&L rather than a
    trade, while the morning is where the owner is told about it.

    The plausible explanations are the filled close, read from the previous close's
    fills, and the broker's own activity feed. An account that could not be read
    answers with an empty block rather than with every name in the store missing:
    the read failed, and that is not evidence about the book.
    """
    from live import positions

    if not holdings.get("account_read"):
        return {"previous_read": "", "exits": [], "feed": "", "window": ""}
    return positions.unexplained_since_last_read(
        before,
        holdings.get("broker"),
        closed=positions.closed_shares(previous_fills(before)),
    )


def stored_adjustment(as_of: str) -> float | None:
    """The adjustment the day's row already carries, or None when there is no row.

    Read for one case: a retry of an evening whose first attempt already saw the
    removal. The store's most recent broker read is then that attempt's own, so the
    comparison cannot see anything that happened before it, a fresh detection finds
    nothing - and writing that nothing over the day's figure would erase a fact the
    first attempt recorded, from a page that has no other place to keep it.
    """
    from live import store

    try:
        frame = store.select("reconciliation")
    except Exception as exc:  # noqa: BLE001 - the row keeps whatever it has
        logger.warning("could not read the day's row (%s)", type(exc).__name__)
        return None
    if frame.empty or not {"trade_date", "unexplained_adjustment"} <= set(
        frame.columns
    ):
        return None
    days = frame["trade_date"].astype(str).str.slice(0, 10)
    rows = frame.loc[days == str(as_of)[:10]]
    if rows.empty:
        return None
    value = rows.iloc[-1]["unexplained_adjustment"]
    if value is None or pd.isna(value):
        return None
    return float(value)


def store_reconciliation(as_of: str, row: dict, *, holdings: dict[str, Any]) -> None:
    """Write the day's reconciliation and NAV rows to the store.

    The NAV row is the account's own equity and cash, read in the same request
    that sized the book, rather than the constant 1,000,000 the loop used to
    write there. The read is a required argument rather than an optional one: a
    NAV row that nobody measured is what this replaces, and a caller with no
    account read would have to say so in as many words.
    """
    from live import store

    store.upsert("reconciliation", [row])
    nav = float(holdings["nav"])
    store.upsert(
        "nav",
        [
            {
                "trade_date": as_of,
                "nav": nav,
                "realized_pnl": realized_pnl(as_of, nav),
                "gross_pnl": None,
                "cash": holdings.get("cash"),
            }
        ],
    )


def store_attribution(run_tree: Path) -> dict[str, Any]:
    """Attribute every stored day without a row, from the run tree's artifacts.

    The run tree is passed rather than read from a module global, because the
    attribution reads the same extended XS-v1 artifacts the proposal was priced
    from and a global would be whichever module was adopted last.
    """
    from live import attribution_job

    return attribution_job.run(run_tree)


def realized_pnl(as_of: str, nav: float) -> float:
    """Tonight's P&L: the change in the account's own equity since the last row.

    The account's equity is the only measurement of what the book is worth, so the
    day's P&L is the change in that number and nothing else. It replaces a zero
    written every evening in dry run, which said the book had made nothing rather
    than that nobody had measured it.

    The reading it is measured against is the previous stored NAV row strictly
    before this close, so a re-run of an evening cannot measure against itself.
    Zero when the store holds no earlier row: the first evening establishes the
    book, and against no earlier equity every dollar in the account would read as
    a day's profit.
    """
    from live import store

    frame = store.select("nav")
    if frame.empty or "trade_date" not in frame.columns:
        return 0.0
    earlier = frame.loc[frame["trade_date"].astype(str) < str(as_of)]
    if earlier.empty:
        return 0.0
    previous = earlier.loc[earlier["trade_date"] == earlier["trade_date"].max()]
    prior = previous["nav"].iloc[0]
    if pd.isna(prior):
        return 0.0
    return float(nav) - float(prior)


def store_broker_book(as_of: str, holdings: dict[str, Any]) -> None:
    """The broker's own per-name book for the day, replaced by date.

    The store's `positions` table is the loop's intention, written before any
    order leaves the process; this table is the account's answer to "what do you
    hold", read in the same request that sized the book. They are different
    questions and are stored apart for that reason: a run that reads the book
    back must be able to tell what the loop meant to hold from what the broker
    reports holding, and E12's attribution must never count the first as the
    second.

    A read that failed writes nothing rather than an empty book. "The account
    holds nothing" and "the account could not be read" are different answers, and
    writing the second as the first would erase the last thing the broker did
    say.
    """
    from live import store

    if holdings.get("account_read") is not True:
        logger.warning(
            "the broker's book is not stored for %s: %s",
            as_of,
            holdings.get("broker_source", "the account could not be read"),
        )
        return
    nav = float(holdings.get("nav") or 0.0)
    quantities = holdings.get("held_quantities") or {}
    rows = [
        {
            "trade_date": as_of,
            "ticker": ticker,
            "side": "long" if float(value) >= 0 else "short",
            "quantity": (float(quantities[ticker]) if ticker in quantities else None),
            "market_value": float(value),
            "weight": (float(value) / nav) if nav else None,
        }
        for ticker, value in sorted((holdings.get("broker") or {}).items())
    ]
    store.replace_by_date("broker_positions", as_of, rows)


def resolve_dry_run(value: str | None) -> bool:
    """The clock starts only on the exact string "false".

    Unset, empty, a different case, surrounding whitespace, or any other spelling
    resolves to dry run. A missing or mistyped variable must never start the clock
    by accident; that is the failure this function guards.
    """
    return value != "false"


# The deliberate out-of-hours bypass, the env equivalent of the smoke scripts'
# `--force-hour`: the window is what keeps an order inside the after-hours session
# the broker's DAY semantics are defined for, so opening it must be explicit.
FORCE_HOUR_ENV = "EFB_FORCE_HOUR"


def resolve_force_hour(value: str | None) -> bool:
    """The window override opens only on the exact string "true".

    The opposite default from `resolve_dry_run`, and for the same reason: a
    missing or mistyped variable must never open the window, so a case difference
    or a stray space refuses the run rather than trading at the wrong hour. A
    dry-run flag left unset costs a rehearsal; a window left open costs an order
    at an hour the broker does not hold a DAY order for.
    """
    return value == "true"


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


def evening_bridge(
    as_of: Any,
    *,
    dry_run: bool,
    holdings: dict[str, Any],
    book: pd.DataFrame | None,
    legs: pd.DataFrame | None,
    reversals: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """The evening's half of the book bridge, or None on a dry run.

    Three sets on the page are correct on their own and read as three
    disagreements without the arithmetic between them: the book the model sized (191
    names on 2026-10-05), the orders the run sent (199) and the positions the
    account holds (188). This is that arithmetic, computed from the run's own read,
    its own book and its own leg rows, and published for the morning to complete
    with the fills and the account it reads.

    None on a dry run, which sends nothing: `sent` would count no leg while the book
    still holds the ones the run decided for, so the block could only be published
    broken. A dry run has no bridge to state, and the page leaves the panel out
    rather than drawing an evening that moved nothing.
    """
    if dry_run:
        return None
    from live import bridge

    return bridge.evening(
        close=as_of,
        held_before=(holdings or {}).get("broker") or {},
        book=list(book["ticker"]) if book is not None else [],
        orders=legs,
        reversals=[
            item.get("ticker") for item in reversals or [] if item.get("ticker")
        ],
    )


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
    spinoffs: list[str] | None = None,
    spinoff_missing: list[str] | None = None,
    spinoff_unusable: list[str] | None = None,
    spinoff_lookup_failed: str | None = None,
    flags: list[dict[str, Any]] | None = None,
    started_at: str | None = None,
    cross_checks_capped: str | None = None,
    establishment: bool = False,
    cost_label: str | None = "rebalance",
    brake_limit: float | None = None,
    positions_check: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    book: pd.DataFrame | None = None,
    reconciliation: dict[str, Any] | None = None,
    actual: dict[str, Any] | None = None,
    init: bool = False,
    no_price: list[str] | None = None,
    no_risk: list[dict[str, Any]] | None = None,
    thin_adv: list[dict[str, Any]] | None = None,
    poster: Any = None,
    snapshot_poster: Any = None,
    snapshot_getter: Any = None,
    deferred_reversals: list[dict[str, Any]] | None = None,
    skipped_minimum: list[dict[str, Any]] | None = None,
    skipped_borrow: list[dict[str, Any]] | None = None,
    no_asset: list[dict[str, Any]] | None = None,
    renames: dict[str, str] | None = None,
    exits: dict[str, Any] | None = None,
    sent_notional: float | None = None,
    bridge_block: dict[str, Any] | None = None,
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
    from live import notify, seed, staleness, store
    from live import snapshot as snapshot_module
    from live.store import store_label

    # The job body is over, so the read allowlist has done its work. Taking it off
    # here means the reporting steps read freely, and a process that runs the job
    # more than once does not stack one watcher per run.
    seed.unwatch()

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
        establishment=establishment,
        cost_label=cost_label,
        positions_check=positions_check,
    )
    book_reason: str | None = None
    # Whether the book in hand is the run's own proposal or the last one the store
    # holds. It decides whether the day's cost and risk belong to this row: a
    # manifest read back from the store is last evening's book, and an evening that
    # refused to price anything has no cost of its own.
    own_manifest = manifest is not None
    if manifest is None:
        # A stopped run still has a book to show: the last one the loop proposed,
        # read from the store rather than from the deploy image's disk. The page
        # must not blank on the evening the loop refused to price another, and it
        # must not show a committed file as the book the owner holds either. When
        # the store holds none, the book is empty and `book_reason` says why.
        manifest, book, book_reason = snapshot_module.previous_proposal()
        # That frame is the store's `positions` rows, which carry no
        # `traded_notional` column, so the page's trades-by-reason table read a
        # column of zeroes for a day that traded - 2026-10-06 sent $355,251.19 and
        # showed none of it. The day's legs are in the store either way, so the same
        # join the evening's own book gets is applied to the borrowed one, from the
        # same definition: `traded_by_name` over that close's legs, a name with no
        # leg zero. A store that cannot be read leaves the column off instead of
        # filling it with zeroes: the page reads a missing key as zero anyway, and a
        # zero chosen for a day whose legs are unknown is a measured-looking number
        # for an evening that may well have traded.
        legs = stored_legs(run_date)
        if legs is not None:
            book = with_traded(book, traded_by_name(legs))
    if reconciliation is None:
        reconciliation = result.get("reconciliation") or {}
    # The day's cost is the proposal's own establishment cost, which is the cost
    # of building the book from flat. Naming it beside the label keeps the number
    # from reading as a rebalance cost it never was.
    #
    # Only the run's own manifest answers this. A manifest read back from the store
    # is the previous evening's book, so lending its cost to tonight's message
    # printed last night's establishment cost beside a refusal to price anything,
    # and lending its risk figures wrote another evening's numbers onto tonight's
    # row. Both stay empty on a stopped run instead.
    cost_bps: float | None = None
    breakdown: dict[str, float] | None = None
    if own_manifest and manifest:
        from live import reconcile as reconcile_module

        # The same four parts the day's reconciliation row carries, from the same
        # manifest: the message and the store must not be able to disagree about
        # what the evening cost.
        breakdown = reconcile_module.cost_breakdown(manifest)
        cost_bps = breakdown.get("total")
        # The traded book's risk figures and the full book's, from the same
        # manifest the proposal was written from, so the run_status row and the
        # reconciliation row cannot describe different books.
        risk = reconcile_module.risk_figures(manifest)
        row["traded_risk"] = store.json_text(risk["traded"])
        row["full_risk"] = store.json_text(risk["full"])
    snapshot_detail, snapshot_failed = "", False
    written: dict[str, Any] | None = None
    try:
        written = snapshot_module.write_snapshot(
            run={**row, "store": store_name},
            manifest=manifest,
            book=book,
            reconciliation=reconciliation,
            construction=snapshot_module.chosen_row(manifest),
            book_reason=book_reason,
            actual=actual,
            bridge_block=bridge_block,
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
    # The per-name list is the one thing the page carries that is not a number out
    # of the manifest, so it is the one thing that can go missing while the page
    # still looks right: the 2026-10-01 evening published an empty book beside a
    # gross of 100%, a correct hedge and 188 orders. The writer reads its own
    # object back and this says so in the message when the list is not the run's
    # own. It cannot fail the run: the orders are already sent, and an unreadable
    # object is named as unreadable rather than as an empty book.
    page_book = ""
    if written is not None and written.get("written"):
        try:
            verdict, page_book = snapshot_module.check_published_book(
                expected=(manifest or {}).get("n_kept"),
                getter=snapshot_getter,
            )
        except Exception as exc:  # noqa: BLE001 - the check never fails the run
            verdict = snapshot_module.PAGE_BOOK_UNREAD
            page_book = f"could not be read back ({type(exc).__name__})"
        logger.info("page book: %s%s", verdict, f" ({page_book})" if page_book else "")
    notified = notify.notify_run(
        status=status,
        target_close=result.get("target_close"),
        dry_run=dry_run,
        orders=orders,
        gross=gross,
        worst_input=result.get("worst_input"),
        worst_sessions_behind=result.get("worst_sessions_behind"),
        failures=result.get("failures") or [],
        inputs=result.get("inputs") or {},
        detail=detail,
        error_type=error_type,
        catch_up_sessions=catch_up_sessions,
        splits=splits,
        spinoffs=spinoffs,
        spinoff_missing=spinoff_missing,
        spinoff_unusable=spinoff_unusable,
        spinoff_lookup_failed=spinoff_lookup_failed,
        flags=flags,
        store=store_name,
        snapshot=snapshot_detail,
        page_book=page_book,
        cross_checks_capped=cross_checks_capped,
        no_price=no_price,
        no_risk=no_risk,
        thin_adv=thin_adv,
        init=init,
        establishment=establishment,
        cost_label=cost_label,
        brake_limit=brake_limit,
        positions_check=positions_check,
        cost_bps=cost_bps,
        cost_breakdown=breakdown or None,
        poster=poster,
        deferred_reversals=deferred_reversals,
        skipped_minimum=skipped_minimum,
        skipped_borrow=skipped_borrow,
        no_asset=no_asset,
        renames=renames,
        exits=exits,
        sent_notional=sent_notional,
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
    completed = status in COMPLETED_STATUSES and delivered and not snapshot_failed
    try:
        # The same condition the exit code uses: the run finished its work, the
        # message went out and the snapshot is up. Nothing else marks the day done,
        # so a failure retries on the next tick.
        if completed:
            record_run("live_daily", run_date, status, cron_detail.strip(" |"))
        else:
            # Leaving no row is what makes a failure retry. The first Render evening
            # recorded the day from a run that died at the email, and every later
            # attempt exited "already ran" without sending anything: a day nothing
            # was produced on, filed as finished.
            logger.info(
                "%s did not complete (%s), so the day is not marked done and the "
                "next tick will run again",
                run_date,
                status,
            )
    except Exception as exc:  # noqa: BLE001 - the message already went out
        store_failed = True
        logger.error(
            "could not record the cron run: %s",
            notify.scrub(f"{type(exc).__name__}: {exc}"),
        )
    logger.info("run recorded as %s, notification %s", status, notified["status"])
    if not delivered or store_failed or snapshot_failed:
        return 1
    return 0 if status in COMPLETED_STATUSES else 1


def market_closed_run(run_date: str) -> int:
    """The exchange is shut: one message, no seed, no extension, no book.

    Asked before anything else, because the run has nothing to do: there is no
    close to price, so downloading a 600 MB seed and extending nine inputs would
    be work spent to produce nothing. The owner is told rather than left in
    silence, because silence is the alarm for a run that never started.

    The day is recorded like every other evening: a `run_status` row with status
    `market_closed`, keyed by the closed date so it cannot overwrite the previous
    session's own row, a snapshot so the page shows the closed day rather than the
    last book with no explanation, and a `cron_runs` row so a re-fire does not
    send a second message. An evening that sends a message and records nothing is
    an evening with no evidence beyond the message, and the page would have shown
    the closed day as a run that never happened.

    The mode is the run's own resolved mode rather than a hard-coded dry run. A
    closed evening after the flip is a live evening that had nothing to do, and a
    message saying "dry run" about it would misstate the one thing the owner reads
    the message for: whether the book is trading. Nothing is sized or sent either
    way, so the flag changes what the message and the page say, not what the run
    does.
    """
    from live import notify, staleness, store

    dry_run = resolve_dry_run(os.environ.get("EFB_DRY_RUN"))

    reason = f"there is no NYSE session on {run_date}"
    try:
        if already_ran("live_daily", run_date):
            logger.info("market closed for %s and already recorded, exit 0", run_date)
            return 0
    except Exception as exc:  # noqa: BLE001 - nothing to write on a closed day
        logger.warning(
            "could not check the run record: %s",
            notify.scrub(f"{type(exc).__name__}: {exc}"),
        )

    try:
        store_name = store.store_label()
    except Exception:  # noqa: BLE001 - the message matters more than the store
        # Unconfigured or unreachable. The message says so rather than the run
        # dying before it can explain why there is no book.
        store_name = "no store configured"
    logger.info("market closed: %s", reason)
    try:
        return finish_run(
            run_date=run_date,
            result=staleness.closed_result(run_date),
            status="market_closed",
            dry_run=dry_run,
            detail=reason,
            # No book was built, so the day is neither an establishment nor a
            # rebalance: an empty label rather than a claim about a cost.
            cost_label=None,
        )
    except Exception as exc:  # noqa: BLE001 - the message still has to go out
        # The reporting path failed before it could send anything. The owner is
        # told in the plainest way available rather than left with silence, which
        # on a closed evening reads as a broken loop.
        detail = notify.scrub(f"{type(exc).__name__}: {exc}")[:200]
        logger.error(
            "the closed day could not be recorded\n%s",
            notify.scrub_traceback(exc),
        )
        try:
            notified = notify.notify_run(
                status="market_closed",
                target_close=run_date,
                dry_run=dry_run,
                detail=f"{reason}; the day could not be recorded: {detail}",
                store=store_name,
            )
        except Exception as exc:  # noqa: BLE001 - nothing left to try
            logger.error(
                "could not send the closed-day message either\n%s",
                notify.scrub_traceback(exc),
            )
            return 1
        return 0 if notified["status"] == notify.STATUS_SENT else 1


def failed_run(
    exc: BaseException,
    *,
    run_date: str,
    dry_run: bool,
    gate: dict[str, Any] | None = None,
    catch_up_sessions: list[str] | None = None,
    first_run: bool = False,
    actual: dict[str, Any] | None = None,
) -> int:
    """One failed evening, reported with what it actually did.

    The failure path is where the message matters most: the run has already raised,
    and anything it sent before raising is still true. On 2026-10-06 it sent 192
    orders and then died on a missing column, and the message said "Orders: none.
    The run failed before sizing" - the one thing an owner must never be told when it
    is not true. So the orders are read from `efb.orders`, the store's own leg rows,
    rather than from the in-memory summary that is exactly what is in doubt.

    Returns the process exit code, so a caller is one line: `return failed_run(...)`.
    """
    from live import notify, staleness

    detail = notify.scrub(f"{type(exc).__name__}: {exc}")[:200]
    logger.error("live daily failed\n%s", notify.scrub_traceback(exc))
    sent, sent_notional, sized_notional = sent_orders(run_date)
    if sent:
        detail = f"{detail} ({sent} order(s) already sent for this close)"
    return finish_run(
        run_date=run_date,
        result=gate if gate is not None else staleness.error_result(detail),
        status="error",
        dry_run=dry_run,
        detail=detail,
        error_type=type(exc).__name__,
        orders=sent or None,
        gross=sized_notional or None,
        sent_notional=sent_notional or None,
        catch_up_sessions=catch_up_sessions,
        init=first_run,
        actual=actual,
    )


def main() -> int:
    from live import (
        corporate_actions,
        evening_job,
        extend,
        fills,
        morning_job,
        notify,
        positions,
        reconcile,
        staleness,
        store,
    )

    run_date = datetime.now(UTC).date().isoformat()
    # The exchange's own calendar decides first, because a shut market has no
    # close to price: no seed, no extension, no gate, no book. The check is
    # before `already_ran` so a holiday is recognised without needing the store
    # to be reachable, and the closed path does its own idempotency check so a
    # re-fire does not send the owner a second message.
    if not staleness.is_session(run_date):
        return market_closed_run(run_date)

    # The window, before anything else. An evening that fires at another hour is
    # not pricing the close it thinks it is: Alpaca's after-hours session is
    # 16:00-20:00 New York, an order placed inside it is held for the next open and
    # one placed outside it is not. The refusal does no work and records nothing,
    # because it is not a run: the day is still owed its evening, and the in-window
    # cron later that day must find it un-run. The override is explicit, and it is
    # the only way past this.
    stamp = datetime.now(UTC)
    if not staleness.in_cron_window(stamp) and not resolve_force_hour(
        os.environ.get(FORCE_HOUR_ENV)
    ):
        local = stamp.astimezone(staleness.NEW_YORK)
        reason = (
            f"{stamp.isoformat(timespec='seconds')} is "
            f"{local.isoformat(timespec='seconds')} in New York, outside the "
            f"{staleness.WINDOW_START_HOUR_ET:02d}:00-"
            f"{staleness.WINDOW_END_HOUR_ET:02d}:00 window the loop trades in"
        )
        logger.error(
            "refused: %s (set %s=true only for a deliberate out-of-hours " "rehearsal)",
            reason,
            FORCE_HOUR_ENV,
        )
        # The refusal does no work and records nothing, so the message is the
        # only place the owner can learn that the evening did not run at that
        # hour. It is one line, because there is one thing to say.
        notified = notify.notify_refusal(reason)
        logger.info("refusal notified: %s", notified["status"])
        return 1

    if already_ran("live_daily", run_date):
        logger.info("already ran for %s, exit 0 (idempotent)", run_date)
        return 0
    dry_run = resolve_dry_run(os.environ.get("EFB_DRY_RUN"))
    from live import appendix as appendix_mod
    from live import preflight, runroot, seed
    from live import snapshot as snapshot_module

    gate: dict[str, Any] | None = None
    catch_up_sessions: list[str] = []
    splits: list[str] = []
    spinoffs: list[str] = []
    # The spin-offs whose child close could not be read, so the parent's return was
    # nulled instead of corrected. Named in the message: a hole the owner did not
    # ask for is a hole the owner has to be told about.
    spinoff_missing: list[str] = []
    # The spin-offs whose own vendor record could not be used, which nulls the same
    # cell for a different reason. Kept apart from the line above because the two say
    # different things to whoever has to look the action up: a close to refetch, or a
    # record whose rates came back empty.
    spinoff_unusable: list[str] = []
    flags: list[dict[str, Any]] = []
    capped: str = ""
    # The line the message carries when the vendor read behind the spin-off rule
    # did not answer. Empty on an ordinary evening, and never inferred from the
    # absence of spin-offs: a read that failed and a read that found nothing are
    # different evenings and only one of them is unverified.
    spinoff_lookup_failed: str = ""
    # Whether this run seeded the store. False on every path that is not the
    # explicit first run, including a run that fails before the guard decides.
    first_run = False
    # The instant the run began, recorded so the gate can tell an evening of the
    # close from a run that was delayed into the next morning.
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    # Filled on the success path; a stopped or failed run writes the snapshot
    # without them, and it falls back to the last proposal on disk.
    snapshot_inputs: dict[str, Any] = {}
    # The account's own book as of this evening's read, for the page's own
    # section. Filled as soon as the account is read, so a run that fails after
    # the read still publishes the book it actually holds rather than nothing.
    actual: dict[str, Any] | None = None
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
        # The schema, before the seed, the gate, the sizing and any order. A
        # database missing a column this code writes fails at the first write, and
        # the first write happens after the orders have gone out: on 2026-10-06,
        # 192 orders were sent and the day's own record was never written, because
        # `efb.reconciliation.unexplained_adjustment` had been declared in
        # live/supabase_schema.sql and never applied. A missed migration must cost
        # one skipped evening, never a crash after the money has moved. The refusal
        # travels the run's own error path, so the owner is told which column and
        # the page says why the evening did not run.
        preflight.check()
        logger.info("schema: every declared column is present")
        # The page's own settings, read before anything is priced or sent. The
        # writer reads them again when the evening is over, and that is the wrong
        # place to discover a missing credential: by then the book has been sized
        # and the orders have been sent, and the page is where the owner sees the
        # book. A run that trades and cannot publish traded invisibly, so a
        # misconfiguration fails here, in the same error path as any other, before
        # the seed is downloaded and long before a submission.
        snapshot_mode = snapshot_module.check_snapshot_config(dry_run)
        logger.info("snapshot: %s", snapshot_mode)
        # yfinance's SQLite caches are private to this run, before the first fetch
        # can touch the shared one. The default directory is per instance, and two
        # runs contending for its one database lose a symbol to "database is
        # locked" without failing the evening: the night's book is quietly a name
        # short. The price download, the share lookups and the corporate-action
        # cross-check all run in this process and share this one directory.
        from efb import prices as prices_module

        logger.info("yfinance cache: %s", prices_module.use_private_tz_cache())
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
        if outcome.splits or outcome.spinoffs:
            close = outcome.sessions[-1] if outcome.sessions else before_last
            rows: list[dict[str, Any]] = []
            if outcome.splits:
                splits = [
                    corporate_actions.describe([split]) for split in outcome.splits
                ]
                rows.extend(
                    corporate_actions.rows(outcome.splits, close, outcome.ratios)
                )
            if outcome.spinoffs:
                # A spin-off is a corporate action like a split and it is recorded
                # in the same table, with `explained_by` saying which of the two the
                # row is. The parent is the row's ticker because the parent is the
                # name whose return the rule replaced.
                spinoffs = corporate_actions.describe_spinoffs(outcome.spinoffs)
                spinoff_missing = corporate_actions.missing_child_notes(
                    outcome.spinoffs
                )
                spinoff_unusable = corporate_actions.unusable_spinoff_notes(
                    outcome.spinoffs
                )
                rows.extend(corporate_actions.spinoff_rows(outcome.spinoffs, close))
            store.upsert(corporate_actions.TABLE, rows)
            logger.info(
                "corporate actions applied: %s",
                "; ".join([*splits, *spinoffs]),
            )
        if spinoff_missing:
            # Named in the log as well as the message: the cell was nulled rather
            # than left as a print that is not a return, and a hole in the panel
            # tonight is the reason for whatever it shows next.
            logger.warning(
                "spin-off close missing, parent return nulled: %s",
                ", ".join(spinoff_missing),
            )
        if spinoff_unusable:
            # The other reason a spin-off cell is null, logged beside the first so a
            # reader of the run's own output does not have to open the message to
            # find out which of the two it was.
            logger.warning(
                "spin-off record unusable, parent return nulled: %s",
                ", ".join(spinoff_unusable),
            )
        capped = corporate_actions.cap_note(outcome.unchecked)
        if capped:
            logger.warning("%s", capped)
        spinoff_lookup_failed = str(outcome.lookup_failure or "")
        if spinoff_lookup_failed:
            logger.warning("%s", spinoff_lookup_failed)
        flags = outcome.flags
        if flags:
            logger.warning("large moves in the appended session: %s", flags)
        extend.extend_model()
        # A member of tonight's universe with no price is out of tonight's book,
        # which is the right answer and not something to stop over. It is named in
        # the email instead, because a book quietly smaller than the index is a
        # book nobody can check.
        #
        # This is a report, so a failure to build it is reported and the run goes
        # on: whatever is wrong with the artifacts will stop the run at the book
        # itself, where it belongs, rather than here in the note about it.
        try:
            no_price = evening_job.universe_without_prices(run_tree)
        except Exception as exc:  # noqa: BLE001 - a note, not a step
            no_price = []
            logger.warning(
                "could not tell which members had no price: %s: %s",
                type(exc).__name__,
                notify.scrub(str(exc)),
            )
        if no_price:
            logger.warning(
                "%s had no price tonight, so they are out of the book",
                ", ".join(no_price),
            )
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

        # Evening: propose tomorrow's book from the latest close. The book the
        # loop held before tonight is read first, because the proposal's trade
        # impact is the cost of trading to the new book rather than of holding
        # it, and the reason column compares against it: the gate's own target
        # close is tonight's close, so it is the date to ask at.
        #
        # What the account holds and what it is worth are read before anything is
        # sized: the traded leg of every order is the difference between the
        # target and this book, and the NAV the book is sized from is the
        # account's own equity rather than a constant. A live evening whose
        # account cannot be read stops here, with no book and no order. The
        # comparison is against the last book the loop held, which is the row
        # strictly before the close being priced: tonight's own target is written
        # by the proposal step below and has never been traded.
        holdings = positions.check(dry_run=dry_run, before=str(gate["target_close"]))
        held = holdings["held"]
        # The day's kind comes from the account, never from the store: after a
        # dry-run evening the store names a book the account has never held, and a
        # store-based answer would miss the real first trading day and measure
        # every leg against a book that does not exist.
        establishment = bool(holdings["establishment"])
        if not holdings["account_read"]:
            logger.warning(
                "the account could not be read, so this is not an establishment "
                "day and the store's book is what the orders are measured against"
            )
        logger.info("nav: %s", holdings["nav_source"])
        logger.info(
            "positions: %s; held %d name(s) from %s, establishment=%s",
            holdings["note"],
            len(held),
            holdings["source"],
            establishment,
        )
        # What left the account since it was last read, and what explains it. Read
        # here because this is the run that writes the day's reconciliation row and
        # the day's P&L: a name that left with no order and no activity behind it is
        # an adjustment to the account rather than a result of the strategy, and the
        # row has to say so beside the P&L it affected. The morning asks the same
        # question and names the names; neither run can assume the other ran.
        exits = departures_since_last_read(str(gate["target_close"]), holdings)
        if exits["exits"]:
            logger.warning(
                "%d position(s) left the account with no order behind them: %s",
                len(exits["exits"]),
                ", ".join(
                    f"{item['ticker']} {abs(float(item['quantity'])):,.2f} shares "
                    f"(${abs(float(item['notional'])):,.2f})"
                    for item in exits["exits"]
                ),
            )
        # The page's account section, built from this read and from nothing else:
        # the store's position row is the loop's record of what it meant to hold,
        # and publishing that as the account's book would be the one claim the
        # section exists to make checkable. `close` and the fills are left empty on
        # purpose, because this read happens before the orders go out: nothing has
        # settled into the book in hand, and the 15:30 UTC reconciler rewrites the
        # section with what the evening's orders did. A run that could not read the
        # account publishes no block at all rather than the store's book, and the
        # page says the account was not read.
        if holdings["account_read"]:
            actual = fills.actual_holdings(
                held,
                float(holdings["nav"]),
                as_of=datetime.now(UTC).isoformat(timespec="seconds"),
                read_by=fills.READ_EVENING,
                exits=exits,
            )
        previous = previous_book(str(gate["target_close"]), [])
        prior = prior_book(holdings, previous)
        prior_weights = (
            prior.set_index("ticker")["weight"] if prior is not None else None
        )
        logger.info(
            "prior book: %s",
            (
                "none (establishment evening: nothing is held, so the whole target "
                "trades)"
                if prior is None
                else f"{len(prior)} name(s) from the account's own holdings over "
                f"${float(holdings['nav']):,.0f} of equity"
            ),
        )
        manifest = evening_job.build_proposal(
            appendix=appendix_identity,
            previous=prior_weights,
            nav=float(holdings["nav"]),
            nav_source=str(holdings["nav_source"]),
        )
        as_of = str(manifest["as_of"])
        # The build drops a kept name it cannot quantize, and the day must not pass
        # without saying so: one name the vendor did not answer for is not a reason
        # to send no orders, but it is a reason for the book to be one name smaller
        # than the model's, which the owner reads on the same line as the universe's
        # own members with no price tonight.
        merged_dropped = evening_job.merged_no_price(no_price, manifest)
        if merged_dropped != no_price:
            logger.warning(
                "%d kept name(s) had no usable close and are out of the book: %s",
                len(merged_dropped) - len(no_price),
                ", ".join(merged_dropped),
            )
        no_price = merged_dropped
        # The other half of the same statement, from the risk side: the names the
        # model cannot measure never reached the sizing, and the day must say so
        # for the reason the line above gives. The reasons travel with the names
        # into the manifest and the message's own line.
        raw_no_risk = manifest.get("dropped_no_risk")
        no_risk: list[dict[str, Any]] = (
            [dict(entry) for entry in raw_no_risk]
            if isinstance(raw_no_risk, list)
            else []
        )
        if no_risk:
            logger.warning(
                "%d name(s) with no risk estimate are out of the book: %s",
                len(no_risk),
                ", ".join(
                    f"{entry.get('ticker')} ({entry.get('reason')})"
                    for entry in no_risk
                ),
            )
        book = store_proposal(
            as_of, run_tree, dry_run=dry_run, previous=prior, prior_settled=True
        )
        raw_thin = manifest.get("thin_adv")
        thin_adv: list[dict[str, Any]] = (
            [dict(entry) for entry in raw_thin] if isinstance(raw_thin, list) else []
        )
        if thin_adv:
            # A kept name whose own ADV is unknown or below $1M has its cost
            # computed from the panel median, so the day's cost is partly a
            # stand-in. Naming them is the difference between a number the owner
            # can read and a number they have to trust.
            logger.warning(
                "%d kept name(s) have an unknown or thin trailing ADV: %s",
                len(thin_adv),
                ", ".join(
                    f"{row['ticker']} "
                    + (
                        "no ADV"
                        if row.get("adv_usd") is None
                        else f"${float(row['adv_usd']):,.0f}"
                    )
                    for row in thin_adv
                ),
            )

        # Morning: gate, guard, submit (dry run by default), reconcile.
        morning = morning_job.run_morning(
            as_of,
            dry_run=dry_run,
            positions=held,
            quantities=holdings.get("held_quantities"),
            establishment=establishment,
        )
        store_orders(as_of, dry_run)
        # The dollars tonight's legs moved, per name, for the page's trades-by-reason
        # table. This is the one column there that says where the turnover came from,
        # and it comes from the run's own legs rather than from anything re-derived:
        # a name the hedge moved with no order built for it shows as a zero beside
        # the position it changed.
        legs = execution_log(as_of)
        book = with_traded(book, traded_by_name(legs))

        # The bridge's first half, from this run's own read, its own book and its own
        # legs; the morning completes it with the fills and the account it reads.
        bridge_block = evening_bridge(
            as_of,
            dry_run=dry_run,
            holdings=holdings,
            book=book,
            legs=legs,
            reversals=morning.get("deferred_reversals") or [],
        )
        if bridge_block is not None and not bridge_block["holds"]:
            logger.warning(
                "the book bridge does not add up: %s",
                "; ".join(
                    f"{item['name']}: {item['left']} vs {item['right']}"
                    for item in bridge_block["identities"]
                    if not item["holds"]
                ),
            )

        row = reconcile.daily_record(as_of, dry_run=dry_run)
        # The day's P&L is the account's own equity move, and a position that left
        # with no order on it is inside that move without being a result of the
        # book. It is written as its own labelled figure rather than netted out of
        # the P&L: a number quietly adjusted is a number nobody can check, and this
        # one is a fact about the account's paper keeping rather than about the
        # strategy. Zero when nothing left.
        adjustment = float(
            -sum(float(item.get("notional") or 0.0) for item in exits["exits"])
        )
        if not exits["exits"] and exits["previous_read"] == str(as_of)[:10]:
            # A retry. The previous read the store holds is this evening's own,
            # written by the attempt before, so there is nothing left for the
            # comparison to see - and the fact the first attempt recorded is not
            # this attempt's to erase. The row keeps the figure it already has.
            kept = stored_adjustment(as_of)
            if kept is not None:
                adjustment = kept
                logger.info(
                    "%s already carries an adjustment of %.2f, kept: the previous "
                    "broker read is this evening's own, so a retry cannot re-derive it",
                    as_of,
                    kept,
                )
        row = {**row, "unexplained_adjustment": adjustment}
        store_reconciliation(as_of, row, holdings=holdings)
        store_broker_book(as_of, holdings)

        # E12: attribute every stored day that has no attribution row yet, from the
        # store's own positions and this run tree's XS-v1 artifacts. It runs after
        # the reconciliation so the day's cost and forecast are already stored, and
        # it is wrapped in its own handler because it is a report about the book:
        # a report that cannot be produced is a bad page, never a reason to leave a
        # book unheld.
        try:
            attributed = store_attribution(run_tree)
            logger.info(
                "attribution: %d session(s) stored, %d already attributed",
                attributed["n_stored"],
                attributed["n_done"],
            )
        except Exception as exc:  # noqa: BLE001 - a report, not a step
            logger.warning(
                "attribution failed and the run continues: %s: %s",
                type(exc).__name__,
                notify.scrub(str(exc)),
            )

        snapshot_inputs = {
            "manifest": manifest,
            "book": book,
            "reconciliation": row,
            "actual": actual,
            "bridge_block": bridge_block,
        }
    except Exception as exc:  # noqa: BLE001 - recorded, never silent
        # The reason is scrubbed before it goes anywhere: a connection string,
        # a key or the webhook URL must not reach the message or the store. The
        # traceback is logged, because a failure inside the pricing path and a
        # failure inside the reporting path read the same without the frames, but
        # it is formatted and scrubbed first: a traceback carries whatever the
        # failing frame was reading, and its chained causes carry it too.
        return failed_run(
            exc,
            run_date=run_date,
            dry_run=dry_run,
            gate=gate,
            catch_up_sessions=catch_up_sessions,
            first_run=first_run,
            actual=actual,
        )

    # A leg that was halted, left in an unknown state, refused or rejected makes
    # the run incomplete. The day is not done and must not be filed: the status is
    # not ok, no `cron_runs` row is written (`finish_run`), and the next tick
    # retries. The snapshot and the message still go out, so the owner sees which
    # leg and why.
    incomplete = morning.get("incomplete_legs") or []
    if morning.get("complete") is False or incomplete:
        status = "incomplete"
        if incomplete:
            detail = f"{len(incomplete)} leg(s) not confirmed: " + ", ".join(
                f"{leg.get('ticker')} "
                f"({leg.get('reason_code') or leg.get('status') or 'unknown'})"
                for leg in incomplete[:6]
            )
        else:
            detail = "the run reported itself incomplete"
    else:
        status, detail = "ok", ""
    return finish_run(
        run_date=run_date,
        result=gate,
        status=status,
        dry_run=dry_run,
        detail=detail,
        orders=int(morning.get("orders") or 0),
        gross=float(morning.get("intended_notional") or 0.0),
        catch_up_sessions=catch_up_sessions,
        splits=splits,
        spinoffs=spinoffs,
        spinoff_missing=spinoff_missing,
        spinoff_unusable=spinoff_unusable,
        spinoff_lookup_failed=spinoff_lookup_failed,
        flags=flags,
        started_at=started_at,
        cross_checks_capped=capped,
        no_price=no_price,
        no_risk=no_risk,
        thin_adv=thin_adv,
        init=first_run,
        establishment=bool(morning.get("establishment")),
        cost_label=str(morning.get("cost_label") or "rebalance"),
        brake_limit=float(morning.get("brake_limit") or 0.0),
        positions_check=holdings,
        deferred_reversals=morning.get("deferred_reversals") or [],
        # The kept names the $250 minimum left untraded: legs of the day that went
        # nowhere, recorded with their reason and named in the message, because a
        # book quietly short of its own target is a book nobody can check.
        skipped_minimum=morning.get("skipped_legs") or [],
        # The shorts the borrow left unopened. Skipped, not incomplete, and named
        # for the same reason: the run did what it should have and the book is one
        # leg short of its own target, which the message has to say.
        skipped_borrow=morning.get("skipped_borrow") or [],
        # The legs no order could be sent for at all, because the broker's own feed
        # carries no asset for the ticker under any spelling. A name the book holds
        # and the run cannot trade is stated rather than silently dropped from the
        # order list.
        no_asset=morning.get("no_asset") or [],
        # The names the broker spells differently from the loop, so the two names in
        # one company's trade are explained rather than left as a missing position.
        renames=morning.get("renamed") or {},
        # What left the account since it was last read with nothing behind it, named
        # in the message as well as written on the day's row: the row is read later
        # and this is the run that saw it happen.
        exits=exits,
        # The two halves of the evening's notional, so the message cannot call the
        # sized figure `sent` or the sent figure `sized`.
        sent_notional=float(morning.get("sent_notional") or 0.0),
        **snapshot_inputs,
    )


if __name__ == "__main__":
    raise SystemExit(main())
