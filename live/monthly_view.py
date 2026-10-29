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

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

REBALANCE = "rebalance"
# The floor the sizing already uses: a position under it is a leg the book asked for
# and the account does not hold, which is a different statement from a name it never
# wanted.
MINIMUM_DOLLARS = 250.0


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
) -> tuple[float | None, str | None, str | None]:
    """One name's filled dollars on one close, that close, and the day it filled.

    The third value is the fill's own date, read from `efb.fills.updated_at`: the
    evening sends after the close and the fill lands at the next open, so a leg
    priced from the 2026-10-23 close filled on 2026-10-26. None when the store holds
    no fill row for it, which is not the same as a fill on the close's own date and
    the page labels the column for which of the two it is showing.
    """
    if orders is None or orders.empty:
        return None, None, None
    sub = orders.loc[
        (orders["ticker"].astype(str) == ticker)
        & (orders["trade_date"].astype(str).str.slice(0, 10) == close)
    ]
    if sub.empty:
        return None, None, None
    if fills is None or fills.empty:
        return None, None, None
    match = fills.loc[
        (fills["ticker"].astype(str) == ticker)
        & (fills["trade_date"].astype(str).str.slice(0, 10) == close)
    ]
    total = 0.0
    filled_at: str | None = None
    for row in sub.itertuples(index=False):
        intended = _number(getattr(row, "intended_notional", None)) or 0.0
        for fill in match.itertuples(index=False):
            if str(getattr(fill, "status", "")).upper() != "FILLED":
                continue
            amount = _number(getattr(fill, "filled_notional", None)) or 0.0
            total += amount if intended >= 0 else -amount
            stamp = getattr(fill, "updated_at", None)
            day = _day(stamp)
            if day and (filled_at is None or day < filled_at):
                filled_at = day
    # The dollars are the evidence that it filled; the timestamp is what says when.
    # A fill row without one still means the leg is filled, and its close date is the
    # honest answer to "which day", marked as the close rather than as the fill.
    return total, close, filled_at


def flip_rows(
    target: pd.DataFrame,
    before: pd.DataFrame,
    now: pd.DataFrame,
    orders: pd.DataFrame,
    fills: pd.DataFrame,
    anchor: str,
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
        close_leg, close_leg_day, close_leg_filled = _leg_dollars(
            orders, fills, ticker, anchor
        )
        open_leg = open_day = open_filled = None
        later = (
            orders.loc[orders["trade_date"].astype(str).str.slice(0, 10) > anchor]
            if orders is not None and not orders.empty
            else pd.DataFrame()
        )
        for day in sorted(later["trade_date"].astype(str).str.slice(0, 10).unique()):
            open_leg, open_day, open_filled = _leg_dollars(orders, fills, ticker, day)
            if open_leg is not None:
                break
        lying = now_side.get(ticker)
        dollars = now_dollars.get(ticker, 0.0)
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
                "complete": lying == wanted and abs(dollars) > MINIMUM_DOLLARS,
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
) -> dict[str, Any]:
    """The account before the rebalance, what the rebalance did, and the account now."""
    before_dollars = _dollars(before)
    now_dollars = _dollars(now)
    target_side = _sides(target)
    flips = flip_rows(target, before, now, orders, fills, anchor)
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
    wanted = {
        str(ticker): float(weight)
        for ticker, weight in zip(
            target["ticker"],
            pd.to_numeric(target["weight"], errors="coerce"),
            strict=False,
        )
        if weight is not None and not pd.isna(weight)
    }
    have: dict[str, float] = {}
    if now is not None and not now.empty and "weight" in now.columns:
        have = {
            str(ticker): float(weight)
            for ticker, weight in zip(
                now["ticker"],
                pd.to_numeric(now["weight"], errors="coerce"),
                strict=False,
            )
            if weight is not None and not pd.isna(weight)
        }
    names = set(wanted) | set(have)
    gaps = {ticker: have.get(ticker, 0.0) - wanted.get(ticker, 0.0) for ticker in names}
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
    tonight_manifest: dict[str, Any] | None = None,
    nav: float | None = None,
    guard_threshold: float | None = None,
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
            tonight_manifest=tonight_manifest or {},
            nav=nav,
            guard_threshold=guard_threshold,
        )
    except Exception as exc:  # noqa: BLE001 - reporting must never stop the evening
        logger.warning(
            "the anchored block was not built: %s: %s", type(exc).__name__, exc
        )
        return None


def from_store(
    *, today: str, tonight_manifest: dict[str, Any] | None, nav: float | None
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
            tonight_manifest=tonight_manifest,
            nav=nav,
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
    nav: float | None,
    guard_threshold: float | None = None,
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

    cadence = tonight_manifest.get("cadence") or anchor_manifest.get("cadence") or {}
    guard = tonight_manifest.get("drift_guard") or {}
    _env_threshold = guard_threshold_from_env()

    since = (
        orders.loc[orders["trade_date"].astype(str).str.slice(0, 10) >= anchor]
        if orders is not None and not orders.empty
        else pd.DataFrame()
    )
    trades: dict[str, dict[str, Any]] = {}
    if not since.empty:
        for row in since.itertuples(index=False):
            code = str(getattr(row, "reason_code", "") or "")
            close = str(getattr(row, "trade_date", ""))[:10]
            intent = str(getattr(row, "position_intent", "") or "")
            if close == anchor:
                reason = "rebalance"
            elif code:
                reason = {
                    "COVER_UNDER_ONE_SHARE": "carried leg",
                    "BELOW_MIN_NOTIONAL": "guard",
                }.get(code, "guard")
            elif intent.endswith("_to_open") or intent.endswith("_to_close"):
                reason = "reversal second leg"
            else:
                reason = "hold day"
            item = trades.setdefault(reason, {"reason": reason, "legs": 0, "usd": 0.0})
            item["legs"] += 1
            item["usd"] += abs(_number(getattr(row, "intended_notional", None)) or 0.0)

    unreachable = tonight_manifest.get("unfilled_unreachable") or []
    remainder = tonight_manifest.get("unfilled_remainder") or {}
    forced_usd = sum(abs(_number(v) or 0.0) for v in remainder.values()) + sum(
        abs(_number(item.get("unfilled_dollars")) or 0.0)
        for item in unreachable
        if isinstance(item, dict)
    )
    return {
        "anchor": {"close": anchor, "day": source, "account_read": now_close},
        "cadence_strip": {
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
            },
        },
        "rebalance_card": rebalance_card(anchor, anchor_manifest, orders, fills, nav),
        "bridge_anchor": bridge(target, before, now, orders, fills, anchor),
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
            "trades_by_reason": sorted(trades.values(), key=lambda item: -item["usd"])
        },
        "tonight": {
            "forced_legs": len(remainder) + len(unreachable),
            "forced_usd": forced_usd,
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
