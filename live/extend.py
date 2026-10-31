"""Sprint E11 live: daily incremental extension of the data and model.

Every function appends one or more sessions, never refits history. Rows
dated on or before 2026-09-03 come back byte-identical, which
`incremental_integrity` asserts with hashes. Prices and share counts come
from yfinance, the same vendor E1 uses.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from efb import hygiene, prices, probes, race, returns, spy, universe
from efb.models import fundamental as fx
from live import corporate_actions, store

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
FROZEN_AS_OF = pd.Timestamp("2026-09-03")


def last_price_session(data_root: Path | None = None) -> pd.Timestamp | None:
    """The latest session in the price panel, read without extending anything.

    The daily run reads it before and after the extension, so the sessions the
    run appended are a measurement rather than an assumption: a first run on a
    fresh container catches up several sessions at once, and the run has to be
    able to say which ones.
    """
    root = Path(data_root) if data_root is not None else DATA_ROOT
    path = root / "raw" / "prices.parquet"
    if not path.exists():
        return None
    dates = pd.DatetimeIndex(
        pd.read_parquet(path, columns=["close"]).index.get_level_values("date")
    )
    return pd.Timestamp(dates.max()) if len(dates) else None


def _frozen_tickers(data_root: Path) -> list[str]:
    """The frozen model universe: sector-mapped names plus the panel names."""
    sectors = pd.read_parquet(data_root / "processed" / "sectors.parquet")
    ret = pd.read_parquet(data_root / "processed" / "returns.parquet")
    panel = list(dict.fromkeys(ret.index.get_level_values("ticker")))
    return sorted(set(sectors["ticker"]) | set(panel))


def _spy_tickers(data_root: Path) -> list[str]:
    """The live universe from the newest SPY archive file."""
    files = sorted((data_root / "raw" / "spy_holdings").glob("spy_holdings_*.parquet"))
    frame = pd.read_parquet(files[-1])
    return sorted(frame["ticker"].astype(str).str.upper().str.strip())


def extend_archives(data_root: Path | None = None) -> dict[str, str]:
    """Fetch and archive a fresh SPY holdings file and Wikipedia snapshot."""
    root = Path(data_root) if data_root is not None else DATA_ROOT
    fetched = spy.fetch_spy_holdings()
    spy_path = spy.archive_snapshot(fetched["equity"], fetched["as_of"], root)
    wiki_path = universe.archive_constituents(root)
    return {
        "spy_as_of": str(spy_path.stem).replace("spy_holdings_", ""),
        "wiki_as_of": str(wiki_path.stem).replace("wikipedia_constituents_", ""),
    }


def _live_tickers(data_root: Path) -> list[str]:
    """Tonight's fetch: the current universe plus whatever the book holds.

    The frozen panel is every name the history ever held, so asking the vendor
    about all of it meant 206 failures an evening for tickers delisted years ago,
    which bury the one failure that would matter. The archive is the universe being
    priced tonight, and the last stored proposal is what the book actually holds: a
    name outside the index but still held is still fetched.

    The stored book is a convenience, not a requirement: if the store cannot
    answer, the universe alone is fetched, because a run must not stop over the
    set it prices rather than the prices themselves.
    """
    tickers = set(_spy_tickers(data_root))
    try:
        from live import snapshot

        _, book, _ = snapshot.previous_proposal()
    except Exception:  # noqa: BLE001 - the universe alone is the safe subset
        book = None
    if book is not None and "ticker" in book.columns:
        tickers |= {str(name).upper().strip() for name in book["ticker"]}
    return sorted(tickers)


def retry_missing_closes(
    frame: pd.DataFrame,
    tickers: list[str],
    start: str,
    end: str,
    *,
    session: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Ask the vendor again, one ticker at a time, for the names it skipped.

    The bulk download is threaded, and yfinance reports a symbol whose fetch failed
    as a failed download rather than as an error, so the frame comes back carrying
    that symbol's rows and no prices. Those names become the book's "no usable
    close" set, which is the right answer for a name that genuinely no longer trades
    and the wrong one for a name the vendor simply did not answer for. One retry,
    single-threaded, tells the two apart: a name that comes back was a lost race, and
    a name that does not is unavailable tonight and goes to the book's drop rule.

    `session` is the close the book will be priced from, and it decides who is
    missing: a name whose earlier sessions came back and whose own bar did not has no
    close to quantize on, so it is retried like any other. It is required because
    this ran without one on 2026-09-29 and skipped exactly that case, which is how
    CSGP was dropped without a retry attempt in a run that had every fix in it.

    The retry happens once and is never retried again, so a vendor that refuses
    everything costs one request per missing name and no more. The recovered rows
    replace the empty ones the bulk pass wrote, because the later row wins on the
    same (date, ticker).

    What the retry could not recover is named one line per ticker, because that is
    the fact the run's log has to carry: on 2026-10-14 the vendor answered 404 for
    the warrant `SKYD/WS` on both passes and the only record of the name was a
    frame with no rows. A zero-row frame is a valid answer here - `download_prices`
    returns one - and it leaves every requested ticker missing.
    """
    missing = prices.missing_tickers(frame, tickers, session=session)
    report: dict[str, object] = {
        "requested": len(tickers),
        "session": session,
        "missing": missing,
        "recovered": [],
        "still_missing": missing,
    }
    if not missing:
        return frame, report
    retry = prices.download_prices(missing, start=start, end=end, threads=False)
    still_missing = prices.missing_tickers(retry, missing, session=session)
    recovered = [ticker for ticker in missing if ticker not in set(still_missing)]
    report["recovered"] = recovered
    report["still_missing"] = still_missing
    if retry is not None and len(retry):
        combined = pd.concat([frame, retry])
        frame = combined[~combined.index.duplicated(keep="last")].sort_index()
    for ticker in still_missing:
        logger.warning("no prices from the vendor: %s", ticker)
    logger.warning(
        "the price fetch missed %d of %d requested ticker(s) on %s; the "
        "single-threaded retry recovered %d and %d are still without a close: %s",
        len(missing),
        len(tickers),
        session,
        len(recovered),
        len(still_missing),
        ", ".join(still_missing) or "none",
    )
    return frame, report


