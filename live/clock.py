"""Sprint E11: the continuous live clock.

The loop runs indefinitely. Day 1 is recorded, and the thirty trading
days from day 1 are a reporting window over the history, not the life
of the run. A start can be voided (discarded, never counted) and the
clock restarted from a new day 1, but every start, voided or live,
stays on the record.

Day 1 is not a date somebody types. It is the first session whose orders filled
after the flip, and registration refuses unless the date it is given matches the
records: the first live run and the first stored proposal, and, once the store
keeps fills, the first filled session as well. The refusal exists because the
alternative is a window that starts on an evening the loop was still a rehearsal,
which is how a thirty-day result gets measured over days nobody traded.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLOCK_PATH = ROOT / "live" / "clock.json"
TRADING_DAYS = 30
RUN_CONDITION = "open_ended"
RUN_CONDITION_REASON = (
    "the book runs indefinitely; the thirty trading days from day 1 are a "
    "reporting window over the history, not the life of the run"
)
LIVE_JOB = "live_daily"


class RegistrationRefused(RuntimeError):
    """The records do not support the day-1 date the caller asked to register."""


def run_condition() -> dict:
    """The loop's run condition: open-ended, the window a reporting slice."""
    return {
        "run_condition": RUN_CONDITION,
        "reason": RUN_CONDITION_REASON,
        "reporting_window_days": TRADING_DAYS,
    }


def _end_date(day_1: str, trading_days: int) -> str:
    """The last business day of the window, day 1 included."""
    days = pd.bdate_range(day_1, periods=trading_days)
    return str(pd.Timestamp(days[-1]).date())


def _now() -> str:
    return datetime.now(UTC).isoformat()


def load_clock(path: Path = CLOCK_PATH) -> dict:
    """The recorded clock, or a clear error before it has started."""
    if not path.exists():
        raise FileNotFoundError(f"no clock at {path}")
    return json.loads(path.read_text())


