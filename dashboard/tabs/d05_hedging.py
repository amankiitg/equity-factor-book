"""D5 Hedging: positions, efficacy, costs and the residual exposures.

Sprint E6, Task 6. Reads parquet only and never fits a model. Every panel
builder goes through `_require`, which raises on an empty read, so a panel
that loses its artifact fails loudly instead of drawing an empty chart.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import version as version_module

ROOT = version_module.ROOT
HEDGE = ROOT / "data" / "hedge"


def _require(frame: pd.DataFrame, what: str) -> pd.DataFrame:
    """A panel must not draw on an empty read."""
    if frame is None or frame.empty:
        raise ValueError(f"D5 panel {what} read an empty artifact")
    return frame


def load_metrics() -> pd.DataFrame:
    frame = pd.read_parquet(HEDGE / "hedge_metrics.parquet")
    return _require(frame, "hedge metrics")


def load_positions() -> pd.DataFrame:
    frame = pd.read_parquet(HEDGE / "hedge_positions.parquet")
    return _require(frame, "hedge positions")


def load_exposures() -> pd.DataFrame:
    frame = pd.read_parquet(HEDGE / "e6_exposures.parquet")
    return _require(frame, "hedge exposures")


def load_efficacy() -> pd.DataFrame:
    frame = pd.read_parquet(HEDGE / "e6_efficacy.parquet")
    return _require(frame, "realized efficacy")


def load_decay() -> pd.DataFrame:
    frame = pd.read_parquet(HEDGE / "e6_decay.parquet")
    return _require(frame, "decay curve")


def headline_panel() -> pd.DataFrame:
    """The factor variance removed and the cost, per book and method."""
    metrics = _require(load_metrics(), "headline panel")
    headline = (
        metrics.groupby(["book", "method", "model"], dropna=False)
        .agg(
            factor_variance_removed_share=("factor_variance_removed_share", "mean"),
            idio_share_after=("idio_share_after", "mean"),
            turnover=("turnover", "mean"),
            cost=("cost", "mean"),
            n_instruments=("n_instruments", "mean"),
        )
        .reset_index()
    )
    return headline


def positions_panel() -> pd.DataFrame:
    """The mean absolute hedge weight per instrument, book and model."""
    positions = _require(load_positions(), "positions panel")
    panel = (
        positions.groupby(["book", "model", "instrument"], dropna=False)["weight"]
        .agg(["mean"])
        .reset_index()
        .rename(columns={"mean": "mean_weight"})
    )
    panel["abs_mean_weight"] = panel["mean_weight"].abs()
    return panel


def residual_exposure_panel() -> pd.DataFrame:
    """F6.5: the per-factor exposure the instrument set cannot reach."""
    exposures = _require(load_exposures(), "residual exposure panel")
    panel = (
        exposures.loc[exposures["book"] == "seed_ew"]
        .groupby("factor", dropna=False)["exposure_after_min_variance"]
        .apply(lambda s: float(s.abs().mean()))
        .reset_index()
        .rename(columns={"exposure_after_min_variance": "mean_abs_residual"})
        .sort_values("mean_abs_residual", ascending=False)
    )
    return panel


def realized_panel() -> pd.DataFrame:
    """The realized beta to Mkt-RF for every hedge, 2018 to 2026."""
    efficacy = _require(load_efficacy(), "realized panel")
    return efficacy


def decay_panel() -> pd.DataFrame:
    """The realized beta against the rebalance frequency."""
    decay = _require(load_decay(), "decay panel")
    return decay


def render() -> None:
    st.markdown("### Factor variance removed, idio share and cost")
    st.dataframe(headline_panel(), use_container_width=True)
    st.caption(
        "Cost uses the E9 provisional constants: 5 bps per unit of turnover "
        "plus 2% per year on short notional."
    )
    st.markdown("### Hedge positions by instrument")
    st.dataframe(positions_panel(), use_container_width=True)
    st.markdown("### Realized beta to Mkt-RF, 2018 to 2026")
    st.dataframe(realized_panel(), use_container_width=True)
    st.markdown("### Efficacy against rebalancing frequency")
    st.dataframe(decay_panel(), use_container_width=True)
    st.markdown("### The residual the instrument set cannot reach (F6.5)")
    st.dataframe(residual_exposure_panel(), use_container_width=True)
