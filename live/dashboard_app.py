"""The Render live dashboard.

Reads the live series from Supabase (through live.store, which falls back
to local files when Supabase is not configured) plus two tiny files: the
clock and the cost reconciliation. It never reads a research parquet, so
no file over 5 MB is touched. It leads with the answer: this is a null
book, run to prove the machinery, not the signal.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]

st.set_page_config(page_title="EFB Live", layout="wide")
st.title("Equity Factor Book: the live book")


@st.cache_data(ttl=60)
def load_clock() -> dict:
    return json.loads((ROOT / "live" / "clock.json").read_text())


@st.cache_data(ttl=60)
def load_table(name: str) -> pd.DataFrame:
    from live import store

    return store.select(name)


def _latest_proposal() -> dict | None:
    frame = load_table("proposals")
    if frame.empty:
        return None
    frame = frame.sort_values("trade_date")
    row = frame.iloc[-1]
    return json.loads(row["manifest"]) if row.get("manifest") else dict(row)


def _no_data(caption: str = "No live data yet.") -> None:
    st.caption(caption)


clock = load_clock()
proposals = load_table("proposals")
positions = load_table("positions")
orders = load_table("orders")
reconciliation = load_table("reconciliation")
nav = load_table("nav")
cron_runs = load_table("cron_runs")
manifest = _latest_proposal()

# 1. Status
st.header("Status")
if not clock.get("started"):
    st.warning("The clock is not started.")
else:
    last_run = "never"
    if not cron_runs.empty:
        last_run = str(cron_runs.sort_values("run_date")["run_date"].iloc[-1])
    day_1 = pd.Timestamp(clock["day_1"])
    day_count = (pd.Timestamp.today().normalize() - day_1).days
    window_end = pd.Timestamp(clock.get("end_date", clock["day_1"]))
    st.markdown(
        f"**Run condition: {clock.get('run_condition', 'open_ended')}.** "
        f"Day 1 {clock['day_1']}, day count {day_count}, reporting window "
        f"ends {str(window_end.date())} (the window is a reporting slice, "
        f"not the life of the loop). Last run: {last_run}."
    )
    if manifest is not None:
        input_as_of = manifest.get("input_as_of", {})
        st.markdown(
            f"Staleness: max {manifest.get('max_input_staleness_days')} days. "
            f"Inputs as of: "
            + ", ".join(f"{key} {value}" for key, value in input_as_of.items())
        )

# 2. The answer
st.header("The answer")
if manifest is None:
    _no_data("No proposal yet: the loop has not produced a book.")
else:
    st.markdown(
        f"This is a **null book**. `{manifest['signal']}` has factor-neutral "
        f"IC {manifest.get('factor_neutral_ic_h21', float('nan')):.4f} "
        f"(t {manifest.get('factor_neutral_t_h21', float('nan')):.2f}) at "
        f"horizon 21, null rather than negative. The book is run to prove "
        f"the machinery, not the signal."
    )

# 3. Tracking metrics
st.header("Tracking")
if reconciliation.empty:
    _no_data("No realized outcomes yet: the loop has not accrued a day.")
else:
    recon = reconciliation.sort_values("trade_date")
    realized = recon["realized_annual_vol"].dropna()
    cost_paid = recon["filled_notional"].sum()
    cost_expected = recon["expected_cost_bps"].sum()
    col1, col2, col3 = st.columns(3)
    col1.metric("days stored", int(len(recon)))
    col2.metric(
        "realized vol (annual)",
        (f"{float(realized.mean()):.3f}" if len(realized) else "no data"),
    )
    col3.metric(
        "cost paid vs expected (bp)",
        (f"{cost_paid:.2f} / {cost_expected:.2f}" if cost_expected else "no data"),
    )
    if len(realized) >= 2:
        sharpe = (
            float(realized.mean() / realized.std(ddof=1)) if realized.std() else 0.0
        )
        se = float(realized.std(ddof=1) / (len(realized) ** 0.5))
        t = float(sharpe / se) if se else 0.0
        claim = (
            "Skill is claimed: t above 2."
            if t > 2
            else "No skill is claimed: t at or below 2."
        )
        st.markdown(f"Sharpe {sharpe:.3f}, standard error {se:.3f}, t {t:.2f}. {claim}")

# 4. The book
st.header("The book")
if manifest is None:
    _no_data()
else:
    book = pd.DataFrame(
        [
            {
                "as of (close)": manifest["as_of"],
                "n names": manifest["n_names"],
                "n excluded from the frozen model": manifest["n_excluded"],
                "gross (fraction of NAV)": manifest["gross"],
                "net (fraction of NAV)": manifest["net"],
                "effective breadth (n_eff)": manifest["n_eff"],
                "idio share after FMP": manifest["idio_share_after_fmp"],
                "target annual vol": manifest["target_annual_vol"],
                "achieved annual vol": manifest["achieved_annual_vol"],
                "expected establishment cost (bp)": (
                    manifest["expected_establishment_cost_bps"]
                ),
                "max input staleness (days)": manifest["max_input_staleness_days"],
            }
        ]
    )
    st.dataframe(book, use_container_width=True)

# 5. Hedge
st.header("Hedge")
if manifest is None:
    _no_data()
else:
    st.markdown(
        f"The exact in-model FMP hedge drives every modeled factor exposure "
        f"to zero: max absolute exposure after the hedge "
        f"{manifest['max_abs_exposure_after_fmp']:.2e}, idio share after the "
        f"hedge {manifest['idio_share_after_fmp']:.3f}. The hedge is part of "
        f"Procedure 6.3, so it is on for every position; it costs no extra "
        f"names because it is a linear transform of the design."
    )

# 6. Trade explanation, per name
st.header("Every position, and why it trades today")
if positions.empty:
    _no_data()
else:
    latest_date = str(positions["trade_date"].max())
    day = positions[positions["trade_date"] == latest_date].sort_values("rank")
    shown = day[
        [
            "ticker",
            "rank",
            "alpha",
            "z",
            "idio_vol",
            "weight",
            "previous_weight",
            "trade",
            "reason",
        ]
    ]
    st.markdown(
        f"{len(day)} positions as of {latest_date}. Every row carries a "
        f"stated reason: alpha moved, risk moved, the hedge moved, or "
        f"drifted past a band. A trade with no stated reason is a bug."
    )
    st.dataframe(shown, use_container_width=True, height=480)

# Footer: where state lives
st.caption(
    "State: the live series lives in Supabase (live/store.py), keyed by "
    "date; research artifacts stay in git and the evidence snapshot."
)
