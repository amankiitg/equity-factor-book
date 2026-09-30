"""Measure the yfinance timezone-cache race, and what the prewarm and retry do to it.

One fresh process, the run's own ticker list, the real vendor:

    .venv/bin/python scripts/probe_cache_race.py baseline     # no prewarm
    .venv/bin/python scripts/probe_cache_race.py prewarm      # prewarm, then fetch
    .venv/bin/python scripts/probe_cache_race.py delayed-bar  # the retry's recovery

`baseline` is the run as it was: yfinance writes one timezone row per ticker from
inside the threaded download, and when two threads write together SQLite refuses
with `OperationalError('database is locked')` for whichever symbol lost, which
yfinance reports as a failed download. The frame still carries that symbol's rows
and no prices, so nothing downstream raises: the name is simply gone. In both modes
the script reports how many timezone rows the download wrote, which names came back
without a close on the session being priced, and what the single-threaded retry
recovered.

`delayed-bar` is the shape that failed on 2026-09-29 with every fix in place: the
vendor answers for the earlier sessions of the window and has no bar for the close
being priced. The gap is injected into a real fetch, because tonight's bytes cannot
be asked for again, and what it measures is the retry on the real vendor once it
fires: the single-threaded pass is a real request for CSGP over the real window.

Measured 2026-09-29 on the 504-name live fetch, this Mac, yfinance 1.7.0:

  baseline  6 runs: 2 lost exactly one symbol (XYL, MS), 504 timezone rows written
            by the download, retry recovered 1 of 1 both times (a lost request)
  prewarm   3 runs: 0 lost, 0 rows written by the download, prewarm 41 to 48s for
            504 rows (the fetch itself is about 10s)
  delayed   the window check calls CSGP covered while the session check calls it
            missing, on an un-injected fetch: the vendor served 1 close of 504 on
            2026-09-29. The retry then fired and recovered nothing, because no bar
            exists for that session, so the name goes to the book's drop rule. With
            the bar present (2026-09-28, the gap injected) the same retry fired and
            recovered the real close, 27.02, the value the vendor had just served.

So the retry recovers a name the fetch lost and cannot recover a bar the vendor does
not have, and either way the name is dropped only after a retry that happened.

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
# the last session of the requested window: the one the run prices and the only one
# a name has to have a close on (see `efb.prices.missing_tickers`)
SESSION = "2026-09-29"

mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
writes = {"n": 0}
original_store = yf_cache._TzCache.store


def counted_store(self, *args, **kwargs):  # noqa: ANN001
    writes["n"] += 1
    return original_store(self, *args, **kwargs)


yf_cache._TzCache.store = counted_store

if mode == "delayed-bar":
    # the shape that failed on 2026-09-29: CSGP answered for the earlier sessions of
    # the window and had no bar for the close being priced. Two readings of it, both
    # against the real vendor, because they have different answers:
    #
    #   the bar exists and the fetch did not get it  -> the retry recovers it
    #   the vendor has no bar for that session at all -> the retry fires and cannot,
    #                                                    and the drop rule is the answer
    #
    # 09-29 is the second case on the evening of 2026-09-29: the vendor served 1 close
    # of 504 on that session later that night, so the bar it had earlier was gone.
    frame = prices.download_prices(TICKERS, start=START, end=END, prewarm=True)
    served = frame.groupby(level="date")["close"].apply(lambda s: int(s.notna().sum()))
    served_counts = {str(day.date()): int(count) for day, count in served.items()}
    print("closes the vendor served per session:", served_counts)
    complete = [day for day, count in served.items() if count > len(TICKERS) / 2]
    short = [day for day, count in served.items() if count <= len(TICKERS) / 2]

    for day in sorted(short, reverse=True):
        print(f"--- {day.date()}: the vendor served {int(served[day])} of {len(TICKERS)} closes")
        print(f"    the window-wide check calls CSGP covered: {'CSGP' in prices.covered_tickers(frame)}")
        want = prices.missing_tickers(frame, ["CSGP"], session=day)
        print(f"    the session check calls CSGP missing: {want}")
        if want:
            _frame, report = extend.retry_missing_closes(
                frame, ["CSGP"], start=START, end=END, session=str(day.date())
            )
            print(f"    the retry fired for {report['missing']} and recovered {report['recovered']}")
            print(f"    still missing {report['still_missing']}: the name goes to the drop rule")

    if not complete:
        raise SystemExit("the vendor served no session in this window")
    session = max(complete)
    if pd.isna(frame.xs(session, level="date").loc["CSGP", "close"]):
        raise SystemExit(f"CSGP is already missing from the real fetch on {session.date()}")
    print(f"--- {session.date()}: the newest session with a served bar, {int(served[session])} of {len(TICKERS)} closes")
    before = frame.xs(session, level="date").loc["CSGP", "close"]
    frame.loc[(session, "CSGP"), ["close", "adj_close"]] = float("nan")
    print(f"    injected: CSGP priced before {session.date()} and no bar on it now")
    print(f"    the window-wide check calls CSGP covered: {'CSGP' in prices.covered_tickers(frame)}")
    want = prices.missing_tickers(frame, ["CSGP"], session=session)
    print(f"    the session check calls CSGP missing: {want}")
    frame, report = extend.retry_missing_closes(
        frame, TICKERS, start=START, end=END, session=str(session.date())
    )
    recovered = frame.xs(session, level="date").loc["CSGP", "close"]
    print(f"    the retry fired for {report['missing']} single-threaded and recovered {report['recovered']}")
    print(f"    CSGP's close on {session.date()} is {recovered}, was {before} before the gap was made")
    raise SystemExit(0)

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
missing = prices.missing_tickers(frame, TICKERS, session=SESSION)

print(
    f"{mode:9s} | tickers {len(TICKERS)} | timezone rows written during the "
    f"download: {writes['n']:3d} | missing on {SESSION}: {len(missing)} {missing}"
)
if warm is not None:
    print(
        f"          | prewarm {warm} in {warm_seconds:.1f}s "
        f"(cache {cache_dir}, download total {fetch_seconds:.1f}s)"
    )
if missing:
    _frame, report = extend.retry_missing_closes(
        frame, TICKERS, start=START, end=END, session=SESSION
    )
    print(f"          | retry recovered {report['recovered']} of {report['missing']}, "
          f"still missing {report['still_missing']}")
