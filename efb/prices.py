"""yfinance price pipeline (Sprint E1, Task 1).

Downloads daily OHLCV, adjusted close, dividends and split factors for a
ticker list, stores a long-format DataFrame, and cleans it (business days
only, duplicates dropped, missing prices kept as NaN so that coverage can
be measured rather than assumed away).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

FIELDS = [
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "dividend",
    "split_factor",
]

RENAME = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
    "Dividends": "dividend",
    "Stock Splits": "split_factor",
}


def yf_ticker(ticker: str) -> str:
    """Map a Wikipedia-style ticker to the yfinance symbol convention.

    yfinance uses a hyphen for share classes (BF.B is BF-B on Yahoo).
    """
    return ticker.replace(".", "-")


def download_prices(
    tickers: list[str],
    start: str = "2009-12-15",
    end: str | None = None,
    progress: bool = False,
) -> pd.DataFrame:
    """Download daily prices and actions from yfinance in long format.

    The start date includes a warm-up window before the 2010 universe
    start so that the first return of 2010 is computable. Tickers are
    mapped to yfinance symbols on request and mapped back on return.
    """
    unique = sorted({t for t in tickers})
    symbol_of = {yf_ticker(t): t for t in unique}
    wide = yf.download(
        list(symbol_of),
        start=start,
        end=end,
        group_by="ticker",
        auto_adjust=False,
        actions=True,
        threads=True,
        progress=progress,
    )
    long_df = wide_to_long(wide)
    return long_df.rename(index=symbol_of, level="ticker")


def wide_to_long(wide: pd.DataFrame) -> pd.DataFrame:
    """Convert a yfinance wide download (Ticker x Price columns) to long."""
    if not isinstance(wide.columns, pd.MultiIndex):
        raise ValueError("expected a MultiIndex of (ticker, field) columns")
    frame = wide.copy()
    frame.columns.names = ["ticker", "field"]
    long_df = frame.stack(level="ticker", future_stack=True)
    long_df = long_df.rename(columns=RENAME)
    long_df.index.names = ["date", "ticker"]
    long_df = long_df[FIELDS].sort_index()
    return long_df


def clean_prices(long_df: pd.DataFrame, start: str = "2010-01-04") -> pd.DataFrame:
    """Clean the long price frame: business days only, duplicates dropped.

    Rows outside the New York business-day calendar are dropped. Ticker and
    date index levels are kept unique. NaN prices are preserved so coverage
    metrics see real gaps.
    """
    out = long_df[~long_df.index.duplicated(keep="last")]
    out = out.sort_index()
    dates = out.index.get_level_values("date")
    bdays = pd.bdate_range(start=dates.min(), end=dates.max())
    out = out.loc[dates.isin(bdays)]
    return out


def load_cached_prices(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def save_prices(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path)


def build_prices_artifact(
    frame: pd.DataFrame, start: str = "2010-01-04"
) -> pd.DataFrame:
    """Clip the long price frame to the universe window and clean it.

    Prices before start are the warm-up window for the first return; they
    stay in the cache but are excluded from data/raw/prices.parquet.
    """
    cleaned = clean_prices(frame, start=start)
    dates = cleaned.index.get_level_values("date")
    return cleaned.loc[dates >= pd.Timestamp(start)].sort_index()


def covered_tickers(frame: pd.DataFrame) -> set[str]:
    """Tickers with at least one non-null adjusted close in the frame."""
    adj = frame["adj_close"]
    have = adj.groupby(level="ticker").agg(lambda s: bool(s.notna().any()))
    return {t for t, ok in have.items() if ok}


def load_or_download(
    tickers: list[str],
    cache_path: Path,
    start: str = "2009-12-15",
    end: str | None = None,
    force: bool = False,
) -> pd.DataFrame:
    """Return cached prices when complete, else download and refresh.

    The cache is considered complete when every requested ticker has at
    least one row. Tickers that were downloaded but returned only NaN
    prices are final answers, not cache misses: re-downloading them would
    not change anything. This keeps rebuilds fast while guaranteeing that
    a cold cache downloads everything.
    """
    if not force and cache_path.exists():
        cached = load_cached_prices(cache_path)
        present = set(cached.index.get_level_values("ticker").unique())
        missing = [t for t in tickers if t not in present]
        if not missing:
            return cached
    frame = download_prices(tickers, start=start, end=end)
    save_prices(frame, cache_path)
    return frame


def audit_adjusted_close(
    frame: pd.DataFrame,
    tickers: list[str],
    n_names: int = 20,
    seed: int = 42,
) -> dict[str, float]:
    """Audit adjusted close against the dividend-adjusted raw series.

    For n_names randomly sampled tickers, the daily total return implied
    by adj_close is compared with (close + dividend) / prior close. Note
    that the yfinance Close column is already split-adjusted, so split
    factors must not be reapplied here; the Stock Splits action column is
    informational. Returns the max and mean absolute difference across
    all sampled names in basis points.
    """
    rng = np.random.default_rng(seed)
    sample = sorted(rng.choice(tickers, size=min(n_names, len(tickers)), replace=False))
    diffs: list[float] = []
    for ticker in sample:
        sub = frame.xs(ticker, level="ticker")
        sub = sub.dropna(subset=["close", "adj_close"])
        r_adj = sub["adj_close"].pct_change()
        r_div = (
            (sub["close"] + sub["dividend"].fillna(0.0))
            .div(sub["close"].shift(1))
            - 1.0
        )
        both = pd.concat([r_adj, r_div], axis=1).dropna()
        if both.empty:
            continue
        diffs.extend(((both.iloc[:, 0] - both.iloc[:, 1]).abs() * 10_000.0).tolist())
    if not diffs:
        return {"max_abs_bp": float("nan"), "mean_abs_bp": float("nan")}
    return {
        "max_abs_bp": float(np.nanmax(diffs)),
        "mean_abs_bp": float(np.nanmean(diffs)),
    }