def extend_prices(
    data_root: Path | None = None,
    end: str | None = None,
    tickers: list[str] | None = None,
) -> int:
    """Download the sessions after the last stored price and append them.

    `end` is the last session wanted, **inclusive**, and defaults to today: a run
    prices tonight's close, so tonight is the session it has to be able to fetch.
    The vendor's own `end` is exclusive, which cost an evening on 2026-09-28: the
    fetch asked for a window ending on the run's own date, the vendor answered with
    the previous session alone, nothing was appended, and the gate stopped the run
    one session behind its own target close.

    The fetch is the one the book is priced from, so it is also the one place a
    silently missing name can be caught: the timezone rows are written serially
    before the threaded download starts (see `prices.prewarm_tz_cache`, which is
    what stops the download's own threads from locking the cache), and every
    requested ticker without a close on the session being priced is asked for once
    more, single threaded, before the book's drop rule sees it
    (`retry_missing_closes`). That session is `end`, the close the book is priced
    from, and not the rest of the window: a name whose earlier sessions came back and
    whose own bar did not is exactly the name the retry is for.

    Returns the number of new sessions appended. Nothing is overwritten: rows
    already present keep their values.
    """
    root = Path(data_root) if data_root is not None else DATA_ROOT
    path = root / "raw" / "prices.parquet"
    existing = pd.read_parquet(path)
    last_date = pd.Timestamp(existing.index.get_level_values("date").max())
    if tickers is None:
        tickers = _live_tickers(root)
    end = end or pd.Timestamp.now().strftime("%Y-%m-%d")
    # yfinance's `end` is exclusive, so the run's own close has to be asked for by
    # naming the day after it. Without this the fetch can never return the session
    # being priced, and on a weekday evening whose previous close is already stored
    # it returns nothing new at all.
    window_end = str((pd.Timestamp(end) + pd.Timedelta(days=1)).date())
    start = str(last_date.date())
    tail = prices.download_prices(tickers, start=start, end=window_end, prewarm=True)
    tail, _fetch_report = retry_missing_closes(
        tail, tickers, start=start, end=window_end, session=end
    )
    if tail is None or len(tail) == 0:
        return 0
    tail = prices.build_prices_artifact(tail, start="2010-01-04")
    tail = tail[tail.index.get_level_values("date") > last_date]
    if len(tail) == 0:
        return 0
    combined = pd.concat([existing, tail])
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    combined.to_parquet(path)
    return int(tail.index.get_level_values("date").nunique())


def recorded_spinoffs() -> list[corporate_actions.Spinoff]:
    """Every spin-off the appendix records, for the rebuild to re-apply.

    A spin-off moves one session's return and neither price vendor adjusts the history
    for it, so the stored prices alone can never produce the right number: the
    correction is a recorded fact rather than a derived one. `extend_returns`
    recomputes every session from those prices, which is why the correction has to be
    re-applied from its record every evening instead of being kept in the returns file
    it writes. Without this, the cell reverts to the raw print - CTVA on 2026-10-01,
    -83.81%, the 77.65 close becoming 12.57 with a VYLR share paid alongside it - and
    the fit reads that print as a return. Measured on the 2026-10-01 run: the cell was
    flagged as an unexplained large move and the whole 2026-10-02 cross-section was
    built from it.

    The store is asked and never written to. A tree with no store behind it - a test, a
    fresh container - reads as no records, and a store that cannot answer is a warning
    rather than a stopped evening: the run's own prices are not the store's problem.
    """
    try:
        rows = store.select(corporate_actions.TABLE)
    except Exception:  # noqa: BLE001 - the run goes on without its own record
        logger.warning("corporate actions could not be read", exc_info=True)
        return []
    return corporate_actions.spinoffs_from_rows(rows)


def extend_returns(data_root: Path | None = None) -> int:
    """Recompute returns and flags over the extended price frame.

    Identity drops and truncations are applied exactly as the E1 build
    applies them, so a reused symbol does not reappear with another
    company's history. Returns the number of new sessions.

    Recorded spin-offs are re-applied before the flags are built, because this
    recomputes every session from the stored prices and the correction is not in them.
    """
    from efb import identity

    root = Path(data_root) if data_root is not None else DATA_ROOT
    path = root / "processed" / "returns.parquet"
    before = pd.read_parquet(path).index.get_level_values("date").nunique()
    prices_frame = pd.read_parquet(root / "raw" / "prices.parquet")
    factors_frame = pd.read_parquet(root / "raw" / "factors_ff.parquet")
    returns_frame = returns.compute_returns(prices_frame, factors_frame["rf"])
    # A spin-off is put back from its record here, between the arithmetic and every
    # reader of it. Nothing is read back from `returns_frame`, so the value is the one
    # the append path wrote last evening and re-running changes nothing.
    for outcome in corporate_actions.apply_recorded(
        returns_frame, prices_frame, recorded_spinoffs()
    ):
        logger.info(
            "re-applied %s: the %s return on %s is %s where the prices alone give %s",
            outcome.spinoff.label,
            outcome.spinoff.parent,
            outcome.session.date(),
            outcome.adjusted_return,
            outcome.raw_return,
        )
    identity_table = pd.read_parquet(root / "processed" / "ticker_identity.parquet")
    readded_path = root / "processed" / "ticker_identity_readded.parquet"
    readded = pd.read_parquet(readded_path) if readded_path.exists() else None
    drops, truncations = identity.exclusions(identity_table, readded=readded)
    if truncations:
        returns_frame = identity.drop_truncated(returns_frame, truncations)
    if drops:
        returns_frame = returns_frame[~returns_frame.index.isin(drops, level="ticker")]
    returns_frame = hygiene.apply_flags(returns_frame)
    returns_frame.to_parquet(path)
    after = pd.read_parquet(path).index.get_level_values("date").nunique()
    return int(after - before)


