"""Split each filled day's realized cost into the overnight move and the execution.

**Read-only.** `live.fills.realized_cost_bps` measures every fill against the close the
book was *sized* from: the evening weights a leg after one close and it fills at the
next open, so that number contains the market's overnight move as well as what the
execution did. On 2026-10-22 the live days averaged 10-24 bp of NAV against a research
model that predicts ~2.5 bp for a daily book, and the overnight gap is the first thing
that has to be taken out of the comparison.

The split uses the open of the fill's own session as the reference at submission - the
first price the order could have traded at - and reports three numbers per day:

    overnight   prior close -> open       the decision's own drift, not a cost
    execution   open -> fill              what the broker did with the order
    total       prior close -> fill       what `realized_cost_bps` reports

Each is in bp of the day's traded notional and in bp of NAV, and the model's predicted
trading cost is printed beside them. Legs with no open (a name the vendor did not
answer for that session) are counted and named rather than priced at zero.

    python scripts/cost_split.py --opens /tmp/opens.parquet            # print the table
    python scripts/cost_split.py --opens /tmp/opens.parquet --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from live import store  # noqa: E402


def _filled() -> pd.DataFrame:
    """The store's filled legs, in the columns this split needs."""
    frame = store.select("fills")
    if frame is None or frame.empty:
        return pd.DataFrame()
    frame = frame.copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str.slice(0, 10)
    frame = frame.loc[frame["status"].astype(str).str.upper() == "FILLED"]
    keep = [
        "trade_date",
        "ticker",
        "intended_notional",
        "filled_quantity",
        "fill_price",
        "close_price",
    ]
    return frame.loc[:, [name for name in keep if name in frame.columns]]


def _opens(path: Path) -> pd.DataFrame:
    """A long frame of `date`, `ticker`, `open`, from a parquet the caller supplies.

    The run tree's price panel has the column but only up to the last extended
    session, so a caller measuring the newest fills supplies the opens they fetched.
    """
    frame = pd.read_parquet(path)
    frame = frame.reset_index() if "date" not in frame.columns else frame
    frame["date"] = pd.to_datetime(frame["date"]).astype(str).str.slice(0, 10)
    return frame.loc[:, ["date", "ticker", "open"]]


def _quotes() -> pd.DataFrame:
    """The order-time quotes the store holds, or an empty frame before the migration.

    `efb.orders` carries the bid, the ask, their mid and the instant they were read
    since `docs/migrations/e13_order_quotes.sql`. Until that is applied the columns do
    not exist, and this returns an empty frame so the split falls back to the open as
    the reference - which is the honest answer for a leg that recorded no quote.
    """
    columns = ["trade_date", "ticker", "submitted_mid", "quoted_at"]
    try:
        catalog = store.select_catalog()
    except Exception:  # noqa: BLE001 - a schema read that must not stop a report
        return pd.DataFrame(columns=columns)
    if catalog is None or catalog.empty:
        return pd.DataFrame(columns=columns)
    have = set(
        catalog.loc[catalog["table_name"].astype(str) == "orders", "column_name"]
        .astype(str)
        .tolist()
    )
    if "submitted_mid" not in have:
        return pd.DataFrame(columns=columns)
    frame = store.select("orders")
    if frame is None or frame.empty or "submitted_mid" not in frame.columns:
        return pd.DataFrame(columns=columns)
    frame = frame.copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str.slice(0, 10)
    keep = [name for name in columns if name in frame.columns]
    return frame.loc[:, keep].dropna(subset=["submitted_mid"])


def _expected() -> dict[str, float]:
    """The model's predicted trading cost per session, from the reconciliation rows."""
    frame = store.select("reconciliation")
    if frame is None or frame.empty or "expected_cost_bps" not in frame.columns:
        return {}
    days = frame["trade_date"].astype(str).str.slice(0, 10)
    return {
        str(day): float(value)
        for day, value in zip(days, frame["expected_cost_bps"], strict=True)
        if pd.notna(value)
    }


def _nav() -> dict[str, float]:
    frame = store.select("nav")
    if frame is None or frame.empty or "nav" not in frame.columns:
        return {}
    days = frame["trade_date"].astype(str).str.slice(0, 10)
    return {
        str(day): float(value)
        for day, value in zip(days, frame["nav"], strict=True)
        if pd.notna(value)
    }


