"""Sprint E11, Part 3: staleness fails the run, counted in trading sessions.

The owner's rule, pre-registered in `handoff/TASK.md`:

- the target close is the most recent completed NYSE session at run time, and
  staleness is counted in sessions behind it, never in calendar days, so a
  Friday close read on Monday is fresh;
- prices, descriptors, factor returns, specific returns, factor covariance,
  specific variance and the universe are gated on their content date, at zero
  sessions behind the target close;
- shares and sectors change slowly, so they are gated on the date of the last
  successful fetch and their content age is reported beside it;
- the check runs before any sizing. On failure no proposal row and no order is
  written, a `run_status` row carries the evidence, and the process exits
  nonzero so Render marks the cron run failed;
- a missing run is stale. `run_state` judges the latest `run_status` row
  against the session that should have closed, so the dashboard cannot present
  an old book as the current one.

Where each date comes from, artifact only, never a clock reading stored:

| input | content date | fetch date |
| --- | --- | --- |
| prices | latest date in raw/prices.parquet | same |
| descriptors | latest `date` in models/XS-v1/descriptors.parquet | same |
| factor_returns | latest `date` in factor_returns.parquet | same |
| specific_returns | latest `date` in specific_returns.parquet | same |
| specific_var | latest `date` in specific_var.parquet | same |
| factor_cov | latest date in processed/returns.parquet | same |
| universe | newest raw/spy_holdings/spy_holdings_<date>.parquet | same |
| shares | latest `date` on a successful fetch | latest `fetched_at` on one |
| sectors | `as_of` in processed/sectors.parquet | newest constituents file |

Two of these need explaining. The factor covariance artifact is a matrix with
no date of its own: the run stamps it with the latest returns session, so that
session is the date its content carries, and a failed returns extension fails
both inputs. The sectors snapshot is a research artifact dated 2026-09-11 that
the loop reads but never rebuilds, so its content date is old by design; the
fetch that feeds it is the daily Wikipedia constituents archive, which is what
the gate measures.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from live import store

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
CALENDAR_NAME = "NYSE"
ALLOWED_SESSIONS_BEHIND = 0
JOB = "live_daily"
TABLE = "run_status"
# long enough to span a holiday week plus the sessions around it
LOOKBACK_DAYS = 21

INPUTS: tuple[str, ...] = (
    "prices",
    "descriptors",
    "factor_returns",
    "specific_returns",
    "factor_cov",
    "specific_var",
    "universe",
    "shares",
    "sectors",
)

# The two inputs gated on the fetch rather than the content date, because
# their content changes slowly and rebuilding it is not what the loop does.
GATED_ON_FETCH: tuple[str, ...] = ("shares", "sectors")
GATED_BY: dict[str, str] = {
    name: ("fetch" if name in GATED_ON_FETCH else "content") for name in INPUTS
}

SOURCES: dict[str, str] = {
    "prices": "raw/prices.parquet",
    "descriptors": "models/XS-v1/descriptors.parquet",
    "factor_returns": "models/XS-v1/factor_returns.parquet",
    "specific_returns": "models/XS-v1/specific_returns.parquet",
    "factor_cov": "processed/returns.parquet (the session the matrix was rolled to)",
    "specific_var": "models/XS-v1/specific_var.parquet",
    "universe": "raw/spy_holdings/",
    "shares": "raw/shares_history.parquet",
    "sectors": "raw/wikipedia_constituents/ (fetch) and processed/sectors.parquet",
}


@lru_cache(maxsize=1)
def calendar():
    """The NYSE session calendar.

    Imported inside the function so the module loads even where the live
    extras are not installed; the gate itself needs them.
    """
    import pandas_market_calendars as mcal  # type: ignore[import-untyped]  # noqa: PLC0415 - live extra

    return mcal.get_calendar(CALENDAR_NAME)


def sessions(start: pd.Timestamp | str, end: pd.Timestamp | str) -> list[pd.Timestamp]:
    """The NYSE sessions in [start, end], both ends inclusive, naive dates."""
    days = calendar().valid_days(
        start_date=pd.Timestamp(start).date(), end_date=pd.Timestamp(end).date()
    )
    return [pd.Timestamp(day).tz_localize(None).normalize() for day in days]


# The cron's own slot, from render.yaml's schedule ("30 22 * * 1-5"), and the
# grace before a missing snapshot counts as a failure on the page. One source: the
# gate's late window, the snapshot's expectation and the browser's countdown all
# read these.
RUN_SLOT_UTC = (22, 30)
GRACE_HOURS = 3


def session_close(session: Any) -> pd.Timestamp:
    """The UTC instant a session closed, from the calendar's own schedule.

    The 16:00 New York close is 20:00 or 21:00 UTC depending on the date, so the
    calendar answers rather than an assumed offset.
    """
    stamp = _naive(session)
    if stamp is None:  # pragma: no cover - a caller without a session
        raise ValueError("no session to find the close of")
    schedule = calendar().schedule(
        start_date=stamp.date(), end_date=stamp.date(), tz="UTC"
    )
    if schedule.empty:  # pragma: no cover - a session the calendar just listed
        raise ValueError(f"{stamp.date()} is not an NYSE session")
    return pd.Timestamp(schedule["market_close"].iloc[0])


def expected_next_by(
    target_close: Any,
    *,
    grace_hours: int = GRACE_HOURS,
    run_slot: tuple[int, int] = RUN_SLOT_UTC,
) -> str:
    """The UTC instant by which the next run's snapshot should exist.

    The next NYSE session after `target_close`, at the cron's own slot, plus the
    grace. A Friday close points at Monday and a holiday is skipped, because the
    calendar answers rather than an assumed weekday.
    """
    stamp = _naive(target_close)
    if stamp is None:
        raise ValueError("no close to count from")
    upcoming = sessions(stamp + pd.Timedelta(days=1), stamp + pd.Timedelta(days=500))
    if not upcoming:  # pragma: no cover - the calendar always has a next session
        raise ValueError(f"no NYSE session in the year after {stamp.date()}")
    hour, minute = run_slot
    due = (
        pd.Timestamp(upcoming[0])
        + pd.Timedelta(hours=hour, minutes=minute)
        + pd.Timedelta(hours=grace_hours)
    )
    return due.tz_localize("UTC").isoformat().replace("+00:00", "Z")


def gate_window_end(
    target_close: Any,
    *,
    grace_hours: int = GRACE_HOURS,
    run_slot: tuple[int, int] = RUN_SLOT_UTC,
) -> pd.Timestamp:
    """The end of the close's own evening, UTC.

    The cron's slot on the close's own date plus the grace, which is stricter than
    `expected_next_by`: that one is when the *next* session's snapshot is due, and
    it is a different question. A run delayed into the next morning appends exactly
    one session, and it is still not an evening of this close, so the gate window
    ends with this close's own evening rather than with the next run's deadline.
    """
    stamp = _naive(target_close)
    if stamp is None:
        raise ValueError("no close to count the evening of")
    hour, minute = run_slot
    end = (
        stamp
        + pd.Timedelta(hours=hour, minutes=minute)
        + pd.Timedelta(hours=grace_hours)
    )
    return end.tz_localize("UTC")


def gate_close(row: dict[str, Any] | None, now: Any = None) -> dict[str, Any]:
    """Whether a stored run counts as one of the gate's two closes.

    The owner's rule, in full: a gate close is a run that **appended exactly one
    session, its target close, and started on that session's own evening**, after
    the close and before the next run was due. The first half alone is not enough,
    which is the condition this adds: a run delayed to the next morning appends
    exactly one session and is still not an evening of that close.

    Returns the verdict with the reason, so the report can quote it rather than
    assert it.
    """
    if not row:
        return {"counts": False, "reason": "no run is recorded"}
    recorded = _iso(row.get("target_close"))
    if not recorded:
        return {"counts": False, "reason": "the run records no target close"}
    sessions_appended = _row_sessions(row)
    if len(sessions_appended) > 1:
        return {
            "counts": False,
            "reason": (
                f"the run appended {len(sessions_appended)} sessions "
                f"({', '.join(sessions_appended)}), so it is a catch-up"
            ),
        }
    if bool(row.get("catch_up")):
        return {"counts": False, "reason": "the run is recorded as a catch-up"}
    started = row.get("started_at")
    if not started:
        return {
            "counts": False,
            "reason": (
                "the run records no start time, so its own evening cannot be shown"
            ),
        }
    began = pd.Timestamp(started)
    if began.tzinfo is None:
        began = began.tz_localize("UTC")
    else:
        began = began.tz_convert("UTC")
    opened = session_close(recorded)
    deadline = gate_window_end(recorded)
    if began < opened:
        return {
            "counts": False,
            "reason": (
                f"the run started at {began.isoformat()} before the {recorded} close "
                f"at {opened.isoformat()}"
            ),
        }
    if began > deadline:
        return {
            "counts": False,
            "reason": (
                f"the run started at {began.isoformat()}, after the "
                f"{deadline.isoformat()} end of the {recorded} evening, so the "
                f"fetch was not made on that session's own evening"
            ),
        }
    status = str(row.get("status") or "")
    if status != "ok":
        return {
            "counts": False,
            "reason": f"the {recorded} run records status {status!r}, not ok",
        }
    return {
        "counts": True,
        "reason": (
            f"the {recorded} session, started at {began.isoformat()} after its "
            f"{opened.isoformat()} close and before {deadline.isoformat()}"
        ),
    }


def _row_sessions(row: dict[str, Any]) -> list[str]:
    """The sessions a stored row recorded as appended."""
    raw = row.get("catch_up_sessions")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:  # pragma: no cover - a corrupted row
            return []
        raw = parsed
    if not raw:
        return []
    return [str(item) for item in raw]


def _naive(stamp: Any) -> pd.Timestamp | None:
    """A naive, normalized date, whatever tz-aware or NaT input arrives."""
    if stamp is None:
        return None
    value = pd.Timestamp(stamp)
    if pd.isna(value):
        return None
    if value.tzinfo is not None:
        value = value.tz_convert("UTC").tz_localize(None)
    return value.normalize()


def target_close(now: datetime | pd.Timestamp | None = None) -> pd.Timestamp:
    """The most recent session whose close has already happened.

    The cron runs at 22:30 UTC, after the 20:00 UTC close, so on a session day
    the target is that day; run before the open and the target is the previous
    session.
    """
    stamp = pd.Timestamp(now if now is not None else datetime.now(UTC))
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    start = (stamp - pd.Timedelta(days=LOOKBACK_DAYS)).date()
    schedule = calendar().schedule(start_date=start, end_date=stamp.date(), tz="UTC")
    completed = schedule.loc[schedule["market_close"] <= stamp]
    if completed.empty:  # pragma: no cover - needs a 21 day calendar outage
        raise RuntimeError(
            f"no completed NYSE session in the {LOOKBACK_DAYS} days to {stamp}"
        )
    return _naive(completed.index[-1])  # type: ignore[return-value]


def sessions_behind(content: Any, target: Any) -> int | None:
    """The sessions after `content` and up to and including `target`.

    None when the input carries no date at all: an undated input cannot be
    fresh, and its distance from the target is not a number.
    """
    stamp = _naive(content)
    if stamp is None:
        return None
    end = _naive(target)
    if end is None:  # pragma: no cover - the caller always passes a target
        return None
    if stamp >= end:
        return 0
    return len(sessions(stamp + pd.Timedelta(days=1), end))


def _latest_values(frame: pd.DataFrame, column: str) -> pd.Timestamp | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_datetime(frame[column], errors="coerce").dropna()
    return _naive(values.max())


def _latest_index_date(frame: pd.DataFrame, level: str) -> pd.Timestamp | None:
    if frame.empty or level not in frame.index.names:
        return None
    values = pd.DatetimeIndex(frame.index.get_level_values(level))
    return _naive(values.max())


def _artifact_date(root: Path, relative: str, column: str) -> pd.Timestamp | None:
    path = root / relative
    if not path.exists():
        return None
    return _latest_values(pd.read_parquet(path), column)


def _index_date(root: Path, relative: str, level: str) -> pd.Timestamp | None:
    path = root / relative
    if not path.exists():
        return None
    return _latest_index_date(pd.read_parquet(path), level)


def _newest_archived_date(
    root: Path, relative: str, pattern: str
) -> pd.Timestamp | None:
    """The date in the newest archive file name, `prefix_<date>.parquet`."""
    files = sorted((root / relative).glob(pattern))
    if not files:
        return None
    return _naive(files[-1].stem.rsplit("_", 1)[-1])


def _shares_dates(root: Path) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """The content date and the fetch date of the share counts.

    Only successful fetches count: the 58 rows whose fetch came back empty
    carry no date and must not date the input.
    """
    path = root / "raw" / "shares_history.parquet"
    if not path.exists():
        return None, None
    frame = pd.read_parquet(path)
    if "status" in frame.columns:
        frame = frame.loc[frame["status"] == "ok"]
    return _latest_values(frame, "date"), _latest_values(frame, "fetched_at")


def input_dates(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Every input's content date and fetch date, read from the artifacts."""
    base = Path(root) if root is not None else DATA_ROOT
    price_date = _index_date(base, "raw/prices.parquet", "date")
    returns_date = _index_date(base, "processed/returns.parquet", "date")
    shares_content, shares_fetch = _shares_dates(base)
    dates: dict[str, tuple[Any, Any]] = {
        "prices": (price_date, price_date),
        "descriptors": (
            _artifact_date(base, "models/XS-v1/descriptors.parquet", "date"),
        )
        * 2,
        "factor_returns": (
            _artifact_date(base, "models/XS-v1/factor_returns.parquet", "date"),
        )
        * 2,
        "specific_returns": (
            _artifact_date(base, "models/XS-v1/specific_returns.parquet", "date"),
        )
        * 2,
        "factor_cov": (returns_date, returns_date),
        "specific_var": (
            _artifact_date(base, "models/XS-v1/specific_var.parquet", "date"),
        )
        * 2,
        "universe": (
            _newest_archived_date(base, "raw/spy_holdings", "spy_holdings_*.parquet"),
        )
        * 2,
        "shares": (shares_content, shares_fetch),
        "sectors": (
            _artifact_date(base, "processed/sectors.parquet", "as_of"),
            _newest_archived_date(
                base,
                "raw/wikipedia_constituents",
                "wikipedia_constituents_*.parquet",
            ),
        ),
    }
    return {
        name: {
            "content": dates[name][0],
            "fetch": dates[name][1],
            "source": SOURCES[name],
        }
        for name in INPUTS
    }


