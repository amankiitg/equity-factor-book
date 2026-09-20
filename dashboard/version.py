"""The dashboard's model version selector, shared by every tab.

Sprint E4, Task 5. One place decides which registered model version the console
is showing, so D0 through D3 cannot disagree about it, and one place maps a
version to the artifacts it owns. Reads the registry for the list of versions
and never writes to it.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "models" / "registry.json"
DEFAULT_VERSION = "XS-v1"


def registry_payload() -> dict:
    if not REGISTRY.exists():
        return {"models": {}}
    return json.loads(REGISTRY.read_text())


def available_versions() -> list[str]:
    """Registered versions, the default first, then the rest in order."""
    names = list(registry_payload().get("models", {}))
    if DEFAULT_VERSION in names:
        names.remove(DEFAULT_VERSION)
        names.insert(0, DEFAULT_VERSION)
    return names or [DEFAULT_VERSION]


def selected_version() -> str:
    """The version every tab renders under.

    Held in the session so a selection survives a tab switch, and reset to the
    first registered version when it points at something unregistered.
    """
    options = available_versions()
    current = st.session_state.get("model_version")
    if current not in options:
        st.session_state["model_version"] = options[0]
    return str(st.session_state["model_version"])


def select_version() -> str:
    """The sidebar widget. Called once, by the app, before any tab renders."""
    options = available_versions()
    index = options.index(selected_version())
    chosen = st.sidebar.selectbox(
        "Model version", options, index=index, key="version_selector"
    )
    st.session_state["model_version"] = chosen
    payload = registry_payload()
    entry = payload.get("models", {}).get(chosen, {})
    st.sidebar.caption(
        f"family {entry.get('family', 'unknown')} | champion "
        f"{'yes' if entry.get('champion') else 'no'} | "
        f"eligible {'yes' if entry.get('eligible_for_champion') else 'no'}"
    )
    return str(chosen)


def artifacts_for(version: str) -> dict[str, Path]:
    """The artifacts each version owns, which is what a tab needs to switch on."""
    mapping = {
        "XS-v1": {
            "model_dir": ROOT / "data" / "models" / "XS-v1",
            "factor_returns": ROOT
            / "data"
            / "models"
            / "XS-v1"
            / "factor_returns.parquet",
            "specific_returns": ROOT
            / "data"
            / "models"
            / "XS-v1"
            / "specific_returns.parquet",
            "descriptors": ROOT / "data" / "models" / "XS-v1" / "descriptors.parquet",
            "r_squared": ROOT / "data" / "models" / "XS-v1" / "xs_r2.parquet",
        },
        "PCA-v1": {
            "model_dir": ROOT / "data" / "models" / "PCA-v1",
            "loadings": ROOT / "data" / "models" / "PCA-v1" / "loadings.parquet",
            "factor_returns": ROOT
            / "data"
            / "models"
            / "PCA-v1"
            / "factor_returns.parquet",
            "eigenvalues": ROOT / "data" / "models" / "PCA-v1" / "eigenvalues.parquet",
            "panel_eigenvalues": ROOT
            / "data"
            / "models"
            / "PCA-v1"
            / "eigenvalues_panel.parquet",
        },
        "PCA-v1c": {
            "model_dir": ROOT / "data" / "models" / "PCA-v1c",
            "loadings": ROOT / "data" / "models" / "PCA-v1c" / "loadings.parquet",
            "spectrum": ROOT / "data" / "models" / "PCA-v1c" / "spectrum.parquet",
            "eigenvalues": ROOT / "data" / "models" / "PCA-v1c" / "eigenvalues.parquet",
        },
        "TS-v1": {
            "model_dir": ROOT / "data" / "models" / "TS-v1",
        },
    }
    return mapping.get(version, {"model_dir": ROOT / "data" / "models" / version})


def spectrum_path(version: str) -> Path:
    """The eigenvalue spectrum of a version, whichever name it uses."""
    artifacts = artifacts_for(version)
    for key in ("eigenvalues", "spectrum", "panel_eigenvalues"):
        if key in artifacts:
            return artifacts[key]
    return ROOT / "data" / "models" / "XS-v1" / "factor_cov.parquet"