def _shares_fetch_stamp(cache: Path) -> pd.Timestamp | None:
    """The newest successful share fetch in the cache, or None."""
    if not cache.exists():
        return None
    frame = pd.read_parquet(cache)
    if "status" in frame.columns:
        frame = frame.loc[frame["status"] == "ok"]
    if frame.empty or "fetched_at" not in frame.columns:
        return None
    stamps = pd.to_datetime(frame["fetched_at"], errors="coerce").dropna()
    return pd.Timestamp(stamps.max()).normalize() if len(stamps) else None


def _trading_names(root: Path, end: pd.Timestamp) -> list[str]:
    """The names that printed on `end`, which are the ones a refresh can update.

    A name that has left trading - acquired, delisted, inactive - cannot be given a
    new row by asking again, so it is not part of the catch-up. On 2026-11-02 KVUE
    completed its merger into KMB; a refresh that waited for it would wait forever.
    """
    path = root / "raw" / "prices.parquet"
    if not path.exists():
        return []
    prices = pd.read_parquet(path, columns=["close"])
    on_day = prices.index.get_level_values("date") == end
    close = prices.loc[on_day, "close"]
    tickers = prices.index.get_level_values("ticker")[on_day]
    return sorted(
        {
            str(ticker)
            for ticker, value in zip(tickers, close, strict=True)
            if pd.notna(value)
        }
    )


def extend_shares(
    data_root: Path | None = None,
    tickers: list[str] | None = None,
    end: str | pd.Timestamp | None = None,
) -> int:
    """Fetch share counts for names not yet cached, and catch the cache up.

    Returns the number of names newly fetched. A cached name is normally not
    re-asked, because a share count does not change unless a corporate action does.

    The gate reads the **fetch** date of this artifact, though, and a cache that is
    only ever added to can only get older: it advances on an evening that adds a
    ticker and stands still on every other, so a run with no new name in the
    universe is stale one session later and stops. Measured on 2026-11-03: the
    stamp stood at 2026-11-02, the day the last two names (BE and P) were fetched,
    and the evening stopped at "shares 1 session behind (allowed 0)".

    So when the stamp is behind `end`, the names that printed on `end` are asked
    again and their rows replaced. Those are exactly the names still trading; a
    retired one cannot produce a new row and is skipped rather than waited for.
    The gate's own rule is untouched: a refresh that fails leaves the stamp where
    it was, and the evening still stops.
    """
    root = Path(data_root) if data_root is not None else DATA_ROOT
    target = (
        pd.Timestamp(end).normalize()
        if end is not None
        else pd.Timestamp.now().normalize()
    )
    if tickers is None:
        tickers = _live_tickers(root)
    before = set()
    cache = root / "raw" / "shares_history.parquet"
    if cache.exists():
        before = set(pd.read_parquet(cache)["ticker"])
    stamp = _shares_fetch_stamp(cache)
    refresh: list[str] = []
    if stamp is None or stamp < target:
        trading = set(_trading_names(root, target))
        refresh = [name for name in tickers if name in trading]
        logger.info(
            "the share counts are stamped %s and the close is %s, so %s name(s) "
            "still trading are asked again and the retired ones are not",
            "never" if stamp is None else stamp.date(),
            target.date(),
            len(refresh),
        )
    # The cache path is passed rather than left to the module default: on a run
    # that works in its own tree, the default would fetch into the repository.
    probes.fetch_share_history(tickers, cache_path=cache, refresh=refresh)
    after = set(pd.read_parquet(cache)["ticker"])
    return int(len(after - before))


def _descriptor_rows_for_dates(
    design: fx.DesignResult,
    dates: list[pd.Timestamp],
    look_ahead: pd.DataFrame,
    tickers: list[str],
) -> pd.DataFrame:
    """Descriptor artifact rows for explicit dates, same schema as E3."""
    obs = design.raw.get("obs_count")
    rows: list[dict[str, object]] = []
    for name in fx.STYLE_NAMES:
        raw = design.raw[name]
        winsorized = design.winsorized.get(name, raw)
        pre = design.standard_pre.get(name, design.standardized[name])
        post = design.standardized[name]
        for date in dates:
            if date not in raw.index:
                continue
            for ticker in tickers:
                rows.append(
                    {
                        "date": date,
                        "ticker": ticker,
                        "descriptor": name,
                        "value_raw": (
                            float(raw.loc[date, ticker])
                            if pd.notna(raw.loc[date, ticker])
                            else np.nan
                        ),
                        "value_winsor": (
                            float(winsorized.loc[date, ticker])
                            if pd.notna(winsorized.loc[date, ticker])
                            else np.nan
                        ),
                        "value_z": (
                            float(pre.loc[date, ticker])
                            if pd.notna(pre.loc[date, ticker])
                            else np.nan
                        ),
                        "value_z_orth": (
                            float(post.loc[date, ticker])
                            if pd.notna(post.loc[date, ticker])
                            else np.nan
                        ),
                        "n_obs": (
                            float(obs.loc[date, ticker])
                            if obs is not None and pd.notna(obs.loc[date, ticker])
                            else np.nan
                        ),
                        "look_ahead": (
                            bool(look_ahead.loc[date, ticker])
                            if ticker in look_ahead.columns
                            and pd.notna(look_ahead.loc[date, ticker])
                            else False
                        ),
                    }
                )
    return pd.DataFrame(rows)


