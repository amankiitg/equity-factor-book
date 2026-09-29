"""Measure the yfinance timezone-cache race, and what the prewarm and retry do to it.

One fresh process, the run's own ticker list, the real vendor:

    .venv/bin/python scripts/probe_cache_race.py baseline   # no prewarm
    .venv/bin/python scripts/probe_cache_race.py prewarm    # prewarm, then fetch

`baseline` is the run as it was: yfinance writes one timezone row per ticker from
inside the threaded download, and when two threads write together SQLite refuses
with `OperationalError('database is locked')` for whichever symbol lost, which
yfinance reports as a failed download. The frame still carries that symbol's rows
and no prices, so nothing downstream raises: the name is simply gone. In both modes
the script reports how many timezone rows the download wrote, which names came back
without a close, and what the single-threaded retry recovered.

Measured 2026-09-29 on the 504-name live fetch, this Mac, yfinance 1.7.0:

  baseline  6 runs: 2 lost exactly one symbol (XYL, MS), 504 timezone rows written
            by the download, retry recovered 1 of 1 both times
  prewarm   3 runs: 0 lost, 0 rows written by the download, prewarm 41 to 48s for
            504 rows (the fetch itself is about 10s)

The prewarm is the fix and it is not free; the cost is one small serial request per
ticker, once per run, in exchange for a fetch whose threaded pass only reads.
"""

import os
import sys
import time
from pathlib import Path

import pandas as pd
from yfinance import cache as yf_cache

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from efb import prices  # noqa: E402 - after the path line
from live import extend  # noqa: E402 - after the path line

archive = pd.read_parquet(
    sorted(Path("data/raw/spy_holdings").glob("spy_holdings_*.parquet"))[-1]
)
TICKERS = sorted({str(t).upper().strip() for t in archive["ticker"]} | {"SPY", "AAPL"})
START, END = "2026-09-28", "2026-09-30"

mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
writes = {"n": 0}
original_store = yf_cache._TzCache.store


def counted_store(self, *args, **kwargs):  # noqa: ANN001
    writes["n"] += 1
    return original_store(self, *args, **kwargs)


yf_cache._TzCache.store = counted_store

started = time.perf_counter()
warm = None
if mode == "prewarm":
    # the live order: the private directory first, then the serial rows, then the
    # threaded download over the same directory
    cache_dir = prices.use_private_tz_cache()
    warm = prices.prewarm_tz_cache(TICKERS)
    warm_seconds = time.perf_counter() - started
    writes["n"] = 0

frame = prices.download_prices(
    TICKERS, start=START, end=END, prewarm=False
)
fetch_seconds = time.perf_counter() - started
missing = prices.missing_tickers(frame, TICKERS)

print(
    f"{mode:9s} | tickers {len(TICKERS)} | timezone rows written during the "
    f"download: {writes['n']:3d} | missing {len(missing)} {missing}"
)
if warm is not None:
    print(
        f"          | prewarm {warm} in {warm_seconds:.1f}s "
        f"(cache {cache_dir}, download total {fetch_seconds:.1f}s)"
    )
if missing:
    _frame, report = extend.retry_missing_closes(
        frame, TICKERS, start=START, end=END
    )
    print(f"          | retry recovered {report['recovered']} of {report['missing']}, "
          f"still missing {report['still_missing']}")
