"""The record script, and the reader the rebuild uses, have to agree.

`scripts/record_spinoff.py` writes the row by hand that `spinoff_rows` writes when
the append path applies a spin-off, because the append path had no record for CTVA
and the print stood. A hand-written row that the reader does not recognise is worse
than no row, so the agreement is asserted here rather than assumed.
"""

from __future__ import annotations

import pandas as pd
import pytest

from live import corporate_actions as ca
from scripts import record_spinoff

CTVA, VYLR, SESSION = "CTVA", "VYLR", "2026-10-01"
PARENT_PREVIOUS_CLOSE = 77.6500015258789
PARENT_CLOSE = 12.5699996948242
CHILD_CLOSE = 68.2600021362305
RAW_PRINT = -0.8381197753018084
TOTAL_RETURN = 0.04095299733015434


def _prices() -> pd.DataFrame:
    """The three rows the appendix carries, in the appendix's own layout."""
    return pd.DataFrame(
        {
            "trade_date": ["2026-09-30", "2026-10-01", "2026-10-01"],
            "ticker": [CTVA, CTVA, VYLR],
            "close": [PARENT_PREVIOUS_CLOSE, PARENT_CLOSE, CHILD_CLOSE],
        }
    )


def test_the_row_the_script_writes_is_the_row_the_rule_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The closes are the input and the return is derived, field for field."""
    monkeypatch.setattr(record_spinoff.store, "select", lambda table: _prices())
    monkeypatch.setattr(record_spinoff, "_seed_closes", lambda: {})

    row, detail = record_spinoff.the_record(CTVA, VYLR, pd.Timestamp(SESSION), 1.0, 1.0)

    assert detail["return"] == pytest.approx(TOTAL_RETURN, abs=1e-15)
    assert f"{detail['return'] * 100:+.2f}%" == "+4.10%"
    assert detail["raw_print"] == pytest.approx(RAW_PRINT)
    assert f"{detail['raw_print'] * 100:+.2f}%" == "-83.81%", "the run's own flag"
    assert detail["parent_previous_session"] == pd.Timestamp("2026-09-30")

    # what `spinoff_rows` writes for the same event, so the two cannot drift
    event = ca.SpinoffOutcome(
        ca.Spinoff(CTVA, VYLR, pd.Timestamp(SESSION), 1.0),
        pd.Timestamp(SESSION),
        detail["raw_print"],
        detail["return"],
        CHILD_CLOSE,
    )
    applied = ca.spinoff_rows([event], pd.Timestamp(SESSION))[0]
    assert set(row) == set(applied), "the writer and the hand-recorded row disagree"
    assert {key: value for key, value in row.items() if key != "source"} == {
        key: value for key, value in applied.items() if key != "source"
    }
    assert row["source"] == "manual.record", "recorded here, not applied by the run"

    # and the reader the rebuild runs gives the record back
    records = ca.spinoffs_from_rows(pd.DataFrame([row]))
    assert [record.parent for record in records] == [CTVA]
    assert records[0].child == VYLR
    assert records[0].ex_date == pd.Timestamp(SESSION)
    assert records[0].child_per_parent == 1.0
    assert records[0].applicable


def test_a_child_close_the_store_does_not_carry_stops_before_anything_is_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The return is derived from the child's close, and a guess is not a record."""
    panel = _prices()
    panel = panel.loc[panel["ticker"] != VYLR]
    monkeypatch.setattr(record_spinoff.store, "select", lambda table: panel)
    monkeypatch.setattr(record_spinoff, "_seed_closes", lambda: {})

    with pytest.raises(SystemExit, match="VYLR has no stored close"):
        record_spinoff.the_record(CTVA, VYLR, pd.Timestamp(SESSION), 1.0, 1.0)


def test_the_script_refuses_to_write_where_the_rebuild_does_not_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without the store URL the write would land in the local fallback."""
    monkeypatch.setattr(record_spinoff.store, "select", lambda table: _prices())
    monkeypatch.setattr(record_spinoff.store, "is_supabase", lambda: False)
    monkeypatch.setattr(record_spinoff, "_seed_closes", lambda: {})

    with pytest.raises(SystemExit, match="EFB_SUPABASE_DB_URL"):
        record_spinoff.main(["--session", SESSION, "--write"])
