"""D8 Cost and Capacity: the cost model and the capacity curve.

Sprint E9, Task 8. Reads the stored cost artifacts only. Every panel
builder raises on an empty read, and the synthetic label travels with every
number.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import version as version_module

ROOT = version_module.ROOT
DATA = ROOT / "data"
COSTS = DATA / "costs"


def _require(frame: pd.DataFrame, what: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError(f"D8 panel {what} read an empty artifact")
    return frame


def load_cost_curves() -> pd.DataFrame:
    return _require(pd.read_parquet(COSTS / "cost_curves.parquet"), "cost curves")


def load_capacity() -> pd.DataFrame:
    return _require(pd.read_parquet(COSTS / "capacity.parquet"), "capacity curve")


def load_halving() -> pd.DataFrame:
    return _require(pd.read_parquet(COSTS / "capacity_halving.parquet"), "halving AUM")


def load_tradeoff() -> pd.DataFrame:
    return _require(
        pd.read_parquet(COSTS / "turnover_tradeoff.parquet"), "turnover trade-off"
    )


def cost_curves_panel() -> pd.DataFrame:
    return load_cost_curves()


def capacity_panel() -> pd.DataFrame:
    """The capacity curve at the selected rho and k, halving point marked."""
    rho = st.selectbox("rho", [0.02, 0.05, 0.10], index=1)
    k = st.selectbox("impact coefficient k", [0.25, 0.5, 1.0], index=1)
    capacity = load_capacity()
    sub = capacity[(capacity["rho"] == rho) & (capacity["k"] == k)].sort_values("aum")
    halving = load_halving()
    halving_row = halving[(halving["rho"] == rho) & (halving["k"] == k)]
    halving_aum = float(halving_row["halving_aum"].iloc[0])
    rows = [
        {
            "aum": row["aum"],
            "gross_sharpe": row["gross_sharpe"],
            "net_sharpe": row["net_sharpe"],
            "halving": bool(row["aum"] >= halving_aum) if halving_aum > 0 else False,
        }
        for row in sub.to_dict(orient="records")
    ]
    return _require(pd.DataFrame(rows), f"capacity curve at rho {rho} k {k}")


def tradeoff_panel() -> pd.DataFrame:
    return load_tradeoff()


def render() -> None:
    st.caption(
        "Synthetic alpha with a known IC; real capacity is undefined because "
        "no signal passed RG-Signal. The table answers the useful question "
        "instead: what IC supports a given AUM under these costs."
    )
    st.markdown("### Cost curves by size decile")
    st.dataframe(cost_curves_panel(), use_container_width=True)
    st.markdown("### Turnover versus ex-ante IR")
    st.dataframe(tradeoff_panel(), use_container_width=True)
    st.markdown("### Capacity curve")
    st.dataframe(capacity_panel(), use_container_width=True)
    st.markdown("### Halving AUM")
    st.dataframe(load_halving(), use_container_width=True)
