"""Tests for Task 9: the E2 research deliverable."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "docs" / "research" / "E2_exposure_study.md"

REQUIRED_SECTIONS = [
    "## PM answer",
    "## Research questions",
    "## Methodology",
    "## Stored numbers",
    "## Beta horse race",
    "## Volatility horse race",
    "## Recommended estimator per use",
    "## Residual correlation structure",
    "## What would falsify this?",
    "## Open questions",
]


def test_note_exists_and_has_required_sections() -> None:
    assert NOTE.is_file()
    text = NOTE.read_text()
    for section in REQUIRED_SECTIONS:
        assert section in text, f"missing section {section}"


def test_note_has_no_em_dashes() -> None:
    assert "\u2014" not in NOTE.read_text()


def test_note_cites_stored_numbers() -> None:
    text = NOTE.read_text()
    for number in ["0.9123", "0.4228", "0.4272", "0.0183", "1.023", "0.018"]:
        assert number in text, f"missing stored number {number}"


def test_note_recommends_an_estimator_per_use() -> None:
    text = NOTE.read_text()
    for use in ["Hedging", "Risk", "Sizing"]:
        assert use in text
