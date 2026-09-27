"""Sprint E11 Task 10: the walkthrough, its render and the criteria it leaves open.

The notebook is the promotion artifact for the book, so the things worth pinning
about it are that it actually ran, that the three criteria appear as **pending**
rather than as verdicts, that the close and the traced name were read rather than
typed, and that no stored number was typed into it by hand.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "E11_walkthrough.ipynb"
RESULTS = ROOT / "sprints" / "E11" / "RESULTS.json"

CRITERIA = ("F11.1", "F11.2", "F11.3")

# A decimal with four or more digits on either side of the point: the shape a
# stored number takes when somebody pastes the answer instead of reading it.
PASTED_NUMBER = re.compile(r"\d\.\d{4,}|\d{5,}\.\d")


def _notebook() -> dict:
    if not NOTEBOOK.exists():
        pytest.skip("the E11 walkthrough is not written yet")
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


def test_the_walkthrough_has_been_executed() -> None:
    notebook = _notebook()
    executed = [
        cell
        for cell in notebook["cells"]
        if cell["cell_type"] == "code" and cell.get("execution_count")
    ]
    assert len(executed) >= 12, "the walkthrough has not been executed"
    printed = _printed(notebook)
    # One evening, end to end: the gate, the book, the hedge, the cost and the email
    # all have to have produced something, or the notebook is a sketch.
    for marker in (
        "one evening traced end to end at the close",
        "live/staleness.py::check",
        "enforce_floor_by_drop_then_admit",
        "worst exposure after the hedge",
        "efb/costs.py",
        "live/notify.py",
        "live/staleness.py::run_status_row",
    ):
        assert marker in printed, f"the notebook never printed {marker!r}"


def test_every_criterion_appears_and_none_is_claimed() -> None:
    """All three are statements about thirty live days, so none may carry a verdict."""
    notebook = _notebook()
    joined = _code_source(notebook) + "\n" + _printed(notebook)
    payload = json.loads(RESULTS.read_text())
    for name in CRITERIA:
        assert name in joined, name
        assert payload["criteria"][name]["verdict"] == "pending", name
    assert "PENDING" in _printed(notebook), "the notebook does not print the verdicts"


def test_the_close_is_read_from_the_price_panel_not_typed() -> None:
    """The evening has to be the one the stored artifacts can price, by construction."""
    source = _code_source(_notebook())
    assert "CLOSE = pd.Timestamp(prices.index.get_level_values('date').max())" in source
    assignments = re.findall(r"^CLOSE\s*=\s*(.+)$", source, flags=re.MULTILINE)
    assert assignments == ["pd.Timestamp(prices.index.get_level_values('date').max())"]


def test_the_traced_name_is_taken_from_the_book_and_its_absence_reported() -> None:
    """The brief names LITE, so the notebook has to say when LITE is not there."""
    notebook = _notebook()
    source = _code_source(notebook)
    printed = _printed(notebook)
    assert "argmax" in source, "the traced name is not chosen from the book"
    assert "is NOT in the book" in source, "an absent traced name passes silently"
    assert "the traced name is" in printed or "is NOT in the book" in printed


def test_no_stored_number_is_typed_by_hand() -> None:
    notebook = _notebook()
    source = _code_source(notebook)
    offenders = sorted(set(PASTED_NUMBER.findall(source)))
    assert offenders == [], f"numbers typed into the notebook: {offenders}"
    # And the checks are against stored files rather than against the notebook's own
    # output: the client order id is verified on ids that are actually stored.
    assert "client_order_id" in source
