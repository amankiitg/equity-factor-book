"""Sprint E11: what the broker did with the orders the loop sent.

The evening sends market orders after the close and does not wait for them. A
DAY order submitted at 18:30 New York fills at the next open, so the evening's
own record of a leg says `ACCEPTED` and nothing more, and `reconciliation.
filled_notional` has been about zero every evening for exactly that reason. What
the loop actually holds is therefore unknown until the next morning, when each
order can be read back from the broker and asked for its filled quantity, its
average fill price, its final status and, if it was cancelled, when.

The read is by `broker_order_id`, never by the deterministic client ticket. The
broker keeps a client order id for the orders it accepted, so the legs the loop
refused at the guard, the shorts it refused for borrow and the legs under the
minimum size would all read as "no such order" through the ticket and be
indistinguishable from an order that never arrived. The id the evening recorded
is the broker's own, and a leg without one was never sent, which is a different
statement from an order that did not fill.

Nothing here can size a book or send an order. The module reads the broker layer
for its enum helper and nothing else, every function takes the frames it is given
rather than reading the store or the tree, and the only writer is the caller.
That is what the cron's own test pins: the job runs to completion against a
client whose `submit_order` raises.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from live import alpaca

# The statuses an order can be in when it is still working at the broker, which is
# what the reconciler must not mistake for a miss: a DAY order from the previous
# evening is out of this set by the next morning because it fills at the 09:30 New
# York open, which is why the job runs at 15:30 UTC (after that open in EST and
# EDT alike) rather than at 14:00 UTC (after it only in EDT). A leg still in this
# set is reported with its status word, and its `cancel_time` is null because it
# has not been cancelled.
WORKING = (
    "NEW",
    "ACCEPTED",
    "PENDING_NEW",
    "ACCEPTED_FOR_BIDDING",
    "HELD",
    "REPLACED",
)
FILLED = "FILLED"
PARTIALLY_FILLED = "PARTIALLY_FILLED"
CANCELED = "CANCELED"
EXPIRED = "EXPIRED"
REJECTED = "REJECTED"

# The status a leg that was never submitted carries in `orders`, and the codes
# that say why. A reconciler has no order to ask the broker about for any of
# these, so they are counted rather than looked up.
SKIPPED = alpaca.SKIPPED

# Which of the two runs read the account, for `actual_holdings.read_by`. The two
# read the same account at different points of one trade: the evening reads it
# before it sizes, so no order has settled into the book it read, and the morning
# reads it to say what those orders did. The page labels the section with this
# rather than inferring it from whether a fills block is present, because an
# evening read is not an evening whose orders all filled.
READ_EVENING = "evening"
READ_MORNING = "morning"

FILL_COLUMNS: tuple[str, ...] = (
    "trade_date",
    "ticker",
    "order_id",
    "intended_notional",
    "filled_notional",
    "fill_price",
    "filled_quantity",
    "status",
    "cancel_time",
    "submitted_at",
    "updated_at",
    "position_intent",
    "close_price",
    "slippage_bps",
)


def order_status(order: Any) -> str:
    """The broker's status word, upper case, as a plain string.

    `alpaca.enum_value` is what makes this readable at all: the status is an
    `OrderStatus` enum, and `str()` on it yields the class and the member rather
    than the word the broker used.
    """
    return str(alpaca.enum_value(getattr(order, "status", "")) or "").upper()


def _number(value: Any) -> float | None:
    """A broker text-or-number field as a float, or None when it is absent."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) else None


def filled_quantity(order: Any) -> float:
    """Shares the broker has filled on this order, zero when it says nothing."""
    return _number(getattr(order, "filled_qty", None)) or 0.0


def fill_price(order: Any) -> float | None:
    """The broker's average fill price, or None when there is no fill."""
    return _number(getattr(order, "filled_avg_price", None))


def side_sign(order: Any) -> float:
    """+1 for a buy, -1 for a sell.

    The sign is the broker's own side rather than a re-derivation from the
    position intent, so a close that bought to cover and a short that sold to
    open both answer about the trade that actually happened.
    """
    side = str(alpaca.enum_value(getattr(order, "side", "")) or "").lower()
    return -1.0 if side == "sell" else 1.0


