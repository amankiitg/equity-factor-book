"""Restore `efb.reconciliation` from the backup taken before the 2026-10-20 back-fill.

**Read-only unless `--apply` is passed.** The backup
(`docs/owner_fixes/backups/reconciliation_before.json`) holds every row the back-fill
overwrote, exactly as it was stored. This script puts them back.

    python scripts/restore_reconciliation.py            # dry run: show the change
    python scripts/restore_reconciliation.py --apply    # write the backup rows back

The dry run prints, per close, the value now stored against the value in the backup
for the two columns the back-fill moves (`filled_notional`, `realized_annual_vol`) and
the number of other columns that differ. A correct restore of an applied back-fill
shows those two columns as the only change.
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

from live import store  # noqa: E402
from scripts.restore_common import (  # noqa: E402
    diff_row,
    load_backup,
    money,
    pct,
)

DEFAULT_BACKUP = (
    ROOT / "docs" / "owner_fixes" / "backups" / "reconciliation_before.json"
)

# Columns compared for the operator's benefit; every other column is only counted.
SHOWN = ("filled_notional", "realized_annual_vol")


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

    current = store.select("reconciliation")
    if current is None or current.empty:
        print(
            "no stored reconciliation rows: nothing to compare, would insert the backup"
        )
        now_by_day: dict[str, dict[str, Any]] = {}
    else:
        current = current.copy()
        current["trade_date"] = pd.to_datetime(current["trade_date"])
        now_by_day = {
            str(day.date()): record
            for day, record in zip(
                current["trade_date"], current.to_dict("records"), strict=False
            )
        }

    print(
        f"\n{'close':<12}{'filled now':>15}{'filled backup':>17}"
        f"{'realized now':>15}{'realized backup':>17}{'other cols':>12}"
    )
    changed_days = 0
    for raw, _ in loaded:
        day = str(pd.Timestamp(raw["trade_date"]).date())
        now = now_by_day.get(day)
        differs = [] if now is None else diff_row(raw, now)
        others = len([key for key in differs if key not in SHOWN])
        if now is None or differs:
            changed_days += 1
        print(
            f"{day:<12}"
            f"{money(None if now is None else now.get('filled_notional')):>15}"
            f"{money(raw.get('filled_notional')):>17}"
            f"{pct(None if now is None else now.get('realized_annual_vol')):>15}"
            f"{pct(raw.get('realized_annual_vol')):>17}{others:>12}"
        )

    if not args.apply:
        print(
            f"\nDRY RUN: {changed_days} row(s) differ from the backup. Nothing was "
            "written. Re-run with --apply to restore them."
        )
        return 0
    store.upsert("reconciliation", [prepared for _, prepared in loaded])
    print(
        f"\nRESTORED: {len(loaded)} row(s) upserted into efb.reconciliation from the "
        "backup"
    )
    print("verify: re-run without --apply and confirm every row shows no difference.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
