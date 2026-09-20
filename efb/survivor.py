"""Task 4: the survivor restriction and the coverage gap, measured three ways.

No point-in-time GICS sector source is reachable, so this is a measurement
rather than a repair. Three views of the same distortion:

4a is the primary one and it is same-period by construction. A style-only model,
the market column plus the seven styles and no sector dummies, is estimated
twice over identical dates: once on the full panel and once on the 502
sector-mapped names the XS-v1 universe actually uses. Two universes, one period,
so the difference is the restriction rather than the calendar.

4b is the earlier proposal, kept and labelled: the 2020-onward subsample against
the full sample, which confounds universe with period.

4c is the direct quantity the others only imply: the excluded names' own return
and volatility differential against the included names, over 2010 to 2016 when
the excluded names were still a large share of the index.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from efb import probes
from efb.models import fundamental as fx

ROOT = Path(__file__).resolve().parents[1]
NW_LAG = 2
SUBSAMPLE_START = pd.Timestamp("2020-01-01")
EARLY_START = pd.Timestamp("2010-01-01")
EARLY_END = pd.Timestamp("2016-12-31")


@dataclass
class StyleOnlyResult:
    """One universe's style-only fit, day by day."""

    label: str
    dates: list[pd.Timestamp]
    factor_returns: pd.DataFrame
    r_squared: pd.Series
    specific_variance: pd.Series
    n_names: pd.Series

    @property
    def premia(self) -> pd.Series:
        return self.factor_returns.mean()

    @property
    def mean_names(self) -> float:
        """Mean names in the cross-section, so a universe mix-up is visible."""
        return float(self.n_names.mean())

    def newey_west_t(self) -> pd.Series:
        """Newey-West t statistic of each factor's mean return."""
        out = {}
        for column in self.factor_returns.columns:
            series = self.factor_returns[column].dropna()
            n_obs = len(series)
            if n_obs < 10:
                out[column] = np.nan
                continue
            mean = float(series.mean())
            centred = series - mean
            variance = float((centred**2).sum() / n_obs)
            for lag in range(1, NW_LAG + 1):
                weight = 1.0 - lag / (NW_LAG + 1.0)
                covariance = float(
                    (centred.iloc[lag:] * centred.iloc[:-lag]).sum() / n_obs
                )
                variance += 2.0 * weight * covariance
            se = np.sqrt(max(variance, 1e-18) / n_obs)
            out[column] = mean / se if se > 0 else np.nan
        return pd.Series(out)


def _style_columns(design_columns: list[str]) -> list[int]:
    keep = ["market", *[name for name in fx.STYLE_NAMES if name != "market"]]
    return [design_columns.index(name) for name in keep]


def raw_descriptors_cached(
    returns: pd.DataFrame,
    close: pd.DataFrame,
    volume: pd.DataFrame,
    cap: pd.DataFrame,
    proxy: pd.Series,
    root: str = "data",
) -> dict[str, pd.DataFrame]:
    """The raw descriptors, computed once and cached to parquet.

    The rolling windows are the expensive part of this sprint and they are a
    property of each name's own history, not of the universe, so they are
    computed on the panel and reused for every style-only run instead of being
    recomputed per universe.
    """
    cache = Path(root) / "raw" / "e4_raw_descriptors.parquet"
    if cache.exists():
        long = pd.read_parquet(cache)
        frames: dict[str, pd.DataFrame] = {}
        for name, block in long.groupby("descriptor"):
            frames[str(name)] = block.pivot(
                index="date", columns="ticker", values="value"
            )
        if frames:
            return frames
    frames = fx.raw_descriptors(
        returns=returns, close=close, volume=volume, market_cap=cap, proxy=proxy
    )
    pieces = []
    for name, frame in frames.items():
        if not isinstance(frame, pd.DataFrame):
            continue
        melted = frame.reset_index(names="date").melt(
            id_vars="date", var_name="ticker", value_name="value"
        )
        melted["descriptor"] = name
        pieces.append(melted)
    if pieces:
        cache.parent.mkdir(parents=True, exist_ok=True)
        pd.concat(pieces, ignore_index=True).to_parquet(cache, index=False)
    return frames


