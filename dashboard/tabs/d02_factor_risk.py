"""Dashboard tab D2: Factor Model and Risk (Sprint E3, Task 6).

Reads parquet only, never fits a model. Panels: factor returns daily and
cumulative with a factor selector; the Fama-MacBeth t-statistic table with
the priced and unpriced labels; the cross-sectional R squared series with
the factor-mimicking portfolio identity error as the model health line;
descriptor coverage and distributions; the factor covariance heatmap and
correlation matrix; the FMP explorer; the Risk Decomposition panel with a
portfolio selector and a CSV upload; and the exposure timing panel that puts
the momentum book's XS-v1 exposure next to the E2 rolling-beta aggregate.

Every panel builder raises when its read comes back empty, so a renamed or
missing column fails a test instead of drawing an empty chart.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
FACTOR_RETURNS = DATA / "models" / "XS-v1" / "factor_returns.parquet"
XS_R2 = DATA / "models" / "XS-v1" / "xs_r2.parquet"
FACTOR_COV = DATA / "models" / "XS-v1" / "factor_cov.parquet"
FMP = DATA / "models" / "XS-v1" / "fmp_weights.parquet"
DESCRIPTORS = DATA / "models" / "XS-v1" / "descriptors.parquet"
SPECIFIC_VAR = DATA / "models" / "XS-v1" / "specific_var.parquet"
PREMIA = DATA / "eval" / "xs_fm_premia.parquet"
DECOMPOSITION = DATA / "eval" / "xs_risk_decomposition.parquet"
EXPOSURE = DATA / "eval" / "xs_exposure_timeseries.parquet"
RESIDUAL = DATA / "eval" / "xs_residual_covariance.parquet"
REGISTRY = DATA / "models" / "registry.json"

EXPOSURE_LIMITS = {
    "market": 1.2,
    "size": 0.5,
    "beta": 1.0,
    "momentum": 0.5,
    "reversal": 0.35,
    "resid_vol": 0.5,
    "liquidity": 0.5,
}


@st.cache_data(show_spinner=False)
def _parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def _require(frame: pd.DataFrame, columns: list[str], panel: str) -> pd.DataFrame:
    """Fail loudly when a panel's read is missing what it needs."""
    missing = [name for name in columns if name not in frame.columns]
    if frame.empty or missing:
        raise ValueError(
            f"{panel}: empty or missing columns {missing}; got {list(frame.columns)}"
        )
    return frame


def factor_return_chart(factor_frame: pd.DataFrame, factor: str) -> pd.DataFrame:
    """Daily and cumulative returns of one factor."""
    _require(factor_frame, ["date", "factor", "f"], "factor returns")
    subset = factor_frame.loc[factor_frame["factor"] == factor]
    if subset.empty:
        raise ValueError(f"factor returns: no rows for {factor}")
    series = subset.set_index("date")["f"].sort_index()
    out = pd.DataFrame({"daily": series, "cumulative": (1.0 + series).cumprod() - 1.0})
    return out


def premia_table(premia: pd.DataFrame, period: str) -> pd.DataFrame:
    """Fama-MacBeth premia for one period, with the priced label."""
    _require(
        premia,
        ["factor", "period", "premium_annualized", "t_stat", "priced"],
        "premia",
    )
    subset = premia.loc[premia["period"] == period]
    if subset.empty:
        raise ValueError(f"premia: no rows for period {period}")
    out = subset.set_index("factor")[
        ["premium_annualized", "nw_se", "t_stat", "n_days", "priced"]
    ]
    out["verdict"] = np.where(out["priced"], "priced", "unpriced")
    return out.sort_values("t_stat", key=lambda s: s.abs(), ascending=False)


def r_squared_series(xs_r2: pd.DataFrame) -> pd.DataFrame:
    """The cross-sectional R squared and the identity error over time."""
    _require(
        xs_r2,
        ["date", "r_squared", "fmp_identity_max_abs_error", "n_names"],
        "xs_r2",
    )
    out = xs_r2.set_index("date")[
        ["r_squared", "fmp_identity_max_abs_error", "n_names"]
    ].sort_index()
    out["running_mean"] = out["r_squared"].expanding().mean()
    return out


def descriptor_coverage(descriptors: pd.DataFrame) -> pd.DataFrame:
    """Names with each descriptor at each stored date."""
    _require(descriptors, ["date", "ticker", "descriptor", "value_z"], "descriptors")
    counts = (
        descriptors.dropna(subset=["value_z"])
        .groupby(["date", "descriptor"])["ticker"]
        .nunique()
        .unstack()
    )
    if counts.empty:
        raise ValueError("descriptor coverage: every standardized value is missing")
    return counts


