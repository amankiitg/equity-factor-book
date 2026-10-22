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

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from efb import attribution
from live import store

logger = logging.getLogger(__name__)

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
    # The fill count is the fills' own. The loop above reads it per day that has an
    # orders row; a close whose fills are in the store but whose orders are not - the
    # morning re-finalizing a row the evening wrote before its orders settled - would
    # otherwise keep `n_filled` empty, and a row that cannot say how many legs filled
    # cannot be told from one that has not been priced.
    for day, count in filled_by_day.items():
        stamp = pd.Timestamp(day)
        forecasts.setdefault(stamp, {}).setdefault("n_filled", int(count))
    return costs, forecasts


def _frames(
    root: Path, panel: attribution.ModelPanel | None, done: set[str]
) -> tuple[pd.DataFrame, int]:
    """The attributed rows for every stored day not in `done`, and how many were."""
    positions = store.select("positions")
    if positions.empty:
        return pd.DataFrame(), 0
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
    return frame, len(done)


def _stored_row(day: str) -> dict[str, Any] | None:
    """The row `efb.attribution` holds for one close, or None."""
    frame = store.select("attribution")
    if frame is None or frame.empty or "trade_date" not in frame.columns:
        return None
    days = frame["trade_date"].astype(str).str.slice(0, 10)
    rows = frame.loc[days == day]
    if rows.empty:
        return None
    return {str(key): value for key, value in rows.iloc[-1].to_dict().items()}


def _same_number(left: Any, right: Any, *, tolerance: float = 1e-12) -> bool:
    """Two stored numbers, equal to a tolerance that survives a jsonb round trip."""
    for value in (left, right):
        if value is None:
            return left is None and right is None
    try:
        first, second = float(left), float(right)
    except (TypeError, ValueError):
        return str(left) == str(right)
    if pd.isna(first) and pd.isna(second):
        return True
    return abs(first - second) <= tolerance * max(1.0, abs(first), abs(second))


# The columns this step exists to correct: the day's cost, its total, and the two
# realized figures derived from them. `pre_hedge_vol` is deliberately not among them
# - the recompute runs the current code, so it can only restate it, never change it.
REFINALIZED = (
    "pnl_cost",
    "pnl_total",
    "realized_vol",
    "vol_ratio",
    "realized_cost_bps",
)


def refinalize(
    day: Any,
    root: Path,
    *,
    panel: attribution.ModelPanel | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Re-attribute one close against the fills it has now, and rewrite its row.

    The evening attributes the close before its orders settle, so the row's cost is
    the day's *expected* cost and `n_filled` is zero - measured on the live store,
    eight rows from 2026-10-09 to 2026-10-20 (see
    `docs/owner_fixes/attribution_recompute.md`). The morning is the first run that
    knows what the fills cost, so this is where the row is corrected: the same
    computation the evening runs, with the fills now in the store.

    Idempotent by construction, in three ways: the row is rewritten only when the
    stored `n_filled` disagrees with the fills the store now holds (so a day whose
    fills are already counted is never touched), only when the recomputed cost
    columns differ, and the recompute is a pure function of the store. A close with
    no fills recorded - a day the loop held, or one whose morning has not run - has
    `n_filled` matching on both sides and is left exactly as it is.

    A failure is reported and swallowed: this is a description of a day that has
    already traded, and never a reason to fail the morning that produced the fills.
    """
    stamp = str(day)[:10]
    stored = _stored_row(stamp)
    if stored is None:
        return {
            "day": stamp,
            "changed": False,
            "reason": "no stored row for this close",
        }
    fills_frame = store.select("fills")
    filled = 0
    if (
        fills_frame is not None
        and not fills_frame.empty
        and "trade_date" in fills_frame.columns
    ):
        days = fills_frame["trade_date"].astype(str).str.slice(0, 10)
        rows = fills_frame.loc[days == stamp]
        if len(rows) and "status" in rows.columns:
            filled = int((rows["status"].astype(str) == "FILLED").sum())
    if filled == 0:
        # Nothing was filled, so there is nothing to price: a hold day, or a close
        # whose morning has not run. The row keeps the evening's estimate rather
        # than being rewritten with the same number under a new timestamp.
        return {
            "day": stamp,
            "changed": False,
            "reason": "no fills are recorded for this close",
            "n_filled": 0,
        }
    already = stored.get("n_filled")
    if already is not None and _same_number(already, filled, tolerance=0.0):
        return {
            "day": stamp,
            "changed": False,
            "reason": "the stored row already counts these fills",
            "n_filled": filled,
        }
    frame, _ = _frames(root, panel, attributed_days() - {stamp})
    if frame.empty:
        return {"day": stamp, "changed": False, "reason": "the close cannot be rebuilt"}
    rows = attribution.store_rows(frame)
    row = next((item for item in rows if str(item["trade_date"])[:10] == stamp), None)
    if row is None:
        return {
            "day": stamp,
            "changed": False,
            "reason": "the rebuild produced no row for this close",
        }
    moved = [
        column
        for column in REFINALIZED
        if not _same_number(stored.get(column), row.get(column))
    ]
    if not moved:
        return {
            "day": stamp,
            "changed": False,
            "reason": "the recomputed row is the stored one",
            "n_filled": filled,
        }
    row = dict(row)
    row["n_filled"] = float(filled)
    if not dry_run:
        store.upsert("attribution", [row])
    logger.info(
        "attribution %s re-finalized against %d fill(s): %s",
        stamp,
        filled,
        ", ".join(
            f"{column} {_shown(stored.get(column))} -> {_shown(row.get(column))}"
            for column in moved
        ),
    )
    return {
        "day": stamp,
        "changed": not dry_run,
        "dry_run": dry_run,
        "n_filled": filled,
        "moved": moved,
        "before": {column: stored.get(column) for column in moved},
        "after": {column: row.get(column) for column in moved},
    }


def _shown(value: Any) -> str:
    """A stored number, short enough to sit in a log line."""
    return "n/a" if value is None else f"{float(value):.6f}"


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
