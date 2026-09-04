"""S&P 500 universe data from Wikipedia (Sprint E1, Task 2).

The constituents table is read from the live Wikipedia page. The "Selected
changes" table was removed from the live page on 2026-08-11. E1 pins
revision WIKI_CHANGES_OLDID (2026-08-10), the last revision that still
publishes it, and records this policy in docs/hygiene_ledger.md.
"""

from __future__ import annotations

import io
import re
from typing import Any

import pandas as pd
import requests

WIKI_PAGE = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_CHANGES_OLDID = "1368675864"  # 2026-08-10, last revision with changes table
HEADERS = {"User-Agent": "Mozilla/5.0 (research; Equity Factor Book E1)"}

TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,4}$")


def _get(url: str, params: dict[str, Any] | None = None, timeout: int = 60) -> str:
    resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_constituents() -> pd.DataFrame:
    """Fetch the current S&P 500 constituents table from the live page.

    Returns a DataFrame with columns: symbol, security, gics_sector,
    gics_sub_industry, headquarters, date_added, cik, founded.
    """
    html = _get(WIKI_PAGE)
    tables = pd.read_html(io.StringIO(html))
    raw = tables[0]
    raw.columns = [
        re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()) for c in raw.columns
    ]
    out = pd.DataFrame(
        {
            "symbol": raw["symbol"].astype(str).str.strip(),
            "security": raw["security"].astype(str).str.strip(),
            "gics_sector": raw["gics_sector"].astype(str).str.strip(),
            "gics_sub_industry": raw["gics_sub_industry"].astype(str).str.strip(),
            "headquarters": raw.get(
                "headquarters_location", pd.Series([""] * len(raw))
            ),
            "date_added": pd.to_datetime(raw.get("date_added"), errors="coerce"),
            "cik": raw.get("cik"),
            "founded": raw.get("founded"),
        }
    )
    return out.sort_values("symbol").reset_index(drop=True)


def fetch_changes() -> pd.DataFrame:
    """Fetch the S&P 500 component changes table from the pinned revision.

    Returns a DataFrame with columns: effective_date, added_ticker,
    added_security, removed_ticker, removed_security, reason.
    """
    params = {
        "action": "parse",
        "oldid": WIKI_CHANGES_OLDID,
        "prop": "text",
        "format": "json",
    }
    resp = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    rendered = resp.json()["parse"]["text"]["*"]
    tables = pd.read_html(io.StringIO(rendered))
    raw = tables[1]

    def _col(top: str, second: str) -> pd.Series:
        if isinstance(raw.columns, pd.MultiIndex):
            return raw[(top, second)]  # type: ignore[index]
        key = f"{top}_{second}"
        return raw[key]

    out = pd.DataFrame(
        {
            "effective_date": pd.to_datetime(
                _col("Effective Date", "Effective Date"), errors="coerce"
            ),
            "added_ticker": _col("Added", "Ticker"),
            "added_security": _col("Added", "Security"),
            "removed_ticker": _col("Removed", "Ticker"),
            "removed_security": _col("Removed", "Security"),
            "reason": _col("Reason", "Reason"),
        }
    )
    out["added_ticker"] = out["added_ticker"].map(_clean_ticker)
    out["removed_ticker"] = out["removed_ticker"].map(_clean_ticker)
    out["reason"] = out["reason"].astype(str).str.strip()
    out = out.dropna(subset=["effective_date"])
    return out.sort_values("effective_date").reset_index(drop=True)


