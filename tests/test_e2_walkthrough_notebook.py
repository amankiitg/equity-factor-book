"""Post-execution checks on notebooks/E2_walkthrough.ipynb.

The notebook asserts every figure against its artifact while it runs, but a
cell cannot see the outputs of its own run, so the two checks that need the
rendered file live here: every stored value has to appear in the printed
output, and no stored value may appear as a literal in the source. Both run
in `make test`, so the audit trail cannot rot quietly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "E2_walkthrough.ipynb"
E1_RESULTS = ROOT / "sprints" / "E1" / "RESULTS.json"
E2_RESULTS = ROOT / "sprints" / "E2" / "RESULTS.json"


def _notebook() -> dict:
    if not NOTEBOOK.exists():
        pytest.skip("E2 walkthrough not generated yet")
    return json.loads(NOTEBOOK.read_text())


def _source(notebook: dict) -> str:
    return "\n".join(
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    )


def _printed(notebook: dict) -> str:
    return "\n".join(
        "".join(output.get("text", []))
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
        for output in cell.get("outputs", [])
    )


def numeric_leaves(node) -> list[float]:
    out: list[float] = []
    if isinstance(node, dict):
        for value in node.values():
            out.extend(numeric_leaves(value))
    elif isinstance(node, list):
        for value in node:
            out.extend(numeric_leaves(value))
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        out.append(float(node))
    return out


def test_notebook_has_been_executed() -> None:
    notebook = _notebook()
    code_cells = [c for c in notebook["cells"] if c["cell_type"] == "code"]
    assert code_cells, "no code cells"
    executed = [c for c in code_cells if c.get("execution_count")]
    if not executed:
        pytest.skip("notebook has not been executed yet")
    assert len(executed) == len(code_cells)


def test_no_cell_errored() -> None:
    notebook = _notebook()
    if not _printed(notebook):
        pytest.skip("notebook has not been executed yet")
    failures = [
        (index, output.get("ename"))
        for index, cell in enumerate(notebook["cells"])
        if cell["cell_type"] == "code"
        for output in cell.get("outputs", [])
        if output.get("output_type") == "error"
    ]
    assert not failures, f"cells with errors: {failures}"


def test_every_stored_value_is_printed() -> None:
    """Every criterion this notebook covers has to be printed in full.

    The scope is every E2 criterion plus the two E1 values the close-out
    restated (F1.3 and F1.5), which is what the notebook claims to audit.
    The rest of E1 belongs to the E1 walkthrough.
    """
    notebook = _notebook()
    printed = _printed(notebook)
    if not printed:
        pytest.skip("notebook has not been executed yet")
    criteria: dict[str, dict] = {}
    if E2_RESULTS.exists():
        criteria.update(json.loads(E2_RESULTS.read_text())["criteria"])
    if E1_RESULTS.exists():
        e1 = json.loads(E1_RESULTS.read_text())["criteria"]
        criteria.update({key: e1[key] for key in ("F1.3", "F1.5") if key in e1})
    missing: list[str] = []
    checked = 0
    for key, criterion in criteria.items():
        numbers = criterion.get("stored_number", criterion.get("stored_numbers"))
        for value in numeric_leaves(numbers):
            if abs(value) >= 100 or value == int(value):
                continue
            checked += 1
            if repr(value) not in printed:
                missing.append(f"{key}:{value!r}")
    assert checked > 20, "the check found almost nothing to verify"
    assert not missing, f"stored values never printed: {missing[:5]}"


def test_no_stored_figure_is_typed_into_the_source() -> None:
    notebook = _notebook()
    criteria = {}
    for path in (E1_RESULTS, E2_RESULTS):
        if path.exists():
            criteria.update(json.loads(path.read_text())["criteria"])
    forbidden: set[str] = set()
    for criterion in criteria.values():
        numbers = criterion.get("stored_number", criterion.get("stored_numbers"))
        for value in numeric_leaves(numbers):
            for text in (f"{value:.4f}", f"{value:.6f}", f"{value:.10f}"):
                if len(text) >= 4:
                    forbidden.add(text)
    registry = ROOT / "data" / "models" / "registry.json"
    if registry.exists():
        forbidden.add(
            str(
                int(
                    json.loads(registry.read_text())["models"]["TS-v1"]["parameters"][
                        "garch_seed"
                    ]
                )
            )
        )
    version = ROOT / "data" / "VERSION.json"
    if version.exists():
        payload = json.loads(version.read_text())
        forbidden.add(payload["data_hash"])
        forbidden.add(payload["data_hash"][:16])
    forbidden.discard("")
    source = _source(notebook)
    offenders = sorted(text for text in forbidden if text in source)
    assert not offenders, f"stored figures typed into the source: {offenders[:5]}"


def test_the_script_reaches_the_deliverable_and_the_dashboard() -> None:
    note = ROOT / "docs" / "research" / "E2_exposure_study.md"
    assert note.exists()
    text = note.read_text()
    for criterion in ("F2.6c", "F2.3c"):
        assert criterion in text, f"{criterion} missing from the deliverable"
    methodology = (ROOT / "dashboard" / "tabs" / "methodology.py").read_text()
    assert "notebooks/E2_walkthrough.html" in methodology