def extend_model(data_root: Path | None = None) -> dict[str, object]:
    """Append one or more sessions to the XS-v1 artifacts.

    Descriptors, factor returns and specific returns are fitted only for
    the new sessions; the pre-2026-09-04 rows are never touched. The factor
    covariance snapshot and the specific variance roll forward by one
    session each.
    """
    root = Path(data_root) if data_root is not None else DATA_ROOT
    xs_dir = root / "models" / "XS-v1"
    inputs = probes.load_panel(root)
    # One decision, two readers: `race.design_panel` is where `EFB_DESIGN_RETURNS`
    # picks the frame, so the model fitted here and the next session's design row
    # are always built from the same panel. A fit on the cleaned frame beside a
    # design built from the raw one is the divergence nov11's
    # `tests/test_live_panel_parity.py` guard exists to catch, and unset is `raw`,
    # which is origin/main's behaviour byte for byte.
    returns_frame = race.design_panel(inputs)
    close = inputs["close"]
    volume = inputs["volume"]
    sectors = inputs["sectors"]
    mapped = inputs["mapped"]
    shares = inputs["shares"]
    look_ahead = inputs["look_ahead"]
    assert isinstance(mapped, list)
    assert isinstance(returns_frame, pd.DataFrame)
    assert isinstance(close, pd.DataFrame)
    assert isinstance(volume, pd.DataFrame)
    assert isinstance(sectors, pd.Series)
    assert isinstance(shares, pd.DataFrame)
    assert isinstance(look_ahead, pd.DataFrame)
    assert isinstance(mapped, list)

    cap = fx.market_cap(close[mapped], shares[mapped])
    proxy = fx.market_proxy(returns_frame[mapped], cap)
    design = fx.build_design(
        returns=returns_frame[mapped],
        close=close[mapped],
        volume=volume[mapped],
        market_cap=cap,
        sectors=sectors,
        proxy=proxy,
    )

    descriptors_path = xs_dir / "descriptors.parquet"
    existing_desc = pd.read_parquet(descriptors_path)
    last = pd.to_datetime(existing_desc["date"]).max()
    new_dates = sorted(day.date for day in design.days if day.date > last)
    # A name that has just become sector-mapped is in this design and has no rows in
    # the artifact: the label is what maps it, so the weeks it spent unmapped left a
    # hole that the "new sessions" append below cannot fill. This does it, on the
    # design already in hand, whether or not there is a session to append.
    people = _backfill(root, design, look_ahead[mapped], mapped)
    if not new_dates:
        return {
            "extended": 0,
            "last_date": str(last.date()),
            "backfilled": people,
        }

    new_desc = _descriptor_rows_for_dates(design, new_dates, look_ahead[mapped], mapped)
    pd.concat([existing_desc, new_desc], ignore_index=True).to_parquet(
        descriptors_path, index=False
    )

    new_days = [day for day in design.days if day.date in set(new_dates)]
    sub = fx.DesignResult(
        factor_names=design.factor_names,
        days=new_days,
        standardized=design.standardized,
        stats=design.stats,
    )
    tables = fx.fit_panel(sub)

    factor_path = xs_dir / "factor_returns.parquet"
    specific_path = xs_dir / "specific_returns.parquet"
    r2_path = xs_dir / "xs_r2.parquet"
    factor_full = pd.concat(
        [pd.read_parquet(factor_path), tables["factor_returns"]], ignore_index=True
    )
    specific_full = pd.concat(
        [pd.read_parquet(specific_path), tables["specific_returns"]],
        ignore_index=True,
    )
    r2_full = pd.concat([pd.read_parquet(r2_path), tables["xs_r2"]], ignore_index=True)
    factor_full.to_parquet(factor_path, index=False)
    specific_full.to_parquet(specific_path, index=False)
    r2_full.to_parquet(r2_path, index=False)

    # the factor covariance snapshot rolls forward with the new sessions
    factor_wide = (
        factor_full.pivot(index="date", columns="factor", values="f")
        .reindex(columns=list(fx.FACTOR_NAMES))
        .dropna()
    )
    factor_cov = fx.ewma_factor_cov(factor_wide, half_life=fx.F_HALF_LIFE)
    factor_cov.to_parquet(xs_dir / "factor_cov.parquet")

    # the specific variance rolls forward with the new sessions
    specific_wide = specific_full.pivot(
        index="date", columns="ticker", values="specific_return"
    )
    specific_long = fx.specific_variance(
        specific_wide, sectors, cap, half_life=fx.D_HALF_LIFE, shrink_k=fx.D_SHRINK_K
    )
    specific_new = specific_long.loc[
        pd.to_datetime(specific_long["date"]).isin(new_dates)
    ]
    sv_path = xs_dir / "specific_var.parquet"
    pd.concat([pd.read_parquet(sv_path), specific_new], ignore_index=True).to_parquet(
        sv_path, index=False
    )

    return {
        "extended": len(new_dates),
        "new_dates": [str(d.date()) for d in new_dates],
        "last_date": str(new_dates[-1].date()),
        "backfilled": people,
    }


