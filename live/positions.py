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


def store_positions() -> tuple[dict[str, float], str]:
    """The loop's own record of the book, and which row it came from."""
    frame = store.select("positions")
    if frame.empty:
        return {}, "the store holds no position row"
    latest = frame["trade_date"].max()
    rows = frame.loc[frame["trade_date"] == latest]
    return (
        {str(row.ticker): float(row.signed_notional) for row in rows.itertuples()},
        f"the {latest} position row",
    )


def account_positions() -> tuple[dict[str, float] | None, str]:
    """The broker's book, or None with the reason it could not be read.

    None is not an empty book. An account that could not be reached and an account
    that holds nothing are different answers, and the message says which one it
    has. Reading is deliberately separate from `alpaca.connect(dry_run=True)`,
    which returns None because it guards submission.
    """
    from live import alpaca

    client = alpaca.read_client()
    if client is None:
        return None, (
            "not read: EFB_ALPACA_PAPER_API_KEY and EFB_ALPACA_PAPER_SECRET_KEY "
            "are not both set"
        )
    try:
        account = client.get_account()
        positions = alpaca.get_positions(client, dry_run=False)
    except Exception as exc:  # noqa: BLE001 - a failed read is stated, not fatal
        logger.warning("could not read the account's positions: %s", exc)
        return None, f"not read: {type(exc).__name__}: {exc}"
    return positions, f"{BROKER_SOURCE} {getattr(account, 'id', '?')}"


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


def check(*, dry_run: bool = True) -> dict[str, Any]:
    """The whole read: both books, the difference between them, and one sentence.

    `held` is the book the orders should be measured against, and it is the
    broker's whenever the broker could be read: that is the point of the exercise.
    """
    broker, broker_source = account_positions()
    believed, believed_source = store_positions()
    result = compare(broker, believed)
    result.update(
        {
            "broker": broker,
            "broker_source": broker_source,
            "store": believed,
            "store_source": believed_source,
            "source": BROKER_SOURCE if broker is not None else STORE_SOURCE,
            "held": broker if broker is not None else believed,
        }
    )
    result["note"] = describe(result, dry_run=dry_run)
    return result


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
