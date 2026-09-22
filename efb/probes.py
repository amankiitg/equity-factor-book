"""Task 0: probe every E1 data source and print its availability report.

A source is not available until its probe has printed rows into
sprints/E1/PROBES.md. Each probe prints row count, first and last date,
ticker coverage, NaN share and notes. Network calls live here and in the
source modules; the parsing helpers are unit tested offline.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
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


# --------------------------------------------------------------------------
# Sprint E3, Task 0: descriptor availability, the shares source, the sector
# restriction and the value source.
#
# The rules encoded here are the windows in sprints/E3/PRD.md. A descriptor
# is not available until its probe has printed rows, so this module owns the
# availability definition that the descriptor build then implements.
# --------------------------------------------------------------------------

SHARES_CACHE = ROOT / "data" / "raw" / "shares_history.parquet"

BETA_WINDOW = 252
BETA_MIN_OBS = 126
MOMENTUM_WINDOW = 252
MOMENTUM_SKIP = 21
MOMENTUM_MIN_OBS = 231
REVERSAL_WINDOW = 21
REVERSAL_MIN_OBS = 20
RESID_VOL_WINDOW = 63
LIQUIDITY_WINDOW = 63
LIQUIDITY_MIN_OBS = 42
MIN_CROSS_SECTION = 300
SHARES_SPLIT_RATIO = 1.5

DESCRIPTOR_NAMES = (
    "market",
    "size",
    "beta",
    "momentum",
    "reversal",
    "resid_vol",
    "liquidity",
    "sector",
)


def _frame(mask: np.ndarray, template: pd.DataFrame) -> pd.DataFrame:
    """Rebuild a wide boolean frame so a numpy mask keeps its labels."""
    return pd.DataFrame(
        np.asarray(mask), index=template.index, columns=template.columns
    )


def _count_recent(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    """Non-null count over the last `window` rows, excluding the current row."""
    return frame.shift(1).rolling(window, min_periods=1).count()


def _naive_date(value: object) -> pd.Timestamp:
    """A vendor timestamp as a tz-naive midnight, or NaT.

    The vendor stamps rows in market time (2020-08-31 00:00:00-04:00) while
    the EFB panel is tz-naive and dated at midnight. The wall clock is kept
    and the offset is dropped rather than converted, because converting would
    move a row filed late in the day onto the next calendar date. NaT passes
    through, which is how an `empty` marker row is written.

    pd.Timestamp is used rather than pd.to_datetime because the latter can
    hand back a plain datetime.datetime for a tz-aware input, which silently
    keeps the offset and then breaks the cache write.
    """
    if value is None or value is pd.NaT:
        return pd.NaT
    stamp = pd.Timestamp(value)
    if stamp is pd.NaT:
        return pd.NaT
    if stamp.tzinfo is not None:
        stamp = stamp.tz_localize(None)
    return stamp.normalize()


def dedupe_share_history(raw: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """One share count per ticker per date, plus the counts that prove it.

    The vendor series carries duplicate timestamps with conflicting values
    (AAPL has 2020-08-31 twice, once pre-split and once post-split). The
    rule is to keep the largest value on a date, because a share count only
    jumps at a split and a duplicate is two vintages of the same filing.

    Returns the clean frame, the number of duplicate rows dropped, and the
    number of split-sized steps (a jump of at least `SHARES_SPLIT_RATIO`
    between consecutive dates), which is the evidence for the as-filed
    claim in the Hygiene Ledger.
    """
    if raw.empty:
        return raw.copy(), 0, 0
    frame = raw.dropna(subset=["date", "shares"]).copy()
    frame["date"] = pd.to_datetime(
        frame["date"].map(_naive_date), errors="coerce", utc=False
    )
    before = len(frame)
    frame = (
        frame.sort_values(["ticker", "date", "shares"])
        .groupby(["ticker", "date"], as_index=False)
        .last()
    )
    dropped = before - len(frame)
    steps = 0
    for _, sub in frame.sort_values(["ticker", "date"]).groupby("ticker"):
        prev = sub["shares"].shift(1)
        ratio = sub["shares"] / prev.replace(0, np.nan)
        steps += int(
            ((ratio >= SHARES_SPLIT_RATIO) | (ratio <= 1 / SHARES_SPLIT_RATIO))
            .fillna(False)
            .sum()
        )
    return frame.reset_index(drop=True), dropped, steps


def share_count_panel(
    history: pd.DataFrame,
    index: pd.DatetimeIndex,
    tickers: list[str] | tuple[str, ...],
) -> pd.DataFrame:
    """Share count usable on each date, with the filing date it came from.

    The panel is dated t-1 on purpose: the count filed on date t is not usable
    until the next session, so the value on date t is the last observation
    dated at or before t-1. A date before a name's first filing is backfilled
    with that first filing and flagged `look_ahead`, because the count was not
    knowable then; the flag is carried into the market cap and into the Size
    descriptor.

    Implemented with merge_asof, which is the vectorized form of "the last
    filing on or before the cutoff". The earlier per-date loop produced the
    same frame and took minutes on the full panel.

    Returns columns date, ticker, shares, shares_as_of, look_ahead.
    """
    frame, _, _ = dedupe_share_history(history)
    index = pd.DatetimeIndex(sorted(index))
    if isinstance(index.dtype, pd.DatetimeTZDtype):
        index = index.tz_localize(None)
    wanted = list(dict.fromkeys(tickers))
    grid = pd.MultiIndex.from_product(
        [index, wanted], names=["date", "ticker"]
    ).to_frame(index=False)
    if frame.empty:
        grid["shares"] = np.nan
        grid["shares_as_of"] = pd.NaT
        grid["look_ahead"] = False
        return grid

    observations = frame.loc[frame["ticker"].isin(wanted), ["ticker", "date", "shares"]]
    observations = observations.sort_values(["date", "ticker"])
    # parquet stores timestamps at microsecond resolution while the panel
    # index is nanosecond, and merge_asof refuses to join across units
    grid["date"] = pd.to_datetime(grid["date"]).astype("datetime64[ns]")
    observations["date"] = pd.to_datetime(observations["date"]).astype("datetime64[ns]")
    merged = pd.merge_asof(
        grid.sort_values(["date", "ticker"]),
        observations.rename(columns={"date": "shares_as_of"}),
        left_on="date",
        right_on="shares_as_of",
        by="ticker",
        direction="backward",
        allow_exact_matches=False,
    )
    first = observations.groupby("ticker")["shares"].first()
    merged["look_ahead"] = merged["shares"].isna()
    backfill = merged["ticker"].map(first)
    merged["shares"] = merged["shares"].fillna(backfill)
    return merged[
        ["date", "ticker", "shares", "shares_as_of", "look_ahead"]
    ].reset_index(drop=True)


def availability_masks(
    returns: pd.DataFrame,
    market: pd.Series,
    volume: pd.DataFrame,
    close: pd.DataFrame,
    shares: pd.DataFrame,
    sectors: pd.Series,
) -> dict[str, pd.DataFrame]:
    """Boolean availability per descriptor, dated t, from data through t-1.

    INPUT (all wide, index = trading date, columns = ticker)
      returns: total return r.
      market: the cap-weighted universe total return of the same universe.
      volume: share volume, for the liquidity window.
      close: unadjusted close, for the market cap used by Size.
      shares: share count usable on that date (already dated t-1 by
        `share_count_panel`), NaN when no count is reachable.
      sectors: sector per ticker, index = ticker.
    OUTPUT: a dict with one boolean frame per descriptor plus `full`, the
    conjunction, which is the cross-section the regression can use.
    """
    n_ret = _count_recent(returns, BETA_WINDOW)
    market_ok = (
        market.shift(1).rolling(BETA_WINDOW, min_periods=1).count() >= BETA_MIN_OBS
    )
    beta_ok = _frame(
        (n_ret.to_numpy() >= BETA_MIN_OBS) & market_ok.to_numpy()[:, None], returns
    )
    momentum_ok = (
        returns.shift(MOMENTUM_SKIP)
        .rolling(MOMENTUM_WINDOW - MOMENTUM_SKIP, min_periods=1)
        .count()
        >= MOMENTUM_MIN_OBS
    )
    reversal_ok = _count_recent(returns, REVERSAL_WINDOW) >= REVERSAL_MIN_OBS
    last_63 = _count_recent(returns, RESID_VOL_WINDOW)
    resid_ok = _frame(
        beta_ok.to_numpy() & (last_63.to_numpy() >= RESID_VOL_WINDOW), returns
    )
    liquidity_ok = _count_recent(volume, LIQUIDITY_WINDOW) >= LIQUIDITY_MIN_OBS
    size_ok = _frame(
        shares.notna().to_numpy() & close.shift(1).notna().to_numpy(), returns
    )
    mapped = np.array([t in set(sectors.index) for t in returns.columns])
    sector_ok = _frame(np.tile(mapped, (len(returns), 1)), returns)
    masks = {
        "market": returns.notna(),
        "size": size_ok,
        "beta": beta_ok,
        "momentum": momentum_ok,
        "reversal": reversal_ok,
        "resid_vol": resid_ok,
        "liquidity": liquidity_ok,
        "sector": sector_ok,
    }
    full = masks["market"].copy()
    for name in DESCRIPTOR_NAMES:
        full = full & masks[name]
    masks["full"] = full
    return masks


def coverage_table(masks: dict[str, pd.DataFrame], by: str = "year") -> pd.DataFrame:
    """Count the names carrying each descriptor at each period end.

    `by` is "year" for year ends (the Task 0 table) or "month" for month
    ends. Every descriptor count is conditioned on the name having a return
    that day, because a descriptor is only usable where the regression has a
    left hand side; without that condition the size column can exceed the
    return count and the columns stop being comparable.
    """
    full = masks["full"]
    base = masks["market"]
    period = full.index.to_period("Y" if by == "year" else "M")
    last_dates = full.index.to_series().groupby(period).max()
    rows: list[dict[str, object]] = []
    for _, date in last_dates.items():
        row: dict[str, object] = {
            "year" if by == "year" else "month": (
                date.year if by == "year" else date.strftime("%Y-%m")
            ),
            "date": str(pd.Timestamp(date).date()),
            "n_names": int(base.loc[date].sum()),
        }
        for name in DESCRIPTOR_NAMES:
            if name == "market":
                row[name] = int(base.loc[date].sum())
            else:
                row[name] = int((masks[name] & base).loc[date].sum())
        row["full"] = int(full.loc[date].sum())
        rows.append(row)
    return pd.DataFrame(rows)


def first_full_row_day(
    masks: dict[str, pd.DataFrame], min_names: int = MIN_CROSS_SECTION
) -> pd.Timestamp | None:
    """First trading day whose complete-row count reaches `min_names`."""
    counts = masks["full"].sum(axis=1)
    eligible = counts[counts >= min_names]
    return None if eligible.empty else pd.Timestamp(eligible.index[0])


def members_outside_sector_file(
    membership: pd.DataFrame,
    sector_tickers: set[str],
    market_cap: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Point-in-time members with no row in the sector file, by year.

    The sector dummies restrict the cross-section to names the sector file
    knows, so this is the size of the survivor-only restriction. It is
    reported two ways because they answer different questions: the share of
    member names, and, when `market_cap` is passed, the share of index
    market cap, which is the number that matters for a cap-weighted
    benchmark. It is a bias measurement, not a fix.
    """
    cols = list(membership.columns)
    outside = [c for c in cols if c not in sector_tickers]
    cap = None if market_cap is None else market_cap.reindex(columns=cols)
    rows: list[dict[str, object]] = []
    for year, block in membership.groupby(membership.index.year):
        per_day = block.sum(axis=1)
        outside_day = block[outside].sum(axis=1)
        row: dict[str, object] = {
            "year": int(year),
            "n_days": int(len(block)),
            "n_members_mean": float(per_day.mean()),
            "n_members_max": int(per_day.max()),
            "n_mapped_mean": float((per_day - outside_day).mean()),
            "n_outside_mean": float(outside_day.mean()),
            "n_outside_distinct": int(
                len([c for c in outside if bool(block[c].any())])
            ),
            "share_outside": float(outside_day.sum() / max(per_day.sum(), 1)),
        }
        if cap is not None:
            cap_year = cap.loc[block.index].where(block)
            total = cap_year.sum().sum()
            outside_cap = cap_year[outside].sum().sum() if outside else 0.0
            row["share_outside_mcap"] = float(outside_cap / max(total, 1e-12))
        rows.append(row)
    return pd.DataFrame(rows)