def fill_missing_sessions(
    data_root: Path | None = None,
    tickers: list[str] | None = None,
    start: object = None,
    end: object = None,
    *,
    write: bool = True,
) -> dict[str, object]:
    """Fetch the sessions the price panel has no bar for, for the named tickers.

    A vendor hole is not a delisting: BE and P have no close for the eleven sessions
    from 2026-09-04 to 2026-09-21 and a full series either side, and every rolling
    descriptor - momentum is a 231-session product - is NaN from the hole to the end
    of the panel. That is why the two names had no descriptors after 2026-08-31 while
    their prices, returns and index membership were all present, and no sector row
    could have fixed it.

    So this asks the vendor for the sessions the panel is missing inside a range,
    writes the bars, and recomputes that ticker's own return rows - returns, flags and
    all - from the repaired series. It is a *hole* repair: a name whose series was
    rewritten by a corporate action is the business of
    `live/corporate_actions.py`, not this.
    """
    root = Path(data_root) if data_root is not None else DATA_ROOT
    path = root / "raw" / "prices.parquet"
    existing = pd.read_parquet(path)
    names = [str(name) for name in (tickers or [])]
    if not names:
        raise ValueError("fill_missing_sessions needs at least one ticker")
    first = pd.Timestamp(start) if start is not None else None
    last = pd.Timestamp(end) if end is not None else None
    session_index = pd.DatetimeIndex(
        sorted({pd.Timestamp(day) for day in existing.index.get_level_values("date")})
    )
    window = [
        day
        for day in session_index
        if (first is None or day >= first) and (last is None or day <= last)
    ]
    stored_returns = pd.read_parquet(root / "processed" / "returns.parquet")
    holes: dict[str, list[pd.Timestamp]] = {}
    stale: dict[str, list[pd.Timestamp]] = {}
    for name in names:
        if name not in set(existing.index.get_level_values("ticker")):
            raise ValueError(f"{name} is not in the price panel at all")
        series = existing.xs(name, level="ticker")["close"]
        missing = [
            day for day in window if day not in series.index or pd.isna(series.get(day))
        ]
        if missing:
            holes[name] = missing
        # A bar that is there while its return row is not is a half-applied repair,
        # and this is what finishes one instead of refusing to.
        present = [
            day
            for day in window
            if day not in missing and day in series.index and pd.notna(series.get(day))
        ]
        absent_rows = []
        for day in present:
            key = (day, name)
            if key not in stored_returns.index:
                absent_rows.append(day)
                continue
            value = stored_returns.loc[key, "r"]
            if pd.isna(value if not isinstance(value, pd.Series) else value.iloc[0]):
                absent_rows.append(day)
        if absent_rows:
            stale[name] = absent_rows
    report: dict[str, object] = {
        "tickers": names,
        "sessions": {
            name: [str(day.date()) for day in days] for name, days in holes.items()
        },
        "filled": {},
        "not_served": {},
        "returns_rows": 0,
    }
    if not holes:
        return report
    if not holes:
        return _repair_returns(root, stored_returns, names, stale, report)
    fetch_start = str(min(min(days) for days in holes.values()).date())
    fetch_end = str(
        (max(max(days) for days in holes.values()) + pd.Timedelta(days=1)).date()
    )
    bars = prices.download_prices(
        sorted(holes), start=fetch_start, end=fetch_end, threads=False
    )
    if bars is None or len(bars) == 0:
        raise ValueError(
            f"the vendor served no bars between {fetch_start} and {fetch_end}"
        )
    filled: dict[str, int] = {}
    not_served: dict[str, list[str]] = {}
    for name, days in holes.items():
        have = (
            bars.xs(name, level="ticker")
            if name in set(bars.index.get_level_values("ticker"))
            else None
        )
        missing = [] if have is None else [day for day in days if day not in have.index]
        if missing:
            not_served[name] = [str(day.date()) for day in missing]
        count = 0
        for day in days:
            if have is None or day not in have.index:
                continue
            row = have.loc[day]
            if pd.isna(row.get("close")):
                continue
            existing.loc[(day, name), list(existing.columns)] = [
                row.get(column) for column in existing.columns
            ]
            count += 1
        filled[name] = count
    report["filled"] = filled
    report["not_served"] = not_served
    if not write:
        return report

    # The panel's key is its index; writing it without one loses date and ticker.
    existing.to_parquet(path)
    for name, days in holes.items():
        stale.setdefault(name, []).extend(days)
    return _repair_returns(root, stored_returns, names, stale, report)


def _repair_returns(
    root: Path,
    stored: pd.DataFrame,
    names: list[str],
    stale: dict[str, list[pd.Timestamp]],
    report: dict[str, object],
) -> dict[str, object]:
    """Rewrite the named sessions' return rows from the repaired price series.

    Flags are rolling and per name, so they are rebuilt over that name's whole
    history and only the repaired sessions are written back.
    """
    pairs = [(day, name) for name, days in stale.items() for day in days]
    if not pairs:
        return report
    prices_frame = pd.read_parquet(root / "raw" / "prices.parquet")
    factors_frame = pd.read_parquet(root / "raw" / "factors_ff.parquet")
    subset = prices_frame.loc[
        prices_frame.index.get_level_values("ticker").isin(sorted(stale))
    ]
    recomputed = returns.compute_returns(subset, factors_frame["rf"])
    recomputed["stale"] = False
    recomputed["outlier"] = False
    recomputed = hygiene.apply_flags(recomputed)
    keys = pd.MultiIndex.from_tuples(
        [pair for pair in pairs if pair in recomputed.index], names=["date", "ticker"]
    )
    fresh = recomputed.reindex(keys)
    fresh = fresh.loc[fresh["r"].notna()]
    kept = stored.drop(index=keys.intersection(stored.index))
    merged = pd.concat([kept, fresh.loc[:, stored.columns]]).sort_index()
    merged.to_parquet(root / "processed" / "returns.parquet")
    report["returns_rows"] = int(len(fresh))
    return report


