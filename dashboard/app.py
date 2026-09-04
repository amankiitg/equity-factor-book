"""EFB Console: global sidebar and tab router (Sprint E1, Task 8).

One Streamlit app grown one tab per sprint. The global sidebar shows the
as-of date, the universe snapshot and the data version hash (E1), and is
extended with model and portfolio selectors in E4 and E3.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from dashboard.tabs import d00_data, methodology

ROOT = Path(__file__).resolve().parents[1]
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
        st.caption("Links live on the Methodology tab.")

    tabs = st.tabs(["D0 Data Health", "Methodology"])
    with tabs[0]:
        d00_data.render()
    with tabs[1]:
        methodology.render()


if __name__ == "__main__":
    main()
