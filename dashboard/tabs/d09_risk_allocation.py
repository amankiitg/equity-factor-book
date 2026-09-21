"""D9 Risk Allocation: Kelly, vol targeting and the stop-loss analysis.

Sprint E10, Task 9. Reads the stored allocation artifacts only. Every panel
builder raises on an empty read.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import version as version_module

ROOT = version_module.ROOT
DATA = ROOT / "data"
ALLOC = DATA / "allocation"


def _require(frame: pd.DataFrame, what: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError(f"D9 panel {what} read an empty artifact")
    return frame


def load_kelly() -> pd.DataFrame:
    return _require(pd.read_parquet(ALLOC / "kelly.parquet"), "Kelly table")


def load_drawdown() -> pd.DataFrame:
    return _require(pd.read_parquet(ALLOC / "drawdown.parquet"), "drawdown table")


def load_voltarget() -> pd.DataFrame:
    return _require(pd.read_parquet(ALLOC / "voltarget.parquet"), "vol-target table")


def load_stoploss() -> pd.DataFrame:
    return _require(pd.read_parquet(ALLOC / "stoploss.parquet"), "stop-loss table")


def load_regime() -> pd.DataFrame:
    return _require(pd.read_parquet(ALLOC / "regime.parquet"), "regime table")


def kelly_panel() -> pd.DataFrame:
    """The Kelly calculator's stored output, labeled."""
    kelly = load_kelly()
    columns = {
        "sharpe": "Sharpe (annualized)",
        "sharpe_se": "SE of Sharpe",
        "mean_ann": "mean (annualized)",
        "vol_ann": "vol (annualized)",
        "kelly_full": "full Kelly leverage",
        "kelly_half": "half Kelly leverage",
        "growth_full": "growth at full Kelly",
        "growth_half": "growth at half Kelly",
        "growth_loss_overbet": "growth loss when SR overstated by one SE",
    }
    return _require(kelly[list(columns)].rename(columns=columns), "Kelly panel")


def drawdown_panel() -> pd.DataFrame:
    return load_drawdown()


def voltarget_panel() -> pd.DataFrame:
    return load_voltarget()


def stoploss_panel() -> pd.DataFrame:
    return load_stoploss()


def regime_panel() -> pd.DataFrame:
    return load_regime()


def render() -> None:
    st.caption(
        "Kelly and fractional Kelly under an estimated Sharpe, vol targeting "
        "and the stop-loss efficiency analysis, on the design book whose net "
        "Sharpe is closest to 1.0."
    )
    st.markdown("### Kelly calculator")
    st.dataframe(kelly_panel(), use_container_width=True)
    st.markdown("### Drawdown distribution against the analytical median")
    st.dataframe(drawdown_panel(), use_container_width=True)
    st.markdown("### Vol-target simulation")
    st.dataframe(voltarget_panel(), use_container_width=True)
    st.markdown("### Stop-loss efficiency")
    st.dataframe(stoploss_panel(), use_container_width=True)
    st.markdown("### Drawdowns by VIX regime")
    st.dataframe(regime_panel(), use_container_width=True)
