"""The book bridge: how 201 names became 199 orders and then 188 positions.

The page shows three sets side by side - the book the model sized, the orders the
run sent and the positions the account holds - and each is correct, but nothing on
the page connects them. 191 names, 199 orders and 188 positions read as three
disagreements rather than as one evening's arithmetic, and the reader is left to
reconstruct which names were opened, which were closed, which merely moved and
which never traded at all.

This is that arithmetic, as one block of counts:

    held before trading (the evening's account read)        201
    in both held-before and the new book                    159
    + opened (in the book, not held before)                  32
    - exited (held before, not in the book)                  42
    continuing names changed by >= $250 (an order sent)      125
    continuing names changed by < $250 (never sent)           34
    orders sent = changed + opened + exited                  199
    filled / did not fill                                 197 / 2
    held after (the morning's account read)                  188

and, when the two do not agree, the names the gap is made of: a reversal the run
closed tonight and reopens tomorrow, a position that left the account with no order
behind it, or a name in neither list, which is the case that fails the bridge.

Every identity in it is a check rather than a decoration, and a block published with
a broken one says so:

    in_both + opened = book                 both + exited = held_before
    changed + under_minimum = in_both       changed + opened + exited = orders_sent
    orders_sent = filled + did_not_fill
    held_before - exited + opened - the reversals and removals = held_after

That last pair is the reason to compute the arithmetic instead of drawing three
numbers: a book that moved 201 names into 188 without a story is a finding, and the
page shows it in amber with the two figures that disagree.

Two writers fill it. The evening knows the first half - what it read, what it sized,
what it sent, what it closed to reopen - and the morning knows the second: what
filled, what the account holds now, and which names the difference is made of. Each
half is computed from the run's own record and published in the snapshot, so the
page recomputes none of it and the two runs cannot disagree about a count.
"""

from __future__ import annotations

from typing import Any

from live import alpaca

# The size below which a continuing name is left untraded: the line between the two
# ends of the bridge. A name whose change is at least this much was worth an order,
# and a name under it is the leg the run decided against.
UNDER_MINIMUM_USD = alpaca.DELTA_MIN_NOTIONAL


def _tickers(names: Any) -> set[str]:
    """A collection of tickers as a set of upper-case names, blanks dropped."""
    out: set[str] = set()
    for name in names or ():
        text = str(name).strip().upper()
        if text:
            out.add(text)
    return out


def _leg_sets(orders: Any) -> tuple[set[str], dict[str, str]]:
    """(tickers with a leg that was sent, ticker -> reason for the ones that were not).

    Read from the run's own order rows, which are the only record of what it built:
    a leg with a broker id was sent, and a leg without one is one the run decided
    against - the $250 minimum, a borrow it could not get, a ticker the broker's feed
    does not carry. Both are legs of the evening, and the bridge counts the first as
    trading and the second as not trading, never as a name that did not exist.
    """
    sent: set[str] = set()
    skipped: dict[str, str] = {}
    if getattr(orders, "itertuples", None) is None:
        return sent, skipped
    for row in orders.itertuples(index=False):
        ticker = str(getattr(row, "ticker", "") or "").strip().upper()
        if not ticker:
            continue
        if str(getattr(row, "broker_order_id", "") or "").strip():
            sent.add(ticker)
        else:
            skipped[ticker] = str(getattr(row, "reason_code", "") or "")
    return sent, skipped


def evening(
    *,
    close: str,
    held_before: Any,
    book: Any,
    orders: Any,
    reversals: Any = (),
) -> dict[str, Any]:
    """The evening's half of the bridge, from the run's own read and its own legs.

    `held_before` is the account as this run read it, `book` is the book it is
    publishing, `orders` are its leg records for the close, and `reversals` are the
    targets it deferred - closed tonight and reopened tomorrow - which the morning
    needs to explain part of the gap. The fills and the account after the orders are
    the morning's to add; until then `held_after` is null rather than zero, because a
    zero would read as an account holding nothing.
    """
    held = _tickers(held_before)
    sized = _tickers(book)
    both = held & sized
    sent, skipped = _leg_sets(orders)
    block: dict[str, Any] = {
        "close": str(close)[:10],
        "seen_by": "evening",
        # The book's own size, carried so the count can be checked against the list
        # the page draws rather than trusted: the bridge's middle number is the book,
        # and a bridge whose book disagrees with the published one is a bridge about a
        # different evening.
        "book": len(sized),
        "held_before": len(held),
        "in_both": len(both),
        "opened": len(sized - held),
        "exited": len(held - sized),
        "changed": len(both & sent),
        "under_minimum": len(both - sent),
        "orders_sent": len(sent),
        "filled": None,
        "did_not_fill": None,
        "held_after": None,
        "reversals_pending": sorted(_tickers(reversals)),
        "removed_without_order": [],
        "unexplained": [],
        "unread": 0,
        "skipped_reasons": _reason_counts(skipped),
        "under_minimum_usd": float(UNDER_MINIMUM_USD),
    }
    return _checked(block)