def _stamp(value: Any) -> pd.Timestamp | None:
    if value is None or value == "":
        return None
    stamp = pd.Timestamp(value)
    return None if pd.isna(stamp) else stamp


def _iso(value: Any) -> str | None:
    stamp = _stamp(value)
    return None if stamp is None else stamp.isoformat()


def clock_word(value: Any) -> str:
    """A wall clock time as the message writes it: `12:15 UTC`, or an empty string.

    The broker answers in UTC and the message is read in New York, so the zone is
    said out loud rather than left for the reader to work out. Nothing localises
    here: an evening whose orders are still open would otherwise print a time
    that reads as this morning's.
    """
    stamp = _stamp(value)
    if stamp is None:
        return ""
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("UTC")
    return f"{stamp.strftime('%H:%M')} UTC"


def size_word(order: Any) -> str:
    """The leg's own size as the message writes it: whole shares, or dollars.

    A short and a close are sent as a share count and a `buy_to_open` as a
    notional, so the order the broker holds is the only place the intended size
    of either is written down.
    """
    quantity = _number(getattr(order, "qty", None))
    if quantity:
        return f"{quantity:.0f}" if float(quantity).is_integer() else f"{quantity:g}"
    notional = _number(getattr(order, "notional", None))
    return "" if notional is None else f"${notional:,.0f}"


def unfilled_line(ticker: str, order: Any) -> str:
    """One message line for an order that did not fill: the reason, with its time.

    The shape is the one the owner asked for, `DG sell_to_open 41 canceled 12:15
    UTC`: the name, the broker's own intent, the intended size, the status in
    words and the instant it reached that status, which for a cancellation is
    the cancellation and otherwise is the broker's last update.

    A rejected order is dated by `failed_at`. That is the only field the broker
    fills in for one, and the reason it carries is exactly the one Alpaca does not
    persist: an order rejected at the open says `rejected 08:00 UTC` and nothing
    more, which is why this line is where the derived reason is written down - it
    is the record, and no column holds it.
    """
    status = order_status(order)
    when = clock_word(
        getattr(order, "canceled_at", None)
        or getattr(order, "failed_at", None)
        or getattr(order, "updated_at", None)
    )
    fields = [
        str(ticker),
        str(alpaca.enum_value(getattr(order, "position_intent", "")) or "").lower(),
        size_word(order),
        status.lower().replace("_", " "),
        when,
    ]
    return " ".join(field for field in fields if field)


def not_sent_line(ticker: str, reason_code: str, notional: float, intent: str) -> str:
    """One line for a leg the evening never sent, with the reason it was not sent.

    A leg the evening decided against did not fill either, and the morning's line
    is about what did not happen: leaving it out reported nine legs where the book
    had ten and said nothing about the tenth. The reason is derived rather than
    read, because the broker never saw the order and has no record of it - a ticker
    whose asset the broker's feed does not carry says `symbol_not_found` - and the
    size is the leg's own intended notional, which is the only size an order that
    was never sent has.
    """
    fields = [
        str(ticker),
        str(intent or "").lower(),
        f"${abs(float(notional or 0.0)):,.0f}",
        "never sent",
        f"({reason_code})" if reason_code else "",
    ]
    return " ".join(field for field in fields if field)