def _iso(stamp: Any) -> str | None:
    value = _naive(stamp)
    return None if value is None else value.date().isoformat()


def _worst(failures: list[dict[str, Any]]) -> tuple[str | None, int | None]:
    """The failing input furthest behind; an undated input outranks any count."""
    if not failures:
        return None, None
    ranked = sorted(
        failures,
        key=lambda item: (
            item["sessions_behind"] is None,
            item["sessions_behind"] or 0,
        ),
        reverse=True,
    )
    return str(ranked[0]["input"]), ranked[0]["sessions_behind"]


def describe_failures(failures: list[dict[str, Any]]) -> str:
    """One line naming every failing input and how far behind it is."""
    parts = []
    for failure in failures:
        behind = failure["sessions_behind"]
        if behind is None:
            parts.append(f"{failure['input']} has no date at all")
        elif behind == 1:
            parts.append(f"{failure['input']} is 1 session behind")
        else:
            parts.append(f"{failure['input']} is {behind} sessions behind")
    return "; ".join(parts) if parts else "no input failed"


def check(
    root: Path | None = None,
    now: datetime | pd.Timestamp | None = None,
    target: Any = None,
) -> dict[str, Any]:
    """The gate: every input's dates, sessions behind, and whether it stops.

    Called before any sizing. `status` is `ok` or `stale_stopped`.
    """
    stamp = _naive(target) if target is not None else target_close(now)
    if stamp is None:  # pragma: no cover - the calendar always answers
        raise RuntimeError("no target close")
    dates = input_dates(root)
    inputs: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    for name in INPUTS:
        info = dates[name]
        content_behind = sessions_behind(info["content"], stamp)
        fetch_behind = sessions_behind(info["fetch"], stamp)
        behind = fetch_behind if GATED_BY[name] == "fetch" else content_behind
        entry = {
            "gated_by": GATED_BY[name],
            "source": info["source"],
            "content": _iso(info["content"]),
            "content_sessions_behind": content_behind,
            "fetch": _iso(info["fetch"]),
            "fetch_sessions_behind": fetch_behind,
            "sessions_behind": behind,
        }
        inputs[name] = entry
        if behind is None or behind > ALLOWED_SESSIONS_BEHIND:
            failures.append({"input": name, **entry})
    calendar_days = [
        (stamp - _naive(inputs[name]["content"])).days
        for name in INPUTS
        if inputs[name]["content"] is not None
    ]
    worst_input, worst_behind = _worst(failures)
    return {
        "job": JOB,
        "checked_at": pd.Timestamp(
            now if now is not None else datetime.now(UTC)
        ).isoformat(),
        "target_close": stamp.date().isoformat(),
        "allowed_sessions_behind": ALLOWED_SESSIONS_BEHIND,
        "inputs": inputs,
        "failures": failures,
        "worst_input": worst_input,
        "worst_sessions_behind": worst_behind,
        "max_input_staleness_days": max(calendar_days) if calendar_days else None,
        "status": "ok" if not failures else "stale_stopped",
    }