def shares_coverage_ramp(
    shares: pd.DataFrame, look_ahead: pd.DataFrame
) -> pd.DataFrame:
    """Names with a share count that is not a backfilled value, by month.

    A backfilled count is one used before the name's first filing, and it is
    the look-ahead the ledger flags. The ramp is therefore the month by
    month count of names whose count was actually filed, and its first month
    is where the panel stops being in part a projection.
    """
    real = shares.notna() & ~look_ahead.reindex(
        index=shares.index, columns=shares.columns
    ).fillna(False)
    counts = real.sum(axis=1)
    return counts.groupby(counts.index.to_period("M")).max()


def sector_members(universe: pd.DataFrame, sectors: pd.Series) -> pd.DataFrame:
    """Names with a return per sector per date (columns = sector, rows = date)."""
    mapped = [c for c in universe.columns if c in set(sectors.index)]
    sub = universe[mapped]
    labels = sectors.reindex(mapped)
    return sub.notna().T.groupby(labels).sum().T


def small_sector_days(counts: pd.DataFrame, min_members: int = 5) -> int:
    """Number of days on which at least one sector has fewer than min_members."""
    return int((counts < min_members).any(axis=1).sum())


def _yfinance_shares_fetcher(symbol: str) -> pd.Series:  # pragma: no cover
    """As-filed share count history from the vendor, one row per filing."""
    return yf.Ticker(symbol).get_shares_full(start="2009-01-01")


