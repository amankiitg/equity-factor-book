"""Follow-up to the churn study: the 23% exposure, partial adjustment, a drift guard.

Research only: nothing here trades, sets a live flag, writes a store or touches
`data/`. Targets are built by the live construction itself
(`live.evening_job.build_proposal`, `store=False`) on a copy of the tree, and every
knob is applied by argument or by a monkeypatch inside this script.

    python scripts/churn_followup.py run --root /tmp/churn/data \
        --out docs/research/churn_followup.json

Same window, cadence, universe and cost model as `scripts/churn_study.py` (imported,
not copied), so the B0 row here reproduces that study's B0 exactly.

The three questions:

C1  Where does the held book's 23% worst-day factor exposure come from - which day,
    which factor, and is it real drift or a measurement artifact? The whole daily
    series is kept, per factor, and the worst day is decomposed name by name.

C2  Partial adjustment: trade `phi * held + (1 - phi) * target`, then project the
    result back onto the design's null space (minimum-norm change) so the hedge is
    still exact on the session it trades. Also with `EFB_HEDGE_MODE=cap_then_rehedge`.

C3  A drift guard: on a hold day, if the held book's worst factor exposure exceeds
    3% of NAV, refresh the hedge only - project the held weights onto the neutral
    space with the minimum-norm change - and trade that.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import pathlib
import sys
import tempfile
from typing import Any

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import cadence_study as icd  # type: ignore[import-not-found]  # noqa: E402
import churn_study as churn  # type: ignore[import-not-found]  # noqa: E402

from efb import costs as cost_model  # noqa: E402
from efb import race  # noqa: E402
from efb.models import fundamental as fx  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("churn_followup")

CADENCE = churn.CADENCE
TRADING_DAYS = churn.TRADING_DAYS
START = churn.START
END = churn.END
NAV = churn.NAV_BASE
DRIFT_GUARD = 0.03  # the brief's 3% of NAV
DESIGN_GROSS_BP = 169.0
BORROW_RATES = (0.0025, 0.005, 0.01, 0.02)

# phi is the *held* share: 1.0 is no partial adjustment at all.
VARIANTS: dict[str, dict[str, Any]] = {
    "B0": {"phi": 1.0, "hedge": "exact", "guard": None},
    "B0H": {"phi": 1.0, "hedge": "cap_then_rehedge", "guard": None},
    "P25": {"phi": 0.25, "hedge": "exact", "guard": None},
    "P50": {"phi": 0.50, "hedge": "exact", "guard": None},
    "P75": {"phi": 0.75, "hedge": "exact", "guard": None},
    "P25H": {"phi": 0.25, "hedge": "cap_then_rehedge", "guard": None},
    "P50H": {"phi": 0.50, "hedge": "cap_then_rehedge", "guard": None},
    "P75H": {"phi": 0.75, "hedge": "cap_then_rehedge", "guard": None},
    "G3": {"phi": 1.0, "hedge": "exact", "guard": DRIFT_GUARD},
    "P50G3": {"phi": 0.50, "hedge": "exact", "guard": DRIFT_GUARD},
    # P50 with the rule the plain blend is missing: a name the target has dropped
    # leaves in full. Without it the blend keeps a decaying residual of every name
    # the alpha has abandoned, and the book's name count grows all window.
    "P50T": {"phi": 0.50, "hedge": "exact", "guard": None, "truncate": True},
}


# ------------------------------------------------------------------ the design


def design_for(
    market: icd.Market, day: pd.Timestamp, names: list[str]
) -> np.ndarray | None:
    """The day's design over `names`, in `fx.ESTIMATED_NAMES` order, or None."""
    if not names:
        return None
    try:
        return race._design_from_styles(market._z(day), names, market._codes())
    except Exception as exc:  # noqa: BLE001 - a missing design is reported, not fatal
        logger.warning("no design for %s: %s", day.date(), exc)
        return None


def exposure_vector(
    design: np.ndarray, weights: dict[str, float], names: list[str]
) -> np.ndarray:
    vector = np.asarray([weights.get(name, 0.0) for name in names], dtype=float)
    return design.T @ vector