def error_result(
    detail: str,
    now: datetime | pd.Timestamp | None = None,
    target: Any = None,
) -> dict[str, Any]:
    """A check-shaped result for a run that failed before the gate ran."""
    stamp = _naive(target) if target is not None else target_close(now)
    return {
        "job": JOB,
        "checked_at": pd.Timestamp(
            now if now is not None else datetime.now(UTC)
        ).isoformat(),
        "target_close": stamp.date().isoformat() if stamp is not None else None,
        "allowed_sessions_behind": ALLOWED_SESSIONS_BEHIND,
        "inputs": {},
        "failures": [],
        "worst_input": None,
        "worst_sessions_behind": None,
        "max_input_staleness_days": None,
        "status": "error",
        "detail": detail[:200],
    }


def run_status_row(
    result: dict[str, Any],
    *,
    run_date: str,
    status: str | None = None,
    dry_run: bool = True,
    detail: str = "",
    notify_status: str = "pending",
    notify_failed: bool = False,
    n_orders: int | None = None,
    gross_notional: float | None = None,
    catch_up: bool = False,
    catch_up_sessions: list[str] | None = None,
    splits: list[str] | None = None,
    flags: list[dict[str, Any]] | None = None,
    snapshot: str | None = None,
    started_at: str | None = None,
    cross_checks_capped: str | None = None,
    init: bool = False,
) -> dict[str, Any]:
    """The `run_status` row for one run: the target close and every date.

    The key columns come first so the local parquet fallback, which dedupes on
    the frame's first column, removes the row for the same target close rather
    than the same job.
    """
    return {
        "target_close": result.get("target_close"),
        "job": str(result.get("job") or JOB),
        "run_date": run_date,
        "status": status or str(result.get("status") or "unknown"),
        "checked_at": result.get("checked_at"),
        "max_input_staleness_days": result.get("max_input_staleness_days"),
        "worst_input": result.get("worst_input"),
        "worst_sessions_behind": result.get("worst_sessions_behind"),
        "n_inputs": len(result.get("inputs") or {}),
        "inputs": store.json_text(result.get("inputs") or {}, sort_keys=True),
        "failures": store.json_text(result.get("failures") or [], sort_keys=True),
        "detail": detail or str(result.get("detail") or ""),
        "notify_status": notify_status,
        "notify_failed": notify_failed,
        "n_orders": n_orders,
        "gross_notional": gross_notional,
        "dry_run": dry_run,
        # Whether this run seeded the store. It is a first and last thing: the
        # flag is removed afterwards and a store is seeded once, so the row is
        # the record of the evening the appendix was taken from git.
        "init": bool(init),
        # A catch-up run appended several sessions at once, which the first
        # deploy will do and which no gate close may be: a gate close is a run
        # whose target close is the only session it appended.
        "catch_up": bool(catch_up),
        "catch_up_sessions": store.json_text(catch_up_sessions or []),
        # The corporate actions this run applied and the large moves it could
        # not explain: the dashboard shows them beside the run it delivered.
        "splits": store.json_text(splits or []),
        "flags": store.json_text(flags or [], sort_keys=True),
        # What the Cloudflare page has: "snapshot: on (latest.json, ...)" or
        # "snapshot: off (dry run)". The dashboard shows it beside the run.
        "snapshot": snapshot,
        # The instant the run began, so its own evening can be shown rather than
        # assumed: a run delayed to the next morning still appends one session.
        "started_at": started_at,
        # Whether the corporate-actions cross-check hit its request cap, and how
        # many names went unchecked because of it. Never an error; never silent.
        "cross_checks_capped": cross_checks_capped,
    }


