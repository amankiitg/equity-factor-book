"""Why does a monthly rebalance trade 87% of NAV? The construction steps, one at a time.

Research only: nothing here trades, sets a flag, writes a store or touches `data/`. The
targets are built by the live construction itself (`live.evening_job.build_proposal`,
`store=False`), on a *copy* of the tree, and every variant's knob is applied by argument
or by a monkeypatch inside this script, never by editing `live/` or `efb/`.

    python scripts/churn_study.py run --root /tmp/churn/data \
        --out docs/research/churn_study.json

**The path is sequential, one build per rebalance day**, passing the *currently held*
book as `previous`, because the floor's release band and the impact term both depend on
it: a rebalance cannot be priced without the book it starts from. Between rebalances the
book is held and drifts with the tree's own returns, exactly as the cadence study does.

The question is the gap in `docs/research/ic_decay.md` §6: the design book's monthly
rebalance trades 35.6% of NAV and the live construction's trades 87.0%, for 42 bp/yr of
cost. The signal is not the cause - its rank autocorrelation is 0.994 at one day - so
the
candidates are the construction's own steps. This study isolates them:

    B0        baseline: the live construction at NAV 1,000,000, trade fully to target
    B1        B0 + the 25% resize band (the cadence study's V1)
    F75/F50   EFB_FLOOR_RELEASE 0.75 / 0.5 - a held name is released only below that
              fraction of its own floor, entry still needs the full floor
    N2/N5     NAV 2,000,000 / 5,000,000 - the 20-share floor is a fixed dollar minimum,
              so it binds less on a bigger book
    F75+B1, N5+B1, F50+N2+B1   the combinations
    NOFLOOR   reference only: the floor removed (share and dollar minimum at zero) to
              show how much of the turnover the floor alone causes

`expected alpha retained` is the robust metric, and the reason it is here: P&L over 2.33
years carries about 280 bp/yr of standard error per cell, so the net column cannot rank
variants. The held book's alpha - the sum of held weight times that day's `alpha_vec`,
which is the linear functional the sizing maximises - is measured every day, and a
variant's ratio to B0's says how much of the edge it gives up to save turnover.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
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

from efb import costs as cost_model  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("churn_study")

CADENCE = 21
START = "2024-06-03"
END = "2026-10-02"
NAV_BASE = 1_000_000.0
BAND = 0.25
TRADING_DAYS = 252
# The decision rule's ceilings.
EXPOSURE_CEILING = 0.05
VARIANCE_SHARE_CEILING = 0.15
ALPHA_FLOOR = 0.90
# For the monthly net at the design anchor.
DESIGN_GROSS_BP = 169.0
DESIGN_BORROW_BP = 100.0

VARIANTS: dict[str, dict[str, Any]] = {
    "B0": {"nav": NAV_BASE, "release": None, "band": False, "nofloor": False},
    "B1": {"nav": NAV_BASE, "release": None, "band": True, "nofloor": False},
    "F75": {"nav": NAV_BASE, "release": 0.75, "band": False, "nofloor": False},
    "F50": {"nav": NAV_BASE, "release": 0.50, "band": False, "nofloor": False},
    "N2": {"nav": 2 * NAV_BASE, "release": None, "band": False, "nofloor": False},
    "N5": {"nav": 5 * NAV_BASE, "release": None, "band": False, "nofloor": False},
    "F75+B1": {"nav": NAV_BASE, "release": 0.75, "band": True, "nofloor": False},
    "N5+B1": {"nav": 5 * NAV_BASE, "release": None, "band": True, "nofloor": False},
    "F50+N2+B1": {"nav": 2 * NAV_BASE, "release": 0.50, "band": True, "nofloor": False},
    "NOFLOOR": {"nav": NAV_BASE, "release": None, "band": False, "nofloor": True},
}
CANDIDATES = [name for name in VARIANTS if name != "NOFLOOR"]


# ------------------------------------------------------------------- the inputs


def sessions(root: pathlib.Path) -> list[pd.Timestamp]:
    frame = pd.read_parquet(root / "processed" / "returns.parquet")
    dates = pd.Index(frame.index.get_level_values("date")).unique().sort_values()
    window = dates[(dates >= pd.Timestamp(START)) & (dates <= pd.Timestamp(END))]
    return [pd.Timestamp(stamp) for stamp in window]


class AlphaSource:
    """The day's `alpha_vec`, without a build, for the days between rebalances.

    The live path forms it as `ic x sigma_i x z_i x kappa` (`alpha_from_contract`) with
    `z` the cross-sectional z-score of the same `idio_momentum` signal and `sigma` the
    square root of the model's stored specific variance. Recomputed here over the day's
    names with a variance and a signal; on the rebalance days it is checked against the
    vector the build itself produced (see `alpha_check` in the output).
    """

    def __init__(self, root: pathlib.Path) -> None:
        from efb import alpha as alpha_mod
        from efb import race
        from live import evening_job

        self.root = root
        self.race = race
        self.ic = float(evening_job._stored_ic("idio_momentum", root))
        self.kappa = float(alpha_mod.KAPPA)
        self.signal = alpha_mod.idio_momentum(root)
        self.signal["date"] = pd.to_datetime(self.signal["date"])
        self.signal = self.signal.pivot(
            index="date", columns="ticker", values="signal"
        ).sort_index()
        variances = pd.read_parquet(root / "models" / "XS-v1" / "specific_var.parquet")
        variances["date"] = pd.to_datetime(variances["date"])
        self.variances = {
            stamp: day.set_index("ticker")["specific_var"]
            for stamp, day in variances.groupby("date", sort=True)
        }
        self.var_dates = np.asarray(sorted(self.variances), dtype="datetime64[ns]")

    def variance(self, date: pd.Timestamp) -> pd.Series:
        """The stored specific variance as of `date`: the latest row on or before."""
        position = int(
            np.searchsorted(self.var_dates, np.datetime64(date), side="right")
        )
        stamp = self.var_dates[max(position - 1, 0)]
        return self.variances[pd.Timestamp(stamp)]

    def alpha(self, date: pd.Timestamp) -> pd.Series:
        variance = self.variance(date)
        sigma = np.sqrt(variance.clip(lower=0.0))
        raw = self.signal.loc[date] if date in self.signal.index else None
        if raw is None:
            return pd.Series(0.0, index=sigma.index)
        raw = raw.reindex(sigma.index)
        usable = raw.notna() & sigma.gt(0.0)
        z = pd.Series(0.0, index=sigma.index)
        if usable.any():
            values = raw.loc[usable]
            deviation = float(values.std(ddof=1))
            if deviation > 0:
                z.loc[usable] = (values - float(values.mean())) / deviation
        return self.ic * sigma.fillna(0.0) * z * self.kappa


# --------------------------------------------------------------- the variant run


def _capture_alpha_specific() -> tuple[Any, dict[str, Any], Any]:
    """Wrap the floor call: the one place `names`, `alpha_vec` and `specific` meet.

    `live/evening_job.py` imports `enforce_floor_by_drop_then_admit` by name, so
    patching
    the module attribute is enough to see the exact vectors the build used - the check
    that the daily `AlphaSource` reconstruction agrees with the real thing.
    """
    from live import evening_job

    original = evening_job.enforce_floor_by_drop_then_admit
    captured: dict[str, Any] = {}

    def wrapper(
        names: list[str],
        alpha_vec: np.ndarray,
        design: np.ndarray,
        factor_covariance: np.ndarray,
        specific: np.ndarray,
        close: dict[str, float],
        nav: float,
        full_weights: np.ndarray,
        dollar_floor: float,
        share_floor: int,
        **kwargs: Any,
    ) -> Any:
        captured["names"] = list(names)
        captured["alpha"] = np.array(alpha_vec, dtype=float)
        captured["specific"] = np.array(specific, dtype=float)
        return original(
            names,
            alpha_vec,
            design,
            factor_covariance,
            specific,
            close,
            nav,
            full_weights,
            dollar_floor,
            share_floor,
            **kwargs,
        )

    return original, captured, wrapper


def _no_floor_patch() -> tuple[Any, Any]:
    """`registry.live_construction` with the share and dollar minimums at zero."""
    from efb import registry

    original = registry.live_construction

    def zero_floor(reg: Any, version: Any) -> dict[str, Any]:
        spec = dict(original(reg, version))
        spec["dollar_floor"] = 0.0
        spec["share_floor"] = 0
        return spec

    return original, zero_floor


def _band_aware_violations() -> tuple[Any, Any, list[str]]:
    """The floor checks, minus the one the band is designed to break.

    **A live defect this study found.** `live/evening_job.py::floor_book_violations`
    ends with `below_floor(shares, prices, dollar_floor, share_floor)` on the *full*
    floor and `build_proposal` raises when it is non-empty, but `EFB_FLOOR_RELEASE` is
    built to keep a held name that is *below* its floor (and above the band). So with
    the flag on, the first rebalance where the band binds raises "the enforced floor
    book fails its checks and must not trade" and the evening produces no book at all.
    The band's own tests exercise the mask and the fixed point directly, and the one
    test that builds a proposal builds it with the flag off, which is why this has not
    been seen. Measured here: it fires on the very first monthly rebalance.

    For the experiment only, the below-floor violation is dropped when the band is on
    (the other four checks - dollar neutrality, the exact hedge, the idio share and the
    rank margin - are kept), and every violation the patch suppresses is recorded so
    the number is reported rather than assumed.
    """
    from live import evening_job

    original = evening_job.floor_book_violations
    suppressed: list[str] = []

    def relaxed(*args: Any, **kwargs: Any) -> list[str]:
        found = original(*args, **kwargs)
        kept = []
        for violation in found:
            if "below their floor" in violation:
                suppressed.append(violation)
            else:
                kept.append(violation)
        return kept

    return original, relaxed, suppressed


def build_target(
    day: pd.Timestamp,
    held: dict[str, float],
    spec: dict[str, Any],
    root: pathlib.Path,
    captured: dict[str, Any],
) -> dict[str, float]:
    """One rebalance day's target book, from the book actually held."""
    from live import evening_job

    previous = pd.Series(held, dtype=float).sort_index() if held else None
    manifest = evening_job.build_proposal(
        data_root=root,
        as_of=day,
        nav=float(spec["nav"]),
        store=False,
        previous=previous,
        floor_release=spec["release"],
    )
    rows = list(manifest["kept_book"])  # type: ignore[call-overload]
    return {str(row["ticker"]): float(row["weight"]) for row in rows}