def refresh_variance(
    tree: Path | None = None,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
    *,
    dates: list[pd.Timestamp] | None = None,
    write: bool = True,
) -> dict[str, object]:
    """Recompute `specific_var` for a set of sessions out of the stored returns.

    The specific variance is an EWMA over the stored specific returns, shrunk toward
    the name's sector-size bucket mean, so it is a *function* of the artifact beside
    it. Anything that adds or repairs a specific return - a backfilled newcomer, a
    re-fit of one session - leaves every later variance row reading a history that no
    longer exists unless this runs over the range.

    `dates` wins over `start`/`end` when given. Rows outside the range are kept as
    they are, in their own order, with their own dtypes.
    """
    root = Path(tree) if tree is not None else DATA_ROOT
    xs_dir = root / "models" / "XS-v1"
    variance_path = xs_dir / "specific_var.parquet"
    specific_path = xs_dir / "specific_returns.parquet"
    prior = pd.read_parquet(variance_path)
    specific = pd.read_parquet(specific_path)
    wide = specific.pivot(
        index="date", columns="ticker", values="specific_return"
    ).sort_index()
    wide.index = pd.to_datetime(wide.index)
    if dates is None:
        first = pd.Timestamp(start) if start is not None else wide.index.min()
        last = pd.Timestamp(end) if end is not None else wide.index.max()
        wanted = [day for day in wide.index if first <= day <= last]
    else:
        wanted = [day for day in wide.index if day in set(pd.to_datetime(dates))]
    # The bucket terciles are ranked across the *columns of the cap frame*, so the
    # name set matters: restricting to the mapped names is what `extend_model` does,
    # and ranking over every name in the market cap panel puts each name in a
    # different tercile and rewrites the whole book's variance.
    inputs = probes.load_panel(root)
    labels = inputs["sectors"]
    close = inputs["close"]
    shares = inputs["shares"]
    mapped_names = inputs["mapped"]
    assert isinstance(labels, pd.Series)
    assert isinstance(close, pd.DataFrame)
    assert isinstance(shares, pd.DataFrame)
    assert isinstance(mapped_names, list)
    names = [str(name) for name in mapped_names]
    cap = fx.market_cap(close[names], shares[names])
    fresh = fx.specific_variance(wide, labels, cap, dates=wanted)
    changed = prior.loc[pd.to_datetime(prior["date"]).isin(wanted)]
    # The artifact's own order is kept: replace rows in place rather than resorting a
    # file every later step reads positionally.
    ordered = prior.reset_index(drop=True).assign(_order=range(len(prior)))
    kept = ordered.drop(index=changed.index)
    renewed = fresh.loc[:, prior.columns].merge(
        ordered[["date", "ticker", "_order"]], on=["date", "ticker"], how="left"
    )
    gaps = renewed["_order"].isna()
    renewed.loc[gaps, "_order"] = range(len(ordered), len(ordered) + int(gaps.sum()))
    merged = (
        pd.concat([kept, renewed], ignore_index=True)
        .sort_values("_order", kind="stable")
        .drop(columns="_order")
        .reset_index(drop=True)
    )
    for column in prior.columns:
        if column not in merged.columns:
            continue
        try:
            merged[column] = merged[column].astype(prior[column].dtype)
        except (TypeError, ValueError):
            pass
    if write:
        merged.to_parquet(variance_path, index=False)
    return {
        "sessions": [str(day.date()) for day in wanted],
        "n_sessions": len(wanted),
        "rows_before": int(len(changed)),
        "rows_after": int(len(merged) - len(kept)),
        "written": bool(write),
    }


def variance_for_newcomers(
    root: Path, newcomers: list[str], dates: list[pd.Timestamp]
) -> dict[str, object]:
    """Write the specific variance for the newcomers only, over the named sessions.

    `refresh_variance` recomputes the range for every name, which is right after a
    re-fit and wrong after a backfill: the bucket terciles are ranked across the
    mapped names and the shrink target is a bucket mean, so adding three names to the
    sector map moves *everyone's* shrunk variance - measured on 2026-10-30, a median
    of 0.37% and 3.6x on HON - and with it a fifth of the book. A newcomer's own rows
    are what the backfill is for; the rest of the table is left as it was, and the
    one inconsistency that buys (the newcomer is shrunk toward a bucket mean that does
    not count it) is what keeps every other name's row the row it was.
    """
    xs_dir = root / "models" / "XS-v1"
    prior = pd.read_parquet(xs_dir / "specific_var.parquet")
    specific = pd.read_parquet(xs_dir / "specific_returns.parquet")
    wide = specific.pivot(
        index="date", columns="ticker", values="specific_return"
    ).sort_index()
    wide.index = pd.to_datetime(wide.index)
    inputs = probes.load_panel(root)
    labels = inputs["sectors"]
    close = inputs["close"]
    shares = inputs["shares"]
    mapped_names = inputs["mapped"]
    assert isinstance(labels, pd.Series)
    assert isinstance(close, pd.DataFrame)
    assert isinstance(shares, pd.DataFrame)
    assert isinstance(mapped_names, list)
    names = [str(name) for name in mapped_names]
    cap = fx.market_cap(close[names], shares[names])
    fresh = fx.specific_variance(wide, labels, cap, dates=dates)
    fresh = fresh.loc[fresh["ticker"].astype(str).isin(set(newcomers))]
    if fresh.empty:
        return {"rows": 0}
    keys = pd.MultiIndex.from_arrays(
        [pd.to_datetime(fresh["date"]), fresh["ticker"].astype(str)],
        names=["date", "ticker"],
    )
    # The artifact's own order is kept: an untouched row stays where it was, and a
    # newcomer's rows land where the rows they replace would have been.
    ordered = prior.reset_index(drop=True).assign(_order=range(len(prior)))
    kept = ordered.drop(index=keys.intersection(prior.index))
    renewed = fresh.loc[:, prior.columns].merge(
        ordered[["date", "ticker", "_order"]], on=["date", "ticker"], how="left"
    )
    gaps = renewed["_order"].isna()
    renewed.loc[gaps, "_order"] = range(len(ordered), len(ordered) + int(gaps.sum()))
    merged = (
        pd.concat([kept, renewed], ignore_index=True)
        .sort_values("_order", kind="stable")
        .drop(columns="_order")
        .reset_index(drop=True)
    )
    for column in prior.columns:
        try:
            merged[column] = merged[column].astype(prior[column].dtype)
        except (TypeError, ValueError):
            pass
    merged.to_parquet(xs_dir / "specific_var.parquet", index=False)
    return {"rows": int(len(fresh)), "names": sorted(set(fresh["ticker"].astype(str)))}