def style_only(
    label: str,
    inputs: dict[str, object],
    dates: list[pd.Timestamp] | None = None,
    universe: list[str] | None = None,
) -> StyleOnlyResult:
    """Fit the market plus seven styles, no sector dummies, on one universe.

    The raw descriptors are computed once, on the panel, because they are a
    property of each name's own history. What is universe specific is the
    cross-sectional standardization and the cross-section itself, and both are
    restricted to `universe` here: passing a universe only to the label was the
    first version of this function, and it silently fitted the full panel twice
    and printed two identical tables.
    """
    returns = inputs["returns"]
    close = inputs["close"]
    volume = inputs["volume"]
    shares = inputs["shares"]
    assert isinstance(returns, pd.DataFrame)
    assert isinstance(close, pd.DataFrame)
    assert isinstance(volume, pd.DataFrame)
    assert isinstance(shares, pd.DataFrame)

    cap = fx.market_cap(close, shares)
    proxy = fx.market_proxy(returns, cap)
    raw = raw_descriptors_cached(returns, close, volume, cap, proxy, root="data")
    usable = returns.notna()
    allowed = None if universe is None else set(universe)
    # `market` is the constant column of the design, not a descriptor: the six
    # style descriptors are the rest of STYLE_NAMES
    style_names = [name for name in fx.STYLE_NAMES if name != "market"]
    standard = {}
    for name in style_names:
        frame = raw[name]
        mask = frame.notna() & usable
        if allowed is not None:
            mask = mask & mask.columns.isin(allowed)
        standardized, _, _ = fx.standardize(frame, mask, cap)
        standard[name] = standardized
    orthogonalized = fx.orthogonalize(standard, fx.DEFAULT_ORTHOGONALIZATION)
    for name in style_names:
        if name in orthogonalized:
            standard[name] = orthogonalized[name]

    keep_dates = set(dates) if dates is not None else None
    sqrt_cap = np.sqrt(cap.where(cap > 0))
    rows: list[dict[str, object]] = []
    index = [date for date in returns.index if keep_dates is None or date in keep_dates]
    for date in index:
        day_returns = returns.loc[date].dropna()
        if allowed is not None:
            day_returns = day_returns[day_returns.index.isin(allowed)]
        if len(day_returns) == 0:
            continue
        columns = [1.0] * len(day_returns)
        block = {"market": pd.Series(columns, index=day_returns.index)}
        ok = pd.Series(True, index=day_returns.index)
        for name in style_names:
            series = standard[name].loc[date].reindex(day_returns.index)
            ok &= series.notna()
            block[name] = series
        if int(ok.sum()) < fx.MIN_NAMES:
            continue
        tickers = list(day_returns.index[ok])
        design = np.column_stack(
            [
                np.asarray(block[name].reindex(tickers), dtype=float)
                for name in ["market", *style_names]
            ]
        )
        target = day_returns.reindex(tickers).to_numpy(dtype=float)
        weights = sqrt_cap.loc[date].reindex(tickers).fillna(0.0).to_numpy(dtype=float)
        if weights.sum() <= 0:
            continue
        weights = weights / weights.mean()
        fit = fx.wls_fit(design, target, weights)
        coefficients = np.asarray(fit.factor_returns, dtype=float).reshape(-1)
        fitted = design @ coefficients
        residual = target - fitted
        average = float(np.average(target, weights=weights))
        total = float((weights * (target - average) ** 2).sum())
        row: dict[str, object] = {
            "date": date,
            "r_squared": (
                1.0 - float((weights * residual**2).sum()) / total
                if total > 0
                else np.nan
            ),
            "specific_variance": float(np.var(residual, ddof=1)),
            "n_names": len(tickers),
        }
        for position, name in enumerate(["market", *style_names]):
            row[f"f_{name}"] = float(coefficients[position])
        rows.append(row)
    frame = pd.DataFrame(rows).set_index("date").sort_index()
    return StyleOnlyResult(
        label=label,
        dates=list(frame.index),
        factor_returns=frame[[f"f_{name}" for name in ["market", *style_names]]].rename(
            columns=lambda column: column[2:]
        ),
        r_squared=frame["r_squared"],
        specific_variance=frame["specific_variance"],
        n_names=frame["n_names"],
    )


