"""With the flags off the manifest is `main`'s, key for key.

The owner's rule, and the one the branch merged on: a run that did not ask for a
calendar must write the manifest it always wrote. The calendar block, the held-book
flag, the reversal and unfilled-leg maps, the guard record and the held-back target
exist only when `EFB_CADENCE > 1`, so a flag-less run emits none of them.

The whole-manifest comparison against `main` is a proof run by hand (see
`docs/cadence_flag.md`, "the manifest, key for key"); what is pinned here is the
property that makes it true and that a later change can break without noticing.
"""

from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from live import cadence, evening_job

ROOT = pathlib.Path(__file__).resolve().parents[1]
# The calendar-only keys: everything the branch adds to the manifest.
CALENDAR_KEYS = (
    "cadence",
    "drift_guard",
    "held_book",
    "left_universe",
    "reversal_targets",
    "target_book_held_back",
    "unfilled_remainder",
)


def _build(**over: object) -> dict[str, object]:
    return evening_job.build_proposal(
        data_root=ROOT / "data",
        as_of=pd.Timestamp("2026-09-21"),
        store=False,
        previous=pd.Series({"AAPL": 0.01, "MSFT": -0.01, "KO": 0.005}),
        **over,  # type: ignore[arg-type]
    )


@pytest.mark.slow
def test_the_daily_loop_writes_no_calendar_keys() -> None:
    manifest = _build()
    absent = [key for key in CALENDAR_KEYS if key in manifest]
    assert absent == [], f"a flag-less run emitted {absent}"


@pytest.mark.slow
def test_a_calendar_run_writes_every_calendar_key() -> None:
    manifest = _build(
        cadence_mode=21,
        cadence_anchor="2026-09-18",
        completed_rebalances=["2026-09-18"],
    )
    assert manifest["cadence"]["k"] == 21
    assert manifest["cadence"]["day"] == cadence.HOLD
    missing = [key for key in CALENDAR_KEYS if key not in manifest]
    assert missing == [], f"a hold day did not write {missing}"


@pytest.mark.slow
def test_the_calendar_keys_appear_with_the_flag_and_not_before() -> None:
    """The same close, built both ways: the difference is exactly the keys."""
    daily = set(_build())
    monthly = set(
        _build(
            cadence_mode=21,
            cadence_anchor="2026-09-18",
            completed_rebalances=["2026-09-18"],
        )
    )
    assert monthly - daily == set(CALENDAR_KEYS)
    assert daily - monthly == set()
