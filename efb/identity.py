"""Ticker identity checks (Sprint E2 close-out, task C1, criterion F2.6b).

A ticker symbol is not an identity. When an S&P 500 member is acquired or
delisted its symbol can be taken over by an unrelated listing, and the
vendor then splices both companies into one price history. Adjusted-close
levels jump by more than 5x with no split behind them, and every date
before the break carries the wrong company's returns. F2.6 detects the
jump; this module asks the cheaper and more direct question, which company
does the symbol belong to today, by comparing the security name in the
Wikipedia changes table with the name yfinance reports for that symbol.

Rules, per the close-out brief:

- Name match: the history is legitimate even if prices continue past the
  removal date.
- No match: the symbol was reused. Rows before the first valid date that
  belongs to the current company are dropped. When that date cannot be
  determined, the ticker is dropped entirely and the reason is recorded.
- Separately, any ticker with a gap above 60 business days between two
  live price segments is flagged.

One extra rule, stated because it decides the four known cases: a reused
symbol whose retained segment does not overlap its S&P 500 membership
window carries no history of the member at all, so it is dropped rather
than truncated. Truncating CPWR would keep an unrelated penny stock and
throw away the member, which is the opposite of the intent.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from efb import hygiene

DEFAULT_CACHE = Path("data/raw/yf_names.parquet")
MATCH_THRESHOLD = 0.5
GAP_BUSINESS_DAYS = 60

# Legal and share-class noise: the brief's list plus the obvious variants
# and single letters, which is what "Class A/B" reduces to.
SUFFIX_TOKENS = frozenset(
    {
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
        "company",
        "ltd",
        "limited",
        "plc",
        "llc",
        "lp",
        "pllc",
        "class",
    }
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_name(name: object) -> frozenset[str]:
    """Name to its content tokens: lowercase, no punctuation, no suffixes."""
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return frozenset()
    text = str(name).lower()
    tokens = [t for t in _NON_ALNUM.split(text) if t]
    return frozenset(
        t for t in tokens if t not in SUFFIX_TOKENS and len(t) > 1 or t.isdigit()
    )


def match_score(removed_name: object, current_name: object) -> float:
    """Jaccard overlap of the two names' content tokens, in [0, 1]."""
    left = normalize_name(removed_name)
    right = normalize_name(current_name)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def usable_name(name: object) -> str | None:
    """A holder name that can be compared, or None when there is none.

    A delisted symbol that nobody holds today returns no name at all, and
    some vendor fields come back as a number or a single letter. Absence of
    a name is not evidence that a symbol was reused, so it must be told
    apart from a name that simply does not match.
    """
    if not isinstance(name, str):
        return None
    text = name.strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    if not any(ch.isalpha() for ch in text):
        return None
    return text


def fetch_symbol_names(
    tickers: list[str],
    cache_path: Path | str = DEFAULT_CACHE,
    fetcher: Callable[[str], dict] | None = None,
    attempts: int = 3,
) -> pd.DataFrame:
    """Current holder name per ticker, cached so each symbol is asked once.

    Returns columns ticker, symbol, long_name, short_name. A lookup is
    retried `attempts` times before being cached as NaN, because a
    transient vendor failure must not be written to the cache as "this
    symbol has no name".
    """
    path = Path(cache_path)
    cached = pd.DataFrame(columns=["ticker", "symbol", "long_name", "short_name"])
    if path.exists():
        cached = pd.read_parquet(path)

    wanted = list(dict.fromkeys(tickers))
    known = set(cached["ticker"]) if len(cached) else set()
    missing = [t for t in wanted if t not in known]

    if missing:
        fetch = fetcher or _yfinance_fetcher
        rows = []
        for ticker in missing:
            symbol = ticker.replace(".", "-")
            long_name: object = None
            short_name: object = None
            for attempt in range(max(1, attempts)):
                try:
                    info = fetch(symbol)
                except Exception:  # pragma: no cover - vendor and network
                    if attempt + 1 >= max(1, attempts):
                        break
                    continue
                long_name = info.get("longName")
                short_name = info.get("shortName")
                if usable_name(long_name) or usable_name(short_name):
                    break
            rows.append(
                {
                    "ticker": ticker,
                    "symbol": symbol,
                    "long_name": long_name,
                    "short_name": short_name,
                }
            )
        fresh = pd.DataFrame(rows)
        cached = pd.concat([cached, fresh], ignore_index=True) if len(cached) else fresh
        path.parent.mkdir(parents=True, exist_ok=True)
        cached.to_parquet(path, index=False)

    return cached[cached["ticker"].isin(wanted)].reset_index(drop=True)


def _yfinance_fetcher(symbol: str) -> dict:  # pragma: no cover - network
    import yfinance as yf

    return yf.Ticker(symbol).info


def removal_dates(changes: pd.DataFrame) -> dict[str, pd.Timestamp]:
    """First removal date per removed ticker, the end of the original stint."""
    removed = changes.dropna(subset=["removed_ticker"])
    out: dict[str, pd.Timestamp] = {}
    for row in removed.itertuples(index=False):
        ticker = str(row.removed_ticker)
        date = pd.Timestamp(row.effective_date)
        if ticker not in out or date < out[ticker]:
            out[ticker] = date
    return out


