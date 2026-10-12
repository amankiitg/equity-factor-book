"""yfinance price pipeline (Sprint E1, Task 1).

Downloads daily OHLCV, adjusted close, dividends and split factors for a
ticker list, stores a long-format DataFrame, and cleans it (business days
only, duplicates dropped, missing prices kept as NaN so that coverage can
be measured rather than assumed away).
"""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
import yfinance.cache as yf_cache

logger = logging.getLogger(__name__)

# The directory yfinance's caches were pointed at, per process. `None` until the
# first call.
_TZ_CACHE_DIR: Path | None = None

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


def use_private_tz_cache(root: Path | None = None) -> Path:
    """Point yfinance's SQLite caches at a directory only this process writes.

    yfinance keeps its timezone, cookie and ISIN caches in one SQLite directory, and
    the default is shared: `~/.cache/py-yfinance`, or on Render
    `/opt/render/.cache/py-yfinance`, which every run on an instance opens. Two runs
    starting together then contend for one SQLite file and it refuses with
    `OperationalError('database is locked')`, which yfinance reports as a failed
    download for whichever symbol lost the race. The run is not stopped by that,
    which is exactly what makes it dangerous: the evening's book is quietly a name
    short. Its folder creation is not race-safe either (`os.makedirs` without
    `exist_ok`), which is the `File exists` line that appears beside it.

    So the cache goes somewhere private: `root`, when the caller has a tree of its
    own, and a fresh temporary directory otherwise. One call per process is
    remembered, because a run's price download, its share lookups and its
    corporate-action cross-check have to share one cache rather than each rebuilding
    it. The directory is created here, atomically, before the library sees it.
    """
    global _TZ_CACHE_DIR
    if root is None and _TZ_CACHE_DIR is not None:
        return _TZ_CACHE_DIR
    target = (
        Path(root) / "yfinance-cache"
        if root is not None
        else Path(tempfile.mkdtemp(prefix="efb-yfinance-"))
    )
    target.mkdir(parents=True, exist_ok=True)
    if _TZ_CACHE_DIR != target:
        yf.set_tz_cache_location(str(target))
        _TZ_CACHE_DIR = target
    return target


def prewarm_tz_cache(tickers: list[str], timeout: float = 10.0) -> dict[str, int]:
    """Resolve and store every ticker's exchange timezone once, single-threaded.

    yfinance keeps one timezone row per ticker in `tkr-tz.db`, inside the directory
    `use_private_tz_cache` gives the run, and it writes that row the first time it
    prices the ticker. A run whose cache is empty, which is every run now that the
    directory is created per process, therefore hands the threaded download one
    write per ticker: 504 of them for the SPY universe, all into a single SQLite
    file. Two threads writing together is `OperationalError('database is locked')`,
    and yfinance reports it as a failed download for whichever symbol lost the race
    rather than failing the run, so the evening is quietly a name short with no
    error anywhere. Measured on 2026-09-29: a cold 504-name fetch lost exactly one
    symbol in 3 of 12 runs (EVRG, BA, ACGL), while repeats against a warm cache lost
    none, which is what this function removes: the rows are written here, one
    ticker at a time, before any thread starts, so the threaded pass only reads a
    cache nobody is writing.

    The lookup is yfinance's own (`Ticker._get_ticker_tz`), so no timezone is
    guessed here and no exchange list is maintained: a ticker the vendor will not
    answer for counts as unresolved and writes nothing, threaded or not.

    Returns how many were resolved now, how many were already cached, and how many
    were left unresolved.
    """
    cache = yf_cache.get_tz_cache()
    resolved = already_cached = unresolved = 0
    started = time.perf_counter()
    for ticker in tickers:
        symbol = yf_ticker(ticker)
        if cache.lookup(symbol):
            already_cached += 1
            continue
        try:
            tz = yf.Ticker(symbol)._get_ticker_tz(timeout=timeout)
        except Exception:  # noqa: BLE001 - the download reports what it cannot price
            tz = None
        if tz:
            resolved += 1
        else:
            unresolved += 1
    report = {
        "requested": len(tickers),
        "resolved": resolved,
        "already_cached": already_cached,
        "unresolved": unresolved,
    }
    logger.info(
        "timezone cache warmed in %.1fs: %d resolved, %d already cached, "
        "%d unresolved, of %d requested",
        time.perf_counter() - started,
        resolved,
        already_cached,
        unresolved,
        len(tickers),
    )
    return report


