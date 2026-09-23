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
CONSTRUCTION_TABLE_PATH = LIVE / "construction_table.parquet"
CONSTRUCTION_WEIGHTS_PATH = LIVE / "construction_weights.parquet"

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


def load_construction_table() -> pd.DataFrame:
    if not CONSTRUCTION_TABLE_PATH.exists():
        raise ValueError("D10 panel construction read an empty construction table")
    return _require(pd.read_parquet(CONSTRUCTION_TABLE_PATH), "construction table")


def load_construction_weights() -> pd.DataFrame:
    if not CONSTRUCTION_WEIGHTS_PATH.exists():
        raise ValueError("D10 panel construction read an empty construction weights")
    return _require(pd.read_parquet(CONSTRUCTION_WEIGHTS_PATH), "construction weights")


def dry_run_state() -> str:
    """True when every reconciliation row is dry run, else the clock started."""
    path = STATE_DIR / "reconciliation.parquet"
    if not path.exists():
        return "dry run (no reconciliation yet)"
    frame = pd.read_parquet(path)
    if frame.empty or "dry_run" not in frame.columns:
        return "dry run (no reconciliation yet)"
    return (
        "dry run (the clock has not started)"
        if bool(frame["dry_run"].all())
        else "live (the clock has started)"
    )


def proposal_names_panel() -> pd.DataFrame:
    """The stored proposal's names, weights and per-name trade reasons."""
    weights = load_proposal_weights()
    out = weights[["ticker", "side", "weight", "z", "alpha"]].copy()
    out = out.reindex(out["weight"].abs().sort_values(ascending=False).index)
    return _require(out, "proposal names")


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
    """The continuous clock: open-ended run, a thirty-day reporting window."""
    clock = load_clock()
    return _require(
        pd.DataFrame(
            [
                {
                    "day 1": clock["day_1"],
                    "reporting window end": clock["end_date"],
                    "reporting window days": clock["trading_days"],
                    "run condition": clock.get("run_condition", "open_ended"),
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


def construction_label() -> dict:
    """Which construction the stored proposal renders, and its parameters."""
    proposal = load_latest_proposal()
    construction = f"min position ${proposal['min_position_dollars']:,.0f}"
    return {
        "as of (close)": proposal["as_of"],
        "construction on disk": construction,
        "n names kept": proposal["n_kept"],
        "n names dropped": proposal["n_dropped"],
        "kept gross before renormalization": f"{proposal['kept_gross']:.4f}",
        "run state": dry_run_state(),
    }


def construction_selector() -> None:
    """Page through the seven books the construction table computed."""
    table = load_construction_table()
    weights = load_construction_weights()
    labels = table["construction"].tolist()
    default = "min_position_5000" if "min_position_5000" in labels else labels[0]
    chosen = st.selectbox(
        "Construction to inspect",
        labels,
        index=labels.index(default),
        format_func=lambda label: label.replace("_", " "),
    )
    row = table.loc[table["construction"] == chosen].iloc[0]
    flagged = bool(row["flagged_for_veto"])
    st.markdown(
        f"#### {chosen.replace('_', ' ')}"
        + (" (flagged for the owner's veto)" if flagged else "")
    )
    summary = pd.DataFrame(
        [
            {
                "metric": "kept names",
                "value": (
                    f"{int(row['n_kept'])} "
                    f"(pre-iteration {int(row['n_kept_pre_iteration'])})"
                ),
            },
            {"metric": "effective names", "value": f"{int(row['n_effective'])}"},
            {
                "metric": "long / short",
                "value": f"{int(row['n_long'])} / {int(row['n_short'])}",
            },
            {
                "metric": "gross before renormalization",
                "value": f"{row['kept_gross_before_renorm']:.4f}",
            },
            {
                "metric": "net dollar share of gross",
                "value": f"{row['net_dollar_share_of_gross']:.2e}",
            },
            {
                "metric": "realized market beta (raw CAPM)",
                "value": f"{row['realized_market_beta']:.4f}",
            },
            {
                "metric": "beta: names filled at the median",
                "value": f"{int(row['n_beta_filled'])}",
            },
            {
                "metric": "beta: raw excluding the fills",
                "value": f"{row['realized_market_beta_ex_fills']:.4f}",
            },
            {
                "metric": "beta: pre-winsorization (Vasicek)",
                "value": f"{row['realized_market_beta_shrunk']:.4f}",
            },
            {
                "metric": "beta: XS-v1's own descriptor",
                "value": f"{row['realized_market_beta_descriptor']:.2e}",
            },
            {
                "metric": "beta: raw-vs-descriptor correlation",
                "value": f"{row['corr_raw_vs_descriptor']:.4f}",
            },
            {
                "metric": "median / p10 share count",
                "value": (
                    f"{row['median_share_count']:.1f} / "
                    f"{row['p10_share_count']:.1f}"
                ),
            },
            {
                "metric": "median quantization error",
                "value": f"{row['quant_error_median_pct_of_target']:.4%}",
            },
            {
                "metric": "p90 quantization error",
                "value": (
                    f"{row['quant_error_p90_pct_of_target']:.4%} "
                    f"(pre-iteration {row['quant_error_p90_pre_iteration']:.4%})"
                ),
            },
            {
                "metric": "total gross error share of NAV",
                "value": f"{row['total_gross_error_share_of_nav']:.4%}",
            },
            {
                "metric": "post-hedge max factor exposure",
                "value": f"{row['post_hedge_max_abs_exposure']:.2e}",
            },
            {
                "metric": "post-hedge idio share",
                "value": f"{row['post_hedge_idio_share']:.4f}",
            },
            {
                "metric": "max weight share of gross",
                "value": f"{row['max_weight_share_of_gross']:.4%}",
            },
            {"metric": "breadth naive", "value": f"{row['breadth_naive']:.3f}"},
            {"metric": "breadth governing", "value": f"{row['breadth_governing']:.3f}"},
            {"metric": "n_eff kept", "value": f"{row['n_eff_kept']:.2f}"},
        ]
    )
    st.dataframe(summary, use_container_width=True, hide_index=True)
    names = weights.loc[
        weights["construction"] == chosen, ["ticker", "side", "weight", "z", "alpha"]
    ].reindex(
        weights.loc[weights["construction"] == chosen, "weight"]
        .abs()
        .sort_values(ascending=False)
        .index
    )
    st.markdown("**Names and weights, largest first**")
    st.dataframe(names, use_container_width=True, hide_index=True)


def render() -> None:
    st.caption(
        "The strategy-review view. Lead with the answer: this book is a null "
        "book, run to prove the machinery, not the signal."
    )
    try:
        label = construction_label()
    except ValueError as exc:
        st.caption(f"No data yet: {exc}")
        return
    st.markdown("### What is on screen")
    st.markdown(
        f"The stored dry-run proposal is the book for the **{label['as of (close)']}** "
        f"close, sized at **{label['construction on disk']}**, "
        f"**{label['n names kept']}** names kept and "
        f"**{label['n names dropped']}** dropped, kept gross before "
        f"renormalization **{label['kept gross before renormalization']}**. "
        f"Run state: **{label['run state']}**. "
        "The selector below pages through the seven books the construction "
        "table computed, so the page is the decision surface, not a single "
        "arbitrary book."
    )
    construction_selector()
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
    _render_frame("The proposal's names and trade reasons", proposal_names_panel)
    _render_frame("Forecast against outcome", reconciliation_panel)
    _render_frame("Guard events", guards_panel)
    _render_frame("The continuous live clock", clock_panel)
