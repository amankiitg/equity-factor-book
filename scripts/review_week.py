"""Sprint E12 item 8: the weekly review, on however many days exist.

Run:

    .venv/bin/python scripts/review_week.py            # every attributed day
    .venv/bin/python scripts/review_week.py --days 5   # the last five
    .venv/bin/python scripts/review_week.py --artifact # the seed book's artifact

The reader is the owner, on a Sunday, asking one question: did the book do what it
was built to do? So each day is one row of the seven things that answer it, and the
summary says in words what the numbers show rather than leaving the arithmetic to
be done in the head.

The three things the review is actually looking for, and why each is in the table:

- **The P&L split.** Factor, idio and cost, against the total. If the three do not
  add up the rest of the table is describing a different book, which is why the
  worst residual is printed with them.
- **Realized factor P&L against the near-zero the hedge promises.** The book is
  built factor-neutral to machine precision, so the factor line should be small and
  the hedge's own timing line smaller. A factor line that is not small means the
  book was not the book the hedge was applied to.
- **Cost realized against expected, and turnover.** The cost model was scored in
  E9 on simulated fills; the live days are the first real test of it, and the
  fill counts say whether the tested book is the traded one.

It works on one day. A single day cannot show a distribution and the summary says
so in those words rather than printing a standard error of one.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SEED_ARTIFACT = ROOT / "data" / "attribution" / "daily.parquet"

# One day is not a week, and the summary's language depends on knowing which it is.
MIN_DAYS_FOR_DISPERSION = 5


def load(days: int | None = None, *, artifact: bool = False) -> pd.DataFrame:
    """The attributed days, newest last, from the store or from the seed artifact.

    The store is the live record and the artifact is the seed book's own, so the
    same review runs against both and the seed run is what the report is scaffolded
    on before the clock starts.
    """
    if artifact:
        frame = pd.read_parquet(SEED_ARTIFACT)
    else:
        from live import store

        frame = store.select("attribution")
    if frame.empty:
        return frame
    frame = frame.copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str.slice(0, 10)
    frame = frame.sort_values("trade_date")
    if days is not None:
        frame = frame.tail(int(days))
    return frame


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    return float(value)


def day_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """One row per day, the seven columns the review reads."""
    rows: list[dict[str, Any]] = []
    for record in frame.to_dict("records"):
        rows.append(
            {
                "trade_date": str(record.get("trade_date"))[:10],
                "pnl_total": _number(record.get("pnl_total")),
                "pnl_factor": _number(record.get("pnl_factor")),
                "pnl_idio": _number(record.get("pnl_idio")),
                "pnl_cost": _number(record.get("pnl_cost")),
                "pnl_timing": _number(record.get("pnl_timing")),
                "identity_residual": _number(record.get("identity_residual")),
                "forecast_vol": _number(record.get("forecast_vol")),
                "realized_vol": _number(record.get("realized_vol")),
                "expected_cost_bps": _number(record.get("expected_cost_bps")),
                "realized_cost_bps": _number(record.get("realized_cost_bps")),
                "n_target": record.get("n_target"),
                "n_filled": record.get("n_filled"),
                "max_fill_gap": _number(record.get("max_fill_gap")),
                "n_missing_return": record.get("n_missing_return"),
                "missing_return_weight": _number(record.get("missing_return_weight")),
            }
        )
    return rows


def _mean(values: list[float]) -> float | None:
    return float(sum(values) / len(values)) if values else None


def _bp(value: float | None) -> str:
    """A P&L in basis points of the book, signed, or n/a when the store has none.

    The book is gross 1.0 of NAV, so a basis point of the book is a basis point of
    NAV. One helper formats every P&L on the page, because a review that printed one
    number as `n/a` and another as `0.0` for the same absence would be worse than
    useless.
    """
    return "n/a" if value is None else f"{value * 1e4:+.1f}"


def summarize(
    frame: pd.DataFrame, *, skill: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The report: the per-day rows, the totals and the plain-English lines.

    `skill` is `efb.attribution.skill_test`'s own result when the caller has it, so
    the review and the memo cannot quote two different t-statistics. It is computed
    here when it is not given, which is what the command does.
    """
    from efb import attribution

    if frame.empty:
        return {
            "n_days": 0,
            "first_day": None,
            "last_day": None,
            "rows": [],
            "totals": {},
            "lines": ["no attributed day is stored: the review has nothing to read"],
        }
    rows = day_rows(frame)
    totals = {
        "pnl_total": _number(frame["pnl_total"].sum()),
        "pnl_factor": _number(frame["pnl_factor"].sum()),
        "pnl_idio": _number(frame["pnl_idio"].sum()),
        "pnl_cost": _number(frame["pnl_cost"].sum()),
        "pnl_timing": _number(frame["pnl_timing"].sum()),
        "max_identity_residual": _number(frame["identity_residual"].abs().max()),
    }
    result = skill if skill is not None else attribution.skill_test(frame)
    expected = [
        float(record["expected_cost_bps"])
        for record in rows
        if record["expected_cost_bps"] is not None
    ]
    realized = [
        float(record["realized_cost_bps"])
        for record in rows
        if record["realized_cost_bps"] is not None
    ]
    forecast = [record["forecast_vol"] for record in rows if record["forecast_vol"]]
    observed = [record["realized_vol"] for record in rows if record["realized_vol"]]
    n_days = len(rows)
    lines: list[str] = []
    lines.append(
        f"{n_days} attributed day{'s' if n_days != 1 else ''}, "
        f"{rows[0]['trade_date']} to {rows[-1]['trade_date']}."
    )
    lines.append(
        "The three components against the total: "
        f"total {_bp(totals['pnl_total'])} bp = factor {_bp(totals['pnl_factor'])} + "
        f"idio {_bp(totals['pnl_idio'])} + cost {_bp(totals['pnl_cost'])}, worst "
        f"day's residual {_bp(totals['max_identity_residual'])} bp."
    )
    lines.append(
        "The hedge's promise: the book is factor-neutral to machine precision, so the "
        "factor line should be small and the hedge's own timing line smaller. Factor "
        f"{_bp(totals['pnl_factor'])} bp, of which the hedge timing is "
        f"{_bp(totals['pnl_timing'])} bp."
    )
    if expected and realized:
        lines.append(
            "Cost, realized against expected: "
            f"{_mean(realized):.2f} bp against {_mean(expected):.2f} bp over "
            f"{len(realized)} of {n_days} day(s) with a realized fill."
        )
    elif expected:
        lines.append(
            "Cost: the expected number is stored at "
            f"{_mean(expected):.2f} bp a day and no day has a realized fill yet, so "
            "the E9 model is still untested by real fills."
        )
    else:
        lines.append(
            "Cost: neither an expected nor a realized cost is stored for these days, "
            "so the cost model is not being reviewed here at all."
        )
    if forecast and observed:
        ratio = [o / f for o, f in zip(observed, forecast, strict=False) if f]
        lines.append(
            "Volatility, realized against forecast: realized "
            f"{_mean(observed):.4f} against forecast {_mean(forecast):.4f} "
            f"annualized, a ratio of {_mean(ratio):.2f}."
        )
    else:
        lines.append(
            "Volatility: no forecast was stored with these days, so ex-ante against "
            "ex-post is not reviewed here."
        )
    filled = [record for record in rows if record["n_filled"] is not None]
    if filled:
        intended = sum(int(record["n_target"] or 0) for record in filled)
        got = sum(int(record["n_filled"] or 0) for record in filled)
        worst_gap = max(
            (record["max_fill_gap"] or 0.0 for record in filled), default=0.0
        )
        lines.append(
            f"Fills: {got} of {intended} intended leg(s) filled, worst difference "
            f"between intended and filled ${worst_gap:,.0f}."
        )
    missing = sum(int(record["n_missing_return"] or 0) for record in rows)
    lines.append(
        f"Coverage: {missing} name-day(s) had no return that session, so their P&L "
        "could not be measured from the panel."
    )
    if n_days < MIN_DAYS_FOR_DISPERSION:
        lines.append(
            f"With {n_days} day{'s' if n_days != 1 else ''} there is no distribution "
            "yet: a mean over one or two days is a day, not an average, and the "
            "t-statistic below is quoted only so its size is visible."
        )
        t_text = (
            "no t-statistic"
            if result["t_stat"] is None
            else f"a t of {result['t_stat']:.2f}, which over "
            f"{n_days} day{'s' if n_days != 1 else ''} is not a test"
        )
    else:
        t_text = result["verdict"]
    lines.append(
        f"Skill: {t_text}. An edge of annualized information ratio 1.0 needs "
        f"{result['days_to_detect'].get(1.0)} days at a t of {result['target_t']:.1f} "
        f"before this window could see it, and 0.5 needs "
        f"{result['days_to_detect'].get(0.5)}."
    )
    return {
        "n_days": n_days,
        "first_day": rows[0]["trade_date"],
        "last_day": rows[-1]["trade_date"],
        "rows": rows,
        "totals": totals,
        "cost": {"expected_bps": _mean(expected), "realized_bps": _mean(realized)},
        "volatility": {
            "forecast": _mean(forecast) if forecast else None,
            "realized": _mean(observed) if observed else None,
        },
        "skill": result,
        "lines": lines,
    }


