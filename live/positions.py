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
"""

from __future__ import annotations

import logging
from typing import Any

from live import store

logger = logging.getLogger(__name__)

# One dollar: both sides are dollar notions rounded to the cent by the time they
# are compared, so anything above a dollar is a real difference rather than
# arithmetic noise.
TOLERANCE_USD = 1.0

BROKER_SOURCE = "alpaca paper account"
STORE_SOURCE = "store"


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
    except Exception:
        if raise_on_failure:
            raise
        logger.warning("could not read the account's positions", exc_info=True)
        return {**nothing, "source": "not read: see the log"}
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
        "source": f"{BROKER_SOURCE} {getattr(account, 'id', '?')}",
    }


def sizing_nav(equity: float | None) -> tuple[float, str]:
    """The NAV the book is sized from, and where that number came from.

    The account's own equity, every evening. A book sized from a constant is the
    same size on an account that has grown and on one that has halved, which is
    the hard-coded 1,000,000 this replaces.

    The design's paper default stands in only when the account could not be read
    at all, which happens in dry run and never live: `account_read` has already
    raised by then, so a live book is never sized from a constant. The second
    element says which number was used, so the row and the manifest can state it
    rather than leave the reader to assume.
    """
    if equity is not None and equity > 0:
        return float(equity), f"the account's own equity (${equity:,.2f})"
    from live import evening_job

    return evening_job.PAPER_NAV, (
        f"the paper default ${evening_job.PAPER_NAV:,.0f}: the account's equity "
        "could not be read, which on a live evening stops the run"
    )


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
