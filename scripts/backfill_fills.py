"""Write the `efb.fills` rows a close is owed, read back from the broker.

Dry run by default.

**Read-only unless `--apply` is passed.** The morning writes one `efb.fills` row per
leg by reading each order back from the broker. Two closes never got theirs:

- 2026-09-30: 178 legs `ACCEPTED`, 177 filled at the broker, and no fill row in the
  store;
- 2026-10-01: 183 legs `ACCEPTED` and 29 `SKIPPED`, 181 filled at the broker, and one
  fill row in the store.

2026-09-29 is not on that list and is not repairable by this script: all 177 of its
legs carry `status = DRY_RUN` and an empty `broker_order_id`, because that evening was
a dry run. Nothing was sent, so there is nothing to read back.

This script is the morning's own path, not a second one: `live.fills.read_orders`
reads each leg by its broker id, `live.fills.facts_rows` builds the rows, and
`store.upsert` writes them, which are the three calls `live.morning_job` makes. A row
whose `order_id` the store already holds is left alone, so a second run writes nothing.

    python scripts/backfill_fills.py --close 2026-09-30 --close 2026-10-01   # dry run
    python scripts/backfill_fills.py --close 2026-09-30 --close 2026-10-01 --apply

The close price each slippage is measured against comes from `efb.e11_prices` for the
same close, which is the panel the book was sized from.

**Backup and restore.** `--apply` requires `--backup`, which writes the rows the store
already held for those closes and the ids this run inserts. `--restore <file>` puts the
store back: it deletes every id the backup says was inserted and upserts the rows it
saved, so a restore is one command and it is proven by running it in a transaction and
comparing the row counts before rolling back.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from live import alpaca, fills, store  # noqa: E402


def _stored_ids() -> set[str]:
    frame = store.select("fills")
    if frame is None or frame.empty or "order_id" not in frame.columns:
        return set()
    return {str(value) for value in frame["order_id"].dropna()}


def _legs(close: str) -> pd.DataFrame:
    orders = store.select("orders")
    if orders is None or orders.empty:
        return pd.DataFrame()
    orders = orders.copy()
    orders["trade_date"] = orders["trade_date"].astype(str).str.slice(0, 10)
    sub = orders.loc[orders["trade_date"] == close].copy()
    sent = sub["broker_order_id"].astype(str).str.strip() != ""
    return sub.loc[sent]


def _closes(close: str) -> pd.Series:
    """The close price per ticker for one close, from the appendix's price table.

    `store.select` carries the live series' own tables and not the appendix ones, so
    this one statement is read directly. It is a read: nothing in this script writes
    anything but `efb.fills`, and only with `--apply`.
    """
    table = store._qualified("e11_prices")  # noqa: SLF001 - an appendix table
    connection = store.get_connection()
    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT "ticker", "close" FROM {table} WHERE "trade_date" = %s', (close,)
        )
        rows = cursor.fetchall()
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series(
        pd.to_numeric(
            pd.Series([value for _, value in rows]), errors="coerce"
        ).to_numpy(),
        index=[str(ticker) for ticker, _ in rows],
    )


def plan(close: str, client: Any, stored: set[str]) -> dict[str, Any]:
    """What this close is owed: the legs, the broker's answer and the rows to write."""
    rows = _legs(close)
    if rows.empty:
        return {"close": close, "legs": 0, "note": "no submitted legs in efb.orders"}
    orders, unread = fills.read_orders(rows, client)
    frame = fills.facts_rows(
        rows, orders, closes=_closes(close), trade_date=pd.Timestamp(close)
    )
    new = frame.loc[~frame["order_id"].astype(str).isin(stored)]
    return {
        "close": close,
        "legs": int(len(rows)),
        "unread": unread,
        "read_back": int(len(frame)),
        "already_stored": int(len(frame) - len(new)),
        "to_write": int(len(new)),
        "filled_rows": int((new["status"].astype(str).str.upper() == "FILLED").sum()),
        "filled_dollars": float(
            pd.to_numeric(new["filled_notional"], errors="coerce").fillna(0.0).sum()
        ),
        "rows": new,
    }


def _backup_rows(closes: list[str]) -> list[dict[str, Any]]:
    """Every `efb.fills` row the store holds for these closes, as it stands."""
    frame = store.select("fills")
    if frame is None or frame.empty:
        return []
    frame = frame.copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str.slice(0, 10)
    kept = frame.loc[frame["trade_date"].isin(closes)]
    return json.loads(kept.to_json(orient="records", date_format="iso"))


