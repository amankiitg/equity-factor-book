"""Sprint E11 pre-flip, item 6: what the broker holds against what the loop thinks.

Before this, the evening's traded legs were measured against the store's own
position row: the loop's record of what it meant to hold. In dry run that record
is built from intended targets that were never sent, so on the evening of the flip
the store would have said the account held a 150-name book while the paper account
held nothing, and every traded leg would have been wrong in the same direction.

So the account is read, every evening, before the orders are built. The read is
free and read-only, which is why it happens in dry run too: "what does the broker
hold" has a real answer before the flip, and the first live evening should not be
the first time it is asked.

Where the two disagree, the disagreement is reported rather than resolved. Nothing
here writes: the broker's book and the store's book are both stated, with the
names that are only in one of them, and the email carries the sentence.

The account itself is checked before anything is sized. The keys are named: every
run compares the account number Alpaca reports against `EFB_ALPACA_ACCOUNT_ID`, and
a run whose keys reach another account refuses, because a key pasted from the
credit lab's project would trade the wrong book and every number after it would be
about somebody else's account. An establishment evening is refused unless the
account is both flat and idle: establishing the whole book over an order that is
still working at the broker would buy names the account is already buying.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import pandas as pd

from live import store

logger = logging.getLogger(__name__)

# One dollar: both sides are dollar notions rounded to the cent by the time they
# are compared, so anything above a dollar is a real difference rather than
# arithmetic noise.
TOLERANCE_USD = 1.0

BROKER_SOURCE = "alpaca paper account"
STORE_SOURCE = "store"


class AccountRefused(RuntimeError):
    """The account is not in the state the run assumes, so the run stopped."""


def store_positions(before: str | None = None) -> tuple[dict[str, float], str]:
    """The loop's own record of the book, and which row it came from.

    `before` is the close this run is pricing. The store's row for that close is
    tonight's target, written by the evening before any order was sent, and
    comparing the account against it asks the account to match a book nobody has
    traded yet: on the first live evening it reported 150 names missing at the
    broker that the run was about to buy. The book to compare against is the last
    one the loop actually held, which is the most recent row strictly before this
    close.
    """
    frame = store.select("positions")
    if frame.empty:
        return {}, "the store holds no position row"
    if before is not None and "trade_date" in frame.columns:
        # String order is date order for ISO dates. A stored timestamp sorts
        # after its own date, so tonight's row is excluded either way.
        frame = frame.loc[frame["trade_date"].astype(str) < str(before)]
        if frame.empty:
            return {}, f"the store holds no position row before {before}"
    latest = frame["trade_date"].max()
    rows = frame.loc[frame["trade_date"] == latest]
    return (
        {str(row.ticker): float(row.signed_notional) for row in rows.itertuples()},
        f"the {latest} position row",
    )


def check_establishment_state(
    book: dict[str, float] | None,
    working_orders: list[dict[str, str]],
    *,
    establishment: bool,
) -> None:
    """Refuse an establishment evening unless the account is flat and idle.

    Establishing means buying the whole target book from nothing, so both halves
    of "nothing" are checked rather than assumed. A name in `book` contradicts the
    claim that this run is establishing, and any working order contradicts it in a
    way no position read can show: an order accepted after yesterday's close holds
    no position yet and is not an order tonight, but it will move the account at
    the next open, and a whole book bought against it lands the loop at twice the
    size it chose. The refusal names the orders so the owner can see which.

    A rebalance is not checked here: it trades the difference between the target
    and a book it can see, so a working order is a leg the broker will settle, not
    a position nobody counted.
    """
    if not establishment:
        return
    if book:
        raise AccountRefused(
            f"this evening would establish the book, and the account holds "
            f"{len(book)} name(s): the run stopped rather than establishing over a "
            "book it did not size"
        )
    if working_orders:
        names = ", ".join(
            sorted({order.get("symbol", "?") for order in working_orders})[:6]
        )
        raise AccountRefused(
            f"this evening would establish the book, and the account has "
            f"{len(working_orders)} open order(s) ({names}): they will move the "
            "account at the next open, so the run stopped rather than buying the "
            "whole book on top of them"
        )


def prior_weights(holdings: dict[str, Any], *, establishment: bool) -> pd.Series | None:
    """The book the orders are measured against, as weights of the account's NAV.

    Zero on an establishment evening, which every caller reads as `None`: from
    flat the whole target trades, and every previous weight is zero by definition.

    On a rebalance it is the account's own holdings divided by the account's own
    equity, never the store's position row. The store holds the loop's intentions,
    written before any order left the process, so after a dry-run evening it names
    a book the account has never held: a cost and a turnover computed against it
    price trades that never happened, and on the first live evening it would price
    a full book twice. The account's own answer is the only book that was actually
    held.

    `None` when the account could not be read or reports no equity, which is the
    same answer as an establishment evening: with no account there is no previous
    book to measure against, and a zero is what the callers do with `None`.
    """
    if establishment or holdings.get("account_read") is not True:
        return None
    nav = float(holdings.get("nav") or 0.0)
    broker = holdings.get("broker") or {}
    if not broker or nav <= 0:
        return None
    return pd.Series(
        {str(ticker): float(value) / nav for ticker, value in broker.items()},
        dtype=float,
    )


def account_read(*, raise_on_failure: bool = False) -> dict[str, Any]:
    """The broker's book, its share counts, its equity and cash, or why not.

    `positions` is None when the read failed, which is not an empty book: an
    account that could not be reached and an account that holds nothing are
    different answers, and the caller says which one it has. Reading is
    deliberately separate from `alpaca.connect(dry_run=True)`, which returns None
    because it guards submission.

    The quantities come back with the notionals from one read, because a full
    close must send the broker's exact held size rather than a re-derived one.
    The equity comes back with them for the same reason: it is read once, from the
    same account object, and it is the number the book is sized from.

    In live mode (`raise_on_failure`) a read that fails raises instead of
    answering None. The store-book fallback is allowed only in dry run: without
    this, a live evening whose account could not be read would measure every
    traded leg against the loop's own intentions, which is the failure the read
    exists to prevent. An equity the account did not report is held to the same
    rule, because a live run that cannot size its book must not build one.
    """
    from live import alpaca

    nothing: dict[str, Any] = {
        "positions": None,
        "quantities": {},
        "equity": None,
        "cash": None,
    }
    client = alpaca.read_client()
    if client is None:
        reason = (
            "not read: EFB_ALPACA_PAPER_API_KEY and EFB_ALPACA_PAPER_SECRET_KEY "
            "are not both set"
        )
        if raise_on_failure:
            raise RuntimeError(
                f"the account's positions could not be read ({reason}), so the "
                "run stopped before building any order"
            )
        return {**nothing, "source": reason}
    try:
        account = client.get_account()
        positions, quantities = alpaca.position_book(client, dry_run=False)
        figures = alpaca.account_figures(account)
        number = alpaca.account_number(account)
    except Exception as exc:
        if raise_on_failure:
            raise
        from live import notify as notify_module

        logger.warning(
            "could not read the account's positions\n%s",
            notify_module.scrub_traceback(exc),
        )
        return {**nothing, "source": "not read: see the log"}
    # The account the keys reach, before anything is sized and in every run,
    # including a dry run. A read that failed is answered above; an account that
    # answered is an account whose number the run is obliged to check.
    identity = alpaca.check_account_identity(
        number, os.environ.get(alpaca.ACCOUNT_ID_ENV)
    )
    working_orders: list[dict[str, str]] = []
    if not positions:
        # Flat, so this evening would establish the whole book, and the second half
        # of "flat" is that no order is already working: an order accepted after
        # yesterday's close holds no position yet and would move the account at the
        # next open. A read that fails here refuses for the same reason.
        try:
            working_orders = alpaca.open_orders(client)
        except Exception as exc:
            raise AccountRefused(
                "the account is flat, so this evening would establish the whole "
                "book, and its open orders could not be read "
                f"({type(exc).__name__}), so the run stopped rather than "
                "establishing over an order it cannot see"
            ) from None
    check_establishment_state(positions, working_orders, establishment=not positions)
    if raise_on_failure and figures["equity"] is None:
        raise RuntimeError(
            "the account's equity could not be read, so the run stopped before "
            "sizing a book or building any order"
        )
    return {
        "positions": positions,
        "quantities": quantities,
        "equity": figures["equity"],
        "cash": figures["cash"],
        "account_number": number,
        "account_identity": identity,
        "open_orders": working_orders,
        "source": f"{BROKER_SOURCE} {number or getattr(account, 'id', '?')}",
    }


def sizing_nav(equity: float | None) -> tuple[float, str]:
    """The NAV the book is sized from, and where that number came from.

    The account's own equity, every evening. A book sized from a constant is the
    same size on an account that has grown and on one that has halved, which is
    the hard-coded 1,000,000 this replaces.

    An equity the account *did* report, but as zero or less, raises. That is a real
    answer about the account rather than a failed read, and sizing from the paper
    default on it would buy a million dollars' worth of book against an account
    with nothing in it. The default stands in only for a read that never happened
    - no credentials, which a dry run allows - and `account_read` has already
    raised by then on a live evening, so a live book is never sized from a
    constant. The second element says which number was used, so the row and the
    manifest can state it rather than leave the reader to assume.
    """
    if equity is None:
        from live import evening_job

        return evening_job.PAPER_NAV, (
            f"the paper default ${evening_job.PAPER_NAV:,.0f}: the account's equity "
            "could not be read, which on a live evening stops the run"
        )
    if equity <= 0:
        raise RuntimeError(
            f"the account reports an equity of {equity:,.2f}, so there is nothing "
            "to size a book from and the run stopped before building one"
        )
    return float(equity), f"the account's own equity (${equity:,.2f})"


def compare(
    broker: dict[str, float] | None,
    believed: dict[str, float],
    *,
    tolerance: float = TOLERANCE_USD,
) -> dict[str, Any]:
    """Where the two books disagree, name by name.

    A name in one and not the other is a mismatch, and so is a difference larger
    than `tolerance`. `missing_at_broker` is the dangerous direction: the loop
    believes it holds something the account does not have, which is the state a
    dry-run store leaves behind.
    """
    if broker is None:
        return {
            "matches": None,
            "n_broker": None,
            "n_store": len(believed),
            "missing_at_broker": [],
            "missing_in_store": [],
            "drift": {},
            "max_abs_drift": None,
        }
    names = sorted(set(broker) | set(believed))
    missing_at_broker = [name for name in names if name not in broker]
    missing_in_store = [name for name in names if name not in believed]
    # Only the names both sides hold: a name absent from one book is already
    # reported as missing, and counting its whole value here as well would report
    # one disagreement twice.
    both = [name for name in names if name in broker and name in believed]
    drift = {
        name: float(broker[name] - believed[name])
        for name in both
        if abs(broker[name] - believed[name]) > tolerance
    }
    return {
        "matches": not (missing_at_broker or missing_in_store or drift),
        "n_broker": len(broker),
        "n_store": len(believed),
        "missing_at_broker": missing_at_broker,
        "missing_in_store": missing_in_store,
        "drift": drift,
        "max_abs_drift": max((abs(value) for value in drift.values()), default=0.0),
    }


def check(*, dry_run: bool = True, before: str | None = None) -> dict[str, Any]:
    """The whole read: both books, the difference between them, and one sentence.

    `held` is the book the orders should be measured against, and it is the
    broker's whenever the broker could be read: that is the point of the exercise.
    In live mode a failed broker read raises (`account_read`), so the store
    book is used only in dry run.

    `before` is the close being priced and is passed to `store_positions`: the
    comparison is against the last book the loop held, not tonight's target.

    `nav` is the account's equity and `nav_source` says so, because the book is
    sized from this number: passing it on from here is what keeps the sizing, the
    guards and the store's own row describing one account.
    """
    read = account_read(raise_on_failure=not dry_run)
    broker = read["positions"]
    broker_quantities = read["quantities"]
    broker_source = read["source"]
    nav, nav_source = sizing_nav(read["equity"])
    believed, believed_source = store_positions(before)
    result = compare(broker, believed)
    result.update(
        {
            "broker": broker,
            "broker_source": broker_source,
            "account_read": broker is not None,
            "equity": read["equity"],
            "cash": read["cash"],
            "nav": nav,
            "nav_source": nav_source,
            "store": believed,
            "store_source": believed_source,
            "source": BROKER_SOURCE if broker is not None else STORE_SOURCE,
            "held": broker if broker is not None else believed,
            # Shares, not dollars: what a full close sends. The store book has no
            # share counts, so a dry-run fallback carries none and a close sizes
            # from its own notional instead.
            "held_quantities": broker_quantities if broker is not None else {},
            "establishment": establishment(broker),
            # Which account the keys reached, and the orders it already had
            # working. Both are recorded rather than only logged: the number is
            # what makes "the right account traded" checkable after the fact, and
            # on an establishment evening the open-order list is the evidence the
            # whole book was bought from a flat, idle account.
            "account_number": read.get("account_number"),
            "account_identity": read.get("account_identity"),
            "open_orders": read.get("open_orders") or [],
        }
    )
    result["note"] = describe(result, dry_run=dry_run)
    return result


def establishment(broker: dict[str, float] | None) -> bool:
    """Whether this run creates the book, decided by the account and never the store.

    The store's position row is the loop's record of what it meant to hold: after a
    dry-run evening it names 150 names the paper account has never held. A
    store-based answer would call the first live evening a rebalance, measure every
    traded leg against a book that does not exist, and trade nothing at all. The
    account is the only thing that can say whether there is a book, so an account
    that could not be read (`None`) is not an empty account and is not an
    establishment day either.
    """
    if broker is None:
        return False
    return not broker


def describe(result: dict[str, Any], *, dry_run: bool = True) -> str:
    """One sentence for the email, and the same sentence for the row."""
    if result["matches"] is None:
        return (
            f"the account was {result['broker_source']}, so the store's book "
            f"({result['n_store']} name(s)) is what the orders were measured "
            f"against and no comparison was made"
        )
    if result["matches"]:
        return (
            f"the account matches the store ({result['n_broker']} name(s), "
            f"nothing drifted)"
        )
    parts = []
    if result["missing_at_broker"]:
        names = ", ".join(sorted(result["missing_at_broker"])[:6])
        more = len(result["missing_at_broker"]) - 6
        parts.append(
            f"{len(result['missing_at_broker'])} name(s) the store holds and the "
            f"account does not ({names}{', ...' if more > 0 else ''})"
        )
    if result["missing_in_store"]:
        names = ", ".join(sorted(result["missing_in_store"])[:6])
        more = len(result["missing_in_store"]) - 6
        parts.append(
            f"{len(result['missing_in_store'])} name(s) the account holds and the "
            f"store does not ({names}{', ...' if more > 0 else ''})"
        )
    if result["drift"]:
        parts.append(
            f"{len(result['drift'])} name(s) drifted, up to "
            f"${result['max_abs_drift']:,.0f}"
        )
    sentence = (
        f"mismatch: the account holds {result['n_broker']} name(s) and the store "
        f"{result['n_store']}: " + "; ".join(parts)
    )
    if dry_run and not result["broker"] and result["store"]:
        # Expected before the flip, and only before it: nothing has been sent, so
        # the account is flat while the store carries the intended book.
        sentence += (
            ". Expected in dry run: nothing has been sent to the account, so the "
            "store's book is an intention, not a holding"
        )
    return sentence