def project_neutral(
    weights: dict[str, float], design: np.ndarray, names: list[str]
) -> dict[str, float]:
    """`weights` with the minimum-norm change that zeroes every factor exposure.

    The minimum-norm solution of `X'delta = X'w` is `delta = X (X'X)^+ X'w`, i.e.
    the projection of `w` onto the design's column space; subtracting it leaves the
    component of `w` the design cannot see. Every dollar removed on one name is
    therefore spread over the book in proportion to loading, not dumped on the
    largest position.
    """
    vector = np.asarray([weights.get(name, 0.0) for name in names], dtype=float)
    coef, *_ = np.linalg.lstsq(design, vector, rcond=None)
    residual = vector - design @ coef
    return {name: float(value) for name, value in zip(names, residual, strict=True)}


# ------------------------------------------------------------------ the variants


def _set_hedge_mode(mode: str) -> None:
    from live import evening_job

    if mode == "cap_then_rehedge":
        os.environ[evening_job.HEDGE_MODE_ENV] = evening_job.HEDGE_MODE_CAP_THEN_REHEDGE
    else:
        os.environ.pop(evening_job.HEDGE_MODE_ENV, None)
    evening_job._HEDGE_MODE_CACHE = None


def run_variant(
    name: str,
    spec: dict[str, Any],
    root: pathlib.Path,
    dates: list[pd.Timestamp],
    market: icd.Market,
    alphas: churn.AlphaSource,
    baseline: dict[str, Any] | None = None,
    detail: bool = False,
) -> dict[str, Any]:
    """Hold and rebalance one variant through the window, and report what it cost."""

    phi = float(spec["phi"])
    guard = spec["guard"]
    _set_hedge_mode(str(spec["hedge"]))
    icd.NAV = NAV
    held: dict[str, float] = {}
    gross: list[float] = []
    costs: list[float] = []
    borrows: list[float] = []
    # Rebalance days and guard trades are kept apart: a guard fires on a hold day,
    # so a mean over every trade would understate what one rebalance costs.
    turnovers: list[float] = []
    trade_turnovers: list[float] = []
    split_total = {"entries": 0.0, "exits": 0.0, "resizes": 0.0}
    names_held: list[int] = []
    exposures: list[float] = []
    exposures_at_rebalance: list[float] = []
    variance_shares: list[float] = []
    variance_shares_at_rebalance: list[float] = []
    held_alpha: list[float] = []
    fresh_alpha: dict[pd.Timestamp, float] = {}
    guard_fires: list[dict[str, Any]] = []
    guard_turnover = 0.0
    guard_cost = 0.0
    rebalances = 0
    daily: list[dict[str, Any]] = []
    try:
        for index, day in enumerate(dates):
            row = market.returns.loc[day] if day in market.returns.index else None
            portfolio = 0.0
            if index and row is not None and held:
                held, portfolio = icd._drift(held, row)
            gross.append(portfolio)
            is_rebalance = index % CADENCE == 0
            legs: dict[str, float] = {}
            split = {"entries": 0.0, "exits": 0.0, "resizes": 0.0}
            if is_rebalance:
                target = churn.build_target(
                    day, held, {"nav": NAV, "release": None, "band": False}, root, {}
                )
                rebalances += 1
                if phi < 1.0 and held:
                    blended = {
                        ticker: phi * held.get(ticker, 0.0)
                        + (1.0 - phi) * target.get(ticker, 0.0)
                        for ticker in set(held) | set(target)
                    }
                    if spec.get("truncate"):
                        # An exit is not a resize: a name the target has dropped
                        # leaves at once instead of decaying by (1 - phi) a month.
                        for ticker in list(blended):
                            if abs(target.get(ticker, 0.0)) < 1e-12:
                                blended[ticker] = 0.0
                    names = sorted(ticker for ticker, w in blended.items() if w != 0.0)
                    design = design_for(market, day, names)
                    traded = (
                        blended
                        if design is None
                        else project_neutral(blended, design, names)
                    )
                else:
                    traded = target
                book, legs, split = icd._rebalance(held, traded, traded, "V0")
                cost, notional = market.cost(legs, day)
                costs.append(cost / NAV)
                turnovers.append(notional / NAV)
                trade_turnovers.append(notional / NAV)
                for key in split_total:
                    split_total[key] += split[key]
                held = book
            elif guard is not None and held:
                # Hold day: measure the drift, and refresh the hedge only when the
                # worst exposure is past the guard. The refresh is the same
                # minimum-norm projection, so it adds no factor bet of its own.
                names = sorted(held)
                design = design_for(market, day, names)
                worst = (
                    float(np.abs(exposure_vector(design, held, names)).max())
                    if design is not None
                    else 0.0
                )
                if worst > float(guard):
                    refreshed = project_neutral(held, design, names)
                    book, legs, split = icd._rebalance(held, refreshed, refreshed, "V0")
                    cost, notional = market.cost(legs, day)
                    costs.append(cost / NAV)
                    trade_turnovers.append(notional / NAV)
                    guard_cost += cost
                    guard_turnover += notional
                    guard_fires.append(
                        {
                            "date": str(day.date()),
                            "exposure_before": worst,
                            "traded_notional": notional,
                            "cost": cost,
                        }
                    )
                    held = book
                else:
                    costs.append(0.0)
            else:
                costs.append(0.0)
            short_gross = float(sum(-w for w in held.values() if w < 0.0))
            borrows.append(float(cost_model.BORROW_RATE) * short_gross / TRADING_DAYS)
            names_held.append(len(held))
            names = sorted(held)
            design = design_for(market, day, names) if names else None
            if design is not None:
                vector = exposure_vector(design, held, names)
                exposures.append(float(np.abs(vector).max()))
                if is_rebalance:
                    exposures_at_rebalance.append(float(np.abs(vector).max()))
                if detail:
                    daily.append(
                        {
                            "date": str(day.date()),
                            "exposure": float(np.abs(vector).max()),
                            "vector": {
                                str(label): float(value)
                                for label, value in zip(
                                    fx.ESTIMATED_NAMES, vector, strict=True
                                )
                            },
                            "max_weight": float(
                                max((abs(w) for w in held.values()), default=0.0)
                            ),
                        }
                    )
            variance = alphas.variance(day)
            if held:
                weights = np.asarray([held[t] for t in held], dtype=float)
                specific = (
                    variance.reindex(list(held)).fillna(0.0).to_numpy(dtype=float)
                )
                squares = (weights**2) * specific
                total = float(squares.sum())
                share = float(squares.max() / total) if total > 0 else float("nan")
                variance_shares.append(share)
                if is_rebalance:
                    variance_shares_at_rebalance.append(share)
            alpha_today = alphas.alpha(day)
            held_alpha.append(
                float(sum(w * alpha_today.get(t, 0.0) for t, w in held.items()))
            )
        frame = pd.DataFrame(
            {"gross": gross, "cost": costs, "borrow": borrows},
            index=[pd.Timestamp(day) for day in dates],
        )
        frame["net"] = frame["gross"] - frame["cost"] - frame["borrow"]
    finally:
        _set_hedge_mode("exact")
        icd.NAV = churn.NAV_BASE

    years = len(frame) / TRADING_DAYS
    bp = 1e4 / years
    vol = float(frame["net"].std(ddof=1)) * math.sqrt(TRADING_DAYS)
    net_bp = float(frame["net"].sum()) * bp
    alpha_series = pd.Series(held_alpha, index=frame.index)
    out: dict[str, Any] = {
        "variant": name,
        "phi": phi,
        "hedge": spec["hedge"],
        "guard_threshold": guard,
        "sessions": int(len(frame)),
        "rebalances": int(rebalances),
        "turnover_per_rebalance": float(np.mean(turnovers)) if turnovers else 0.0,
        "trade_events": len(trade_turnovers),
        "turnover_per_trade_event": (
            float(np.mean(trade_turnovers)) if trade_turnovers else 0.0
        ),
        "turnover_per_year": float(np.sum(trade_turnovers)) / years,
        "split": {
            key: value / max(years, 1e-9) / (rebalances or 1)
            for key, value in split_total.items()
        },
        "gross_bp": float(frame["gross"].sum()) * bp,
        "cost_bp": float(frame["cost"].sum()) * bp,
        "borrow_bp": float(frame["borrow"].sum()) * bp,
        "net_bp": net_bp,
        "vol": vol,
        "sharpe": net_bp / 1e4 / vol if vol > 0 else float("nan"),
        "names_held": float(np.mean(names_held)),
        "exposure": {
            "median": float(np.median(exposures)) if exposures else float("nan"),
            "p95": float(np.percentile(exposures, 95)) if exposures else float("nan"),
            "p99": float(np.percentile(exposures, 99)) if exposures else float("nan"),
            "avg": float(np.mean(exposures)) if exposures else float("nan"),
            "max": float(np.max(exposures)) if exposures else float("nan"),
            "max_at_rebalance": (
                float(np.max(exposures_at_rebalance))
                if exposures_at_rebalance
                else float("nan")
            ),
        },
        "variance_share_avg": (
            float(np.nanmean(variance_shares)) if variance_shares else float("nan")
        ),
        "variance_share_max": (
            float(np.nanmax(variance_shares)) if variance_shares else float("nan")
        ),
        "variance_share_max_at_rebalance": (
            float(np.nanmax(variance_shares_at_rebalance))
            if variance_shares_at_rebalance
            else float("nan")
        ),
        "held_alpha": {str(day.date()): float(v) for day, v in alpha_series.items()},
        "fresh_alpha": {str(day.date()): value for day, value in fresh_alpha.items()},
        "guard": (
            {
                "threshold": guard,
                "fires": len(guard_fires),
                "turnover_per_year": guard_turnover / years / NAV,
                "cost_bp": guard_cost / NAV * bp,
                "events": guard_fires if detail else guard_fires[:5],
            }
            if guard is not None
            else None
        ),
    }
    if detail:
        out["daily"] = daily
    if baseline is not None:
        base_series = pd.Series(baseline["held_alpha"])
        base_series.index = pd.to_datetime(base_series.index)
        aligned = pd.concat(
            [alpha_series.rename("variant"), base_series.rename("base")], axis=1
        ).dropna()
        usable = aligned.loc[aligned["base"] != 0.0]
        out["alpha_retained"] = float((usable["variant"] / usable["base"]).mean())
    return out