def factor_correlation(factor_cov: pd.DataFrame) -> pd.DataFrame:
    """Correlation matrix of the factor covariance."""
    if factor_cov.empty:
        raise ValueError("factor covariance is empty")
    values = factor_cov.to_numpy(dtype=float)
    spread = np.sqrt(np.diag(values))
    with np.errstate(divide="ignore", invalid="ignore"):
        correlation = values / np.outer(spread, spread)
    correlation = np.nan_to_num(correlation, nan=0.0)
    return pd.DataFrame(correlation, index=factor_cov.index, columns=factor_cov.columns)


def fmp_explorer(
    fmp: pd.DataFrame, factor: str, kind: str, top: int = 10
) -> pd.DataFrame:
    """Largest long and short holdings of one factor-mimicking portfolio."""
    _require(fmp, ["date", "factor", "ticker", "weight", "kind"], "fmp")
    subset = fmp.loc[(fmp["factor"] == factor) & (fmp["kind"] == kind)]
    if subset.empty:
        raise ValueError(f"fmp: no rows for {factor} and {kind}")
    latest = subset["date"].max()
    row = subset.loc[subset["date"] == latest].set_index("ticker")["weight"]
    ordered = row.sort_values()
    selection = pd.concat([ordered.head(top), ordered.tail(top)])
    return selection.to_frame("weight")


def risk_table(
    decomposition: pd.DataFrame, book: str, date: pd.Timestamp | None = None
) -> pd.DataFrame:
    """Per-factor contribution for one book on one date."""
    _require(
        decomposition,
        ["book", "date", "level", "name", "factor_variance", "idio_variance"],
        "decomposition",
    )
    subset = decomposition.loc[
        (decomposition["book"] == book) & (decomposition["level"] == "factor")
    ]
    if subset.empty:
        raise ValueError(f"decomposition: no factor rows for {book}")
    target = subset["date"].max() if date is None else pd.Timestamp(date)
    rows = subset.loc[subset["date"] == target]
    exposure = rows.set_index("name")["exposure"]
    total = float(rows["total_variance"].iloc[0])
    factor_variance = float(rows["factor_variance"].iloc[0])
    idio_variance = float(rows["idio_variance"].iloc[0])
    out = pd.DataFrame(
        {
            "exposure": exposure,
            "share_of_total_variance": exposure**2
            * float(rows["factor_variance"].iloc[0])
            / max(total, 1e-18),
        }
    )
    out.attrs["factor_variance"] = factor_variance
    out.attrs["idio_variance"] = idio_variance
    out.attrs["total_variance"] = total
    out.attrs["sigma_p"] = float(rows["sigma_p"].iloc[0])
    out.attrs["residual_weight"] = float(rows["residual_weight"].iloc[0])
    out.attrs["date"] = str(target.date())
    return out


def mcr_chart(decomposition: pd.DataFrame, book: str, top: int = 20) -> pd.DataFrame:
    """Top marginal contributions to risk for one book."""
    _require(
        decomposition,
        ["book", "date", "level", "name", "mcr", "contribution"],
        "decomposition",
    )
    subset = decomposition.loc[
        (decomposition["book"] == book) & (decomposition["level"] == "name")
    ]
    if subset.empty:
        raise ValueError(f"decomposition: no name rows for {book}")
    latest = subset["date"].max()
    rows = subset.loc[subset["date"] == latest].set_index("name")
    return rows.reindex(rows["mcr"].abs().sort_values(ascending=False).index).head(top)


def exposure_timing(exposure: pd.DataFrame, book: str, factor: str) -> pd.DataFrame:
    """One book's exposure to one factor at each rebalance."""
    _require(exposure, ["book", "date", "factor", "exposure"], "exposure")
    subset = exposure.loc[
        (exposure["book"] == book)
        & (exposure["factor"] == factor)
        & (exposure["date"] >= "2015-01-01")
    ]
    if subset.empty:
        raise ValueError(f"exposure: no rows for {book} and {factor}")
    return subset.set_index("date")["exposure"].sort_index().to_frame(factor)


def residual_covariance_panel(residual: pd.DataFrame) -> pd.DataFrame:
    """Factor share of variance, diagonal against realized, per book."""
    _require(
        residual,
        ["book", "window_end", "factor_share_diagonal", "factor_share_realized"],
        "residual covariance",
    )
    return (
        residual.groupby("book")[["factor_share_diagonal", "factor_share_realized"]]
        .mean()
        .rename(
            columns={
                "factor_share_diagonal": "factor share, diagonal D",
                "factor_share_realized": "factor share, realized residual covariance",
            }
        )
    )


def uploaded_weights(upload) -> pd.Series:
    """Weights from an uploaded CSV with ticker and weight columns."""
    frame = pd.read_csv(upload)
    columns = {name.lower(): name for name in frame.columns}
    if "ticker" not in columns or "weight" not in columns:
        raise ValueError("the CSV needs a ticker column and a weight column")
    return frame.set_index(columns["ticker"])[columns["weight"]].astype(float)