def void_start(
    day_1: str,
    reason: str,
    path: Path = CLOCK_PATH,
) -> dict:
    """Void a start: the window is discarded and never counts.

    The voided start and its reason stay on the record, so the file shows
    a restart rather than a silent edit. The clock is left not started.
    """
    existing = load_clock(path) if path.exists() else {}
    history = list(existing.get("history", []))
    if existing.get("started"):
        history.append(
            {
                "day_1": existing.get("day_1"),
                "end_date": existing.get("end_date"),
                "status": "void",
                "reason": reason,
                "voided_at": _now(),
            }
        )
    elif not any(
        entry.get("day_1") == day_1 and entry.get("status") == "void"
        for entry in history
    ):
        history.append(
            {
                "day_1": day_1,
                "end_date": _end_date(
                    day_1, existing.get("trading_days", TRADING_DAYS)
                ),
                "status": "void",
                "reason": reason,
                "voided_at": _now(),
            }
        )
    payload = {
        "started": False,
        "day_1": None,
        "end_date": None,
        "run_condition": RUN_CONDITION,
        "reporting_window_days": existing.get("trading_days", TRADING_DAYS),
        "trading_days": existing.get("trading_days", TRADING_DAYS),
        "history": history,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def start_clock(
    day_1: str,
    trading_days: int = TRADING_DAYS,
    path: Path = CLOCK_PATH,
    *,
    records: dict[str, list[str]],
) -> dict:
    """Start the clock on day 1, which the records have to support.

    `records` is required rather than defaulted. Registration is the one act that
    starts a reporting window, and a caller that cannot say what the records hold
    cannot register; an empty default would make the check skippable by omission,
    which is how a clock gets started on an evening nothing traded.
    """
    check_registration(day_1, records)
    existing = load_clock(path) if path.exists() else {}
    payload = {
        "started": True,
        "day_1": day_1,
        "end_date": _end_date(day_1, trading_days),
        "reporting_window_days": trading_days,
        "run_condition": RUN_CONDITION,
        "trading_days": trading_days,
        "history": existing.get("history", []),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def _dates(frame: Any, column: str, *, where: Any = None) -> list[str]:
    """The distinct dates in one column, sorted, as ISO day strings.

    A missing column is an empty set rather than an error: an unseeded store
    returns an empty frame with no columns at all, and "no proposal has been
    stored" is the answer, not a crash.
    """
    if frame is None or getattr(frame, "empty", True) or column not in frame.columns:
        return []
    selected = frame if where is None else frame.loc[where]
    if selected.empty or column not in selected.columns:
        return []
    values = pd.to_datetime(selected[column], errors="coerce").dropna()
    return sorted({str(value.date()) for value in values})


def records_from_store() -> dict[str, list[str]]:
    """The record sets a day-1 date has to agree with, read from the store.

    `run` is a live run: a `run_status` row for the live series that was not a dry
    run and that sent at least one order. A dry-run evening, a gate stop and a
    refusal are all recorded and none of them is a live run, so the first date
    here is the flip evening.

    `proposal` is every close the loop stored a proposal for **on the live series**,
    which the same evening writes: the proposal is priced from that close. It is
    scoped by `run_status` rather than read whole, because the loop also stores a
    proposal on a rehearsal and on a dry run, and a rehearsal priced from a close
    before the flip is not a live close. Unscoped, the set started on 2026-09-25, a
    dry-run rehearsal, and no day-1 date could ever agree with it.

    `filled` is the sessions whose legs the store records a fill for, read from
    `efb.fills`, which is what the morning writes when it reconciles a close.
    Alpaca accepts an order sent after the close and fills it at the next open,
    and the evening does not wait for that fill, so `efb.orders.filled_notional`
    is 0 in every row it holds: reading that column made this set permanently
    empty and the third test of `check_registration` vacuous rather than passing
    or failing on anything.
    """
    from live import staleness, store

    runs = store.select(staleness.TABLE)
    live_runs = []
    live_closes: list[str] = []
    if not runs.empty and {"job", "dry_run", "n_orders", "target_close"} <= set(
        runs.columns
    ):
        live_runs = _dates(
            runs,
            "target_close",
            where=(runs["job"] == LIVE_JOB)
            & (~runs["dry_run"])
            & (runs["n_orders"].fillna(0) > 0),
        )
        # Every close the live series ran on, including the ones it sent no order
        # for: a hold day is a live close with a proposal and nothing to trade.
        live_closes = _dates(
            runs,
            "target_close",
            where=(runs["job"] == LIVE_JOB) & (~runs["dry_run"]),
        )

    fills = store.select("fills")
    filled = []
    if not fills.empty and {"trade_date", "status"} <= set(fills.columns):
        # A fill row is a leg that came back from the broker with something on it;
        # a row the morning wrote for a leg that did not fill carries 0 and its own
        # status, so the set is the sessions with a filled leg rather than the
        # sessions with a leg.
        filled = _dates(
            fills,
            "trade_date",
            where=fills["status"].astype(str) == "FILLED",
        )

    # The closes the loop actually put orders out for. `filled` is read from the
    # fills and `ordered` from the legs, and the two are compared by
    # `check_registration`: a close with an order and no fill is a close whose
    # "orders filled" claim is not established.
    orders = store.select("orders")
    ordered = []
    if not orders.empty and "trade_date" in orders.columns:
        # A broker id that is present and non-empty. `notna()` counted the empty
        # string too, and a dry run writes exactly that: measured on 2026-10-29, the
        # 2026-09-29 close's 177 legs are all `DRY_RUN` with `broker_order_id = ''`
        # and `notna()` read them as 177 orders sent.
        sent = (
            orders["broker_order_id"].astype("string").fillna("").str.strip() != ""
            if "broker_order_id" in orders.columns
            else pd.Series(False, index=orders.index)
        )
        ordered = _dates(orders, "trade_date", where=sent)

    proposed = _dates(store.select("proposals"), "trade_date")
    if live_closes:
        # Scoped, but only when there is a scope to apply: a store whose
        # `run_status` is empty is one the scope cannot speak about, and reading it
        # as "no live close was ever proposed" would refuse for the wrong reason.
        proposed = [date for date in proposed if date in set(live_closes)]

    return {
        "run": live_runs,
        "proposal": proposed,
        "filled": filled,
        "ordered": ordered,
    }


def check_registration(day_1: str, records: dict[str, list[str]]) -> None:
    """Refuse unless `day_1` is the first live run and the first proposal.

    Both records have to exist and both have to start on `day_1`: an evening that
    ran but stored no proposal is not the first trading day, and a proposal with
    no run behind it is an artifact nobody can place. A third set is checked when
    it is not empty, the sessions whose orders filled, which is the definition of
    day 1 rather than a proxy for it.
    """
    for key, what in (
        ("run", "live run"),
        ("proposal", "stored proposal"),
    ):
        dates = [str(date) for date in records.get(key) or []]
        if not dates:
            raise RegistrationRefused(
                f"no {what} is recorded yet, so there is no day 1 to register: "
                "day 1 is the first session whose orders filled after the flip"
            )
        if dates[0] != day_1:
            raise RegistrationRefused(
                f"day 1 {day_1} is not the first {what}: the records start at "
                f"{dates[0]}, and day 1 is the first session whose orders filled "
                "after the flip"
            )
    filled = [str(date) for date in records.get("filled") or []]
    if filled and filled[0] != day_1:
        raise RegistrationRefused(
            f"day 1 {day_1} is not the first session whose orders filled: the "
            f"store records a fill on {filled[0]}"
        )
    # A close the loop sent legs on and the store holds no fill for is a close whose
    # day-1 claim is unproven, and registering it would date the reporting window
    # from a session nothing is known to have filled on.
    ordered = [str(date) for date in records.get("ordered") or []]
    if day_1 in ordered and day_1 not in filled:
        raise RegistrationRefused(
            f"day 1 {day_1} is a close the loop sent orders for and the store holds "
            "no fill for it: day 1 is the first session whose orders filled, so the "
            "fills have to be recorded before the clock can start on it"
        )


def first_day(records: dict[str, list[str]]) -> str:
    """The day-1 date the records support, or a refusal naming what is missing."""
    runs = [str(date) for date in records.get("run") or []]
    if not runs:
        raise RegistrationRefused(
            "no live run is recorded yet, so there is no day 1 to register: day 1 "
            "is the first session whose orders filled after the flip"
        )
    day_1 = runs[0]
    check_registration(day_1, records)
    return day_1


def register(
    path: Path = CLOCK_PATH, records: dict[str, list[str]] | None = None
) -> dict:
    """Start the clock on the first live session, refusing on any disagreement."""
    resolved = records_from_store() if records is None else records
    return start_clock(first_day(resolved), path=path, records=resolved)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--register",
        action="store_true",
        help="start the clock on the first live session the records support",
    )
    args = parser.parse_args()
    if args.register:
        print(json.dumps(register(), indent=2, sort_keys=True))
    else:
        print(json.dumps(load_clock(), indent=2, sort_keys=True))
