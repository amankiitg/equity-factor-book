"""Sprint E7 Task 8: the walkthrough, its render and the docs links.

The walkthrough checks are post-execution: a cell cannot see its own output,
so the properties that need the executed file, that every stored value was
printed and that none was typed, live here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from efb import evaluate

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "E7_walkthrough.ipynb"
HTML = ROOT / "notebooks" / "E7_walkthrough.html"
RESULTS = ROOT / "sprints" / "E7" / "RESULTS.json"
GATE = ROOT / "sprints" / "E7" / "RG_SIGNAL.json"

CRITERIA = [f"F7.{index}" for index in range(1, 5)]


def _notebook() -> dict:
    if not NOTEBOOK.exists():
        pytest.skip("E7 walkthrough not written yet")
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
def test_walkthrough_has_been_executed() -> None:
    notebook = _notebook()
    executed = [
        cell
        for cell in notebook["cells"]
        if cell["cell_type"] == "code" and cell.get("execution_count")
    ]
    assert len(executed) >= 11, "the walkthrough has not been executed"
    assert "data_hash" in _printed(notebook)


@pytest.mark.integration
def test_the_hash_cell_asserts_the_sprint_hash_against_the_artifacts() -> None:
    notebook = _notebook()
    payload = json.loads(RESULTS.read_text())
    first_code = [
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    ][:3]
    joined = "\n".join(first_code)
    assert "e7_data_hash" in joined, "the hash is not recomputed in the notebook"
    assert str(payload["data_hash"]) in _printed(
        notebook
    ), "the stored hash is not printed by any cell"
    assert evaluate.e7_data_hash() == payload["data_hash"]


@pytest.mark.integration
def test_walkthrough_prints_every_stored_criterion_and_the_gate() -> None:
    printed = _printed(_notebook())
    for name in CRITERIA:
        assert name in printed, f"{name} is not covered by the walkthrough"
    assert "closing checklist" in printed
    for name in json.loads(GATE.read_text()):
        assert name in printed


@pytest.mark.integration
def test_walkthrough_hardcodes_no_stored_number() -> None:
    """A stored value must never be typed into a code cell."""
    payload = json.loads(RESULTS.read_text())
    gate = json.loads(GATE.read_text())
    values = numeric_leaves(payload["criteria"]) + numeric_leaves(gate)
    source = _code_source(_notebook())
    offenders: list[str] = []
    for value in values:
        for text in (f"{value:.6f}", f"{value:.4f}"):
            if len(text) > 6 and text in source:
                offenders.append(text)
    assert offenders == [], f"stored values typed into a cell: {offenders}"


@pytest.mark.integration
def test_the_html_render_exists() -> None:
    assert HTML.exists(), "the walkthrough has not been rendered"
    assert HTML.stat().st_size > 100_000