def missing_tickers(
    frame: pd.DataFrame, tickers: list[str], *, session: object
) -> list[str]:
    """The requested tickers the frame carries no usable close for on `session`.

    `session` is the close the caller needs, the last session of the window that was
    asked for, and it is required rather than optional because the looser question
    hides the case that matters: a name whose earlier sessions came back and whose own
    bar did not has nothing to quantize on, and asking whether it has a close anywhere
    in the frame calls it covered.

    Measured on 2026-09-29, in the run that carried the prewarm and the retry: CSGP
    answered for the earlier sessions of the fetched window and had no bar for the
    close being priced, the window-wide check called it covered, the single-threaded
    retry never ran, and the book dropped the name with nothing in the log to say a
    retry had been skipped. The session reading is the question the book needs
    answered.

    A symbol the vendor refused and a symbol that no longer trades still look the same
    here, because both come back with rows and no close: each leaves the book with
    nothing to quantize on, so the fetch retries the set and the book drops whatever
    the retry could not recover. `close` is the column read, not `adj_close`, because
    `close` is the price the quantization divides by.
    """
    wanted = sorted(set(tickers))
    if frame is None or len(frame) == 0:
        return wanted
    dates = frame.index.get_level_values("date")
    day = frame.loc[dates == pd.Timestamp(session)]
    if len(day) == 0:
        return wanted
    priced = {
        str(name) for name in day.index.get_level_values("ticker")[day["close"].notna()]
    }
    return [ticker for ticker in wanted if ticker not in priced]


def download_prices(
    tickers: list[str],
    start: str = "2009-12-15",
    end: str | None = None,
    progress: bool = False,
    cache_root: Path | None = None,
    prewarm: bool = False,
    threads: bool = True,
) -> pd.DataFrame:
    """Download daily prices and actions from yfinance in long format.

    `end` is yfinance's own and is **exclusive**: a caller that wants a session
    included has to name the day after it. That is not a detail, it is the mistake
    `live.extend` made with the run's own close, so it is stated here where the
    parameter is read.

    `cache_root` is where yfinance's SQLite caches go, one directory per run by
    default (see `use_private_tz_cache`): the shared default is a single file that
    concurrent runs contend for.

    `prewarm` resolves the timezone rows serially before the threaded download
    starts (see `prewarm_tz_cache`), which is what stops the download's own threads
    from writing that one file together. The live fetch asks for it; a research
    build with thousands of tickers does not, because there the serial lookups cost
    more than the download they protect.

    `threads` is passed through to the vendor. A retry of a handful of names wants
    one thread: nothing is gained by threading five symbols, and single-threaded is
    the pass that cannot lose one to a cache write.

    The start date includes a warm-up window before the 2010 universe
    start so that the first return of 2010 is computable. Tickers are
    mapped to yfinance symbols on request and mapped back on return.
    """
    use_private_tz_cache(cache_root)
    unique = sorted({t for t in tickers})
    if prewarm:
        prewarm_tz_cache(unique)
    symbol_of = {yf_ticker(t): t for t in unique}
    wide = yf.download(
        list(symbol_of),
        start=start,
        end=end,
        group_by="ticker",
        auto_adjust=False,
        actions=True,
        threads=threads,
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
    frame: pd.DataFrame, start: str = "2010-01-04", end: str | None = None
) -> pd.DataFrame:
    """Clip the long price frame to the universe window and clean it.

    Prices before start are the warm-up window for the first return; they
    stay in the cache but are excluded from data/raw/prices.parquet.

    `end` bounds the other side, and is the panel pin: the cache is served as it
    stands when every ticker is present, so a cache refreshed by a live run can
    hold sessions newer than the panel a research rebuild means to reproduce.
    """
    cleaned = clean_prices(frame, start=start)
    dates = cleaned.index.get_level_values("date")
    keep = dates >= pd.Timestamp(start)
    if end is not None:
        keep &= dates <= pd.Timestamp(end)
    return cleaned.loc[keep].sort_index()


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
        r_adj = sub["adj_close"].pct_change(fill_method=None)
        r_div = (sub["close"] + sub["dividend"].fillna(0.0)).div(
            sub["close"].shift(1)
        ) - 1.0
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


def audit_adjusted_close_details(
    frame: pd.DataFrame,
    tickers: list[str],
    n_names: int = 20,
    seed: int = 42,
    threshold_bp: float = 50.0,
) -> pd.DataFrame:
    """Audited days whose adjusted-close difference exceeds a threshold.

    Returns ticker, date and diff_bp rows for the same random sample used
    by audit_adjusted_close. Used by F2.0c to require every large audited
    difference to appear in events.parquet with a cause.
    """
    rng = np.random.default_rng(seed)
    sample = sorted(rng.choice(tickers, size=min(n_names, len(tickers)), replace=False))
    rows: list[dict[str, object]] = []
    for ticker in sample:
        sub = frame.xs(ticker, level="ticker")
        sub = sub.dropna(subset=["close", "adj_close"])
        r_adj = sub["adj_close"].pct_change(fill_method=None)
        r_div = (sub["close"] + sub["dividend"].fillna(0.0)).div(
            sub["close"].shift(1)
        ) - 1.0
        both = pd.concat([r_adj, r_div], axis=1).dropna()
        if both.empty:
            continue
        diff = (both.iloc[:, 0] - both.iloc[:, 1]).abs() * 10_000.0
        for date, value in diff[diff > threshold_bp].items():
            rows.append({"ticker": ticker, "date": date, "diff_bp": float(value)})
    return pd.DataFrame(rows, columns=["ticker", "date", "diff_bp"])
