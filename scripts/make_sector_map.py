"""The page's bundled ticker-to-GICS map, generated from the stored files.

The live snapshot carries no sector: the book rows are ticker, weight, side,
reason, z and alpha, and the design's sector columns are exposures, not per-name
labels. The page needs the label to group a book by sector, and it must not be
typed by hand, because a hand-typed sector map goes stale silently and every
number below it stays plausible.

So the map is generated here, from the two stored files that know the answer, and
committed beside the page:

- `data/processed/sectors.parquet`, the ticker-to-GICS table the risk model
  itself uses, which is the only authoritative source in the repository;
- `data/raw/spy_holdings/spy_holdings_<date>.parquet`, the ongoing constituent
  archive, which names the current membership and carries no sector of its own
  (its `sector` column is a placeholder), so it contributes the universe and the
  sectors file supplies the labels.

The code-to-name table is `efb.models.fundamental.SECTOR_CODES`, the same one the
design columns are built from, so `sector_45` and "Information Technology" cannot
disagree.

A ticker in neither file's world, or one whose GICS name is not a sector the model
knows, is deliberately left out: the page renders those as Unmapped, which is the
truth about them rather than a guess.

Regenerate with:

    .venv/bin/python scripts/make_sector_map.py

`tests/test_web_sector_map.py` regenerates it and asserts the committed bytes are
what this produces, so the map cannot drift from the files it came from.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from efb.models.fundamental import SECTOR_CODES

ROOT = Path(__file__).resolve().parents[1]
SECTORS_PATH = ROOT / "data" / "processed" / "sectors.parquet"
HOLDINGS_DIR = ROOT / "data" / "raw" / "spy_holdings"
TARGET = ROOT / "web" / "src" / "sector_map.json"
TICKER_COLUMN = "ticker"
SECTOR_COLUMN = "gics_sector"


def latest_holdings(directory: Path = HOLDINGS_DIR) -> Path:
    """The most recent dated holdings file, which is the current membership."""
    files = sorted(directory.glob("spy_holdings_*.parquet"))
    if not files:
        raise FileNotFoundError(f"no holdings archive under {directory}")
    return files[-1]


def _as_of(frame: pd.DataFrame) -> str | None:
    """The single as-of date the file records, or None when it records several."""
    if "as_of" not in frame.columns or frame.empty:
        return None
    stamps = {str(value)[:10] for value in frame["as_of"].dropna()}
    return stamps.pop() if len(stamps) == 1 else None


def build_map(sectors: pd.DataFrame, holdings: pd.DataFrame) -> dict[str, Any]:
    """The document the page imports, from the two frames and nothing else."""
    known = {
        str(row[TICKER_COLUMN]).strip().upper(): str(row[SECTOR_COLUMN]).strip()
        for _, row in sectors.iterrows()
        if pd.notna(row.get(TICKER_COLUMN)) and pd.notna(row.get(SECTOR_COLUMN))
    }
    universe = sorted(
        {
            str(ticker).strip().upper()
            for ticker in holdings.get(TICKER_COLUMN, pd.Series(dtype=object)).dropna()
        }
        | set(known)
    )
    tickers: dict[str, int] = {}
    unknown_names: list[str] = []
    for ticker in universe:
        name = known.get(ticker)
        if name is None:
            continue
        code = SECTOR_CODES.get(name)
        if code is None:
            if name not in unknown_names:
                unknown_names.append(name)
            continue
        tickers[ticker] = code
    return {
        "source": {
            "sectors": str(SECTORS_PATH.relative_to(ROOT)),
            "sectors_as_of": _as_of(sectors),
            "holdings": str(latest_holdings().relative_to(ROOT)),
            "holdings_as_of": _as_of(holdings),
            "codes": "efb.models.fundamental.SECTOR_CODES",
        },
        "sectors": {str(code): name for name, code in SECTOR_CODES.items()},
        "tickers": tickers,
        # What the map leaves out, kept here rather than in the bundle: the page
        # never needs the list, and a test asserting that the gaps are the
        # sources' gaps should read the sources, not the file under test.
        "unmapped_universe": sorted(set(universe) - set(tickers)),
        "unknown_sector_names": sorted(unknown_names),
    }


def bundle(document: dict[str, Any]) -> dict[str, Any]:
    """The part of the document the page imports, and nothing else.

    `unmapped_universe` is a diagnosis, not data: it is the tickers this map does
    not carry, which the page renders as Unmapped from their absence. Shipping it
    would put several hundred strings into the browser bundle to describe names
    that are not there.
    """
    return {
        key: document[key] for key in ("source", "sectors", "tickers")
    }


def main() -> int:
    sectors = pd.read_parquet(SECTORS_PATH)
    holdings = pd.read_parquet(latest_holdings())
    document = build_map(sectors, holdings)
    TARGET.write_text(json.dumps(bundle(document), indent=1, sort_keys=True) + "\n")
    print(f"wrote {TARGET.relative_to(ROOT)}")
    print(f"  {len(document['tickers'])} tickers mapped")
    print(f"  {len(document['unmapped_universe'])} in the universe with no sector")
    unknown = document["unknown_sector_names"]
    if unknown:
        print(f"  GICS names the model does not know: {unknown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
