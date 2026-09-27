"""Prove the loop's four position intents against the real paper account.

The evening loop sends every leg with an Alpaca position intent, and an intent the
broker refuses is a leg the book never gets. This script is the on-account proof,
in two evenings, and it needs no proposal and no book:

    # evening one, after the close
    python scripts/smoke_position_intents.py --evening one --yes

    # evening two, after the next close
    python scripts/smoke_position_intents.py --evening two --yes

Evening one opens a small long (BUY_TO_OPEN, notional) in `--long-symbol` and a
one-share short (SELL_TO_OPEN, whole shares) in `--short-symbol`, and leaves both
accepted for the next open. Evening two closes both (SELL_TO_CLOSE the long,
BUY_TO_CLOSE the short, sized from the broker's own held quantities) so the account
is flat again before the flip.

Every id is prefixed `efb-smoke`, so a smoke order can never be mistaken for, or
block, a real leg: the book's ids are `efb-<close>-<ticker>-<side>-<digest>`.

Each evening prints one JSON line per leg and a final line saying whether every
order was accepted. Nothing is cancelled: the orders are meant to fill at the open,
and evening two is what makes the account flat again.

Like `scripts/smoke_order_timing.py`, it refuses to submit outside the 16:00-20:00
ET window: a DAY order placed after the close is held for the next open, and one
placed earlier is not, so an acceptance at another hour would prove nothing.
`--force-hour` is the deliberate out-of-hours bypass.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live import alpaca, guards, staleness  # noqa: E402 - after the path fix above

SMOKE_ID_PREFIX = "efb-smoke"
NEW_YORK = ZoneInfo("America/New_York")
# The after-hours window the loop submits in, the same one smoke_order_timing
# enforces: the close is 16:00 ET and the overnight session starts at 20:00 ET.
WINDOW_START_HOUR_ET = 16
WINDOW_END_HOUR_ET = 20
# The statuses that mean the broker took the order. After the close a DAY order is
# accepted and held for the next open, which is exactly the acceptance this checks.
ACCEPTED_STATUSES = frozenset(
    {"accepted", "new", "pending_new", "partially_filled", "filled"}
)
REFUSED_STATUSES = frozenset({"rejected", "canceled", "expired", "suspended"})


def in_cron_window(stamp: datetime) -> bool:
    """Whether `stamp` is inside the window the loop submits in.

    The definition lives in `live.staleness`, beside the cron slot and the
    calendar, and the daily run refuses outside it, so the smoke order and the
    book cannot disagree about which hour the after-hours semantics are defined
    for.
    """
    return staleness.in_cron_window(stamp)


def _fill_report(fill: Any) -> dict[str, Any]:
    # Status as a plain value: an alpaca-py `OrderStatus` has no useful `str()`.
    status = str(alpaca.enum_value(fill.status))
    return {
        "ticker": fill.ticker,
        "position_intent": str(alpaca.enum_value(fill.intent)),
        "intended_notional": float(fill.intended_notional),
        "status": status,
        "reason_code": str(alpaca.enum_value(fill.reason_code)),
        "detail": fill.detail,
        "client_order_id": fill.client_order_id,
        "accepted": status.lower() in ACCEPTED_STATUSES,
    }


def _submit(
    orders: list[guards.OrderSpec],
    client: Any,
    prices: dict[str, float],
    *,
    close: str,
) -> list[dict[str, Any]]:
    fills = alpaca.submit_market_orders(
        orders,
        client,
        prices,
        close=close,
        throttle=alpaca.Throttle(0),
        id_prefix=SMOKE_ID_PREFIX,
    )
    return [_fill_report(fill) for fill in fills]


def evening_one(
    client: Any,
    *,
    long_symbol: str = "SPY",
    short_symbol: str = "AAPL",
    notional: float = 500.0,
    short_qty: int = 1,
    short_price: float,
    close: str,
) -> list[dict[str, Any]]:
    """Open a small long and a one-share short, both left for the next open."""
    orders = [
        # BUY_TO_OPEN is a notional order: the same side as a BUY_TO_CLOSE, told
        # apart by the intent the broker reads.
        guards.OrderSpec(
            ticker=long_symbol,
            target_notional=notional,
            trade_notional=notional,
            intent=alpaca.INTENT_BUY_TO_OPEN,
        ),
        # SELL_TO_OPEN is whole shares, and the only intent that is shortable-
        # checked; a fractional sell-to-open is refused.
        guards.OrderSpec(
            ticker=short_symbol,
            target_notional=-short_qty * short_price,
            trade_notional=-short_qty * short_price,
            intent=alpaca.INTENT_SELL_TO_OPEN,
        ),
    ]
    return _submit(orders, client, {short_symbol: short_price}, close=close)


def evening_two(
    client: Any,
    *,
    long_symbol: str = "SPY",
    short_symbol: str = "AAPL",
    close: str,
) -> list[dict[str, Any]]:
    """Close the long and the short, sized from the broker's held quantities."""
    notional, quantities = alpaca.position_book(client, dry_run=False)
    orders: list[guards.OrderSpec] = []
    if notional.get(long_symbol, 0.0) > 0:
        orders.append(
            guards.OrderSpec(
                ticker=long_symbol,
                target_notional=0.0,
                trade_notional=-notional[long_symbol],
                intent=alpaca.INTENT_SELL_TO_CLOSE,
                held_quantity=quantities.get(long_symbol, 0.0),
            )
        )
    if notional.get(short_symbol, 0.0) < 0:
        orders.append(
            guards.OrderSpec(
                ticker=short_symbol,
                target_notional=0.0,
                trade_notional=-notional[short_symbol],
                intent=alpaca.INTENT_BUY_TO_CLOSE,
                held_quantity=quantities.get(short_symbol, 0.0),
            )
        )
    if not orders:
        return []
    return _submit(orders, client, {}, close=close)


