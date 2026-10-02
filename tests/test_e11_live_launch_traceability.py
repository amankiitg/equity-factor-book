"""The E11 launch note is traceable to the sprint and live artifacts.

The project rule is that no number is typed by hand and that a qualitative
artifact is auditable anyway. `docs/research/E11_live_launch.md` is prose
written for a listener who has never seen the repository, so it cannot be
executed, but every figure in it must be findable in a stored artifact with
the sign intact: a sprint RESULTS.json, the probe records, the research
memos, the handoff records, the live configuration files, the page fixtures,
or the registry. This test is what makes that a property of the repository
rather than a promise.

Percentages: the artifacts store fractions (0.0643), while the note reads
"6.43 percent". The stored set therefore also carries each value times 100,
so a percentage reads back to the fraction it came from.

The note's two sections on the pre-launch review rounds and the alpha
correction quote figures whose source record is `handoff/LOG.md` and
`handoff/REPORT.md`. Those two files are on this branch, with the same text
main carries, so the pool reads them from the working tree like every other
source. There was a bridge here once, reading them through `git show main:`
while this branch's copies stopped the day before that work; the folded
branches brought the newer copies with them and the bridge is gone rather
than left in place as a second source that could drift.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "docs" / "research" / "E11_live_launch.md"
STATUS = ROOT / "docs" / "research" / "STATUS_REPORT.md"

_FLOAT = r"-?\d+\.\d+(?:e-?\d+)?"

WORD_FLOOR = 5_000
WORD_CEILING = 7_000


def _artifact_texts() -> list[str]:
    """Every artifact the note quotes, the note itself excluded.

    The sprint results carry the verdicts and the construction table, the
    probe records carry the data-layer measurements, the research memos
    carry each sprint's headline numbers, the handoff records carry the live
    book's measurements and the review findings, the clock and the cost
    reconciliation carry the live loop's own state, and the remaining files
    are the smaller sources named in the prose.
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
        if memo.name in {"STATUS_REPORT.md", "E11_live_launch.md"}:
            continue
        texts.append(memo.read_text())
    for record in sorted((ROOT / "handoff").glob("*.md")):
        texts.append(record.read_text())
    texts.append((ROOT / "docs" / "credit_port_design.md").read_text())
    texts.append((ROOT / "docs" / "open_items.md").read_text())
    texts.append((ROOT / "docs" / "roadmap_v2.md").read_text())
    texts.append((ROOT / "data" / "VERSION.json").read_text())
    texts.append((ROOT / "live" / "cost_reconciliation.json").read_text())
    texts.append((ROOT / "live" / "clock.json").read_text())
    texts.append((ROOT / "tests" / "test_hedge_vintage.py").read_text())
    for fixture in sorted((ROOT / "web" / "fixtures").glob("*.json")):
        texts.append(fixture.read_text())
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


def _untraceable(note_text: str, stored: list[float]) -> list[str]:
    """The note's numbers that match no stored number, sign included."""
    text = " ".join(note_text.split())
    offenders: list[str] = []
    for match in re.findall(_FLOAT, text):
        value = float(match)
        digits = len(match.split(".")[1])
        tolerance = 0.5 * 10 ** (-digits)
        if not any(abs(value - v) <= tolerance for v in stored):
            offenders.append(match)
    return offenders


@pytest.mark.integration
def test_the_note_exists_and_is_traceable(stored_numbers: list[float]) -> None:
    assert NOTE.exists()
    offenders = _untraceable(NOTE.read_text(), stored_numbers)
    assert offenders == [], f"numbers not traceable: {offenders}"


@pytest.mark.integration
def test_the_note_stays_inside_its_length_band() -> None:
    """It is written to be listened to, so it is one document of a stated
    length rather than a set of fragments.
    """
    words = len(NOTE.read_text().split())
    assert WORD_FLOOR <= words <= WORD_CEILING, words


