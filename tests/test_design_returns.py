"""`EFB_DESIGN_RETURNS`: which panel the built design row comes from.

`probes.load_panel` returns two frames of the same panel: `returns`, the file's own
rows, and `returns_clean`, the same panel with the hygiene-flagged rows masked. The
XS-v1 fit reads the cleaned one, so a design row built from the raw one disagrees
with the row the model publishes for the same session; the loop has always built
from the raw one, and the difference is a live behaviour change rather than a
tidy-up (measured on the 2026-10-13 close: two masked cells inside the 400-session
window move 1,477 of the 8,534 design cells, and the kept book goes from 171 names
to 186). So the choice is a flag, `raw` by default, and this file pins all three
cases of it.
"""

from __future__ import annotations

import logging

import pandas as pd
import pytest

from efb import race


def _mode(monkeypatch: pytest.MonkeyPatch, value: str | None) -> str:
    """The mode the module resolves for one value of the flag, cache and all."""
    monkeypatch.setattr(race, "_DESIGN_RETURNS_CACHE", None)
    if value is None:
        monkeypatch.delenv(race.DESIGN_RETURNS_ENV, raising=False)
    else:
        monkeypatch.setenv(race.DESIGN_RETURNS_ENV, value)
    return race.design_returns()


@pytest.mark.parametrize("value", [None, "", "raw", "raw ", "RAW", "Raw"])
def test_the_default_is_the_raw_panel(
    value: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unset, empty and `raw` in any case are the same setting."""
    assert _mode(monkeypatch, value) == race.DESIGN_RETURNS_RAW


def test_the_one_other_value_the_loop_reacts_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _mode(monkeypatch, "clean") == race.DESIGN_RETURNS_CLEAN
    assert _mode(monkeypatch, " CLEAN ") == race.DESIGN_RETURNS_CLEAN


@pytest.mark.parametrize("value", ["cleaned", "clen", "yes", "1", "returns_clean"])
def test_a_typo_falls_back_to_the_raw_panel_and_says_so(
    value: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A typo must never change the book, and it must not be silent either."""
    with caplog.at_level(logging.WARNING):
        resolved = _mode(monkeypatch, value)

    assert resolved == race.DESIGN_RETURNS_RAW
    assert f"{race.DESIGN_RETURNS_ENV}={value!r} is not a panel" in caplog.text
    assert "the raw panel is used" in caplog.text


def test_the_mode_is_decided_once_and_then_remembered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A start-of-run decision, so a value that changed mid-run cannot split a book."""
    assert _mode(monkeypatch, race.DESIGN_RETURNS_CLEAN) == race.DESIGN_RETURNS_CLEAN
    monkeypatch.setenv(race.DESIGN_RETURNS_ENV, "raw")
    assert race.design_returns() == race.DESIGN_RETURNS_CLEAN, "read once per process"

    monkeypatch.setattr(race, "_DESIGN_RETURNS_CACHE", None)
    assert race.design_returns() == race.DESIGN_RETURNS_RAW


def _panel() -> dict[str, object]:
    """A panel whose two frames are distinguishable, which is the whole point."""
    raw = pd.DataFrame({"AAA": [0.01, 0.02], "BBB": [0.03, 0.04]})
    clean = pd.DataFrame({"AAA": [0.01, float("nan")], "BBB": [0.03, 0.04]})
    return {"returns": raw, "returns_clean": clean}


def test_the_built_row_reads_the_panel_the_flag_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one line the flag controls, on both settings.

    `raw` is the file's own rows and the default; `clean` is the masked panel, and
    the frame that comes back is the one the row is standardised over.
    """
    panel = _panel()
    raw: pd.DataFrame = panel["returns"]  # type: ignore[assignment]
    clean: pd.DataFrame = panel["returns_clean"]  # type: ignore[assignment]

    assert _mode(monkeypatch, None) == race.DESIGN_RETURNS_RAW
    assert race.design_panel(panel) is raw
    assert race.design_panel(panel).equals(raw)

    assert _mode(monkeypatch, race.DESIGN_RETURNS_CLEAN) == race.DESIGN_RETURNS_CLEAN
    assert race.design_panel(panel) is clean
    assert not race.design_panel(panel).equals(raw), "the fixture must differ"

    # the control: with the flag unset again the choice is back, so the assertion
    # above is about the flag rather than about which frame happened to be handed in
    assert _mode(monkeypatch, None) == race.DESIGN_RETURNS_RAW
    assert race.design_panel(panel) is raw