def _clean_ticker(value: Any) -> str | None:
    """Normalize a ticker cell; return None when the cell is not a symbol."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if text.lower() in {"nan", "none", ""}:
        return None
    if TICKER_RE.match(text):
        return text
    return None


def current_tickers(constituents: pd.DataFrame) -> list[str]:
    return sorted(constituents["symbol"].dropna().unique().tolist())


def deleted_tickers(changes: pd.DataFrame) -> list[str]:
    removed = changes["removed_ticker"].dropna().unique().tolist()
    return sorted(removed)


def all_tickers(constituents: pd.DataFrame, changes: pd.DataFrame) -> list[str]:
    """Every ticker that is or was an S&P 500 member per our sources."""
    return sorted(set(current_tickers(constituents)) | set(deleted_tickers(changes)))


def membership_start_dates(changes: pd.DataFrame) -> dict[str, pd.Timestamp]:
    """Approximate first membership date per ticker from the changes table.

    A ticker not in the changes table is assumed to have joined before the
    table's window; its start date is the table's first event date.
    """
    first_event = changes["effective_date"].min()
    starts: dict[str, pd.Timestamp] = {}
    for row in changes.itertuples(index=False):
        added, removed, date = row.added_ticker, row.removed_ticker, row.effective_date
        if added is not None:
            starts[added] = min(starts.get(added, pd.Timestamp.max), date)
        if removed is not None:
            starts.pop(removed, None)  # removal ends a stint; re-add will reinsert
    return {t: starts.get(t, first_event) for t in starts}


def build_membership(
    changes: pd.DataFrame,
    constituents: pd.DataFrame,
    start: str = "2010-01-04",
    end: str | None = None,
) -> pd.DataFrame:
    """Rebuild the point-in-time membership matrix (date x ticker).

    Walks the changes table backward from today's members: at each event
    date, for all earlier dates the removed ticker is a member and the
    added ticker is not. The walk handles re-entries and removals exactly
    within the table's window; before the earliest event, membership is
    extended backward unchanged. Events fall on the next business day at
    or after their calendar date.
    """
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    dates = pd.bdate_range(start=start, end=end)
    current = set(current_tickers(constituents))
    deleted = set(deleted_tickers(changes))
    columns = sorted(current | deleted)
    members = pd.DataFrame(False, index=dates, columns=columns)
    members[list(current)] = True
    events = changes.dropna(subset=["effective_date"]).sort_values(
        "effective_date", ascending=False
    )
    for row in events.itertuples(index=False):
        added, removed, date = row.added_ticker, row.removed_ticker, row.effective_date
        eff = dates[dates >= pd.Timestamp(date)]
        if len(eff) == 0:
            continue
        cutoff = eff[0]
        earlier = members.index < cutoff
        if removed is not None and removed in members.columns:
            members.loc[earlier, removed] = True
        if added is not None and added in members.columns:
            members.loc[earlier, added] = False
    return members


def membership_changes(members: pd.DataFrame) -> pd.DataFrame:
    """Per-date additions and removals implied by the membership matrix."""
    diff = members.astype(int).diff()
    rows: list[dict[str, object]] = []
    for ticker in members.columns:
        series = diff[ticker]
        added = series[series == 1]
        removed = series[series == -1]
        rows.extend(
            {"date": d, "ticker": ticker, "event_type": "added"} for d in added.index
        )
        rows.extend(
            {"date": d, "ticker": ticker, "event_type": "removed"}
            for d in removed.index
        )
    if not rows:
        return pd.DataFrame(columns=["date", "ticker", "event_type"])
    return pd.DataFrame(rows).sort_values(["date", "ticker"]).reset_index(drop=True)


def survivorship_stats(
    members: pd.DataFrame, price_tickers: set[str]
) -> dict[str, float | int]:
    """Fraction of deleted members with recoverable price history (F1.5)."""
    current = set(members.columns[members.iloc[-1]])
    deleted = set(members.columns) - current
    recovered = deleted & price_tickers
    return {
        "n_deleted": len(deleted),
        "n_recovered": len(recovered),
        "fraction": len(recovered) / len(deleted) if deleted else float("nan"),
    }


def build_sectors(constituents: pd.DataFrame, as_of: str) -> pd.DataFrame:
    """Build sectors.parquet rows from the constituents snapshot."""
    out = pd.DataFrame(
        {
            "ticker": constituents["symbol"],
            "gics_sector": constituents["gics_sector"],
            "gics_sub_industry": constituents["gics_sub_industry"],
            "source": "wikipedia",
            "as_of": pd.Timestamp(as_of),
        }
    )
    return out.sort_values("ticker").reset_index(drop=True)
