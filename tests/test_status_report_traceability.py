"""The status report is traceable to the sprint artifacts.

The project rule is that no number is typed by hand. The status report is
prose, so it cannot be executed, but every headline number in it must be
findable in a stored artifact with the sign intact: a sprint RESULTS.json,
the probe records, the data ledger, a research memo, the registry, or a
risk-allocation parquet. This test is what makes that a property of the
repository rather than a promise. It fails the moment the report and a
stored measurement disagree.

Percentages: the artifacts store fractions (0.447887), while the report
reads "44.8 percent". The stored set therefore also carries each value
times 100, so a percentage reads back to the fraction it came from.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "research" / "STATUS_REPORT.md"

_FLOAT = r"-?\d+\.\d+(?:e-?\d+)?"


def _artifact_texts() -> list[str]:
    """Every artifact the report quotes, the report itself excluded.

    Sprint results carry the verdicts, the signal gate carries the six NULL
    answers, the registry carries the model metadata, the probe records and
    the data ledger carry the data-layer measurements, the research memos
    carry each sprint's headline numbers, and the allocation parquets carry
    the risk-allocation figures.
    """
    texts: list[str] = []
    for results in sorted((ROOT / "sprints").glob("*/RESULTS.json")):
        texts.append(results.read_text())
    for probes in sorted((ROOT / "sprints").glob("*/PROBES.md")):
        texts.append(probes.read_text())
    texts.append((ROOT / "sprints" / "E7" / "RG_SIGNAL.json").read_text())
    texts.append((ROOT / "data" / "models" / "registry.json").read_text())
    texts.append((ROOT / "docs" / "hygiene_ledger.md").read_text())
    for memo in sorted((ROOT / "docs" / "research").glob("*.md")):
        if memo.name == "STATUS_REPORT.md":
            continue
        texts.append(memo.read_text())
    for frame_path in sorted((ROOT / "data" / "allocation").glob("*.parquet")):
        frame = pd.read_parquet(frame_path)
        texts.append(frame.select_dtypes(include="number").to_string())
    return texts


@pytest.fixture(scope="module")
def stored_numbers() -> list[float]:
    values: list[float] = []
    for text in _artifact_texts():
        for match in re.findall(_FLOAT, text):
            value = float(match)
            values.extend([value, value * 100.0])
    return values


def _untraceable(report_text: str, stored: list[float]) -> list[str]:
    """The report numbers that match no stored number, sign included."""
    text = " ".join(report_text.split())
    offenders: list[str] = []
    for match in re.findall(_FLOAT, text):
        value = float(match)
        digits = len(match.split(".")[1])
        tolerance = 0.5 * 10 ** (-digits)
        if not any(abs(value - v) <= tolerance for v in stored):
            offenders.append(match)
    return offenders


@pytest.mark.integration
def test_the_report_exists_and_is_traceable(stored_numbers: list[float]) -> None:
    assert REPORT.exists()
    offenders = _untraceable(REPORT.read_text(), stored_numbers)
    assert offenders == [], f"numbers not traceable: {offenders}"


@pytest.mark.integration
def test_a_flipped_sign_is_rejected() -> None:
    # signed matching: the sign is part of the value
    stored = [-0.1994]
    assert _untraceable("| gap | 0.1994 |", stored) == ["0.1994"]
    assert _untraceable("| gap | -0.1994 |", stored) == []


@pytest.mark.integration
def test_the_report_names_the_three_gates_and_their_answers() -> None:
    text = " ".join(REPORT.read_text().split())
    for phrase in (
        "RG-Data",
        "G1",
        "G3",
        "RG-Signal",
        "RG-Operate",
        "all six signals NULL",
        "not cleared",
        "365.10",
    ):
        assert phrase in text, phrase


@pytest.mark.integration
def test_the_report_is_current_through_e11() -> None:
    text = " ".join(REPORT.read_text().split())
    for phrase in (
        "E11",
        "construction table",
        "paper",
        "dry run",
        "1,000,000",
    ):
        assert phrase in text, phrase