@pytest.mark.integration
def test_the_note_stays_readable_aloud() -> None:
    """Prose only: no tables, no bullet runs, no em or en dashes, and no
    character a reader would have to see rather than hear.
    """
    text = NOTE.read_text()
    lines = text.splitlines()
    assert not [line for line in lines if line.startswith("|")]
    assert not [line for line in lines if line.startswith(("- ", "* "))]
    assert not [line for line in lines if "\u2014" in line or "\u2013" in line]
    assert not [char for char in text if ord(char) > 127], "non-ascii present"


@pytest.mark.integration
def test_the_note_tells_the_launch_story() -> None:
    """Every beat the note exists to carry, in the order a reader meets it:
    the incident, the evening loop, the store split, first contact, the
    construction problem, the cost bug, the stale hedge, the reviews, the
    alpha correction, the final state, and the lessons.
    """
    text = " ".join(NOTE.read_text().split())
    for phrase in (
        "an order is a change, not a position",
        "delta",
        "dry_run",
        "Postgres",
        "row-level security",
        "first-run",
        "universe",
        "share floor",
        "15.0945",
        "fail closed",
        "pre-launch",
        "volatility",
        "variance",
        "E12",
        "million",
    ):
        assert phrase in text, phrase
    for heading in (
        "## An order that would have gone the wrong way",
        "## What the live book is, and what runs each evening",
        "## Why the seed went into an object store and the new days into a database",
        "## The construction problem on a million dollars",
        "## The cost of a stock nobody trades, and a hedge one session stale",
        "## The reviews that found what the tests could not",
        "## The alpha that multiplied the wrong quantity",
        "## Where the book stands, and what the next thirty days measure",
        "## What this taught",
        "## Where these numbers come from",
    ):
        assert heading in text, heading


@pytest.mark.integration
def test_the_note_opens_with_the_incident() -> None:
    """The listener has no knowledge of the project, so sprint numbering
    cannot be the first thing they meet. The first two paragraphs must
    describe the order that would have gone the wrong way and must not name
    a sprint.
    """
    paragraphs = [
        block.strip()
        for block in NOTE.read_text().split("\n\n")
        if block.strip() and not block.startswith("#")
    ]
    lead = " ".join(paragraphs[:2])
    assert "order" in lead and "bought" in lead, lead[:200]
    for phrase in ("Sprint", "E11", "E12", "RG-", "G1", "G3"):
        assert phrase not in lead, phrase


@pytest.mark.integration
def test_the_note_names_its_sources() -> None:
    """A traceable document says where its numbers came from.

    Every source named here is a file in this tree, and the test above reads
    the same files. The bridge that once read two of them from the main line
    is gone: the note says so, and this asserts that no source is described as
    living somewhere other than the working tree.
    """
    text = " ".join(NOTE.read_text().split())
    for phrase in (
        "handoff/LOG.md",
        "handoff/REPORT.md",
        "handoff/PROJECT_CONTEXT.md",
        "docs/open_items.md",
        "sprints/E7/RG_SIGNAL.json",
        "RESULTS.json",
        "web/fixtures/",
        "live/clock.json",
        "There is no bridge and no second copy",
    ):
        assert phrase in text, phrase


@pytest.mark.integration
def test_the_status_report_points_at_the_note() -> None:
    text = " ".join(STATUS.read_text().split())
    assert "docs/research/E11_live_launch.md" in text


@pytest.mark.integration
def test_a_flipped_sign_is_rejected() -> None:
    stored = [-0.1994]
    assert _untraceable("the gap is 0.1994", stored) == ["0.1994"]
    assert _untraceable("the gap is -0.1994", stored) == []


@pytest.mark.integration
def test_a_fabricated_decimal_is_rejected() -> None:
    stored = [94.2573, 131.9175]
    assert _untraceable("a breadth of 94.2573", stored) == []
    assert _untraceable("a breadth of 94.2574", stored) == ["94.2574"]
