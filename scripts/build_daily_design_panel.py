"""Build a daily XS-v1 descriptor panel with the live code path, in a data copy.

The study tree's `models/XS-v1/descriptors.parquet` publishes on month ends only -
190 rows for 2011-2026, 29 of them inside the 2024-2026 study window - so a study
that measures exposure between two refreshes has almost no days to measure on. The
live tree is different: `efb.race.next_descriptor_design` builds the next session's
row from data through tonight's close, every evening.

This script runs that same build once per session and writes the result beside the
frozen panel as `descriptors_daily.parquet`, in the frozen panel's own long format
(`date, ticker, descriptor, value_z_orth`). Nothing outside `--root` is written.

    python scripts/build_daily_design_panel.py --root /tmp/churn/daily

Three readings per session, exactly the three `next_descriptor_design` takes:

- `published` - the frozen panel already carries the row for this session, so it is
  used as it stands. This is what a live run does at the previous close, and it is
  also the check: on those sessions the rebuilt panel must reproduce the frozen row.
- `built` - the live shape. The row is built from data through the previous close
  with the cross-section taken as the names priced at that close.
- `stale` - fewer than `NEXT_DESIGN_WINDOW` sessions behind the close, so the last
  published row is used, which is the fallback the live code takes.

Only the *previous* close is read for a session's row: the row dated `d` is the
design the book carries on `d`, and it is knowable at the close of `d-1`. Nothing in
the window leans on a session's own price.
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
import time
from typing import Any

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from efb import probes, race  # noqa: E402
from efb.models import fundamental as fx  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("daily_design_panel")

STYLES = [name for name in fx.STYLE_NAMES if name != "market"]


def _published(descriptors: pd.DataFrame, stamp: pd.Timestamp) -> pd.DataFrame:
    day = descriptors.loc[pd.to_datetime(descriptors["date"]) == stamp]
    return day.pivot_table(index="ticker", columns="descriptor", values="value_z_orth")


def _built(
    stamp: pd.Timestamp,
    window: pd.DatetimeIndex,
    returns: pd.DataFrame,
    close: pd.DataFrame,
    volume: pd.DataFrame,
    shares: pd.DataFrame,
    mapped: list[str],
) -> pd.DataFrame:
    """The live branch of `race.next_descriptor_design`, one row, verbatim."""
    row_date = stamp + pd.Timedelta(days=1)
    priced = returns.loc[stamp].notna()
    blank = pd.DataFrame(np.nan, index=[row_date], columns=returns.columns, dtype=float)
    described = blank.copy()
    described.loc[row_date, priced[priced].index] = 0.0

    r = pd.concat([returns.loc[window], described])
    c = pd.concat([close[mapped].loc[window], blank])
    v = pd.concat([volume[mapped].loc[window], blank])
    sh = pd.concat([shares[mapped].loc[window], blank])
    cap = fx.market_cap(c, sh)
    raw = fx.raw_descriptors(r, c, v, cap, fx.market_proxy(r, cap))
    standard: dict[str, pd.DataFrame] = {"market": raw["market"]}
    for name in fx.STYLE_NAMES:
        if name == "market":
            continue
        frame_z, _table, _clipped = fx.standardize(raw[name], r.notna(), cap.shift(1))
        frame_z.columns = r.columns
        standard[name] = frame_z
    orthogonal = fx.orthogonalize(standard, fx.DEFAULT_ORTHOGONALIZATION)
    return pd.DataFrame({name: orthogonal[name].loc[row_date] for name in STYLES})


def build(
    root: pathlib.Path, start: str, end: str, out: pathlib.Path, limit: int = 0
) -> int:
    panel = probes.load_panel(root)
    frame = race.design_panel(panel)
    close = panel["close"]
    volume = panel["volume"]
    shares = panel["shares"]
    mapped = panel["mapped"]
    assert isinstance(frame, pd.DataFrame)
    assert isinstance(close, pd.DataFrame)
    assert isinstance(volume, pd.DataFrame)
    assert isinstance(shares, pd.DataFrame)
    assert isinstance(mapped, list)
    returns = frame[mapped]

    descriptors = pd.read_parquet(root / "models" / "XS-v1" / "descriptors.parquet")
    published = pd.DatetimeIndex(sorted(pd.to_datetime(descriptors["date"]).unique()))
    sessions = pd.DatetimeIndex(sorted(returns.index))
    wanted = sessions[
        (sessions >= pd.Timestamp(start)) & (sessions <= pd.Timestamp(end))
    ]
    if limit:
        wanted = wanted[:limit]
    logger.info("%d sessions to describe (%s..%s)", len(wanted), start, end)

    records: list[dict[str, Any]] = []
    labels: dict[str, str] = {}
    began = time.time()
    for done, day in enumerate(wanted, start=1):
        position = sessions.get_indexer([day])[0]
        if position == 0:
            logger.warning("%s has no session behind it: skipped", day.date())
            continue
        stamp = sessions[position - 1]
        if day in published:
            z = _published(descriptors, day)
            labels[str(day.date())] = f"published {day.date()}"
        else:
            window = sessions[(sessions <= stamp)][-race.NEXT_DESIGN_WINDOW :]
            if len(window) < race.NEXT_DESIGN_WINDOW:
                stale = race._as_of(descriptors, stamp)  # noqa: SLF001
                assert stale is not None
                z = _published(descriptors, stale)
                labels[str(day.date())] = f"stale {stale.date()}"
            else:
                z = _built(stamp, window, returns, close, volume, shares, mapped)
                labels[str(day.date())] = f"built through {stamp.date()}"
        for ticker in z.index:
            for descriptor in STYLES:
                value = z.at[ticker, descriptor]
                if pd.notna(value):
                    records.append(
                        {
                            "date": day,
                            "ticker": str(ticker),
                            "descriptor": descriptor,
                            "value_z_orth": float(value),
                        }
                    )
        if done % 50 == 0 or done == len(wanted):
            logger.info(
                "%d/%d rows, %.1fs elapsed, %.2fs per session",
                done,
                len(wanted),
                time.time() - began,
                (time.time() - began) / done,
            )

    long = pd.DataFrame.from_records(records)
    out.parent.mkdir(parents=True, exist_ok=True)
    long.to_parquet(out, index=False)
    (out.with_suffix(".labels.json")).write_text(
        json.dumps(labels, indent=2, sort_keys=True) + "\n"
    )
    logger.info("wrote %s (%d cells)", out, len(long))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="build the daily design panel")
    parser.add_argument("--root", required=True)
    parser.add_argument("--start", default="2024-06-03")
    parser.add_argument("--end", default="2026-10-02")
    parser.add_argument(
        "--out",
        default="",
        help="default: <root>/models/XS-v1/descriptors_daily.parquet",
    )
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    out = (
        pathlib.Path(args.out)
        if args.out
        else root / "models" / "XS-v1" / "descriptors_daily.parquet"
    )
    return build(root, args.start, args.end, out, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
