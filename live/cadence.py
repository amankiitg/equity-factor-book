"""Sprint EFB-CADENCE: the rebalance calendar, as a flag.

The live loop rebalances every close, which is what `EFB_CADENCE=1` (the default)
still does. `EFB_CADENCE=k` with `k > 1` makes the loop hold the book between
rebalances and trade only on the sessions the calendar names, plus the forced
reasons a hold day cannot avoid.

    EFB_CADENCE=21
    EFB_CADENCE_ANCHOR=2026-10-01

A close is a **rebalance day** when the number of sessions from the anchor is a
multiple of `k`; every other close is a **hold day**. The anchor is session 0 and
is therefore itself a rebalance day.

A **missed rebalance** makes the next successful evening a rebalance. The
completion record is the one the morning already writes - this job's own
`efb.run_status` row for the close - so nothing new is stored: a scheduled
rebalance day with no completed row is a gap, and the next evening reads it.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Sequence
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

CADENCE_ENV = "EFB_CADENCE"
ANCHOR_ENV = "EFB_CADENCE_ANCHOR"
CADENCE_DAILY = 1
# A run that produced a book, whether or not every leg filled. Anything else -
# stale_stopped, error, or no row at all - is a night the calendar did not get.
COMPLETED_STATUSES = ("ok", "incomplete")

REBALANCE = "rebalance"
HOLD = "hold"


def resolve_cadence(value: str | None = None) -> int:
    """`EFB_CADENCE` as sessions between rebalances, `1` when it is not usable.

    Unset, empty and `1` are all the daily behaviour the loop has always had, so a
    deployment that sets nothing is unchanged. A value that is not a positive whole
    number is refused loudly in the log and treated as unset rather than guessed
    at: a book that silently rebalances on the wrong calendar is worse than one
    that rebalances daily.
    """
    raw = value if value is not None else os.environ.get(CADENCE_ENV)
    text = str(raw or "").strip()
    if not text:
        return CADENCE_DAILY
    try:
        parsed = int(text)
    except ValueError:
        logger.warning("ignoring %s=%r: not a whole number", CADENCE_ENV, text)
        return CADENCE_DAILY
    if parsed < 1:
        logger.warning("ignoring %s=%r: below 1", CADENCE_ENV, text)
        return CADENCE_DAILY
    return parsed


def resolve_anchor(value: str | None = None) -> pd.Timestamp | None:
    """`EFB_CADENCE_ANCHOR` as a day, or None when it is not set or not a date."""
    raw = value if value is not None else os.environ.get(ANCHOR_ENV)
    text = str(raw or "").strip()
    if not text:
        return None
    stamp = pd.to_datetime(text, errors="coerce")
    if pd.isna(stamp):
        logger.warning("ignoring %s=%r: not a date", ANCHOR_ENV, text)
        return None
    return pd.Timestamp(stamp).normalize()


def _sessions(dates: Iterable[Any]) -> list[pd.Timestamp]:
    return [pd.Timestamp(day).normalize() for day in sorted(set(pd.to_datetime(list(dates))))]


def _anchor_index(sessions: list[pd.Timestamp], anchor: pd.Timestamp) -> int:
    """The session the calendar counts from: the anchor, or the one before it.

    An anchor on a non-session (a holiday, a weekend, or a date before the panel)
    is snapped to the last session on or before it, which is the session the
    owner meant; a date before every stored session starts the calendar at the
    first one rather than leaving it undefined.
    """
    position = 0
    for index, day in enumerate(sessions):
        if day <= anchor:
            position = index
        else:
            break
    return position


def _next_rebalance(
    sessions: list[pd.Timestamp], position: int, k: int, anchor: pd.Timestamp
) -> str | None:
    """The date of the next scheduled rebalance after `position`.

    From the stored sessions when they reach far enough; otherwise the calendar is
    extended with business days, which is an estimate (it does not know holidays)
    and is labelled as one by the caller that prints it.
    """
    if k <= 1:
        if position + 1 < len(sessions):
            return str(sessions[position + 1].date())
        return str((pd.Timestamp(sessions[position]) + pd.offsets.BDay(1)).date())
    for index in range(position + 1, len(sessions)):
        if (index - _anchor_index(sessions, anchor)) % k == 0:
            return str(sessions[index].date())
    step = k - ((position - _anchor_index(sessions, anchor)) % k)
    estimated = pd.Timestamp(sessions[position]) + pd.offsets.BDay(int(step))
    return str(estimated.date())


def plan(
    sessions: Sequence[Any],
    as_of: Any,
    k: int,
    anchor: Any = None,
    completed: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Whether the close being priced is a rebalance or a hold, and why.

    `sessions` is the trading-session list the close belongs to, `completed` the
    closes this job's own completion record holds (see `COMPLETED_STATUSES`).
    `completed=None` means the record could not be read: the calendar still says
    which day this is, but a missed rebalance cannot be proven, so nothing is
    promoted - and that is logged, because a promotion silently skipped is exactly
    the failure this rule exists to prevent.
    """
    days = _sessions(sessions)
    stamp = pd.Timestamp(as_of).normalize()
    if stamp not in days:
        raise ValueError(f"{stamp.date()} is not a session in the calendar")
    position = days.index(stamp)
    k = max(1, int(k))
    anchor_day = pd.Timestamp(anchor).normalize() if anchor is not None else stamp
    anchor_position = _anchor_index(days, anchor_day)
    offset = position - anchor_position
    # A close before the anchor is the book being built, not held: the calendar has
    # not started yet, and holding an empty book forever is not a state the loop can
    # be in. It is a rebalance, and the anchor then counts from its own session.
    before_anchor = offset < 0
    scheduled = k == 1 or before_anchor or (offset >= 0 and offset % k == 0)
    done = (
        {str(pd.Timestamp(day).date()) for day in completed}
        if completed is not None
        else None
    )
    missed: list[str] = []
    if not scheduled and done is not None:
        # The most recent scheduled rebalance before today, and whether the record
        # says it ran. A gap means every evening since has held a book the calendar
        # says should have been rebalanced, so today takes that rebalance.
        for index in range(position - 1, anchor_position - 1, -1):
            if (index - anchor_position) % k == 0:
                if str(days[index].date()) not in done:
                    missed.append(str(days[index].date()))
                break
    if not scheduled and done is None and k > 1:
        logger.warning(
            "the completion record could not be read, so a missed rebalance "
            "cannot be proven: %s is treated as scheduled (%s)",
            stamp.date(),
            REBALANCE if scheduled else HOLD,
        )
    day = REBALANCE if (scheduled or missed) else HOLD
    return {
        "k": k,
        # What was configured, and the session the count actually starts from: an
        # anchor on a holiday is snapped back, and the manifest has to say so.
        "anchor": str(anchor_day.date()),
        "anchor_session": str(days[anchor_position].date()),
        "day": day,
        "scheduled": bool(scheduled),
        "pending": bool(missed),
        "missed": missed,
        "offset": int(offset),
        "sessions_since": int(max(offset, 0)),
        "next_rebalance": _next_rebalance(days, position, k, anchor_day),
        # What the page and the email read: one sentence for a hold day, and the
        # date the owner is waiting for.
        "label": (
            f"hold day, next rebalance {_next_rebalance(days, position, k, anchor_day)}"
            if day == HOLD
            else (
                f"rebalance day (a missed rebalance on {missed[0]} is taken today)"
                if missed
                else "rebalance day"
            )
        ),
    }


def forced_reasons() -> tuple[str, ...]:
    """The reasons a hold day still trades, in the order the message lists them.

    Every one is a state the book cannot keep: a name that left the universe, a
    corporate action that moved the cash or the share count, and a short the broker
    will not lend. A reversal the order path already defers is in the same set,
    because closing it is a leg the loop has already decided it must send.
    """
    return ("left universe", "corporate action", "not shortable", "reversal")
