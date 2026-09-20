"""Sprint E4 Task 8: the walkthrough, its render and the docs links.

The walkthrough checks are post-execution: a cell cannot see its own output, so
the two properties that need the rendered file, that every stored value was
printed and that none was typed, live here. The scan is the same one the
notebook's last cell runs on itself.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from efb import evaluate

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "E4_walkthrough.ipynb"
HTML = ROOT / "notebooks" / "E4_walkthrough.html"
RESULTS = ROOT / "sprints" / "E4" / "RESULTS.json"
REGISTRY = ROOT / "data" / "models" / "registry.json"
MEMO = ROOT / "docs" / "research" / "E4_covariance_memo.md"

CRITERIA = [f"F4.{index}" for index in range(1, 8)]


def _notebook() -> dict:
    if not NOTEBOOK.exists():
        pytest.skip("E4 walkthrough not written yet")
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
    assert len(executed) >= 15, "the walkthrough has not been executed"
    assert "data_hash" in _printed(notebook)


@pytest.mark.integration
def test_cell_1_asserts_the_sprint_hash_against_the_registry() -> None:
    notebook = _notebook()
    payload = json.loads(RESULTS.read_text())
    first_code = [
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    ][:2]
    joined = "\n".join(first_code)
    assert "e4_data_hash" in joined, "the hash is not recomputed in the notebook"
    assert str(payload["data_hash"]) in _printed(
        notebook
    ), "the stored hash is not printed by any cell"
    assert evaluate.e4_data_hash() == payload["data_hash"]


@pytest.mark.integration
def test_walkthrough_prints_every_stored_criterion() -> None:
    printed = _printed(_notebook())
    for name in CRITERIA:
        assert name in printed, f"{name} is not covered by the walkthrough"
    assert "closing checklist" in printed


@pytest.mark.integration
def test_the_four_residual_measurements_are_printed() -> None:
    printed = _printed(_notebook())
    payload = json.loads(RESULTS.read_text())
    numbers = payload["criteria"]["F4.5"]["stored_numbers"]
    assert f"{numbers['residual_spectrum_largest']:.4f}" in printed
    assert f"{numbers['residual_spectrum_edge']:.4f}" in printed
    assert "1.039161e-06" in printed, "the factor-specific covariance is not printed"
    assert "3.9 points" in printed


@pytest.mark.integration
def test_walkthrough_hardcodes_no_stored_number() -> None:
    """A stored value must never be typed into a code cell."""
    payload = json.loads(RESULTS.read_text())
    registry = json.loads(REGISTRY.read_text())
    values = numeric_leaves(payload["criteria"]) + numeric_leaves(registry["models"])
    source = _code_source(_notebook())
    offenders: list[str] = []
    for value in values:
        for text in (f"{value:.6f}", f"{value:.4f}"):
            if len(text) > 6 and text in source:
                offenders.append(text)
    assert (
        not offenders
    ), f"stored values typed into the notebook: {sorted(set(offenders))}"


@pytest.mark.integration
def test_the_ewma_effective_sample_reading_is_recorded() -> None:
    """The new diagnostic: below N, so it explains the EWMA row."""
    printed = _printed(_notebook())
    assert "implied effective sample size" in printed
    assert "effective T below N: True" in printed
    assert "RECORDED" in printed
    # and it reached the deliverable as one sentence
    memo = MEMO.read_text()
    assert "181.78" in memo and "39.0" in memo


@pytest.mark.integration
def test_the_by_hand_derivations_are_present() -> None:
    source = _code_source(_notebook())
    for phrase in (
        "np.linalg.eigh",
        "st.mp_edge",
        "shrinkage_intensity",
        "min_variance_weights",
        "realized_vol",
    ):
        assert phrase in source, phrase
    printed = _printed(_notebook())
    assert "reconstruction error" in printed
    assert "intensity without the correction" in printed
    assert "the module agrees" in printed


def test_the_credit_port_note_is_present() -> None:
    source = _code_source(_notebook())
    assert "issuer blocks" in source or "issuer-level" in _printed(_notebook())


@pytest.mark.integration
def test_the_render_exists_and_the_methodology_links_resolve() -> None:
    assert HTML.exists(), "the walkthrough has not been rendered to HTML"
    assert HTML.stat().st_size > 100_000
    methodology = (ROOT / "dashboard" / "tabs" / "methodology.py").read_text()
    for target in (
        "notebooks/E4_walkthrough.html",
        "docs/research/E4_covariance_memo.md",
        "sprints/E4/RESULTS.json",
    ):
        assert target in methodology, target


@pytest.mark.integration
def test_published_docs_exist_for_every_e4_link() -> None:
    static = ROOT / "dashboard" / "static" / "docs"
    if not static.exists():
        pytest.skip("docs not published yet")
    for target in (
        "notebooks/E4_walkthrough.html",
        "docs/research/E4_covariance_memo.md",
    ):
        assert (static / target).exists(), target


@pytest.mark.integration
def test_no_em_dashes_in_anything_the_sprint_writes() -> None:
    targets = [
        MEMO,
        ROOT / "sprints" / "E4" / "PRD.md",
        ROOT / "sprints" / "E4" / "TASKS.md",
        ROOT / "sprints" / "E4" / "PROBES.md",
        ROOT / "docs" / "open_items.md",
        ROOT / "docs" / "hygiene_ledger.md",
    ]
    for path in targets:
        text = path.read_text()
        for bad in ("\u2014", "\u2013"):
            assert bad not in text, f"{path.name} contains an em or en dash"


def test_the_notebook_carries_its_own_forbidden_literal_scan() -> None:
    source = _code_source(_notebook())
    assert "closing checklist" in source
    assert re.search(r"offenders", source), "the scan is not in the last cell"