# --------------------------------------------------------------------- the run


def run(root: pathlib.Path, out: pathlib.Path, only: list[str], detail_b0: bool) -> int:
    dates = churn.sessions(root)
    logger.info("%d sessions %s..%s", len(dates), dates[0].date(), dates[-1].date())
    market = icd.Market(root, [str(day.date()) for day in dates])
    alphas = churn.AlphaSource(root)
    partial = pathlib.Path(tempfile.gettempdir()) / f"{out.stem}_rows.partial.json"
    done: dict[str, dict[str, Any]] = {}
    if partial.exists():
        for row in json.loads(partial.read_text()):
            done[row["variant"]] = row
        logger.info("resuming with %d variant(s)", len(done))
    rows: list[dict[str, Any]] = []
    baseline: dict[str, Any] | None = done.get("B0")
    for name, spec in VARIANTS.items():
        if only and name not in only:
            continue
        if name in done:
            row = done[name]
        else:
            row = run_variant(
                name,
                spec,
                root,
                dates,
                market,
                alphas,
                baseline,
                detail=(name == "B0" and detail_b0),
            )
            done[name] = row
            partial.write_text(json.dumps(list(done.values()), default=str))
        rows.append(row)
        if name == "B0":
            baseline = row
        logger.info(
            "%-6s turnover/reb %6.2f%% cost %6.1f bp/yr net %7.1f expo med %.2f%% "
            "p99 %.2f%% max %.2f%%",
            name,
            row["turnover_per_rebalance"] * 100.0,
            row["cost_bp"],
            row["net_bp"],
            row["exposure"]["median"] * 100.0,
            row["exposure"]["p99"] * 100.0,
            row["exposure"]["max"] * 100.0,
        )
    payload = {
        "window": {
            "start": str(dates[0].date()),
            "end": str(dates[-1].date()),
            "sessions": len(dates),
            "years": round(len(dates) / TRADING_DAYS, 2),
            "cadence": CADENCE,
            "nav": NAV,
            "universe": (
                "frozen at the 2026-09-18 SPY archive, dated for every session: "
                "today's membership applied to the past, so P&L levels are indicative "
                "and the cross-variant comparison is the result"
            ),
        },
        "rows": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    logger.info("wrote %s", out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="churn follow-up")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--root", required=True)
    run_parser.add_argument("--out", required=True)
    run_parser.add_argument("--only", default="", help="comma-separated variant names")
    run_parser.add_argument("--no-detail", action="store_true")
    run_parser.set_defaults(
        func=lambda args: run(
            pathlib.Path(args.root).resolve(),
            pathlib.Path(args.out),
            [name for name in args.only.split(",") if name],
            not args.no_detail,
        )
    )
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