def restricted_names(inputs: dict[str, object]) -> tuple[list[str], list[str]]:
    """The panel split into the sector-mapped names and the excluded ones."""
    returns = inputs["returns"]
    sectors = inputs["sectors"]
    assert isinstance(returns, pd.DataFrame)
    assert isinstance(sectors, pd.Series)
    mapped = set(sectors.index)
    included = [name for name in returns.columns if name in mapped]
    excluded = [name for name in returns.columns if name not in mapped]
    return included, excluded


def excluded_name_differential(
    inputs: dict[str, object], membership: pd.DataFrame | None = None
) -> pd.DataFrame:
    """4c: the excluded names' return and volatility against the included ones."""
    from efb import hygiene

    returns = inputs["returns"]
    assert isinstance(returns, pd.DataFrame)
    clean = hygiene.clean_returns(
        pd.read_parquet(ROOT / "data" / "processed" / "returns.parquet")
    ).unstack("ticker")
    included, excluded = restricted_names(inputs)
    window = clean.loc[(clean.index >= EARLY_START) & (clean.index <= EARLY_END)]
    rows: list[dict[str, object]] = []
    for label, names in (
        ("included, in the sector file", included),
        ("excluded, outside it", excluded),
    ):
        block = window[[name for name in names if name in window.columns]]
        rows.append(
            {
                "group": label,
                "names": block.shape[1],
                "days": len(block),
                "mean_daily_return": float(block.mean(axis=1).mean()),
                "annualized_vol": float(
                    block.mean(axis=1).std(ddof=1) * np.sqrt(252.0)
                ),
                "annualized_mean": float(block.mean(axis=1).mean() * 252.0),
                "cross_sectional_vol_mean": float(
                    block.std(ddof=1).mean() * np.sqrt(252.0)
                ),
            }
        )
    frame = pd.DataFrame(rows)
    frame["differential_annualized"] = (
        frame["annualized_mean"] - frame.loc[0, "annualized_mean"]
    )
    return frame


