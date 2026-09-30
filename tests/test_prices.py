"""Tests for Task 1: yfinance price pipeline and adjusted-close audit."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb import prices


def _frame(ticker: str, close: list[float], dividend: list[float]) -> pd.DataFrame:
    idx = pd.MultiIndex.from_product(
        [pd.bdate_range("2026-07-01", periods=len(close)), [ticker]],
        names=["date", "ticker"],
    )
    close_a = np.asarray(close, dtype=float)
    div_a = np.asarray(dividend, dtype=float)
    return pd.DataFrame(
        {
            "open": close_a - 0.5,
            "high": close_a + 1.0,
            "low": close_a - 1.0,
            "close": close_a,
            "adj_close": np.nan,
            "volume": 1_000_000,
            "dividend": div_a,
            "split_factor": 0.0,
        },
        index=idx,
    )


def _total_return_index(close: list[float], dividend: list[float]) -> list[float]:
    """Adj close implied by close + dividends, scaled to start at close[0]."""
    out = [float(close[0])]
    for t in range(1, len(close)):
        out.append(out[-1] * (close[t] + dividend[t]) / close[t - 1])
    return out


def test_yf_ticker_maps_share_classes() -> None:
    assert prices.yf_ticker("BF.B") == "BF-B"
    assert prices.yf_ticker("AAPL") == "AAPL"


def test_audit_adjusted_close_zero_when_consistent() -> None:
    close = [100.0, 101.0, 102.0, 100.5, 101.5]
    dividend = [0.0, 0.0, 0.0, 1.5, 0.0]
    frame = _frame("AAA", close, dividend)
    frame["adj_close"] = _total_return_index(close, dividend)
    result = prices.audit_adjusted_close(frame, ["AAA"], n_names=1, seed=0)
    assert result["max_abs_bp"] == pytest.approx(0.0, abs=1e-6)
    assert result["mean_abs_bp"] == pytest.approx(0.0, abs=1e-6)


def test_audit_adjusted_close_handles_split() -> None:
    # yfinance delivers Close already split-adjusted: on the split date the
    # close drops by the ratio, and adj_close is the total-return index
    # consistent with close + dividends. The audit must not reapply splits.
    close = [100.0, 101.0, 102.0, 25.5, 26.0]  # 4:1 split reflected in close
    dividend = [0.0, 0.0, 0.0, 0.0, 0.0]
    frame = _frame("AAA", close, dividend)
    frame.loc[
        frame.index.get_level_values("date") == pd.Timestamp("2026-07-06"),
        "split_factor",
    ] = 4.0
    frame["adj_close"] = _total_return_index(close, dividend)
    result = prices.audit_adjusted_close(frame, ["AAA"], n_names=1, seed=0)
    assert result["max_abs_bp"] == pytest.approx(0.0, abs=1e-6)


def test_audit_adjusted_close_detects_mismatch() -> None:
    close = [100.0, 101.0, 102.0, 100.5, 101.5]
    dividend = [0.0, 0.0, 0.0, 1.5, 0.0]
    frame = _frame("AAA", close, dividend)
    tri = _total_return_index(close, dividend)
    tri[2] *= 1.001  # a 10 bp fake move
    frame["adj_close"] = tri
    result = prices.audit_adjusted_close(frame, ["AAA"], n_names=1, seed=0)
    assert result["max_abs_bp"] > 5.0


def test_load_or_download_uses_complete_cache(tmp_path: Path, monkeypatch) -> None:
    cache = tmp_path / "cache.parquet"
    frame = _frame("AAA", [100.0, 101.0], [0.0, 0.0])
    frame["adj_close"] = frame["close"]
    prices.save_prices(frame, cache)

    def _explode(*args, **kwargs):
        raise AssertionError("downloader must not run when cache is complete")

    monkeypatch.setattr(prices, "download_prices", _explode)
    out = prices.load_or_download(["AAA"], cache)
    assert list(out.columns) == prices.FIELDS


def test_load_or_download_downloads_when_ticker_missing(
    tmp_path: Path, monkeypatch
) -> None:
    cache = tmp_path / "cache.parquet"
    frame = _frame("AAA", [100.0, 101.0], [0.0, 0.0])
    frame["adj_close"] = frame["close"]
    prices.save_prices(frame, cache)
    called: list[str] = []

    def _fake_download(tickers, start, end):
        called.extend(tickers)
        extra = _frame("BBB", [10.0, 11.0], [0.0, 0.0])
        extra["adj_close"] = extra["close"]
        return pd.concat([frame, extra])

    monkeypatch.setattr(prices, "download_prices", _fake_download)
    out = prices.load_or_download(["AAA", "BBB"], cache)
    assert "BBB" in called
    assert "BBB" in out.index.get_level_values("ticker")


def test_build_prices_artifact_clips_to_start(tmp_path: Path) -> None:
    frame = _frame("AAA", [100.0, 101.0, 102.0], [0.0, 0.0, 0.0])
    frame["adj_close"] = frame["close"]
    artifact = prices.build_prices_artifact(frame, start="2026-07-02")
    assert artifact.index.get_level_values("date").min() >= pd.Timestamp("2026-07-02")
    assert set(artifact.columns) == set(prices.FIELDS)


def test_a_run_does_not_use_the_shared_tz_cache(tmp_path: Path, monkeypatch) -> None:
    """The SQLite caches move to a directory this process owns.

    yfinance keeps its timezone, cookie and ISIN caches in one SQLite directory,
    and the default is shared: on Render `/opt/render/.cache/py-yfinance`, which
    every run on an instance opens at once. Two runs then contend for the same
    file and SQLite refuses with `OperationalError('database is locked')`, which
    yfinance reports as a failed download for whichever symbol lost the race. The
    run is not stopped by it, which is what makes it dangerous: a name quietly
    drops out of the book. The directory is also created here rather than by the
    library, whose own `os.makedirs` has no `exist_ok` and raises `File exists`.
    """
    from yfinance import cache as yf_cache

    monkeypatch.setattr(prices, "_TZ_CACHE_DIR", None)
    shared = Path(yf_cache._TzDBManager.get_location())

    target = prices.use_private_tz_cache(tmp_path / "run-a")

    assert target.is_dir(), "the directory was not created for the library to use"
    assert target.parent == tmp_path / "run-a"
    # The library really moved, and it moved all three caches with it: one call is
    # what `set_tz_cache_location` forwards to the tz, cookie and ISIN managers.
    assert Path(yf_cache._TzDBManager.get_location()) == target
    assert Path(yf_cache._CookieDBManager.get_location()) == target
    assert Path(yf_cache._ISINDBManager.get_location()) == target
    # and the shared file is not the one this process opens
    assert target != shared


def test_two_runs_cannot_share_one_cache(tmp_path: Path, monkeypatch) -> None:
    """The property that matters: run B's cache is not run A's.

    Two cron runs on one instance is how Monday lost a symbol, so the directory is
    derived per run rather than per instance.
    """
    from yfinance import cache as yf_cache

    monkeypatch.setattr(prices, "_TZ_CACHE_DIR", None)
    first = prices.use_private_tz_cache(tmp_path / "run-a")
    second = prices.use_private_tz_cache(tmp_path / "run-b")

    assert first != second
    assert Path(yf_cache._TzDBManager.get_location()) == second


def test_a_process_asks_the_library_once(monkeypatch) -> None:
    """Within one run the directory is remembered rather than remade per download.

    A price download, the share lookups and the corporate-action cross-check all
    run in one process, and they have to share one cache: pointing the library at a
    fresh directory each time would throw away the symbols already looked up.
    """
    monkeypatch.setattr(prices, "_TZ_CACHE_DIR", None)
    calls: list[str] = []
    monkeypatch.setattr(
        prices.yf, "set_tz_cache_location", lambda path: calls.append(path)
    )

    first = prices.use_private_tz_cache()
    again = prices.use_private_tz_cache()

    assert first == again
    assert calls == [str(first)], calls
    assert first.is_dir()
    # the default is a private temporary directory, not the shared default one
    assert "py-yfinance" not in str(first)


def _wide_download(symbols, dates) -> pd.DataFrame:
    """A frame shaped like `yf.download`'s, with every field present."""
    fields = list(prices.RENAME)
    return pd.DataFrame(
        1.0,
        index=pd.DatetimeIndex(dates),
        columns=pd.MultiIndex.from_product([symbols, fields]),
    )