def text(report: dict[str, Any]) -> str:
    """The review as the owner reads it: the days first, then the words."""
    out: list[str] = ["EFB weekly review"]
    if not report["rows"]:
        out.extend(report["lines"])
        return "\n".join(out)
    header = (
        f"{'close':11s} {'total':>9s} {'factor':>9s} {'idio':>9s} {'cost':>8s} "
        f"{'hedge':>8s} {'real/exp cost':>15s} {'vol real/fc':>14s} {'fills':>9s}"
    )
    out.append(header)
    out.append("-" * len(header))
    for record in report["rows"]:
        hedge = _bp(record["pnl_timing"])
        cost = (
            f"{record['realized_cost_bps']:.1f}/{record['expected_cost_bps']:.1f}"
            if record["realized_cost_bps"] is not None
            and record["expected_cost_bps"] is not None
            else "n/a"
        )
        vol = (
            f"{record['realized_vol']:.3f}/{record['forecast_vol']:.3f}"
            if record["realized_vol"] is not None and record["forecast_vol"] is not None
            else "n/a"
        )
        fills = (
            f"{record['n_filled']}/{record['n_target']}"
            if record["n_filled"] is not None
            else "n/a"
        )
        out.append(
            f"{record['trade_date']:11s} {_bp(record['pnl_total']):>9s} "
            f"{_bp(record['pnl_factor']):>9s} {_bp(record['pnl_idio']):>9s} "
            f"{_bp(record['pnl_cost']):>8s} {hedge:>8s} {cost:>15s} {vol:>14s} "
            f"{fills:>9s}"
        )
    out.append("")
    out.append(
        "bp of the book; the book is gross 1.0 of NAV, so bp of book is bp of NAV."
    )
    out.append("")
    out.extend(report["lines"])
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--days", type=int, default=None, help="how many of the most recent days"
    )
    parser.add_argument(
        "--artifact",
        action="store_true",
        help="read the seed book's artifact instead of the live store",
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    frame = load(args.days, artifact=args.artifact)
    report = summarize(frame)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
