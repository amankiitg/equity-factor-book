"""The page on a monthly cadence: every panel measured from the last rebalance.

With `EFB_CADENCE=21` most evenings are hold days, and a panel that compares tonight
with last night is true and useless on one: 0 orders, $0 of sector gaps, 0 hedge legs.
This module builds the block the page reads instead, measured from the **anchor**, the
latest close whose manifest cadence day is `rebalance` (2026-10-23 today).

Every function here takes the frames it needs rather than reading the store, and the
one entry point, `block()`, returns `None` on any exception. That is deliberate: this is
reporting, it runs inside the evening, and a page that loses its new panels is worth
infinitely more than an evening that fails to publish.

**No identifier leaves here.** Every field is a number, a date or a ticker: no order id,
no account id, no client order id, so the Worker's sanitizer and its tests are
untouched.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

REBALANCE = "rebalance"
# The reason the loop records on a name the hedge moved, and the one the page's own
# hedge panel filters on.
HEDGE_REASON = "the hedge moved"
# The floor the sizing already uses: a position under it is a leg the book asked for
# and the account does not hold, which is a different statement from a name it never
# wanted.
MINIMUM_DOLLARS = 250.0

# A name the account can no longer trade because the company is gone. KVUE was
# acquired by KMB, so the rebalance target still owns the gap and no order can
# close it. It gets its own row rather than being dropped from the table.
RETIRED = {"KVUE": "retired (acquired by KMB), owed, cannot be traded"}

# The 2026-10-26 hold day re-sent eight legs of the 2026-10-23 rebalance (INTC, MRVL,
# STX, WDC, CHTR, HPE, AKAM, NVDA; $3,632) because its unfilled remainder was read
# from `efb.orders.filled_notional`, which is written before the open and never
# updated: the manifest saw the whole rebalance outstanding and the evening traded a
# book that had already settled. The fix (4ffd083) landed on 2026-10-27 and reads
# `efb.fills`. A leg from that evening is not a rebalance remainder: it re-traded a
# leg that had already filled, which is a different fact and gets its own row.
RETRADE_BUG_DAYS = {"2026-10-26": "remainder re-trade (bug, fixed 10-27)"}


def _day(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(pd.Timestamp(value))[:10]


def _manifest_of(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip().startswith("{"):
        import json

        return json.loads(value)
    return {}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def _count(value: Any) -> int:
    """A manifest count, whether the block stored the count or the legs themselves.

    `drift_guard.legs_under_minimum` is an integer in the 2026-10-30 manifest and a
    list in none of the ones this reads; taking `len()` of it raised, the anchored
    block was dropped, and a republish wrote a document with no monthly view at all.
    """
    if isinstance(value, list | tuple):
        return len(value)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def guard_threshold_from_env() -> float | None:
    """`EFB_DRIFT_GUARD` as a fraction, read exactly as `live.evening_job` reads it.

    A hold-day manifest records `drift_guard` as null when the guard **looked and
    left the book alone**, which is not the same as the guard being off: the
    threshold it compared against is a setting, not a measurement, and a strip that
    showed null for it said "no threshold" on every quiet evening. `EFB_DRIFT_GUARD`
    is where the evening gets it, so it is where this reads it, with the same
    unset/off/typo rule: only a fraction strictly between 0 and 1 is a threshold.
    """
    import os

    raw = os.environ.get("EFB_DRIFT_GUARD", "").strip().lower()
    if not raw or raw in {"off", "none", "0", "false"}:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if 0.0 < value < 1.0 else None


def _trading_bps(manifest: dict[str, Any]) -> float | None:
    """Spread plus impact plus commission: the half of the cost a fill can move.

    The manifest records the four parts and a total that includes borrow. The trading
    half is the parts, not the total, because borrow is paid whether or not anything
    trades and would make a quiet evening look expensive.
    """
    costs = manifest.get("cost_breakdown_bps") or {}
    recorded = _number(costs.get("trading"))
    if recorded is not None:
        return recorded
    parts = [_number(costs.get(key)) for key in ("spread", "impact", "commission")]
    known = [part for part in parts if part is not None]
    return float(sum(known)) if known else None


def anchor_close(proposals: pd.DataFrame) -> tuple[str | None, str]:
    """The latest close whose cadence day is a rebalance, and where that came from.

    Returns `(close, source)` where source is one of:

    - `rebalance` - the latest close is itself a rebalance, so the anchor is tonight
      and every panel is the panel it is on a rebalance evening;
    - `cadence` - the latest close is a hold day and the anchor is an earlier one;
    - `daily` - no close carries a cadence block, so the anchor is tonight and the
      page's daily behaviour is unchanged.
    """
    if proposals is None or proposals.empty or "trade_date" not in proposals.columns:
        return None, "daily"
    frame = proposals.copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str.slice(0, 10)
    frame = frame.sort_values("trade_date")
    latest = str(frame["trade_date"].iloc[-1])
    days: list[tuple[str, str | None]] = []
    for record in frame.to_dict("records"):
        cadence = _manifest_of(record.get("manifest")).get("cadence")
        days.append(
            (
                str(record["trade_date"]),
                str(cadence.get("day")) if isinstance(cadence, dict) else None,
            )
        )
    if not any(day for _, day in days):
        return latest, "daily"
    latest_day = days[-1][1]
    if latest_day == REBALANCE:
        return latest, REBALANCE
    earlier = [close for close, day in days if day == REBALANCE]
    if not earlier:
        return latest, "daily"
    return earlier[-1], "cadence"


def _book(frame: pd.DataFrame | None, close: str) -> pd.DataFrame:
    """One close's rows, with `ticker`, `side` and a signed dollar or weight column."""
    if frame is None or frame.empty or "trade_date" not in frame.columns:
        return pd.DataFrame()
    sub = frame.copy()
    sub["trade_date"] = sub["trade_date"].astype(str).str.slice(0, 10)
    sub = sub.loc[sub["trade_date"] == close].copy()
    if sub.empty:
        return sub
    sub["ticker"] = sub["ticker"].astype(str)
    if "side" in sub.columns:
        sub["side"] = sub["side"].astype(str).str.lower()
    return sub


def _dollars(frame: pd.DataFrame) -> dict[str, float]:
    """Signed dollars per ticker, from `market_value` or `weight` x NAV."""
    if frame is None or frame.empty:
        return {}
    column = "market_value" if "market_value" in frame.columns else None
    values = (
        pd.to_numeric(frame[column], errors="coerce")
        if column
        else pd.Series(dtype=float)
    )
    return {
        str(ticker): float(value)
        for ticker, value in zip(frame["ticker"], values, strict=False)
        if value is not None and not pd.isna(value)
    }


def _sides(frame: pd.DataFrame) -> dict[str, str]:
    if frame is None or frame.empty or "side" not in frame.columns:
        return {}
    return {
        str(ticker): str(side).lower()
        for ticker, side in zip(frame["ticker"], frame["side"], strict=False)
    }


