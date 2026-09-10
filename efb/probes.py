"""Task 0: probe every E1 data source and print its availability report.

A source is not available until its probe has printed rows into
sprints/E1/PROBES.md. Each probe prints row count, first and last date,
ticker coverage, NaN share and notes. Network calls live here and in the
source modules; the parsing helpers are unit tested offline.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from efb import factors, prices
from efb.universe import (
    WIKI_CHANGES_OLDID,
    all_tickers,
    fetch_changes,
    fetch_constituents,
)

ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "raw" / "yf_cache.parquet"
FRED_DTB3_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"
HEADERS = {"User-Agent": "Mozilla/5.0 (research; Equity Factor Book E1)"}


@dataclass
class ProbeReport:
    source: str
    status: str
    n_rows: int | None
    first_date: str | None
    last_date: str | None
    coverage: float | None
    nan_share: float | None
    notes: str

    def render(self) -> str:
        cov = "NA" if self.coverage is None else f"{self.coverage:.4f}"
        nans = "NA" if self.nan_share is None else f"{self.nan_share:.4f}"
        return (
            f"### {self.source}\n"
            f"status: {self.status}\n"
            f"rows: {self.n_rows} | first: {self.first_date} | last: {self.last_date}\n"
            f"ticker_coverage: {cov} | nan_share: {nans}\n"
            f"notes: {self.notes}\n"
        )


def _date_range_text(index: pd.Index) -> tuple[str | None, str | None]:
    if len(index) == 0:
        return None, None
    return (
        pd.Timestamp(index.min()).strftime("%Y-%m-%d"),
        pd.Timestamp(index.max()).strftime("%Y-%m-%d"),
    )


def probe_wikipedia() -> tuple[list[ProbeReport], pd.DataFrame, pd.DataFrame]:
    """Probe the constituents table and the pinned changes table."""
    reports: list[ProbeReport] = []
    constituents = fetch_constituents()
    first, last = _date_range_text(constituents["date_added"].dropna())
    reports.append(
        ProbeReport(
            source="wikipedia_constituents",
            status="ok",
            n_rows=len(constituents),
            first_date=first,
            last_date=last,
            coverage=None,
            nan_share=float(
                constituents[["symbol", "gics_sector"]].isna().mean().mean()
            ),
            notes=(
                "live page; columns symbol, security, gics_sector, "
                "gics_sub_industry, date_added, cik, founded"
            ),
        )
    )
    changes = fetch_changes()
    first, last = _date_range_text(changes["effective_date"])
    n_adds = changes["added_ticker"].notna().sum()
    n_rems = changes["removed_ticker"].notna().sum()
    reports.append(
        ProbeReport(
            source="wikipedia_changes",
            status="ok",
            n_rows=len(changes),
            first_date=first,
            last_date=last,
            coverage=None,
            nan_share=float(
                changes[["added_ticker", "removed_ticker"]].isna().mean().mean()
            ),
            notes=(
                f"pinned revision {WIKI_CHANGES_OLDID} (2026-08-10), the last "
                f"revision that still publishes the table; {n_adds} additions "
                f"with ticker, {n_rems} removals with ticker"
            ),
        )
    )
    return reports, constituents, changes


def probe_yfinance_prices(tickers: list[str], start: str, end: str) -> ProbeReport:
    """Download the full price history for the universe and cache it."""
    long_df = prices.load_or_download(tickers, CACHE_PATH, start=start, end=end)
    covered = prices.covered_tickers(long_df)
    adj = long_df["adj_close"]
    nan_share = float(adj.isna().mean())
    first, last = _date_range_text(long_df.index.get_level_values("date").unique())
    return ProbeReport(
        source="yfinance_prices",
        status="ok" if covered else "failed",
        n_rows=len(long_df),
        first_date=first,
        last_date=last,
        coverage=len(covered) / max(len(tickers), 1),
        nan_share=nan_share,
        notes=(
            f"requested {len(tickers)} tickers, {len(covered)} returned at least "
            f"one non-null adjusted close; auto_adjust=False, actions=True; "
            f"cached at data/raw/yf_cache.parquet"
        ),
    )


def probe_french(frames: dict[str, pd.DataFrame] | None = None) -> list[ProbeReport]:
    """Probe the four Kenneth French daily files."""
    if frames is None:
        frames = factors.load_french_factors()
    reports: list[ProbeReport] = []
    for key, frame in frames.items():
        first, last = _date_range_text(frame.index)
        reports.append(
            ProbeReport(
                source=f"french_{key}",
                status="ok",
                n_rows=len(frame),
                first_date=first,
                last_date=last,
                coverage=None,
                nan_share=float(frame.isna().mean().mean()),
                notes=f"columns: {list(frame.columns)}",
            )
        )
    return reports


def probe_sectors(constituents: pd.DataFrame) -> ProbeReport:
    """Probe GICS sector coverage on the constituents table."""
    sector = constituents["gics_sector"]
    blank = (sector.isna() | (sector == "")).sum()
    return ProbeReport(
        source="gics_sectors",
        status="ok",
        n_rows=len(constituents),
        first_date=None,
        last_date=None,
        coverage=1.0 - blank / max(len(constituents), 1),
        nan_share=blank / max(len(constituents), 1),
        notes=(
            "sector read from the Wikipedia constituents table; current members "
            "only, not point-in-time (ledger entry)"
        ),
    )


def probe_shares_outstanding(tickers: list[str], n: int = 12) -> ProbeReport:
    """Probe shares outstanding: history vs current value only."""
    sample = tickers[:n]
    rows: list[dict[str, str | int]] = []
    for ticker in sample:
        try:
            t = yf.Ticker(ticker)
            hist = t.get_shares_full(start="2010-01-01")
            if hist is None:
                n_hist = 0
            else:
                n_hist = int(len(hist))
            current = t.info.get("sharesOutstanding")
            rows.append(
                {
                    "ticker": ticker,
                    "history_rows": n_hist,
                    "current_shares": f"{current}",
                }
            )
        except Exception as exc:  # noqa: BLE001 - probe must never die
            rows.append(
                {
                    "ticker": ticker,
                    "history_rows": -1,
                    "current_shares": f"error: {exc}",
                }
            )
    frame = pd.DataFrame(rows)
    n_with_history = int((frame["history_rows"] > 1).sum())
    return ProbeReport(
        source="shares_outstanding",
        status="ok",
        n_rows=len(frame),
        first_date=None,
        last_date=None,
        coverage=float(n_with_history / max(len(frame), 1)),
        nan_share=float((frame["current_shares"].str.startswith("error")).mean()),
        notes=(
            f"sample of {len(frame)} tickers: {n_with_history} return a history "
            "from get_shares_full, the rest return only the current value; "
            "NOT point-in-time from free sources (ledger entry)"
        ),
    )


def probe_risk_free(frames: dict[str, pd.DataFrame] | None = None) -> list[ProbeReport]:
    """Probe the FF RF column and cross-check it against FRED DTB3."""
    if frames is None:
        frames = factors.load_french_factors()
    reports: list[ProbeReport] = []
    ff5 = frames["ff5"]
    rf = ff5["rf"].dropna()
    first, last = _date_range_text(rf.index)
    reports.append(
        ProbeReport(
            source="ff_risk_free",
            status="ok",
            n_rows=len(rf),
            first_date=first,
            last_date=last,
            coverage=None,
            nan_share=float(ff5["rf"].isna().mean()),
            notes=f"FF daily RF column; annualized mean {rf.mean() * 252 * 100:.2f}%",
        )
    )
    try:
        resp = requests.get(FRED_DTB3_URL, headers=HEADERS, timeout=90)
        resp.raise_for_status()
        dtb3 = pd.read_csv(io.StringIO(resp.text), parse_dates=["observation_date"])
        dtb3 = dtb3.set_index("observation_date")["DTB3"].astype(float).dropna()
        first, last = _date_range_text(dtb3.index)
        corr = float(rf.reindex(dtb3.index).corr(dtb3)) if len(dtb3) else float("nan")
        reports.append(
            ProbeReport(
                source="fred_dtb3",
                status="ok",
                n_rows=len(dtb3),
                first_date=first,
                last_date=last,
                coverage=None,
                nan_share=float(dtb3.isna().mean()),
                notes=f"cross-check correlation with FF RF: {corr:.4f}",
            )
        )
    except Exception as exc:  # noqa: BLE001 - a failed probe is a finding, not a crash
        reports.append(
            ProbeReport(
                source="fred_dtb3",
                status="failed",
                n_rows=0,
                first_date=None,
                last_date=None,
                coverage=None,
                nan_share=None,
                notes=(
                    f"unreachable from the build host ({type(exc).__name__}); "
                    "recorded as null, FF RF is the authoritative risk-free "
                    "rate for E1 (ledger entry)"
                ),
            )
        )
    return reports


def coverage_by_year(
    members: pd.DataFrame, prices: pd.DataFrame, min_fraction: float = 0.5
) -> pd.DataFrame:
    """Point-in-time members with price coverage, by calendar year (E2 Task 0).

    A member counts as covered in a year when at least min_fraction of the
    business days on which it was a member have a non-null adjusted close.
    The denominator is the ticker's own membership window, so a mid-year
    joiner is not penalized for the months before it joined.
    """
    adj = prices["adj_close"].unstack("ticker")
    dates = pd.DatetimeIndex(sorted(members.index))
    adj = adj.reindex(index=dates)
    member_bool = members.astype(bool).reindex(
        index=dates, columns=adj.columns, fill_value=False
    )
    present = adj.notna().where(member_bool, False)
    rows: list[dict[str, float]] = []
    for year, group in present.groupby(present.index.year):
        mem_year = member_bool.loc[group.index]
        days_member = mem_year.sum(axis=0)
        days_covered = group.sum(axis=0)
        frac = (days_covered / days_member.replace(0, np.nan)).fillna(0.0)
        n_members = int(mem_year.any(axis=0).sum())
        n_covered = int((frac >= min_fraction).sum())
        rows.append(
            {
                "year": int(year),
                "n_members": n_members,
                "n_covered": n_covered,
                "coverage": (n_covered / n_members) if n_members else 0.0,
            }
        )
    return pd.DataFrame(rows)


def select_model_start(table: pd.DataFrame, min_names: int = 300) -> int:
    """First calendar year whose covered-name count reaches min_names."""
    eligible = table[table["n_covered"] >= min_names]
    if eligible.empty:
        raise ValueError(
            f"no year reaches {min_names} covered members; "
            f"max is {int(table['n_covered'].max())}"
        )
    return int(eligible["year"].iloc[0])


def run_all() -> list[ProbeReport]:
    """Run every probe and return the printed reports."""
    reports: list[ProbeReport] = []
    wiki, constituents, changes = probe_wikipedia()
    reports.extend(wiki)
    tickers = all_tickers(constituents, changes)
    reports.append(
        probe_yfinance_prices(
            tickers, start="2009-12-15", end=pd.Timestamp.today().strftime("%Y-%m-%d")
        )
    )
    frames = factors.load_french_factors()
    reports.extend(probe_french(frames))
    reports.append(probe_sectors(constituents))
    reports.append(probe_shares_outstanding(tickers))
    reports.extend(probe_risk_free(frames))
    return reports


def main() -> None:
    for report in run_all():
        print(report.render())


if __name__ == "__main__":
    main()
