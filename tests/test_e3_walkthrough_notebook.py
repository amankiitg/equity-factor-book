"""Sprint E3 Task 7: the evaluation, the walkthrough and the docs links.

The walkthrough checks are post-execution: a cell cannot see the output of its
own run, so the two properties that need the rendered file, that every stored
value was printed and that none was typed, live here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "E3_walkthrough.ipynb"
RESULTS = ROOT / "sprints" / "E3" / "RESULTS.json"
NOTE = ROOT / "docs" / "research" / "E3_factor_model_note.md"
REPORT = ROOT / "docs" / "research" / "E3_risk_report.md"

CRITERIA = [f"F3.{index}" for index in range(1, 10)]


def _notebook() -> dict:
    if not NOTEBOOK.exists():
        pytest.skip("E3 walkthrough not written yet")
    return json.loads(NOTEBOOK.read_text())


def _code_source(notebook: dict) -> str:
    return "\n".join(
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    )


def _printed(notebook: dict) -> str:
    chunks: list[str] = []
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        for output in cell.get("outputs", []):
            text = output.get("text")
            if isinstance(text, list):
                chunks.append("".join(text))
            elif isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def numeric_leaves(node: object) -> list[float]:
    out: list[float] = []
    if isinstance(node, dict):
        for value in node.values():
            out.extend(numeric_leaves(value))
    elif isinstance(node, list):
        for value in node:
            out.extend(numeric_leaves(value))
    elif isinstance(node, float):
        out.append(node)
    return out


@pytest.mark.integration
def test_results_file_has_every_criterion_with_a_stored_number() -> None:
    payload = json.loads(RESULTS.read_text())
    assert payload["sprint"] == "E3"
    assert sorted(payload["criteria"]) == CRITERIA
    for name, block in payload["criteria"].items():
        assert block["criterion"], name
        assert block["threshold"], name
        assert block["stored_numbers"], name
        assert block["verdict"] in {"pass", "fail"}, name
        assert block["note"], name


@pytest.mark.integration
def test_results_history_is_append_only_across_two_identical_writes(
    tmp_path: Path,
) -> None:
    from efb import evaluate

    criteria = json.loads(RESULTS.read_text())["criteria"]
    path = tmp_path / "RESULTS.json"
    evaluate.write_results(criteria, path, sprint="E3", data_hash="abc")
    first = json.loads(path.read_text())
    evaluate.write_results(criteria, path, sprint="E3", data_hash="abc")
    second = json.loads(path.read_text())
    assert len(first["revisions"]["history"]) == len(second["revisions"]["history"])
    assert second["revisions"]["n_changed"] == 0
    assert second["revisions"]["changed"]["F3.1"]["changed"] is False


@pytest.mark.integration
def test_walkthrough_has_been_executed() -> None:
    notebook = _notebook()
    executed = [
        cell
        for cell in notebook["cells"]
        if cell["cell_type"] == "code" and cell.get("execution_count")
    ]
    assert len(executed) >= 15, "the walkthrough has not been executed"
    assert "data_hash" in _printed(notebook)


@pytest.mark.integration
def test_walkthrough_prints_every_stored_criterion() -> None:
    printed = _printed(_notebook())
    payload = json.loads(RESULTS.read_text())
    for name in CRITERIA:
        assert name in printed, f"{name} is not covered by the walkthrough"
    assert str(payload["data_hash"]) in printed
    assert "closing checklist" in printed


@pytest.mark.integration
def test_walkthrough_hardcodes_no_stored_number() -> None:
    """A stored value must never be typed into a code cell."""
    payload = json.loads(RESULTS.read_text())
    registry = json.loads((ROOT / "data" / "models" / "registry.json").read_text())
    values = numeric_leaves(payload["criteria"]) + numeric_leaves(
        registry["models"]["XS-v1"]["parameters"]
    )
    source = _code_source(_notebook())
    offenders: list[str] = []
    for value in values:
        for text in {f"{value:.6f}", f"{value:.4f}"}:
            if len(text) > 6 and text in source:
                offenders.append(text)
    assert (
        not offenders
    ), f"stored values typed into the notebook: {sorted(set(offenders))}"


@pytest.mark.integration
def test_research_notes_have_the_required_sections() -> None:
    note = NOTE.read_text()
    report = REPORT.read_text()
    for phrase in (
        "Fama-MacBeth",
        "What would falsify this",
        "look_ahead",
        "survivors",
    ):
        assert phrase in note, phrase
    for phrase in (
        "MCR",
        "unintended",
        "F3.8",
        "F3.9",
        "What would falsify this",
        "0.09681972392333447",
        "0.2884639400639966",
        "0.06978002876927968",
        "-0.3322050420277022",
        "0.3904549841533205",
        "-0.016190070548666415",
    ):
        assert phrase in report, phrase


@pytest.mark.integration
def test_no_em_dashes_in_anything_the_sprint_writes() -> None:
    targets = [
        NOTE,
        REPORT,
        ROOT / "sprints" / "E3" / "PRD.md",
        ROOT / "sprints" / "E3" / "TASKS.md",
        ROOT / "sprints" / "E3" / "PROBES.md",
    ]
    for path in targets:
        text = path.read_text()
        for bad in ("\u2014", "\u2013"):
            assert bad not in text, f"{path.name} contains an em or en dash"


@pytest.mark.integration
def test_methodology_tab_links_the_three_walkthroughs_and_the_deliverables() -> None:
    methodology = (ROOT / "dashboard" / "tabs" / "methodology.py").read_text()
    links = (ROOT / "dashboard" / "publish.py").read_text()
    combined = methodology + links
    for target in (
        "notebooks/E1_walkthrough.html",
        "notebooks/E2_walkthrough.html",
        "notebooks/E3_walkthrough.html",
        "docs/research/E3_factor_model_note.md",
        "docs/research/E3_risk_report.md",
    ):
        assert target in combined, target


@pytest.mark.integration
def test_published_docs_exist_for_every_link() -> None:
    static = ROOT / "dashboard" / "static" / "docs"
    if not static.exists():
        pytest.skip("docs not published yet")
    for target in (
        "notebooks/E3_walkthrough.html",
        "docs/research/E3_factor_model_note.md",
        "docs/research/E3_risk_report.md",
    ):
        assert (static / target).exists(), target
