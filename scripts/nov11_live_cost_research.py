"""What the live loop's own book costs under the live cost model, session by session.

Read-only. The live book series comes from `efb.positions` (one row per close per
name, the weights the loop published), and the cost function is the one in
`scripts/nov11_turnover_research.py`, so the live loop and the monthly backtest are
priced by the same arithmetic and can be read side by side.

    .venv/bin/python scripts/nov11_live_cost_research.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import nov11_turnover_research as research  # noqa: E402


def main() -> None:
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    from live import store

    positions = store.select("positions")
    positions["trade_date"] = pd.to_datetime(positions["trade_date"])
    book = (
        positions.pivot_table(index="trade_date", columns="ticker", values="weight")
        .sort_index()
        .fillna(0.0)
    )
    proposals = store.select("proposals")[["trade_date", "nav"]].dropna()
    proposals["trade_date"] = pd.to_datetime(proposals["trade_date"])
    nav_map = dict(zip(proposals["trade_date"], proposals["nav"], strict=False))
    nav = float(np.nanmedian([float(value) for value in nav_map.values()])) if nav_map else 1_000_000.0
    print(f"live book: {len(book)} closes {book.index[0].date()} -> {book.index[-1].date()}, "
          f"{book.shape[1]} tickers, NAV ${nav:,.0f}")

    spread, adv = research.cost_inputs()
    previous = book.shift(1).dropna(how="all")
    held = research.cost_per_rebalance(
        book, previous, spread, adv, nav, charge_spread_on_trade=False
    )
    traded = research.cost_per_rebalance(
        book, previous, spread, adv, nav, charge_spread_on_trade=True
    )
    engine = research.research_cost_per_rebalance(book, previous, spread, adv, nav)

    print("\n## the live book, three cost conventions, per session (bp of NAV)\n")
    table = pd.DataFrame(
        {
            "turnover_of_gross": held["turnover"],
            "traded_notional": held["turnover"] * nav,
            "engine_total": engine["total_bps"],
            "live_trade_total": traded["total_bps"],
            "live_trade_trading": traded["trading_bps"],
            "live_trade_borrow": traded["borrow_bps"],
            "live_held_trading": held["trading_bps"],
        }
    )
    print(table.to_string(float_format=lambda value: f"{value:,.3f}"))

    per_year = research.TRADING_DAYS / research.HORIZON
    print("\n## annualized the way every other trading number in the project is\n")
    for label, frame in (("research engine (no borrow)", engine), ("live, spread on the trade", traded),
                         ("live as written (spread on the held book)", held)):
        annual = float(frame["total_bps"].mean()) * per_year
        trading = float(frame["trading_bps"].mean()) * per_year
        borrow = float(frame["borrow_bps"].mean()) * per_year
        print(f"  {label:44s} total {annual:7.0f} bp/yr   trading {trading:7.0f}   borrow {borrow:7.0f}")
    print(f"  turnover {float(held['turnover'].mean()) * per_year * 100:,.0f}% of gross per year "
          f"({float(held['turnover'].mean()) * 100:.1f}% per session)")

    out = ROOT / "docs" / "research" / "nov11_live_cost_numbers.json"
    out.write_text(table.to_json(orient="index", indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