def fetch_share_history(
    tickers: list[str] | tuple[str, ...],
    cache_path: Path | str = SHARES_CACHE,
    fetcher: Callable[[str], pd.Series | None] | None = None,
    attempts: int = 3,
) -> pd.DataFrame:
    """Share-count history per ticker, cached so each symbol is asked once.

    Rows are ticker, date, shares, source, fetched_at, status. A ticker the
    vendor answers with nothing gets a single `empty` marker row with a NaT
    date, so a rebuild does not re-ask, and a ticker whose calls all fail
    gets an `error` marker instead, because a network failure must not be
    recorded as "this company has no share count".
    """
    path = Path(cache_path)
    columns = ["ticker", "date", "shares", "source", "fetched_at", "status"]
    cached = pd.DataFrame(columns=columns)
    if path.exists():
        cached = pd.read_parquet(path)
        # A cache written before the timestamps were normalised still carries
        # market-time offsets, and concatenating mixed offsets raises, so the
        # stored dates are normalised on the way in.
        cached["date"] = pd.to_datetime(
            cached["date"].map(_naive_date), errors="coerce"
        )

    wanted = list(dict.fromkeys(tickers))
    known = set(cached["ticker"]) if len(cached) else set()
    missing = [t for t in wanted if t not in known]
    if missing:
        fetch = fetcher or _yfinance_shares_fetcher
        now = pd.Timestamp.now().isoformat(timespec="seconds")
        rows: list[dict[str, object]] = []
        for ticker in missing:
            symbol = ticker.replace(".", "-")
            series: pd.Series | None = None
            failed = False
            for attempt in range(max(1, attempts)):
                try:
                    series = fetch(symbol)
                    failed = False
                    break
                except Exception:  # noqa: BLE001 - a probe never dies
                    failed = True
                    series = None
                    if attempt + 1 >= max(1, attempts):
                        break
            if series is not None and len(series):
                for date, value in series.items():
                    rows.append(
                        {
                            "ticker": ticker,
                            "date": _naive_date(date),
                            "shares": float(value),
                            "source": "yfinance_get_shares_full",
                            "fetched_at": now,
                            "status": "ok",
                        }
                    )
            else:
                rows.append(
                    {
                        "ticker": ticker,
                        "date": pd.NaT,
                        "shares": np.nan,
                        "source": "yfinance_get_shares_full",
                        "fetched_at": now,
                        "status": "error" if failed else "empty",
                    }
                )
        fresh = pd.DataFrame(rows, columns=columns)
        cached = pd.concat([cached, fresh], ignore_index=True) if len(cached) else fresh
        if len(cached):
            cached = cached.loc[:, columns]
        path.parent.mkdir(parents=True, exist_ok=True)
        cached.to_parquet(path, index=False)
    return cached[cached["ticker"].isin(wanted)].reset_index(drop=True)


def probe_value_source(sample: list[str]) -> pd.DataFrame:
    """Book value reachability: how many quarters, and are they dated?

    A quarter end is not a filing date, so a value used at its period end is
    look-ahead. This probe prints the count of quarters and the column dates
    so the value variant's deferral is a measurement rather than an opinion.
    """
    rows: list[dict[str, object]] = []
    for ticker in sample:
        symbol = ticker.replace(".", "-")
        try:
            handle = yf.Ticker(symbol)
            sheet = handle.quarterly_balance_sheet
            columns = (
                [str(pd.Timestamp(c).date()) for c in sheet.columns]
                if sheet is not None and not sheet.empty
                else []
            )
            equity = (
                int(sheet.loc["Stockholders Equity"].dropna().shape[0])
                if sheet is not None
                and not sheet.empty
                and "Stockholders Equity" in sheet.index
                else 0
            )
            info = handle.info
            rows.append(
                {
                    "ticker": ticker,
                    "rows": 0 if sheet is None else int(sheet.shape[0]),
                    "quarters": len(columns),
                    "equity_quarters": equity,
                    "first_column": columns[-1] if columns else None,
                    "last_column": columns[0] if columns else None,
                    "book_value_current": info.get("bookValue"),
                }
            )
        except Exception as exc:  # noqa: BLE001 - a probe never dies
            rows.append(
                {
                    "ticker": ticker,
                    "rows": -1,
                    "quarters": 0,
                    "equity_quarters": 0,
                    "first_column": None,
                    "last_column": None,
                    "book_value_current": f"error: {type(exc).__name__}",
                }
            )
    return pd.DataFrame(rows)


def run_e3_shares(all_panel_names: bool = False) -> pd.DataFrame:
    """Fetch (or read from cache) the share history.

    With `all_panel_names` the panel's own names are asked for as well as
    the sector file's, which is what the cap-weighted share of the names
    outside the sector file needs: without a share count for a name there is
    no market cap, and a share of index weight cannot be computed.
    """
    sectors = pd.read_parquet(ROOT / "data" / "processed" / "sectors.parquet")
    tickers = list(dict.fromkeys(sectors["ticker"]))
    if all_panel_names:
        returns_frame = pd.read_parquet(ROOT / "data" / "processed" / "returns.parquet")
        panel = list(dict.fromkeys(returns_frame.index.get_level_values("ticker")))
        tickers = list(dict.fromkeys(tickers + panel))
    frame = fetch_share_history(tickers)
    clean, dropped, steps = dedupe_share_history(frame)
    print("### shares_history")
    print(f"tickers requested: {len(tickers)}")
    print(f"rows: {len(frame)} | status ok: {int((frame['status'] == 'ok').sum())}")
    print(f"rows after dedupe: {len(clean)} | duplicate rows dropped: {dropped}")
    print(f"split-sized steps: {steps}")
    first = clean.groupby("ticker")["date"].min().sort_values().head(8)
    print("earliest filing date per name (first 8):")
    for ticker, date in first.items():
        print(f"  {ticker}: {pd.Timestamp(date).date()}")
    print(
        "median earliest date: "
        f"{pd.Timestamp(clean.groupby('ticker')['date'].min().median()).date()}"
    )
    return clean


