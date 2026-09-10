"""Dashboard tab D1: Exposures (Sprint E2, Task 7).

Reads parquet only, never fits a model. Panels: per-stock loadings with
standard errors; rolling beta with raw, Vasicek and Blume overlays;
R squared distribution; idio versus total vol scatter; volatility
estimator comparison with the QLIKE table; portfolio exposure panel; and
the beta horse-race table.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from efb import portfolios as pf
from efb import vol as vol_mod

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
LOADINGS = DATA / "models" / "TS-v1" / "loadings.parquet"
LOADINGS_SE = DATA / "models" / "TS-v1" / "loadings_se.parquet"
IDIO = DATA / "models" / "TS-v1" / "idio_vol.parquet"
BETA_HISTORY = DATA / "models" / "TS-v1" / "beta_history.parquet"
VOL_RACE = DATA / "eval" / "vol_horse_race.parquet"
BETA_RACE = DATA / "eval" / "beta_horse_race.parquet"
RISK_SNAPSHOT = DATA / "eval" / "portfolio_risk_snapshot.parquet"
RETURNS = DATA / "processed" / "returns.parquet"
SEED_EW = DATA / "portfolios" / "seed_ew.parquet"
SEED_LS = DATA / "portfolios" / "seed_mom_ls.parquet"


@st.cache_data(show_spinner=False)
def _parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def loadings_table(loadings: pd.DataFrame, se: pd.DataFrame) -> pd.DataFrame:
    """Loadings next to Newey-West standard errors for every factor."""
    table = loadings.copy()
    if isinstance(se.columns, pd.MultiIndex):
        nw = se["nw_l5"] if "nw_l5" in se.columns.get_level_values(0) else se.iloc[:, :0]
    else:
        nw = se
    for column in nw.columns:
        table[f"{column}_nw_se"] = nw[column]
    return table


def beta_overlay(history: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Raw, Vasicek and Blume beta history for one ticker."""
    out = {}
    for method in ("raw", "vasicek", "blume"):
        if (method, ticker) in history.columns:
            out[method] = history[(method, ticker)]
    frame = pd.DataFrame(out)
    frame.index.name = "date"
    return frame


def r2_distribution(loadings: pd.DataFrame) -> pd.Series:
    """R squared across the universe."""
    return loadings["r_squared"].dropna()


def idio_vs_total(idio: pd.DataFrame, returns_wide: pd.DataFrame) -> pd.DataFrame:
    """Idio annualized vol against realized total vol per name."""
    total = returns_wide.std(ddof=1) * np.sqrt(252.0)
    frame = pd.DataFrame(
        {
            "idio_vol_ann": idio["idio_vol_ann"],
            "total_vol_ann": total,
        }
    ).dropna()
    frame.index.name = "ticker"
    return frame.reset_index()


def vol_summary(table: pd.DataFrame, baseline: str = "trailing_252") -> pd.DataFrame:
    """Mean QLIKE and win share per volatility method."""
    summary = table.groupby("method")["qlike"].mean().rename("mean_qlike").to_frame()
    wins = vol_mod.beats_baseline(table, baseline=baseline).set_index("method")
    summary = summary.join(wins[["win_share", "n_names"]])
    return summary.sort_values("mean_qlike")


def beta_race_table(race: pd.DataFrame) -> pd.DataFrame:
    """Beta horse race sorted by RMSE."""
    return race.sort_values("rmse").reset_index(drop=True)


def portfolio_exposure(
    weights_long: pd.DataFrame, loadings: pd.DataFrame, date: str
) -> pd.DataFrame:
    """Weights at a date next to each name's factor loadings."""
    stamp = pd.Timestamp(date)
    rows = weights_long[pd.to_datetime(weights_long["date"]) == stamp]
    frame = rows.set_index("ticker")[["weight"]].join(loadings, how="left")
    return frame.reset_index()


def render() -> None:
    st.title("D1 Exposures")
    loadings = _parquet(LOADINGS)
    se = _parquet(LOADINGS_SE)
    idio = _parquet(IDIO)
    history = _parquet(BETA_HISTORY)
    vol_table = _parquet(VOL_RACE)
    beta_race = _parquet(BETA_RACE)
    snapshot = _parquet(RISK_SNAPSHOT)
    returns_wide = _parquet(RETURNS)["r"].unstack("ticker")

    st.subheader("Loadings with Newey-West standard errors")
    table = loadings_table(loadings, se)
    st.dataframe(table.head(300), use_container_width=True)

    st.subheader("Rolling beta: raw, Vasicek, Blume")
    ticker = st.selectbox("Ticker", sorted(loadings.index))
    overlay = beta_overlay(history, ticker)
    fig = px.line(overlay, labels={"value": "beta", "date": "date"})
    st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("R squared distribution")
        st.plotly_chart(
            px.histogram(r2_distribution(loadings), nbins=40),
            use_container_width=True,
        )
    with col2:
        st.subheader("Idio vs total vol")
        st.plotly_chart(
            px.scatter(
                idio_vs_total(idio, returns_wide),
                x="total_vol_ann",
                y="idio_vol_ann",
                hover_name="ticker",
            ),
            use_container_width=True,
        )

    st.subheader("Volatility estimator comparison (out-of-sample QLIKE)")
    st.dataframe(vol_summary(vol_table), use_container_width=True)

    st.subheader("Portfolio exposure panel")
    book = st.selectbox("Seed portfolio", ["seed_ew", "seed_mom_ls"])
    weights_long = _parquet(SEED_EW if book == "seed_ew" else SEED_LS)
    last_date = pd.to_datetime(weights_long["date"]).max()
    st.dataframe(
        portfolio_exposure(weights_long, loadings, str(last_date.date())),
        use_container_width=True,
    )
    st.dataframe(snapshot, use_container_width=True)

    st.subheader("Beta horse race: next-quarter realized beta")
    st.dataframe(beta_race_table(beta_race), use_container_width=True)
