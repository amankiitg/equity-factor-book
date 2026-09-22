"""SSGA SPY daily holdings, the ongoing constituent and identity source.

Sprint E10, Part B. The SSGA SPY holdings file is fetched with a plain
unauthenticated GET and carries, per row, Name, Ticker, Identifier (CUSIP),
SEDOL, Weight, Sector, Shares Held and Local Currency. CUSIP and SEDOL are
the point: a ticker symbol is not an identity, and this file supplies both
daily. The file is an xlsx; openpyxl is not a dependency, so the xlsx is
read through its zip and sheet XML directly.

The payload is validated by shape, not by the HTTP status code: a 200 with
an HTML body (as IVV returns) is a failing source.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"

SPY_HOLDINGS_URL = (
    "https://www.ssga.com/us/en/intermediary/etfs/library-content/products/"
    "fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"
)
HEADERS = {"User-Agent": "Mozilla/5.0 (research; Equity Factor Book)"}

EXPECTED_HEADERS = [
    "Name",
    "Ticker",
    "Identifier",
    "SEDOL",
    "Weight",
    "Sector",
    "Shares Held",
    "Local Currency",
]

# the non-equity rows known to sit in the file, dropped explicitly and logged
KNOWN_NON_EQUITY = [
    {
        "name": "US DOLLAR",
        "ticker": "-",
        "identifier": "999USDZ92",
        "reason": "cash line",
    },
    {
        "name": "TPG INC",
        "ticker": "2602335D",
        "identifier": "436CVR021",
        "reason": "contingent-value-right line",
    },
]

MIN_EQUITY_ROWS = 490  # the S&P 500 index has 500 members plus a little slack
MAX_EQUITY_ROWS = 520

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_AS_OF_RE = re.compile(r"as of\s+(\d{1,2}-[A-Za-z]{3}-\d{4})", re.IGNORECASE)


def _column_letter(cell_ref: str) -> str:
    return "".join(ch for ch in cell_ref if ch.isalpha())


def parse_spy_xlsx(content: bytes) -> tuple[pd.DataFrame, str]:
    """Parse the SSGA SPY holdings xlsx from its raw bytes.

    Returns the parsed frame (columns Name, Ticker, Identifier, SEDOL,
    Weight, Sector, Shares Held, Local Currency) and the as-of date string.
    Raises with a message naming what was wrong when the payload is not the
    expected file: a 200 with an HTML body is a failing source.
    """
    if not content.startswith(b"PK"):
        snippet = content[:80].decode("utf-8", "replace").strip()
        raise ValueError(
            "SPY holdings payload is not an xlsx zip (starts with "
            f"{content[:4]!r}, first bytes {snippet!r}); a 200 with an HTML "
            "body is a failing source"
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:  # pragma: no cover - guarded above
        raise ValueError("SPY holdings payload is not a readable xlsx zip") from exc
    try:
        shared = archive.read("xl/sharedStrings.xml")
        sheet = archive.read("xl/worksheets/sheet1.xml")
    except KeyError as exc:
        raise ValueError(
            f"SPY holdings xlsx is missing the expected part {exc.args[0]!r}"
        ) from exc

    strings: list[str] = []
    shared_root = ET.fromstring(shared)
    for item in shared_root.iter(f"{{{_NS}}}si"):
        strings.append("".join(t.text or "" for t in item.iter(f"{{{_NS}}}t")))

    rows: dict[int, dict[str, Any]] = {}
    sheet_root = ET.fromstring(sheet)
    for row in sheet_root.iter(f"{{{_NS}}}row"):
        row_ref = row.get("r")
        if row_ref is None:
            continue
        row_index = int(row_ref)
        cells: dict[str, Any] = {}
        for cell in row.findall(f"{{{_NS}}}c"):
            ref = cell.get("r")
            if ref is None:
                continue
            value_node = cell.find(f"{{{_NS}}}v")
            if value_node is None or value_node.text is None:
                continue
            if cell.get("t") == "s":
                cells[_column_letter(ref)] = strings[int(value_node.text)]
            else:
                cells[_column_letter(ref)] = value_node.text
        if cells:
            rows[row_index] = cells

    # the as-of date sits in B3; the header sits in row 5
    as_of_cell = rows.get(3, {}).get("B", "")
    match = _AS_OF_RE.search(str(as_of_cell))
    if match is None:
        raise ValueError(
            f"SPY holdings xlsx has no parseable as-of date (B3 is " f"{as_of_cell!r})"
        )
    as_of = match.group(1)

    header = rows.get(5, {})
    header_names = [str(header.get(letter, "")) for letter in "ABCDEFGH"]
    if header_names != EXPECTED_HEADERS:
        raise ValueError(
            f"SPY holdings xlsx header row is {header_names!r}, expected "
            f"{EXPECTED_HEADERS!r}"
        )

    data_rows = [
        {
            "name": str(row.get("A", "")).strip(),
            "ticker": str(row.get("B", "")).strip(),
            "identifier": str(row.get("C", "")).strip(),
            "sedol": str(row.get("D", "")).strip(),
            "weight": row.get("E"),
            "sector": str(row.get("F", "")).strip(),
            "shares_held": row.get("G"),
            "local_currency": str(row.get("H", "")).strip(),
        }
        for row_index, row in sorted(rows.items())
        if row_index > 5 and str(row.get("B", "")).strip()
    ]
    frame = pd.DataFrame(data_rows)
    return frame, as_of


def _drop_non_equity(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    """Drop the known non-equity rows and return the dropped rows with reasons."""
    dropped: list[dict[str, str]] = []
    keep_mask = pd.Series(True, index=frame.index)
    for known in KNOWN_NON_EQUITY:
        hit = frame["name"].str.upper() == known["name"]
        keep_mask &= ~hit
        if hit.any():
            dropped.append(
                {
                    "name": known["name"],
                    "ticker": known["ticker"],
                    "identifier": known["identifier"],
                    "reason": known["reason"],
                }
            )
    equity = frame.loc[keep_mask].reset_index(drop=True)
    return equity, dropped


def fetch_spy_holdings(
    url: str = SPY_HOLDINGS_URL, timeout: int = 60
) -> dict[str, Any]:
    """Fetch and validate the SPY daily holdings file.

    The HTTP status is not the test: the parsed shape is. Returns a dict
    with the as-of date, the full parsed frame, the equity frame, and the
    dropped non-equity rows.
    """
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    frame, as_of = parse_spy_xlsx(response.content)
    equity, dropped = _drop_non_equity(frame)
    n_equity = len(equity)
    if not (MIN_EQUITY_ROWS <= n_equity <= MAX_EQUITY_ROWS):
        raise ValueError(
            f"SPY holdings equity row count {n_equity} is outside the sane "
            f"band {MIN_EQUITY_ROWS}..{MAX_EQUITY_ROWS}"
        )
    if equity[["identifier", "sedol"]].isna().any().any() or (
        equity["identifier"].eq("").any() or equity["sedol"].eq("").any()
    ):
        raise ValueError("SPY holdings has an equity row without CUSIP or SEDOL")
    return {
        "as_of": as_of,
        "frame": frame,
        "equity": equity,
        "dropped": dropped,
    }


def archive_snapshot(
    equity: pd.DataFrame,
    as_of: str,
    data_root: Path = DATA_ROOT,
    overwrite: bool = False,
) -> Path:
    """Write one dated, append-only snapshot of the SPY holdings.

    One file per as-of date, never overwritten; a second fetch on the same
    as-of date does not duplicate the file.
    """
    out_dir = data_root / "raw" / "spy_holdings"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = pd.to_datetime(as_of, errors="coerce")
    if pd.isna(stamp):
        raise ValueError(f"cannot derive an archive date from {as_of!r}")
    path = out_dir / f"spy_holdings_{stamp.strftime('%Y-%m-%d')}.parquet"
    if path.exists() and not overwrite:
        return path
    payload = equity.copy()
    payload["as_of"] = stamp.strftime("%Y-%m-%d")
    payload.to_parquet(path, index=False)
    return path


def cross_check(
    equity: pd.DataFrame,
    constituents: pd.DataFrame,
    membership: pd.DataFrame,
    as_of: str,
) -> pd.DataFrame:
    """The three-way disagreement between SPY, Wikipedia and stored membership.

    Returns one row per ticker with the membership verdict in each source
    and the reason where it is knowable, limited to the names where the
    three sources disagree.
    """
    spy_tickers = set(equity["ticker"].str.upper())
    wiki_tickers = set(constituents["symbol"].astype(str).str.upper())
    stored_tickers = set(str(t).upper() for t in membership.columns)
    stored_live = set(
        str(t).upper() for t in membership.columns if membership.iloc[-1][t]
    )

    all_names = sorted(spy_tickers | wiki_tickers | stored_tickers)
    rows: list[dict[str, Any]] = []
    for name in all_names:
        in_spy = name in spy_tickers
        in_wiki = name in wiki_tickers
        in_stored = name in stored_live
        if in_spy == in_wiki == in_stored:
            continue
        reason = ""
        if in_spy and not in_wiki:
            reason = "in SPY but not Wikipedia"
        elif in_wiki and not in_spy:
            reason = "in Wikipedia but not SPY"
        elif in_stored and not in_wiki:
            reason = "in stored membership but not Wikipedia (removed after the pin)"
        elif in_wiki and not in_stored:
            reason = "in Wikipedia but not stored membership (added after the pin)"
        rows.append(
            {
                "as_of": as_of,
                "ticker": name,
                "in_spy": in_spy,
                "in_wikipedia": in_wiki,
                "in_stored_membership": in_stored,
                "reason": reason,
            }
        )
    return pd.DataFrame(rows)
