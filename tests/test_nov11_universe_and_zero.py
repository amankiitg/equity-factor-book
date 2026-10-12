"""The universe is deduplicated, and a zero variance is refused on both sides."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts import run_live_daily


def test_the_zero_refusal_is_the_same_predicate_as_the_drop() -> None:
    # The drop rejects a value that is not positive; the write refused only what was
    # not finite. Item 15: one predicate, both sides.
    with pytest.raises(ValueError, match="no specific variance"):
        run_live_daily.specific_std_or_refuse(
            "AAA", {"AAA": 0.0}, pd.Timestamp("2026-09-21")
        )
    with pytest.raises(ValueError, match="no specific variance"):
        run_live_daily.specific_std_or_refuse(
            "AAA", {"AAA": float("nan")}, pd.Timestamp("2026-09-21")
        )
    with pytest.raises(ValueError, match="no specific variance"):
        run_live_daily.specific_std_or_refuse(
            "AAA", {"AAA": -1e-6}, pd.Timestamp("2026-09-21")
        )
    # The value is stored as it arrives: the column that holds it is `idio_vol`,
    # and the refusal is about whether it is an estimate at all.
    assert run_live_daily.specific_std_or_refuse(
        "AAA", {"AAA": 4e-4}, pd.Timestamp("2026-09-21")
    ) == pytest.approx(4e-4)


def test_a_positive_variance_still_passes() -> None:
    value = run_live_daily.specific_std_or_refuse(
        "AAA", {"AAA": 1e-4}, pd.Timestamp("2026-09-21")
    )
    assert value == pytest.approx(1e-4)
