"""EFB Console: global sidebar and tab router (Sprint E1, Task 8).

One Streamlit app grown one tab per sprint. The global sidebar shows the
as-of date, the universe snapshot and the data version hash (E1), and is
extended with model and portfolio selectors in E4 and E3.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]

# `streamlit run dashboard/app.py` puts the dashboard folder, not the repo
# root, first on sys.path, so the package import below fails without this.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard import version as version_module  # noqa: E402
from dashboard.tabs import (  # noqa: E402
    d00_data,
    d01_exposures,
    d02_factor_risk,
    d03_covariance,
    d04_risk_eval,
    d05_hedging,
    methodology,
)

VERSION_PATH = ROOT / "data" / "VERSION.json"


@st.cache_data(show_spinner=False)
def load_version() -> dict:
    return json.loads(VERSION_PATH.read_text())


def main() -> None:
    st.set_page_config(page_title="EFB Console", layout="wide")
    version = load_version()
    artifacts = version.get("artifacts", {})

    with st.sidebar:
        st.title("EFB Console")
        st.caption(f"Data built {version.get('built_at', 'unknown')}")
        first_hash = next(iter(artifacts.values()), {}).get("sha256", "no artifacts")
        st.metric("Data version hash", first_hash[:12])
        st.caption(f"{len(artifacts)} artifacts versioned")
        st.markdown("---")
        # one selector, read by every tab through dashboard.version, so D0 to D3
        # cannot disagree about which model version is on screen
        chosen = version_module.select_version()
        st.caption(f"rendering under {chosen}")
        st.markdown("---")
        st.caption("Links live on the Methodology tab.")

    tabs = st.tabs(
        [
            "D0 Data Health",
            "D1 Exposures",
            "D2 Factor Model and Risk",
            "D3 Covariance Lab",
            "D4 Risk Model Evaluation",
            "D5 Hedging",
            "Methodology",
        ]
    )
    with tabs[0]:
        d00_data.render()
    with tabs[1]:
        d01_exposures.render()
    with tabs[2]:
        d02_factor_risk.render()
    with tabs[3]:
        d03_covariance.render()
    with tabs[4]:
        d04_risk_eval.render()
    with tabs[5]:
        d05_hedging.render()
    with tabs[6]:
        methodology.render()


if __name__ == "__main__":
    main()
