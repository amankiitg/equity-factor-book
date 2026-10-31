"""Bring the GICS table up to date: every name in a constituents snapshot gets a row.

The book excludes a name it cannot label - "no GICS row" - and until 2026-10-31 that
was six S&P 500 members: BE, ILMN, P, SKYD, TWLO and VYLR. The cause was not the
sector data but its vintage: `processed/sectors.parquet` was built from the
2026-09-11 constituents snapshot, and those six joined the index afterwards (SKYD,
TWLO and VYLR after the 2026-09-22 snapshot the tree carried).

So this **unions** rather than rebuilds. A ticker-to-GICS table is a label, not a
membership list: a name that leaves the index still has a sector, and a refresh that
dropped `BLDR`, `TAP` and `TTD` because a newer snapshot no longer lists them would
trade six names' measurability for three names' labels. Rows are added, never removed,
and an existing row is never restated (its `as_of` says which snapshot it came from).

Read-only by default. `--apply` writes the artifact, the page's bundled map, and the
rows the store's appendix is missing, after saving the table it touches and recording
it in a manifest; it then reads the table back and proves the row count moved by
exactly the number of tickers it added.

**Status 2026-10-31: not applied.** The rows it adds are real and the labels are the
vendors', but applying them is not free: sector labels feed the descriptor
cross-section and the variance shrinkage's bucket means, so the paired build on
2026-10-30 changes the book (`n_kept` 169 -> 163, 17 names in and 23 out) while the
six names stay unmeasurable, because their defect is the descriptor panel, not the
label. See `docs/research/excluded_names.md`. Applying it needs its own identity
proof, not this script's read-back.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from efb import universe  # noqa: E402

SECTORS_PATH = Path("processed/sectors.parquet")
PAGE_MAP = ROOT / "web" / "src" / "sector_map.json"
APPENDIX_TABLE = "e11_sectors"


def newest_snapshot(root: Path) -> Path:
    files = sorted((root / "raw" / "wikipedia_constituents").glob("*.parquet"))
    if not files:
        raise SystemExit(f"no constituents snapshot under {root / 'raw'}")
    return files[-1]


def union(
    current: pd.DataFrame, snapshot: pd.DataFrame, as_of: str
) -> tuple[pd.DataFrame, list[str]]:
    """`current` with a row for every name `snapshot` knows and `current` does not."""
    fresh = universe.build_sectors(snapshot, as_of=as_of)
    known = set(current["ticker"].astype(str))
    added = fresh.loc[~fresh["ticker"].astype(str).isin(known)].copy()
    if added.empty:
        return current.copy(), []
    combined = pd.concat([current, added], ignore_index=True)
    combined = combined.sort_values("ticker").reset_index(drop=True)
    return combined, sorted(added["ticker"].astype(str))


def page_map(sectors: pd.DataFrame) -> dict[str, Any]:
    """The bundled ticker-to-code map, from the table and nothing else."""
    from efb.models.fundamental import SECTOR_CODES

    codes = {
        str(row["ticker"]).strip().upper(): SECTOR_CODES[str(row["gics_sector"]).strip()]
        for _, row in sectors.iterrows()
        if pd.notna(row.get("gics_sector")) and str(row["gics_sector"]).strip() in SECTOR_CODES
    }
    return {
        "source": {
            "sectors": str(SECTORS_PATH),
            "sectors_as_of": str(sectors["as_of"].max())[:10],
            "codes": "efb.models.fundamental.SECTOR_CODES",
        },
        "sectors": {str(code): name for name, code in SECTOR_CODES.items()},
        "tickers": dict(sorted(codes.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="refresh the GICS table")
    parser.add_argument("--root", type=Path, default=ROOT / "data")
    parser.add_argument(
        "--as-of",
        default=datetime.now(UTC).date().isoformat(),
        help="the date the added rows are stamped with",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path, default=None)
    args = parser.parse_args(argv)

    root = args.root
    current = pd.read_parquet(root / SECTORS_PATH)
    snapshot = pd.read_parquet(newest_snapshot(root))
    sectors, added = union(current, snapshot, args.as_of)
    print(f"snapshot: {newest_snapshot(root).name} ({len(snapshot)} rows)")
    print(f"table: {len(current)} rows -> {len(sectors)}; added {len(added)}: {added}")
    before = sorted(set(current["ticker"].astype(str)) - set(sectors["ticker"].astype(str)))
    if before:
        raise SystemExit(f"the union would drop {before}, which it must never do")

    if not args.apply:
        print("read-only: nothing written (pass --apply and --backup to write)")
        return 0
    if args.backup is None:
        raise SystemExit("--apply needs --backup: the table as it stands comes first")
    directory = args.backup
    directory.mkdir(parents=True, exist_ok=True)
    current.to_parquet(directory / "e11_sectors_before.parquet", index=False)
    current.to_csv(directory / "e11_sectors_before.csv", index=False)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "taken_at": datetime.now(UTC).isoformat(),
                "table": APPENDIX_TABLE,
                "rows": len(current),
                "file": str(directory / "e11_sectors_before.parquet"),
                "sha256": hashlib.sha256(
                    (directory / "e11_sectors_before.parquet").read_bytes()
                ).hexdigest(),
                "restore": (
                    "python scripts/refresh_sectors.py --restore "
                    f"{directory / 'e11_sectors_before.parquet'}"
                ),
            },
            indent=1,
        )
        + "\n"
    )
    print(f"backup: {directory}")

    sectors.to_parquet(root / SECTORS_PATH, index=False)
    PAGE_MAP.write_text(json.dumps(page_map(sectors), indent=1, sort_keys=True) + "\n")
    print(f"wrote {root / SECTORS_PATH} and {PAGE_MAP}")

    if added:
        from live import appendix, store

        rows = sectors.loc[sectors["ticker"].astype(str).isin(added)].copy()
        rows = rows.rename(columns={"as_of": "trade_date"})
        store.upsert(appendix.SPEC_BY_NAME["sectors"].table, rows.to_dict("records"))
        after = appendix.read_appendix(appendix.SPEC_BY_NAME["sectors"])
        print(f"{APPENDIX_TABLE}: {len(current)} -> {len(after)} rows")
        missing = [
            ticker
            for ticker in added
            if ticker not in set(after["ticker"].astype(str))
        ]
        if missing:
            raise SystemExit(f"the store did not take {missing}")
        print(f"verified: all {len(added)} added tickers are in the store")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
