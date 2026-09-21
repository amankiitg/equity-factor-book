"""Sprint E10 Task 10: the walkthrough, its render and the docs links."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from efb import evaluate

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "E10_walkthrough.ipynb"
HTML = ROOT / "notebooks" / "E10_walkthrough.html"
RESULTS = ROOT / "sprints" / "E10" / "RESULTS.json"

CRITERIA = ["F10.1", "F10.2", "F10.3"]


def _notebook() -> dict:
    if not NOTEBOOK.exists():
        pytest.skip("E10 walkthrough not written yet")
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
    assert "e10_data_hash" in joined, "the hash is not recomputed in the notebook"
    assert str(payload["data_hash"]) in _printed(notebook)
    assert evaluate.e10_data_hash() == payload["data_hash"]


@pytest.mark.integration
def test_every_criterion_appears_in_the_notebook() -> None:
    notebook = _notebook()
    joined = _code_source(notebook) + " " + _printed(notebook)
    for name in CRITERIA:
        assert name in joined, name


@pytest.mark.integration
def test_no_stored_value_is_typed_by_hand() -> None:
    notebook = _notebook()
    payload = json.loads(RESULTS.read_text())
    forbidden: set[str] = set()
    for value in numeric_leaves(payload["criteria"]):
        if isinstance(value, float) and abs(value) >= 1e-4:
            forbidden.add(f"{value:.6f}")
    joined = _code_source(notebook)
    offenders = [token for token in forbidden if token in joined]
    assert offenders == [], f"typed values in the notebook: {offenders}"
