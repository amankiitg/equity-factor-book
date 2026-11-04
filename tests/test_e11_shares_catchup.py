"""The share counts catch up, and a retired name cannot hold the gate open.

On 2026-11-03 the evening stopped before pricing: `shares 1 session behind (allowed
0)`. The share-count artifact is gated on its **fetch** date and the cache was only
ever added to, so the stamp advanced only on an evening that added a ticker. The two
names added on 2026-11-02 (BE and P) stamped it 2026-11-02; the 2026-11-03 run added
nothing, so the stamp stood still and the gate refused the close.

KVUE is the name that makes the other half of the rule concrete: it completed its
merger into KMB on 2026-11-02, it prints no close after that, and no amount of asking
will give it a new row. A catch-up that waited for it would wait forever.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from efb import probes
from live import extend, staleness

CLOSE = pd.Timestamp("2026-11-03")
STAMPED = pd.Timestamp("2026-11-02")


def _tree(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    raw.mkdir()
    index = pd.MultiIndex.from_product(
        [[STAMPED, CLOSE], ["AAPL", "KVUE"]], names=["date", "ticker"]
    )
    # KVUE printed on 2026-11-02 and nothing on 2026-11-03: the merger completed.
    prices = pd.DataFrame({"close": [100.0, 19.31, 101.0, float("nan")]}, index=index)
    prices.to_parquet(raw / "prices.parquet")
    rows = [
        {
            "ticker": ticker,
            "date": STAMPED,
            "shares": 1_000.0,
            "source": "test",
            "fetched_at": STAMPED.isoformat(),
            "status": "ok",
        }
        for ticker in ("AAPL", "KVUE")
    ]
    pd.DataFrame(rows).to_parquet(raw / "shares_history.parquet", index=False)
    return tmp_path


def test_the_stamp_is_what_the_gate_reads(tmp_path: Path) -> None:
    """One session behind is a stop, and the rule is the panel's newest fetch."""
    tree = _tree(tmp_path)
    cache = tree / "raw" / "shares_history.parquet"
    assert extend._shares_fetch_stamp(cache) == STAMPED
    behind = staleness.sessions_behind(extend._shares_fetch_stamp(cache), CLOSE)
    assert behind == 1
    assert staleness.ALLOWED_SESSIONS_BEHIND["shares"] == 0
    assert staleness.GATED_BY["shares"] == "fetch"


def test_a_stale_cache_is_refreshed_for_the_names_that_still_trade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The catch-up asks the trading names and leaves the retired one alone."""
    tree = _tree(tmp_path)
    asked: list[str] = []

    def fetcher(symbol: str) -> pd.Series:
        asked.append(symbol)
        return pd.Series([1_050.0], index=[CLOSE])

    monkeypatch.setattr(probes, "_yfinance_shares_fetcher", fetcher)
    monkeypatch.setattr(extend, "_live_tickers", lambda root: ["AAPL", "KVUE"])

    extend.extend_shares(data_root=tree, end=str(CLOSE.date()))

    assert asked == [
        "AAPL"
    ], "KVUE prints no close on the session, so it cannot be refreshed"
    frame = pd.read_parquet(tree / "raw" / "shares_history.parquet")
    assert extend._shares_fetch_stamp(tree / "raw" / "shares_history.parquet") > STAMPED
    # the retired name keeps the row it had; nothing is invented for it
    kvue = frame.loc[frame["ticker"] == "KVUE"]
    assert len(kvue) == 1
    assert pd.Timestamp(kvue.iloc[0]["fetched_at"]) == STAMPED
    assert (
        staleness.sessions_behind(
            extend._shares_fetch_stamp(tree / "raw" / "shares_history.parquet"), CLOSE
        )
        == 0
    )


def test_the_refresh_replaces_the_rows_rather_than_appending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = _tree(tmp_path)
    monkeypatch.setattr(
        probes,
        "_yfinance_shares_fetcher",
        lambda symbol: pd.Series([1_050.0, 1_060.0], index=[STAMPED, CLOSE]),
    )
    monkeypatch.setattr(extend, "_live_tickers", lambda root: ["AAPL", "KVUE"])
    extend.extend_shares(data_root=tree, end=str(CLOSE.date()))
    frame = pd.read_parquet(tree / "raw" / "shares_history.parquet")
    aapl = frame.loc[frame["ticker"] == "AAPL"]
    assert len(aapl) == 2, "the refreshed name carries the vendor's series once"
    assert set(aapl["shares"]) == {1_050.0, 1_060.0}


def test_a_failed_refresh_leaves_the_gate_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rule is not loosened: no answer means the stamp does not move."""
    tree = _tree(tmp_path)

    def fetcher(symbol: str) -> pd.Series:
        raise RuntimeError("the vendor is down")

    monkeypatch.setattr(probes, "_yfinance_shares_fetcher", fetcher)
    monkeypatch.setattr(extend, "_live_tickers", lambda root: ["AAPL", "KVUE"])

    extend.extend_shares(data_root=tree, end=str(CLOSE.date()))

    assert (
        extend._shares_fetch_stamp(tree / "raw" / "shares_history.parquet") == STAMPED
    )
    assert (
        staleness.sessions_behind(
            extend._shares_fetch_stamp(tree / "raw" / "shares_history.parquet"), CLOSE
        )
        == 1
    )


def test_a_fresh_cache_asks_nobody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The catch-up is a repair, not a nightly full read."""
    tree = _tree(tmp_path)
    asked: list[str] = []

    def fetcher(symbol: str) -> pd.Series:
        asked.append(symbol)
        return pd.Series([1_050.0], index=[CLOSE])

    monkeypatch.setattr(probes, "_yfinance_shares_fetcher", fetcher)
    monkeypatch.setattr(extend, "_live_tickers", lambda root: ["AAPL", "KVUE"])
    stamp = pd.Timestamp.now().normalize() + pd.Timedelta(days=1)
    cache = tree / "raw" / "shares_history.parquet"
    frame = pd.read_parquet(cache)
    frame["fetched_at"] = stamp.isoformat()
    frame.to_parquet(cache, index=False)

    extend.extend_shares(data_root=tree, end=str(stamp.date()))
    assert asked == []
