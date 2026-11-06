"""The record script and the reader the rebuild uses have to agree for a merger.

scripts/record_merger.py writes the row by hand that merger_rows writes when the append
path applies a merger, because the append path has no record for KVUE yet. A
hand-written row that the reader does not recognise is worse than no row, so the
agreement is asserted here rather than assumed.
"""

from __future__ import annotations

import pandas as pd
import pytest

from live import corporate_actions as ca
from scripts import record_merger

TARGET, ACQUIRER, SESSION = "KVUE", "KMB", "2026-11-02"
TARGET_PREVIOUS_CLOSE = 19.31
ACQUIRER_CLOSE = 108.25
RATIO = 0.14625
CASH = 3.50
TOTAL_RETURN = (RATIO * ACQUIRER_CLOSE + CASH) / TARGET_PREVIOUS_CLOSE - 1.0


def _prices() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": ["2026-10-30", "2026-11-02"],
            "ticker": [TARGET, ACQUIRER],
            "close": [TARGET_PREVIOUS_CLOSE, ACQUIRER_CLOSE],
        }
    )


def test_the_row_the_script_writes_is_the_row_the_rule_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(record_merger.store, "select", lambda table: _prices())
    monkeypatch.setattr(record_merger, "_seed_closes", lambda: {})

    row, detail = record_merger.the_record(
        TARGET, ACQUIRER, pd.Timestamp(SESSION), RATIO, CASH
    )

    assert detail["return"] == pytest.approx(TOTAL_RETURN, abs=1e-15)
    assert f"{detail['return'] * 100:+.2f}%" == "+0.11%"
    assert detail["target_previous_session"] == pd.Timestamp("2026-10-30")

    event = ca.Merger(TARGET, ACQUIRER, pd.Timestamp(SESSION), RATIO, CASH)
    outcome = ca.MergerOutcome(
        event, pd.Timestamp(SESSION), None, detail["return"], ACQUIRER_CLOSE
    )
    applied = ca.merger_rows([outcome], pd.Timestamp(SESSION))[0]
    assert set(row) == set(applied), "the writer and the hand-recorded row disagree"
    assert {k: v for k, v in row.items() if k != "source"} == {
        k: v for k, v in applied.items() if k != "source"
    }
    assert row["source"] == "manual.record"

    records = ca.mergers_from_rows(pd.DataFrame([row]))
    assert [r.target for r in records] == [TARGET]
    assert records[0].acquirer == ACQUIRER
    assert records[0].acquirer_per_target == RATIO
    assert records[0].cash_per_share == CASH
    assert records[0].applicable


def test_an_acquirer_close_the_store_does_not_carry_stops_before_anything_is_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panel = _prices()
    panel = panel.loc[panel["ticker"] != ACQUIRER]
    monkeypatch.setattr(record_merger.store, "select", lambda table: panel)
    monkeypatch.setattr(record_merger, "_seed_closes", lambda: {})

    with pytest.raises(SystemExit, match="KMB has no stored close"):
        record_merger.the_record(TARGET, ACQUIRER, pd.Timestamp(SESSION), RATIO, CASH)


def test_the_script_refuses_to_write_where_the_rebuild_does_not_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(record_merger.store, "select", lambda table: _prices())
    monkeypatch.setattr(record_merger.store, "is_supabase", lambda: False)
    monkeypatch.setattr(record_merger, "_seed_closes", lambda: {})

    with pytest.raises(SystemExit, match="EFB_SUPABASE_DB_URL"):
        record_merger.main(["--session", SESSION, "--write"])
