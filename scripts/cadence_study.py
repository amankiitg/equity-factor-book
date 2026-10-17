"""Cadence study: daily, weekly, fortnightly or monthly - and does a band change it?

Research only. Nothing here trades, sets a flag or writes a store: the target books
are built by the live construction itself (`live.evening_job.build_proposal`,
`store=False`, every flag unset, NAV fixed at 1,000,000) on a *copy* of the tree, and
the holding simulation is arithmetic on those books plus the tree's own returns.

    python scripts/cadence_study.py targets  --root /tmp/cadence/data \\
        --start 2024-01-02 --end 2026-10-02 --out /tmp/cadence/targets/pass
    python scripts/cadence_study.py simulate --root /tmp/cadence/data \\
        --targets /tmp/cadence/targets/pass1.jsonl --json /tmp/cadence/study.json

`targets` writes one JSON line per session: the kept (traded) book, the pre-floor full
book, and the numbers the build reports. The pre-floor book is the same build with the
floor's dollar and share minimums released to zero: "the full book still holds it"
means the sizing's own book, before the floor drops what cannot clear the minimum.

The costs are the same for every row, which is what makes the comparison mean
anything: half-spread by size decile and the commission from `efb.costs`, impact by
the square-root law `k * sigma * sqrt(dollar / adv)`, and borrow accrued on the short
gross every held day at `efb.costs.BORROW_RATE / 252`. The residual factor exposure is
measured against the tree's own design (`efb.race`), because a band or a hysteresis
rule can only break the hedge's neutrality by the weight it leaves off target.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import multiprocessing
import pathlib
import sys
from typing import Any

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cadence_study")

NAV = 1_000_000.0
CADENCES = (1, 5, 10, 21)
CURVE_CADENCES = (1, 2, 3, 5, 10, 21)
VARIANTS = ("V0", "V1", "V2")
BAND = 0.25
MINIMUM_LEG = 250.0
TRADING_DAYS = 252
VOL_WINDOW = 60

_ROOT: pathlib.Path | None = None


# ---------------------------------------------------------------- target books


def _book(manifest: dict[str, Any]) -> dict[str, float]:
    return {str(row["ticker"]): float(row["weight"]) for row in manifest["kept_book"]}


def _relaxed_floor() -> Any:
    """`registry.live_construction` with the floor's minimums at zero.

    The pre-floor full book is the sizing's own book: the floor drops every name that
    cannot clear the dollar or the share minimum, so a build with zero minimums keeps
    all of them. Patched rather than passed because the construction spec is read from
    the registry inside the build, and the patch lives in one worker process only.
    """
    from efb import registry

    original = registry.live_construction

    def zero_floor(reg: Any, version: Any) -> dict[str, Any]:
        spec = dict(original(reg, version))
        spec["dollar_floor"] = 0.0
        spec["share_floor"] = 0
        return spec

    return original, zero_floor


def _build_day(item: tuple[str, dict[str, float] | None]) -> dict[str, Any]:
    """One session's kept book, pre-floor full book and reported numbers."""
    from efb import registry
    from live import evening_job

    date, previous = item
    as_of = pd.Timestamp(date)
    prior = None if previous is None else pd.Series(previous, dtype=float).sort_index()
    manifest = evening_job.build_proposal(
        data_root=_ROOT, as_of=as_of, nav=NAV, store=False, previous=prior
    )
    original, zero_floor = _relaxed_floor()
    registry.live_construction = zero_floor
    try:
        full = evening_job.build_proposal(
            data_root=_ROOT, as_of=as_of, nav=NAV, store=False, previous=prior
        )
    finally:
        registry.live_construction = original
    return {
        "date": date,
        "kept": _book(manifest),
        "full": _book(full),
        "n_kept": int(manifest["n_kept"]),
        "n_full": int(full["n_kept"]),
        "kept_gross": float(manifest["kept_gross"]),
        "kept_vol": float(manifest["kept_achieved_annual_vol"]),
        "traded_notional": float(manifest["traded_notional"]),
    }


def _init_worker(root: str) -> None:
    global _ROOT
    _ROOT = pathlib.Path(root)


def _sessions(root: pathlib.Path, start: str, end: str) -> list[str]:
    frame = pd.read_parquet(root / "processed" / "returns.parquet")
    dates = pd.Index(frame.index.get_level_values("date")).unique().sort_values()
    window = dates[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))]
    return [str(pd.Timestamp(stamp).date()) for stamp in window]


