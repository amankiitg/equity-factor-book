"""The shadow run: the calendar over 2026-10-01..2026-10-19, fully offline.

Research/verification only: `store=False`, no broker, no writes outside the tree it
is given. One proposal per close, with the book carried forward exactly as the loop
carries it, and the orders the morning would build beside it.

    python scripts/cadence_shadow.py --data /tmp/nov11merge/cut-2026-10-19/data \
        --as-of 2026-10-19 --out /tmp/cadence_shadow.json

Two passes over the same closes:

- **cadence**: `EFB_CADENCE=21` from the 2026-10-01 anchor, with the completion
  record the shadow loop itself produces (a rebalance that ran is a completed one).
- **daily**: the same closes with the flag off, which is what the loop does today.
  The difference between the two is what the calendar saved.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, cast

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live import cadence, evening_job, morning_job  # noqa: E402

CLOSES = [
    "2026-10-01",
    "2026-10-02",
    "2026-10-05",
    "2026-10-06",
    "2026-10-07",
    "2026-10-08",
    "2026-10-09",
    "2026-10-12",
    "2026-10-13",
    "2026-10-14",
    "2026-10-15",
    "2026-10-16",
    "2026-10-19",
]
ANCHOR = "2026-10-01"
K = 21


def _book(manifest: dict[str, Any]) -> dict[str, float]:
    return {str(row["ticker"]): float(row["weight"]) for row in manifest["kept_book"]}


def run_pass(
    data: pathlib.Path, nav: float, closes: list[str], *, k: int
) -> list[dict[str, Any]]:
    held: dict[str, float] = {}
    completed: list[str] = []
    rows: list[dict[str, Any]] = []
    for close in closes:
        manifest = cast(
            dict[str, Any],
            evening_job.build_proposal(
                data_root=data,
                as_of=pd.Timestamp(close),
                nav=nav,
                store=False,
                previous=pd.Series(held, dtype=float) if held else None,
                cadence_mode=k,
                cadence_anchor=ANCHOR if k > 1 else None,
                completed_rebalances=list(completed) if k > 1 else None,
            ),
        )
        book = _book(manifest)
        plan = manifest.get("cadence") or {}
        proposal = pd.DataFrame({"ticker": list(book), "weight": list(book.values())})
        # `current` is in dollars, which is what the morning reads from the
        # account; `held` is in weights, so the two are converted rather than
        # compared as though they were the same unit.
        orders = morning_job.target_orders(
            proposal,
            nav=nav,
            current={name: weight * nav for name, weight in held.items()},
            forced=(
                evening_job.forced_names_for_hold(manifest)
                if manifest.get("held_book")
                else None
            ),
        )
        row = {
            "close": close,
            "day": plan.get("day", "rebalance"),
            "scheduled": plan.get("scheduled"),
            "pending": plan.get("pending"),
            "next_rebalance": plan.get("next_rebalance"),
            "held_book": bool(manifest.get("held_book")),
            "n_kept": int(manifest["n_kept"]),
            "kept_gross": float(manifest["kept_gross"]),
            "gross": float(manifest["gross"]),
            "traded_notional": float(manifest["traded_notional"]),
            "orders": len(orders),
            "order_notional": float(sum(abs(order.trade_notional) for order in orders)),
            "order_names": sorted(order.ticker for order in orders),
            "dropped_no_risk": [str(n) for n in manifest["dropped_no_risk"]],
            "dropped_no_price": [str(n) for n in manifest["dropped_no_price"]],
            "forced": sorted(
                evening_job.forced_names_for_hold(manifest)
                if manifest.get("held_book")
                else []
            ),
        }
        rows.append(row)
        held = book
        if row["day"] == cadence.REBALANCE:
            completed.append(close)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="cadence shadow run")
    parser.add_argument("--data", required=True)
    parser.add_argument("--as-of", default="2026-10-19")
    parser.add_argument("--out", required=True)
    parser.add_argument("--nav", type=float, default=985_941.27)
    args = parser.parse_args(argv)
    data = pathlib.Path(args.data)
    closes = [c for c in CLOSES if c <= args.as_of]
    monthly = run_pass(data, args.nav, closes, k=K)
    daily = run_pass(data, args.nav, closes, k=1)
    payload: dict[str, Any] = {
        "window": {
            "anchor": ANCHOR,
            "k": K,
            "closes": closes,
            "nav": args.nav,
            "data": str(data),
        },
        "monthly": monthly,
        "daily": daily,
        "totals": {
            "monthly_traded": sum(row["traded_notional"] for row in monthly),
            "daily_traded": sum(row["traded_notional"] for row in daily),
            "monthly_orders": sum(row["orders"] for row in monthly),
            "daily_orders": sum(row["orders"] for row in daily),
            "hold_days": sum(1 for row in monthly if row["day"] == cadence.HOLD),
            "rebalance_days": sum(
                1 for row in monthly if row["day"] == cadence.REBALANCE
            ),
            "hold_day_orders": sum(
                row["orders"] for row in monthly if row["day"] == cadence.HOLD
            ),
        },
    }
    pathlib.Path(args.out).write_text(json.dumps(payload, indent=2, default=str) + "\n")
    totals = payload["totals"]
    print(
        f"{len(closes)} closes: {totals['rebalance_days']} rebalance, "
        f"{totals['hold_days']} hold; monthly traded ${totals['monthly_traded']:,.0f} "
        f"vs daily ${totals['daily_traded']:,.0f}"
    )
    for row in monthly:
        print(
            f"  {row['close']} {row['day']:<9} held={row['held_book']!s:<5} "
            f"orders={row['orders']:<3} notional=${row['order_notional']:,.0f} "
            f"next={row['next_rebalance']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