def _last_close(symbol: str, as_of: date) -> float:
    """The panel's close for a symbol, so a short can be sized to whole shares."""
    from live import morning_job

    close = morning_job._close_prices(as_of.isoformat())
    return float(close.get(symbol, 0.0))


def main(
    argv: list[str] | None = None,
    client: Any = None,
    now: datetime | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evening", choices=("one", "two"), required=True)
    parser.add_argument("--long-symbol", default="SPY")
    parser.add_argument("--short-symbol", default="AAPL")
    parser.add_argument("--notional", type=float, default=500.0)
    parser.add_argument("--short-qty", type=int, default=1)
    parser.add_argument(
        "--price",
        type=float,
        default=None,
        help="the short symbol's close; read from the panel when omitted",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="required: without it nothing is submitted",
    )
    parser.add_argument(
        "--force-hour",
        action="store_true",
        help="submit outside the after-close window, for a deliberate probe",
    )
    parser.add_argument("--json", action="store_true", help="print the report only")
    args = parser.parse_args(argv)

    if not args.yes:
        print("refusing to submit without --yes", file=sys.stderr)
        return 2

    stamp = now or datetime.now(UTC)
    if not in_cron_window(stamp) and not args.force_hour:
        print(
            f"refusing to submit at {stamp.astimezone(NEW_YORK).isoformat()}: the "
            f"smoke runs between {WINDOW_START_HOUR_ET}:00 and "
            f"{WINDOW_END_HOUR_ET}:00 ET, because a DAY order placed after the "
            "close is held for the next open and one placed earlier is not. Use "
            "--force-hour for a deliberate probe.",
            file=sys.stderr,
        )
        return 2
    if not in_cron_window(stamp):
        print(
            "warning: --force-hour, so this is not the after-close window",
            file=sys.stderr,
        )

    if client is None:
        client = alpaca.connect(dry_run=False)
    close = stamp.date().isoformat()

    if args.evening == "one":
        price = (
            args.price
            if args.price is not None
            else _last_close(args.short_symbol, stamp.date())
        )
        if price <= 0:
            print(
                f"no price for {args.short_symbol}: pass --price so the one-share "
                "short can be sized",
                file=sys.stderr,
            )
            return 2
        report = evening_one(
            client,
            long_symbol=args.long_symbol,
            short_symbol=args.short_symbol,
            notional=args.notional,
            short_qty=args.short_qty,
            short_price=price,
            close=close,
        )
    else:
        report = evening_two(
            client,
            long_symbol=args.long_symbol,
            short_symbol=args.short_symbol,
            close=close,
        )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for leg in report:
            print(json.dumps(leg, sort_keys=True))
    every_accepted = bool(report) and all(leg["accepted"] for leg in report)
    if not report:
        print(f"evening {args.evening}: nothing to do (no smoke positions were open)")
        return 0
    print(
        f"evening {args.evening}: "
        + ("every order was accepted" if every_accepted else "SOME ORDERS WERE REFUSED")
    )
    return 0 if every_accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