class _FakeCache:
    """The two methods the prewarm uses, with the rows kept where a test can see."""

    def __init__(self) -> None:
        self.rows: dict[str, str] = {}
        self.lookups: list[str] = []
        self.stores: list[tuple[str, str]] = []

    def lookup(self, key: str) -> str | None:
        self.lookups.append(key)
        return self.rows.get(key)

    def store(self, key: str, value: str) -> None:
        self.stores.append((key, value))
        self.rows[key] = value


def test_the_prewarm_writes_a_timezone_row_for_every_ticker(
    tmp_path: Path, monkeypatch
) -> None:
    """One row per ticker, written serially, before any thread can race for it.

    yfinance writes a timezone row per ticker the first time it prices it, so a cold
    run hands its threaded download 504 writes to one SQLite file and two threads
    writing at once is `OperationalError('database is locked')`: the symbol that
    loses comes back with no price and the run does not fail. Measured on
    2026-09-29: 3 of 12 cold 504-name fetches lost exactly one symbol (EVRG, BA,
    ACGL), and none of the repeats against a warm cache lost any. The prewarm is
    what makes the threaded pass read-only.

    The cache is a fake rather than the library's own object, because the library
    keeps one instance for the process that stays bound to whichever directory it
    first opened: in a test session that is an earlier test's directory, and its
    rows would make this test pass without the prewarm doing anything.
    """
    from yfinance import cache as yf_cache

    monkeypatch.setattr(prices, "_TZ_CACHE_DIR", None)
    cache = _FakeCache()
    monkeypatch.setattr(yf_cache, "get_tz_cache", lambda: cache)
    state: dict[str, object] = {"inside": False, "order": [], "timeouts": []}

    class FakeTicker:
        """yfinance's own lookup, minus the network: it stores the row it resolves."""

        def __init__(self, symbol: str) -> None:
            assert state["inside"] is False, "two tickers were resolved at once"
            self.symbol = symbol

        def _get_ticker_tz(self, timeout: float | None = None) -> str | None:
            state["inside"] = True
            try:
                state["order"].append(self.symbol)  # type: ignore[union-attr]
                state["timeouts"].append(timeout)  # type: ignore[union-attr]
                if self.symbol == "NOPE":
                    return None
                cache.store(self.symbol, "America/New_York")
                return "America/New_York"
            finally:
                state["inside"] = False

    monkeypatch.setattr(prices.yf, "Ticker", FakeTicker)
    # the directory is the run's own, which is where those rows have to land
    target = prices.use_private_tz_cache(tmp_path / "cache")
    assert Path(yf_cache._TzDBManager.get_location()) == target

    report = prices.prewarm_tz_cache(["AAPL", "BF.B", "CSGP", "NOPE"])

    # every ticker was asked for, in order, one at a time, and the share class went
    # as the symbol the vendor uses
    assert cache.lookups == ["AAPL", "BF-B", "CSGP", "NOPE"]
    assert state["order"] == ["AAPL", "BF-B", "CSGP", "NOPE"]
    assert state["timeouts"] == [10.0, 10.0, 10.0, 10.0]
    # and each resolved row was written, before anything threaded can run
    assert cache.stores == [
        ("AAPL", "America/New_York"),
        ("BF-B", "America/New_York"),
        ("CSGP", "America/New_York"),
    ]
    assert report == {
        "requested": 4,
        "resolved": 3,
        "already_cached": 0,
        "unresolved": 1,
    }
    # a ticker the vendor will not answer for writes nothing, so it cannot be a
    # second thread's race either
    assert "NOPE" not in cache.rows

    # a second call over the same list resolves nothing that has a row: the threaded
    # pass has nothing left to write. The one ticker with no row is asked again,
    # because a cache miss is the only thing that can be retried safely here.
    resolved_before = list(state["order"])
    again = prices.prewarm_tz_cache(["AAPL", "BF.B", "CSGP", "NOPE"])
    assert again == {
        "requested": 4,
        "resolved": 0,
        "already_cached": 3,
        "unresolved": 1,
    }
    assert state["order"] == resolved_before + ["NOPE"], "a cached ticker was resolved"


