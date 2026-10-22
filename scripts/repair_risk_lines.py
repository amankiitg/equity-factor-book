"""Restate the attribution's risk lines from the P&L history. Dry run by default.

**Read-only unless `--apply` is passed.** `realized_vol` is a trailing-quarter standard
deviation of the book's own P&L, and `vol_ratio` its ratio to the forecast. Both were
computed over *the frame the writing run held* rather than over the history, so a
session attributed alone was stored with no realized volatility and a session
attributed in a two-session batch was stored with the standard deviation of two
numbers (2026-10-15: 0.226% against 2.477% over its own history, on 2026-10-22).

This recomputes the three series columns for every stored day through
`efb.attribution.risk_lines_over` - the same function the evening now calls after it
writes a row - and writes the full row with only those columns changed.

    python scripts/repair_risk_lines.py                       # dry run, prints the diff
    python scripts/repair_risk_lines.py --apply               # writes the three columns

Nothing else is written: `pnl_*`, the volatilities, the exposures and `written_at` are
read for the report and put back untouched.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live import attribution_job  # noqa: E402

SHOWN = ("realized_vol", "vol_ratio", "bias_statistic")


def _shown(value: object) -> str:
    if value is None:
        return "  -  "
    try:
        return f"{float(value):.6f}"  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the restated columns (default: dry run)",
    )
    args = parser.parse_args(argv)

    changed = attribution_job.restate_risk_lines(dry_run=not args.apply)
    if not changed:
        print("nothing to restate: every stored day already carries the series' values")
        return 0
    print(f"{'day':12s} {'column':16s} {'stored':>10s} {'restated':>10s}  moved")
    for item in changed:
        for column in item["moved"]:
            print(
                f"{item['day']:12s} {column:16s} "
                f"{_shown(item['before'].get(column)):>10s} "
                f"{_shown(item['after'].get(column)):>10s}"
            )
    verb = "wrote" if args.apply else "would write"
    print(f"\n{verb} {len(changed)} row(s), columns {', '.join(SHOWN)} only")
    if not args.apply:
        print("dry run: nothing was written. Pass --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
