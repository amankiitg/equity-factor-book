"""D6 Alpha Lab: signal evaluation and the multiple-testing ledger.

Sprint E7, Task 6. Reads parquet and the ledger markdown only, never fits a
model. Every panel builder goes through `_require`, which raises on an empty
read, so a panel that loses its artifact fails loudly instead of drawing an
empty chart. The expected-return calculator labels every input and output on
screen: alpha = IC x sigma_idio x z, shrunk by kappa.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import version as version_module

ROOT = version_module.ROOT
DATA = ROOT / "data"
ALPHA = DATA / "alpha"
LEDGER_PATH = ROOT / "docs" / "multiple_testing_ledger.md"

SIGNALS = (
    "momentum_12_1",
    "short_term_reversal",
    "idio_momentum",
    "low_residual_volatility",
    "short_interest",
    "post_earnings_drift",
)


def _require(frame: pd.DataFrame, what: str) -> pd.DataFrame:
    """A panel must not draw on an empty read."""
    if frame is None or frame.empty:
        raise ValueError(f"D6 panel {what} read an empty artifact")
    return frame


def load_summary() -> pd.DataFrame:
    frame = pd.read_parquet(ALPHA / "summary.parquet")
    return _require(frame, "signal summary")


def load_signal(name: str, stem: str) -> pd.DataFrame:
    frame = pd.read_parquet(ALPHA / name / f"{stem}.parquet")
    return _require(frame, f"{name} {stem}")


def ic_panel(name: str) -> pd.DataFrame:
    """The daily IC series at all four horizons."""
    return _require(load_signal(name, "ic"), f"{name} IC")


def decay_panel(name: str) -> pd.DataFrame:
    """The decay curve: mean IC per horizon."""
    ic = ic_panel(name)
    columns = [c for c in ic.columns if c.startswith("ic_h")]
    rows = [
        {"horizon": int(c.split("h")[1]), "mean_ic": float(ic[c].mean())}
        for c in columns
    ]
    return pd.DataFrame(rows)


def neutral_panel(name: str) -> pd.DataFrame:
    """The factor-neutral IC series at the rebalance grid."""
    return _require(load_signal(name, "neutral_ic"), f"{name} neutral IC")


def quantile_panel(name: str) -> pd.DataFrame:
    """The quintile returns, the spread and the hit rate."""
    quantiles = _require(load_signal(name, "quantiles"), f"{name} quantiles")
    pivot = quantiles.pivot_table(index="date", columns="quantile", values="return")
    spread = (
        pivot[5] - pivot[1] if {1, 5} <= set(pivot.columns) else pd.Series(dtype=float)
    )
    rows: list[dict[str, object]] = [
        {
            "quantile": "hit_rate",
            "mean_return": float((spread > 0).mean()) if len(spread) else float("nan"),
        },
        {
            "quantile": "spread_mean_daily",
            "mean_return": float(spread.mean()) if len(spread) else float("nan"),
        },
    ]
    rows.extend(
        {"quantile": int(q), "mean_return": float(pivot[q].mean())}
        for q in pivot.columns
    )
    return pd.DataFrame(rows)


def regime_panel(name: str) -> pd.DataFrame:
    """The IC within VIX terciles."""
    return _require(load_signal(name, "regime_ic"), f"{name} regime IC")


def ledger_panel() -> pd.DataFrame:
    """The multiple-testing ledger as a table."""
    lines = LEDGER_PATH.read_text().splitlines()
    rows: list[dict[str, object]] = []
    for line in lines:
        if line.startswith("| ") and not line.startswith("| run_id"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) >= 11:
                rows.append(
                    {
                        "run_id": cells[0],
                        "signal": cells[1],
                        "variant": cells[2],
                        "horizon": cells[3],
                        "ic_mean": cells[4],
                        "t_stat": cells[5],
                        "deflated_sharpe": cells[6],
                        "hlz_t_hurdle": cells[7],
                        "bonferroni_t": cells[8],
                        "verdict": cells[9],
                        "note": cells[10],
                    }
                )
    return _require(pd.DataFrame(rows), "the multiple-testing ledger")


def alpha_calculator() -> pd.DataFrame:
    """The expected-return calculator: alpha = IC x sigma_idio x z x kappa."""
    ic = st.number_input(
        "IC (information coefficient)", value=0.02, step=0.001, format="%.3f"
    )
    sigma_idio = st.number_input(
        "sigma_idio (daily idio vol)", value=0.012, step=0.001, format="%.3f"
    )
    z = st.number_input("z-score of the signal", value=1.0, step=0.1, format="%.2f")
    kappa = st.number_input(
        "kappa (shrinkage toward zero)", value=0.1, step=0.01, format="%.2f"
    )
    alpha_daily = ic * sigma_idio * z * kappa
    alpha_bp = alpha_daily * 10_000.0
    return pd.DataFrame(
        [
            {
                "input": "IC",
                "value": ic,
                "unit": "rank correlation",
            },
            {
                "input": "sigma_idio",
                "value": sigma_idio,
                "unit": "daily",
            },
            {
                "input": "z",
                "value": z,
                "unit": "standard deviations",
            },
            {
                "input": "kappa",
                "value": kappa,
                "unit": "shrinkage",
            },
            {
                "input": "alpha (daily)",
                "value": alpha_daily,
                "unit": "fraction per day",
            },
            {
                "input": "alpha (bp per day)",
                "value": alpha_bp,
                "unit": "basis points per day",
            },
        ]
    )


def render() -> None:
    summary = load_summary()
    st.dataframe(summary, use_container_width=True)
    st.caption("The signal summary is the stored artifact behind F7.1 to F7.4.")
    st.markdown("### Multiple-Testing Ledger")
    st.dataframe(ledger_panel(), use_container_width=True)
    st.markdown("### One signal, full record")
    chosen = st.selectbox("Signal", SIGNALS)
    st.markdown("#### IC decay")
    st.dataframe(decay_panel(chosen), use_container_width=True)
    st.markdown("#### Factor-neutral IC")
    st.dataframe(neutral_panel(chosen).tail(100), use_container_width=True)
    st.markdown("#### Quantile spread")
    st.dataframe(quantile_panel(chosen), use_container_width=True)
    st.markdown("#### Regime IC")
    st.dataframe(regime_panel(chosen), use_container_width=True)
    st.markdown("### Expected-return calculator")
    st.dataframe(alpha_calculator(), use_container_width=True)