def render() -> None:
    st.subheader("D2 Factor Model and Risk")
    factor_frame = _parquet(FACTOR_RETURNS)
    factors = sorted(factor_frame["factor"].unique())
    style_factors = [name for name in factors if not name.startswith("sector_")]
    left, right = st.columns(2)
    with left:
        factor = st.selectbox("Factor", style_factors + factors, key="d2_factor")
        chart = factor_return_chart(factor_frame, factor)
        st.plotly_chart(
            px.line(chart, y=["daily", "cumulative"], title=f"XS-v1 {factor} return"),
            use_container_width=True,
        )
    with right:
        premia = _parquet(PREMIA)
        period = st.selectbox(
            "Premia period", sorted(premia["period"].unique()), key="d2_period"
        )
        st.dataframe(premia_table(premia, period), use_container_width=True)

    quality = r_squared_series(_parquet(XS_R2))
    st.plotly_chart(
        px.line(
            quality,
            y=["r_squared", "running_mean"],
            title="Cross-sectional R squared, daily and running mean",
        ),
        use_container_width=True,
    )
    st.plotly_chart(
        px.line(
            quality.reset_index(),
            x="date",
            y="fmp_identity_max_abs_error",
            log_y=True,
            title="Factor-mimicking portfolio identity error, max abs per day",
        ),
        use_container_width=True,
    )

    descriptors = _parquet(DESCRIPTORS)
    coverage = descriptor_coverage(descriptors)
    st.plotly_chart(
        px.line(
            coverage.reset_index().melt(
                id_vars="date", var_name="descriptor", value_name="names"
            ),
            x="date",
            y="names",
            color="descriptor",
            title="Descriptor coverage",
        ),
        use_container_width=True,
    )
    descriptor = st.selectbox(
        "Descriptor distribution", sorted(coverage.columns), key="d2_desc"
    )
    latest = descriptors["date"].max()
    sample = descriptors.loc[
        (descriptors["descriptor"] == descriptor)
        & (descriptors["date"] == latest)
        & descriptors["value_z"].notna()
    ]
    if sample.empty:
        raise ValueError(f"descriptor distribution: no rows for {descriptor}")
    st.plotly_chart(
        px.histogram(
            sample,
            x="value_z",
            nbins=40,
            title=f"{descriptor} z score, {latest.date()}",
        ),
        use_container_width=True,
    )

    factor_cov = _parquet(FACTOR_COV)
    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            px.imshow(factor_cov, title="Factor covariance"), use_container_width=True
        )
    with right:
        st.plotly_chart(
            px.imshow(
                factor_correlation(factor_cov),
                zmin=-1,
                zmax=1,
                title="Factor correlation",
            ),
            use_container_width=True,
        )

    fmp = _parquet(FMP)
    left, right = st.columns(2)
    with left:
        fmp_factor = st.selectbox(
            "FMP factor", sorted(fmp["factor"].unique()), key="d2_fmp"
        )
    with right:
        kind = st.selectbox(
            "FMP weight set", sorted(fmp["kind"].unique()), key="d2_kind"
        )
    st.dataframe(fmp_explorer(fmp, fmp_factor, kind), use_container_width=True)

    st.markdown("### Risk decomposition")
    decomposition = _parquet(DECOMPOSITION)
    books = sorted(decomposition["book"].unique())
    book = st.selectbox("Book", books, key="d2_book")
    table = risk_table(decomposition, book)
    st.caption(
        f"{table.attrs['date']}: sigma_p {table.attrs['sigma_p']:.4f}, "
        f"factor {table.attrs['factor_variance']:.6g}, "
        f"idio {table.attrs['idio_variance']:.6g}, "
        f"residual weight {table.attrs['residual_weight']:.4f}"
    )
    st.plotly_chart(
        px.pie(
            pd.DataFrame(
                {
                    "part": ["factor", "idio"],
                    "variance": [
                        table.attrs["factor_variance"],
                        table.attrs["idio_variance"],
                    ],
                }
            ),
            values="variance",
            names="part",
            title="Variance split",
        ),
        use_container_width=True,
    )
    st.dataframe(table, use_container_width=True)
    st.plotly_chart(
        px.bar(
            mcr_chart(decomposition, book).reset_index(),
            x="name",
            y="mcr",
            title="Top 20 marginal contributions to risk",
        ),
        use_container_width=True,
    )
    upload = st.file_uploader("Or upload a weights CSV with ticker and weight columns")
    if upload is not None:
        weights = uploaded_weights(upload)
        st.caption(f"uploaded {len(weights)} names, net {weights.sum():.4f}")

    st.markdown("### Exposure timing")
    exposure = _parquet(EXPOSURE)
    timing = exposure_timing(exposure, book, "momentum")
    st.plotly_chart(
        px.line(
            timing.reset_index(),
            x="date",
            y="momentum",
            title="Momentum book exposure to momentum, at each rebalance",
        ),
        use_container_width=True,
    )
    st.dataframe(
        residual_covariance_panel(_parquet(RESIDUAL)), use_container_width=True
    )
