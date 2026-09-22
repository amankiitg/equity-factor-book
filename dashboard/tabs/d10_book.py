"""D10 Book Monitor: the strategy-review view of the paper book.

Sprint E11, Task 8. Built for someone deciding whether the book is doing
what it was built to do, not for someone auditing a pipeline. It leads
with the answer: this is a null book. Every number carries its n and its
units, one idea per panel, and every panel builder raises on an empty
read.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from dashboard import version as version_module

ROOT = version_module.ROOT
DATA = ROOT / "data"
LIVE = ROOT / "live"
PROPOSAL_DIR = LIVE / "proposals"
EXECUTION_LOG_DIR = LIVE / "logs"
STATE_DIR = LIVE / "state"
CLOCK_PATH = LIVE / "clock.json"

SIGNAL = "idio_momentum"
EXPECTED_E12_VERDICT = "luck"


def _require(frame: pd.DataFrame | dict | None, what: str):
    if frame is None or (isinstance(frame, (pd.DataFrame, pd.Series)) and frame.empty):
        raise ValueError(f"D10 panel {what} read an empty artifact")
    return frame


def load_latest_proposal() -> dict:
    proposals = sorted(PROPOSAL_DIR.glob("proposal_*.json"))
    if not proposals:
        raise ValueError("D10 panel book read an empty proposal directory")
    return json.loads(proposals[-1].read_text())


def load_proposal_weights() -> pd.DataFrame:
    proposal = load_latest_proposal()
    path = PROPOSAL_DIR / f"proposal_{proposal['as_of']}.parquet"
    return _require(pd.read_parquet(path), "weights")


def load_reconciliation() -> pd.DataFrame:
    path = STATE_DIR / "reconciliation.parquet"
    if not path.exists():
        raise ValueError("D10 panel reconciliation read an empty artifact")
    return _require(pd.read_parquet(path), "reconciliation")


def load_execution() -> pd.DataFrame:
    logs = sorted(EXECUTION_LOG_DIR.glob("execution_*.parquet"))
    if not logs:
        raise ValueError("D10 panel guards read an empty execution log")
    return _require(pd.read_parquet(logs[-1]), "execution log")


def load_clock() -> dict:
    if not CLOCK_PATH.exists():
        raise ValueError("D10 panel clock read an empty artifact")
    return json.loads(CLOCK_PATH.read_text())


def answer_panel() -> dict:
    """The answer, first and impossible to miss: this is a null book."""
    summary = pd.read_parquet(DATA / "alpha" / "summary.parquet")
    row = summary.loc[summary["signal"] == SIGNAL]
    if row.empty:
        raise ValueError(f"D10 panel answer read no summary row for {SIGNAL}")
    proposal = load_latest_proposal()
    return {
        "what this book is": "null book",
        "signal": SIGNAL,
        "factor-neutral IC, horizon 21": float(row["neutral_ic_h21_mean"].iloc[0]),
        "factor-neutral t": float(row["neutral_ic_h21_t"].iloc[0]),
        "raw IC, horizon 1": float(row["ic_h1_mean"].iloc[0]),
        "raw t, horizon 1": float(row["ic_h1_t"].iloc[0]),
        "expected E12 verdict (pre-written)": EXPECTED_E12_VERDICT,
        "n names in the book": int(proposal["n_names"]),
    }


def book_panel() -> pd.DataFrame:
    """The book's own numbers, every one with its unit and its n."""
    proposal = load_latest_proposal()
    return _require(
        pd.DataFrame(
            [
                {
                    "as of (close)": proposal["as_of"],
                    "n names": proposal["n_names"],
                    "n excluded from the frozen model": proposal["n_excluded"],
                    "idio share after FMP (unitless)": proposal["idio_share_after_fmp"],
                    "gross (fraction of NAV)": proposal["gross"],
                    "net (fraction of NAV)": proposal["net"],
                    "effective breadth (n_eff)": proposal["n_eff"],
                    "target annual vol (%)": proposal["target_annual_vol"] * 100,
                    "achieved annual vol (%)": proposal["achieved_annual_vol"] * 100,
                    "gross cap bound": proposal["gross_cap_bound"],
                    "expected establishment cost (bps)": (
                        proposal["expected_establishment_cost_bps"]
                    ),
                }
            ]
        ),
        "book",
    )


def reconciliation_panel() -> pd.DataFrame:
    """Forecast beside outcome, one row per trading day."""
    frame = load_reconciliation()
    out = frame[
        [
            "trade_date",
            "forecast_annual_vol",
            "realized_annual_vol",
            "idio_share_after_fmp",
            "gross",
            "net",
            "intended_notional",
            "filled_notional",
            "dry_run",
        ]
    ].copy()
    return _require(out, "reconciliation")


def guards_panel() -> pd.DataFrame:
    """The guard events: what the two fail-safes rejected and why."""
    frame = load_execution()
    statuses = frame["status"].value_counts().to_frame("n orders")
    statuses.index.name = "status"
    return _require(statuses.reset_index(), "guards")


def clock_panel() -> pd.DataFrame:
    """The thirty-trading-day clock, day 1 and the end date."""
    clock = load_clock()
    return _require(
        pd.DataFrame(
            [
                {
                    "day 1": clock["day_1"],
                    "end date": clock["end_date"],
                    "trading days": clock["trading_days"],
                    "started": clock.get("started", True),
                }
            ]
        ),
        "clock",
    )


def _render_frame(title: str, builder) -> None:
    st.markdown(f"### {title}")
    try:
        st.dataframe(builder(), use_container_width=True)
    except ValueError as exc:
        st.caption(f"No data yet: {exc}")


def render() -> None:
    st.caption(
        "The strategy-review view. Lead with the answer: this book is a null "
        "book, run to prove the machinery, not the signal."
    )
    try:
        answer = answer_panel()
    except ValueError as exc:
        st.caption(f"No data yet: {exc}")
        return
    st.markdown("### The answer")
    st.markdown(
        f"This is a **null book**. `{answer['signal']}` has factor-neutral IC "
        f"{answer['factor-neutral IC, horizon 21']:.4f} (t "
        f"{answer['factor-neutral t']:.2f}) at horizon 21, null rather than "
        f"negative, against a raw IC of {answer['raw IC, horizon 1']:.4f} (t "
        f"{answer['raw t, horizon 1']:.2f}). The expected E12 verdict, "
        f"written before the clock started, is "
        f"**{answer['expected E12 verdict (pre-written)']}**."
    )
    _render_frame("The book", book_panel)
    _render_frame("Forecast against outcome", reconciliation_panel)
    _render_frame("Guard events", guards_panel)
    _render_frame("The thirty-trading-day clock", clock_panel)
