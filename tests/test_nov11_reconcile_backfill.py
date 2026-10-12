"""The morning fills in the two columns the evening could only placeholder."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from live import reconcile, store


def evening_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trade_date": "2026-10-08",
        "forecast_annual_vol": 0.0266,
        "realized_annual_vol": float("nan"),
        "gross": 1.0,
        "net": 0.0,
        "intended_notional": 506978.0,
        "filled_notional": 0.0,
        "expected_cost_bps": 14.23,
        "unexplained_adjustment": 0.0,
    }
    row.update(overrides)
    return row


def test_the_backfill_replaces_two_columns_and_leaves_the_rest_alone(
    monkeypatch,
) -> None:
    frame = pd.DataFrame([evening_row()])
    written: list[tuple[str, list[dict[str, object]]]] = []
    monkeypatch.setattr(store, "select", lambda table: frame.copy())
    monkeypatch.setattr(
        store, "upsert", lambda table, rows: written.append((table, rows))
    )

    row = reconcile.backfill(
        "2026-10-08", filled_notional=496340.86, realized_annual_vol=0.0123
    )

    assert row is not None
    assert row["filled_notional"] == 496340.86
    assert row["realized_annual_vol"] == 0.0123
    # Everything the evening wrote is still there, including the NaN turned into a
    # null rather than sent to Postgres as a float non-number.
    assert row["intended_notional"] == 506978.0
    assert row["expected_cost_bps"] == 14.23
    assert written and written[0][0] == "reconciliation"
    assert len(written[0][1]) == 1


def test_a_row_that_is_not_there_is_left_alone(monkeypatch) -> None:
    monkeypatch.setattr(store, "select", lambda table: pd.DataFrame([evening_row()]))
    calls: list[object] = []
    monkeypatch.setattr(store, "upsert", lambda table, rows: calls.append(rows))
    assert reconcile.backfill("2026-10-09", filled_notional=1.0) is None
    assert calls == []


def test_nothing_to_say_writes_nothing(monkeypatch) -> None:
    monkeypatch.setattr(store, "select", lambda table: pd.DataFrame([evening_row()]))
    calls: list[object] = []
    monkeypatch.setattr(store, "upsert", lambda table, rows: calls.append(rows))
    assert reconcile.backfill("2026-10-08") is None
    assert calls == []


def test_the_realized_vol_is_the_window_the_page_uses() -> None:
    # 63 sessions of noise with a known dispersion, plus a session after the close
    # that must not be read: the row describes what was known at the close.
    values = [0.001 * value for value in range(70)]
    rows = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-07-01", periods=70, freq="D"),
            "pnl_total": values,
            "forecast_vol": [0.02] * 70,
        }
    )
    value = reconcile.realized_annual_vol_for("2026-08-31", rows)
    used = rows.loc[pd.to_datetime(rows["trade_date"]) <= pd.Timestamp("2026-08-31")]
    window = used["pnl_total"].to_numpy(dtype=float)[-63:]
    assert value == pytest.approx(float(np.std(window, ddof=1) * np.sqrt(252.0)))
    # One session is not a dispersion, and neither is none.
    assert reconcile.realized_annual_vol_for("2026-07-01", rows) is None
    assert reconcile.realized_annual_vol_for("2026-08-31", pd.DataFrame()) is None