def write_run_status(result: dict[str, Any], **kwargs: Any) -> None:
    """Store one run's status. Keyed by target close and job, so it upserts."""
    store.upsert(TABLE, [run_status_row(result, **kwargs)])


def latest_row(frame: pd.DataFrame) -> dict[str, Any] | None:
    """The newest status row in a frame already in hand, else None."""
    if frame.empty:
        return None
    ordered = frame.sort_values(["target_close", "run_date"])
    return {str(key): value for key, value in ordered.iloc[-1].to_dict().items()}


def latest_run_status() -> dict[str, Any] | None:
    """The most recent stored run status, or None when nothing is stored."""
    return latest_row(store.select(TABLE))


def _row_failures(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("failures")
    if not raw or not isinstance(raw, str):
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:  # pragma: no cover - only a corrupted row
        return []
    return [item for item in parsed if isinstance(item, dict)]


LABELS: dict[str, str] = {
    "clean": "clean",
    "no_run": "no run recorded at all",
    "no_run_for_session": "no run for the most recent close",
    "stale_stopped": "STALE STOP: the run refused to price a book",
    "error": "the run errored",
    "notify_failed": "the notification failed",
    "notify_not_configured": "no notification channel is configured",
}


def run_state(
    row: dict[str, Any] | None = None,
    now: datetime | pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Whether the latest recorded run is a clean run for the open session.

    Anything else is a state the owner must see: the job stopped on staleness,
    it errored, it recorded a failed notification, it ran for an older close,
    or it never ran. A page that keeps showing an old book as the current one
    is the failure this guards.
    """
    state = _evaluate(row, now)
    state["label"] = LABELS.get(str(state["state"]), str(state["state"]))
    return state


def _evaluate(
    row: dict[str, Any] | None = None,
    now: datetime | pd.Timestamp | None = None,
) -> dict[str, Any]:
    if row is None:
        row = latest_run_status()
    expected = target_close(now).date().isoformat()
    if row is None:
        return {
            "state": "no_run",
            "clean": False,
            "target_close": expected,
            "recorded_target_close": None,
            "message": (
                f"No run is recorded at all. No evening run has stored a status "
                f"for the {expected} close, so nothing below is current."
            ),
        }
    recorded = _iso(row.get("target_close"))
    if recorded != expected:
        return {
            "state": "no_run_for_session",
            "clean": False,
            "target_close": expected,
            "recorded_target_close": recorded,
            "message": (
                f"The latest recorded run is for the {recorded or 'unknown'} close and "
                f"the most recent completed session is {expected}. No run has stored a "
                f"status for {expected}, so nothing below is current."
            ),
        }
    status = str(row.get("status") or "unknown")
    notify_status = str(row.get("notify_status") or "")
    notify_failed = bool(row.get("notify_failed"))
    if status != "ok" or notify_failed:
        reason = str(row.get("detail") or "").strip()
        failures = describe_failures(_row_failures(row))
        if status == "stale_stopped":
            message = (
                f"The run for the {expected} close refused to price a book: "
                f"{failures}. No book exists for {expected}, so anything shown "
                f"below it is older and not current."
            )
        elif status == "error":
            message = (
                f"The run for the {expected} close failed: "
                f"{reason or 'no reason recorded'}."
            )
        elif notify_status == "skipped":
            message = (
                f"The run for the {expected} close completed, but no notification "
                f"channel is set, so the owner was not told. Set "
                f"EFB_RESEND_API_KEY and EFB_NOTIFY_EMAIL_TO on the cron service."
            )
        elif notify_failed:
            message = (
                f"The run for the {expected} close completed, but its "
                f"notification could not be sent, so the owner was not told."
            )
        else:
            message = f"The run for the {expected} close recorded status {status}."
        if status != "ok":
            state = status
        elif notify_status == "skipped":
            state = "notify_not_configured"
        else:
            state = "notify_failed"
        return {
            "state": state,
            "clean": False,
            "target_close": expected,
            "recorded_target_close": recorded,
            "message": message,
        }
    return {
        "state": "clean",
        "clean": True,
        "target_close": expected,
        "recorded_target_close": recorded,
        "message": f"The run for the {expected} close completed cleanly.",
    }
