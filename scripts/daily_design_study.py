"""What the drift guard costs once the loadings refresh every evening.

`docs/research/churn_followup.md` measured B0, G3 and the rest against the frozen
descriptor panel, which publishes on month ends: 29 design days in a 586-session
window. Live is not like that - `race.next_descriptor_design` builds the next
session's row from tonight's close, every night - so the study could not see the
drift between two refreshes and could not price a guard that fires on it.

This script reruns the same window, cadence, universe and cost model against the
daily panel built by `scripts/build_daily_design_panel.py`, so:

- every session has a design, so **exposure is measured every session** rather than
  on the 29 days the frozen panel happens to publish;
- a hold day's drift is measured against the design the book is actually hedged
  with, which is one close old, exactly as live measures it.

Variants (all on the same daily panel):

    D1     daily rebalance - the live baseline, k=1
    B0     monthly, no guard
    G3     monthly + 3% guard (hedge-only refresh on hold days)
    G5     monthly + 5% guard
    B0H    monthly, `EFB_HEDGE_MODE=cap_then_rehedge`
    G3H    monthly + 3% guard, cap_then_rehedge
    G5H    monthly + 5% guard, cap_then_rehedge

    EFB_DESIGN_RETURNS=clean python scripts/daily_design_study.py run \
        --root /tmp/churn/daily --out docs/research/daily_design_study.json

`EFB_DESIGN_RETURNS=clean` is required: the frozen rows the daily panel is validated
against were fitted on the cleaned panel, and the rebuilt rows reproduce them
exactly only on that branch (see `validate_daily_panel.py`).
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
from typing import Any

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import cadence_study as icd  # type: ignore[import-not-found]  # noqa: E402
import churn_followup as cf  # type: ignore[import-not-found]  # noqa: E402
import churn_study as churn  # type: ignore[import-not-found]  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("daily_design_study")

ANCHOR_GROSS_BP = 169.0
BORROW_RATES = (0.005, 0.02)

# B0 runs first so every other row has an alpha-retained reference to compare with.
SPECS: dict[str, dict[str, Any]] = {
    "B0": {"phi": 1.0, "hedge": "exact", "guard": None, "cadence": 21},
    "D1": {"phi": 1.0, "hedge": "exact", "guard": None, "cadence": 1},
    "G3": {"phi": 1.0, "hedge": "exact", "guard": 0.03, "cadence": 21},
    "G5": {"phi": 1.0, "hedge": "exact", "guard": 0.05, "cadence": 21},
    "B0H": {"phi": 1.0, "hedge": "cap_then_rehedge", "guard": None, "cadence": 21},
    "G3H": {"phi": 1.0, "hedge": "cap_then_rehedge", "guard": 0.03, "cadence": 21},
    "G5H": {"phi": 1.0, "hedge": "cap_then_rehedge", "guard": 0.05, "cadence": 21},
}


class DailyMarket(icd.Market):
    """`icd.Market` with the daily descriptor panel in place of the frozen one."""

    def __init__(self, root: pathlib.Path, dates: list[str]) -> None:
        super().__init__(root, dates)
        path = root / "models" / "XS-v1" / "descriptors_daily.parquet"
        if not path.exists():
            raise SystemExit(
                f"{path} is missing: run scripts/build_daily_design_panel.py first"
            )
        self._descriptors = pd.read_parquet(path)
        self._descriptors["date"] = pd.to_datetime(self._descriptors["date"])
        self._z_cache: dict[pd.Timestamp, pd.DataFrame] = {}
        logger.info(
            "daily panel: %d descriptors rows over %d sessions",
            len(self._descriptors),
            self._descriptors["date"].nunique(),
        )


def net_at_anchor(row: dict[str, Any], rate: float, model_rate: float) -> float:
    """The variant's net if the alpha source paid the design's 169 bp gross.

    Cost is the variant's own; borrow scales linearly off the study's modelled rate,
    so this is the same restatement `churn_followup.md` uses.
    """
    borrow = float(row["borrow_bp"]) * (rate / model_rate) if model_rate else 0.0
    return ANCHOR_GROSS_BP - float(row["cost_bp"]) - borrow


def run(root: pathlib.Path, out: pathlib.Path, only: list[str]) -> int:
    from efb import costs as cost_model

    dates = churn.sessions(root)
    logger.info("%d sessions %s..%s", len(dates), dates[0].date(), dates[-1].date())
    market = DailyMarket(root, [str(day.date()) for day in dates])
    alphas = churn.AlphaSource(root)
    model_rate = float(cost_model.BORROW_RATE)
    logger.info("model borrow rate %.4f", model_rate)

    partial = pathlib.Path("/tmp") / f"{out.stem}_rows.partial.json"
    done: dict[str, dict[str, Any]] = {}
    if partial.exists():
        for row in json.loads(partial.read_text()):
            done[row["variant"]] = row
        logger.info("resuming with %d variant(s)", len(done))

    rows: list[dict[str, Any]] = []
    baseline: dict[str, Any] | None = done.get("B0")
    for name, spec in SPECS.items():
        if only and name not in only:
            continue
        if name in done:
            row = done[name]
        else:
            cf.CADENCE = int(spec["cadence"])
            row = cf.run_variant(
                name,
                {key: value for key, value in spec.items() if key != "cadence"},
                root,
                dates,
                market,
                alphas,
                baseline,
                detail=False,
                design_sessions=None,
            )
        row["cadence"] = int(spec["cadence"])
        row["net_at_anchor"] = {
            f"{rate:.4f}": net_at_anchor(row, rate, model_rate) for rate in BORROW_RATES
        }
        if name not in done:
            done[name] = row
            partial.write_text(json.dumps(list(done.values()), default=str))
        if name == "B0":
            baseline = row
        rows.append(row)
        logger.info(
            "%-4s turnover/reb %6.2f%% cost %6.1f bp net %7.1f expo med %.2f%% "
            "p95 %.2f%% max %.2f%%",
            name,
            row["turnover_per_rebalance"] * 100.0,
            row["cost_bp"],
            row["net_bp"],
            row["exposure"]["median"] * 100.0,
            row["exposure"]["p95"] * 100.0,
            row["exposure"]["max"] * 100.0,
        )

    payload = {
        "window": {
            "start": str(dates[0].date()),
            "end": str(dates[-1].date()),
            "sessions": len(dates),
            "years": round(len(dates) / cf.TRADING_DAYS, 2),
            "nav": cf.NAV,
            "design_panel": "daily, built by scripts/build_daily_design_panel.py "
            "with race.next_descriptor_design's live branch (clean returns branch), "
            "installed as models/XS-v1/descriptors.parquet in the data copy so the "
            "construction hedges on the row dated the next session, as live does",
            "frozen_panel_design_days": 29,
            "universe": (
                "frozen at the 2026-09-18 SPY archive, dated for every session: "
                "today's membership applied to the past, so P&L levels are indicative "
                "and the cross-variant comparison is the result"
            ),
            "anchor_gross_bp": ANCHOR_GROSS_BP,
            "borrow_rates": list(BORROW_RATES),
            "model_borrow_rate": model_rate,
        },
        "rows": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    logger.info("wrote %s", out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="daily-design drift-guard study")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--root", required=True)
    run_parser.add_argument("--out", required=True)
    run_parser.add_argument("--only", default="")
    run_parser.set_defaults(
        func=lambda args: run(
            pathlib.Path(args.root).resolve(),
            pathlib.Path(args.out),
            [name for name in args.only.split(",") if name],
        )
    )
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
