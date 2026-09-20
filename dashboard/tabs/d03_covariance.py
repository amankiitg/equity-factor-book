"""D3 Covariance Lab: the eigenvalue spectrum, the estimator race and the audit.

Sprint E4, Task 5. Reads parquet only and never fits a model. Every panel
builder goes through `_require`, which raises on an empty read, so a panel that
loses its artifact fails loudly instead of drawing an empty chart.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import version as version_module

ROOT = version_module.ROOT


def _require(frame: pd.DataFrame, what: str) -> pd.DataFrame:
    """A panel must not draw on an empty read."""
    if frame is None or frame.empty:
        raise ValueError(f"D3 panel {what} read an empty artifact")
    return frame


def load_spectrum() -> pd.DataFrame:
    frame = pd.read_parquet(ROOT / "data" / "models" / "PCA-v1" / "eigenvalues.parquet")
    return _require(frame, "eigenvalue spectrum")


def load_panel_spectrum() -> pd.DataFrame:
    frame = pd.read_parquet(
        ROOT / "data" / "models" / "PCA-v1" / "eigenvalues_panel.parquet"
    )
    return _require(frame, "panel spectrum")


def load_residual_spectrum() -> pd.DataFrame:
    frame = pd.read_parquet(ROOT / "data" / "eval" / "xs_residual_spectrum.parquet")
    return _require(frame, "residual spectrum")


def load_horse_race() -> pd.DataFrame:
    frame = pd.read_parquet(ROOT / "data" / "eval" / "cov_horse_race.parquet")
    return _require(frame, "estimator horse race")


def load_pca_factor_returns() -> pd.DataFrame:
    frame = pd.read_parquet(
        ROOT / "data" / "models" / "PCA-v1" / "factor_returns.parquet"
    )
    return _require(frame, "PCA factor returns")


def load_xs_factor_returns(version: str = "XS-v1") -> pd.DataFrame:
    frame = pd.read_parquet(
        ROOT / "data" / "models" / version / "factor_returns.parquet"
    )
    return _require(frame, f"{version} factor returns")


def load_halflife_sweep() -> pd.DataFrame:
    frame = pd.read_parquet(ROOT / "data" / "eval" / "xs_task3_sweep.parquet")
    return _require(frame, "half-life sweep")


def load_residual_projection() -> pd.DataFrame:
    frame = pd.read_parquet(ROOT / "data" / "eval" / "xs_task3_projection.parquet")
    return _require(frame, "residual projection")


def eigenvalue_panel() -> pd.DataFrame:
    """The spectrum against the Marchenko-Pastur edge, both universes."""
    model = load_spectrum()
    panel = load_panel_spectrum()
    return _require(pd.concat([model, panel], ignore_index=True), "eigenvalue spectrum")


def explained_variance_panel() -> pd.DataFrame:
    frame = _require(load_spectrum(), "explained variance")
    return frame.loc[:, ["index", "explained_share", "cumulative_share", "mp_edge"]]


def factor_correlation_panel() -> pd.DataFrame:
    """PCA factors against the fundamental factors, on the overlap."""
    pca = _require(load_pca_factor_returns(), "PCA factor returns")
    fundamental = _require(load_xs_factor_returns(), "XS-v1 factor returns")
    left = pca.pivot(index="date", columns="factor", values="f")
    right = fundamental.pivot(index="date", columns="factor", values="f")
    joined = left.join(right, how="inner", lsuffix="_pca", rsuffix="_xs")
    return _require(
        joined.corr().loc[left.columns, right.columns], "factor correlation"
    )


def estimator_table_panel() -> pd.DataFrame:
    """Medians and win counts, never means: the mean ranking is a tail statistic."""
    race = _require(load_horse_race(), "estimator horse race")
    pivot = race.pivot(index="date", columns="estimator", values="realized_vol")
    table = pd.DataFrame(
        {
            "median_realized_vol": pivot.median(),
            "windows_won": (pivot.rank(axis=1, method="min") == 1).sum(),
            "median_condition_number": race.groupby("estimator")[
                "condition_number"
            ].median(),
            "parameters": race.groupby("estimator")["parameter_count"].median(),
            "median_ratio_to_sample": pivot.div(pivot["sample"], axis=0).median(),
            "windows": race.groupby("estimator").size(),
        }
    )
    return _require(table.sort_values("median_realized_vol"), "estimator table")


def halflife_panel() -> pd.DataFrame:
    sweep = _require(load_halflife_sweep(), "half-life sweep")
    return _require(
        sweep.groupby(["half_life", "tercile"])[
            ["predicted_vol", "realized_vol", "bias", "momentum_share"]
        ].mean(),
        "half-life sweep",
    )


def residual_direction_panel() -> pd.DataFrame:
    projection = _require(load_residual_projection(), "residual projection")
    return _require(
        projection.groupby("tercile")[
            [
                "largest_eigenvalue",
                "mp_edge",
                "n_above_edge",
                "effective_directions",
                "top1_share",
                "top3_share",
                "top5_share",
                "top10_share",
            ]
        ].mean(),
        "residual projection",
    )


def render() -> None:
    """The D3 tab: six panels, the last four version aware."""
    chosen = version_module.selected_version()
    st.subheader("D3 Covariance Lab")
    st.caption(
        f"showing {chosen}. Eigenvalues, the estimator race and the residual "
        "audit read parquet only."
    )

    st.markdown("**Eigenvalue spectrum against the Marchenko-Pastur edge**")
    spectrum = eigenvalue_panel()
    st.dataframe(spectrum.loc[spectrum["index"] <= 30], hide_index=True)
    st.line_chart(
        spectrum.loc[spectrum["index"] <= 50].set_index("index")["eigenvalue"]
    )

    st.markdown("**Explained variance**")
    st.dataframe(explained_variance_panel().head(30), hide_index=True)
    st.line_chart(
        explained_variance_panel().set_index("index")["cumulative_share"].head(50)
    )

    st.markdown("**PCA factors against the fundamental factors**")
    st.dataframe(factor_correlation_panel().round(4))

    st.markdown("**Estimator comparison: medians and win counts**")
    st.dataframe(estimator_table_panel().round(6))

    st.markdown("**The momentum book's bias by half-life and exposure tercile**")
    st.dataframe(halflife_panel().round(6))

    st.markdown("**Residual directions that carry the book's specific variance**")
    st.dataframe(residual_direction_panel().round(6))
