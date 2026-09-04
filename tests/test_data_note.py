"""Tests for Task 10: the research deliverable."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "docs" / "research" / "E1_data_note.md"

REQUIRED_SECTIONS = [
    "## PM question",
    "## Research questions",
    "## Methodology",
    "## Stored numbers",
    "## Practitioner conclusion",
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


def test_note_quotes_criteria_verbatim() -> None:
    text = NOTE.read_text()
    assert (
        "Equal-weight universe daily return vs the Kenneth French market "
        "return (Mkt-RF + RF) correlation above 0.95."
    ) in text
    assert "at least 95% of requested tickers with at least 10 years of" in text


def test_note_cites_stored_numbers() -> None:
    text = NOTE.read_text()
    assert "0.4479" in text  # survivorship fraction
    assert "0.9557" in text  # F1.3 correlation
