"""Restore `efb.attribution` from the backup taken before the 2026-10-20 recompute.

**Read-only unless `--apply` is passed.** The backup
(`docs/owner_fixes/backups/attribution_before.json`) holds every row the recompute
overwrote, exactly as it was stored. This script puts them back.

    python scripts/restore_attribution.py            # dry run: show what would change
    python scripts/restore_attribution.py --apply    # write the backup rows back

The dry run prints, per close, the value now stored against the value in the backup
for the two columns the recompute deliberately moves (`pre_hedge_vol`, `hedged_vol`)
and the number of other columns that differ. A correct restore of an applied
recompute shows the backup's `pre_hedge_vol` as the change and nothing else.

The backup is JSON, so the jsonb columns come back as objects and the timestamps as
strings; both are re-encoded here into the shapes `store.upsert` expects.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from live import store  # noqa: E402
from scripts.restore_common import diff_row, load_backup, pct  # noqa: E402

DEFAULT_BACKUP = ROOT / "docs" / "owner_fixes" / "backups" / "attribution_before.json"

# Columns compared for the operator's benefit; every other column is only counted.
SHOWN = ("pre_hedge_vol", "hedged_vol", "realized_vol")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", default=str(DEFAULT_BACKUP))
    parser.add_argument(
        "--apply",
        action="store_true",
        help="upsert the backup rows (default: dry run, nothing is written)",
    )
    args = parser.parse_args(argv)

    path = pathlib.Path(args.backup).resolve()
    loaded = load_backup(path)
    print(f"backup: {path} ({len(loaded)} row(s))")

    current = store.select("attribution")
    if current is None or current.empty:
        print("no stored attribution rows: nothing to compare, would insert the backup")
        current = pd.DataFrame()
    else:
        current = current.copy()
        current["trade_date"] = pd.to_datetime(current["trade_date"])
    now_by_day = (
        {
            str(day.date()): record
            for day, record in zip(
                current["trade_date"], current.to_dict("records"), strict=False
            )
        }
        if not current.empty
        else {}
    )

    print(
        f"\n{'close':<12}{'pre-hedge now':>15}{'pre-hedge backup':>19}"
        f"{'hedged now':>13}{'hedged backup':>15}{'other cols':>12}"
    )
    changed_days = 0
    for raw, row in loaded:
        day = str(pd.Timestamp(raw["trade_date"]).date())
        now = now_by_day.get(day)
        differs = [] if now is None else diff_row(raw, now)
        others = len([key for key in differs if key not in SHOWN])
        if now is None or differs:
            changed_days += 1
        print(
            f"{day:<12}{pct(None if now is None else now.get('pre_hedge_vol')):>15}"
            f"{pct(row.get('pre_hedge_vol')):>19}"
            f"{pct(None if now is None else now.get('hedged_vol')):>13}"
            f"{pct(row.get('hedged_vol')):>15}{others:>12}"
        )

    if not args.apply:
        print(
            f"\nDRY RUN: {changed_days} row(s) differ from the backup. Nothing was "
            "written. Re-run with --apply to restore them."
        )
        return 0
    store.upsert("attribution", [prepared for _, prepared in loaded])
    print(
        f"\nRESTORED: {len(loaded)} row(s) upserted into efb.attribution "
        "from the backup"
    )
    print("verify: re-run without --apply and confirm every row shows no difference.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