def completed(
    evening_block: dict[str, Any] | None,
    *,
    filled: int,
    did_not_fill: int,
    held_after: Any,
    book: Any,
    removed: Any = (),
    reversals: Any = (),
    unread: int = 0,
) -> dict[str, Any]:
    """The morning's half: the fills, the account now, and the names in the gap.

    The gap is `book` less `held_after`, itemised by what explains each name: a
    reversal the evening closed in order to reopen the other side, a position that
    left with no order behind it, or - the case the bridge exists to catch - neither,
    which is a name the loop believes it holds and the account does not. An empty
    evening block completes to nothing: a morning with no bridge to complete has no
    arithmetic to state, and an invented one would describe an evening nobody ran.
    """
    block = dict(evening_block or {})
    if not block:
        return {}
    pending = _tickers(block.get("reversals_pending")) | _tickers(reversals)
    gone = [
        {
            "ticker": str(item.get("ticker")),
            "quantity": _number(item.get("quantity")),
            "notional": _number(item.get("notional")),
        }
        for item in (removed or ())
        if isinstance(item, dict) and item.get("ticker")
    ]
    removed_now = _tickers(item["ticker"] for item in gone)
    after = _tickers(held_after)
    gap = sorted(_tickers(book) - after)
    block.update(
        {
            "seen_by": "morning",
            "book": len(_tickers(book)) or int(block.get("book") or 0),
            "filled": int(filled),
            "did_not_fill": int(did_not_fill),
            "held_after": len(after),
            "unread": int(unread),
            "reversals_pending": sorted(pending),
            "removed_without_order": gone,
            "unexplained": [
                name for name in gap if name not in pending and name not in removed_now
            ],
        }
    )
    return _checked(block)


def gap_names(block: dict[str, Any]) -> list[str]:
    """The names the book has and the account does not, in the order the page lists."""
    names: list[str] = []
    for key in ("reversals_pending", "removed_without_order", "unexplained"):
        for item in block.get(key) or ():
            names.append(
                str(item.get("ticker")) if isinstance(item, dict) else str(item)
            )
    return sorted(names)


def identities(block: dict[str, Any]) -> list[dict[str, Any]]:
    """Every identity the block claims, with both sides and whether each holds.

    The three that need the morning's figures are checked only once it has
    published: an evening block has no fills and no account after, and a check whose
    right-hand side is unknown must not read as a failure. Each check names both of
    its sides in words, so a reader who sees one fail on the page can see which
    number is wrong rather than only that something is.
    """

    def count(key: str) -> int:
        value = block.get(key)
        return int(value) if isinstance(value, (int, float)) else 0

    checks = [
        _identity(
            "in both + opened = the book",
            count("in_both") + count("opened"),
            count("book"),
        ),
        _identity(
            "in both + exited = held before trading",
            count("in_both") + count("exited"),
            count("held_before"),
        ),
        _identity(
            "changed + under the minimum = in both",
            count("changed") + count("under_minimum"),
            count("in_both"),
        ),
        _identity(
            "changed + opened + exited = orders sent",
            count("changed") + count("opened") + count("exited"),
            count("orders_sent"),
        ),
    ]
    if block.get("held_after") is not None:
        checks.append(
            _identity(
                "orders sent = filled + did not fill",
                count("orders_sent"),
                count("filled") + count("did_not_fill") + count("unread"),
            )
        )
        # The gap counts the two kinds the loop can account for and *only* those:
        # a name in neither list is a name the loop believes it holds and the account
        # does not, so it fails the identity rather than being folded into it. That
        # is the check the bridge exists for - an unrelated disappearance, the PSKY
        # case before Part B named it - and a check that counted its own leftovers
        # could never fail.
        checks.append(
            _identity(
                "held before - exited + opened - reversals and removals = held after",
                count("held_before") - count("exited") + count("opened"),
                count("held_after")
                + len(block.get("reversals_pending") or ())
                + len(block.get("removed_without_order") or ()),
            )
        )
    return checks


def _reason_counts(skipped: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for reason in skipped.values():
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _identity(name: str, left: int, right: int) -> dict[str, Any]:
    return {
        "name": name,
        "left": int(left),
        "right": int(right),
        "holds": left == right,
    }


def _checked(block: dict[str, Any]) -> dict[str, Any]:
    """The block with its identities computed and its own verdict on them."""
    checks = identities(block)
    out = dict(block)
    out["identities"] = checks
    out["holds"] = all(item["holds"] for item in checks)
    return out