def write_backup(path: Path, closes: list[str], inserting: list[str]) -> None:
    """The pre-write rows and the ids about to be inserted, in one file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "written_at": datetime.now(UTC).isoformat(),
        "closes": closes,
        "store_rows_before": _backup_rows(closes),
        "inserting": sorted(inserting),
        "restore": f"python scripts/backfill_fills.py --restore {path} --apply",
    }
    path.write_text(json.dumps(document, indent=2) + "\n")


def restore(path: Path, *, apply: bool) -> int:
    """Delete the ids the backup says were inserted, then put its rows back."""
    document = json.loads(path.read_text())
    inserted = [str(value) for value in document.get("inserting", [])]
    rows = document.get("store_rows_before", [])
    table = store._qualified("fills")  # noqa: SLF001 - the restore is one statement
    print(f"backup: {path}")
    print(f"inserted ids to delete: {len(inserted)}")
    print(f"rows to put back: {len(rows)}")
    if not apply:
        print("\nDRY RUN (--restore): nothing was written.")
        return 0
    # One transaction, through the cursor: `store.upsert` opens its own connection
    # and commits on it, so a restore built from a delete and an upsert would be two
    # commits with a window between them, and a proof run inside a transaction would
    # leak the insert outside it. Measured on 2026-10-29, the first version did
    # exactly that.
    connection = store.get_connection()
    with connection.cursor() as cursor:
        if inserted:
            cursor.execute(
                f'DELETE FROM {table} WHERE "order_id" = ANY(%s)', (inserted,)
            )
            print(f"deleted {cursor.rowcount} row(s)")
        for row in rows:
            columns = ", ".join(f'"{key}"' for key in row)
            placeholders = ", ".join(["%s"] * len(row))
            cursor.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                list(row.values()),
            )
        print(f"put back {len(rows)} row(s) from the backup")
    connection.commit()
    print("RESTORED")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--close", action="append", default=[], help="a close, YYYY-MM-DD"
    )
    parser.add_argument(
        "--apply", action="store_true", help="write the rows (default: dry run)"
    )
    parser.add_argument(
        "--backup", type=Path, default=None, help="where to save the pre-write state"
    )
    parser.add_argument(
        "--restore", type=Path, default=None, help="restore from a backup file"
    )
    args = parser.parse_args(argv)

    if args.restore is not None:
        return restore(args.restore, apply=args.apply)
    if not args.close:
        parser.error("--close is required unless --restore is given")
    if args.apply and args.backup is None:
        parser.error("--apply requires --backup, so the write can be undone")

    client = alpaca.read_client()
    stored = _stored_ids()
    print(
        f"{'close':<12}{'legs':>6}{'read back':>11}{'stored':>8}{'to write':>9}"
        f"{'filled':>8}{'filled $':>14}"
    )
    plans = []
    for close in args.close:
        item = plan(close, client, stored)
        plans.append(item)
        if item.get("note"):
            print(f"{close:<12}{item['note']}")
            continue
        print(
            f"{close:<12}{item['legs']:>6}{item['read_back']:>11}"
            f"{item['already_stored']:>8}{item['to_write']:>9}"
            f"{item['filled_rows']:>8}{item['filled_dollars']:>14,.2f}"
        )
        for miss in item["unread"]:
            print(f"  unread: {miss['ticker']} {miss['error']}")

    frames = [item["rows"] for item in plans if "rows" in item and len(item["rows"])]
    total = sum(int(len(frame)) for frame in frames)
    if not total:
        print("\nnothing to write: every leg the broker answers for is already stored")
        return 0
    if not args.apply:
        print(
            f"\nDRY RUN: {total} row(s) would be written to efb.fills. "
            "Nothing was written."
        )
        return 0
    assert args.backup is not None
    combined = pd.concat(frames, ignore_index=True)
    write_backup(
        args.backup,
        list(args.close),
        [str(value) for value in combined["order_id"].tolist()],
    )
    print(f"\nbackup written: {args.backup}")
    store.upsert("fills", combined.to_dict("records"))
    print(f"APPLIED: {total} row(s) written to efb.fills through store.upsert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
