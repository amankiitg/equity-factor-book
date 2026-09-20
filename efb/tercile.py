"""Task 3: where the momentum book's predicted risk comes from, and where it misses.

Sprint E4. The momentum long/short book's monthly bias statistic is 0.6664
against an 0.8 to 1.25 band, and the E3 tercile diagnostic located the miss in
the factor covariance. This module runs five measurements on stored artifacts.
None of them changes XS-v1.

- 3a decomposes predicted variance by source inside each exposure tercile, so
  the flat prediction can be attributed to a factor, a group of factors or the
  diagonal.
- 3b is the confound check: tercile membership by year and the market factor's
  realized volatility in each tercile, because a falling realized book variance
  could be a calm-period effect rather than an exposure effect.
- 3c tests the orthogonality assumption directly. The model adds the factor and
  specific variances, which is only right if their components are uncorrelated;
  realized total volatility below the predicted factor part alone would refute
  it.
- 3d sweeps the factor covariance half-life, reported as secondary.
- 3e projects the book's weights onto the leading residual eigenvectors. The
  residual PCA found a largest eigenvalue of 22.303 against an edge of 3.952,
  which is a large amount of common structure in the specific returns. If a few
  residual directions carry most of the book's specific variance, then the
  diagonal D understates concentrated risk and the residual audit, 3a and 3c
  are one finding rather than three.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from efb import risk
from efb.models import fundamental as fx
from efb.models import statistical as st

ROOT = Path(__file__).resolve().parents[1]
BOOK = "seed_mom_ls"
FORWARD = 21
HALF_LIVES = (21, 42, 90)
STYLE_NAMES = tuple(fx.STYLE_NAMES)


@dataclass
class TercileInputs:
    """Everything the five measurements read, assembled once."""

    dates: list[pd.Timestamp]
    weights: dict[pd.Timestamp, pd.Series]
    design: dict[pd.Timestamp, pd.DataFrame]
    factor_returns: pd.DataFrame
    factor_covariance: dict[pd.Timestamp, np.ndarray]
    specific_variance: dict[pd.Timestamp, pd.Series]
    forward: dict[pd.Timestamp, pd.DataFrame]
    specific_returns: pd.DataFrame
    terciles: pd.Series
    bias: pd.DataFrame
    data_root: Path

    @property
    def factor_names(self) -> list[str]:
        return list(fx.FACTOR_NAMES)


def load_inputs(data_root: Path | None = None) -> TercileInputs:
    """Assemble the book weights, the design and the stored variance artifacts."""
    root = ROOT / "data" if data_root is None else Path(data_root)
    descriptors = pd.read_parquet(root / "models" / "XS-v1" / "descriptors.parquet")
    specific_var = pd.read_parquet(root / "models" / "XS-v1" / "specific_var.parquet")
    factor_returns = pd.read_parquet(
        root / "models" / "XS-v1" / "factor_returns.parquet"
    )
    specific_returns = pd.read_parquet(
        root / "models" / "XS-v1" / "specific_returns.parquet"
    )
    sectors = pd.read_parquet(root / "processed" / "sectors.parquet")
    returns = pd.read_parquet(root / "processed" / "returns.parquet")
    exposure = pd.read_parquet(root / "eval" / "xs_exposure_timeseries.parquet")
    bias = pd.read_parquet(root / "eval" / "xs_bias.parquet")

    names_all = list(fx.FACTOR_NAMES)
    sector_of = sectors.set_index("ticker")["gics_sector"]
    styles = [name for name in names_all if not name.startswith("sector")]
    dummies = {
        name: {
            sector
            for sector, code in fx.SECTOR_CODES.items()
            if code == int(name.split("_")[1])
        }
        for name in names_all
        if name.startswith("sector")
    }
    design_by_date = {
        date: frame.pivot(index="ticker", columns="descriptor", values="value_z_orth")
        for date, frame in descriptors.groupby("date")
    }
    specific_by_date = {
        date: frame.set_index("ticker")["specific_var"]
        for date, frame in specific_var.groupby("date")
    }
    factor_wide = factor_returns.pivot(index="date", columns="factor", values="f").loc[
        :, names_all
    ]
    clean = st.clean_wide(returns)

    book_dates = sorted(
        date
        for date in specific_by_date
        if date in design_by_date and date in factor_wide.index
    )
    book_weights: dict[pd.Timestamp, pd.Series] = {}
    designs: dict[pd.Timestamp, pd.DataFrame] = {}
    covariances: dict[pd.Timestamp, np.ndarray] = {}
    specifics: dict[pd.Timestamp, pd.Series] = {}
    forwards: dict[pd.Timestamp, pd.DataFrame] = {}
    residual_weight: dict[pd.Timestamp, float] = {}
    momentum_exposure = (
        exposure.loc[(exposure["book"] == BOOK) & (exposure["factor"] == "momentum")]
        .set_index("date")["exposure"]
        .sort_index()
    )
    book_bias = bias.loc[bias["book"] == BOOK].set_index("date").sort_index()
    ranked = momentum_exposure.reindex(book_bias.index).rank(method="first")
    total = len(book_bias)
    labels = pd.Series("low", index=book_bias.index)
    labels[ranked > total / 3.0] = "mid"
    labels[ranked > 2.0 * total / 3.0] = "high"

    for date in book_dates:
        if date not in momentum_exposure.index:
            continue
        weights = risk.load_book(root / "portfolios" / f"{BOOK}.parquet", date)
        held = [name for name in weights.index if not np.isclose(weights[name], 0.0)]
        frame_all = design_by_date[date]
        specific_all = specific_by_date[date]
        # a held name with no descriptor row is outside the model, which E3
        # records as residual weight rather than dropping the date
        names = [
            name
            for name in held
            if name in frame_all.index and name in specific_all.index
        ]
        if len(names) < 10:
            continue
        frame = frame_all.reindex(index=names, columns=styles)
        specific = specific_all
        if frame.isna().to_numpy().any():
            continue
        kept_weight = float(weights.reindex(names).abs().sum())
        blocks = [frame.to_numpy(dtype=float)]
        for wanted in dummies.values():
            blocks.append(
                np.array(
                    [[1.0 if sector_of.get(name) in wanted else 0.0] for name in names]
                )
            )
        design = pd.DataFrame(
            np.column_stack(blocks), index=names, columns=names_all, dtype=float
        )
        window = factor_wide.loc[:date]
        covariances[date] = (
            fx.ewma_factor_cov(window).loc[names_all, names_all].to_numpy(dtype=float)
        )
        designs[date] = design
        book_weights[date] = weights.reindex(names).fillna(0.0)
        residual_weight[date] = float(weights.reindex(held).abs().sum() - kept_weight)
        specifics[date] = specific.reindex(names)
        forward = clean.loc[date:].iloc[1 : FORWARD + 1, :]
        forwards[date] = forward.loc[:, forward.notna().all()]

    dates = sorted(
        date
        for date in (set(designs) & set(forwards) & set(specifics))
        if date in labels.index
    )
    return TercileInputs(
        dates=dates,
        weights=book_weights,
        design=designs,
        factor_returns=factor_wide,
        factor_covariance=covariances,
        specific_variance=specifics,
        forward=forwards,
        specific_returns=specific_returns,
        terciles=labels,
        bias=book_bias,
        data_root=root,
    )


def _book_vector(
    inputs: TercileInputs, date: pd.Timestamp
) -> tuple[np.ndarray, list[str]]:
    weights = inputs.weights[date]
    return weights.to_numpy(dtype=float), list(weights.index)


def predicted_variance_by_source(inputs: TercileInputs) -> pd.DataFrame:
    """3a: predicted variance split into every factor and the diagonal."""
    rows: list[dict[str, object]] = []
    names_all = inputs.factor_names
    for date in inputs.dates:
        weights, _ = _book_vector(inputs, date)
        design = inputs.design[date].to_numpy(dtype=float)
        covariance = inputs.factor_covariance[date]
        specific = inputs.specific_variance[date].to_numpy(dtype=float)
        exposure = design.T @ weights
        factor_part = exposure @ covariance @ exposure
        contributions = exposure * (covariance @ exposure)
        idio = float(np.sum(weights**2 * specific))
        total = factor_part + idio
        row: dict[str, object] = {
            "date": date,
            "tercile": inputs.terciles.get(date, "unknown"),
            "predicted_variance": total,
            "predicted_vol": np.sqrt(total * 252.0),
            "factor_variance": factor_part,
            "idio_variance": idio,
            "momentum_variance": float(contributions[names_all.index("momentum")]),
            "market_variance": float(contributions[names_all.index("market")]),
            "momentum_share": float(contributions[names_all.index("momentum")] / total),
            "style_share": float(contributions[: len(STYLE_NAMES)].sum() / total),
            "sector_share": float(contributions[len(STYLE_NAMES) :].sum() / total),
            "idio_share": idio / total,
            "factor_share": factor_part / total,
        }
        for position, name in enumerate(names_all):
            row[f"contribution_{name}"] = float(contributions[position])
        rows.append(row)
    return pd.DataFrame(rows)


def tercile_confound(inputs: TercileInputs) -> pd.DataFrame:
    """3b: tercile membership by year, and the market factor's volatility.

    The membership table is the part that matters: if the high-exposure
    tercile is mostly 2015 to 2020 and the low one is mostly 2021 to 2026, then
    the tercile comparison is a period comparison wearing an exposure label.
    The market volatility columns are the same question in numbers.
    """
    market = inputs.factor_returns["market"]
    membership = pd.Series(
        {date: inputs.terciles.get(date, "unknown") for date in inputs.dates}
    )
    rows: list[dict[str, object]] = []
    for tercile in ("low", "mid", "high"):
        dates = [date for date in inputs.dates if membership.get(date) == tercile]
        if not dates:
            continue
        forward_sessions = [
            session for date in dates for session in inputs.forward[date].index
        ]
        rows.append(
            {
                "tercile": tercile,
                "months": len(dates),
                "first_month": min(dates),
                "last_month": max(dates),
                "mean_year": float(np.mean([date.year for date in dates])),
                "market_vol_own_month": float(
                    market.reindex(dates).std(ddof=1) * np.sqrt(252.0)
                ),
                "market_vol_forward": float(
                    market.reindex(forward_sessions).std(ddof=1) * np.sqrt(252.0)
                ),
                "book_realized_vol": float(
                    np.mean([stored_realized_vol(inputs, date) for date in dates])
                ),
                "book_predicted_vol": float(
                    np.mean([stored_predicted_vol(inputs, date) for date in dates])
                ),
                "book_realized_vol_covariance_form": float(
                    np.sqrt(252.0)
                    * np.mean([_book_realized_vol(inputs, date) for date in dates])
                ),
            }
        )
    by_tercile = pd.DataFrame(rows)
    yearly = pd.DataFrame(
        {
            "tercile": [
                tercile for tercile in ("low", "mid", "high") for _ in range(1)
            ],
        }
    ).drop(columns=["tercile"])
    year_rows: list[dict[str, object]] = []
    for tercile in ("low", "mid", "high"):
        dates = [date for date in inputs.dates if membership.get(date) == tercile]
        for year, group in pd.Series(dates).groupby(pd.Series(dates).dt.year):
            year_rows.append(
                {
                    "tercile": tercile,
                    "year": int(year),
                    "months_in_year": int(len(group)),
                }
            )
    yearly = pd.DataFrame(year_rows)
    return yearly.merge(by_tercile, on="tercile", how="left")


def stored_realized_vol(inputs: TercileInputs, date: pd.Timestamp) -> float:
    """The F3.6 realized volatility of the book on that date.

    E3 defines it as the standard deviation of the book's own daily return
    series over the forward horizon and then multiplied by sqrt(252), which is
    not the same number as `sqrt(w' S w)` on the names with complete data. The
    bias statistic is written on the stored definition, so every Task 3
    measurement that talks about realized volatility quotes it rather than a
    second definition, and the covariance form is kept as a diagnostic column.
    """
    if date in inputs.bias.index:
        return float(inputs.bias.loc[date, "realized_vol_ann"])
    return float("nan")


def stored_predicted_vol(inputs: TercileInputs, date: pd.Timestamp) -> float:
    if date in inputs.bias.index:
        return float(inputs.bias.loc[date, "predicted_vol_ann"])
    return float("nan")


def _book_realized_vol(inputs: TercileInputs, date: pd.Timestamp) -> float:
    weights = inputs.weights[date]
    forward = inputs.forward[date]
    names = [name for name in weights.index if name in forward.columns]
    if len(names) < 2:
        return float("nan")
    w = weights[names].to_numpy(dtype=float)
    returns = forward[names].to_numpy(dtype=float)
    return float(np.sqrt(w @ np.cov(returns, rowvar=False, ddof=1) @ w))


def orthogonality_test(inputs: TercileInputs) -> pd.DataFrame:
    """3c: the realized covariance between the factor and specific components.

    The model adds the two variances, which is right only if the components are
    uncorrelated. The test builds both series over the forward window: the
    factor component from the book's exposures times the realized factor
    returns, the specific component from the book's weights times the realized
    specific returns.
    """
    specific_wide = inputs.specific_returns.pivot(
        index="date", columns="ticker", values="specific_return"
    )
    rows: list[dict[str, object]] = []
    for date in inputs.dates:
        weights, names = _book_vector(inputs, date)
        design = inputs.design[date].to_numpy(dtype=float)
        exposure = design.T @ weights
        forward = inputs.forward[date]
        factor_block = inputs.factor_returns.reindex(forward.index).to_numpy(
            dtype=float
        )
        factor_component = factor_block @ exposure
        block = specific_wide.reindex(index=forward.index, columns=names).fillna(0.0)
        specific_component = block.to_numpy(dtype=float) @ weights
        covariance = float(np.cov(factor_component, specific_component, ddof=1)[0, 1])
        var_factor = float(np.var(factor_component, ddof=1))
        var_specific = float(np.var(specific_component, ddof=1))
        var_total = float(np.var(factor_component + specific_component, ddof=1))
        rows.append(
            {
                "date": date,
                "tercile": inputs.terciles.get(date, "unknown"),
                "var_factor_component": var_factor,
                "var_specific_component": var_specific,
                "covariance": covariance,
                "var_total": var_total,
                "sum_without_covariance": var_factor + var_specific,
                "correlation": (
                    covariance / np.sqrt(var_factor * var_specific)
                    if var_factor > 0 and var_specific > 0
                    else np.nan
                ),
            }
        )
    frame = pd.DataFrame(rows)
    frame["covariance_share_of_total"] = frame["covariance"] / frame["var_total"]
    return frame


def half_life_sweep(inputs: TercileInputs) -> pd.DataFrame:
    """3d: the factor covariance re-estimated at three half-lives."""
    factor_wide = inputs.factor_returns
    names_all = inputs.factor_names
    rows: list[dict[str, object]] = []
    for half_life in HALF_LIVES:
        for date in inputs.dates:
            weights, _ = _book_vector(inputs, date)
            design = inputs.design[date].to_numpy(dtype=float)
            specific = inputs.specific_variance[date].to_numpy(dtype=float)
            covariance = (
                fx.ewma_factor_cov(factor_wide.loc[:date], half_life=half_life)
                .loc[names_all, names_all]
                .to_numpy(dtype=float)
            )
            exposure = design.T @ weights
            total = float(
                exposure @ covariance @ exposure + np.sum(weights**2 * specific)
            )
            predicted_vol = float(np.sqrt(total * 252.0))
            realized_vol = stored_realized_vol(inputs, date)
            rows.append(
                {
                    "half_life": half_life,
                    "date": date,
                    "tercile": inputs.terciles.get(date, "unknown"),
                    "predicted_vol": predicted_vol,
                    "realized_vol": realized_vol,
                    "bias": (
                        realized_vol / predicted_vol if predicted_vol > 0 else np.nan
                    ),
                    "momentum_share": float(
                        (exposure * (covariance @ exposure))[
                            names_all.index("momentum")
                        ]
                        / total
                    ),
                }
            )
    return pd.DataFrame(rows)


def residual_projection(
    inputs: TercileInputs, k_values: tuple[int, ...] = (1, 3, 5, 10)
) -> pd.DataFrame:
    """3e: how much of the book's specific variance sits in a few directions.

    The residual PCA is refitted on the same 504-day window as each rebalance,
    the book's weights are projected onto the leading residual eigenvectors,
    and the variance each direction carries is `(v'w)^2 lambda`. The diagonal
    model assumes that variance is spread across names; if a handful of
    directions carry most of it, the diagonal understates concentrated risk.
    """
    rows: list[dict[str, object]] = []
    specific_frame = inputs.specific_returns
    for date in inputs.dates:
        weights = inputs.weights[date]
        names = list(weights.index)
        window = specific_frame.loc[specific_frame["date"] <= date]
        block = window.pivot(index="date", columns="ticker", values="specific_return")
        block = block.iloc[-st.PCA_WINDOW :]
        block = block.reindex(columns=names)
        block = block.loc[:, block.notna().all(axis=0)]
        if block.shape[1] < 20:
            continue
        fit = st.fit(block)
        w = weights.reindex(fit.tickers).fillna(0.0).to_numpy(dtype=float)
        projections = fit.eigenvectors.T @ w
        direction_variance = (projections**2) * fit.eigenvalues
        total = float(direction_variance.sum())
        if total <= 0:
            continue
        order = np.argsort(direction_variance)[::-1]
        sorted_variance = direction_variance[order]
        share = sorted_variance / total
        row: dict[str, object] = {
            "date": date,
            "tercile": inputs.terciles.get(date, "unknown"),
            "n_names": fit.n_names,
            "largest_eigenvalue": float(fit.eigenvalues[0]),
            "mp_edge": float(fit.mp_edge),
            "n_above_edge": int(np.sum(fit.eigenvalues > fit.mp_edge)),
            "realized_specific_variance": total,
            "effective_directions": float(1.0 / np.sum(share**2)),
            "diagonal_specific_variance": float(
                np.sum(
                    w**2
                    * inputs.specific_variance[date]
                    .reindex(fit.tickers)
                    .fillna(0.0)
                    .to_numpy()
                )
            ),
        }
        for k in k_values:
            row[f"top{k}_share"] = float(share[:k].sum())
        rows.append(row)
    return pd.DataFrame(rows)


def run(data_root: Path | None = None) -> dict[str, pd.DataFrame]:
    """Run all five measurements and return them, printing the summary."""
    inputs = load_inputs(data_root)
    decomposition = predicted_variance_by_source(inputs)
    confound = tercile_confound(inputs)
    orthogonality = orthogonality_test(inputs)
    sweep = half_life_sweep(inputs)
    projection = residual_projection(inputs)

    print("### Task 3a: predicted variance by source, per tercile")
    grouped = decomposition.groupby("tercile")
    summary = pd.DataFrame(
        {
            "months": grouped.size(),
            "predicted_vol": grouped["predicted_vol"].mean(),
            "momentum_share": grouped["momentum_share"].mean(),
            "market_share": (
                grouped["market_share"].mean()
                if "market_share" in decomposition.columns
                else np.nan
            ),
            "style_share": grouped["style_share"].mean(),
            "sector_share": grouped["sector_share"].mean(),
            "idio_share": grouped["idio_share"].mean(),
            "factor_share": grouped["factor_share"].mean(),
        }
    )
    print(summary.round(6).to_string())
    print()
    print("### Task 3b: tercile membership by year and the market factor")
    print(
        confound.pivot_table(
            index="year", columns="tercile", values="months_in_year", aggfunc="sum"
        )
        .fillna(0)
        .astype(int)
        .to_string()
    )
    print()
    print(
        confound.groupby("tercile")[
            [
                "first_month",
                "last_month",
                "market_vol_own_month",
                "market_vol_forward",
                "book_predicted_vol",
                "book_realized_vol",
                "book_realized_vol_covariance_form",
            ]
        ]
        .first()
        .round(6)
        .to_string()
    )
    print()
    print("### Task 3c: orthogonality of the factor and specific components")
    print(
        orthogonality.groupby("tercile")[
            [
                "var_factor_component",
                "var_specific_component",
                "covariance",
                "var_total",
                "correlation",
                "covariance_share_of_total",
            ]
        ]
        .mean()
        .round(8)
        .to_string()
    )
    print()
    print("### Task 3d: half-life sweep, secondary")
    print(
        sweep.groupby(["half_life", "tercile"])[
            ["predicted_vol", "realized_vol", "bias", "momentum_share"]
        ]
        .mean()
        .round(6)
        .to_string()
    )
    print()
    print("### Task 3e: the book's specific variance in a few residual directions")
    print(
        projection.groupby("tercile")[
            [
                "n_names",
                "largest_eigenvalue",
                "mp_edge",
                "n_above_edge",
                "realized_specific_variance",
                "diagonal_specific_variance",
                "effective_directions",
                "top1_share",
                "top3_share",
                "top5_share",
                "top10_share",
            ]
        ]
        .mean()
        .round(6)
        .to_string()
    )
    return {
        "decomposition": decomposition,
        "confound": confound,
        "orthogonality": orthogonality,
        "sweep": sweep,
        "projection": projection,
    }
