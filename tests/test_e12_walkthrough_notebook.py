"""Sprint E12 item 9: the memo, the walkthrough, and the criteria they cite.

The two documents are the sprint's evidence, so the tests here are about the trail
rather than the prose: the criteria are in the results file verbatim from the
roadmap, the memo's numbers are the artifact's own, the walkthrough has been
executed, and no stored result was typed into it by hand.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

from efb import attribution

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "sprints" / "E12" / "RESULTS.json"
MEMO = ROOT / "docs" / "research" / "E12_attribution_report.md"
NOTEBOOK = ROOT / "notebooks" / "E12_walkthrough.ipynb"
DAILY = ROOT / "data" / "attribution" / "daily.parquet"
ROADMAP = ROOT / "docs" / "roadmap_v2.md"

CRITERIA = ("F12.1", "F12.2", "F12.3")


def _results() -> dict:
    if not RESULTS.exists():
        pytest.skip("E12's results are not registered yet")
    return json.loads(RESULTS.read_text())


def _notebook() -> dict:
    if not NOTEBOOK.exists():
        pytest.skip("the E12 walkthrough is not written yet")
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


def test_the_criteria_are_the_roadmap_s_own_words() -> None:
    """Copied, never retyped: the rule the project holds itself to."""
    lines = ROADMAP.read_text().splitlines()
    verbatim: dict[str, str] = {}
    for index, line in enumerate(lines):
        if line.strip() in CRITERIA and index + 1 < len(lines):
            verbatim[line.strip()] = lines[index + 1].strip()
    payload = _results()
    for name, text in verbatim.items():
        assert payload["criteria"][name]["criterion"] == text, name


def test_f12_3_writes_the_expected_verdict_down_before_the_numbers() -> None:
    payload = _results()
    assert payload["criteria"]["F12.3"]["expected_verdict"] == "luck"
    # And the two that need the live window say so, rather than being scored on the
    # seed book and read as met.
    assert payload["criteria"]["F12.2"]["verdict"] == "pending"
    assert payload["criteria"]["F12.3"]["verdict"] == "pending"
    assert payload["status"] == "pending"


def test_f12_1_s_numbers_are_the_artifact_s_own() -> None:
    """The registered residual is recomputed from the stored rows, not restated."""
    payload = _results()
    frame = pd.read_parquet(DAILY)
    residual = frame["identity_residual"].abs()
    stored = payload["criteria"]["F12.1"]["stored_numbers"]
    assert stored["n_sessions"] == len(frame)
    assert stored["median_abs_residual"] == pytest.approx(float(residual.median()))
    assert stored["max_abs_residual"] == pytest.approx(float(residual.max()))
    assert stored["n_days_within_1e10"] == int(
        (residual < attribution.IDENTITY_ATOL).sum()
    )
    # The verdict says which sessions it holds on, because it does not hold on all
    # of them.
    assert payload["criteria"]["F12.1"]["verdict"] == "partial"


def test_f12_3_s_numbers_are_the_library_s_own() -> None:
    payload = _results()
    frame = pd.read_parquet(DAILY)
    skill = attribution.skill_test(frame)
    stored = payload["criteria"]["F12.3"]["stored_numbers"][0]
    assert stored["n_days"] == skill["n_days"]
    assert stored["t_stat"] == pytest.approx(skill["t_stat"])
    assert stored["sharpe_annual"] == pytest.approx(skill["sharpe_annual"])
    assert stored["sharpe_se_lo2002"] == pytest.approx(skill["sharpe_se_lo2002"])
    assert stored["days_to_detect_ir_1"] == 1008


def test_the_memo_carries_the_artifact_s_numbers() -> None:
    """Every number the memo quotes is a number the builder read from a file."""
    if not MEMO.exists():
        pytest.skip("the memo is not written yet")
    text = MEMO.read_text()
    frame = pd.read_parquet(DAILY)
    skill = attribution.skill_test(frame)
    assert f"{len(frame):,}" in text
    assert f"{skill['sharpe_annual']:.3f}" in text
    assert f"{skill['sharpe_se_lo2002']:.3f}" in text
    assert f"{float(frame['pnl_total'].sum()) * 1e4:+.1f}" in text
    assert f"{skill['days_to_detect'][1.0]:,}" in text
    # The criteria appear by ID and the expected verdict is written down.
    for name in CRITERIA:
        assert name in text, name
    assert "luck" in text
    # And the deliverable does not claim the parts that were not built.
    assert "seven-way" in text


def test_the_memo_s_timing_share_states_its_denominator() -> None:
    """The two readings of that share differ, so the text says which one it is."""
    if not MEMO.exists():
        pytest.skip("the memo is not written yet")
    text = MEMO.read_text()
    frame = pd.read_parquet(DAILY)
    moved = frame.loc[frame["pnl_timing"].abs() > 0]
    net_share = abs(float(moved["pnl_timing"].sum())) / abs(
        float(moved["pnl_total"].sum())
    )
    assert f"{net_share * 100:.1f}%" in text
    assert "net" in text


def test_the_walkthrough_has_been_executed_and_prints_the_panels() -> None:
    notebook = _notebook()
    executed = [
        cell
        for cell in notebook["cells"]
        if cell["cell_type"] == "code" and cell.get("execution_count")
    ]
    assert len(executed) >= 8, "the walkthrough has not been executed"
    printed = _printed(notebook)
    for marker in (
        "identity residual",
        "median |residual|",
        "sessions where the two vintages differ",
        "mean |per-factor gap|",
        "t-statistic",
        "days needed for a t of",
        "the schema declares attribution as required",
    ):
        assert marker in printed, marker


def test_the_walkthrough_checks_the_hand_arithmetic_against_the_library() -> None:
    """By hand on two names, then against the library, which is the house rule."""
    notebook = _notebook()
    source = _code_source(notebook)
    printed = _printed(notebook)
    assert "exposure X" in source, "the by-hand exposure is not computed"
    assert "factor P&L" in source
    # The hand numbers, and the library's agreement with them, both printed.
    assert "+0.008000  (library +0.008000)" in printed
    assert "identity residual" in printed


def test_no_stored_result_is_typed_by_hand() -> None:
    """Two checks, because they catch different mistakes.

    First, the results file's own floats must not appear in the notebook's code: that
    is a number pasted from the answer. Second, no code cell may carry a decimal with
    five or more digits behind the point, which is the shape any such paste takes.
    The hand-checked fixture is exempt by construction: its inputs are 0.6, -0.4,
    0.02 and 0.01, and typing those is the point of a by-hand section.
    """
    notebook = _notebook()
    payload = _results()
    source = _code_source(notebook)
    typed: set[str] = set()
    for block in payload["criteria"].values():
        for entry in block.get("stored_numbers") or []:
            if not isinstance(entry, dict):
                continue
            for value in entry.values():
                if isinstance(value, float):
                    typed.add(repr(value))
                    typed.add(f"{value:.6f}")
    offenders = sorted(token for token in typed if token and token in source)
    assert offenders == [], f"pasted values in the notebook: {offenders}"
    long_decimals = sorted(set(re.findall(r"\d\.\d{5,}|\d{5,}\.\d", source)))
    assert long_decimals == [], f"numbers typed into the notebook: {long_decimals}"