def _leg_dollars(
    orders: pd.DataFrame, fills: pd.DataFrame, ticker: str, close: str
) -> tuple[float | None, str | None, str | None, bool]:
    """One name's filled dollars on one close, that close, and the day it filled.

    The third value is the fill's own date, read from `efb.fills.updated_at`: the
    evening sends after the close and the fill lands at the next open, so a leg
    priced from the 2026-10-23 close filled on 2026-10-26. None when the store holds
    no fill row for it, which is not the same as a fill on the close's own date and
    the page labels the column for which of the two it is showing. The fourth value
    is whether a FILLED row was found at all, which is what says a leg is truly
    unfilled rather than merely unpriced.
    """
    if orders is None or orders.empty:
        return None, None, None, False
    sub = orders.loc[
        (orders["ticker"].astype(str) == ticker)
        & (orders["trade_date"].astype(str).str.slice(0, 10) == close)
    ]
    if sub.empty:
        return None, None, None, False
    if fills is None or fills.empty:
        return None, close, None, False
    match = fills.loc[
        (fills["ticker"].astype(str) == ticker)
        & (fills["trade_date"].astype(str).str.slice(0, 10) == close)
    ]
    total = 0.0
    filled_at: str | None = None
    filled = False
    for row in sub.itertuples(index=False):
        intended = _number(getattr(row, "intended_notional", None)) or 0.0
        for fill in match.itertuples(index=False):
            if str(getattr(fill, "status", "")).upper() != "FILLED":
                continue
            filled = True
            amount = _number(getattr(fill, "filled_notional", None)) or 0.0
            total += amount if intended >= 0 else -amount
            stamp = getattr(fill, "updated_at", None)
            day = _day(stamp)
            if day and (filled_at is None or day < filled_at):
                filled_at = day
    # The dollars are the evidence that it filled; the timestamp is what says when.
    # A fill row without one still means the leg is filled, and its close date is the
    # honest answer to "which day", marked as the close rather than as the fill.
    if not filled:
        return None, close, None, False
    return total, close, filled_at, True


