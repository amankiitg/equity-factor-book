"""Back up `efb.attribution` rows to the JSON shape the restore script reads.

**Read-only.** The 2026-10-20/21 recomputes each needed a backup of exactly the rows
they were about to overwrite, taken before the write and committed beside the note that
describes it. This is that step, made repeatable:

    python scripts/backup_attribution_rows.py --since 2026-09-28 --through 2026-09-28 \
        --out docs/owner_fixes/backups/attribution_0928_before.json

The file carries every column of every selected row - not only the columns a given
write touches - because a restore has to put the row back whole. Restore with
`scripts/restore_attribution.py --backup <file>`.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import UTC, datetime
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from live import store  # noqa: E402


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, pd.Timestamp.__mro__[1]):  # datetime.date and friends
        return value.isoformat()
    if hasattr(value, "as_tuple"):  # Decimal
        return float(value)
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True)
    parser.add_argument("--through", default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)

    frame = store.select("attribution")
    if frame is None or frame.empty:
        print("no stored attribution rows: nothing to back up")
        return 1
    frame = frame.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    since = pd.Timestamp(args.since)
    through = pd.Timestamp(args.through) if args.through else since
    selected = frame.loc[
        (frame["trade_date"] >= since) & (frame["trade_date"] <= through)
    ].sort_values("trade_date")
    if selected.empty:
        print(f"no rows between {since.date()} and {through.date()}")
        return 1

    rows = [
        {key: _jsonable(value) for key, value in record.items()}
        for record in selected.to_dict("records")
    ]
    payload = {
        "captured_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": args.note
        or "Rows the attribution write of this session overwrote. Restore with "
        "scripts/restore_attribution.py --backup <this file>.",
        "row_count": len(rows),
        "scope_since": str(since.date()),
        "scope_through": str(through.date()),
        "rows": rows,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_jsonable) + "\n"
    )
    scope = f"{payload['scope_since']}..{payload['scope_through']}"
    print(f"wrote {out} ({len(rows)} row(s), {scope})")
    for record in rows:
        day = str(record["trade_date"])[:10]
        print(f"  {day}  pre_hedge_vol={record.get('pre_hedge_vol')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
