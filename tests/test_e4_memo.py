"""Sprint E4 Task 7: the memo's numbers are traceable to stored artifacts.

The rule for this project is that no number is typed by hand. The memo is
prose, so it cannot be executed, but every headline number in it has to be
findable in `sprints/E4/RESULTS.json` or in the registry, and this test is
what makes that a property of the repository rather than a promise. It fails
the moment the memo and the stored measurement disagree.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MEMO = ROOT / "docs" / "research" / "E4_covariance_memo.md"
RESULTS = ROOT / "sprints" / "E4" / "RESULTS.json"
REGISTRY = ROOT / "data" / "models" / "registry.json"

# Every number the memo leans on, in the rounding the memo prints it at.
HEADLINE_NUMBERS = [
    "0.577780",  # size correlation between universes
    "0.625560",  # liquidity correlation
    "0.893133",  # residual volatility correlation
    "0.997009",  # market correlation
    "-0.000032",  # size premium, panel
    "-0.000173",  # size premium, mapped
    "0.133530",  # mean cross-sectional R squared, panel
    "0.142526",  # mean cross-sectional R squared, mapped
    "0.199281",  # excluded names' annualized volatility
    "0.166796",  # included names' annualized volatility
    "0.385727",  # XS-v1 daily refit, held out
    "0.313303",  # PCA rolling refit, held out
    "0.253997",  # XS-v1 descriptors frozen
    "0.292699",  # XS-v1 plus three residual PCs
    "0.319808",  # momentum share, low tercile
    "0.561267",  # momentum share, high tercile
    "0.086042",  # clip median
    "0.088007",  # XS-v1 median
    "0.280404",  # sample median
    "0.150948",  # TS-v1 median
    "0.298494",  # EWMA median
    "0.5715",  # worst ratio to sample, F4.3
]


@pytest.fixture(scope="module")
def memo() -> str:
    """The memo with newlines collapsed, so a phrase that wraps still matches."""
    return " ".join(MEMO.read_text().split())


@pytest.fixture(scope="module")
def stored_numbers() -> list[float]:
    """Every number in the stored files, for the traceability check."""
    text = RESULTS.read_text() + REGISTRY.read_text()
    return [float(match) for match in re.findall(r"-?\d+\.\d+(?:e-?\d+)?", text)]


def test_the_memo_exists_and_carries_the_required_sections(memo: str) -> None:
    for heading in (
        "## The answer, in two sentences",
        "## Finding 1: the residual structure",
        "## Finding 2: the survivor restriction",
        "## The covariance horse race",
        "## The criteria",
        "## What would falsify this?",
    ):
        assert heading in memo, heading
    assert "What would falsify this?" in memo


@pytest.mark.integration
def test_every_headline_number_is_in_the_memo_and_in_a_stored_artifact(
    memo: str, stored_numbers: list[float]
) -> None:
    missing_from_memo = [n for n in HEADLINE_NUMBERS if n not in memo]
    assert missing_from_memo == [], f"memo does not quote {missing_from_memo}"
    # a stored value is printed at full precision, so the memo's rounding is
    # traceable when some stored float rounds to the number the memo prints
    untraceable: list[str] = []
    for number in HEADLINE_NUMBERS:
        printed = abs(float(number))
        digits = len(number.split(".")[1])
        tolerance = 0.5 * 10 ** (-digits)
        if not any(abs(abs(value) - printed) <= tolerance for value in stored_numbers):
            untraceable.append(number)
    assert untraceable == [], f"not traceable to an artifact: {untraceable}"


def test_the_memo_keeps_the_two_findings_separate(memo: str) -> None:
    """The model problem and the data problem are different problem classes."""
    first = memo.index("## Finding 1: the residual structure")
    second = memo.index("## Finding 2: the survivor restriction")
    assert first < second
    between = memo[first:second]
    assert "residual" in between.lower()
    assert "point-in-time" in memo[second:]
    assert "no model can fix" in memo


@pytest.mark.integration
def test_the_two_pca_counts_are_stated_where_both_appear(memo: str) -> None:
    assert "F4.2 governs the correlation PCA's 13" in memo
    assert "PCA-v1c's 16" in memo
    assert "never scored against F4.2" in memo


def test_the_withdrawn_threshold_is_not_restated_as_a_criterion(memo: str) -> None:
    assert "withdrawn" in memo
    # the value itself does not appear, so it cannot be read as a live threshold
    assert "0.9 was" not in memo and "below 0.9" not in memo


@pytest.mark.integration
def test_the_memo_carries_the_seven_carry_throughs(memo: str) -> None:
    assert "## Seven carry-throughs" in memo
    for phrase in (
        "Medians and win counts, never means",
        "realized-volatility definition collision",
        "period confound",
        "E3 open item",
        "F4.1 specification conflict",
        "swallowed-error defects",
        "withdrawn stop threshold",
    ):
        assert phrase in memo, phrase


def test_every_f4_verdict_in_the_memo_matches_the_results_file(memo: str) -> None:
    payload = json.loads(RESULTS.read_text())
    cells = [cell.strip() for cell in memo.split("|")]
    for key, block in payload["criteria"].items():
        assert key in cells, f"{key} is missing from the memo's criteria table"
        row = " | ".join(cells[cells.index(key) : cells.index(key) + 5])
        assert block["verdict"] in row, row