def split(
    fills: pd.DataFrame,
    opens: pd.DataFrame,
    nav: dict[str, float],
    quotes: pd.DataFrame | None = None,
) -> tuple[list[dict[str, object]], list[str]]:
    """The per-day split, and the legs that could not be priced for want of an open."""
    if fills.empty:
        return [], []
    legs = fills.merge(
        opens, left_on=["trade_date", "ticker"], right_on=["date", "ticker"], how="left"
    )
    if quotes is not None and not quotes.empty:
        legs = legs.merge(quotes, on=["trade_date", "ticker"], how="left")
    if "submitted_mid" not in legs.columns:
        legs["submitted_mid"] = pd.NA
    unpriced = sorted(
        {
            f"{row.ticker} {row.trade_date}"
            for row in legs.loc[
                legs["open"].isna() | legs["close_price"].isna()
            ].itertuples(index=False)
        }
    )
    legs = legs.loc[legs["open"].notna() & legs["close_price"].notna()].copy()
    if legs.empty:
        return [], unpriced
    # The side is the sign of the order's own notional: positive is a buy, negative a
    # sell, and a cost is positive for both - the convention `slippage_bps` uses.
    sign = (
        legs["intended_notional"]
        .astype(float)
        .apply(lambda value: 1.0 if value >= 0 else -1.0)
    )
    close = legs["close_price"].astype(float)
    open_price = legs["open"].astype(float)
    fill = legs["fill_price"].astype(float)
    quoted = pd.to_numeric(legs["submitted_mid"], errors="coerce")
    # The reference at submission is the mid the order saw. Where there is none the
    # open is the only reference there is, and the row says so through `basis`.
    reference = quoted.where(quoted > 0, open_price)
    legs = legs.assign(
        dollars=(legs["filled_quantity"].astype(float) * fill).abs(),
        overnight=1e4 * sign * (open_price - close) / close,
        drift=1e4 * sign * (reference - open_price) / open_price,
        execution=1e4 * sign * (fill - reference) / reference,
        total=1e4 * sign * (fill - close) / close,
        basis="submission mid where quoted, open otherwise",
    )
    rows: list[dict[str, object]] = []
    for day, block in legs.groupby("trade_date", sort=True):
        traded = float(block["dollars"].sum())
        equity = nav.get(str(day))
        weights = block["dollars"] / traded if traded else block["dollars"] * 0.0

        def row_quoted(block: pd.DataFrame) -> bool:
            values = pd.to_numeric(block["submitted_mid"], errors="coerce")
            return bool((values > 0).any())

        def _bp(column: str) -> float | None:
            value = float((block[column] * weights).sum())
            return value if pd.notna(value) else None

        def _of_nav(value: float | None) -> float | None:
            if value is None or not equity:
                return None
            return value * traded / float(equity)

        rows.append(
            {
                "trade_date": str(day),
                "n_legs": int(len(block)),
                "n_quoted": int(
                    (pd.to_numeric(block["submitted_mid"], errors="coerce") > 0).sum()
                ),
                "traded_notional": traded,
                "overnight_bp_traded": _bp("overnight"),
                "drift_bp_traded": _bp("drift"),
                "execution_bp_traded": _bp("execution"),
                "total_bp_traded": _bp("total"),
                "overnight_bp_nav": _of_nav(_bp("overnight")),
                "drift_bp_nav": _of_nav(_bp("drift")),
                "execution_bp_nav": _of_nav(_bp("execution")),
                "total_bp_nav": _of_nav(_bp("total")),
                "nav": equity,
                "basis": (
                    "submission mid where quoted, open otherwise"
                    if row_quoted(block)
                    else "open (no submission quote recorded)"
                ),
            }
        )
    return rows, unpriced


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opens", required=True, help="parquet of date, ticker, open")
    parser.add_argument("--json", default=None, help="also write the rows here")
    args = parser.parse_args(argv)

    rows, unpriced = split(_filled(), _opens(Path(args.opens)), _nav(), _quotes())
    if not rows:
        print("no filled leg in the store: nothing to split")
        return 1
    expected = _expected()
    header = (
        f"{'day':12s} {'legs':>4s} {'quoted':>6s} {'traded $':>12s} "
        f"{'overnight':>10s} {'drift':>7s} {'execution':>10s} {'total':>7s} "
        f"{'model':>6s}   {'o/n NAV':>7s} {'drift':>7s} {'exec':>7s}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['trade_date']:12s} {row['n_legs']:4d} {row['n_quoted']:6d} "
            f"{row['traded_notional']:12,.0f} "
            f"{row['overnight_bp_traded']:10.1f} {row['drift_bp_traded']:7.1f} "
            f"{row['execution_bp_traded']:10.1f} {row['total_bp_traded']:7.1f} "
            f"{expected.get(str(row['trade_date']), float('nan')):6.1f}   "
            f"{row['overnight_bp_nav'] or 0.0:7.2f} {row['drift_bp_nav'] or 0.0:7.2f} "
            f"{row['execution_bp_nav'] or 0.0:7.2f}"
        )
    print("\nbp of traded notional unless the column says NAV; the model column is")
    print("`expected_cost_bps`, the estimate the evening wrote for that session.")
    if unpriced:
        print(
            f"\n{len(unpriced)} leg(s) have no open for their session: {', '.join(unpriced)}"
        )
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1, default=str))
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
