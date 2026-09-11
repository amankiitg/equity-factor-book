"""Tests for Task 9: the E2 research deliverable."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "docs" / "research" / "E2_exposure_study.md"
RESULTS = ROOT / "sprints" / "E2" / "RESULTS.json"

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
    # the numbers come from RESULTS.json, so a corrected artifact forces the
    # document to be updated rather than leaving a stale figure in place
    text = NOTE.read_text()
    criteria = json.loads(RESULTS.read_text())["criteria"]
    f23 = criteria["F2.3"]["stored_numbers"]
    numbers = [
        f"{criteria['F2.1']['stored_number']:.4f}",
        f"{criteria['F2.2']['stored_numbers']['mean_pairwise_correlation']:.4f}",
        f"{f23['garch_win_share']:.1%}",
        f"{f23['ewma_094_win_share']:.1%}",
        f"{criteria['F2.4']['stored_numbers']['bias_mean']:.4f}",
        f"{criteria['F2.5']['stored_number']:.1%}",
    ]
    for number in numbers:
        assert number in text, f"missing stored number {number}"
    for ticker in criteria["F2.6"]["stored_numbers"]["break_tickers"]:
        assert ticker in text, f"missing series-break ticker {ticker}"


def test_note_recommends_an_estimator_per_use() -> None:
    text = NOTE.read_text()
    for use in ["Hedging", "Risk", "Sizing"]:
        assert use in text


def test_note_lists_every_criterion_with_its_verdict() -> None:
    """The last list in the document has to match the stored file.

    A reader who only reads the last paragraph should still see the count
    of what passed and what failed, and it should not be possible for that
    list to disagree with sprints/E2/RESULTS.json.
    """
    text = NOTE.read_text()
    results = json.loads(RESULTS.read_text())
    criteria = results["criteria"]
    for key, value in criteria.items():
        assert f"| {key} | {value['verdict']} |" in text, key
    n_pass = sum(1 for value in criteria.values() if value["verdict"] == "pass")
    assert (
        f"{len(criteria)} criteria, {n_pass} passing and "
        f"{len(criteria) - n_pass} failing."
    ) in text
    assert results["data_hash"][:16] in text
