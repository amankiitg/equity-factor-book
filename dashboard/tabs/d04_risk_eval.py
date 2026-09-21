"""D4 Risk Model Evaluation: bias, calibration, horizons and the champion.

Sprint E5, Task 8. Reads parquet only and never fits a model. Every panel
builder goes through `_require`, which raises on an empty read, so a panel
that loses its artifact fails loudly instead of drawing an empty chart. The
champion badge reads the registry rather than a constant, so it can never
disagree with the declared champion.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from dashboard import version as version_module

ROOT = version_module.ROOT
REGISTRY = version_module.REGISTRY


def _require(frame: pd.DataFrame, what: str) -> pd.DataFrame:
    """A panel must not draw on an empty read."""
    if frame is None or frame.empty:
        raise ValueError(f"D4 panel {what} read an empty artifact")
    return frame


def load_family_bias() -> pd.DataFrame:
    frame = pd.read_parquet(ROOT / "data" / "eval" / "e5_family_bias.parquet")
    return _require(frame, "family bias")


def load_summary() -> pd.DataFrame:
    frame = pd.read_parquet(ROOT / "data" / "eval" / "e5_bias_summary.parquet")
    return _require(frame, "bias summary")


def load_regimes() -> pd.DataFrame:
    frame = pd.read_parquet(ROOT / "data" / "eval" / "e5_regimes.parquet")
    return _require(frame, "regime table")


def load_rolling() -> pd.DataFrame:
    frame = pd.read_parquet(ROOT / "data" / "eval" / "e5_rolling_bias.parquet")
    return _require(frame, "rolling bias")


def load_horizon() -> pd.DataFrame:
    frame = pd.read_parquet(ROOT / "data" / "eval" / "e5_horizon.parquet")
    return _require(frame, "horizon table")


def load_haircut() -> pd.DataFrame:
    frame = pd.read_parquet(ROOT / "data" / "eval" / "e5_stress_haircut.parquet")
    return _require(frame, "stress haircut")


def bias_heatmap_panel() -> pd.DataFrame:
    """Bias by version, family and regime: the long form a heatmap pivots on."""
    regimes = _require(load_regimes(), "bias heatmap")
    return regimes.loc[
        regimes["regime"].isin(("vix_low", "vix_mid", "vix_high", "2020_q1", "2022")),
        ["version", "family", "regime", "bias"],
    ]


def rolling_bias_panel() -> pd.DataFrame:
    """The rolling 12-month bias with its delta-method band."""
    rolling = _require(load_rolling(), "rolling bias")
    return rolling.sort_values(["version", "family", "date"])


def calibration_panel() -> pd.DataFrame:
    """Bias, coverage, MAD and the Q-Q pair, pooled per version and family."""
    summary = _require(load_summary(), "calibration")
    pooled = summary.loc[summary["portfolio"] == "pooled"].copy()
    return pooled.loc[
        :,
        [
            "version",
            "family",
            "bias",
            "bias_lower",
            "bias_upper",
            "coverage",
            "mad_ratio",
            "qq_slope",
            "qq_intercept",
        ],
    ]


def horizon_panel() -> pd.DataFrame:
    return _require(load_horizon(), "horizon table")


def champion_badge() -> dict:
    """The champion, its rule and the deciding number, read from the registry.

    The deciding number is the champion's mean |bias-1| across families, the
    value the rule minimizes, recomputed from the stored table rather than
    retyped.
    """
    payload = json.loads(REGISTRY.read_text())
    champions = [
        name for name, entry in payload["models"].items() if entry.get("champion")
    ]
    if not champions:
        return {
            "champion": None,
            "rule": payload.get("champion_rule", ""),
            "deciding_number": float("nan"),
        }
    champion = champions[0]
    from efb import registry as registry_module

    tag = registry_module.engine_tag(champion)
    family = _require(load_family_bias(), "champion badge")
    rows = family.loc[family["version"] == tag]
    deciding = float(rows["abs_bias_minus_1"].mean()) if len(rows) else float("nan")
    return {
        "champion": champion,
        "rule": payload.get("champion_rule", ""),
        "deciding_number": deciding,
    }


def render() -> None:
    badge = champion_badge()
    if badge["champion"] is None:
        st.warning("No champion is declared yet.")
    else:
        st.success(
            f"Champion: **{badge['champion']}**  |  deciding number "
            f"(mean |bias-1| across families) **{badge['deciding_number']:.4f}**"
        )
        st.caption(f"Rule: {badge['rule']}")
        try:
            haircut = load_haircut().iloc[0]
            st.info(
                f"Recommended stress haircut: **{haircut['stress_haircut']:.2%}** "
                f"of the model forecast in stress."
            )
        except (ValueError, FileNotFoundError):
            pass
    st.markdown("### Bias by version, family and regime")
    st.dataframe(bias_heatmap_panel(), use_container_width=True)
    st.markdown("### Rolling 12-month bias with bands")
    st.dataframe(rolling_bias_panel().tail(200), use_container_width=True)
    st.markdown("### Calibration and Q-Q")
    st.dataframe(calibration_panel(), use_container_width=True)
    st.markdown("### Horizon consistency: sqrt(21) scaled against direct 21-day")
    st.dataframe(horizon_panel(), use_container_width=True)
