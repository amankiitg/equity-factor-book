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
    ("Sprint E3 PRD", "sprints/E3/PRD.md"),
    ("Sprint E3 tasks", "sprints/E3/TASKS.md"),
    ("Sprint E3 probes (descriptors, shares, sectors)", "sprints/E3/PROBES.md"),
    ("Sprint E3 results (F criteria)", "sprints/E3/RESULTS.json"),
    (
        "Research deliverable: Fund Model Research Note XS-v1",
        "docs/research/E3_factor_model_note.md",
    ),
    (
        "Research deliverable: Factor Exposure and Risk Report",
        "docs/research/E3_risk_report.md",
    ),
    ("Sprint E4 PRD", "sprints/E4/PRD.md"),
    ("Sprint E4 tasks", "sprints/E4/TASKS.md"),
    (
        "Sprint E4 probes (eigenvalue feasibility, sectors, momentum)",
        "sprints/E4/PROBES.md",
    ),
    ("Sprint E4 results (F criteria)", "sprints/E4/RESULTS.json"),
    (
        "Research deliverable: Covariance Estimator Comparison and Residual "
        "Factor Audit",
        "docs/research/E4_covariance_memo.md",
    ),
    ("Walkthrough notebook", "notebooks/E1_walkthrough.html"),
    ("Walkthrough notebook E2", "notebooks/E2_walkthrough.html"),
    ("Walkthrough notebook E3 (XS-v1)", "notebooks/E3_walkthrough.html"),
    (
        "Walkthrough notebook E4 (PCA and the covariance lab)",
        "notebooks/E4_walkthrough.html",
    ),
    ("Sprint E5 PRD", "sprints/E5/PRD.md"),
    ("Sprint E5 tasks", "sprints/E5/TASKS.md"),
    (
        "Sprint E5 probes (race grid, champion rule, eligibility)",
        "sprints/E5/PROBES.md",
    ),
    ("Sprint E5 results (F criteria)", "sprints/E5/RESULTS.json"),
    (
        "Research deliverable: Risk Model Diagnostic and Champion Decision",
        "docs/research/E5_risk_model_diagnostic.md",
    ),
    (
        "Walkthrough notebook E5 (risk evaluation and the champion)",
        "notebooks/E5_walkthrough.html",
    ),
    ("Sprint E6 PRD", "sprints/E6/PRD.md"),
    ("Sprint E6 tasks", "sprints/E6/TASKS.md"),
    ("Sprint E6 results (F criteria)", "sprints/E6/RESULTS.json"),
    (
        "Research deliverable: Hedge Effectiveness Study",
        "docs/research/E6_hedge_study.md",
    ),
    (
        "Walkthrough notebook E6 (hedging)",
        "notebooks/E6_walkthrough.html",
    ),
    ("Sprint E7 PRD", "sprints/E7/PRD.md"),
    ("Sprint E7 tasks", "sprints/E7/TASKS.md"),
    ("Sprint E7 results (F criteria)", "sprints/E7/RESULTS.json"),
    (
        "The Multiple-Testing Ledger",
        "docs/multiple_testing_ledger.md",
    ),
    (
        "Research deliverable: Signal Evaluation Reports (six)",
        "docs/research/E7_signal_momentum_12_1.md",
    ),
    (
        "Walkthrough notebook E7 (alpha lab)",
        "notebooks/E7_walkthrough.html",
    ),
    ("Sprint E8 PRD", "sprints/E8/PRD.md"),
    ("Sprint E8 tasks", "sprints/E8/TASKS.md"),
    ("Sprint E8 results (F criteria)", "sprints/E8/RESULTS.json"),
    (
        "Research deliverable: Portfolio Construction Memo",
        "docs/research/E8_construction_memo.md",
    ),
    (
        "Walkthrough notebook E8 (sizing)",
        "notebooks/E8_walkthrough.html",
    ),
    ("Sprint E9 PRD", "sprints/E9/PRD.md"),
    ("Sprint E9 tasks", "sprints/E9/TASKS.md"),
    ("Sprint E9 results (F criteria)", "sprints/E9/RESULTS.json"),
    (
        "Research deliverable: Transaction Cost and Capacity Analysis",
        "docs/research/E9_tcost_capacity.md",
    ),
    (
        "Walkthrough notebook E9 (cost and capacity)",
        "notebooks/E9_walkthrough.html",
    ),
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
