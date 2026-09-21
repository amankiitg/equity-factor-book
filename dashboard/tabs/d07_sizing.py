"""D7 Sizing and Optimizer: construction on synthetic alpha.

Sprint E8, Task 9. Reads the stored construction artifacts only, never fits
a model. Every panel builder raises on an empty read, and every quantity is
labeled INPUT or OUTPUT. The synthetic label travels with every number.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import version as version_module

ROOT = version_module.ROOT
DATA = ROOT / "data"
PORTFOLIOS = DATA / "portfolios"

CONSTRUCTIONS = (
    "proportional",
    "sharpe",
    "procedure_6_3",
    "mv_unconstrained",
    "mv_constrained",
    "combined",
    "shrunk",
)


def _require(frame: pd.DataFrame, what: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError(f"D7 panel {what} read an empty artifact")
    return frame


def load_summary() -> pd.DataFrame:
    frame = pd.read_parquet(PORTFOLIOS / "e8_summary.parquet")
    return _require(frame, "construction summary")


def load_construction(name: str) -> pd.DataFrame:
    frame = pd.read_parquet(PORTFOLIOS / f"{name}.parquet")
    return _require(frame, f"{name} weights")


def comparison_panel() -> pd.DataFrame:
    """The side-by-side rule comparison at the selected rho."""
    summary = load_summary()
    rho = st.selectbox("rho (known IC)", [0.02, 0.05, 0.10], index=1)
    sub = summary[summary["rho"] == rho]
    rows = [
        {
            "construction": row["construction"],
            "mean_idio_share": float(row["mean_idio_share"]),
            "mean_idio_share_after_fmp": float(row["mean_idio_share_after_fmp"]),
            "mean_n_eff": float(row["mean_n_eff"]),
            "realized_ir": float(row["realized_ir"]),
        }
        for row in sub.to_dict(orient="records")
    ]
    return _require(pd.DataFrame(rows), f"rule comparison at rho {rho}")


def worked_example_panel() -> pd.DataFrame:
    """One stock followed from alpha to weight on the latest date."""
    name = st.selectbox("Construction", CONSTRUCTIONS)
    frame = load_construction(name)
    latest = frame.loc[frame["date"] == frame["date"].max()]
    sample = latest.head(1)
    row = sample.iloc[0]
    return pd.DataFrame(
        [
            {
                "quantity": "INPUT date",
                "value": str(pd.Timestamp(row["date"]).date()),
            },
            {
                "quantity": "INPUT ticker",
                "value": str(row["ticker"]),
            },
            {
                "quantity": "OUTPUT weight",
                "value": float(row["weight"]),
            },
            {
                "quantity": "OUTPUT idio share after FMP (book)",
                "value": float(row["idio_share_after_fmp"]),
            },
        ]
    )


def exposures_panel(name: str) -> pd.DataFrame:
    """The weight distribution and the idio share of one construction."""
    frame = load_construction(name)
    rho = st.selectbox("rho", sorted(frame["rho"].unique().tolist()), key=f"{name}_rho")
    sub = frame[frame["rho"] == rho]
    latest = sub[sub["date"] == sub["date"].max()]
    gross = float(latest["gross"].iloc[0])
    net = float(latest["net"].iloc[0])
    return pd.DataFrame(
        [
            {"quantity": "INPUT gross", "value": gross},
            {"quantity": "INPUT net", "value": net},
            {
                "quantity": "OUTPUT mean idio share after FMP",
                "value": float(sub["idio_share_after_fmp"].mean()),
            },
            {"quantity": "OUTPUT mean n_eff", "value": float(sub["n_eff"].mean())},
        ]
    )


def render() -> None:
    st.caption(
        "Synthetic controlled experiment: z = rho * standardized e(t+h) + "
        "sqrt(1 - rho^2) * eps, never a backtest."
    )
    st.markdown("### Rule comparison")
    st.dataframe(comparison_panel(), use_container_width=True)
    st.markdown("### Worked example: one stock from alpha to weight")
    st.dataframe(worked_example_panel(), use_container_width=True)
    st.markdown("### Exposures of one construction")
    chosen = st.selectbox("Construction for exposures", CONSTRUCTIONS)
    st.dataframe(exposures_panel(chosen), use_container_width=True)
    st.markdown("### Stored summary")
    st.dataframe(load_summary(), use_container_width=True)
