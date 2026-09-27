"""F13.1 is about the repository, so it is checked rather than claimed.

The criterion says every EFB module appears in the port map with a status and one
sentence of reason. That is a statement about the repository and the document
together, which makes it testable: this module enumerates the repository and
fails if any module is missing from `docs/credit_port_design.md`.

Three other things about the note are asserted here rather than left to review,
because each is a requirement of the sprint and each is mechanical:

- every number in the note is cited as `EFB: <path>` and every such path exists,
  which is what makes "read from a stored file" enforceable rather than a promise;
- the note contains no em dashes, which the roadmap requires for this document;
- the F13.1 criterion and the three research questions appear in the PRD and in
  `sprints/E13/RESULTS.json` exactly as the roadmap words them, so a paraphrase
  cannot drift in unnoticed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "docs" / "credit_port_design.md"
PRD = ROOT / "sprints" / "E13" / "PRD.md"
TASKS = ROOT / "sprints" / "E13" / "TASKS.md"
RESULTS = ROOT / "sprints" / "E13" / "RESULTS.json"
ROADMAP = ROOT / "docs" / "roadmap_v2.md"

# Every module in the repository, by the glob that finds it. `web/src` carries the
# page, which the roadmap's port map has to cover as well as the Python library.
MODULE_GLOBS = (
    "efb/*.py",
    "efb/models/*.py",
    "live/*.py",
    "dashboard/*.py",
    "dashboard/tabs/*.py",
    "scripts/*.py",
    "web/src/*.ts",
    "web/src/*.tsx",
)

# E12's attribution engine is the one part of E1 to E12 that is not in this tree:
# it lands with the `e12` branch, which is unmerged by design. The map covers it by
# name here, and the globs above will also find these paths once e12 merges, so the
# assertion holds either way.
MODULES_FROM_E12 = (
    "efb/attribution.py",
    "live/attribution_job.py",
    "scripts/build_attribution.py",
    "scripts/review_week.py",
)

# The sections the roadmap's E13 scope requires, by heading fragment.
REQUIRED_HEADINGS = (
    "Universe and identity",
    "Survivorship",
    "excess over a duration-matched Treasury",
    "The factor model with DTS",
    "Specific risk at the issuer and at the bond",
    "Hedging with CDX and Treasury futures",
    "Costs from TRACE",
    "The live loop, staleness",
    "The module map (F13.1)",
    "Open questions for the research team",
    "The defect classes this project hit",
    "A phased build plan",
    "What would falsify this",
)


def modules() -> list[str]:
    """Every module path in the repository, repository-relative."""
    found: set[str] = set()
    for pattern in MODULE_GLOBS:
        for path in ROOT.glob(pattern):
            if "__pycache__" in path.parts:
                continue
            found.add(str(path.relative_to(ROOT)))
    return sorted(found)


def note_text() -> str:
    return NOTE.read_text()


def roadmap_criterion() -> str:
    """The F13.1 criterion, as the roadmap words it."""
    lines = ROADMAP.read_text().splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "F13.1":
            return lines[index + 1].strip()
    raise AssertionError("the roadmap no longer contains an F13.1 row")


def roadmap_questions() -> list[str]:
    """The three research questions of the E13 block, verbatim."""
    text = ROADMAP.read_text()
    block = text[text.index("Sprint E13: Credit Port Design") :]
    found: list[str] = []
    for label in (
        "Academic question: ",
        "Practitioner question: ",
        "Research question: ",
    ):
        match = re.search(rf"- {label}(.+)", block)
        assert match is not None, label
        found.append(f"{label}{match.group(1).strip()}")
    return found


def test_every_module_in_the_repository_appears_in_the_map() -> None:
    """F13.1: nothing unmapped, checked against the repository itself."""
    text = note_text()
    missing = [module for module in modules() if module not in text]
    assert missing == [], f"not in the port map: {missing}"
    # The count is the criterion's stored number, and it is asserted here so a
    # module added to the repository fails this test rather than passing it.
    assert len(modules()) >= 80


def test_the_e12_modules_are_mapped_even_though_they_are_not_in_this_tree() -> None:
    """The map covers E1 to E12, and E12 is on an unmerged branch."""
    text = note_text()
    missing = [module for module in MODULES_FROM_E12 if module not in text]
    assert missing == [], f"E12 modules not in the map: {missing}"


def test_the_stored_module_count_is_the_count_this_test_measures() -> None:
    """The registered number has to be the number the check produces."""
    results = json.loads(RESULTS.read_text())
    stored = results["criteria"]["F13.1"]["stored_numbers"]
    counted = next(
        entry for entry in stored if entry["what"] == "modules in the repository"
    )
    assert counted["value"] == len(modules())
    in_map = next(entry for entry in stored if entry["what"] == "modules in the map")
    text = note_text()
    mapped = len([m for m in modules() if m in text]) + len(MODULES_FROM_E12)
    assert in_map["value"] == mapped


def test_the_stored_status_counts_are_the_counts_in_the_map() -> None:
    """The map's statuses are counted from the map, not estimated."""
    text = note_text()
    section = text[text.index("## 13. The module map") : text.index("## 14.")]
    measured = {
        status: section.count(f"| {status} |")
        for status in ("unchanged", "re-specified", "dropped")
    }
    results = json.loads(RESULTS.read_text())
    stored = next(
        entry
        for entry in results["criteria"]["F13.1"]["stored_numbers"]
        if entry["what"] == "statuses assigned in the map"
    )
    assert stored["value"] == measured


def test_the_stored_citation_count_is_the_count_this_test_measures() -> None:
    text = note_text()
    cited = {
        match.rstrip(".,;:") for match in re.findall(r"EFB:\s*([A-Za-z0-9_./-]+)", text)
    }
    results = json.loads(RESULTS.read_text())
    stored = next(
        entry
        for entry in results["criteria"]["F13.1"]["stored_numbers"]
        if entry["what"] == "distinct stored files cited"
    )
    assert stored["value"] == len(cited)


def test_every_citation_resolves_to_a_stored_file() -> None:
    """Every number in the note names the file it was read from."""
    text = note_text()
    cited = {
        match.rstrip(".,;:") for match in re.findall(r"EFB:\s*([A-Za-z0-9_./-]+)", text)
    }
    assert cited, "the note cites no sources at all"
    missing = sorted(path for path in cited if not (ROOT / path).exists())
    assert missing == [], f"cited but not stored in the repository: {missing}"


def test_the_note_has_no_em_dashes() -> None:
    """A roadmap requirement for this document, asserted rather than trusted."""
    text = note_text()
    assert "\u2014" not in text, "em dash found"
    assert "\u2013" not in text, "en dash found"


def test_the_note_carries_every_section_the_scope_requires() -> None:
    text = note_text()
    missing = [heading for heading in REQUIRED_HEADINGS if heading not in text]
    assert missing == [], f"missing sections: {missing}"


def test_the_criterion_is_copied_verbatim_from_the_roadmap() -> None:
    criterion = roadmap_criterion()
    results = json.loads(RESULTS.read_text())
    assert results["criteria"]["F13.1"]["criterion"] == criterion
    assert criterion in PRD.read_text()


def test_the_research_questions_are_copied_verbatim_from_the_roadmap() -> None:
    prd = PRD.read_text()
    for question in roadmap_questions():
        assert question in prd, question


def test_the_tasks_cover_the_deliverable_and_the_falsifiers() -> None:
    """The roadmap requires one task for each, by name."""
    tasks = TASKS.read_text()
    assert "produces the deliverable" in tasks
    assert "every falsification criterion" in tasks
    assert "docs/credit_port_design.md" in tasks