def removal_names(changes: pd.DataFrame) -> dict[str, str]:
    """Security name recorded on the removal row per ticker."""
    removed = changes.dropna(subset=["removed_ticker"])
    out: dict[str, str] = {}
    for row in removed.itertuples(index=False):
        ticker = str(row.removed_ticker)
        name = row.removed_security
        if ticker not in out and isinstance(name, str) and name.strip():
            out[ticker] = name.strip()
    return out


def _missing_between(dates: pd.DatetimeIndex) -> list[int]:
    """Missing business days between consecutive live observations.

    Calendar-day differences cannot be used here: every weekend would look
    like a break. Bdate_range counts trading days only, so a Friday to
    Monday step is zero and a two-year hole is about five hundred.
    """
    return [
        int(pd.bdate_range(dates[i - 1], dates[i]).size - 2)
        for i in range(1, len(dates))
    ]


def _segments_and_gap(series: pd.Series, gap_days: int) -> tuple[list[pd.Series], int]:
    """Live segments separated by more than `gap_days` missing business days.

    Returns the segments and the longest run of missing business days. The
    two are consistent by construction: more than one segment means the
    longest run exceeded the threshold.
    """
    live = series.dropna()
    if live.empty:
        return [], 0
    if len(live) < 2:
        return [live], 0
    gaps = _missing_between(pd.DatetimeIndex(live.index))
    longest = max(gaps) if gaps else 0
    segments: list[list[pd.Timestamp]] = []
    current: list[pd.Timestamp] = [pd.Timestamp(live.index[0])]
    for position, gap in enumerate(gaps, start=1):
        if gap > gap_days:
            segments.append(current)
            current = []
        current.append(pd.Timestamp(live.index[position]))
    segments.append(current)
    return [live.loc[seg] for seg in segments], int(longest)


def identity_table(
    changes: pd.DataFrame,
    prices: pd.DataFrame,
    names: pd.DataFrame,
    threshold: float = MATCH_THRESHOLD,
    gap_days: int = GAP_BUSINESS_DAYS,
    members: pd.DataFrame | None = None,
    breaks: set[str] | None = None,
) -> pd.DataFrame:
    """One row per removed ticker: who holds the symbol now, and what to do.

    prices: long frame with an adj_close column on a (date, ticker) index.
    names: output of fetch_symbol_names.
    members: optional membership matrix (date x ticker) used to check that a
    retained segment actually overlaps the member's stint.
    breaks: tickers with a level break no split explains, from
    efb.hygiene.series_break_tickers. A verified name mismatch excludes the
    ticker, which is the brief's rule, and `has_break` records whether the
    splice was visible in the prices. The rule is deliberately conservative
    in both directions of risk: a name change without a price break is
    usually a real rename (du Pont to DuPont, 21st Century Fox to Fox, V.F.
    Corp to VF Corp) but it is sometimes a reuse the vendor hid by keeping
    only one company's history (ADC Telecommunications to ADC
    Therapeutics, Amoco to AutoNation), and the two cannot be told apart
    from prices and names alone. Keeping a fabricated history is worse than
    dropping a legitimate one, so mismatches are excluded and the renames
    are listed for the security-master work in docs/open_items.md.
    """
    dates = removal_dates(changes)
    securities = removal_names(changes)
    name_map = dict(zip(names["ticker"], names["long_name"], strict=False))
    short_map = dict(zip(names["ticker"], names["short_name"], strict=False))
    break_set = set(breaks or ())

    wide = prices["adj_close"].unstack("ticker")
    membership = members if members is not None else None

    rows: list[dict[str, object]] = []
    for ticker in sorted(dates):
        series = wide[ticker] if ticker in wide.columns else pd.Series(dtype=float)
        segments, gap = _segments_and_gap(series, gap_days)
        removed_name = securities.get(ticker)
        current_name = usable_name(name_map.get(ticker)) or usable_name(
            short_map.get(ticker)
        )
        score = match_score(removed_name, current_name)
        verified = current_name is not None
        # no name today is not evidence of reuse: most delisted members have
        # no listing left, so those rows stay unverified rather than dropped
        mismatch = verified and score < threshold
        has_break = ticker in break_set
        reused = mismatch
        rename_suspect = mismatch and not has_break

        action = "keep"
        drop_before: pd.Timestamp | None = None
        if not verified:
            note = "no current holder name available, could not verify"
        elif not mismatch:
            note = "name matches the current holder"
        elif not has_break:
            note = "symbol reused, no price discontinuity visible"
        else:
            note = "symbol reused"
        kept = series
        if reused:
            if len(segments) >= 2:
                kept = segments[-1]
                drop_before = pd.Timestamp(kept.index.min())
                action = "truncate"
                note = "symbol reused, rows before the current company dropped"
            else:
                action = "drop"
                note = "symbol reused and break date cannot be determined"
        if action == "truncate" and membership is not None and ticker in membership:
            stint = membership[ticker].astype(bool)
            overlap = bool(stint.reindex(kept.index).fillna(False).any())
            if not overlap:
                action = "drop"
                drop_before = None
                note = (
                    "symbol reused and the kept segment does not overlap "
                    "the member stint"
                )

        first_valid = (
            pd.Timestamp(series.dropna().index.min()) if series.notna().any() else None
        )
        last_valid = (
            pd.Timestamp(series.dropna().index.max()) if series.notna().any() else None
        )
        rows.append(
            {
                "ticker": ticker,
                "removed_name": removed_name,
                "removal_date": dates[ticker],
                "current_name": current_name,
                "match_score": round(float(score), 4),
                "verified": verified,
                "reused": reused,
                "rename_suspect": rename_suspect,
                "has_break": has_break,
                "first_valid_date": first_valid,
                "last_valid_date": last_valid,
                "n_observations": int(series.notna().sum()),
                "gap_days": gap,
                "has_gap": gap > gap_days,
                "action": action,
                "drop_before": drop_before,
                "note": note,
            }
        )
    return pd.DataFrame(rows)