def run_variant(
    name: str,
    spec: dict[str, Any],
    root: pathlib.Path,
    dates: list[pd.Timestamp],
    market: icd.Market,
    alphas: AlphaSource,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hold and rebalance one variant through the window, and report what it cost."""
    original_floor, captured, wrapper = _capture_alpha_specific()
    violations_original = None
    suppressed: list[str] = []
    if spec["release"] is not None and float(spec["release"]) < 1.0:
        violations_original, relaxed, suppressed = _band_aware_violations()
        from live import evening_job as evening_job_mod

        evening_job_mod.floor_book_violations = relaxed
    registry_original = None
    if spec["nofloor"]:
        registry_original, zero_floor = _no_floor_patch()
        from efb import registry as registry_mod

        registry_mod.live_construction = zero_floor
    icd.NAV = float(spec["nav"])

    from live import evening_job

    evening_job.enforce_floor_by_drop_then_admit = wrapper
    try:
        held: dict[str, float] = {}
        gross: list[float] = []
        costs: list[float] = []
        borrows: list[float] = []
        turnovers: list[float] = []
        split_total = {"entries": 0.0, "exits": 0.0, "resizes": 0.0}
        names_held: list[int] = []
        exposures: list[float] = []
        exposures_at_rebalance: list[float] = []
        variance_shares: list[float] = []
        variance_shares_at_rebalance: list[float] = []
        held_alpha: list[float] = []
        fresh_alpha: dict[pd.Timestamp, float] = {}
        alpha_compare: list[tuple[float, float]] = []
        n_built = 0
        for index, day in enumerate(dates):
            row = market.returns.loc[day] if day in market.returns.index else None
            portfolio = 0.0
            if index and row is not None and held:
                held, portfolio = icd._drift(held, row)
            gross.append(portfolio)
            if index % CADENCE == 0:
                captured.clear()
                target = build_target(day, held, spec, root, captured)
                n_built += 1
                if captured.get("names"):
                    alpha_series = pd.Series(
                        captured["alpha"], index=[str(n) for n in captured["names"]]
                    )
                    reconstructed = alphas.alpha(day).reindex(alpha_series.index)
                    alpha_compare.append(
                        (
                            float(np.corrcoef(reconstructed, alpha_series)[0, 1]),
                            float(
                                reconstructed.dot(alpha_series)
                                / max(alpha_series.dot(alpha_series), 1e-30)
                            ),
                        )
                    )
                    fresh_alpha[day] = float(
                        sum(
                            target.get(t, 0.0) * alpha_series.get(t, 0.0)
                            for t in target
                        )
                    )
                book, legs, split = icd._rebalance(
                    held, target, target, "V1" if spec["band"] else "V0"
                )
                cost, notional = market.cost(legs, day)
                costs.append(cost / float(spec["nav"]))
                turnovers.append(notional / float(spec["nav"]))
                for key in split_total:
                    split_total[key] += split[key]
                held = book
            else:
                costs.append(0.0)
            short_gross = float(
                sum(-weight for weight in held.values() if weight < 0.0)
            )
            borrows.append(float(cost_model.BORROW_RATE) * short_gross / TRADING_DAYS)
            names_held.append(len(held))
            at_rebalance = index % CADENCE == 0
            value = market.exposure(day, held)
            if value is not None:
                exposures.append(value)
                if at_rebalance:
                    exposures_at_rebalance.append(value)
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
                if at_rebalance:
                    variance_shares_at_rebalance.append(share)
            alpha_today = alphas.alpha(day)
            held_alpha.append(
                float(
                    sum(
                        weight * alpha_today.get(name, 0.0)
                        for name, weight in held.items()
                    )
                )
            )
        frame = pd.DataFrame(
            {"gross": gross, "cost": costs, "borrow": borrows},
            index=[pd.Timestamp(day) for day in dates],
        )
        frame["net"] = frame["gross"] - frame["cost"] - frame["borrow"]
    finally:
        evening_job.enforce_floor_by_drop_then_admit = original_floor
        if violations_original is not None:
            from live import evening_job as evening_job_mod

            evening_job_mod.floor_book_violations = violations_original
        if registry_original is not None:
            from efb import registry as registry_mod

            registry_mod.live_construction = registry_original
        icd.NAV = NAV_BASE

    years = len(frame) / TRADING_DAYS
    bp = 1e4 / years
    vol = float(frame["net"].std(ddof=1)) * math.sqrt(TRADING_DAYS)
    net_bp = float(frame["net"].sum()) * bp
    alpha_series = pd.Series(held_alpha, index=frame.index)
    out = {
        "variant": name,
        "nav": float(spec["nav"]),
        "release": spec["release"],
        "band": bool(spec["band"]),
        "nofloor": bool(spec["nofloor"]),
        "sessions": int(len(frame)),
        "rebalances": int(n_built),
        "turnover_per_rebalance": float(np.mean(turnovers)) if turnovers else 0.0,
        "turnover_per_year": float(np.sum(turnovers)) / years,
        "split": {
            key: value / max(years, 1e-9) / (len(turnovers) or 1)
            for key, value in split_total.items()
        },
        "split_total": dict(split_total),
        "gross_bp": float(frame["gross"].sum()) * bp,
        "cost_bp": float(frame["cost"].sum()) * bp,
        "borrow_bp": float(frame["borrow"].sum()) * bp,
        "net_bp": net_bp,
        "vol": vol,
        "sharpe": net_bp / 1e4 / vol if vol > 0 else float("nan"),
        "names_held": float(np.mean(names_held)),
        "exposure_avg": float(np.mean(exposures)) if exposures else float("nan"),
        "exposure_max": float(np.max(exposures)) if exposures else float("nan"),
        # The variant's own doing, measured right after it trades, against the drift
        # that every 21-session cadence accumulates whatever the variant does.
        "exposure_max_at_rebalance": (
            float(np.max(exposures_at_rebalance))
            if exposures_at_rebalance
            else float("nan")
        ),
        "exposure_avg_at_rebalance": (
            float(np.mean(exposures_at_rebalance))
            if exposures_at_rebalance
            else float("nan")
        ),
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
        "alpha_check_correlation": (
            float(np.mean([c for c, _ in alpha_compare])) if alpha_compare else None
        ),
        "alpha_check_scale": (
            float(np.mean([s for _, s in alpha_compare])) if alpha_compare else None
        ),
        "below_floor_violations_suppressed": len(suppressed),
    }
    if baseline is not None:
        base_series = pd.Series(baseline["held_alpha"])
        base_series.index = pd.to_datetime(base_series.index)
        aligned = pd.concat(
            [alpha_series.rename("variant"), base_series.rename("base")], axis=1
        ).dropna()
        usable = aligned.loc[aligned["base"] != 0.0]
        out["alpha_retained"] = float((usable["variant"] / usable["base"]).mean())
        fresh_base = pd.Series(
            {pd.Timestamp(day): value for day, value in baseline["fresh_alpha"].items()}
        )
        shared = [day for day in fresh_alpha if day in fresh_base.index]
        if shared:
            out["alpha_retained_vs_fresh"] = float(
                np.mean(
                    [
                        fresh_alpha[day] / fresh_base.loc[day]
                        for day in shared
                        if fresh_base.loc[day]
                    ]
                )
            )
    return out


def _eligible(
    by_name: dict[str, Any], exposure_key: str, share_key: str
) -> tuple[list[str], list[dict[str, Any]]]:
    """The candidates that clear all three ceilings under one reading of exposure."""
    eligible: list[str] = []
    rejected: list[dict[str, Any]] = []
    for name in CANDIDATES:
        row = by_name[name]
        reasons = []
        exposure = row[exposure_key]
        share = row[share_key]
        if not (exposure <= EXPOSURE_CEILING):
            reasons.append(f"exposure {exposure:.2%} > 5%")
        if not (share <= VARIANCE_SHARE_CEILING):
            reasons.append(f"variance share {share:.1%} > 15%")
        # B0 is the baseline the ratio is taken against, so its own retained alpha is
        # 100% by definition rather than missing.
        retained = 1.0 if name == "B0" else row.get("alpha_retained", 0.0)
        if not (retained >= ALPHA_FLOOR):
            reasons.append(f"alpha retained {retained:.1%} < 90%")
        if reasons:
            rejected.append({"variant": name, "reasons": reasons})
        else:
            eligible.append(name)
    return eligible, rejected


def _winner(by_name: dict[str, Any], eligible: list[str]) -> dict[str, Any] | None:
    if not eligible:
        return None
    best = min(eligible, key=lambda name: by_name[name]["turnover_per_rebalance"])
    row = by_name[best]
    baseline = by_name["B0"]
    saving = baseline["cost_bp"] - row["cost_bp"]
    return {
        "variant": best,
        "turnover_per_rebalance": row["turnover_per_rebalance"],
        "saving_bp": float(saving),
        "baseline_cost_bp": float(baseline["cost_bp"]),
        "winner_cost_bp": float(row["cost_bp"]),
        "monthly_net_at_design_anchor": float(
            DESIGN_GROSS_BP - row["cost_bp"] - DESIGN_BORROW_BP
        ),
        "baseline_monthly_net_at_design_anchor": float(
            DESIGN_GROSS_BP - baseline["cost_bp"] - DESIGN_BORROW_BP
        ),
    }


def _eligible_no_worse_than_baseline(
    by_name: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    """The third reading: the ceilings are breached by B0 itself, so ask for no worse.

    Two of the rule's three tests are failed by the *baseline* construction, before any
    variant is considered: the worst day's factor exposure is drift between rebalances
    (a property of the 21-session cadence), and the worst single-name variance share
    exceeds the cap because the cap is applied to the sized book before the floor drops
    names and renormalizes onto a subset. A rule that no candidate can pass cannot pick
    one, so this reading asks the question the variants can actually answer: does this
    variant leave the book no worse on either risk measure than B0, and keep at least
    90% of its alpha? The ranking is then by turnover, which is what the study is about.
    """
    base = by_name["B0"]
    eligible: list[str] = []
    rejected: list[dict[str, Any]] = []
    for name in CANDIDATES:
        row = by_name[name]
        reasons = []
        if row["exposure_max_at_rebalance"] > base["exposure_max_at_rebalance"]:
            reasons.append(
                f"rebalance exposure {row['exposure_max_at_rebalance']:.2%} worse than "
                f"B0's {base['exposure_max_at_rebalance']:.2%}"
            )
        if (
            row["variance_share_max_at_rebalance"]
            > base["variance_share_max_at_rebalance"]
        ):
            reasons.append(
                f"variance share {row['variance_share_max_at_rebalance']:.1%} worse "
                f"than B0's {base['variance_share_max_at_rebalance']:.1%}"
            )
        retained = 1.0 if name == "B0" else row.get("alpha_retained", 0.0)
        if retained < ALPHA_FLOOR:
            reasons.append(f"alpha retained {retained:.1%} < 90%")
        if reasons:
            rejected.append({"variant": name, "reasons": reasons})
        else:
            eligible.append(name)
    return eligible, rejected


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The decision rule, applied twice: as written, and on the variant's own exposure.

    The rule's two ceilings are about the **held** book, so they are applied as written
    to the worst day of the whole hold. That reading fails the exposure test for every
    candidate, B0 included, because the hedge decays between rebalances: at a 21-session
    cadence the book carries several percent of factor exposure on the days before it is
    re-hedged, and no variant can change that, since all of them rebalance every 21
    sessions. The second reading applies the same ceilings to the worst day **right
    after trading**, which is the part the construction controls. Both are reported:
    the first is the rule as stated, the second is what separates the variants.
    """
    by_name = {row["variant"]: row for row in rows}
    eligible_all, rejected_all = _eligible(
        by_name, "exposure_max", "variance_share_max"
    )
    eligible_reb, rejected_reb = _eligible(
        by_name, "exposure_max_at_rebalance", "variance_share_max_at_rebalance"
    )
    eligible_rel, rejected_rel = _eligible_no_worse_than_baseline(by_name)
    return {
        "no_worse_than_baseline": {
            "eligible": eligible_rel,
            "rejected": rejected_rel,
            "winner": _winner(by_name, eligible_rel),
        },
        "as_written": {
            "eligible": eligible_all,
            "rejected": rejected_all,
            "winner": _winner(by_name, eligible_all),
        },
        "at_rebalance": {
            "eligible": eligible_reb,
            "rejected": rejected_reb,
            "winner": _winner(by_name, eligible_reb),
        },
        "drift_note": (
            "exposure_max is the worst day of the whole hold and the at_rebalance max "
            "the worst day right after trading; the difference is the hedge decaying "
            "between rebalances, which every variant shares: the cadence is fixed"
        ),
    }


def run(root: pathlib.Path, out: pathlib.Path) -> int:
    dates = sessions(root)
    logger.info(
        "%d sessions %s..%s, %d monthly rebalances",
        len(dates),
        dates[0].date(),
        dates[-1].date(),
        len(dates) // CADENCE,
    )
    market = icd.Market(root, [str(day.date()) for day in dates])
    alphas = AlphaSource(root)
    # One variant is ~2.5 minutes of builds; the partial file means an interruption
    # costs the variant it was in, not the ones already finished.
    partial = pathlib.Path(tempfile.gettempdir()) / f"{out.stem}_rows.partial.json"
    done: dict[str, dict[str, Any]] = {}
    if partial.exists():
        for row in json.loads(partial.read_text()):
            done[row["variant"]] = row
        logger.info("resuming with %d variant(s) already measured", len(done))
    rows: list[dict[str, Any]] = []
    baseline: dict[str, Any] | None = None
    for name, spec in VARIANTS.items():
        if name in done:
            row = done[name]
        else:
            row = run_variant(name, spec, root, dates, market, alphas, baseline)
            done[name] = row
            partial.write_text(json.dumps(list(done.values()), default=str))
        rows.append(row)
        if name == "B0":
            baseline = row
        logger.info(
            "%-10s turnover/reb %6.2f%% cost %6.1f bp/yr net %7.1f alpha %s "
            "expo max %.2f%% var share max %.1f%%",
            name,
            row["turnover_per_rebalance"] * 100.0,
            row["cost_bp"],
            row["net_bp"],
            f"{row.get('alpha_retained', 1.0):.1%}",
            row["exposure_max"] * 100.0,
            row["variance_share_max"] * 100.0,
        )
    payload = {
        "window": {
            "start": str(dates[0].date()),
            "end": str(dates[-1].date()),
            "sessions": len(dates),
            "years": round(len(dates) / TRADING_DAYS, 2),
            "cadence": CADENCE,
            "universe": (
                "frozen at the 2026-09-18 SPY archive, dated for every session: "
                "today's "
                "membership applied to the past, so P&L levels are indicative and the "
                "cross-variant comparison is the result"
            ),
        },
        "rows": rows,
        "decision": summarise(rows),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    logger.info("wrote %s", out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="churn study")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--root", required=True)
    run_parser.add_argument("--out", required=True)
    run_parser.set_defaults(
        func=lambda args: run(pathlib.Path(args.root).resolve(), pathlib.Path(args.out))
    )
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
