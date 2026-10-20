"""Back-fill `efb.reconciliation`'s two morning-owned columns, dry run by default.

**Read-only unless `--apply` is passed.** The evening writes a reconciliation row
before its orders settle, so it can only leave `filled_notional = 0.0` and
`realized_annual_vol` empty; the morning is what knows both. Before nov11's B1/B2 the
morning never wrote them back, so every row up to 2026-10-16 still carries the
evening's placeholder.

    python scripts/backfill_reconciliation.py                    # dry run
    python scripts/backfill_reconciliation.py --apply

What each column becomes:

- `filled_notional` is `sum(abs(filled_notional))` over `efb.fills` for the close -
  the same expression `live/reconcile.py::_execution_row` uses.
- `realized_annual_vol` is `live.reconcile.realized_annual_vol_for(close, attribution)`
  - the standard deviation of the book's daily P&L over the stored attribution rows
  up to the close, annualized. It is `None` until two sessions exist, and the script
  prints that rather than inventing a zero.

A close with **no fills rows at all** is reported and left alone unless
`--include-empty-fills` is passed: an empty fills table can mean a day that genuinely
traded nothing (the 2026-09-25 dry run) or a morning that has not run yet (the newest
close always has this shape). The script cannot tell those apart, so the owner does.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from live import reconcile, store  # noqa: E402


def _filled_by_day(fills: pd.DataFrame) -> dict[str, float]:
    if fills is None or fills.empty or "trade_date" not in fills.columns:
        return {}
    days = fills["trade_date"].astype(str).str.slice(0, 10)
    amounts = pd.to_numeric(fills["filled_notional"], errors="coerce").abs()
    return {
        str(day): float(value) for day, value in amounts.groupby(days).sum().items()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the rows")
    parser.add_argument("--through", default=None, help="last close, YYYY-MM-DD")
    parser.add_argument(
        "--include-empty-fills",
        action="store_true",
        help="treat a close with no fills rows as a day that traded nothing",
    )
    args = parser.parse_args(argv)

    rows = store.select("reconciliation")
    if rows is None or rows.empty:
        print("no reconciliation rows")
        return 0
    fills = store.select("fills")
    attribution = store.select("attribution")
    by_day = _filled_by_day(fills)

    frame = rows.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.sort_values("trade_date")
    if args.through:
        frame = frame.loc[frame["trade_date"] <= pd.Timestamp(args.through)]
    newest = frame["trade_date"].max() if len(frame) else None

    updates: list[dict[str, Any]] = []
    print(
        f"{'close':<12}{'filled before':>15}{'filled after':>15}"
        f"{'realized before':>17}{'realized after':>16}   note"
    )
    for record in frame.to_dict("records"):
        day = pd.Timestamp(record["trade_date"])
        key = str(day.date())
        old_filled = record.get("filled_notional")
        old_realized = record.get("realized_annual_vol")
        filled = by_day.get(key, 0.0)
        realized = reconcile.realized_annual_vol_for(key, attribution)
        note = ""
        if key not in by_day and not args.include_empty_fills:
            filled = old_filled
            note = "no fills rows: verify the morning ran"
        if realized is None:
            realized = old_realized
            if note:
                note += "; "
            note += "realized needs two attributed sessions"
        changed = (
            old_filled != filled and not (pd.isna(old_filled) and pd.isna(filled))
        ) or (
            old_realized != realized
            and not (pd.isna(old_realized) and pd.isna(realized))
        )
        print(
            f"{key:<12}{_num(old_filled):>15}{_num(filled):>15}"
            f"{_num(old_realized):>17}{_num(realized):>16}   {note}"
        )
        if not changed:
            continue
        row = {
            column: (None if isinstance(value, float) and pd.isna(value) else value)
            for column, value in record.items()
        }
        row["filled_notional"] = float(filled) if filled is not None else None
        row["realized_annual_vol"] = float(realized) if realized is not None else None
        updates.append(row)

    if newest is not None:
        print(f"\nnewest close considered: {newest.date()}")
    if not args.apply:
        print(
            f"\nDRY RUN: {len(updates)} row(s) would be updated. Nothing was written. "
            "Re-run with --apply to write them."
        )
        return 0
    if updates:
        store.upsert("reconciliation", updates)
    print(f"\nAPPLIED: {len(updates)} row(s) upserted into efb.reconciliation")
    return 0


def _num(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    return f"{float(value):,.2f}"


if __name__ == "__main__":
    raise SystemExit(main())