def test_the_download_asks_for_the_prewarm_before_it_starts_its_threads(
    tmp_path: Path, monkeypatch
) -> None:
    """The order is the fix: rows first, threads second, and the retry unthreaded.

    The download's threads only read the cache when every requested row is already
    written, so the test stands where `yf.download` does and asserts the rows are
    there at that moment rather than counting calls afterwards.
    """
    from yfinance import cache as yf_cache

    monkeypatch.setattr(prices, "_TZ_CACHE_DIR", None)
    cache = _FakeCache()
    monkeypatch.setattr(yf_cache, "get_tz_cache", lambda: cache)
    events: list[str] = []

    def _prewarm(tickers, timeout=10.0):  # noqa: ANN001
        events.append("prewarm " + ",".join(tickers))
        for ticker in tickers:
            cache.store(prices.yf_ticker(ticker), "America/New_York")
        return {"requested": len(tickers)}

    def _download(symbols, **kwargs):  # noqa: ANN001
        events.append("download " + ",".join(sorted(symbols)))
        assert all(
            cache.lookup(s) for s in symbols
        ), "a ticker reached the threaded download without its timezone row"
        events.append(f"threads={kwargs['threads']}")
        return _wide_download(sorted(symbols), pd.bdate_range("2026-09-28", periods=2))

    monkeypatch.setattr(prices, "prewarm_tz_cache", _prewarm)
    monkeypatch.setattr(prices.yf, "download", _download)

    # the live fetch asks for the prewarm, and asks for the mapping to happen
    frame = prices.download_prices(
        ["BF.B", "AAPL"], start="2026-09-28", end="2026-09-30", prewarm=True
    )
    assert events == [
        "prewarm AAPL,BF.B",
        "download AAPL,BF-B",
        "threads=True",
    ], events
    assert set(frame.index.get_level_values("ticker")) == {"AAPL", "BF.B"}

    # the retry of a handful of names is the unthreaded pass
    events.clear()
    prices.download_prices(
        ["AAPL"], start="2026-09-28", end="2026-09-30", threads=False
    )
    assert events == ["download AAPL", "threads=False"], events
    # and a caller that did not ask for the prewarm pays for nothing
    events.clear()
    prices.download_prices(["AAPL"], start="2026-09-28", end="2026-09-30")
    assert events == ["download AAPL", "threads=True"], events


