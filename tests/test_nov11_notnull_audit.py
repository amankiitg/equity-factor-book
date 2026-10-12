"""The NaN audit: the 28 declared columns, and a NaN in one of them is a failure."""

from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from scripts import nov11_notnull_audit as audit


def test_the_declared_columns_are_the_schema_s_own_not_null_numerics() -> None:
    columns = audit.not_null_numeric_columns()
    flat = {f"{table}.{column}" for table, cols in columns.items() for column in cols}
    # The 28 the runbook counts, and the three that are the reason the audit exists:
    # `idio_vol` is the column the 2026-10-07 evening died on, and the other two are
    # the placeholders items 26 and 33 were about.
    assert len(flat) == 28, sorted(flat)
    assert "positions.idio_vol" in flat
    assert "orders.intended_notional" in flat
    assert "orders.filled_notional" in flat
    # A nullable column is not in the list, and neither is a date or a text.
    assert "positions.ticker" not in flat
    assert "reconciliation.realized_annual_vol" not in flat
    assert "reconciliation.filled_notional" not in flat


def test_a_nan_is_found_and_fails_the_run(tmp_path: pathlib.Path) -> None:
    frame = pd.DataFrame({"idio_vol": [0.02, float("nan"), 0.03]})
    rows = _audit_one("positions", "idio_vol", frame)
    assert rows["read"] is True
    assert rows["nans"] == 1
    assert audit.verdict(rows) == "NaN"


def test_a_value_that_is_not_a_number_at_all_is_a_finding(
    tmp_path: pathlib.Path,
) -> None:
    frame = pd.DataFrame({"weight": [0.1, "n/a", 0.2]})
    rows = _audit_one("positions", "weight", frame)
    assert rows["nans"] == 1
    assert audit.verdict(rows) == "NaN"


def test_a_clean_column_is_clean_and_a_missing_table_is_not() -> None:
    frame = pd.DataFrame({"gross": [1.0, 0.99]})
    assert audit.verdict(_audit_one("proposals", "gross", frame)) == "clean"
    # An empty table is no rows to scan, which the audit reports as not read: a
    # report of nothing is not a pass, and `verdict` says which it is.
    empty = pd.DataFrame()
    assert audit._local_rows("proposals", "gross", reader=lambda name: empty) is None
    row = {
        "table": "proposals",
        "column": "gross",
        "read": False,
        "n": None,
        "nans": None,
        "nulls": None,
        "not_number": None,
    }
    assert audit.verdict(row) == "not read"


def test_the_report_says_what_was_not_read(tmp_path: pathlib.Path) -> None:
    rows = [
        {
            "table": "positions",
            "column": "idio_vol",
            "read": True,
            "n": 3,
            "nans": 0,
            "nulls": 0,
            "not_number": 0,
        },
        {
            "table": "fills",
            "column": "fill_price",
            "read": False,
            "n": None,
            "nans": None,
            "nulls": None,
            "not_number": None,
        },
    ]
    text = audit.report(rows, source="a test")
    assert "1 clean, 0 with a NaN or a null, 1 not read" in text
    assert "| `fills` | `fill_price` | — | — | — | not read |" in text


def test_main_refuses_to_call_an_unreadable_store_a_pass(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from live import store

    monkeypatch.setattr(store, "select", _empty)
    monkeypatch.setattr(
        store, "get_connection", lambda: pytest.fail("this run has no database")
    )
    assert audit.main(["--local"]) == 2


def _empty(table: str) -> pd.DataFrame:
    return pd.DataFrame()


def _audit_one(table: str, column: str, frame: pd.DataFrame) -> dict[str, object]:
    """One column's counts, through the same reader the audit uses."""
    counts = audit._local_rows(table, column, reader=lambda name: frame)
    assert counts is not None
    not_number = int(counts.get("not_number") or 0)
    return {
        "table": table,
        "column": column,
        "read": True,
        "n": int(counts["n"]),
        "nans": int(counts["nans"]) + not_number,
        "nulls": int(counts["nulls"]),
        "not_number": not_number,
    }
