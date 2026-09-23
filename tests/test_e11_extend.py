"""Sprint E11 live: incremental extension integrity.

Rows dated on or before 2026-09-03 in descriptors, factor_returns and
specific_returns are frozen invariants: every extension appends new
sessions without touching them. The pre-cutoff block hashes are recorded
here and asserted, and the extension must have added sessions after the
frozen as-of.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from live import extend

ROOT = Path(__file__).resolve().parents[1]
XS = ROOT / "data" / "models" / "XS-v1"

# recorded before the first extension, and unchanged after it
BASELINE = {
    "descriptors": ("8f93968f67f31cd33453a7fad13685d74748f3f480f17406954459fdd31caafa"),
    "factor_returns": (
        "42a31d64e0cb7619f09669cfdac217085172ccd577ee37c304da6bab3246700a"
    ),
    "specific_returns": (
        "176dc4b39fb75f1dae6afd0f6afea3b14c64bd6ebcc855450d392d46bd9d489a"
    ),
}


def test_block_hash_is_deterministic() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2026-09-01", "2026-09-02"],
            "ticker": ["A", "A"],
            "descriptor": ["size", "size"],
            "value": [1.0, 2.0],
        }
    )
    assert extend._block_hash(frame, pd.Timestamp("2026-09-03")) == extend._block_hash(
        frame, pd.Timestamp("2026-09-03")
    )


@pytest.mark.integration
@pytest.mark.slow
def test_pre_cutoff_blocks_are_byte_identical() -> None:
    if not (XS / "factor_returns.parquet").exists():
        pytest.skip("XS-v1 artifacts not built")
    current = extend.incremental_integrity()
    for name, expected in BASELINE.items():
        assert current[name] == expected, name


@pytest.mark.integration
def test_sessions_after_the_frozen_as_of_were_appended() -> None:
    for name in ("descriptors", "factor_returns", "specific_returns"):
        frame = pd.read_parquet(XS / f"{name}.parquet")
        last = pd.to_datetime(frame["date"]).max()
        assert last > pd.Timestamp("2026-09-03"), name


@pytest.mark.integration
@pytest.mark.slow
def test_identity_drops_do_not_reappear_in_the_extension() -> None:
    """The extension applies the E1 identity exclusions, so a reused
    symbol does not come back with another company's history. DD is the
    one dropped ticker the sector file maps, so it is the one the buggy
    extension put back into returns and specific_returns.
    """
    returns_frame = pd.read_parquet(ROOT / "data" / "processed" / "returns.parquet")
    specific = pd.read_parquet(XS / "specific_returns.parquet")
    assert "DD" not in set(returns_frame.index.get_level_values("ticker"))
    assert "DD" not in set(specific["ticker"])
