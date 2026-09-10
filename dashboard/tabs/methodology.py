"""Methodology tab: links to every E1 and E2 evidence artifact (Task 8).

Points at the Hygiene Ledger, the research deliverables, the walkthrough
notebooks (rendered HTML), the sprint PRDs and probes and the model
registry. Later sprints add their own links here.

Links go through Streamlit's static route, not the repository path: a bare
relative link falls through to the app shell, so clicking it just reloads
the dashboard. `dashboard/publish.py` copies these files into
`dashboard/static/docs/` and `make dashboard` runs it first.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:  # see the note in dashboard/app.py
    sys.path.insert(0, str(ROOT))

from dashboard.publish import LINK_PREFIX  # noqa: E402

LINKS = [
    ("Sprint E1 PRD", "sprints/E1/PRD.md"),
    ("Sprint E1 tasks", "sprints/E1/TASKS.md"),
    ("Sprint E1 probes", "sprints/E1/PROBES.md"),
    ("Sprint E1 results (F criteria)", "sprints/E1/RESULTS.json"),
    ("Sprint E2 PRD", "sprints/E2/PRD.md"),
    ("Sprint E2 tasks", "sprints/E2/TASKS.md"),
    ("Sprint E2 probes (coverage by year)", "sprints/E2/PROBES.md"),
    ("Sprint E2 results (F criteria)", "sprints/E2/RESULTS.json"),
    ("Hygiene Ledger", "docs/hygiene_ledger.md"),
    ("Open items", "docs/open_items.md"),
    ("Model registry (TS-v1)", "data/models/registry.json"),
    (
        "Research deliverable: Data Quality and Universe Note",
        "docs/research/E1_data_note.md",
    ),
    (
        "Research deliverable: Beta and Volatility Estimation Study",
        "docs/research/E2_exposure_study.md",
    ),
    ("Walkthrough notebook", "notebooks/E1_walkthrough.html"),
    ("Walkthrough notebook E2", "notebooks/E2_walkthrough.html"),
]


def render() -> None:
    st.title("Methodology")
    st.markdown(
        "Every number in the book traces back to the artifacts below. The "
        "dashboard reads parquet only; the documents here record why each "
        "number is what it is."
    )
    missing: list[str] = []
    for label, rel in LINKS:
        target = ROOT / rel
        if not target.exists():
            missing.append(rel)
            continue
        st.markdown(f"- [{label}](/{LINK_PREFIX}/{rel})")
    if missing:
        st.caption("Not generated yet: " + ", ".join(missing))
