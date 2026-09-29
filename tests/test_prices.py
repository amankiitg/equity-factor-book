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