def read_orders(
    rows: pd.DataFrame, client: Any, *, read: Any = None
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Every submitted order, read back from the broker by its own id.

    Returns the orders by id and the ones that could not be read, which are
    reported rather than treated as unfilled: an order the broker will not answer
    about is a question to answer, not a leg that did not happen. A leg with no
    `broker_order_id` was never sent and is not asked about at all.
    """
    reader = read or alpaca.read_order
    orders: dict[str, Any] = {}
    unread: list[dict[str, str]] = []
    for row in rows.itertuples(index=False):
        order_id = str(getattr(row, "broker_order_id", "") or "")
        if not order_id:
            continue
        try:
            orders[order_id] = reader(client, order_id)
        except Exception as exc:  # noqa: BLE001 - reported, never fatal
            unread.append(
                {
                    "ticker": str(row.ticker),
                    "order_id": order_id,
                    "error": type(exc).__name__,
                }
            )
    return orders, unread


def slippage_bps(order: Any, close: float | None) -> float | None:
    """What the fill cost against the close the book was sized from, in bp.

    Positive is a cost, which is how the expected side is signed: a buy filled
    above the close and a sell filled below it both paid. The close is the price
    the decision was made at, so this is the execution's own contribution and not
    the day's market move, which the book carries anyway.
    """
    price = fill_price(order)
    if price is None or close is None or not close:
        return None
    return 1e4 * side_sign(order) * (price - float(close)) / float(close)


def facts_rows(
    rows: pd.DataFrame,
    orders: dict[str, Any],
    *,
    closes: pd.Series | None = None,
    trade_date: Any = None,
) -> pd.DataFrame:
    """One `efb.fills` row per submitted leg, in the order the evening recorded them.

    A leg the broker has no record for is left out rather than written with a
    guessed status: `read_orders` has already listed it as unread, and a row that
    says "nothing happened" about an order nobody can see is the one answer that
    cannot be checked later.
    """
    close_of = {} if closes is None else closes.to_dict()
    records: list[dict[str, Any]] = []
    for row in rows.itertuples(index=False):
        order_id = str(getattr(row, "broker_order_id", "") or "")
        order = orders.get(order_id)
        if order is None:
            continue
        ticker = str(row.ticker)
        close = _number(close_of.get(ticker))
        quantity = filled_quantity(order)
        price = fill_price(order)
        # The table's four original columns are NOT NULL, and a leg with no fill
        # is written as zero rather than as null: that is the same convention
        # `Fill` uses for a leg the broker never filled, and it keeps "no fill"
        # from reading as "the field was not collected".
        records.append(
            {
                "trade_date": trade_date if trade_date is not None else row.trade_date,
                "ticker": ticker,
                "order_id": order_id,
                "intended_notional": _number(getattr(row, "intended_notional", None))
                or 0.0,
                "filled_notional": 0.0 if price is None else abs(quantity * price),
                "fill_price": 0.0 if price is None else price,
                "filled_quantity": quantity,
                "status": order_status(order),
                "cancel_time": _iso(getattr(order, "canceled_at", None)),
                "submitted_at": _iso(getattr(order, "submitted_at", None)),
                "updated_at": _iso(getattr(order, "updated_at", None)),
                "position_intent": str(
                    alpaca.enum_value(getattr(order, "position_intent", "")) or ""
                ),
                "close_price": close,
                "slippage_bps": slippage_bps(order, close),
            }
        )
    return pd.DataFrame(records, columns=list(FILL_COLUMNS))


def miss_statuses(fills: pd.DataFrame) -> dict[str, int]:
    """How many legs missed, by the broker's own status word.

    A count alone cannot say "2 rejected" from "2 canceled", and the morning
    message's inbox line has to: a cancellation is a working order the broker took
    back and a rejection is an order that never worked, which are two different
    things to go and look at. Empty when every leg filled, which is what a morning
    that only had a page write to report sends.
    """
    if fills.empty or "status" not in fills.columns:
        return {}
    missed = fills.loc[fills["status"].astype(str) != FILLED, "status"].astype(str)
    counts = missed.value_counts()
    # Sorted by count then status word so two mornings with the same legs produce
    # the same sentence rather than one that depends on the frame's row order.
    ranked = sorted(counts.items(), key=lambda item: (-int(item[1]), str(item[0])))
    return {str(word): int(count) for word, count in ranked}


def unfilled_lines(fills: pd.DataFrame, orders: dict[str, Any]) -> list[str]:
    """One line per leg that is not filled, in the order the book lists them.

    A partial fill is reported as well as a cancellation: the owner's question is
    what the account did not do, and half an order is half an order. A leg that
    filled is silent, because the summary line already carries the count.
    """
    lines: list[str] = []
    for row in fills.itertuples(index=False):
        if str(row.status) == FILLED:
            continue
        order = orders.get(str(row.order_id))
        if order is None:
            continue
        lines.append(unfilled_line(str(row.ticker), order))
    return lines


def never_sent_lines(rows: pd.DataFrame) -> list[str]:
    """One line per leg the evening could not send at all, with the derived reason.

    Read from the evening's own order rows rather than from the fills frame: a leg
    that was never sent has no broker order to read back, and its reason exists
    only in the record the evening wrote. A leg the broker already held from a
    rerun is not one of these - it was sent, just not twice - so the test is the
    absence of a broker id, which is the same predicate the fill reconciliation
    uses.

    Only the legs the broker could not have traded under any spelling are listed,
    which is `symbol_not_found`. The evening's other never-sent legs are its own
    decisions and it has already named them - the $250 minimum, the borrow it could
    not get, the halt it stopped on - and repeating them here would say the
    morning had found something new about a leg whose reason was already reported.
    """
    if rows.empty or "broker_order_id" not in rows.columns:
        return []
    unsent = rows.loc[
        (rows["broker_order_id"].astype(str).str.len() == 0)
        & (
            rows.get("reason_code", pd.Series(dtype=str)).astype(str)
            == alpaca.REASON_SYMBOL_NOT_FOUND
        )
    ]
    return [
        not_sent_line(
            str(row.ticker),
            str(getattr(row, "reason_code", "") or ""),
            float(getattr(row, "intended_notional", 0.0) or 0.0),
            str(getattr(row, "position_intent", "") or ""),
        )
        for row in unsent.itertuples(index=False)
    ]


def realized_cost_bps(fills: pd.DataFrame, nav: float | None) -> float | None:
    """The fills' own cost against the close, in bp of NAV, or None.

    Summed in dollars and divided by the NAV once, rather than averaged over the
    legs: a 40 bp miss on a name that traded $1,000 is not the same event as 40 bp
    on the largest leg of the book, and the expected cost it is compared against
    is a share of NAV in the same way. None when no leg has both a fill and a
    close, which is the honest answer for an evening nothing filled on.
    """
    if fills.empty or not nav:
        return None
    priced = fills.loc[fills["slippage_bps"].notna() & fills["filled_quantity"].notna()]
    if priced.empty:
        return None
    # Only the legs that have both a fill and a close are summed. A leg with no
    # close is left out rather than counted as free, and the count of legs behind
    # the number is on the row beside it.
    block = priced.loc[:, ["slippage_bps", "close_price", "filled_quantity"]].astype(
        float
    )
    dollars = float(
        (block["slippage_bps"] * block["close_price"] * block["filled_quantity"]).sum()
    )
    return 1e4 * dollars * 1e-4 / float(nav)


def actual_holdings(
    notional: dict[str, float] | None,
    nav: float | None,
    *,
    as_of: Any = None,
    close: Any = None,
    report: dict[str, Any] | None = None,
    expected_cost_bps: float | None = None,
    read_by: str | None = None,
    exits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The account's own book, and the fills that produced it, for the snapshot.

    The target book the page draws comes from the manifest; this is the other
    half of the same evening, what the account actually holds, so the two can be
    read against each other. Weights are of the account's own equity, the same
    denominator the sizing uses, and the names are ordered by absolute notional
    so the section reads in the same order as the book above it.

    The fills block is dated with the close whose orders settled rather than with
    the morning the account was read: the realized cost belongs to that trade, and
    a section that showed it beside a book from another day would be comparing two
    days' numbers in one line.

    `read_by` says which of the two runs read the account, because the two read it
    at different points of the same trade and only one of them can have fills: the
    evening reads it before it sizes and sends, so nothing has settled into the
    book it read and `close` and `report` are both absent; the morning reads it to
    say what the evening's orders did. Without the label the page would have to
    infer which it was holding, and a book read before the orders is not a book the
    orders produced.
    """
    prices = {str(ticker): float(value) for ticker, value in (notional or {}).items()}
    ordered = sorted(prices.items(), key=lambda item: abs(item[1]), reverse=True)
    scale = float(nav) if nav else None
    names = [
        {
            "ticker": ticker,
            "side": "long" if value >= 0 else "short",
            "notional": value,
            "weight": (value / scale) if scale else None,
        }
        for ticker, value in ordered
    ]
    total = float(sum(prices.values()))
    block: dict[str, Any] = {
        "as_of": None if as_of is None else str(as_of),
        "close": None if close is None else str(close),
        "read_by": read_by,
        "n_names": len(names),
        "gross_notional": float(sum(abs(value) for value in prices.values())),
        "net_notional": total,
        "names": names,
        "fills": None,
    }
    if report is not None:
        block["fills"] = {
            "trade_date": report.get("trade_date"),
            "n_orders": report.get("n_orders"),
            "n_filled": report.get("n_filled"),
            "n_unfilled": report.get("n_unfilled"),
            "not_sent": report.get("not_sent"),
            "realized_cost_bps": report.get("realized_cost_bps"),
            "expected_cost_bps": expected_cost_bps,
            "unfilled": list(report.get("unfilled") or []),
            "not_sent_lines": list(report.get("not_sent_lines") or []),
            "unread": list(report.get("unread") or []),
        }
    if exits is not None:
        # The names the account held when it was last read and does not hold now,
        # with nothing the loop did to explain them. It travels with the account
        # rather than with the fills because it is a fact about the book in hand:
        # the page draws them beside the holdings, where a reader looking for a
        # name that is gone will actually see them.
        block["exits"] = {
            "previous_read": exits.get("previous_read"),
            "feed": exits.get("feed"),
            "window": exits.get("window"),
            "names": [
                {
                    "ticker": str(item.get("ticker")),
                    "quantity": float(item.get("quantity") or 0.0),
                    "notional": float(item.get("notional") or 0.0),
                }
                for item in (exits.get("exits") or [])
            ],
        }
    return block


def reconcile_day(
    orders: pd.DataFrame,
    client: Any,
    *,
    closes: pd.Series | None = None,
    nav: float | None = None,
    read: Any = None,
) -> dict[str, Any]:
    """Everything the morning after knows about one evening's orders.

    `orders` is the evening's own rows for that close, which is the only record
    of what was intended, of which legs were sent and of the broker's id for
    each. The returned dictionary is what the caller writes and messages: the
    fills frame, the legs that did not fill with a line each, the ones the broker
    could not be asked about, the trades that were never sent, and the realized
    cost beside the count of orders.
    """
    submitted = orders.loc[orders["broker_order_id"].astype(str).str.len() > 0]
    broker_orders, unread = read_orders(submitted, client, read=read)
    trade_date = (
        str(orders["trade_date"].max())[:10] if "trade_date" in orders.columns else None
    )
    fills = facts_rows(submitted, broker_orders, closes=closes, trade_date=trade_date)
    unmoved = orders.loc[orders["broker_order_id"].astype(str).str.len() == 0]
    return {
        "fills": fills,
        "orders": broker_orders,
        "unfilled": unfilled_lines(fills, broker_orders),
        # The legs the evening never sent, with their derived reasons. They are
        # not broker misses and are not counted as ones; they are the rest of what
        # did not happen, and the morning's line names them for that reason.
        "not_sent_lines": never_sent_lines(orders),
        "unread": unread,
        "not_sent": int(len(unmoved)),
        "n_orders": int(len(submitted)),
        "n_filled": int((fills["status"] == FILLED).sum()) if len(fills) else 0,
        "n_unfilled": (
            int(len(fills) - (fills["status"] == FILLED).sum()) if len(fills) else 0
        ),
        "miss_statuses": miss_statuses(fills),
        "realized_cost_bps": realized_cost_bps(fills, nav),
        "trade_date": trade_date,
    }