def backfill_new_names(data_root: Path | None = None) -> dict[str, object]:
    """Load the panel and backfill every mapped name the artifact does not carry."""
    root = Path(data_root) if data_root is not None else DATA_ROOT
    inputs = probes.load_panel(root)
    returns_frame = race.design_panel(inputs)
    close = inputs["close"]
    volume = inputs["volume"]
    sectors = inputs["sectors"]
    mapped_names = inputs["mapped"]
    shares = inputs["shares"]
    look_ahead = inputs["look_ahead"]
    assert isinstance(mapped_names, list)
    assert isinstance(returns_frame, pd.DataFrame)
    assert isinstance(close, pd.DataFrame)
    assert isinstance(volume, pd.DataFrame)
    assert isinstance(sectors, pd.Series)
    assert isinstance(shares, pd.DataFrame)
    assert isinstance(look_ahead, pd.DataFrame)
    mapped: list[str] = [str(name) for name in mapped_names]
    cap = fx.market_cap(close[mapped], shares[mapped])
    proxy = fx.market_proxy(returns_frame[mapped], cap)
    design = fx.build_design(
        returns=returns_frame[mapped],
        close=close[mapped],
        volume=volume[mapped],
        market_cap=cap,
        sectors=sectors,
        proxy=proxy,
    )
    return _backfill(root, design, look_ahead[mapped], mapped)


def _backfill(
    root: Path, design: fx.DesignResult, look_ahead: pd.DataFrame, mapped: list[str]
) -> dict[str, object]:
    """Give a name that has just become sector-mapped the rows it never got.

    A GICS row is what puts a name into the design: `probes.load_panel` maps a ticker
    only when the sector table carries it, so a missing label does not just leave a
    name unlabelled, it removes the name from every cross-section until the label
    comes back. The label came back for BE, ILMN and P on 2026-10-31 and the design
    would only see them from the next session on: the artifact's descriptor and
    specific-return rows for the weeks they were out were never written, and without
    them there is no specific variance to size on either.

    So: for every mapped name the descriptor artifact has no rows for, rebuild the
    design over the whole panel and append that name's rows for the dates the artifact
    already covers - only the dates the cross-section itself accepts it, which is what
    keeps a name below the model's minimum history (momentum needs 231 sessions) out,
    exactly as it would be out of a fresh fit. The specific returns are the stored
    factor returns applied to that day's design row, not a re-fit, so the factor
    returns of those sessions stay the artifact they are; `reconstruction_error`
    measures that this reproduces the names that were already there.

    Nothing else is rewritten: no other name's descriptor or specific row changes.
    The specific variance is then refreshed over the backfilled sessions, which is the
    one place the rest of the book can move, because the bucket means it shrinks
    toward are cross-sectional.
    """
    xs_dir = root / "models" / "XS-v1"
    descriptor_path = xs_dir / "descriptors.parquet"
    existing = pd.read_parquet(descriptor_path)
    existing["date"] = pd.to_datetime(existing["date"])
    last = existing["date"].max()
    present = set(existing.loc[existing["date"] == last, "ticker"].astype(str))
    newcomers = sorted(name for name in mapped if name not in present)
    report: dict[str, object] = {
        "newcomers": newcomers,
        "descriptor_rows": 0,
        "specific_rows": 0,
        "sessions": [],
        "reconstruction_error": None,
    }
    if not newcomers:
        return report

    covered = set(existing["date"])
    # A newcomer is missing rows for *some* dates, not necessarily all of them: BE,
    # ILMN and P each have descriptor and specific rows up to the session the label
    # went missing. Only the dates it has no row for are the hole to fill; writing
    # over the ones it has would duplicate a key and rewrite a stored row with a
    # rebuild.
    have = set(
        zip(
            existing["date"].to_numpy(),
            existing["ticker"].astype(str).to_numpy(),
            strict=True,
        )
    )
    accepted: dict[pd.Timestamp, list[str]] = {}
    for day in design.days:
        if day.date not in covered:
            continue
        hits = [
            name
            for name in newcomers
            if name in set(day.tickers) and (day.date, name) not in have
        ]
        if hits:
            accepted[day.date] = hits
    if not accepted:
        return report

    wanted = sorted(accepted)
    descriptor_rows = _descriptor_rows_for_dates(
        design, wanted, look_ahead[mapped], newcomers
    )
    keep = pd.MultiIndex.from_tuples(
        [(day, name) for day in wanted for name in accepted[day]],
        names=["date", "ticker"],
    )
    descriptor_rows = descriptor_rows.set_index(["date", "ticker"])
    descriptor_rows = descriptor_rows.loc[
        descriptor_rows.index.isin(keep)
    ].reset_index()

    factor_path = xs_dir / "factor_returns.parquet"
    specific_path = xs_dir / "specific_returns.parquet"
    factor = pd.read_parquet(factor_path)
    factor["date"] = pd.to_datetime(factor["date"])
    # The fit's own vector is the pre-identification one: `identify` picks a
    # representative of the collinear family for reporting, and the residuals were
    # formed before it. Using the identified column instead moves a residual by up to
    # 2e-3, which is what the reconstruction check below would have caught.
    stored_factor = factor.pivot(
        index="date", columns="factor", values="f_pre_identification"
    )
    specific = pd.read_parquet(specific_path)
    specific["date"] = pd.to_datetime(specific["date"])
    prior_specific = specific.set_index(["date", "ticker"])["specific_return"]
    stored_z = existing.loc[
        existing["date"].isin(wanted), ["date", "ticker", "descriptor", "value_z_orth"]
    ].pivot(index=["date", "ticker"], columns="descriptor", values="value_z_orth")
    styles = list(fx.STYLE_NAMES)
    columns = styles + [
        f"sector_{fx.SECTOR_CODES[sector]}" for sector in fx.SECTOR_NAMES[:-1]
    ]

    rows: list[dict[str, object]] = []
    kept_dates: list[pd.Timestamp] = []
    skipped: list[str] = []
    error = 0.0
    drift = 0.0
    for day in design.days:
        wanted_names = accepted.get(day.date)
        if not wanted_names:
            continue
        factors = stored_factor.loc[day.date].reindex(columns).to_numpy(dtype=float)
        # The newcomer's own design row comes from this rebuild; every other name's
        # comes from the artifact, so `reconstruction_error` measures the factor
        # vector and `design_drift` how far the rebuild is from the rows the session
        # was fitted on. A session whose own stored rows do not come back is not one
        # to write a residual for, so it is left alone and named.
        residual = day.returns - day.design @ factors
        positions = {str(name): index for index, name in enumerate(day.tickers)}
        labels = dict(
            zip([str(t) for t in day.tickers], list(day.sector_names), strict=True)
        )
        held = [name for name in positions if name not in set(wanted_names)]
        held = [name for name in held if (day.date, name) in stored_z.index]
        session_error = 0.0
        checked = 0
        for name in held:
            stored_row = stored_z.loc[(day.date, name)].reindex(styles).to_numpy(float)
            if np.isnan(stored_row).any():
                continue
            dummy = np.array(
                [
                    1.0 if labels[name] == sector else 0.0
                    for sector in fx.SECTOR_NAMES[:-1]
                ]
            )
            rebuilt = (
                day.returns[positions[name]]
                - np.concatenate([stored_row, dummy]) @ factors
            )
            value = prior_specific.get((day.date, name))
            if value is None or pd.isna(value):
                continue
            session_error = max(session_error, abs(float(value) - rebuilt))
            checked += 1
            design_row = day.design[positions[name]][: len(styles)]
            drift = max(drift, float(np.nanmax(np.abs(stored_row - design_row))))
        if checked and session_error > 1e-9:
            skipped.append(str(day.date.date()))
            continue
        error = max(error, session_error)
        kept_dates.append(day.date)
        for name in wanted_names:
            rows.append(
                {
                    "date": day.date,
                    "ticker": name,
                    "specific_return": float(residual[positions[name]]),
                }
            )
    report["reconstruction_error"] = error
    report["design_drift"] = drift
    report["sessions_not_reproduced"] = skipped
    wanted_kept = sorted(kept_dates)
    if not wanted_kept:
        raise ValueError(
            "no session's stored factor returns reproduce its stored specific "
            "returns, so a backfilled row would not be the one a fit wrote"
        )
    if error > 1e-9:
        raise ValueError(
            "the stored factor returns do not reproduce the stored specific "
            f"returns (max |gap| {error:g}) on a session that would be written"
        )
    if not rows:
        return report
    descriptor_rows = descriptor_rows.loc[
        descriptor_rows["date"].isin(wanted_kept)
    ].reset_index(drop=True)

    pd.concat([existing, descriptor_rows], ignore_index=True).to_parquet(
        descriptor_path, index=False
    )
    pd.concat([specific, pd.DataFrame(rows)], ignore_index=True).to_parquet(
        specific_path, index=False
    )
    variance = variance_for_newcomers(root, newcomers, wanted_kept)
    report["descriptor_rows"] = int(len(descriptor_rows))
    report["specific_rows"] = int(len(rows))
    report["sessions"] = [str(day.date()) for day in wanted_kept]
    report["variance_rows"] = variance.get("rows", 0)
    return report