def _moved(previous: dict[str, dict[str, float]], records: list[dict[str, Any]]) -> int:
    """How many sessions changed a weight versus the pass before (convergence)."""
    if not previous:
        return 0
    moved = 0
    for index, record in enumerate(records):
        if not index:
            continue
        before = previous.get(records[index - 1]["date"])
        if before is None:
            continue
        after = record["kept"]
        if set(before) != set(after) or any(
            abs(before[ticker] - after.get(ticker, 0.0)) > 1e-12 for ticker in before
        ):
            moved += 1
    return moved


def cmd_targets(args: argparse.Namespace) -> int:
    root = pathlib.Path(args.root).resolve()
    dates = _sessions(root, args.start, args.end)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    logger.info("%s sessions %s..%s", len(dates), dates[0], dates[-1])
    previous: dict[str, dict[str, float]] = {}
    for pass_number in range(args.passes):
        items: list[tuple[str, dict[str, float] | None]] = [
            (date, previous.get(dates[index - 1]) if index else None)
            for index, date in enumerate(dates)
        ]
        context = multiprocessing.get_context("fork")
        with context.Pool(
            args.workers, initializer=_init_worker, initargs=(str(root),)
        ) as pool:
            records = pool.map(_build_day, items, chunksize=1)
        path = out.parent / f"{out.name}{pass_number}.jsonl"
        with path.open("w") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")
        logger.info(
            "pass %d wrote %s; %d of %d session(s) moved versus the pass before",
            pass_number,
            path,
            _moved(previous, records),
            max(len(records) - 1, 1),
        )
        previous = {record["date"]: record["kept"] for record in records}
    return 0


# ------------------------------------------------------------------- simulation


