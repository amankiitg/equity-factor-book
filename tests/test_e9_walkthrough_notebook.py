"""Sprint E9 Task 9: the walkthrough, its render and the docs links."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from efb import evaluate

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "E9_walkthrough.ipynb"
HTML = ROOT / "notebooks" / "E9_walkthrough.html"
RESULTS = ROOT / "sprints" / "E9" / "RESULTS.json"

CRITERIA = [f"F9.{index}" for index in range(1, 6)]


def _notebook() -> dict:
    if not NOTEBOOK.exists():
        pytest.skip("E9 walkthrough not written yet")
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
    assert len(executed) >= 8, "the walkthrough has not been executed"
    assert "data_hash" in _printed(notebook)


@pytest.mark.integration
def test_the_hash_cell_asserts_the_sprint_hash_against_the_artifacts() -> None:
    notebook = _notebook()
    payload = json.loads(RESULTS.read_text())
    joined = _code_source(notebook)
    assert "e9_data_hash" in joined, "the hash is not recomputed in the notebook"
    assert str(payload["data_hash"]) in _printed(notebook)
    assert evaluate.e9_data_hash() == payload["data_hash"]


@pytest.mark.integration
def test_walkthrough_prints_every_stored_criterion() -> None:
    printed = _printed(_notebook())
    for name in CRITERIA:
        assert name in printed, f"{name} is not covered by the walkthrough"
    assert "closing checklist" in printed


@pytest.mark.integration
def test_walkthrough_hardcodes_no_stored_number() -> None:
    payload = json.loads(RESULTS.read_text())
    values = numeric_leaves(payload["criteria"])
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