def revert_model_to_frozen(data_root: Path | None = None) -> None:
    """Trim every XS-v1 artifact back to the frozen as-of.

    Used after an extension is rolled back: the rows dated after
    FROZEN_AS_OF are removed and the factor covariance snapshot is
    recomputed from the frozen factor returns, so the next extension
    restarts from the frozen state.
    """
    root = Path(data_root) if data_root is not None else DATA_ROOT
    xs_dir = root / "models" / "XS-v1"
    trimmed_names = (
        "descriptors",
        "factor_returns",
        "specific_returns",
        "xs_r2",
        "specific_var",
    )
    for name in trimmed_names:
        path = xs_dir / f"{name}.parquet"
        frame = pd.read_parquet(path)
        trimmed = frame.loc[pd.to_datetime(frame["date"]) <= FROZEN_AS_OF]
        trimmed.to_parquet(path, index=False)
    factor = pd.read_parquet(xs_dir / "factor_returns.parquet")
    factor_wide = (
        factor.pivot(index="date", columns="factor", values="f")
        .reindex(columns=list(fx.FACTOR_NAMES))
        .dropna()
    )
    fx.ewma_factor_cov(factor_wide, half_life=fx.F_HALF_LIFE).to_parquet(
        xs_dir / "factor_cov.parquet"
    )


def _block_hash(frame: pd.DataFrame, cutoff: pd.Timestamp) -> str:
    """SHA-256 of the rows dated on or before the cutoff, row order fixed."""
    import hashlib

    block = frame.loc[pd.to_datetime(frame["date"]) <= cutoff].copy()
    sort_keys = ["date", "ticker"]
    if "descriptor" in block.columns:
        sort_keys = ["date", "ticker", "descriptor"]
    elif "factor" in block.columns:
        sort_keys = ["date", "factor"]
    block = block.sort_values(sort_keys)
    serialized = block.to_csv(index=False).encode()
    return hashlib.sha256(serialized).hexdigest()


def incremental_integrity(
    data_root: Path | None = None, cutoff: pd.Timestamp = FROZEN_AS_OF
) -> dict[str, str]:
    """The hash of the pre-cutoff block of each extended cross-sectional artifact."""
    root = Path(data_root) if data_root is not None else DATA_ROOT
    xs_dir = root / "models" / "XS-v1"
    out: dict[str, str] = {}
    for name in ("descriptors", "factor_returns", "specific_returns"):
        frame = pd.read_parquet(xs_dir / f"{name}.parquet")
        out[name] = _block_hash(frame, cutoff)
    return out