def _load_targets(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with path.open() as handle:
        for line in handle:
            record = json.loads(line)
            records[record["date"]] = record
    return records


class Market:
    """Everything the simulation needs from the tree, read once."""

    def __init__(self, root: pathlib.Path, dates: list[str]) -> None:
        from efb import costs as costs_mod

        self.root = root
        frame = pd.read_parquet(root / "processed" / "returns.parquet")
        stamps = [pd.Timestamp(date) for date in dates]
        self.returns = frame["r"].unstack("ticker").sort_index().reindex(stamps)
        self.vol = self.returns.rolling(VOL_WINDOW, min_periods=20).std()
        prices = pd.read_parquet(root / "raw" / "prices.parquet")
        self.spread = costs_mod.spread_schedule(prices, root)
        self.adv = costs_mod.trailing_adv(prices)
        self._spread_median = float(self.spread.median())
        adv_clean = self.adv.dropna()
        self._adv_median = float(adv_clean.median()) if len(adv_clean) else 1e7
        self.impact_k = float(costs_mod.IMPACT_K)
        self.commission = float(costs_mod.COMMISSION)
        self.borrow_rate = float(costs_mod.BORROW_RATE)
        self._descriptors = pd.read_parquet(
            root / "models" / "XS-v1" / "descriptors.parquet"
        )
        self._codes_cache: Any = None
        self._z_cache: dict[pd.Timestamp, pd.DataFrame] = {}

    def cost(self, delta: dict[str, float], date: pd.Timestamp) -> tuple[float, float]:
        """Spread + commission + impact in dollars, and the traded notional."""
        if not delta:
            return 0.0, 0.0
        names = list(delta)
        spread = self.spread.reindex(names).fillna(self._spread_median)
        adv = np.maximum(self.adv.reindex(names).fillna(self._adv_median).to_numpy(float), 1.0)
        traded = np.abs(np.asarray([delta[name] for name in names], dtype=float)) * NAV
        sigma = self._sigma(names, date)
        spread_cost = float(np.sum((spread.to_numpy(float) + self.commission) * traded))
        impact = float(
            np.sum(self.impact_k * sigma * np.sqrt(traded / adv) * traded)
        )
        return spread_cost + impact, float(traded.sum())

    def _sigma(self, names: list[str], date: pd.Timestamp) -> np.ndarray:
        row = self.vol.loc[date] if date in self.vol.index else None
        values = (
            np.asarray([float(row.get(name, np.nan)) for name in names], dtype=float)
            if row is not None
            else np.full(len(names), np.nan)
        )
        fallback = float(self.vol.median().median() or 0.02)
        fallback = fallback if math.isfinite(fallback) and fallback > 0 else 0.02
        return np.where(np.isfinite(values), values, fallback)

    def borrow(self, held: dict[str, float]) -> float:
        short_gross = float(sum(-weight for weight in held.values() if weight < 0.0))
        return self.borrow_rate * short_gross * NAV / TRADING_DAYS

    def exposure(self, date: pd.Timestamp, weights: dict[str, float]) -> float | None:
        from efb import race

        names = sorted(weights)
        if not names:
            return None
        try:
            design = race._design_from_styles(self._z(date), names, self._codes())
        except Exception as exc:  # noqa: BLE001 - a missing design is reported, not fatal
            logger.warning("no design for %s: %s", date.date(), exc)
            return None
        vector = np.asarray([weights[name] for name in names], dtype=float)
        return float(np.abs(design.T @ vector).max())

    def _codes(self) -> Any:
        if self._codes_cache is None:
            from efb import race

            self._codes_cache = race._sector_codes(self.root)
        return self._codes_cache

    def _z(self, date: pd.Timestamp) -> pd.DataFrame:
        if date not in self._z_cache:
            day = self._descriptors.loc[
                pd.to_datetime(self._descriptors["date"]) == date
            ]
            self._z_cache[date] = day.pivot_table(
                index="ticker", columns="descriptor", values="value_z_orth"
            )
        if len(self._z_cache) > 16:
            for stale in list(self._z_cache)[:-8]:
                del self._z_cache[stale]
        return self._z_cache[date]


def _rebalance(
    held: dict[str, float], target: dict[str, float], full: dict[str, float], variant: str
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """The book after the rebalance, its legs, and the split by leg kind."""
    book: dict[str, float] = {}
    legs: dict[str, float] = {}
    split = {"entries": 0.0, "exits": 0.0, "resizes": 0.0}
    for ticker in sorted(set(held) | set(target)):
        now = held.get(ticker, 0.0)
        want = target.get(ticker, 0.0)
        entry = abs(now) < 1e-12
        closing = abs(want) < 1e-12
        if abs(want - now) * NAV < MINIMUM_LEG:
            book[ticker] = now
            continue
        if variant in ("V1", "V2") and not entry and not closing:
            if abs(want - now) < BAND * abs(want):
                book[ticker] = now
                continue
        if variant == "V2" and closing:
            kept = full.get(ticker, 0.0)
            if kept != 0.0 and (kept > 0.0) == (now > 0.0):
                book[ticker] = now
                continue
        book[ticker] = want
        legs[ticker] = want - now
        if entry:
            split["entries"] += abs(want - now)
        elif closing:
            split["exits"] += abs(want - now)
        else:
            split["resizes"] += abs(want - now)
    return {t: w for t, w in book.items() if abs(w) > 0.0}, legs, split


def _drift(held: dict[str, float], row: pd.Series) -> tuple[dict[str, float], float]:
    """Held weights after a session's returns, and the book's own return."""
    if not held:
        return {}, 0.0
    names = list(held)
    returns = np.nan_to_num(
        np.asarray([float(row.get(name, 0.0) or 0.0) for name in names], dtype=float)
    )
    weights = np.asarray([held[name] for name in names], dtype=float)
    portfolio = float(np.sum(weights * returns))
    grown = weights * (1.0 + returns)
    # The book is dollar-neutral with cash, so its weights are fractions of NAV and
    # NAV grows by the portfolio's own return: dividing by the sum of the grown
    # weights would divide by the net exposure, which is zero by construction. It
    # showed up as a 1,535x book on the first smoke run.
    scale = 1.0 + portfolio
    if abs(scale) < 1e-9:
        return dict(held), portfolio
    return {name: float(value) / scale for name, value in zip(names, grown)}, portfolio


def _simulate(
    records: dict[str, dict[str, Any]],
    market: Market,
    cadence: int,
    variant: str,
    exposure_every: int | None = 1,
) -> dict[str, Any]:
    dates = sorted(records)
    held: dict[str, float] = {}
    gross: list[float] = []
    costs: list[float] = []
    borrows: list[float] = []
    turnovers: list[float] = []
    split_total = {"entries": 0.0, "exits": 0.0, "resizes": 0.0}
    names_held: list[int] = []
    exposures: list[float] = []
    for index, date in enumerate(dates):
        stamp = pd.Timestamp(date)
        row = market.returns.loc[stamp] if stamp in market.returns.index else None
        portfolio = 0.0
        if index and row is not None and held:
            held, portfolio = _drift(held, row)
        gross.append(portfolio)
        if index % cadence == 0:
            record = records[date]
            book, legs, split = _rebalance(
                held,
                {t: float(w) for t, w in record["kept"].items()},
                {t: float(w) for t, w in record["full"].items()},
                variant,
            )
            cost, notional = market.cost(legs, stamp)
            costs.append(cost / NAV)
            turnovers.append(notional / NAV)
            for key in split_total:
                split_total[key] += split[key]
            held = book
            names_held.append(len(held))
            if exposure_every is not None and index % exposure_every == 0:
                value = market.exposure(stamp, held)
                if value is not None:
                    exposures.append(value)
        else:
            costs.append(0.0)
        borrows.append(market.borrow(held) / NAV)
    frame = pd.DataFrame(
        {"gross": gross, "cost": costs, "borrow": borrows},
        index=[pd.Timestamp(date) for date in dates],
    )
    frame["net"] = frame["gross"] - frame["cost"] - frame["borrow"]
    years = len(frame) / TRADING_DAYS
    bp = 1e4 / years
    net = float(frame["net"].sum()) * bp
    vol = float(frame["net"].std(ddof=1)) * math.sqrt(TRADING_DAYS)
    return {
        "cadence": cadence,
        "variant": variant,
        "sessions": len(frame),
        "years": years,
        "rebalances": len(turnovers),
        "turnover_per_rebalance": float(np.mean(turnovers)) if turnovers else 0.0,
        "turnover_per_year": float(np.sum(turnovers)) / years,
        "gross_bp": float(frame["gross"].sum()) * bp,
        "cost_bp": float(frame["cost"].sum()) * bp,
        "borrow_bp": float(frame["borrow"].sum()) * bp,
        "net_bp": net,
        "vol": vol,
        "sharpe": net / 1e4 / vol if vol > 0 else float("nan"),
        "names_held": float(np.mean(names_held)) if names_held else 0.0,
        "exposure_avg": float(np.mean(exposures)) if exposures else float("nan"),
        "exposure_max": float(np.max(exposures)) if exposures else float("nan"),
        "exposure_days": len(exposures),
        "split": split_total,
    }


def cmd_simulate(args: argparse.Namespace) -> int:
    root = pathlib.Path(args.root).resolve()
    global _ROOT
    _ROOT = root
    records = _load_targets(pathlib.Path(args.targets))
    dates = sorted(records)
    market = Market(root, dates)
    rows = []
    for cadence in CADENCES:
        for variant in VARIANTS:
            row = _simulate(records, market, cadence, variant)
            rows.append(row)
            logger.info(
                "%s k=%2d: net %8.1f bp/yr  sharpe %.2f  turnover/rebalance %.4f",
                variant,
                cadence,
                row["net_bp"],
                row["sharpe"],
                row["turnover_per_rebalance"],
            )
    curve = []
    for cadence in CURVE_CADENCES:
        row = _simulate(records, market, cadence, "V0", exposure_every=None)
        curve.append(
            {
                "cadence": cadence,
                "turnover_per_rebalance": row["turnover_per_rebalance"],
                "turnover_per_year": row["turnover_per_year"],
            }
        )
    daily = _simulate(records, market, 1, "V0", exposure_every=None)
    payload = {
        "window": {"start": dates[0], "end": dates[-1], "sessions": len(dates)},
        "targets": str(args.targets),
        "rows": rows,
        "curve": curve,
        "daily_split": daily["split"],
        "daily_turnover": daily["turnover_per_rebalance"],
    }
    pathlib.Path(args.json).write_text(json.dumps(payload, indent=2, sort_keys=True))
    logger.info("wrote %s", args.json)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="cadence study")
    sub = parser.add_subparsers(dest="command", required=True)
    targets = sub.add_parser("targets")
    targets.add_argument("--root", required=True)
    targets.add_argument("--start", required=True)
    targets.add_argument("--end", required=True)
    targets.add_argument("--out", required=True)
    targets.add_argument("--passes", type=int, default=2)
    targets.add_argument("--workers", type=int, default=4)
    targets.set_defaults(func=cmd_targets)
    simulate = sub.add_parser("simulate")
    simulate.add_argument("--root", required=True)
    simulate.add_argument("--targets", required=True)
    simulate.add_argument("--json", required=True)
    simulate.set_defaults(func=cmd_simulate)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
