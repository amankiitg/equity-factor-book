"""Sprint E12: attribute the stored days, and store the rows.

The evening run calls this after the day's reconciliation is stored. It reads the
loop's own `positions` table and the run tree's XS-v1 artifacts, attributes every
session that has no row in `efb.attribution` yet, and writes those rows.

Two properties matter more than the arithmetic, which lives in
`efb.attribution`:

- **Every day, not just tonight.** The attribution is a pure function of stored
  positions and stored model artifacts, so a day the loop never attributed, or a
  day an earlier version attributed with a bug, is filled in by the next run. That
  is why the work list is "the sessions with a book and no row" rather than
  "tonight".
- **A report, never a step.** A failure here is logged and never stops the
  trading run. Attribution is a description of what the book did; a description
  that cannot be produced is a bad page, not a reason to leave a book unheld.

The day's own cost and forecast are read from the store as well, so the row
carries realized against expected cost and forecast against realized volatility
without a second source for either.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from efb import attribution
from live import store

# The columns of the store's `positions` table this reads. Named so a change to
# the table is a failure here rather than a silently narrower book.
POSITION_COLUMNS = ("trade_date", "ticker", "weight")


def attributed_days() -> set[str]:
    """The sessions `efb.attribution` already holds, as ISO date strings."""
    frame = store.select("attribution")
    if frame.empty or "trade_date" not in frame.columns:
        return set()
    return {str(value)[:10] for value in frame["trade_date"].astype(str)}


def books(positions: pd.DataFrame) -> pd.DataFrame:
    """The store's position rows in the three columns `daily_weights` reads."""
    missing = [name for name in POSITION_COLUMNS if name not in positions.columns]
    if missing:
        raise ValueError(
            f"the stored positions have no {', '.join(missing)} column, so the "
            "books cannot be rebuilt from them"
        )
    return positions.loc[:, list(POSITION_COLUMNS)]


def _number(value: Any) -> float | None:
    """A stored number, or None when the store has no usable value."""
    if value is None or pd.isna(value):
        return None
    return float(value)


def nav_equity(nav: pd.DataFrame | None) -> dict[str, float]:
    """The store's own equity per day, keyed by ISO date, for a cost's denominator."""
    if nav is None or getattr(nav, "empty", True) or "trade_date" not in nav.columns:
        return {}
    out: dict[str, float] = {}
    for row in nav.to_dict("records"):
        value = _number(row.get("nav"))
        if value is not None:
            out[str(row["trade_date"])[:10]] = float(value)
    return out


