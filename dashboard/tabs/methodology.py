"""Methodology tab: links to every E1 evidence artifact (Sprint E1, Task 8).

Points at the Hygiene Ledger, the research deliverable, the walkthrough
notebook (rendered HTML) and the sprint PRD and probes. Later sprints add
their own links here.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]

LINKS = [
    ("Sprint E1 PRD", "sprints/E1/PRD.md"),
    ("Sprint E1 tasks", "sprints/E1/TASKS.md"),
    ("Sprint E1 probes", "sprints/E1/PROBES.md"),
    ("Sprint E1 results (F criteria)", "sprints/E1/RESULTS.json"),
    ("Hygiene Ledger", "docs/hygiene_ledger.md"),
    (
        "Research deliverable: Data Quality and Universe Note",
        "docs/research/E1_data_note.md",
    ),
    ("Walkthrough notebook", "notebooks/E1_walkthrough.html"),
]


def render() -> None:
    st.title("Methodology")
    st.markdown(
        "Every number in the book traces back to the artifacts below. The "
        "dashboard reads parquet only; the documents here record why each "
        "number is what it is."
    )
    for label, rel in LINKS:
        target = ROOT / rel
        if target.exists():
            st.markdown(f"- [{label}]({rel})")
        else:
            st.markdown(f"- {label} (not generated yet: {rel})")
