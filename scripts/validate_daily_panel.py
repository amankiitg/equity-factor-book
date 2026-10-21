"""Validate the daily design panel before any study is run on it.

Two checks, both of which have to pass before `daily_design_study.py` is worth
running:

(a) **Against the frozen panel.** On every session the frozen tree publishes, the
    live branch of `race.next_descriptor_design` - the row built at the previous
    close - must reproduce the row the model published for that session. This is
    the only check that the copied build is the model's build, because the panel
    itself uses the published row unchanged on those dates and would match itself
    otherwise.
    Expected: exact to rounding, except on the session after a market holiday,
    where the priced set moves between the two closes (the documented limitation).

(b) **Against the live store.** For the sessions the live tree has actually
    published, `efb.e11_descriptors` holds the row the evening wrote. Comparing the
    rebuilt panel with it says whether the build agrees with the live pipeline
    rather than with this machine's idea of it. Read-only SELECT.

    python scripts/validate_daily_panel.py --root /tmp/churn/daily
    python scripts/validate_daily_panel.py --root /tmp/churn/daily --no-store
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
from typing import Any

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import build_daily_design_panel as builder  # type: ignore[import-not-found]  # noqa: E402

from efb import probes, race  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("validate_daily_panel")


def _frames(root: pathlib.Path) -> dict[str, Any]:
    panel = probes.load_panel(root)
    frame = race.design_panel(panel)
    assert isinstance(frame, pd.DataFrame)
    mapped = panel["mapped"]
    assert isinstance(mapped, list)
    close = panel["close"]
    volume = panel["volume"]
    shares = panel["shares"]
    assert isinstance(close, pd.DataFrame)
    assert isinstance(volume, pd.DataFrame)
    assert isinstance(shares, pd.DataFrame)
    return {
        "returns": frame[mapped],
        "close": close,
        "volume": volume,
        "shares": shares,
        "mapped": mapped,
    }


def check_frozen(
    root: pathlib.Path,
    dates: list[str] | None = None,
    start: str = "2024-06-03",
    end: str = "2026-10-02",
) -> dict[str, Any]:
    frames = _frames(root)
    returns = frames["returns"]
    descriptors = pd.read_parquet(root / "models" / "XS-v1" / "descriptors.parquet")
    published = pd.DatetimeIndex(sorted(pd.to_datetime(descriptors["date"]).unique()))
    sessions = pd.DatetimeIndex(sorted(returns.index))
    if dates:
        wanted = [pd.Timestamp(value) for value in dates]
    else:
        wanted = [
            d
            for d in published
            if d in set(sessions) and pd.Timestamp(start) <= d <= pd.Timestamp(end)
        ]

    per_descriptor: dict[str, list[float]] = {name: [] for name in builder.STYLES}
    per_day: list[dict[str, Any]] = []
    for day in wanted:
        position = sessions.get_indexer([day])[0]
        if position < race.NEXT_DESIGN_WINDOW:
            continue
        stamp = sessions[position - 1]
        window = sessions[(sessions <= stamp)][-race.NEXT_DESIGN_WINDOW :]
        built = builder._built(
            stamp,
            window,
            returns,
            frames["close"],
            frames["volume"],
            frames["shares"],
            frames["mapped"],
        )
        frozen = builder._published(descriptors, day)
        common = built.index.intersection(frozen.index)
        row: dict[str, Any] = {
            "date": str(day.date()),
            "stamp": str(stamp.date()),
            "names_built": int(len(built)),
            "names_frozen": int(len(frozen)),
            "names_common": int(len(common)),
            "max_abs": {},
            "holiday_after": bool((day - stamp).days > 1),
        }
        for name in builder.STYLES:
            left = pd.to_numeric(built.loc[common, name], errors="coerce")
            right = pd.to_numeric(frozen.loc[common, name], errors="coerce")
            difference = (left - right).abs()
            worst = (
                float(difference.max()) if difference.notna().any() else float("nan")
            )
            row["max_abs"][name] = worst
            per_descriptor[name].append(worst)
        row["worst"] = float(np.nanmax([v for v in row["max_abs"].values()]))
        per_day.append(row)
        logger.info(
            "%s vs frozen: names %d/%d worst %.3e%s",
            day.date(),
            len(common),
            len(frozen),
            row["worst"],
            " (session after a gap in the calendar)" if row["holiday_after"] else "",
        )

    summary = {
        "check": "built row vs the frozen published row, on every published session",
        "days": len(per_day),
        "max_abs_by_descriptor": {
            name: (float(np.nanmax(values)) if values else float("nan"))
            for name, values in per_descriptor.items()
        },
        "median_abs_by_descriptor": {
            name: (float(np.nanmedian(values)) if values else float("nan"))
            for name, values in per_descriptor.items()
        },
        "worst_day": max(per_day, key=lambda row: row["worst"]) if per_day else None,
        "days_over_1e-06": [row["date"] for row in per_day if row["worst"] > 1e-06],
        "detail": per_day,
    }
    return summary


def check_store(root: pathlib.Path, start: str, end: str) -> dict[str, Any]:
    from live import store

    panel_path = root / "models" / "XS-v1" / "descriptors_daily.parquet"
    if not panel_path.exists():
        return {"check": "vs efb.e11_descriptors", "status": "panel not built yet"}
    daily = pd.read_parquet(panel_path)
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.loc[
        (daily["date"] >= pd.Timestamp(start)) & (daily["date"] <= pd.Timestamp(end))
    ]
    connection = store.get_connection()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT trade_date, ticker, descriptor, value_z_orth "
            'FROM "efb"."e11_descriptors" '
            "WHERE trade_date >= %s AND trade_date <= %s",
            (start, end),
        )
        fetched = cursor.fetchall()
    if not fetched:
        return {"check": "vs efb.e11_descriptors", "status": "no rows in the store"}
    stored = pd.DataFrame(
        fetched, columns=["date", "ticker", "descriptor", "value_z_orth"]
    )
    stored["date"] = pd.to_datetime(stored["date"])
    stored["ticker"] = stored["ticker"].astype(str)
    stored["descriptor"] = stored["descriptor"].astype(str)
    stored = stored.rename(columns={"value_z_orth": "value_store"})
    value = "value_store"
    daily["ticker"] = daily["ticker"].astype(str)
    daily["descriptor"] = daily["descriptor"].astype(str)
    merged = daily.merge(
        stored[["date", "ticker", "descriptor", value]],
        on=["date", "ticker", "descriptor"],
        how="inner",
    )
    difference = (merged["value_z_orth"] - merged["value_store"]).abs()
    by_descriptor = difference.groupby(merged["descriptor"]).agg(
        ["max", "median", "count"]
    )
    only_panel = len(daily) - len(merged)
    return {
        "check": "rebuilt daily panel vs efb.e11_descriptors",
        "window": [start, end],
        "cells_panel": int(len(daily)),
        "cells_matched": int(len(merged)),
        "cells_panel_only": int(only_panel),
        "dates_panel": int(daily["date"].nunique()),
        "dates_store": int(stored["date"].nunique()),
        "max_abs": float(difference.max()) if len(merged) else float("nan"),
        "median_abs": float(difference.median()) if len(merged) else float("nan"),
        "by_descriptor": {
            str(name): {
                "max": float(row["max"]),
                "median": float(row["median"]),
                "cells": int(row["count"]),
            }
            for name, row in by_descriptor.iterrows()
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="validate the daily design panel")
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", default="docs/research/daily_design_validation.json")
    parser.add_argument(
        "--frozen-start", default="2024-06-03", help="first month-end to rebuild"
    )
    parser.add_argument("--frozen-end", default="2026-10-02")
    parser.add_argument(
        "--start", default="2026-09-04", help="first session to compare with the store"
    )
    parser.add_argument("--end", default="2026-10-02")
    parser.add_argument("--no-store", action="store_true")
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()

    frozen = check_frozen(root, start=args.frozen_start, end=args.frozen_end)
    payload: dict[str, Any] = {"frozen": frozen}
    if not args.no_store:
        try:
            payload["store"] = check_store(root, args.start, args.end)
        except Exception as exc:  # noqa: BLE001 - report rather than lose check (a)
            payload["store"] = {"check": "vs efb.e11_descriptors", "error": str(exc)}
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    logger.info("wrote %s", out)
    print(json.dumps({k: v for k, v in payload.items() if k != "frozen"}, indent=2))
    print("frozen: days", frozen["days"], "max by descriptor:")
    print(json.dumps(frozen["max_abs_by_descriptor"], indent=2))
    print("days over 1e-06:", frozen["days_over_1e-06"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