def exclusions(table: pd.DataFrame) -> tuple[list[str], dict[str, pd.Timestamp]]:
    """Split the identity table into tickers to drop and dates to truncate from."""
    if table.empty or "action" not in table.columns:
        return [], {}
    dropped = sorted(table.loc[table["action"] == "drop", "ticker"].tolist())
    truncated: dict[str, pd.Timestamp] = {}
    for row in table.loc[table["action"] == "truncate"].itertuples(index=False):
        if row.drop_before is not None and not pd.isna(row.drop_before):
            truncated[str(row.ticker)] = pd.Timestamp(row.drop_before)
    return dropped, truncated


def drop_truncated(
    frame: pd.DataFrame, truncated: dict[str, pd.Timestamp]
) -> pd.DataFrame:
    """Remove early rows of reused symbols, per the truncation dates."""
    if not truncated:
        return frame
    dates = frame.index.get_level_values("date")
    tickers = frame.index.get_level_values("ticker")
    keep = pd.Series(True, index=frame.index)
    for ticker, cutoff in truncated.items():
        keep &= ~((tickers == ticker) & (dates < cutoff))
    return frame.loc[keep.to_numpy()]


REPORT_COLUMNS = [
    "ticker",
    "removed_name",
    "current_name",
    "match_score",
    "first_valid_date",
    "last_valid_date",
    "removal_date",
]


def run(data_root: Path | str = "data", verbose: bool = True) -> pd.DataFrame:
    """Identity check end to end: fetch names, build the table, save it."""
    root = Path(data_root)
    changes = pd.read_parquet(root / "processed" / "universe_changes.parquet")
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    members = pd.read_parquet(root / "processed" / "universe_membership.parquet")

    tickers = sorted(set(changes["removed_ticker"].dropna().astype(str)))
    names = fetch_symbol_names(tickers, cache_path=root / "raw" / "yf_names.parquet")
    table = identity_table(
        changes,
        prices,
        names,
        members=members,
        breaks=set(hygiene.series_break_tickers(prices)),
    )
    table.to_parquet(root / "processed" / "ticker_identity.parquet", index=False)

    if verbose:
        print("=== C1 ticker identity: removed members vs the current holder ===")
        print(table[REPORT_COLUMNS].to_string(index=False))
        dropped, truncated = exclusions(table)
        print()
        matched = table["verified"] & (table["match_score"] >= MATCH_THRESHOLD)
        unverified = ~table["verified"]
        reused = table["reused"].astype(bool)
        print(f"rows compared: {len(table)}")
        print(f"name matches the current holder: {int(matched.sum())}")
        print(f"could not verify, no name today: {int(unverified.sum())}")
        print(f"symbol reused: {int(reused.sum())}")
        visible = int((reused & table["has_break"]).sum())
        hidden = int((reused & ~table["has_break"]).sum())
        print(f"  of which with a visible price break: {visible}")
        print(f"  of which no price break visible: {hidden}")
        if reused.any():
            print(
                "  "
                + ", ".join(
                    f"{r.ticker} ({r.removed_name} -> {r.current_name})"
                    for r in table[reused].itertuples(index=False)
                )
            )
        print(f"dropped by the build: {dropped}")
        print(
            "truncated to the current company: "
            f"{ {k: str(v.date()) for k, v in truncated.items()} }"
        )
        print(
            "gaps above 60 business days: "
            f"{sorted(table.loc[table['has_gap'].astype(bool), 'ticker'])}"
        )
        known = {"CPWR", "EP", "MI", "POM"}
        caught = set(table.loc[table["reused"].astype(bool), "ticker"])
        print(f"the four known cases caught: {sorted(known & caught)}")
        print(f"missing from the check: {sorted(known - caught)}")
        print(f"additional tickers caught: {sorted(caught - known)}")
    return table


def main() -> None:  # pragma: no cover - CLI
    run()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
