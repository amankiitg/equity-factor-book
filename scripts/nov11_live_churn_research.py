"""The live loop's own turnover and the floor's round-trip churn, from the store.

Read-only (`SELECT` only). Item 12 asks for the churn at the floor since launch:
names that leave and return, the dollars traded twice, and what the two legs cost
against the name's own weight. Item 3a asks what the live loop's own turnover is,
which is the number the monthly backtest has to be compared against.

    .venv/bin/python scripts/nov11_live_churn_research.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def env() -> None:
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    env()
    from live import store

    positions = store.select("positions")
    positions["trade_date"] = pd.to_datetime(positions["trade_date"])
    book = positions.pivot_table(index="trade_date", columns="ticker", values="weight").fillna(0.0)
    book = book.sort_index()
    closes = list(book.index)
    print(f"live closes in efb.positions: {len(closes)}  {closes[0].date()} -> {closes[-1].date()}")

    nav = store.select("proposals")[["trade_date", "nav"]].dropna()
    nav["trade_date"] = pd.to_datetime(nav["trade_date"])
    nav_map = dict(zip(nav["trade_date"], nav["nav"], strict=False))

    rows = []
    for index in range(1, len(closes)):
        today, prior = closes[index], closes[index - 1]
        current = book.loc[today]
        previous = book.loc[prior]
        delta = current - previous
        traded = float(delta.abs().sum())
        rows.append(
            {
                "close": today.date().isoformat(),
                "turnover_of_gross": traded,
                "traded_notional": traded * float(nav_map.get(today, np.nan) or np.nan),
                "left": int(((previous.abs() > 0) & (current.abs() == 0)).sum()),
                "arrived": int(((previous.abs() == 0) & (current.abs() > 0)).sum()),
                "held": int((current.abs() > 0).sum()),
            }
        )
    frame = pd.DataFrame(rows)
    print("\n## the live book's own turnover, close by close\n")
    print(frame.to_string(index=False, float_format=lambda value: f"{value:,.4f}"))
    print(
        f"\nmean turnover of gross: {frame['turnover_of_gross'].mean():.1%} per session; "
        f"median {frame['turnover_of_gross'].median():.1%}; "
        f"mean names left {frame['left'].mean():.1f}, arrived {frame['arrived'].mean():.1f}"
    )

    # Item 12: a name that leaves and comes back within k sessions, and its two legs.
    present = (book.abs() > 0)
    trips: list[dict[str, object]] = []
    for ticker in present.columns:
        series = present[ticker].to_numpy()
        stamps = list(book.index)
        exits = [i for i in range(1, len(series)) if series[i - 1] and not series[i]]
        for exit_index in exits:
            for back in range(exit_index + 1, min(exit_index + 22, len(series))):
                if series[back]:
                    weight_out = abs(float(book.loc[stamps[exit_index - 1], ticker]))
                    weight_in = abs(float(book.loc[stamps[back], ticker]))
                    trips.append(
                        {
                            "ticker": ticker,
                            "left": stamps[exit_index].date().isoformat(),
                            "returned": stamps[back].date().isoformat(),
                            "sessions_away": back - exit_index,
                            "weight_out": weight_out,
                            "weight_in": weight_in,
                            "dollars_both_ways": (weight_out + weight_in)
                            * float(nav_map.get(stamps[back], np.nan) or np.nan),
                        }
                    )
                    break
    rounds = pd.DataFrame(trips)
    if rounds.empty:
        print("\nno round trips inside 21 sessions in the stored closes")
    else:
        print("\n## round trips: a name that left and came back within 21 sessions\n")
        print(rounds.to_string(index=False, float_format=lambda value: f"{value:,.4f}"))
        print(
            f"\n{len(rounds)} round trip(s) over {len(closes)} closes; "
            f"mean {rounds['sessions_away'].mean():.1f} sessions away; "
            f"mean dollars both ways ${rounds['dollars_both_ways'].mean():,.0f}"
        )

    out = ROOT / "docs" / "research" / "nov11_live_churn_numbers.json"
    out.write_text(
        json.dumps(
            {
                "closes": [str(stamp.date()) for stamp in closes],
                "turnover": rows,
                "round_trips": trips,
            },
            indent=1,
            default=float,
        )
    )
    print(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
