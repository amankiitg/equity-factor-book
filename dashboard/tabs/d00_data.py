"""Dashboard tab D0: Data Health (Sprint E1, Task 8).

Reads parquet and the Hygiene Ledger only; never recomputes a number that
should live in an artifact. Panels: coverage heatmap, missing and stale
counts, universe size with additions and deletions, event log, the ledger
rendered in-app, and the data version hash in the global sidebar.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
PRICES = DATA / "raw" / "prices.parquet"
RETURNS = DATA / "processed" / "returns.parquet"
MEMBERS = DATA / "processed" / "universe_membership.parquet"
EVENTS = DATA / "processed" / "events.parquet"
LEDGER = ROOT / "docs" / "hygiene_ledger.md"


@st.cache_data(show_spinner=False)
def load_prices() -> pd.DataFrame:
    return pd.read_parquet(PRICES)


@st.cache_data(show_spinner=False)
def load_returns() -> pd.DataFrame:
    return pd.read_parquet(RETURNS)


@st.cache_data(show_spinner=False)
def load_members() -> pd.DataFrame:
    return pd.read_parquet(MEMBERS)


@st.cache_data(show_spinner=False)
def load_events() -> pd.DataFrame:
    return pd.read_parquet(EVENTS)


def coverage_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    """Ticker x month matrix of the fraction of business days covered.

    Month labels are strings (YYYY-MM) so the matrix serializes cleanly
    into Plotly.
    """
    dates = prices.index.get_level_values("date")
    months = dates.to_period("M").astype(str)
    adj = prices["adj_close"]
    present = adj.notna()
    present.index = pd.MultiIndex.from_arrays(
        [months, present.index.get_level_values("ticker")], names=["month", "ticker"]
    )
    return present.groupby(["month", "ticker"]).mean().unstack("ticker")


def missing_tickers(
    returns_frame: pd.DataFrame, as_of: str, window: int = 5
) -> list[str]:
    """Tickers with no return in the last `window` business days."""
    cutoff = pd.Timestamp(as_of)
    recent = returns_frame[
        returns_frame.index.get_level_values("date")
        >= cutoff - pd.Timedelta(days=window * 2)
    ]
    have = recent.groupby(level="ticker")["r"].apply(lambda s: s.notna().any())
    return sorted(have[~have].index.tolist())


def stale_counts(returns_frame: pd.DataFrame) -> pd.Series:
    """Stale-flag days per ticker."""
    return (
        returns_frame.groupby(level="ticker")["stale"]
        .sum()
        .sort_values(ascending=False)
    )


def universe_size(members: pd.DataFrame) -> pd.Series:
    """Number of members per date."""
    return members.sum(axis=1)


def membership_change_summary(members: pd.DataFrame) -> pd.DataFrame:
    """Per-date additions and removals as a wide DataFrame."""
    diff = members.astype(int).diff()
    return pd.DataFrame(
        {
            "added": (diff == 1).sum(axis=1),
            "removed": (diff == -1).sum(axis=1),
        }
    ).fillna(0)


def event_counts(events: pd.DataFrame) -> pd.Series:
    """Number of events per type."""
    return events["event_type"].value_counts()


def render() -> None:
    st.title("D0 Data Health")
    prices = load_prices()
    returns_frame = load_returns()
    members = load_members()
    events = load_events()

    st.subheader("Coverage heatmap: ticker x month")
    cov = coverage_matrix(prices)
    fig = px.imshow(
        cov.T,
        labels=dict(x="month", y="ticker", color="coverage"),
        aspect="auto",
        color_continuous_scale="RdYlGn",
        zmin=0.0,
        zmax=1.0,
    )
    fig.update_layout(height=520)
    st.plotly_chart(fig, width="stretch")

    st.subheader("Missing and stale counts")
    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            "Tickers with no data in the last 5 business days",
            len(
                missing_tickers(
                    returns_frame,
                    as_of=str(returns_frame.index.get_level_values("date").max()),
                )
            ),
        )
    with col2:
        st.metric(
            "Stale zero-return runs (>= 5 days)",
            int(events["event_type"].eq("stale_start").sum()) if len(events) else 0,
        )
    st.dataframe(stale_counts(returns_frame).rename("stale_days"), width="stretch")

    st.subheader("Universe size over time")
    size = universe_size(members)
    changes = membership_change_summary(members)
    fig2 = px.line(size, labels=dict(index="date", value="members"))
    st.plotly_chart(fig2, width="stretch")
    st.dataframe(changes[changes.any(axis=1)], width="stretch")

    st.subheader("Corporate-action and outlier event log")
    st.dataframe(event_counts(events).rename("count"), width="stretch")
    st.dataframe(events.sort_values("date", ascending=False).head(200), width="stretch")

    st.subheader("Hygiene Ledger")
    st.markdown(LEDGER.read_text())
