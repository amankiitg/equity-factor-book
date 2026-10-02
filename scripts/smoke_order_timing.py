"""Prove, once, that Alpaca accepts the loop's orders at the loop's own hour.

The evening cron fires at 22:30 UTC (render.yaml, `efb-live-daily`'s "30 22 * *
1-5"), which is
18:30 ET in summer and 17:30 ET in winter: after the 16:00 ET close and inside the
16:00-20:00 ET after-hours window. The orders the loop builds have to be accepted
at that hour and held for the next session, and `live.alpaca.NEXT_OPEN_TIF`
carries the rule and the doc citation that says which time-in-force does that.

This script is the proof: it submits one 1-share market order with the loop's
time-in-force, confirms Alpaca accepted it, and cancels it. Run it once against
the paper account before the first real order:

    python scripts/smoke_order_timing.py --symbol SPY --yes

Three things it refuses to do, each because the refusal is the value:

- it will not submit without `--yes`, so it can never run from a stray shell or
  a wrapper script;
- it will not submit outside the cron's own window (16:00-20:00 ET), because an
  order accepted at 10:00 ET proves nothing about 18:30 ET. `--force-hour` exists
  for a deliberate out-of-hours probe and prints that it was used;
- it will not submit for a symbol that is not tradable.

Nothing is left behind. The order is cancelled before the script returns, and it
is a market order for a single share, so even a cancel that raced a fill costs
one share of a liquid name. The account is the paper account, never a real one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live import alpaca, staleness  # noqa: E402 - after the path fix above

# The after-hours window an order submitted at the cron's slot lands in. The
# close is 16:00 ET and the overnight session starts at 20:00 ET, from Alpaca's
# own description of "After-hours: 4:00pm - 8:00pm ET, Monday to Friday".
WINDOW_START_HOUR_ET = 16
WINDOW_END_HOUR_ET = 20
NEW_YORK = ZoneInfo("America/New_York")

# The statuses that mean Alpaca took the order. `accepted` is the one an
# after-hours submission gets, because the order is held rather than routed.
ACCEPTED_STATUSES = frozenset(
    {"accepted", "new", "pending_new", "partially_filled", "filled"}
)
REFUSED_STATUSES = frozenset({"rejected", "canceled", "expired", "suspended"})


def in_cron_window(stamp: datetime) -> bool:
    """Whether `stamp` is inside the after-hours window the cron submits in.

    The window itself is defined in `live.staleness`, beside the cron slot and
    the calendar, and the daily run refuses outside it: one definition, so the
    smoke order and the book cannot disagree about the hour the after-hours
    semantics hold for.
    """
    return staleness.in_cron_window(stamp)


def _status_of(order: Any) -> str:
    """The broker's status as a plain string, never an enum repr.

    alpaca-py returns `OrderStatus.ACCEPTED`, whose `str()` is "OrderStatus.ACCEPTED"
    and matches none of the sets above, so the value is read with
    `getattr(x, "value", x)`.
    """
    return str(alpaca.enum_value(getattr(order, "status", ""))).lower()


def submit_verify_cancel(
    client: Any,
    *,
    symbol: str,
    now: datetime | None = None,
    sleep: Any = None,
) -> dict[str, Any]:
    """Submit one 1-share order with the loop's TIF, verify it, cancel it.

    Raises `RuntimeError` with the broker's own answer when the order is refused,
    so the failure is the reason rather than a bare status.
    """
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    stamp = now or datetime.now(UTC)
    ticket = stamp.strftime("%Y%m%dT%H%M%SZ")
    request = MarketOrderRequest(
        symbol=symbol,
        qty=1,
        side=OrderSide.BUY,
        time_in_force=TimeInForce(alpaca.NEXT_OPEN_TIF),
        client_order_id=f"efb-timing-smoke-{ticket}",
    )
    submitted = client.submit_order(order_data=request)
    order_id = str(submitted.id)
    status = _status_of(submitted)
    if status in REFUSED_STATUSES:
        raise RuntimeError(
            f"Alpaca refused a 1-share {alpaca.NEXT_OPEN_TIF} order for {symbol} "
            f"at {stamp.isoformat()}: status {status!r}"
        )
    # Read it back rather than trusting the submit response: the acceptance that
    # matters is the one the broker stores.
    stored = client.get_order(order_id)
    status = _status_of(stored)
    if status not in ACCEPTED_STATUSES:
        raise RuntimeError(
            f"the stored order {order_id} has status {status!r}, which is not an "
            f"acceptance; refusing to cancel and report success"
        )
    client.cancel_order_by_id(order_id)
    after = client.get_order(order_id)
    return {
        "symbol": symbol,
        "time_in_force": alpaca.NEXT_OPEN_TIF,
        "submitted_at_utc": stamp.astimezone(UTC).isoformat(),
        "submitted_at_et": stamp.astimezone(NEW_YORK).isoformat(),
        "in_cron_window": in_cron_window(stamp),
        "order_id": order_id,
        "client_order_id": str(getattr(stored, "client_order_id", "")),
        "status_after_submit": status,
        "status_after_cancel": _status_of(after),
        "cancelled": True,
    }


def main(
    argv: list[str] | None = None,
    client: Any = None,
    now: datetime | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="required: without it nothing is submitted",
    )
    parser.add_argument(
        "--force-hour",
        action="store_true",
        help="submit outside the cron's window, for a deliberate out-of-hours probe",
    )
    args = parser.parse_args(argv)

    stamp = now or datetime.now(UTC)
    if not args.yes:
        print(
            "refusing to submit without --yes: this places one real order on the "
            "paper account and cancels it"
        )
        return 2
    if not in_cron_window(stamp) and not args.force_hour:
        print(
            f"refusing to submit at {stamp.astimezone(NEW_YORK).isoformat()}: the cron "
            f"submits between {WINDOW_START_HOUR_ET}:00 and {WINDOW_END_HOUR_ET}:00 "
            f"ET, and an order accepted at another hour proves nothing about that "
            f"one. Use --force-hour for a deliberate probe."
        )
        return 2

    if client is None:
        if not (
            os.environ.get("EFB_ALPACA_PAPER_API_KEY")
            and os.environ.get("EFB_ALPACA_PAPER_SECRET_KEY")
        ):
            print(
                "EFB_ALPACA_PAPER_API_KEY and EFB_ALPACA_PAPER_SECRET_KEY are not "
                "both set, so there is no paper account to test against"
            )
            return 2
        client = alpaca.connect(dry_run=False)

    account = client.get_account()
    asset = client.get_asset(args.symbol)
    if not bool(getattr(asset, "tradable", False)):
        print(f"{args.symbol} is not tradable, so nothing was submitted")
        return 2
    print(
        f"account {getattr(account, 'id', '?')}, buying power "
        f"{getattr(account, 'buying_power', '?')}, symbol {args.symbol}, "
        f"tradable {getattr(asset, 'tradable', None)}, "
        f"shortable {getattr(asset, 'shortable', None)}"
    )
    if not in_cron_window(stamp):
        print("WARNING: --force-hour, so this is not the cron's own hour")

    try:
        report = submit_verify_cancel(client, symbol=args.symbol, now=stamp)
    except Exception as exc:  # noqa: BLE001 - the report is the point
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    print(
        f"ACCEPTED: a 1-share market order with time_in_force="
        f"{report['time_in_force']!r} was accepted at "
        f"{report['submitted_at_et']} and cancelled."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
