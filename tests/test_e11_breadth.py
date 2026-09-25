"""Sprint E11 pre-deploy, item 3: the breadth of the book, never an unqualified n_eff.

The stored `n_eff` was the full 499-name book's number and read as the breadth of
the book that trades. These tests pin the two qualified names, the legacy mapping
that can only ever produce the full book's number, and both pages' figures against
the real regenerated artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dashboard.tabs import d10_book
from live import breadth, dashboard_app

ROOT = Path(__file__).resolve().parents[1]
CLOSE = "2026-09-21"


def _manifest(close: str = CLOSE) -> dict:
    return json.loads(
        (ROOT / "live" / "proposals" / f"proposal_{close}.json").read_text()
    )


def _stored_weights(close: str = CLOSE) -> pd.Series:
    book = pd.read_parquet(ROOT / "live" / "proposals" / f"proposal_{close}.parquet")
    return book.set_index("ticker")["weight"]


def test_the_two_names_are_the_two_books() -> None:
    record = {"n_eff_kept": 70.59, "n_eff_full_book": 157.33}
    assert breadth.book_breadth(record) == 70.59
    assert breadth.full_book_breadth(record) == 157.33
    assert breadth.legacy_artifact(record) is False
    assert "n_eff" not in breadth.BOOK_LABEL
    assert "n_eff" not in breadth.FULL_BOOK_LABEL


def test_a_legacy_artifact_maps_to_the_full_book_only() -> None:
    """An artifact older than the split carries one n_eff, and it is not the book's."""
    legacy = {"n_eff": 157.33, "n_kept": 150}
    assert breadth.book_breadth(legacy) is None
    assert breadth.full_book_breadth(legacy) == 157.33
    assert breadth.legacy_artifact(legacy) is True
    note = breadth.breadths(legacy)
    assert note["note"] == breadth.LEGACY_NOTE
    assert note["book"] is None
    # and neither is invented from a missing field
    assert breadth.breadths({})["book"] is None
    assert breadth.breadths(None)["full_book"] is None


def test_the_stored_proposals_carry_both_names_and_no_unqualified_one() -> None:
    for close in ("2026-09-18", "2026-09-21"):
        manifest = _manifest(close)
        assert "n_eff" not in manifest
        assert manifest["n_eff_kept"] < manifest["n_eff_full_book"]
        # the book's number is the one the stored weights give, recomputed here
        weights = _stored_weights(close)
        recomputed = float(weights.abs().sum() ** 2 / (weights**2).sum())
        assert (
            manifest["n_eff_kept"] == float(f"{recomputed:.4f}")
            or abs(manifest["n_eff_kept"] - recomputed) < 1e-6
        )


def test_the_render_page_shows_the_books_breadth_and_labels_the_full_books() -> None:
    manifest = _manifest()
    columns = dashboard_app._breadth_columns(manifest)
    assert set(columns) == {breadth.BOOK_LABEL, breadth.FULL_BOOK_LABEL}
    assert columns[breadth.BOOK_LABEL] == manifest["n_eff_kept"]
    assert columns[breadth.FULL_BOOK_LABEL] == manifest["n_eff_full_book"]
    # the book's figure is the traded book's own breadth
    weights = _stored_weights()
    recomputed = float(weights.abs().sum() ** 2 / (weights**2).sum())
    assert abs(columns[breadth.BOOK_LABEL] - recomputed) < 1e-6
    assert abs(columns[breadth.FULL_BOOK_LABEL] - recomputed) > 1.0


def test_the_research_page_shows_the_books_breadth_too() -> None:
    manifest = _manifest()
    panel = d10_book.book_panel()
    assert panel[breadth.BOOK_LABEL].iloc[0] == manifest["n_eff_kept"]
    assert panel[breadth.FULL_BOOK_LABEL].iloc[0] == manifest["n_eff_full_book"]
    weights = _stored_weights()
    recomputed = float(weights.abs().sum() ** 2 / (weights**2).sum())
    assert np.isclose(panel[breadth.BOOK_LABEL].iloc[0], recomputed, atol=1e-6)