def flip_rows(
    target: pd.DataFrame,
    before: pd.DataFrame,
    now: pd.DataFrame,
    orders: pd.DataFrame,
    fills: pd.DataFrame,
    anchor: str,
    guard_dates: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Every name whose side before the rebalance differs from its target side.

    A flip counts **once**, with both legs' dollars and the close each filled on, and
    it is complete when the account is on the target side within the minimum. It is
    never an exit plus an open: the one-close bridge reports the 2026-10-23 rebalance
    as four exits and the 2026-10-26 hold as four opens, which is one position each
    time, and this says so.
    """
    target_side = _sides(target)
    before_side = _sides(before)
    now_side = _sides(now)
    now_dollars = _dollars(now)
    rows: list[dict[str, Any]] = []
    for ticker, before in before_side.items():
        wanted = target_side.get(ticker)
        if wanted is None or wanted == before:
            continue
        close_leg, close_leg_day, close_leg_filled, close_ok = _leg_dollars(
            orders, fills, ticker, anchor
        )
        open_leg = open_day = open_filled = None
        open_ok = False
        later = (
            orders.loc[orders["trade_date"].astype(str).str.slice(0, 10) > anchor]
            if orders is not None and not orders.empty
            else pd.DataFrame()
        )
        for day in sorted(later["trade_date"].astype(str).str.slice(0, 10).unique()):
            open_leg, open_day, open_filled, open_ok = _leg_dollars(
                orders, fills, ticker, day
            )
            if open_leg is not None:
                break
        lying = now_side.get(ticker)
        dollars = now_dollars.get(ticker, 0.0)
        later_guards = [
            day
            for day in (guard_dates or {}).get(ticker, [])
            if day > (open_day or close_leg_day or anchor)
        ]
        refipped_on = later_guards[-1] if later_guards else None
        legs_filled = bool(close_ok and open_ok)
        if refipped_on:
            state = "refipped"
            state_label = f"re-flipped later by the drift guard on {refipped_on}"
        elif legs_filled:
            state = "complete"
            state_label = "complete"
        else:
            state = "owed"
            state_label = "still owed"
        rows.append(
            {
                "ticker": ticker,
                "from_side": before,
                "to_side": wanted,
                "close_dollars": None if close_leg is None else abs(close_leg),
                "close_filled": close_leg_day,
                "close_filled_at": close_leg_filled,
                "open_dollars": None if open_leg is None else abs(open_leg),
                "open_filled": open_day,
                "open_filled_at": open_filled,
                "now_dollars": dollars,
                "on_target_side": lying == wanted,
                "legs_filled": legs_filled,
                "refipped_on": refipped_on,
                "state": state,
                "state_label": state_label,
                "complete": legs_filled
                and lying == wanted
                and abs(dollars) > MINIMUM_DOLLARS,
            }
        )
    return sorted(rows, key=lambda row: -abs(row["now_dollars"]))


def bridge(
    target: pd.DataFrame,
    before: pd.DataFrame,
    now: pd.DataFrame,
    orders: pd.DataFrame,
    fills: pd.DataFrame,
    anchor: str,
    guard_dates: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """The account before the rebalance, what the rebalance did, and the account now."""
    before_dollars = _dollars(before)
    now_dollars = _dollars(now)
    target_side = _sides(target)
    flips = flip_rows(target, before, now, orders, fills, anchor, guard_dates)
    flipped = {row["ticker"] for row in flips}
    opened = sorted(set(now_dollars) - set(before_dollars) - flipped)
    exited = sorted(
        ticker
        for ticker in before_dollars
        if ticker not in now_dollars
        and ticker not in target_side
        and ticker not in flipped
    )
    resized = sorted(
        ticker
        for ticker in before_dollars
        if ticker in now_dollars and ticker not in flipped
    )
    under_minimum = sorted(
        ticker
        for ticker, dollars in now_dollars.items()
        if abs(dollars) < MINIMUM_DOLLARS and ticker not in before_dollars
    )
    # Gross, not net: a market-neutral book's signed dollars sum to about zero, so a
    # bridge on the signed total says nothing. Every term below is absolute too, which
    # makes the identity exact rather than approximate.
    total_before = sum(abs(value) for value in before_dollars.values())
    total_now = sum(abs(value) for value in now_dollars.values())
    opened_usd = sum(abs(now_dollars[t]) for t in opened if t in now_dollars)
    exited_usd = sum(abs(before_dollars[t]) for t in exited)
    resized_usd = sum(
        abs(now_dollars.get(t, 0.0)) - abs(before_dollars.get(t, 0.0)) for t in resized
    )
    flipped_usd = sum(
        abs(now_dollars.get(row["ticker"], 0.0))
        - abs(before_dollars.get(row["ticker"], 0.0))
        for row in flips
    )
    rebuilt = total_before + opened_usd - exited_usd + resized_usd + flipped_usd
    return {
        "before_dollars": total_before,
        "after_dollars": total_now,
        "opened": len(opened),
        "exited": len(exited),
        "resized": len(resized),
        "flipped": len(flips),
        "under_minimum": len(under_minimum),
        "opened_usd": opened_usd,
        "exited_usd": exited_usd,
        "resized_usd": resized_usd,
        "flipped_usd": flipped_usd,
        "flip_rows": flips,
        "complete_flips": sum(1 for row in flips if row["complete"]),
        "identities": [
            {
                "name": "gross before + opened - exited + resized + flipped",
                "left": rebuilt,
                "right": total_now,
                "holds": abs(total_now - rebuilt) <= 1.0,
            }
        ],
        "holds": abs(total_now - rebuilt) <= 1.0,
    }


def _guard_events(
    proposals: pd.DataFrame, anchor: str, today: str
) -> dict[str, list[str]]:
    """The names a drift guard traded after the rebalance, and the days it did.

    The guard's legs are recorded in the hold day's own manifest. They are what
    makes CCL a re-flip rather than a flip that stayed complete: the rebalance
    closed the short and opened the long, and the 2026-11-04 guard moved the long
    again. Reading the manifests is the only way the page can tell that later leg
    from a second rebalance.
    """
    events: dict[str, list[str]] = {}
    if proposals is None or proposals.empty or "trade_date" not in proposals.columns:
        return events
    frame = proposals.copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str.slice(0, 10)
    frame = frame.loc[(frame["trade_date"] > anchor) & (frame["trade_date"] <= today)]
    for record in frame.to_dict("records"):
        guard = _manifest_of(record.get("manifest")).get("drift_guard") or {}
        if not isinstance(guard, dict) or not guard.get("fired"):
            continue
        day = str(record["trade_date"])[:10]
        for leg in guard.get("legs") or []:
            if not isinstance(leg, dict) or leg.get("traded") is False:
                continue
            ticker = str(leg.get("ticker") or "").strip()
            if ticker:
                events.setdefault(ticker, []).append(day)
    return {ticker: sorted(set(days)) for ticker, days in events.items()}


def _guard_days(proposals: pd.DataFrame, anchor: str, today: str) -> set[str]:
    """The closes on which the drift guard fired, whether it could size a leg or not.

    A guard evening is a day, not a name: on 2026-10-30 it sent 109 legs and on
    2026-11-04 about 140, and every one of them is the same decision made in the
    same evening. Reading the dates from the manifests is what lets a leg be
    attributed to the evening that wanted it rather than to its own open or close
    intent, which every submitted order carries.
    """
    days: set[str] = set()
    if proposals is None or proposals.empty or "trade_date" not in proposals.columns:
        return days
    frame = proposals.copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str.slice(0, 10)
    frame = frame.loc[(frame["trade_date"] > anchor) & (frame["trade_date"] <= today)]
    for record in frame.to_dict("records"):
        guard = _manifest_of(record.get("manifest")).get("drift_guard") or {}
        if isinstance(guard, dict) and guard.get("fired"):
            days.add(str(record["trade_date"])[:10])
    return days


def _weights(frame: pd.DataFrame | None) -> dict[str, float]:
    """Signed weight per ticker, from a book frame's own `weight` column."""
    if frame is None or frame.empty or "weight" not in frame.columns:
        return {}
    return {
        str(ticker): float(weight)
        for ticker, weight in zip(
            frame["ticker"],
            pd.to_numeric(frame["weight"], errors="coerce"),
            strict=False,
        )
        if weight is not None and not pd.isna(weight)
    }


def _gaps(target: pd.DataFrame, now: pd.DataFrame) -> dict[str, float]:
    """`w_now - w_target` per ticker, over the union of the two books.

    One function because three panels read it - the drift card, the sector deltas and
    the drift list - and a page whose sector bars summed to a different number from
    the drift above them would be worse than either alone.
    """
    wanted = _weights(target)
    have = _weights(now)
    # Sorted, because this dict decides the order two sums run in and floating point
    # addition is not associative: an unsorted set made a republish of the same close
    # differ from the first write in the twelfth decimal, which turns "the fixture is
    # the published document" into a claim about the machine rather than the data.
    return {
        ticker: have.get(ticker, 0.0) - wanted.get(ticker, 0.0)
        for ticker in sorted(set(wanted) | set(have))
    }


def drift(
    target: pd.DataFrame,
    now: pd.DataFrame,
    nav: float | None,
    trading_bps: float | None,
) -> dict[str, Any]:
    """The distance from the rebalance target, and what closing it would cost.

    `half_turnover` is `sum|w_now - w_target| / 2`, the standard one-sided turnover:
    a dollar sold and a dollar bought are one dollar of drift, not two. The cost is the
    dollars that would trade, both sides, at the proposal's trading cost per dollar,
    which is spread plus impact plus commission and excludes borrow.
    """
    if target is None or target.empty or "weight" not in target.columns:
        return {}
    wanted = _weights(target)
    have = _weights(now)
    gaps = _gaps(target, now)
    half = sum(abs(gap) for gap in gaps.values()) / 2.0
    traded = sum(abs(gap) for gap in gaps.values())
    largest = sorted(gaps.items(), key=lambda item: -abs(item[1]))[:5]
    return {
        "half_turnover_pct": half,
        "half_turnover_usd": None if nav is None else half * nav,
        "traded_usd": None if nav is None else traded * nav,
        "estimated_cost_usd": (
            None
            if nav is None or trading_bps is None
            else traded * nav * float(trading_bps) / 1e4
        ),
        "largest": [
            {
                "ticker": ticker,
                "weight_now": have.get(ticker, 0.0),
                "weight_target": wanted.get(ticker, 0.0),
                "usd": None if nav is None else gap * nav,
            }
            for ticker, gap in largest
        ],
    }


def _events_of(
    orders: pd.DataFrame, ticker: str, anchor: str, now_close: str
) -> list[dict[str, Any]]:
    """One name's order legs between the rebalance and the latest read.

    A row in `efb.orders` is a leg the evening asked for, not a trade: the store
    holds the ones under the minimum and the ones the broker refused too, with a
    `reason_code` and no broker id. Each row says whether it became an order, by
    the same rule the leg table uses, so a reader that is about what changed can
    ignore the rows that never reached the broker.
    """
    if orders is None or orders.empty or "trade_date" not in orders.columns:
        return []
    days = orders["trade_date"].astype(str).str.slice(0, 10)
    rows = orders.loc[
        (orders["ticker"].astype(str) == ticker)
        & (days >= anchor)
        & (days <= now_close)
    ]
    has_broker = "broker_order_id" in rows.columns
    events: list[dict[str, Any]] = []
    for row in rows.itertuples(index=False):
        code = str(getattr(row, "reason_code", "") or "").strip()
        broker = str(getattr(row, "broker_order_id", "") or "").strip()
        events.append(
            {
                "date": str(row.trade_date)[:10],
                "code": code,
                "intent": str(getattr(row, "position_intent", "") or ""),
                "sent": bool(broker) if has_broker else not code,
            }
        )
    return events


def _trade_note(day: str, anchor: str, guard_days: set[str]) -> tuple[str, str]:
    """What a sent leg on `day` was, in the holdings column's own words.

    A holding changes size on the evening that asked for the leg, and the evening
    is read from the manifest, not from the fact that a row exists. The anchor is
    the rebalance's own evening and a resize there is real. After it, the only
    evenings that trade a name are a guard evening and a hold day re-trading a leg
    the rebalance did not complete; a hold day never resizes a holding.
    """
    if day == anchor:
        return (f"resized ({day})", "resized")
    if day in guard_days:
        return (f"drift guard leg ({day})", "guard")
    if day in RETRADE_BUG_DAYS:
        return (f"remainder re-trade ({day})", "re-trade")
    return (f"rebalance remainder ({day})", "remainder")


def _unsent_note(events: list[dict[str, Any]], guard_days: set[str]) -> tuple[str, str]:
    """A hold-day leg the evening wanted and never sent, said as such.

    The store writes a row for a leg under the minimum and for one the broker
    refused, with no broker id, so a holdings table that read any row as a trade
    said every name the guard could not size had been resized. It had not: the
    position is the one the rebalance left.
    """
    guarded = [event["date"] for event in events if event["date"] in guard_days]
    day = max(guarded) if guarded else events[-1]["date"]
    codes = {event["code"] for event in events if event["code"]}
    under = "BELOW_MIN_NOTIONAL" in codes
    if guarded and under:
        return (f"held, guard leg under the minimum ({day})", "held")
    if guarded:
        return (f"held, guard leg refused ({day})", "held")
    if under:
        return (f"held, leg under the minimum ({day})", "held")
    return ("held, no trade since", "held")


def _tonight_note(events: list[dict[str, Any]], now_close: str) -> str | None:
    """The small secondary note: what tonight did, and only when it did anything."""
    tonight = [event for event in events if event["date"] == now_close]
    if not tonight:
        return None
    event = tonight[-1]
    code = event["code"]
    intent = event["intent"]
    if code == "BELOW_MIN_NOTIONAL":
        detail = "a leg under the minimum"
    elif code == "COVER_UNDER_ONE_SHARE":
        detail = "a cover under one share"
    elif code:
        detail = code.replace("_", " ").lower()
    elif intent.endswith("_to_open"):
        detail = "opened a position"
    elif intent.endswith("_to_close"):
        detail = "closed a position"
    else:
        detail = "traded"
    return f"traded tonight: {detail}"


def holdings(
    target: pd.DataFrame,
    before: pd.DataFrame,
    now: pd.DataFrame,
    orders: pd.DataFrame,
    flips: list[dict[str, Any]],
    guard_dates: dict[str, list[str]],
    guard_days: set[str],
    anchor: str,
    now_close: str,
    nav: float | None,
) -> dict[str, Any]:
    """One row per name: what it did since the rebalance, and its gap now.

    The gap is exactly the number the distance panel uses: w_now minus w_target,
    as a fraction of NAV and the same fraction times NAV in dollars. The since
    column replaces tonight's reason as the primary column. Tonight's reason is
    kept only when tonight actually traded.
    """
    wanted = _weights(target)
    have = _weights(now)
    before_weights = _weights(before)
    gaps = _gaps(target, now)
    flip_by_ticker = {str(row["ticker"]): row for row in flips}
    tickers = (
        set(wanted)
        | set(have)
        | set(before_weights)
        | set(flip_by_ticker)
        | set(guard_dates)
        | set(RETIRED)
    )
    rows: list[dict[str, Any]] = []
    for ticker in sorted(tickers):
        events = _events_of(orders, ticker, anchor, now_close)
        traded = [event for event in events if event["sent"]]
        last_trade = traded[-1] if traded else None
        guards = guard_dates.get(ticker, [])
        flip = flip_by_ticker.get(ticker)
        retired_note = RETIRED.get(ticker)
        since_kind = "held"
        since_date = anchor
        if retired_note:
            since = retired_note
            since_kind = "retired"
        elif flip is not None:
            closed = flip.get("close_filled") or anchor
            opened = flip.get("open_filled")
            since = (
                f"flipped ({closed} to {opened})"
                if opened
                else f"flipped (closed {closed}, open still owed)"
            )
            since_kind = "flipped"
            since_date = opened or closed
            later = [day for day in guards if day > since_date]
            if later:
                since = f"{since}; drift guard leg ({later[-1]})"
                since_date = later[-1]
        elif guards:
            since = f"drift guard leg ({guards[-1]})"
            since_kind = "guard"
            since_date = guards[-1]
        elif last_trade is not None and last_trade["date"] in guard_days:
            # The evening decides it. A name the guard's own leg list omitted, or
            # listed only as a candidate under the minimum, still traded on a guard
            # evening, and a guard evening is not a rebalance resizing a holding.
            since, since_kind = _trade_note(last_trade["date"], anchor, guard_days)
            since_date = last_trade["date"]
        elif ticker in before_weights and ticker not in wanted and ticker not in have:
            since_date = events[-1]["date"] if events else anchor
            since = f"exited ({since_date})"
            since_kind = "exited"
        elif ticker not in before_weights and ticker in wanted:
            since_date = events[0]["date"] if events else anchor
            if since_date == anchor:
                since = f"opened at the rebalance ({anchor})"
            else:
                since = f"opened ({since_date})"
            since_kind = "opened"
        elif ticker in before_weights and ticker in have:
            if last_trade is not None:
                since_date = last_trade["date"]
                since, since_kind = _trade_note(since_date, anchor, guard_days)
            elif events:
                since_date = events[-1]["date"]
                since, since_kind = _unsent_note(events, guard_days)
            else:
                since = "held, no trade since"
        elif ticker in have and ticker not in wanted:
            since_date = events[-1]["date"] if events else anchor
            since = f"held, not in the target since {since_date}"
            since_kind = "held-other"
        elif last_trade is not None:
            since_date = last_trade["date"]
            since, since_kind = _trade_note(since_date, anchor, guard_days)
        elif events:
            since_date = events[-1]["date"]
            since, since_kind = _unsent_note(events, guard_days)
        else:
            since = "held, no trade since"
        gap = gaps.get(ticker, 0.0)
        rows.append(
            {
                "ticker": ticker,
                "since": since,
                "since_kind": since_kind,
                "since_date": since_date,
                "weight_now": have.get(ticker, 0.0),
                "weight_target": wanted.get(ticker, 0.0),
                "gap_weight": gap,
                "gap_usd": None if nav is None else gap * float(nav),
                "tonight": _tonight_note(events, now_close),
                "retired": bool(retired_note),
                "owed": bool(retired_note),
                "note": retired_note,
            }
        )
    rows.sort(key=lambda row: (-abs(row["gap_weight"]), row["ticker"]))
    return {"anchor": anchor, "as_of": now_close, "rows": rows}


def _labels() -> dict[int, str]:
    """GICS code to name, from the table the risk model's sector columns use."""
    from efb.models.fundamental import SECTOR_CODES

    return {int(code): name for name, code in SECTOR_CODES.items()}


def sectors(
    target: pd.DataFrame,
    now: pd.DataFrame,
    nav: float | None,
    sector_of: dict[str, int] | None,
    *,
    anchor: str | None = None,
    drivers: int = 3,
) -> dict[str, Any]:
    """The account against the **anchor rebalance's** target, by sector, in dollars.

    The page's own sector panel compares the account against tonight's book, and on a
    hold day tonight's book *is* the account: eleven rows of `+$0`, which is a true
    reading of nothing. This is the same comparison against the book the last rebalance
    asked for, so a hold day answers where the account has drifted from - and the
    answer is the same set of name-level gaps the drift card is made from, grouped.

    Two numbers per sector, because a market- and sector-neutral book needs both: the
    **net** delta says which way the sector is away from target, and it is small by
    construction because the book is built sector-neutral; the **traded** dollars say
    how far the names inside it are from their own targets, which is where the drift
    actually lives - a sector flat net and eight percent away name by name is a stale
    book, not an aligned one. The identity is on the traded side and is asserted in the
    tests:

        sum over sectors of traded_usd / 2  ==  drift.half_turnover_usd

    Names the sector map does not carry are their own row rather than a guessed one,
    as they are on the page, and a name in neither book contributes nothing.
    """
    if nav is None or not sector_of:
        return {}
    if target is None or target.empty or "weight" not in target.columns:
        return {}
    wanted = _weights(target)
    have = _weights(now)
    gaps = _gaps(target, now)
    labels = _labels()

    grouped: dict[int | None, dict[str, Any]] = {}
    for ticker, gap in gaps.items():
        code = sector_of.get(ticker)
        code = None if code is None else int(code)
        row = grouped.get(code)
        if row is None:
            row = grouped[code] = {
                "code": code,
                "label": (
                    labels.get(code, "Unmapped") if code is not None else "Unmapped"
                ),
                "target_usd": 0.0,
                "account_usd": 0.0,
                "delta_usd": 0.0,
                "traded_usd": 0.0,
                "n_target": 0,
                "n_account": 0,
                "_drivers": [],
            }
        if ticker in wanted:
            row["target_usd"] += wanted[ticker] * nav
            row["n_target"] += 1
        if ticker in have:
            row["account_usd"] += have[ticker] * nav
            row["n_account"] += 1
        row["delta_usd"] += gap * nav
        row["traded_usd"] += abs(gap) * nav
        row["_drivers"].append(
            {
                "ticker": ticker,
                "usd": gap * nav,
                "weight_now": have.get(ticker, 0.0),
                "weight_target": wanted.get(ticker, 0.0),
            }
        )

    rows: list[dict[str, Any]] = []
    for row in grouped.values():
        top = sorted(row.pop("_drivers"), key=lambda item: -abs(item["usd"]))[:drivers]
        row["drivers"] = top
        rows.append(row)
    rows.sort(key=lambda row: -abs(row["delta_usd"]))
    both = sum(row["traded_usd"] for row in rows)
    one_side = both / 2.0
    return {
        "anchor": anchor,
        "nav": nav,
        "rows": rows,
        "one_side_usd": one_side,
        "both_sides_usd": both,
        "unmapped_usd": sum(row["delta_usd"] for row in rows if row["code"] is None),
        "n_names": len(gaps),
        "n_mapped": sum(1 for ticker in gaps if sector_of.get(ticker) is not None),
    }


def hedge(
    target: pd.DataFrame,
    reconciliation: pd.DataFrame | None,
    close: str,
    nav: float | None,
    turnover_usd: float | None,
) -> dict[str, Any]:
    """The rebalance's own hedge: what it moved, and what carries the risk.

    The page's hedge panel reads tonight's book, so on a hold day it reports "0 of 196
    names, $0 of legs" - true, and about a night that did nothing. This is the same
    footprint for the close that actually hedged, from the target rows' own `reason`
    and the leg between `previous_weight` and `weight`, and from that close's
    `reconciliation.traded_risk` for the risk shares.

    Read-only and descriptive: nothing here is a causal claim, and the page keeps
    saying so.
    """
    if target is None or target.empty or "weight" not in target.columns:
        return {}
    frame = target.copy()
    weight = pd.to_numeric(frame["weight"], errors="coerce")
    previous = pd.to_numeric(frame.get("previous_weight"), errors="coerce")
    legs = (weight - previous).abs() if previous is not None else weight * 0
    reasons = (
        frame["reason"].astype(str)
        if "reason" in frame.columns
        else pd.Series("", index=frame.index, dtype=str)
    )
    moved = reasons.str.strip() == HEDGE_REASON
    moved_legs = float(legs.where(moved, 0.0).fillna(0.0).sum())
    moved_usd = None if nav is None else moved_legs * nav
    risk = _traded_risk(reconciliation, close)
    anchors = {
        str(ticker): float(value)
        for ticker, value in zip(frame["ticker"], weight, strict=False)
        if value is not None and not pd.isna(value)
    }
    return {
        "anchor": close,
        "moved_names": int(moved.sum()),
        "book_names": int(len(frame)),
        "moved_usd": moved_usd,
        "share_of_turnover": (
            None
            if not turnover_usd or moved_legs == 0
            else moved_legs * (nav or 0.0) / turnover_usd
        ),
        "variance_shares": [
            {
                "ticker": str(entry.get("ticker")),
                "variance_share": _number(entry.get("variance_share")),
                "weight": anchors.get(str(entry.get("ticker"))),
            }
            for entry in (risk.get("top_variance_shares") or [])
            if isinstance(entry, dict)
        ],
        "n_eff": _number(risk.get("n_eff")),
        "max_weight": _number(risk.get("max_weight")),
    }


def _traded_risk(reconciliation: pd.DataFrame | None, close: str) -> dict[str, Any]:
    """One close's stored risk block, or `{}` when the store has none for it."""
    if reconciliation is None or reconciliation.empty:
        return {}
    if "trade_date" not in reconciliation.columns:
        return {}
    frame = reconciliation.copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str.slice(0, 10)
    rows = frame.loc[frame["trade_date"] == close]
    if rows.empty:
        return {}
    value = rows.iloc[-1].get("traded_risk")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _filled_order_ids(day_fills: pd.DataFrame) -> set[str]:
    """The order ids the close's fills record as FILLED."""
    if day_fills is None or day_fills.empty or "order_id" not in day_fills.columns:
        return set()
    status = day_fills["status"].astype(str).str.upper()
    done = day_fills.loc[status == "FILLED"]
    return {str(value) for value in done["order_id"].dropna()}


def _shortfall(sent: pd.DataFrame, filled_ids: set[str]) -> float:
    """What the sent legs still owe: the dollars of the ones with no fill."""
    if sent is None or sent.empty:
        return 0.0
    ids = (
        sent["broker_order_id"].astype("string").fillna("").str.strip()
        if "broker_order_id" in sent.columns
        else pd.Series("", index=sent.index)
    )
    owed = pd.to_numeric(sent["intended_notional"], errors="coerce").fillna(0.0).abs()
    return float(owed.loc[~ids.isin(filled_ids)].sum())


def rebalance_card(
    anchor: str,
    anchor_manifest: dict[str, Any],
    orders: pd.DataFrame,
    fills: pd.DataFrame,
    nav: float | None,
) -> dict[str, Any]:
    """The rebalance itself: what it sent, what it cost, and what is still owed."""
    if orders is None or orders.empty:
        return {"close": anchor}
    legs = orders.loc[orders["trade_date"].astype(str).str.slice(0, 10) == anchor]
    if legs.empty:
        return {"close": anchor}
    intended = (
        pd.to_numeric(legs["intended_notional"], errors="coerce").fillna(0.0).abs()
    )
    # Two different counts, and the card said one number for both. A leg under the
    # $250 minimum is built and never sent: it is not an order the broker answered,
    # and calling it an unfilled leg overstates what the rebalance owes. Measured on
    # the 2026-10-23 anchor: 224 legs built, 208 sent (every one of them filled), and
    # 16 under the minimum carrying $2,253.26 that was never meant to trade.
    codes = (
        legs["reason_code"].fillna("").astype(str)
        if "reason_code" in legs.columns
        else pd.Series("", index=legs.index)
    )
    # A frame without the column is a book written before the column existed, and
    # every leg in it was sent; reading it as "none sent" would report the whole
    # rebalance as never sent.
    sent_mask = (
        legs["broker_order_id"].astype("string").fillna("").str.strip() != ""
        if "broker_order_id" in legs.columns
        else pd.Series(True, index=legs.index)
    )
    sent = legs.loc[sent_mask]
    skipped = legs.loc[~sent_mask]
    under_minimum = skipped.loc[codes.loc[~sent_mask] == "BELOW_MIN_NOTIONAL"]
    other_skipped = skipped.loc[codes.loc[~sent_mask] != "BELOW_MIN_NOTIONAL"]
    sent_usd = float(intended.loc[sent_mask].sum())
    under_usd = float(intended.loc[under_minimum.index].sum())

    costs = anchor_manifest.get("cost_breakdown_bps") or {}
    day_fills = (
        fills.loc[fills["trade_date"].astype(str).str.slice(0, 10) == anchor]
        if fills is not None and not fills.empty
        else pd.DataFrame()
    )
    filled_usd = 0.0
    if not day_fills.empty:
        status = day_fills["status"].astype(str).str.upper()
        done = day_fills.loc[status == "FILLED"]
        filled_usd = float(
            pd.to_numeric(done["filled_notional"], errors="coerce").fillna(0.0).sum()
        )
    filled_ids = _filled_order_ids(day_fills)
    # A sent leg is filled when its own fill row says so, counted leg by leg.
    sent_ids = (
        sent["broker_order_id"].astype("string").fillna("").str.strip()
        if "broker_order_id" in sent.columns
        else pd.Series("", index=sent.index)
    )
    filled_legs = int(sent_ids.isin(filled_ids).sum())
    realized = None
    if nav and filled_usd:
        from live import fills as fills_module

        try:
            realized = fills_module.realized_cost_bps(day_fills, nav)
        except Exception as exc:  # noqa: BLE001 - one field, not the block
            logger.warning(
                "the rebalance's realized cost could not be measured: %s",
                type(exc).__name__,
            )
            realized = None
    return {
        "close": anchor,
        "orders": int(len(legs)),
        # The legs that were meant to be sent, and how many of those filled. The
        # shortfall is what is owed; the under-minimum legs are reported beside it
        # because they explain the gap between the leg count and the sent count.
        "sent_legs": int(len(sent)),
        "filled_legs": filled_legs,
        "under_minimum_legs": int(len(under_minimum)),
        "under_minimum_usd": under_usd,
        "skipped_other_legs": int(len(other_skipped)),
        "notional": sent_usd,
        "pct_nav": None if not nav else sent_usd / float(nav),
        "expected_cost_bps": _number(
            anchor_manifest.get("expected_establishment_cost_bps") or costs.get("total")
        ),
        "expected_cost_usd": (
            None
            if nav is None
            else (_number(costs.get("total")) or 0.0) * float(nav) / 1e4
        ),
        "realized_cost_bps": realized,
        "legs_total": int(len(legs)),
        "legs_complete": filled_legs,
        "legs_incomplete": max(int(len(sent)) - filled_legs, 0),
        # Owed is the sent legs with no fill, in dollars: the leg-level rule the page
        # states, and not a sum of dollar gaps, which reported a fully filled
        # rebalance as owing whatever the prices moved.
        "dollars_owed": _shortfall(sent, filled_ids),
    }


def block(
    *,
    proposals: pd.DataFrame,
    targets: pd.DataFrame,
    account: pd.DataFrame,
    orders: pd.DataFrame,
    fills: pd.DataFrame,
    today: str,
    reconciliation: pd.DataFrame | None = None,
    tonight_manifest: dict[str, Any] | None = None,
    nav: float | None = None,
    guard_threshold: float | None = None,
    sector_of: dict[str, int] | None = None,
) -> dict[str, Any] | None:
    """The whole anchored block, or `None` when it cannot be built.

    `None` is the absent block: the page renders exactly as it does today, which is
    what a document written before this existed has to look like.
    """
    try:
        return _block(
            proposals=proposals,
            targets=targets,
            account=account,
            orders=orders,
            fills=fills,
            today=today,
            reconciliation=reconciliation,
            tonight_manifest=tonight_manifest or {},
            nav=nav,
            guard_threshold=guard_threshold,
            sector_of=sector_of,
        )
    except Exception as exc:  # noqa: BLE001 - reporting must never stop the evening
        logger.warning(
            "the anchored block was not built: %s: %s", type(exc).__name__, exc
        )
        return None


def sector_map_from_store() -> dict[str, int]:
    """Ticker to GICS code, from the store's own `efb.e11_sectors`.

    The page's sector panel reads a bundled map generated from
    `data/processed/sectors.parquet`, and this is the same table in the store (the
    appendix keeps them in step), so a dollar the writer files under "Information
    Technology" is the sector the page colours it with. Labels the risk model does not
    know are left out rather than guessed: they land in the page's Unmapped row, which
    is the truth about them.

    Empty rather than raising: no map means no sector field, and the page then renders
    its own panel exactly as before.
    """
    from efb.models.fundamental import SECTOR_CODES
    from live import appendix

    try:
        rows = appendix.read_appendix(appendix.SPEC_BY_NAME["sectors"])
    except Exception as exc:  # noqa: BLE001 - a page field, never the evening
        logger.warning(
            "the sector map could not be read: %s: %s", type(exc).__name__, exc
        )
        return {}
    if rows is None or rows.empty or "ticker" not in rows.columns:
        return {}
    frame = rows.copy()
    for column in ("trade_date", "as_of"):
        if column in frame.columns:
            frame = frame.sort_values(column)
            break
    codes = {name: int(code) for name, code in SECTOR_CODES.items()}
    labels = frame["gics_sector"].astype(str)
    return {
        str(ticker): codes[label]
        for ticker, label in zip(frame["ticker"], labels, strict=False)
        if label in codes
    }


def state_line(block: dict[str, Any] | None) -> str:
    """One line for the evening's email: whether the anchored block was built.

    A block that fails to build publishes a page that still looks complete - the
    nightly panels take its place - so the failure is invisible unless the message
    says it. `block()` returns `{}` when the frames cannot answer and `None` when it
    raised, and the two are different failures worth telling apart.
    """
    if block is None:
        return "not built: the block raised while it was being built"
    if not block:
        return "not built: the store had no anchor close to build from"
    anchor = (block.get("anchor") or {}).get("close")
    if not anchor:
        return "not built: the block carries no anchor"
    return f"built (anchor {anchor})"


def from_store(
    *,
    today: str,
    tonight_manifest: dict[str, Any] | None,
    nav: float | None,
    sector_of: dict[str, int] | None = None,
    guard_threshold: float | None = None,
) -> dict[str, Any] | None:
    """The block, read from the store: the one place the evening's frames come from.

    Read-only. Every read is the store's own table, so the page's numbers and the
    store's cannot disagree; a store that cannot answer gives `None`, which is the
    absent block rather than a failed evening.
    """
    from live import store

    try:
        return block(
            proposals=store.select("proposals"),
            targets=store.select("positions"),
            account=store.select("broker_positions"),
            orders=store.select("orders"),
            fills=store.select("fills"),
            today=today,
            reconciliation=store.select("reconciliation"),
            tonight_manifest=tonight_manifest,
            nav=nav,
            sector_of=sector_of,
            guard_threshold=guard_threshold,
        )
    except Exception as exc:  # noqa: BLE001 - reporting must never stop the evening
        logger.warning(
            "the anchored block could not be read from the store: %s: %s",
            type(exc).__name__,
            exc,
        )
        return None


def _block(
    *,
    proposals: pd.DataFrame,
    targets: pd.DataFrame,
    account: pd.DataFrame,
    orders: pd.DataFrame,
    fills: pd.DataFrame,
    today: str,
    tonight_manifest: dict[str, Any],
    reconciliation: pd.DataFrame | None = None,
    nav: float | None = None,
    guard_threshold: float | None = None,
    sector_of: dict[str, int] | None = None,
) -> dict[str, Any]:
    anchor, source = anchor_close(proposals)
    if anchor is None:
        return {}
    anchor_manifest = {}
    if proposals is not None and not proposals.empty:
        frame = proposals.copy()
        frame["trade_date"] = frame["trade_date"].astype(str).str.slice(0, 10)
        rows = frame.loc[frame["trade_date"] == anchor]
        if not rows.empty:
            anchor_manifest = _manifest_of(rows.iloc[-1].get("manifest"))

    target = _book(targets, anchor)
    before = _book(account, anchor)
    now_close = today
    if account is not None and not account.empty:
        days = sorted(set(account["trade_date"].astype(str).str.slice(0, 10)))
        now_close = days[-1] if days else today
    now = _book(account, now_close)
    guard_dates = _guard_events(proposals, anchor, today)
    bridge_anchor = bridge(target, before, now, orders, fills, anchor, guard_dates)
    # The names whose side the rebalance actually changed. On the 2026-10-26
    # re-trade evening every leg but these re-traded the rebalance's remainder;
    # only these can be its second legs.
    flip_tickers = {
        str(row.get("ticker")) for row in bridge_anchor.get("flip_rows") or []
    }

    cadence = tonight_manifest.get("cadence") or anchor_manifest.get("cadence") or {}
    guard = tonight_manifest.get("drift_guard") or {}
    _env_threshold = guard_threshold_from_env()

    since = (
        orders.loc[orders["trade_date"].astype(str).str.slice(0, 10) >= anchor]
        if orders is not None and not orders.empty
        else pd.DataFrame()
    )
    guard_days = _guard_days(proposals, anchor, today)
    trades: dict[str, dict[str, Any]] = {}
    not_sent: dict[str, Any] = {
        "legs": 0,
        "usd": 0.0,
        "under_minimum": {"legs": 0, "usd": 0.0},
        "other": {},
    }
    closed_on: dict[str, set[str]] = {}
    if not since.empty:
        frame = since.copy()
        frame["_close"] = frame["trade_date"].astype(str).str.slice(0, 10)
        frame = frame.sort_values(["_close", "ticker"], kind="stable")
        has_broker = "broker_order_id" in frame.columns
        for row in frame.itertuples(index=False):
            code = str(getattr(row, "reason_code", "") or "").strip()
            close = str(getattr(row, "trade_date", ""))[:10]
            ticker = str(getattr(row, "ticker", "") or "").strip()
            intent = str(getattr(row, "position_intent", "") or "").strip()
            usd = abs(_number(getattr(row, "intended_notional", None)) or 0.0)
            # A reason code is the durable record of a leg that never became an
            # order, so it is read for what happened to the leg and never as why
            # the leg was wanted: every refused leg carries one, and reading the
            # code as a reason is what made 315 legs the guard never sent look
            # like guard legs.
            refused = bool(code)
            sent = (
                bool(str(getattr(row, "broker_order_id", "") or "").strip())
                if has_broker
                else not refused
            )
            if intent.endswith("_to_close"):
                closed_on.setdefault(ticker, set()).add(close)
            if close == anchor:
                # The anchor evening's own table: 224 legs, of which 16 were under
                # the minimum and never sent. They are the rebalance's legs and stay
                # in its row, flagged unsent, because a reader who subtracts them
                # from the reason table and adds them to the not-sent line counts
                # the same dollars twice.
                reason = "rebalance"
            elif refused and code != "COVER_UNDER_ONE_SHARE":
                not_sent["legs"] += 1
                not_sent["usd"] += usd
                if code == "BELOW_MIN_NOTIONAL":
                    not_sent["under_minimum"]["legs"] += 1
                    not_sent["under_minimum"]["usd"] += usd
                else:
                    other = not_sent["other"].setdefault(
                        code or "UNCODED",
                        {"code": code or "UNCODED", "legs": 0, "usd": 0.0},
                    )
                    other["legs"] += 1
                    other["usd"] += usd
                continue
            elif code == "COVER_UNDER_ONE_SHARE":
                # Owed and impossible: the leg is under one share, so there is no
                # order to place at any price and retrying it never ends.
                reason = "carried leg"
            elif close in guard_days:
                # The day the guard fired decides it, not the leg's own intent: a
                # guard day closes and opens in the same evening, and every leg it
                # sent belongs to that evening's drift repair.
                reason = "guard"
            elif close in RETRADE_BUG_DAYS and not (
                ticker in flip_tickers and intent.endswith("_to_open")
            ):
                # The 2026-10-26 hold day re-traded eight legs of a rebalance that
                # had already filled, because the remainder it read was built from
                # filled_notional and saw the whole rebalance outstanding. The fix
                # landed on 2026-10-27; the legs it produced are not a remainder.
                # Every sent leg that evening is a re-trade except a name the
                # rebalance actually flipped: only a flip has a second leg to send.
                reason = RETRADE_BUG_DAYS[close]
            elif ticker in flip_tickers and intent.endswith("_to_open"):
                # A flip's second leg on a later close. CHTR is the case that made
                # this explicit: it had a close on an earlier day, so the old
                # close-then-open proxy called its 2026-10-26 open a second leg, but
                # its side did not change across the rebalance (long before, long
                # target), so that leg is a remainder re-trade, not a second leg.
                reason = "reversal second leg"
            elif intent.endswith("_to_open") and any(
                day < close for day in closed_on.get(ticker, set())
            ):
                # Outside a re-trade day the evidence of a reversal is the close
                # that went out on an earlier day; the 2026-11-05 legs that answer
                # the guard's own 2026-11-04 closes are second legs of that evening.
                reason = "reversal second leg"
            else:
                # A sent leg on a hold day that is neither a guard day nor the open
                # of a flip: a rebalance leg the account did not take on the anchor
                # day, sent again on the next close.
                reason = "rebalance remainder"
            item = trades.setdefault(
                reason,
                {
                    "reason": reason,
                    "legs": 0,
                    "usd": 0.0,
                    "sent_legs": 0,
                    "sent_usd": 0.0,
                },
            )
            item["legs"] += 1
            item["usd"] += usd
            if sent:
                item["sent_legs"] += 1
                item["sent_usd"] += usd

    unreachable = tonight_manifest.get("unfilled_unreachable") or []
    remainder = tonight_manifest.get("unfilled_remainder") or {}
    forced_usd = sum(abs(_number(v) or 0.0) for v in remainder.values()) + sum(
        abs(_number(item.get("unfilled_dollars")) or 0.0)
        for item in unreachable
        if isinstance(item, dict)
    )
    # Two different things, and until now one line said "1 forced leg, $269" for both:
    # a leg that is owed and will be sent on the next close, and a leg that is owed and
    # can never be sent - JBL's $269 on 2026-10-26 is under one share, so there is no
    # order to place and retrying it every close would be a loop that never ends.
    owed_usd = sum(abs(_number(value) or 0.0) for value in remainder.values())
    cannot_send: list[dict[str, Any]] = [
        {
            "ticker": str(item.get("ticker")),
            "usd": abs(_number(item.get("unfilled_dollars")) or 0.0),
            "code": str(item.get("reason_code") or ""),
        }
        for item in unreachable
        if isinstance(item, dict)
    ]
    cannot_send_usd = sum(float(item["usd"]) for item in cannot_send)
    out = {
        "anchor": {"close": anchor, "day": source, "account_read": now_close},
        "cadence_strip": {
            "day": cadence.get("day"),
            "k": cadence.get("k"),
            "offset": cadence.get("offset"),
            "sessions_since": cadence.get("sessions_since"),
            "last_rebalance": anchor,
            "next_rebalance": cadence.get("next_rebalance"),
            # The guard's own reading when it ran, and the book's worst exposure
            # when it did not: `exposure_before` is what the book carried going in,
            # and a guard that fired reports what it left as well.
            "guard": {
                "worst_abs_exposure": _number(
                    guard.get("exposure_before")
                    or tonight_manifest.get("max_abs_exposure_after_fmp")
                ),
                "exposure_after": _number(guard.get("exposure_after")),
                "threshold": (
                    _number(guard.get("threshold")) or guard_threshold or _env_threshold
                ),
                "fired": bool(guard.get("fired", False)),
                "ran": bool(guard),
                # The legs the guard actually sent: the candidates it could not size
                # (under the order minimum) are in the list too, and counting them
                # would say 196 for a night that sent 109.
                "legs": sum(
                    1
                    for leg in (guard.get("legs") or [])
                    if isinstance(leg, dict) and leg.get("traded")
                ),
                "legs_under_minimum": _count(guard.get("legs_under_minimum")),
            },
        },
        "rebalance_card": rebalance_card(anchor, anchor_manifest, orders, fills, nav),
        "bridge_anchor": bridge_anchor,
        # Tonight's own trading cost when it has one, and the anchor rebalance's
        # when it does not: a hold day's manifest prices only borrow, and pricing a
        # hypothetical rebalance at zero would say closing the drift is free.
        "drift": drift(
            target,
            now,
            nav,
            _trading_bps(tonight_manifest) or _trading_bps(anchor_manifest),
        ),
        "since_anchor": {
            "trades_by_reason": sorted(trades.values(), key=lambda item: -item["usd"]),
            # What the table cannot count as a leg that went: the legs under the
            # order minimum and the ones the broker refused. Stated apart because a
            # reader who adds them to the reasons is adding orders that do not exist.
            "not_sent": {
                "legs": not_sent["legs"],
                "usd": not_sent["usd"],
                "under_minimum": not_sent["under_minimum"],
                "other": sorted(
                    not_sent["other"].values(), key=lambda item: -item["usd"]
                ),
            },
        },
        "tonight": {
            "forced_legs": len(remainder) + len(unreachable),
            "forced_usd": forced_usd,
            # What will be sent, and what cannot be. The count of owed legs is the
            # remainder's: an unreachable leg is owed too, but it is not a leg that
            # will go out, and adding the two was what the line got wrong.
            "owed_legs": len(remainder),
            "owed_usd": owed_usd,
            "cannot_send_legs": len(cannot_send),
            "cannot_send_usd": cannot_send_usd,
            "cannot_send": cannot_send,
        },
        "rebalance_dates": sorted(
            {
                str(row["trade_date"])[:10]
                for row in (
                    proposals.to_dict("records")
                    if proposals is not None and not proposals.empty
                    else []
                )
                if str(
                    (_manifest_of(row.get("manifest")).get("cadence") or {}).get("day")
                )
                == REBALANCE
            }
        ),
    }
    # The same name-level gaps the drift card is made from, grouped by sector: on a
    # hold day the page's own sector panel compares the account with tonight's book,
    # which is the account, and reads eleven rows of +$0. Left out entirely when the
    # map or the NAV is missing, which is the page rendering as it did before.
    anchored = sectors(target, now, nav, sector_of, anchor=anchor)
    if anchored:
        out["sectors"] = anchored
    if not target.empty or not now.empty:
        out["holdings"] = holdings(
            target,
            before,
            now,
            orders,
            bridge_anchor.get("flip_rows") or [],
            guard_dates,
            guard_days,
            anchor,
            now_close,
            nav,
        )
    # The anchor close's own hedge, for the exposures panel: on a hold day tonight's
    # book is the account and nothing is hedged, so the only before/after pair that
    # says anything is the rebalance's. Absent when the anchor manifest carries no
    # vectors - a document written before the field existed renders as it did.
    anchor_before = anchor_manifest.get("exposures_before_hedge") or {}
    anchor_after = anchor_manifest.get("exposures_after_hedge") or {}
    if isinstance(anchor_before, dict) and isinstance(anchor_after, dict):
        if anchor_before and anchor_after:
            out["anchor_exposures"] = {
                "anchor": anchor,
                "before": anchor_before,
                "after": anchor_after,
            }
    card = rebalance_card(anchor, anchor_manifest, orders, fills, nav)
    footprint = hedge(
        target,
        reconciliation,
        anchor,
        nav,
        _number(card.get("notional")),
    )
    if footprint:
        out["hedge"] = footprint
    return out
