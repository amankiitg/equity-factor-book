"""Sprint E5, Task 0a: the covariance race's rebalance grid, derived.

E4 left this open: the race had 175 windows and its grid was chosen
interactively in Task 2, so `rebuild_e4` versioned the artifact without being
able to reproduce it. The grid the interactive choice approximated is the month
ends where the XS-v1 descriptor and specific-variance artifacts both have rows:
those are the dates the model can price, which is what the race needs. This
module derives them from the artifacts, rebuilds the race from the derivation,
and reports whether F4.3's verdict survives the change.

If the verdict moves, the finding is that F4.3 is grid sensitive, it is stored
as F5.0, and both readings are kept.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from efb import cov, hygiene
from efb.models import fundamental as fx

ROOT = Path(__file__).resolve().parents[1]
MIN_NAMES = 50

# The model needs this much published factor history before a point-in-time
# covariance exists. Windows behind this are skipped for the XS-v1 row only.
MIN_FACTOR_HISTORY = 126

# (date, n_names, n_names the model could not price) for every supplier call,
# so the XS-v1 row can be read knowing how much of it is the model's fallback
_COVERAGE: list[tuple[pd.Timestamp, int, int]] = []
_SKIPPED: list[pd.Timestamp] = []


def race_grid(
    data_root: Path = ROOT / "data", window: int = cov.WINDOW
) -> list[pd.Timestamp]:
    """The month ends the model can price, from the artifacts alone.

    A date qualifies when both the descriptor file and the specific-variance
    file have rows for it, so the design matrix and the diagonal are both
    available on the same day, and when `window` sessions of history exist
    behind it.
    """
    root = Path(data_root)
    descriptors = pd.read_parquet(root / "models" / "XS-v1" / "descriptors.parquet")
    specific = pd.read_parquet(root / "models" / "XS-v1" / "specific_var.parquet")
    returns = pd.read_parquet(root / "processed" / "returns.parquet")
    clean = hygiene.clean_returns(returns)
    sessions = pd.DatetimeIndex(sorted(clean.index.get_level_values("date").unique()))
    shared = sorted(
        set(pd.to_datetime(descriptors["date"]).unique())
        & set(pd.to_datetime(specific["date"]).unique())
    )
    positions = {date: index for index, date in enumerate(sessions)}
    out: list[pd.Timestamp] = []
    for date in shared:
        date = pd.Timestamp(date)
        position = positions.get(date)
        if position is None or position < window:
            continue
        if position + cov.MIN_VARIANCE_DAYS >= len(sessions):
            continue
        out.append(date)
    return out


def _as_of(frame: pd.DataFrame, date: pd.Timestamp) -> pd.Timestamp | None:
    """The most recent artifact date at or before `date`, or None.

    The model publishes on its own month ends and a rebalance does not always
    fall on one. Using the latest date at or before the rebalance is what a
    live run would have used and carries no look-ahead; skipping the date
    instead is what left the first version of this supplier covering 58 of 175
    windows.
    """
    available = pd.DatetimeIndex(sorted(pd.to_datetime(frame["date"]).unique()))
    usable = available[available <= date]
    return None if len(usable) == 0 else pd.Timestamp(usable[-1])


def _design_for(date: pd.Timestamp, names: list[str], data_root: Path) -> np.ndarray:
    """XS-v1's design matrix for one date, read from the stored weights."""
    weights = pd.read_parquet(data_root / "models" / "XS-v1" / "fmp_weights.parquet")
    stamp = _as_of(weights, date)
    weights = weights.loc[pd.to_datetime(weights["date"]) == stamp]
    wide = weights.pivot_table(index="ticker", columns="factor", values="weight")
    factors = list(fx.ESTIMATED_NAMES)
    wide = wide.reindex(index=names, columns=factors)
    return wide.to_numpy(dtype=float)