def _wide(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    return frame[column].unstack("ticker")


def load_panel(data_root: Path | None = None) -> dict[str, object]:
    """Load and align every frame the XS-v1 probes and the build read.

    This is the shared loader: efb.build calls it, so the build and the probes
    cannot disagree about the panel. It lives here because the Task 0 probes
    were written first; moving it into its own module is a tidy-up for E4.
    """
    root = ROOT / "data" if data_root is None else Path(data_root)
    returns_frame = pd.read_parquet(root / "processed" / "returns.parquet")
    prices_frame = pd.read_parquet(root / "raw" / "prices.parquet")
    sectors_frame = pd.read_parquet(root / "processed" / "sectors.parquet")
    membership = pd.read_parquet(root / "processed" / "universe_membership.parquet")
    returns = _wide(returns_frame, "r")
    close = _wide(prices_frame, "close")
    volume = _wide(prices_frame, "volume")
    index = returns.index
    sectors = sectors_frame.set_index("ticker")["gics_sector"]
    mapped = [c for c in returns.columns if c in set(sectors.index)]
    history_path = root / "raw" / "shares_history.parquet"
    if not history_path.exists():
        history_path = SHARES_CACHE
    history = (
        pd.read_parquet(history_path)
        if history_path.exists()
        else pd.DataFrame(columns=["ticker", "date", "shares"])
    )
    # The share panel covers every panel name, not only the sector-mapped
    # ones, because the cap-weighted share of the names the sector file
    # cannot reach needs a market cap for names outside the model universe.
    shares_long = share_count_panel(history, index, list(returns.columns))
    shares = shares_long.pivot(index="date", columns="ticker", values="shares")
    look_ahead = shares_long.pivot(index="date", columns="ticker", values="look_ahead")
    return {
        "returns": returns,
        "close": close.reindex(index=returns.index, columns=returns.columns),
        "volume": volume.reindex(index=returns.index, columns=returns.columns),
        "sectors": sectors,
        "membership": membership.reindex(index=index),
        "mapped": mapped,
        "shares": shares.reindex(index=index, columns=returns.columns),
        "shares_mapped": shares.reindex(index=index, columns=mapped),
        "look_ahead": look_ahead.reindex(index=index, columns=returns.columns),
        "shares_long": shares_long,
        "history": history,
    }


def market_factor_two_ways(
    data_root: Path | None = None, verbose: bool = True
) -> dict[str, object]:
    """The Market factor estimated on total returns and on excess returns.

    XS-v1 regresses the total return r, because the panel's excess column is
    all NaN after 2026-07-31 while r runs to 2026-09-03. This is the standing
    instruction C measurement of what that choice costs. The design is built
    once and every day is fitted twice, once on r and once on r - rf, so the
    two series differ only through the regressand. Because the design carries
    a constant column, subtracting a common rf on a day moves the intercept
    and leaves every other coefficient untouched, which the probe prints
    rather than assumes.

    OUTPUT: the two Market factor series, their correlation on the overlap,
    the maximum deviation of the style and sector returns between the two
    fits, and the maximum deviation of the market gap from rf, which is the
    same statement measured on the real design.
    """
    from efb.models import fundamental

    inputs = load_panel(data_root)
    returns = inputs["returns"]
    close = inputs["close"]
    volume = inputs["volume"]
    sectors = inputs["sectors"]
    mapped = inputs["mapped"]
    shares = inputs["shares"]
    assert isinstance(returns, pd.DataFrame)
    assert isinstance(close, pd.DataFrame)
    assert isinstance(volume, pd.DataFrame)
    assert isinstance(sectors, pd.Series)
    assert isinstance(shares, pd.DataFrame)
    assert isinstance(mapped, list)

    factors_path = (data_root or (ROOT / "data")) / "raw" / "factors_ff.parquet"
    ff = pd.read_parquet(factors_path)
    rf = ff["rf"].astype(float)

    cap = fundamental.market_cap(close[mapped], shares[mapped])
    proxy = fundamental.market_proxy(returns[mapped], cap)
    design = fundamental.build_design(
        returns=returns[mapped],
        close=close[mapped],
        volume=volume[mapped],
        market_cap=cap,
        sectors=sectors,
        proxy=proxy,
    )
    # the market factor is the constant column, so it is the intercept of the
    # fit and the only coefficient a common shift of the regressand can move
    if list(fundamental.FACTOR_NAMES).index("market") != 0:
        raise RuntimeError("the market factor must be the intercept position")
    style_count = len(fundamental.STYLE_NAMES)

    total_rows: list[dict[str, object]] = []
    excess_rows: list[dict[str, object]] = []
    other_gap = 0.0
    market_gap_error = 0.0
    for day in design.days:
        rate = rf.get(day.date, np.nan)
        total = fundamental.wls_fit(day.design, day.returns, day.weights)
        total_weights = fundamental.sector_cap_weights(day)
        total_market = fundamental.identify(
            total.factor_returns, total_weights, n_styles=style_count
        )
        total_rows.append({"date": day.date, "market": float(total_market.market)})
        if not np.isfinite(rate):
            continue
        excess = fundamental.wls_fit(day.design, day.returns - rate, day.weights)
        excess_weights = fundamental.sector_cap_weights(day)
        excess_market = fundamental.identify(
            excess.factor_returns, excess_weights, n_styles=style_count
        )
        excess_rows.append({"date": day.date, "market": float(excess_market.market)})
        other_gap = max(
            other_gap,
            float(
                np.max(
                    np.abs(total_market.as_vector()[1:] - excess_market.as_vector()[1:])
                )
            ),
        )
        market_gap_error = max(
            market_gap_error,
            abs(float(total_market.market) - float(excess_market.market) - rate),
        )

    total_frame = pd.DataFrame(total_rows).set_index("date")["market"]
    excess_frame = pd.DataFrame(excess_rows).set_index("date")["market"]
    overlap = total_frame.index.intersection(excess_frame.index)
    correlation = float(
        np.corrcoef(total_frame.reindex(overlap), excess_frame.reindex(overlap))[0, 1]
    )
    # both FF series are used: the total return, which is the comparison F3.4
    # stores, and the excess return, which is the series the model would be
    # compared against if it regressed the excess return instead
    ff_total = (ff["mkt_rf"] + ff["rf"]).astype(float)
    ff_excess = ff["mkt_rf"].astype(float)
    ff_overlap = overlap.intersection(ff_total.index)
    correlation_ff_total = float(
        np.corrcoef(total_frame.reindex(ff_overlap), ff_total.reindex(ff_overlap))[0, 1]
    )
    correlation_ff_excess = float(
        np.corrcoef(excess_frame.reindex(ff_overlap), ff_excess.reindex(ff_overlap))[
            0, 1
        ]
    )
    summary: dict[str, object] = {
        "n_days_total": int(len(total_frame)),
        "n_days_overlap": int(len(overlap)),
        "overlap_first": str(overlap.min().date()),
        "overlap_last": str(overlap.max().date()),
        "market_total_mean": float(total_frame.mean()),
        "market_total_std": float(total_frame.std(ddof=1)),
        "market_excess_mean": float(excess_frame.mean()),
        "market_excess_std": float(excess_frame.std(ddof=1)),
        "mean_rf_on_overlap": float(rf.reindex(overlap).mean()),
        "correlation_total_vs_excess": correlation,
        "correlation_ff_market_total": correlation_ff_total,
        "correlation_ff_market_excess": correlation_ff_excess,
        "ff_total_label": "Mkt-RF plus RF",
        "ff_excess_label": "Mkt-RF",
        "max_abs_other_factors_gap": other_gap,
        "max_abs_market_gap_minus_rf": market_gap_error,
    }
    if verbose:
        print("### the Market factor, estimated both ways (total vs excess)")
        for key, value in summary.items():
            if isinstance(value, float):
                print(f"{key}: {value:.10g}")
            else:
                print(f"{key}: {value}")
    return summary


def cap_weighted_market_return(
    returns: pd.DataFrame, close: pd.DataFrame, shares: pd.DataFrame
) -> pd.Series:
    """Cap-weighted universe total return, market caps dated t-1.

    INPUT: returns (wide), close (wide), shares (wide, already usable on t).
    OUTPUT: one series, the EFB market proxy. A name contributes only when
    its return and its t-1 market cap both exist.
    """
    mcap = close.shift(1) * shares.shift(1)
    weight = mcap.where(returns.notna())
    total = weight.sum(axis=1)
    return (weight * returns).sum(axis=1) / total.replace(0, np.nan)


def run_e3_probes() -> None:
    """Print every Sprint E3 Task 0 table."""
    inputs = load_panel()
    returns = inputs["returns"]
    close = inputs["close"]
    volume = inputs["volume"]
    sectors = inputs["sectors"]
    membership = inputs["membership"]
    mapped = inputs["mapped"]
    shares = inputs["shares"]
    shares_mapped = inputs["shares_mapped"]
    history = inputs["history"]
    look_ahead_frame = inputs["look_ahead"]
    assert isinstance(returns, pd.DataFrame)
    assert isinstance(close, pd.DataFrame)
    assert isinstance(volume, pd.DataFrame)
    assert isinstance(sectors, pd.Series)
    assert isinstance(membership, pd.DataFrame)
    assert isinstance(shares, pd.DataFrame)
    assert isinstance(shares_mapped, pd.DataFrame)
    assert isinstance(history, pd.DataFrame)
    assert isinstance(look_ahead_frame, pd.DataFrame)
    assert isinstance(mapped, list)

    market = cap_weighted_market_return(returns[mapped], close[mapped], shares_mapped)
    masks = availability_masks(
        returns=returns[mapped],
        market=market,
        volume=volume[mapped],
        close=close[mapped],
        shares=shares_mapped,
        sectors=sectors,
    )
    table = coverage_table(masks, by="year")
    print("### descriptor_coverage_by_year_end")
    print(table.to_string(index=False))

    full_counts = masks["full"].sum(axis=1)
    print()
    print("### universe per day")
    print(f"days: {len(full_counts)} | mean full rows: {full_counts.mean():.1f}")
    print(f"min full rows: {int(full_counts.min())} on {full_counts.idxmin().date()}")
    print("days below 300 names: " f"{int((full_counts < MIN_CROSS_SECTION).sum())}")
    start = first_full_row_day(masks)
    print(f"first day with at least {MIN_CROSS_SECTION} full rows: {start}")

    print()
    print("### shares coverage ramp (names with a count actually filed)")
    ramp = shares_coverage_ramp(shares_mapped, look_ahead_frame[mapped])
    print(f"first month with any filed count: {ramp[ramp > 0].index.min()}")
    print("months where the filed count changes:")
    changed = ramp[ramp.diff().fillna(ramp) != 0]
    print(changed.head(20).to_string())
    print(
        f"last month value: {int(ramp.iloc[-1])} of {shares_mapped.shape[1]} "
        "sector-mapped names"
    )
    clean, dropped, steps = dedupe_share_history(history)
    print(f"duplicate rows dropped: {dropped} | split-sized steps: {steps}")
    print(f"names with any share count: {int((shares.notna().any()).sum())}")
    print(f"name-days flagged look_ahead: {int(look_ahead_frame.sum().sum())}")

    print()
    print("### sector coverage")
    counts = sector_members(returns[mapped], sectors)
    summary = pd.DataFrame(
        {
            "min": counts.min(),
            "median": counts.median(),
            "max": counts.max(),
        }
    ).sort_values("min")
    print(summary.astype(int).to_string())
    print(
        f"days with a sector below 5 members: {small_sector_days(counts)} "
        f"of {len(counts)}"
    )

    print()
    print("### members outside the sector file (the survivor-only restriction)")
    market_cap = close.shift(1) * shares.shift(1)
    outside = members_outside_sector_file(
        membership, set(mapped), market_cap=market_cap
    )
    print(outside.to_string(index=False))

    print()
    print("### value source")
    print(probe_value_source(["AAPL", "JPM", "KR"]).to_string(index=False))


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


def eigenvalue_feasibility(
    data_root: Path | None = None,
    windows: tuple[int, ...] = (252, 504, 756),
) -> pd.DataFrame:
    """Task 0a: how many names are there, against how many days.

    Marchenko-Pastur needs N and T stated before any factor count is claimed.
    N is the number of names with a complete return history inside the window,
    counted per calendar year, and T is the rolling window length the estimator
    will use. The probe reports both the model universe (the sector-mapped
    names the cross-section actually holds) and the wider panel, because the
    residual PCA runs on the model universe while the total-return PCA can use
    the panel.
    """
    inputs = load_panel(data_root)
    returns = inputs["returns"]
    mapped = inputs["mapped"]
    assert isinstance(returns, pd.DataFrame)
    assert isinstance(mapped, list)

    # Freeze at the last model session: the live loop appends sessions after
    # it, and the feasibility arithmetic is a stored probe, not a live one.
    frozen_as_of = pd.Timestamp("2026-09-03")
    returns = returns[returns.index <= frozen_as_of]

    model_start = pd.Timestamp("2011-01-03")
    index = returns.index[returns.index >= model_start]
    frames = {"model_universe": returns.loc[index, mapped], "panel": returns.loc[index]}

    rows: list[dict[str, object]] = []
    for label, frame in frames.items():
        for year, block in frame.groupby(frame.index.year):
            complete = int(block.notna().all(axis=0).sum())
            present = block.notna().sum(axis=1)
            rows.append(
                {
                    "universe": label,
                    "year": int(year),
                    "days": int(len(block)),
                    "names_complete_all_year": complete,
                    "names_median_present": float(present.median()),
                    "ratio_n_over_t_504": complete / 504.0,
                }
            )
    feasibility = pd.DataFrame(rows)

    print("### E4 Task 0a: eigenvalue feasibility")
    print("N is the name count with a complete return history inside the year;")
    print("T is the rolling window the estimator will use.")
    print(feasibility.round(4).to_string(index=False))
    print()
    for label, frame in frames.items():
        present = frame.notna().sum(axis=1)
        n_median = float(present.median())
        n_min = float(present.min())
        print(
            f"{label}: days {len(frame)}, names present median {n_median:.0f}, "
            f"minimum {n_min:.0f}"
        )
        for window in windows:
            ratio = n_median / window
            edge = (1.0 + np.sqrt(ratio)) ** 2
            print(f"   T = {window:4d}  N/T = {ratio:6.3f}   MP edge = {edge:6.3f}")
        print()
    return feasibility


_DELISTED_PROBE = ("CPWR", "EP", "MI", "POM", "ABK", "ABS", "ACAS", "ACE", "AGN", "AKS")

_UA = {"User-Agent": "EquityFactorBook research contact@example.com"}


@dataclass
class SourceProbe:
    """One delisted name's answers from the three candidate sources."""

    ticker: str
    security: str
    removal_date: str
    sec: dict[str, object]
    wiki: dict[str, object]
    yf: dict[str, object]


def _fetch(url: str, timeout: float = 12.0) -> tuple[object, str]:
    """GET a URL and return (status, body); status is the code or the error name."""
    import urllib.request

    request = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - a probe records every failure mode
        return type(exc).__name__, str(getattr(exc, "code", "")) or str(exc)[:60]


def _sec_company(name: str, with_filings: bool = True) -> dict[str, object]:
    """EDGAR company search: the issuer's own SIC code, CIK and 10-K dates.

    The SIC is the filer's assigned code, so it belongs to the issuer rather
    than to the current holder of a ticker. The filings give the dates on which
    that issuer was on file, which is what makes a classification attachable to
    a date rather than to a snapshot.
    """
    import re
    import urllib.parse

    query = urllib.parse.quote(name)
    url = (
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
        f"&company={query}&type=10-K&dateb=&owner=include&count=10&output=atom"
    )
    status, body = _fetch(url)
    if status != 200:
        return {"status": str(status)}
    sic = re.search(r"<assigned-sic>(.*?)</assigned-sic>", body)
    description = re.search(r"<assigned-sic-desc>(.*?)</assigned-sic-desc>", body)
    cik = re.search(r"CIK=(\d+)", body)
    out: dict[str, object] = {
        "status": "ok",
        "sic": sic.group(1).strip() if sic else None,
        "sic_desc": (
            description.group(1).strip().replace("&amp;", "&") if description else None
        ),
        "cik": cik.group(1) if cik else None,
    }
    if with_filings and out["cik"]:
        padded = str(out["cik"]).zfill(10)
        code, payload = _fetch(f"https://data.sec.gov/submissions/CIK{padded}.json")
        if code == 200:
            try:
                data = json.loads(str(payload))
            except ValueError:
                out["n_filings"] = None
                return out
            recent = data.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            tens = [
                date
                for form, date in zip(forms, dates, strict=False)
                if str(form).startswith("10-K")
            ]
            out["n_filings"] = len(dates)
            out["first_filing"] = dates[-1] if dates else None
            out["last_filing"] = dates[0] if dates else None
            out["first_10k"] = tens[-1] if tens else None
            out["last_10k"] = tens[0] if tens else None
        else:
            out["n_filings"] = None
    return out


def _wikipedia_summary(name: str, attempts: int = 3) -> dict[str, object]:
    """Wikipedia REST summary: a one-line description of a delisted issuer."""
    import time
    import urllib.parse

    title = urllib.parse.quote(name.replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    for attempt in range(attempts):
        status, body = _fetch(url)
        if status == 200:
            try:
                payload = json.loads(body)
            except ValueError:
                return {"status": "unparsable"}
            return {
                "status": "ok",
                "description": str(payload.get("description", ""))[:52],
            }
        if "429" not in str(status):
            return {"status": str(status)}
        time.sleep(2.0 * (attempt + 1))
    return {"status": "rate_limited_429"}


def _yfinance_identity(ticker: str) -> dict[str, object]:
    """yfinance's name and sector for a ticker that no longer trades.

    The name is requested as well as the sector, because for a reused symbol
    the sector describes whoever holds the ticker today, which is the failure
    this probe exists to expose.
    """
    try:
        import yfinance
    except ImportError:
        return {"status": "no_yfinance"}
    try:
        info = yfinance.Ticker(ticker).info
    except Exception as exc:  # noqa: BLE001
        return {"status": type(exc).__name__}
    return {
        "status": "ok" if info else "empty",
        "long_name": str(info.get("longName", ""))[:28],
        "sector": info.get("sector"),
        "quote_type": info.get("quoteType"),
    }


def sector_source_probe(
    tickers: tuple[str, ...] = _DELISTED_PROBE,
    data_root: Path | None = None,
    offline: bool = False,
) -> pd.DataFrame:
    """Task 0b: is any point-in-time sector and constituent source reachable?

    Three candidate sources, each asked for ten known delisted index members:
    the changes table's own dated record and security names, the issuer's own
    SIC code through EDGAR (with its filing dates), and the yfinance sector
    field. A source closes the survivor restriction only if it dates the
    classification and describes the issuer rather than the ticker.
    """
    root = ROOT / "data" if data_root is None else Path(data_root)
    changes = pd.read_parquet(root / "processed" / "universe_changes.parquet")
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        matched = changes.loc[changes["removed_ticker"] == ticker]
        name = str(matched["removed_security"].iloc[0]) if len(matched) else ""
        date = str(matched["effective_date"].iloc[0].date()) if len(matched) else ""
        rows.append({"ticker": ticker, "removed_security": name, "removal_date": date})
    subject = pd.DataFrame(rows)

    print("### E4 Task 0b: point-in-time sector and constituent sources")
    print("source 1, the pinned changes table: dated membership and a name")
    print(subject.to_string(index=False))
    print()
    print(f"network probes: {'offline, skipped' if offline else 'live'}")
    results: list[SourceProbe] = []
    for ticker, name, date in zip(
        subject["ticker"],
        subject["removed_security"],
        subject["removal_date"],
        strict=True,
    ):
        if offline:
            sec: dict[str, object] = {"status": "skipped"}
            wiki: dict[str, object] = {"status": "skipped"}
            yf: dict[str, object] = {"status": "skipped"}
        else:
            sec = _sec_company(str(name))
            wiki = _wikipedia_summary(str(name))
            yf = _yfinance_identity(ticker)
        results.append(
            SourceProbe(
                ticker=str(ticker),
                security=str(name),
                removal_date=str(date),
                sec=sec,
                wiki=wiki,
                yf=yf,
            )
        )
        print(f"  {ticker:5s} {str(name)[:30]:30s} removed {date}")
        print(f"        SEC      {sec}")
        print(f"        Wikipedia {wiki}")
        print(f"        yfinance  {yf}")
    print()
    with_sic = [row for row in results if row.sec.get("sic")]
    print(f"SEC SIC returned for {len(with_sic)} of {len(results)} names")
    if with_sic:
        print("sic  description                          first_10k   last_10k")
        for row in with_sic:
            sic = str(row.sec.get("sic"))
            desc = str(row.sec.get("sic_desc"))[:34]
            first = str(row.sec.get("first_10k"))
            last = str(row.sec.get("last_10k"))
            print(f"  {sic:4s} {desc:34s} {first:11s} {last}")
    yf_sector = [row for row in results if row.yf.get("sector")]
    print()
    print(f"yfinance returned a sector for {len(yf_sector)} of {len(results)} names:")
    for row in yf_sector:
        print(
            f"  {row.ticker:5s} {row.security[:26]:26s} -> "
            f"{row.yf.get('long_name')} / {row.yf.get('sector')}"
        )
    print()
    print("read this as follows: the changes table dates membership and names the")
    print("issuer being removed. EDGAR returns the issuer's own SIC code and the")
    print("dates it was on file, so a classification can be attached to an issuer")
    print("and not to whoever holds the ticker today, but SIC is not GICS and the")
    print("code is the filer's, not a sector assigned at a date. A yfinance sector")
    print("describes the current holder of the symbol, which is why it is printed")
    print("beside the long name: for a reused symbol it names a different company.")
    return subject


def momentum_factor_vol_by_tercile(data_root: Path | None = None) -> pd.DataFrame:
    """Task 0c: is the momentum factor's own realized volatility low in the
    months when the book's momentum exposure is high?

    The terciles are the ones E3 stored in data/eval/xs_bias_by_exposure.parquet:
    the momentum book's 141 rebalances sorted on its own momentum exposure into
    three groups of 47. This probe recomputes the grouping, checks it against
    the stored exposure means, and then measures the factor itself rather than
    the book, which is the measurement that separates the two explanations in
    Task 3.
    """
    root = ROOT / "data" if data_root is None else Path(data_root)
    exposure = pd.read_parquet(root / "eval" / "xs_exposure_timeseries.parquet")
    bias = pd.read_parquet(root / "eval" / "xs_bias.parquet")
    stored = pd.read_parquet(root / "eval" / "xs_bias_by_exposure.parquet")
    factors = pd.read_parquet(root / "models" / "XS-v1" / "factor_returns.parquet")
    # The tercile probe is stored at the last model session; the live loop's
    # appended factor rows must not change its forward windows.
    frozen_as_of = pd.Timestamp("2026-09-03")
    factors = factors[pd.to_datetime(factors["date"]) <= frozen_as_of]

    momentum_exposure = (
        exposure.loc[
            (exposure["book"] == "seed_mom_ls") & (exposure["factor"] == "momentum")
        ]
        .set_index("date")["exposure"]
        .sort_index()
    )
    book_bias = bias.loc[bias["book"] == "seed_mom_ls"].set_index("date").sort_index()
    factor_series = (
        factors.loc[factors["factor"] == "momentum"].set_index("date")["f"].sort_index()
    )

    dates = book_bias.index.intersection(momentum_exposure.index)
    ranked = momentum_exposure.reindex(dates).rank(method="first")
    n = len(dates)
    labels = pd.Series("low", index=dates)
    labels[ranked > n / 3.0] = "mid"
    labels[ranked > 2.0 * n / 3.0] = "high"

    rows: list[dict[str, object]] = []
    for bucket in ("low", "mid", "high"):
        members = dates[labels == bucket]
        forward = []
        trailing = []
        for date in members:
            position = factor_series.index.get_indexer([date])[0]
            if position < 0:
                continue
            fwd = factor_series.iloc[position + 1 : position + 22]
            back = factor_series.iloc[max(0, position - 20) : position + 1]
            if len(fwd) > 1:
                forward.append(float(np.std(fwd, ddof=1) * np.sqrt(252)))
            if len(back) > 1:
                trailing.append(float(np.std(back, ddof=1) * np.sqrt(252)))
        stored_row = stored.loc[
            (stored["book"] == "seed_mom_ls") & (stored["bucket"] == bucket)
        ].iloc[0]
        rows.append(
            {
                "bucket": bucket,
                "n_months": len(members),
                "exposure_mean": float(momentum_exposure.reindex(members).mean()),
                "stored_exposure_mean": float(stored_row["exposure_mean"]),
                "stored_predicted_vol": float(stored_row["predicted_vol_ann_mean"]),
                "stored_realized_vol": float(stored_row["realized_vol_ann_mean"]),
                "stored_bias_mean": float(stored_row["bias_mean"]),
                "factor_vol_forward_21d": float(np.mean(forward)),
                "factor_vol_trailing_21d": float(np.mean(trailing)),
                "book_realized_vol_mean": (
                    float(book_bias.reindex(members)["realized_vol_ann"].mean())
                    if "realized_vol_ann" in book_bias.columns
                    else float("nan")
                ),
            }
        )
    table = pd.DataFrame(rows)
    print("### E4 Task 0c: the momentum factor's own volatility by exposure tercile")
    print("buckets are the book's own momentum exposure, 47 rebalances each")
    print(table.round(6).to_string(index=False))
    print()
    print("swings across the three buckets")
    for column in (
        "stored_predicted_vol",
        "stored_realized_vol",
        "factor_vol_forward_21d",
        "factor_vol_trailing_21d",
        "stored_bias_mean",
    ):
        series = table[column]
        print(
            f"  {column:24s} min {series.min():.6f} max {series.max():.6f} "
            f"max-min {series.max() - series.min():.6f} "
            f"low-to-high {series.iloc[2] - series.iloc[0]:+.6f}"
        )
    print()
    print("the question the probe answers: if factor_vol_forward_21d is lower in")
    print("the high-exposure bucket, the factor itself was quiet in those months")
    print("and the model's error is a conditional factor variance rather than a")
    print("smoothing half-life.")
    return table


def run_e4_probes(offline: bool = False) -> None:
    """Task 0 of Sprint E4: the three probes, in order."""
    eigenvalue_feasibility()
    print()
    sector_source_probe(offline=offline)
    print()
    momentum_factor_vol_by_tercile()


def probe_finra_short_interest(sample_tickers: list[str] | None = None) -> ProbeReport:
    """Sprint E7 Task 0: can the FINRA consolidated short interest be read?

    The consolidated short interest endpoint is settled twice a month; the
    probe asks for one settlement date and prints the rows it gets for a
    handful of known tickers. A probe that prints nothing records the source
    as unavailable in the multiple-testing ledger, not as a NULL signal.
    """
    tickers = sample_tickers or ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]
    url = "https://api.finra.org/data/group/otcMarket/name/" "consolidatedShortInterest"
    payload = {
        "limit": 1000,
        "compareFilters": [
            {
                "compareType": "equal",
                "fieldName": "settlementDate",
                "fieldValue": "2026-07-31",
            }
        ],
    }
    try:
        response = requests.post(
            url,
            headers={**HEADERS, "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=30,
        )
        if response.status_code != 200:
            return ProbeReport(
                source="FINRA consolidated short interest",
                status="FAIL",
                n_rows=0,
                first_date=None,
                last_date=None,
                coverage=None,
                nan_share=None,
                notes=f"HTTP {response.status_code}",
            )
        frame = pd.read_csv(io.StringIO(response.text))
    except (requests.RequestException, ValueError) as error:
        return ProbeReport(
            source="FINRA consolidated short interest",
            status="FAIL",
            n_rows=0,
            first_date=None,
            last_date=None,
            coverage=None,
            nan_share=None,
            notes=f"{type(error).__name__}: {error}",
        )
    if frame.empty:
        return ProbeReport(
            source="FINRA consolidated short interest",
            status="EMPTY",
            n_rows=0,
            first_date=None,
            last_date=None,
            coverage=None,
            nan_share=None,
            notes="no rows returned for the settlement date",
        )
    ticker_col = "symbolCode" if "symbolCode" in frame.columns else frame.columns[0]
    frame = frame.loc[frame[ticker_col].isin(tickers)]
    print(frame.head(3).to_string())
    return ProbeReport(
        source="FINRA consolidated short interest",
        status="OK" if len(frame) else "EMPTY",
        n_rows=int(len(frame)),
        first_date=None,
        last_date=None,
        coverage=float(frame[ticker_col].nunique()) / len(tickers),
        nan_share=float(frame.isna().mean().mean()),
        notes=f"columns: {sorted(frame.columns)}",
    )


def probe_earnings_dates(sample_tickers: list[str] | None = None) -> ProbeReport:
    """Sprint E7 Task 0: can yfinance supply point-in-time earnings dates?

    Earnings dates are the raw input of post-earnings drift. The probe asks
    yfinance for one ticker's history and prints the rows it gets. A probe
    that prints nothing records the source as unavailable in the ledger.
    """
    tickers = sample_tickers or ["AAPL", "MSFT", "NVDA"]
    frames: list[pd.DataFrame] = []
    notes: list[str] = []
    for ticker in tickers:
        try:
            instrument = yf.Ticker(ticker)
            frame = instrument.get_earnings_dates(limit=12)
            if frame is not None and not frame.empty:
                frame = frame.reset_index()
                frame["ticker"] = ticker
                frames.append(frame)
            else:
                notes.append(f"{ticker}: empty")
        except Exception as error:  # pragma: no cover - network shape varies
            notes.append(f"{ticker}: {type(error).__name__}: {error}")
    if not frames:
        return ProbeReport(
            source="yfinance earnings dates",
            status="EMPTY",
            n_rows=0,
            first_date=None,
            last_date=None,
            coverage=None,
            nan_share=None,
            notes="; ".join(notes) if notes else "no rows for any ticker",
        )
    frame = pd.concat(frames, ignore_index=True)
    print(frame.head(3).to_string())
    return ProbeReport(
        source="yfinance earnings dates",
        status="OK",
        n_rows=int(len(frame)),
        first_date=str(frame.iloc[:, 0].min()),
        last_date=str(frame.iloc[:, 0].max()),
        coverage=float(frame["ticker"].nunique()) / len(tickers),
        nan_share=float(frame.isna().mean().mean()),
        notes=f"columns: {sorted(frame.columns)}"
        + ("; " + "; ".join(notes) if notes else ""),
    )


def run_e7_probes() -> None:
    """Task 0 of Sprint E7: the optional data sources, in order."""
    print(probe_finra_short_interest().render())
    print()
    print(probe_earnings_dates().render())


def main() -> None:
    import sys

    args = sys.argv[1:]
    if "--e7" in args:
        run_e7_probes()
        return
    if "--e4-offline" in args:
        run_e4_probes(offline=True)
        return
    if "--e4" in args:
        run_e4_probes()
        return
    if "--e3-two-ways" in args:
        market_factor_two_ways()
        return
    if "--e3-shares-all" in args:
        run_e3_shares(all_panel_names=True)
        return
    if "--e3-shares" in args:
        run_e3_shares()
        return
    if "--e3" in args:
        run_e3_probes()
        return
    for report in run_all():
        print(report.render())


if __name__ == "__main__":
    main()