def session_inputs(
    reconciliation: pd.DataFrame,
    orders: pd.DataFrame,
    *,
    fills: pd.DataFrame | None = None,
    nav: pd.DataFrame | None = None,
) -> tuple[dict[pd.Timestamp, dict[str, Any]], dict[pd.Timestamp, dict[str, Any]]]:
    """The per-session cost and forecast, from the store's own rows.

    The cost is the **realized** one, computed from the day's own fills by
    `live.fills.realized_cost_bps` - the same function the morning report uses, so
    the page's cost and the email's cannot disagree - and the day's expected cost is
    the fallback for a session whose fills are not in yet, which is every evening
    before its own morning. Both numbers travel on the row, in basis points of NAV,
    negated into the P&L units the attribution works in: the book is gross 1.0 of
    NAV, so a basis point of NAV is a basis point of gross.

    The fill counts come from `efb.fills`, which is where a fill is recorded: the
    `orders` table carries the legs the evening *sent* and their submission state
    (`ACCEPTED`), so counting `FILLED` there counted nothing and reported every
    traded day as having filled no leg.

    The expected cost travels split as well as total: `expected_trading_bps` is the
    half a fill price can be measured against (spread + impact + commission) and
    `expected_borrow_bps` is the short leg's holding cost, which no fill pays. The
    two are the reconciliation row's own four parts, summed here so the parts and
    the total cannot disagree.
    """
    costs: dict[pd.Timestamp, dict[str, Any]] = {}
    forecasts: dict[pd.Timestamp, dict[str, Any]] = {}
    realized_from_fills: dict[str, float] = {}
    filled_by_day: dict[str, int] = {}
    if (
        fills is not None
        and not getattr(fills, "empty", True)
        and "trade_date" in fills.columns
    ):
        from live import fills as fills_module

        equity = nav_equity(nav)
        days = fills["trade_date"].astype(str).str.slice(0, 10)
        for day, rows in fills.groupby(days):
            bps = fills_module.realized_cost_bps(rows, equity.get(str(day)))
            if bps is not None:
                realized_from_fills[str(day)] = float(bps)
            filled = rows["status"].astype(str) == "FILLED"
            filled_by_day[str(day)] = int(filled.sum())
    if not reconciliation.empty and "trade_date" in reconciliation.columns:
        for row in reconciliation.to_dict("records"):
            day = pd.Timestamp(str(row["trade_date"])[:10])
            expected = _number(row.get("expected_cost_bps"))
            stored = _number(row.get("realized_cost_bps"))
            realized = (
                stored if stored is not None else realized_from_fills.get(str(day)[:10])
            )
            chosen = realized if realized is not None else expected
            if chosen is not None:
                costs[day] = {"cost_usd": -chosen / 1e4}
            parts = {
                name: _number(row.get(column))
                for name, column in (
                    ("spread", "expected_spread_bps"),
                    ("impact", "expected_impact_bps"),
                    ("commission", "expected_commission_bps"),
                    ("borrow", "expected_borrow_bps"),
                )
            }
            known_trading = [
                value
                for name in ("spread", "impact", "commission")
                if (value := parts[name]) is not None
            ]
            forecasts[day] = {
                "forecast_vol": _number(row.get("forecast_annual_vol")),
                "expected_cost_bps": expected,
                "expected_trading_bps": (
                    float(sum(known_trading)) if known_trading else None
                ),
                "expected_borrow_bps": parts["borrow"],
                "realized_cost_bps": realized,
            }
    if not orders.empty and "trade_date" in orders.columns:
        stamp_column = orders["trade_date"].astype(str).str.slice(0, 10)
        for day, group in orders.groupby(stamp_column):
            stamp = pd.Timestamp(str(day)[:10])
            intended = pd.to_numeric(group["intended_notional"], errors="coerce")
            filled = pd.to_numeric(group["filled_notional"], errors="coerce")
            status = group["status"].astype(str)
            gap = _number((intended - filled).abs().max())
            known = filled_by_day.get(str(day)[:10])
            forecasts.setdefault(stamp, {}).update(
                {
                    "n_target": int(len(group)),
                    "n_filled": (
                        known if known is not None else int((status == "FILLED").sum())
                    ),
                    "max_fill_gap": gap if gap is not None else 0.0,
                }
            )
    return costs, forecasts


def run(root: Path, *, panel: attribution.ModelPanel | None = None) -> dict[str, Any]:
    """Attribute every stored day without a row, store the rows, and report.

    Returns what it did rather than only doing it: the evening run logs the counts,
    so an evening that attributed nothing because the store was empty reads
    differently from one that attributed nothing because every day was already
    done.
    """
    positions = store.select("positions")
    if positions.empty:
        return {
            "n_stored": 0,
            "n_done": 0,
            "sessions": [],
            "detail": "no positions are stored",
        }
    done = attributed_days()
    panel = panel if panel is not None else attribution.ModelPanel(root)
    costs, forecasts = session_inputs(
        store.select("reconciliation"),
        store.select("orders"),
        fills=store.select("fills"),
        nav=store.select("nav"),
    )
    frame = attribution.from_positions(
        books(positions),
        panel,
        done=done,
        costs=costs,
        forecasts=forecasts,
        risk_split=True,
        # The same rows again, for the `alpha` and specific volatility the sizing
        # used: they are what the pre-hedge book is rebuilt from, so the row can
        # say what the hedge removed rather than only what it left.
        sizing=positions,
    )
    if frame.empty:
        return {
            "n_stored": 0,
            "n_done": len(done),
            "sessions": [],
            "detail": "every stored day already has an attribution row",
        }
    rows = attribution.store_rows(frame)
    store.upsert("attribution", rows)
    return {
        "n_stored": len(rows),
        "n_done": len(done),
        "sessions": [str(row["trade_date"]) for row in rows],
        "detail": "",
    }