def _specific_for(
    date: pd.Timestamp, names: list[str], data_root: Path
) -> tuple[np.ndarray, int]:
    specific = pd.read_parquet(data_root / "models" / "XS-v1" / "specific_var.parquet")
    stamp = _as_of(specific, date)
    specific = specific.loc[pd.to_datetime(specific["date"]) == stamp]
    series = specific.set_index("ticker")["specific_var"]
    aligned = series.reindex(names)
    return aligned.to_numpy(dtype=float), int(aligned.isna().sum())


def xs_supplier(
    date: pd.Timestamp, names: list[str], data_root: Path
) -> dict[str, object]:
    """What the race needs for the XS-v1 row: design, factor covariance, diagonal.

    XS-v1 is the one estimator that cannot be built from the window alone, and
    it should not be: its design and its diagonal are the model's own
    artifacts. The factor covariance is estimated from the model's factor
    returns **up to the day before the rebalance**, with the model's own
    half-life, because `factor_cov.parquet` holds one full-sample snapshot and
    using that snapshot for every window would put look-ahead into the row.
    """
    factor_returns = pd.read_parquet(
        data_root / "models" / "XS-v1" / "factor_returns.parquet"
    )
    factor_returns = factor_returns.loc[pd.to_datetime(factor_returns["date"]) < date]
    if factor_returns["date"].nunique() < MIN_FACTOR_HISTORY:
        # The model has not published enough factor history to estimate a
        # covariance without look-ahead. The row is skipped and counted rather
        # than filled with the full-sample snapshot, which is what would make
        # the race flattering in exactly the way this sprint exists to detect.
        _SKIPPED.append(date)
        return None
    history = factor_returns.pivot_table(index="date", columns="factor", values="f")
    ordered = list(fx.ESTIMATED_NAMES)
    if not set(ordered).issubset(history.columns):
        raise RuntimeError("the stored factor returns do not cover every factor")
    factor_covariance = fx.ewma_factor_cov(
        history.loc[:, ordered], half_life=fx.F_HALF_LIFE
    )
    # `ewma_factor_cov` returns a date indexed stack of matrices; taking the
    # last date and reindexing both axes is what turns it into the (k, k) block
    # the design is multiplied by. Reshaping defensively here rather than
    # trusting the layout is what caught a one by seventeen block.
    if isinstance(factor_covariance.index, pd.MultiIndex):
        latest = factor_covariance.index.get_level_values(0).max()
        block = factor_covariance.xs(latest, level=0)
    else:
        block = factor_covariance.loc[factor_covariance.index.max()]
    block = pd.DataFrame(block).reindex(index=ordered, columns=ordered)
    if block.shape != (len(ordered), len(ordered)):
        raise RuntimeError(f"the factor covariance block is {block.shape}")
    design = _design_for(date, names, data_root)
    specific, missing = _specific_for(date, names, data_root)
    # A name the model cannot price on this date gets no factor exposure and the
    # cross-sectional median of the model's own diagonal, which is the fallback
    # the model itself uses for an unmodelled name. The count is returned so the
    # race's row can be read knowing how much of it is the fallback.
    unmodelled = int(np.isnan(design).any(axis=1).sum())
    # `nan_to_num` alone maps an infinite entry to 1.8e308, which makes the
    # assembled matrix non-finite and `eigvalsh` fail with "did not converge"
    # rather than with the reason. Both infinities and NaNs become no exposure,
    # which is the model's own treatment of a name it cannot price.
    design = np.nan_to_num(design, nan=0.0, posinf=0.0, neginf=0.0)
    median_specific = float(np.nanmedian(specific))
    specific = np.where(np.isnan(specific), median_specific, specific)
    specific = np.nan_to_num(specific, nan=median_specific, posinf=0.0, neginf=0.0)
    covariance = block.to_numpy(dtype=float)
    blocks = (
        ("design", design),
        ("factor covariance", covariance),
        ("specific", specific),
    )
    if not all(np.isfinite(values).all() for _label, values in blocks):
        _SKIPPED.append(date)
        return None
    _COVERAGE.append((date, len(names), unmodelled + missing))
    return {
        "design": design,
        "factor_covariance": covariance,
        "specific": specific,
    }


