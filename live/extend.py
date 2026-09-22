"""Sprint E11 live: daily incremental extension of the data and model.

Every function appends one or more sessions, never refits history. Rows
dated on or before 2026-09-03 come back byte-identical, which
`incremental_integrity` asserts with hashes. Prices and share counts come
from yfinance, the same vendor E1 uses.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from efb import hygiene, prices, probes, returns, spy, universe
from efb.models import fundamental as fx

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
FROZEN_AS_OF = pd.Timestamp("2026-09-03")


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


def extend_archives(data_root: Path = DATA_ROOT) -> dict[str, str]:
    """Fetch and archive a fresh SPY holdings file and Wikipedia snapshot."""
    fetched = spy.fetch_spy_holdings()
    spy_path = spy.archive_snapshot(fetched["equity"], fetched["as_of"], data_root)
    wiki_path = universe.archive_constituents(data_root)
    return {
        "spy_as_of": str(spy_path.stem).replace("spy_holdings_", ""),
        "wiki_as_of": str(wiki_path.stem).replace("wikipedia_constituents_", ""),
    }


def extend_prices(
    data_root: Path = DATA_ROOT,
    end: str | None = None,
    tickers: list[str] | None = None,
) -> int:
    """Download the sessions after the last stored price and append them.

    Returns the number of new sessions appended. Nothing is overwritten:
    rows already present keep their values.
    """
    root = Path(data_root)
    path = root / "raw" / "prices.parquet"
    existing = pd.read_parquet(path)
    last_date = pd.Timestamp(existing.index.get_level_values("date").max())
    if tickers is None:
        tickers = _frozen_tickers(root)
    end = end or pd.Timestamp.now().strftime("%Y-%m-%d")
    tail = prices.download_prices(tickers, start=str(last_date.date()), end=end)
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


def extend_returns(data_root: Path = DATA_ROOT) -> int:
    """Recompute returns and flags over the extended price frame.

    Returns the number of new sessions now in processed/returns.parquet.
    """
    root = Path(data_root)
    path = root / "processed" / "returns.parquet"
    before = pd.read_parquet(path).index.get_level_values("date").nunique()
    prices_frame = pd.read_parquet(root / "raw" / "prices.parquet")
    factors_frame = pd.read_parquet(root / "raw" / "factors_ff.parquet")
    returns_frame = returns.compute_returns(prices_frame, factors_frame["rf"])
    returns_frame = hygiene.apply_flags(returns_frame)
    returns_frame.to_parquet(path)
    after = pd.read_parquet(path).index.get_level_values("date").nunique()
    return int(after - before)


def extend_shares(data_root: Path = DATA_ROOT, tickers: list[str] | None = None) -> int:
    """Fetch share counts for names not yet in the cache and append.

    Returns the number of names newly fetched. Cached names are not
    re-asked, because a share count does not change unless a corporate
    action does.
    """
    root = Path(data_root)
    if tickers is None:
        tickers = _frozen_tickers(root)
    before = set()
    cache = root / "raw" / "shares_history.parquet"
    if cache.exists():
        before = set(pd.read_parquet(cache)["ticker"])
    probes.fetch_share_history(tickers)
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


def extend_model(data_root: Path = DATA_ROOT) -> dict[str, object]:
    """Append one or more sessions to the XS-v1 artifacts.

    Descriptors, factor returns and specific returns are fitted only for
    the new sessions; the pre-2026-09-04 rows are never touched. The factor
    covariance snapshot and the specific variance roll forward by one
    session each.
    """
    root = Path(data_root)
    xs_dir = root / "models" / "XS-v1"
    inputs = probes.load_panel(root)
    returns_frame = inputs["returns"]
    close = inputs["close"]
    volume = inputs["volume"]
    sectors = inputs["sectors"]
    mapped = inputs["mapped"]
    shares = inputs["shares"]
    look_ahead = inputs["look_ahead"]
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
    if not new_dates:
        return {"extended": 0, "last_date": str(last.date())}

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
    }


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
    data_root: Path = DATA_ROOT, cutoff: pd.Timestamp = FROZEN_AS_OF
) -> dict[str, str]:
    """The hash of the pre-cutoff block of each extended cross-sectional artifact."""
    root = Path(data_root)
    xs_dir = root / "models" / "XS-v1"
    out: dict[str, str] = {}
    for name in ("descriptors", "factor_returns", "specific_returns"):
        frame = pd.read_parquet(xs_dir / f"{name}.parquet")
        out[name] = _block_hash(frame, cutoff)
    return out
