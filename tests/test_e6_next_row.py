"""F6.1 is scored on the row the session carries, not on the hedge's own design.

`hedge.run` builds each hedge against the row `race.next_descriptor_design` can
build at the close - the next session's row with the cross-section taken as the
names priced at the close - and zeroing the exposures in that row is true by
construction. The row the book actually earns is the one `fx.build_design` builds
for the next session, standardized over the names priced on that session's own
date. On an ordinary session the two agree to 7e-14; on a month end the priced set
moves, and the residual is the basis exposure F6.1 now fails on.

These tests read the stored artifacts and re-derive the criterion's numbers from
them, so a stored number that disagrees with the artifact fails here rather than
reaching the record.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPOSURES = ROOT / "data" / "hedge" / "e6_exposures.parquet"
RESULTS = ROOT / "sprints" / "E6" / "RESULTS.json"


def _exposures() -> pd.DataFrame:
    if not EXPOSURES.exists():
        pytest.skip("the hedge run has not happened yet")
    return pd.read_parquet(EXPOSURES)


@pytest.mark.integration
def test_every_exposure_row_names_the_row_its_hedge_was_built_against() -> None:
    exposures = _exposures()
    assert "design_vintage" in exposures.columns
    assert "exposure_after_fmp_next_row" in exposures.columns
    assert "next_row_distance" in exposures.columns
    vintages = exposures["design_vintage"].astype(str)
    assert (vintages.str.len() > 0).all()
    # the label says which reading of the next session's row was used
    assert vintages.str.startswith(("published", "built", "stale")).all(), set(vintages)


@pytest.mark.integration
def test_the_next_row_number_is_measured_rather_than_zero_by_construction() -> None:
    """The negative control: in-model zero, real exposure through the next row.

    The in-model number is zero because the hedge subtracts the design's own
    columns; that is arithmetic, not a result. If the next-row number were also
    ~0 the measurement would be reading the same object twice, which is the
    mistake this test exists to catch.
    """
    exposures = _exposures()
    in_model = float(exposures["exposure_after_fmp"].abs().max())
    next_row = float(exposures["exposure_after_fmp_next_row"].abs().max())
    assert in_model < 1e-12, in_model
    assert math.isfinite(next_row), next_row
    assert next_row > 1e-6, (
        "the next session's row is the same object as the built row here, so the "
        "measurement is not testing anything"
    )
    assert next_row > in_model * 1e6


@pytest.mark.integration
def test_every_scored_date_has_a_next_session() -> None:
    """A missing next row would be a NaN that silently fails the criterion."""
    payload = json.loads(RESULTS.read_text())
    stored = payload["criteria"]["F6.1"]["stored_numbers"]
    assert stored["n_exposure_rows_without_a_next_row"] == 0
    assert stored["n_dates_scored_on_the_next_row"] > 0
    exposures = _exposures()
    assert not exposures["next_row_distance"].isna().any()
    assert float(exposures["next_row_distance"].max()) > 0


@pytest.mark.integration
def test_f6_1_is_scored_from_the_artifacts_and_fails_on_the_next_row() -> None:
    """The stored verdict is the arithmetic on the stored numbers, both sides."""
    payload = json.loads(RESULTS.read_text())
    block = payload["criteria"]["F6.1"]
    stored = block["stored_numbers"]
    exposures = _exposures()

    # re-derived from the artifact, not read back from the record
    assert stored["worst_abs_exposure_after_fmp"] == pytest.approx(
        float(exposures["exposure_after_fmp"].abs().max()), rel=1e-12
    )
    assert stored["worst_abs_exposure_after_fmp_next_row"] == pytest.approx(
        float(exposures["exposure_after_fmp_next_row"].abs().max()), rel=1e-12
    )
    failed = (
        stored["worst_abs_exposure_after_fmp"] >= 1e-6
        or stored["worst_abs_exposure_after_fmp_next_row"] >= 1e-6
        or stored["mean_idio_share_after_fmp"] <= 0.95
    )
    assert block["verdict"] == ("fail" if failed else "pass")
    # and it is the next-row term that decides it, so the flip is the one the
    # 2026-10-03 re-score made rather than a bound that moved
    assert stored["worst_abs_exposure_after_fmp"] < 1e-6
    assert stored["mean_idio_share_after_fmp"] > 0.95
    assert stored["worst_abs_exposure_after_fmp_next_row"] > 1e-6
    assert block["verdict"] == "fail"


@pytest.mark.integration
def test_the_vintage_counts_name_every_date_once() -> None:
    payload = json.loads(RESULTS.read_text())
    stored = payload["criteria"]["F6.1"]["stored_numbers"]
    exposures = _exposures()
    expected = {
        str(vintage): int(count)
        for vintage, count in exposures.groupby("design_vintage")["date"]
        .nunique()
        .items()
    }
    assert stored["design_vintages"] == expected
    assert sum(expected.values()) == stored["n_fmp_dates"]


def test_the_next_row_reads_the_book_over_its_own_cross_section() -> None:
    """The alignment rule, on hand-built matrices rather than on the panel.

    A name the next row does not carry holds no weight in it, and the distance
    is taken over the names the two rows share. Both are the difference between
    a measurement and a claim, so they are pinned here where they are cheap.
    """
    import numpy as np

    from efb import hedge

    names = ["A", "B"]
    design = np.array([[1.0, 1.0], [1.0, 0.0]])
    next_design = np.array([[1.0, 0.5], [1.0, -1.0]])
    held = np.array([0.6, 0.4])

    exposure, distance = hedge.next_row_exposure(
        design, names, held, next_design, ["A", "C"]
    )
    # B's weight has nowhere to go: the next row's cross-section does not carry it
    assert exposure[0] == pytest.approx(0.6)
    assert exposure[1] == pytest.approx(0.3)
    assert distance == pytest.approx(0.5)

    # the control: read through the row the hedge was built on, the exposure is
    # the book's own exposures and the rows are the same object
    same, zero = hedge.next_row_exposure(design, names, held, design, names)
    assert same[0] == pytest.approx(0.6 + 0.4)
    assert same[1] == pytest.approx(0.6)
    assert zero == pytest.approx(0.0)
