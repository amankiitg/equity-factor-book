"""C1: where the held book's worst-day factor exposure comes from.

Replays the churn study's B0 (monthly cadence, exact hedge, trade fully to target)
and, for the worst days, decomposes the exposure name by name. Read-only; nothing
is written but the JSON it is asked for.

    python scripts/exposure_diagnostic.py --root /tmp/churn/data \
        --out /tmp/exposure_diagnostic.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import cadence_study as icd  # type: ignore[import-not-found]  # noqa: E402
import churn_study as churn  # type: ignore[import-not-found]  # noqa: E402

from efb.models import fundamental as fx  # noqa: E402

CADENCE = churn.CADENCE
NAV = churn.NAV_BASE


def replay(
    root: pathlib.Path, dates: list[pd.Timestamp], market: icd.Market
) -> list[dict[str, Any]]:
    """B0's held book, day by day, with the design that measured it."""
    held: dict[str, float] = {}
    out: list[dict[str, Any]] = []
    for index, day in enumerate(dates):
        row = market.returns.loc[day] if day in market.returns.index else None
        if index and row is not None and held:
            held, _ = icd._drift(held, row)
        is_rebalance = index % CADENCE == 0
        if is_rebalance:
            target = churn.build_target(
                day, held, {"nav": NAV, "release": None, "band": False}, root, {}
            )
            book, _legs, _split = icd._rebalance(held, target, target, "V0")
            held = book
        names = sorted(held)
        if not names:
            continue
        design = market._design(day, names) if hasattr(market, "_design") else None
        if design is None:
            from efb import race

            design = race._design_from_styles(market._z(day), names, market._codes())
        vector = design.T @ np.asarray([held[n] for n in names], dtype=float)
        out.append(
            {
                "date": day,
                "index": index,
                "rebalance": is_rebalance,
                "names": names,
                "weights": {n: held[n] for n in names},
                "vector": vector,
                "design": design,
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C1 exposure diagnostic")
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--top", type=int, default=8)
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    dates = churn.sessions(root)
    market = icd.Market(root, [str(day.date()) for day in dates])
    days = replay(root, dates, market)

    exposures = np.array([float(np.abs(d["vector"]).max()) for d in days])
    ranked = np.argsort(-exposures)[: args.top]
    descriptor_dates = {
        pd.Timestamp(day).normalize()
        for day in pd.read_parquet(root / "models" / "XS-v1" / "descriptors.parquet")[
            "date"
        ]
    }
    design_days = [d for d in days if d["date"] in descriptor_dates]
    design_exposures = np.array([float(np.abs(d["vector"]).max()) for d in design_days])
    report: dict[str, Any] = {
        "design_days": {
            "n": int(len(design_days)),
            "of": int(len(days)),
            "median": (
                float(np.median(design_exposures)) if len(design_exposures) else None
            ),
            "p95": (
                float(np.percentile(design_exposures, 95))
                if len(design_exposures)
                else None
            ),
            "max": float(design_exposures.max()) if len(design_exposures) else None,
            "dates": [str(d["date"].date()) for d in design_days],
        },
        "distribution": {
            "n_days": int(len(exposures)),
            "median": float(np.median(exposures)),
            "mean": float(np.mean(exposures)),
            "p90": float(np.percentile(exposures, 90)),
            "p95": float(np.percentile(exposures, 95)),
            "p99": float(np.percentile(exposures, 99)),
            "max": float(exposures.max()),
            "share_over_3pct": float((exposures > 0.03).mean()),
            "share_over_5pct": float((exposures > 0.05).mean()),
        },
        "worst_days": [],
        "rebalance_days": {
            "n": int(sum(1 for d in days if d["rebalance"])),
            "max": float(
                max(
                    (float(np.abs(d["vector"]).max()) for d in days if d["rebalance"]),
                    default=float("nan"),
                )
            ),
        },
    }

    for position in ranked:
        day = days[position]
        vector = np.asarray(day["vector"], dtype=float)
        labels = list(fx.ESTIMATED_NAMES)
        worst_label = labels[int(np.argmax(np.abs(vector)))]
        column = labels.index(worst_label)
        weights = day["weights"]
        names = day["names"]
        design = day["design"]
        loadings = design[:, column]
        contributions = [
            (name, float(weights[name]), float(loading), float(weights[name] * loading))
            for name, loading in zip(names, loadings, strict=True)
        ]
        contributions.sort(key=lambda item: -abs(item[3]))
        total_abs = float(sum(abs(item[3]) for item in contributions))
        net = float(sum(item[3] for item in contributions))
        z_day = market._z(day["date"])
        previous = None
        if day["index"] > 0:
            prior = days[position - 1]
            if prior["date"] == dates[day["index"] - 1]:
                prior_vector = np.asarray(prior["vector"], dtype=float)
                previous = {
                    "date": str(prior["date"].date()),
                    "exposure": float(np.abs(prior_vector).max()),
                    "this_factor": float(prior_vector[column]),
                }
        window = market.returns.loc[: day["date"]].tail(21)
        stale = []
        for name, _w, _l, _c in contributions[:5]:
            series = window[name] if name in window.columns else pd.Series(dtype=float)
            stale.append(
                {
                    "ticker": name,
                    "sessions": int(len(series)),
                    "missing_returns": int(series.isna().sum()),
                    "zero_returns": int((series.fillna(0.0) == 0.0).sum()),
                    "cum_return": float(np.nansum(series.to_numpy(dtype=float))),
                    "z_used": (
                        float(z_day.loc[name, "reversal"])
                        if name in z_day.index and "reversal" in z_day.columns
                        else None
                    ),
                }
            )
        report["worst_days"].append(
            {
                "date": str(day["date"].date()),
                "sessions_since_rebalance": int(day["index"] % CADENCE),
                "is_rebalance": bool(day["rebalance"]),
                "exposure": float(np.abs(vector).max()),
                "factor": worst_label,
                "this_factor_exposure": float(vector[column]),
                "next_factors": {
                    labels[i]: float(vector[i]) for i in np.argsort(-np.abs(vector))[:4]
                },
                "net_over_gross": net / total_abs if total_abs else float("nan"),
                "n_names": len(names),
                "top_contributions": [
                    {
                        "ticker": name,
                        "weight": weight,
                        "loading": loading,
                        "contribution": contribution,
                    }
                    for name, weight, loading, contribution in contributions[:8]
                ],
                "loading_std_cross_section": float(np.std(loadings)),
                "max_abs_loading": float(np.max(np.abs(loadings))),
                "max_abs_weight": float(max(abs(w) for w in weights.values())),
                "previous_day": previous,
                "top5_returns_21d": stale,
            }
        )

    # The worst day under a *fixed* design: the same loadings applied to the book
    # as it was on each of the sessions before it. That separates the weights moving
    # (drift) from the design being re-estimated (measurement).
    worst = days[int(ranked[0])]
    worst_column = list(fx.ESTIMATED_NAMES).index(
        list(fx.ESTIMATED_NAMES)[int(np.argmax(np.abs(worst["vector"])))]
    )
    series = []
    for entry in days[max(0, int(ranked[0]) - 21) : int(ranked[0]) + 1]:
        shared = [n for n in worst["names"] if n in entry["weights"]]
        if not shared:
            continue
        index = [worst["names"].index(n) for n in shared]
        vector = worst["design"][index].T @ np.asarray(
            [entry["weights"][n] for n in shared], dtype=float
        )
        series.append(
            {
                "date": str(entry["date"].date()),
                "exposure_fixed_design": float(np.abs(vector).max()),
                "this_factor": float(vector[worst_column]),
                "shared_names": len(shared),
            }
        )
    report["fixed_design_series"] = {
        "factor": list(fx.ESTIMATED_NAMES)[worst_column],
        "design_date": str(worst["date"].date()),
        "series": series,
    }
    winsor = market._z(worst["date"])["reversal"].dropna()
    report["winsorization"] = {
        "n": int(len(winsor)),
        "max": float(winsor.max()),
        "min": float(winsor.min()),
        "count_at_max": int((winsor == winsor.max()).sum()),
        "count_at_min": int((winsor == winsor.min()).sum()),
        "std": float(winsor.std()),
    }

    pathlib.Path(args.out).write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    )
    print(json.dumps(report["distribution"], indent=2))
    for entry in report["worst_days"]:
        print(
            entry["date"],
            f"{entry['exposure']*100:.2f}%",
            entry["factor"],
            f"net/gross {entry['net_over_gross']:.3f}",
            f"since_reb {entry['sessions_since_rebalance']}",
            "top:",
            [
                (c["ticker"], round(c["contribution"] * 100, 1))
                for c in entry["top_contributions"][:4]
            ],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