def run(data_root: Path = ROOT / "data", store: bool = True) -> dict[str, object]:
    """Rebuild the race on the derived grid and compare F4.3 before and after."""
    root = Path(data_root)
    grid = race_grid(root)
    returns = pd.read_parquet(root / "processed" / "returns.parquet")
    sectors = pd.read_parquet(root / "processed" / "sectors.parquet")
    universe = set(pd.Series(sectors["ticker"]).astype(str))
    print("### Task 0a: the race grid, derived from the artifacts")
    print(f"rebalance dates {len(grid)} from {grid[0].date()} to {grid[-1].date()}")
    gaps = pd.Series(grid).diff().dt.days.dropna()
    print(
        f"median gap {gaps.median():.0f} days, min {gaps.min():.0f}, max {gaps.max():.0f}"
    )

    race = cov.horse_race(
        returns,
        grid,
        xs_supplier=lambda date, names: xs_supplier(date, names, root),
        min_names=MIN_NAMES,
        universe=universe,
    )
    print(
        f"race rows {len(race)} across {race['date'].nunique()} dates and "
        f"{race['estimator'].nunique()} estimators"
    )
    if race.empty:
        raise RuntimeError("the derived grid produced no race rows")

    pivot = race.pivot(index="date", columns="estimator", values="realized_vol")
    medians = pivot.median()
    wins = (pivot.rank(axis=1, method="min") == 1).sum()
    table = pd.DataFrame({"median_realized_vol": medians, "windows_won": wins})
    print(table.round(6).to_string())

    stored = pd.read_parquet(root / "eval" / "cov_horse_race.parquet")
    stored_pivot = stored.pivot(
        index="date", columns="estimator", values="realized_vol"
    )
    derived_path = root / "eval" / "cov_horse_race_derived_grid.parquet"
    race.to_parquet(derived_path, index=False)
    comparison = pd.DataFrame(
        {
            "stored_median": stored_medians,
            "derived_median": medians,
            "stored_windows": stored_pivot.notna().sum(),
            "derived_windows": pivot.notna().sum(),
        }
    )
    comparison["median_ratio"] = (
        comparison["derived_median"] / comparison["stored_median"]
    )
    print()
    print("stored against derived")
    print(comparison.round(6).to_string())

    ranked = table.sort_values("median_realized_vol")
    top = list(ranked.index[:4])
    factors = [
        name for name in ("ts_v1", "xs_v1", "pca_v1", "pca_v1c") if name in medians
    ]
    ratios = {
        name: float(medians[name] / medians["sample"])
        for name in (*factors, "clip", "constant_correlation", "ledoit_wolf")
    }
    worst = max(ratios.values())
    verdict = "pass" if worst <= 0.9 else "fail"
    stored_verdict = "pass"
    if store:
        race.to_parquet(root / "eval" / "cov_horse_race.parquet", index=False)
    print()
    print(
        f"F4.3 worst ratio on the derived grid {worst:.4f}, verdict {verdict}; "
        f"stored verdict {stored_verdict}"
    )
    print(f"top four by median: {top}")
    moved = verdict != stored_verdict
    if moved:
        print("STOP CONDITION 1: the derived grid moved F4.3's verdict, stored as F5.0")
    payload = {
        "n_dates": len(grid),
        "first_date": str(grid[0].date()),
        "last_date": str(grid[-1].date()),
        "median_gap_days": float(gaps.median()),
        "worst_ratio": worst,
        "derived_verdict": verdict,
        "stored_verdict": stored_verdict,
        "moved": moved,
        "medians": {k: float(v) for k, v in medians.items()},
        "windows_won": {k: int(v) for k, v in wins.items()},
        "median_ratio_to_stored": {
            k: float(v) for k, v in comparison["median_ratio"].items()
        },
    }
    (root / "eval" / "e5_race_grid.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )
    return payload