def test_missing_tickers_is_the_names_the_frame_never_priced() -> None:
    """A refused symbol and a delisted one look the same, which is the point.

    Both arrive with rows and no close, so both leave the book with nothing to
    quantize on. The fetch retries the set and the book drops what the retry could
    not recover, so this helper must not pretend to know which is which.
    """
    dates = pd.bdate_range("2026-09-28", periods=2)
    index = pd.MultiIndex.from_product(
        [dates, ["AAA", "BBB"]], names=["date", "ticker"]
    )
    frame = pd.DataFrame({"close": [1.0, np.nan, 1.0, np.nan]}, index=index)
    session = "2026-09-28"
    assert prices.missing_tickers(frame, ["AAA", "BBB"], session=session) == ["BBB"]
    assert prices.missing_tickers(frame, ["AAA"], session=session) == []
    # nothing came back at all, which is the case the prewarm cannot help with
    assert prices.missing_tickers(None, ["AAA", "BBB"], session=session) == [
        "AAA",
        "BBB",
    ]
    assert prices.missing_tickers(pd.DataFrame(), ["AAA"], session=session) == ["AAA"]
    # a frame that does not carry the session at all is missing everything on it
    assert prices.missing_tickers(frame, ["AAA"], session="2026-09-30") == ["AAA"]
    # and a name that is priced on that session is not missing, whatever the rest of
    # the window looks like
    assert prices.missing_tickers(frame, ["AAA"], session="2026-09-29") == []


def test_missing_tickers_reads_the_session_the_book_is_priced_from() -> None:
    """A name priced on the earlier sessions and not on the close is missing.

    This is CSGP on 2026-09-29, in the run that had every fix in it: the fetched
    window came back for the name on the earlier sessions and had no bar for the
    close being priced. The window-wide check called that covered, so the
    single-threaded retry never ran and the book dropped the name without the log
    saying a retry had been skipped. The session reading is the question the book
    needs answered, and the window reading is not a substitute for it.
    """
    days = pd.bdate_range("2026-09-25", "2026-09-29")
    index = pd.MultiIndex.from_product(
        [days, ["CSGP", "AAPL"]], names=["date", "ticker"]
    )
    frame = pd.DataFrame({"close": 1.0}, index=index)
    frame.loc[(pd.Timestamp("2026-09-29"), "CSGP"), "close"] = float("nan")

    # the name answered for the earlier sessions of the window
    closes = frame.index.get_level_values("date")
    earlier = frame.loc[closes < pd.Timestamp("2026-09-29")]
    assert prices.missing_tickers(earlier, ["CSGP"], session="2026-09-28") == []
    # and has nothing on the close the book is priced from
    assert prices.missing_tickers(frame, ["CSGP", "AAPL"], session="2026-09-29") == [
        "CSGP"
    ]
