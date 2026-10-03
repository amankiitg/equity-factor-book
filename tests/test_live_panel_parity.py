"""One panel, two readers: the live model fit and the next-session design.

The hedge is solved against the design row the model will date with the next
session, and that row is built (when the tree publishes nothing for it) from the
same panel the model fit reads. If the two readers disagree about the panel they
disagree about who is in the cross-section, and the hedge then zeroes exposures
against a cross-section that does not exist.

This branch splits them. `race.next_descriptor_design` was changed to build on
`returns_clean` (the panel with flagged cells masked), while `live/extend.py`
still reads `inputs["returns"]`. On a live tree the two are the same numbers, so
nothing observes the split *yet* - but on the regenerated seed they are not, and
after the merge the branch is what makes them the same frame read twice.

So there are two tests here:

- `test_the_live_fit_and_the_next_design_read_one_panel` is a merge guard. It
  fails today, on purpose, and passes the moment `live/extend.py` is changed to
  read `returns_clean` in the same commit that lands this branch. It is marked
  `merge_guard`, so the default suite deselects it and reports the deselection
  rather than skipping it quietly; docs/backport_runbook.md carries it as the
  first item of the merge checklist, to be run as
  `pytest tests/test_live_panel_parity.py -m merge_guard`.
- `test_the_built_row_reads_the_cleaned_panel` is behaviour, and passes today.
  It shows what "the two readers disagree" would mean if it were left alone: a
  name whose cell is masked drops out of the built row's cross-section, so the
  design the hedge is solved against changes.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb import probes, race
from efb.models import fundamental as fx

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def _function_source(path: Path, name: str) -> str:
    """The source of the top-level function `name`, up to the next one.

    Read as text rather than imported so the assertion is about what the live
    loop will run, including a call site that no test can reach without a live
    tree.
    """
    lines = path.read_text().splitlines(keepends=True)
    start = None
    for index, line in enumerate(lines):
        if line.startswith(f"def {name}("):
            start = index
            break
    if start is None:
        raise AssertionError(f"{name} is not defined in {path}")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("def ") or line.startswith("class ") or line.startswith("@"):
            end = index
            break
    return "".join(lines[start:end])


def _panel_keys(source: str) -> set[str]:
    """The panel keys a function reads its returns frame from."""
    keys = set(re.findall(r"""(?:inputs|panel)\[["']([a-z_]+)["']\]""", source))
    return keys & {"returns", "returns_clean"}


@pytest.mark.merge_guard
def test_the_live_fit_and_the_next_design_read_one_panel() -> None:
    """The merge guard: both readers must take the same frame from the panel.

    Fails today. The fix is the merge commit, not a test edit: change
    `live/extend.py::extend_model` to read `inputs["returns_clean"]` in the same
    commit that lands this branch, so that the live model fit and
    `efb/race.py::next_descriptor_design` read one panel.
    """
    fit = _panel_keys(_function_source(ROOT / "live" / "extend.py", "extend_model"))
    hedge = _panel_keys(
        _function_source(ROOT / "efb" / "race.py", "next_descriptor_design")
    )

    assert fit, "extend_model reads no panel key at all - has it been rewritten?"
    assert hedge, "next_descriptor_design reads no panel key - has the builder moved?"
    assert fit == hedge == {"returns_clean"}, (
        "the live model fit reads "
        f"{sorted(fit)} and the next-session design reads {sorted(hedge)}. "
        "At merge, live/extend.py must read returns_clean as well, in the same "
        "commit, so the live model fit and next_descriptor_design use the same "
        "panel. See docs/backport_runbook.md."
    )


def _mapped_columns(panel: dict[str, object]) -> list[str]:
    mapped = panel["mapped"]
    assert isinstance(mapped, list)
    return [str(name) for name in mapped]


def test_the_built_row_reads_the_cleaned_panel() -> None:
    """A masked cell leaves the cross-section the hedge is solved against.

    The built row's cross-section is the set of names priced on the row's own
    date, which `next_descriptor_design` reads off the frame it is given. Pick
    the final session of the tree - the one shape in which no published row
    exists and the row is built here - and mask one name's cell. Read off the
    cleaned frame the name is out of the cross-section and its z is zero, which
    is the record of a print the rule replaced; read off the raw frame it is in
    and its z is not.
    """
    panel = probes.load_panel(DATA)
    clean = panel["returns_clean"]
    raw = panel["returns"]
    assert isinstance(clean, pd.DataFrame) and isinstance(raw, pd.DataFrame)

    stamp = pd.DatetimeIndex(clean.index).max()
    assert race._session_after(pd.Timestamp(stamp), DATA) is None, (
        f"{stamp.date()} is not the last session of this tree, so the row would "
        "come from the published artifact and this test would assert nothing"
    )

    priced = clean.loc[stamp].dropna()
    mapped = [name for name in _mapped_columns(panel) if name in set(priced.index)]
    assert len(mapped) > 5, "too few names priced at the final session to test with"
    name = mapped[0]

    assert not np.allclose(_styles(races_row(panel, stamp, name, mask=None)), 0.0), (
        "the control failed: the name is not in the cross-section before masking, "
        "so masking it proves nothing"
    )
    assert np.allclose(_styles(races_row(panel, stamp, name, mask=name)), 0.0), (
        "a name whose cell was masked is still in the cross-section the hedge is "
        "solved against, so the built row is not reading the cleaned panel"
    )


def _styles(row: np.ndarray) -> np.ndarray:
    """The style block of a design row.

    `race._design_from_styles` assembles the row as the constant, then one
    column per non-market style in `fx.STYLE_NAMES` order, then one dummy per
    estimated sector. The sector dummies survive a masked cell - the name still
    has a sector - so the styles are the part a mask can zero, and they are the
    part the hedge is solved against.
    """
    styles = [name for name in fx.STYLE_NAMES if name != "market"]
    return row[1 : 1 + len(styles)]


def races_row(
    panel: dict[str, object], stamp: pd.Timestamp, name: str, *, mask: str | None
) -> np.ndarray:
    """`next_descriptor_design`'s row for one name, with `mask` dropped.

    The design is returned as a bare matrix whose rows follow the `names` order,
    so asking for one name gives a one-row answer and the row is the whole of
    what a mask can change.
    """
    clean = panel["returns_clean"]
    assert isinstance(clean, pd.DataFrame)
    frame = clean if mask is None else clean.copy()
    if mask is not None:
        frame.loc[stamp, mask] = np.nan
    shaped = dict(panel)
    shaped["returns_clean"] = frame

    def fake_loader(root: Path | None = None) -> dict[str, object]:
        return shaped

    monkey = pytest.MonkeyPatch()
    monkey.setattr(probes, "load_panel", fake_loader)
    try:
        design, label = race.next_descriptor_design(pd.Timestamp(stamp), [name], DATA)
    finally:
        monkey.undo()
    assert label.startswith("built from data through"), label
    assert design.shape[0] == 1, design.shape
    return np.asarray(design[0], dtype=float)


def test_the_guard_is_named_where_the_suite_summary_will_show_it() -> None:
    """The merge guard is a marker, so a default run reports it as deselected."""
    assert "merge_guard" in (ROOT / "pyproject.toml").read_text(), (
        "the merge_guard marker is not registered, so deselecting it would be a "
        "warning rather than a selection"
    )
    runbook = ROOT / "docs" / "backport_runbook.md"
    assert runbook.exists(), "the merge checklist the guard belongs to is missing"
    assert "test_live_panel_parity" in runbook.read_text()