def run(data_root: Path | None = None) -> dict[str, object]:
    """4a, 4b and 4c, printed and returned."""
    root = ROOT / "data" if data_root is None else Path(data_root)
    inputs = probes.load_panel(root)
    returns = inputs["returns"]
    assert isinstance(returns, pd.DataFrame)
    # the replication grid: XS-v1's own stored month ends, so both universes are
    # fitted on exactly the same dates
    descriptors = pd.read_parquet(root / "models" / "XS-v1" / "descriptors.parquet")
    dates = sorted(descriptors["date"].drop_duplicates())
    dates = [date for date in dates if date in returns.index]

    included, excluded = restricted_names(inputs)
    panel_result = style_only("panel_825", inputs, dates)
    mapped_result = style_only("mapped_502", inputs, dates, universe=included)
    if panel_result.mean_names == mapped_result.mean_names:
        raise RuntimeError(
            "both universes have the same cross-section: the restriction is not "
            "being applied, so the comparison below would be one fit printed twice"
        )

    print("### Task 4a: style-only model, two universes, identical dates")
    print(
        f"dates {len(panel_result.dates)} from {panel_result.dates[0].date()} to "
        f"{panel_result.dates[-1].date()}"
    )
    overlap = panel_result.factor_returns.join(
        mapped_result.factor_returns, lsuffix="_panel", rsuffix="_mapped", how="inner"
    ).dropna()
    correlations = {
        name: float(overlap[f"{name}_panel"].corr(overlap[f"{name}_mapped"]))
        for name in ["market", *fx.STYLE_NAMES]
    }
    comparison = pd.DataFrame(
        {
            "correlation_panel_vs_mapped": correlations,
            "premium_panel": panel_result.premia,
            "premium_mapped": mapped_result.premia,
            "t_panel": panel_result.newey_west_t(),
            "t_mapped": mapped_result.newey_west_t(),
            "mean_r_squared_panel": panel_result.r_squared.mean(),
            "mean_r_squared_mapped": mapped_result.r_squared.mean(),
        }
    )
    comparison["premium_difference"] = (
        comparison["premium_panel"] - comparison["premium_mapped"]
    )
    print(comparison.round(6).to_string())
    print()
    print(
        f"mean cross-sectional R squared: panel {panel_result.r_squared.mean():.6f}, "
        f"mapped {mapped_result.r_squared.mean():.6f}"
    )
    print(
        f"mean names in the cross-section: panel {panel_result.mean_names:.1f}, "
        f"mapped {mapped_result.mean_names:.1f}"
    )
    print(
        f"mean specific variance: panel {panel_result.specific_variance.mean():.10e}, "
        f"mapped {mapped_result.specific_variance.mean():.10e}"
    )
    print(
        f"names per date: panel {len(included) + len(excluded)}, "
        f"mapped {len(included)}, excluded {len(excluded)}"
    )

    print()
    print("### Task 4b: 2020 onward against the full sample, universe and period")
    for label, result in (("panel_825", panel_result), ("mapped_502", mapped_result)):
        frame = result.factor_returns
        late = result.r_squared[result.r_squared.index >= SUBSAMPLE_START]
        early = result.r_squared[result.r_squared.index < SUBSAMPLE_START]
        late_premia = frame[frame.index >= SUBSAMPLE_START].mean()
        print(
            f"{label}: R squared 2020+ {late.mean():.6f} against before "
            f"{early.mean():.6f}, premium correlation "
            f"{late_premia.corr(frame.mean()):.4f}"
        )

    print()
    print("### Task 4c: the excluded names themselves, 2010 to 2016")
    differential = excluded_name_differential(inputs)
    print(differential.round(6).to_string(index=False))

    stored = comparison.reset_index(names="factor")
    stored.to_parquet(root / "eval" / "xs_survivor_measurement.parquet", index=False)
    differential.to_parquet(
        root / "eval" / "xs_survivor_excluded_names.parquet", index=False
    )
    pd.DataFrame(
        {
            "universe": ["panel_825", "mapped_502"],
            "mean_r_squared": [
                panel_result.r_squared.mean(),
                mapped_result.r_squared.mean(),
            ],
            "mean_specific_variance": [
                panel_result.specific_variance.mean(),
                mapped_result.specific_variance.mean(),
            ],
            "dates": [len(panel_result.dates), len(mapped_result.dates)],
            # the names actually in the cross-section on an average date: the
            # evidence that the restriction was applied at all
            "mean_names": [panel_result.mean_names, mapped_result.mean_names],
        }
    ).to_parquet(root / "eval" / "xs_survivor_universe_summary.parquet", index=False)
    return {
        "correlations": correlations,
        "mean_r_squared": {
            "panel": float(panel_result.r_squared.mean()),
            "mapped": float(mapped_result.r_squared.mean()),
        },
        "mean_specific_variance": {
            "panel": float(panel_result.specific_variance.mean()),
            "mapped": float(mapped_result.specific_variance.mean()),
        },
        "premia": comparison[
            ["premium_panel", "premium_mapped", "t_panel", "t_mapped"]
        ],
        "differential": differential,
        "min_style_correlation": float(min(correlations.values())),
    }
