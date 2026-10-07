"""The schema preflight, and the message a failed evening sends.

Two defects from 2026-10-06, one cause each.

The first is the crash: `efb.reconciliation.unexplained_adjustment` was declared in
`live/supabase_schema.sql`, never applied to the live database, and the evening run
found out at `store_reconciliation` - after 192 orders had gone out. `live.preflight`
compares every declared column against the live catalogue and refuses the run before
the seed, the gate, the sizing and any order, so a missed migration costs one skipped
evening instead of a night's record.

The second is the message: the failure path passed no order count, so the email read
`EFB ERROR 2026-10-06 | none proposed | UndefinedColumn` and "Orders: none. The run
failed before sizing, so no book was priced" over an evening whose 192 orders were at
the broker. `run_live_daily.failed_run` reads them from `efb.orders` - the store's own
leg rows, not the run's in-memory summary, because the summary is exactly what is in
doubt when the run has just raised - and both the subject and the body report them.

Third, the same class of defect in what the evening reads: `run_morning`'s
not-executed path returned four keys while the caller read thirteen. Both paths now
return one shape, with `executed` as the marker.

Every test here drives the run's own function rather than `notify` or the summary
alone, which is the distinction that let the original wording ship: the composition
was covered, the call site was not.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pandas as pd
import pytest

from live import morning_job, notify, preflight, snapshot
from scripts import run_live_daily

ROOT = pathlib.Path(__file__).resolve().parents[1]
DDL = ROOT / "live" / "supabase_schema.sql"

# Every key `run_live_daily` reads off the summary `run_morning` returns.
CALLER_KEYS = (
    "orders",
    "intended_notional",
    "sent_notional",
    "no_asset",
    "renamed",
    "skipped_legs",
    "skipped_borrow",
    "deferred_reversals",
    "complete",
    "incomplete_legs",
    "establishment",
    "brake_limit",
    "cost_label",
)


# --- the preflight ---------------------------------------------------------


def test_the_expected_columns_come_from_the_repo_own_ddl() -> None:
    """One source of truth: the declaration the migration is written in."""
    declared = preflight.declared_columns(DDL)
    assert len(declared) == 21
    assert "unexplained_adjustment" in declared["reconciliation"]
    assert "position_intent" in declared["fills"]
    # The composite keys and the foreign references are not columns.
    assert not [name for name in declared["orders"] if name.startswith(("(", ")"))]
    assert {"trade_date", "ticker", "broker_order_id"} <= declared["orders"]
    # A column declared only by `alter table ... add column` is included: `kind` is
    # not in the create block for `positions`.
    assert "kind" in declared["positions"]


def test_the_declared_set_matches_itself_and_reports_a_dropped_column() -> None:
    """The regression: the night this guard exists for had one column missing."""
    declared = preflight.declared_columns(DDL)
    live = {table: set(columns) for table, columns in declared.items()}
    assert preflight.missing_columns(declared, live) == {}
    live["reconciliation"].discard("unexplained_adjustment")
    assert preflight.missing_columns(declared, live) == {
        "reconciliation": ["unexplained_adjustment"]
    }


def test_a_missing_column_is_named_and_refuses_the_run() -> None:
    declared = {"reconciliation": {"trade_date", "unexplained_adjustment"}}
    live = {"reconciliation": {"trade_date"}}
    assert preflight.missing_columns(declared, live) == {
        "reconciliation": ["unexplained_adjustment"]
    }
    with pytest.raises(preflight.SchemaOutOfDate) as raised:
        preflight.check(declared, live)
    message = str(raised.value)
    assert "reconciliation.unexplained_adjustment" in message
    assert "after the orders were sent" in message


def test_a_complete_schema_checks_clean() -> None:
    preflight.check({"orders": {"ticker"}}, {"orders": {"ticker", "extra"}})


def test_a_table_the_database_does_not_have_is_not_a_verdict() -> None:
    """A store with no schema is refused by the store's own checks, not here.

    The distinction matters: a local fallback, a test double and a brand-new
    database all answer "no such table", and none of them is evidence that a column
    was never migrated. A table that is there and missing a column is, and that is
    what this guard reports.
    """
    declared = {"efb_new": {"a", "b"}, "orders": {"ticker", "broker_order_id"}}
    live = {"orders": {"ticker", "broker_order_id"}}
    assert preflight.missing_columns(declared, live) == {}
    live["orders"].discard("broker_order_id")
    assert preflight.missing_columns(declared, live) == {"orders": ["broker_order_id"]}


def test_the_catalog_read_is_one_select_of_the_stores_own_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live side is read from the catalogue, not from a list in the code."""
    from live import store

    seen: list[str] = []

    class _Cursor:
        def __enter__(self) -> _Cursor:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def execute(self, sql: str) -> None:
            seen.append(sql)

        def fetchall(self) -> list[tuple[str, str]]:
            return [("orders", "ticker"), ("orders", "broker_order_id")]

    class _Connection:
        def cursor(self) -> _Cursor:
            return _Cursor()

    monkeypatch.setattr(store, "get_connection", lambda: _Connection())
    monkeypatch.setattr(store, "_schema", lambda: "efb")
    frame = store.select_catalog()
    assert list(frame.columns) == ["table_name", "column_name"]
    assert len(frame) == 2
    assert "information_schema.columns" in seen[0]
    assert "'efb'" in seen[0]


def test_a_local_store_has_no_catalog_and_nothing_to_compare() -> None:
    """The local fallback is not a database, and the preflight knows it."""
    from live import store

    assert list(store.select_catalog().columns) == ["table_name", "column_name"]


def test_the_run_checks_the_schema_before_it_does_anything_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Driven through `main`, because *where* the check sits is the whole point.

    A preflight that ran after the orders would be the defect it exists to prevent,
    so this asserts the refusal happens before the store mode is read, the seed is
    fetched and the book is priced, and that the run reports it as any other failure.
    """
    from live import staleness

    order: list[str] = []

    def _refuse(*args: Any, **kwargs: Any) -> None:
        order.append("preflight")
        raise preflight.SchemaOutOfDate(
            "the live database is missing 1 declared column(s): "
            "reconciliation.unexplained_adjustment"
        )

    def _later(step: str):
        def _called(*args: Any, **kwargs: Any) -> Any:
            order.append(step)
            raise AssertionError(f"the run reached {step} after a refused preflight")

        return _called

    monkeypatch.setattr(staleness, "is_session", lambda day: True)
    monkeypatch.setattr(staleness, "in_cron_window", lambda stamp: False)
    monkeypatch.setattr(run_live_daily, "resolve_force_hour", lambda value: True)
    monkeypatch.setattr(run_live_daily, "already_ran", lambda *a, **k: False)
    monkeypatch.setattr(preflight, "check", _refuse)
    # The next step after the preflight: the page's own configuration, still before
    # the seed and long before a submission.
    monkeypatch.setattr(snapshot, "check_snapshot_config", _later("snapshot config"))

    finished: dict[str, Any] = {}

    def _finish(**kwargs: Any) -> int:
        finished.update(kwargs)
        return 1

    monkeypatch.setattr(run_live_daily, "finish_run", _finish)
    assert run_live_daily.main() == 1
    assert order == ["preflight"]
    assert finished["status"] == "error"
    assert finished["error_type"] == "SchemaOutOfDate"
    assert "unexplained_adjustment" in finished["detail"]


# --- the failure message ---------------------------------------------------


def test_sent_orders_are_read_from_the_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legs with a broker id were sent; legs without one were not."""
    from live import store

    frame = pd.DataFrame(
        {
            "trade_date": ["2026-10-06"] * 4,
            "ticker": ["AAA", "BBB", "CCC", "DDD"],
            "intended_notional": [100.0, -50.0, 20.0, -30.0],
            "broker_order_id": ["id-1", "id-2", "", ""],
        }
    )
    monkeypatch.setattr(store, "select", lambda table: frame)
    assert run_live_daily.sent_orders("2026-10-06") == (2, 150.0, 200.0)


def test_sent_orders_ignores_another_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Yesterday's legs are not tonight's."""
    from live import store

    frame = pd.DataFrame(
        {
            "trade_date": ["2026-10-05"],
            "ticker": ["AAA"],
            "intended_notional": [100.0],
            "broker_order_id": ["id-1"],
        }
    )
    monkeypatch.setattr(store, "select", lambda table: frame)
    assert run_live_daily.sent_orders("2026-10-06") == (0, 0.0, 0.0)


def test_sent_orders_is_zero_when_the_store_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed read is "none sent", not a second failure on a failing run."""
    from live import store

    def _boom(table: str) -> Any:
        raise RuntimeError("the store is unreachable")

    monkeypatch.setattr(store, "select", _boom)
    assert run_live_daily.sent_orders("2026-10-06") == (0, 0.0, 0.0)


def test_a_failed_run_that_sent_orders_reports_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run's own failure function, with the store's rows behind it."""
    from live import store

    frame = pd.DataFrame(
        {
            "trade_date": ["2026-10-06"] * 2,
            "ticker": ["AAA", "BBB"],
            "intended_notional": [355_251.19, 3_173.13],
            "broker_order_id": ["id-1", ""],
        }
    )
    monkeypatch.setattr(store, "select", lambda table: frame)
    captured: dict[str, Any] = {}

    def _finish(**kwargs: Any) -> int:
        captured.update(kwargs)
        return 1

    monkeypatch.setattr(run_live_daily, "finish_run", _finish)
    code = run_live_daily.failed_run(
        RuntimeError("pricing failed after the orders"),
        run_date="2026-10-06",
        dry_run=False,
    )

    assert code == 1
    assert captured["status"] == "error"
    assert captured["orders"] == 1
    assert captured["gross"] == pytest.approx(358_424.32)
    assert captured["sent_notional"] == pytest.approx(355_251.19)
    assert "1 order(s) already sent" in captured["detail"]
    message = notify.compose(
        status="error",
        target_close="2026-10-06",
        dry_run=False,
        orders=captured["orders"],
        gross=captured["gross"],
        sent_notional=captured["sent_notional"],
        detail=captured["detail"],
        error_type=captured["error_type"],
    )
    assert "1 orders sent" in message
    assert "$355,251 sent of $358,424 sized" in message
    assert "failed before sizing" not in message


def test_a_failed_run_that_sent_nothing_keeps_the_old_wording(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wording exists for the run it was written for, and stays for it."""
    from live import store

    monkeypatch.setattr(store, "select", lambda table: pd.DataFrame())
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        run_live_daily, "finish_run", lambda **kwargs: captured.update(kwargs) or 1
    )
    run_live_daily.failed_run(
        KeyError("something before the book"), run_date="2026-10-06", dry_run=False
    )
    assert captured["orders"] is None
    message = notify.compose(
        status="error",
        target_close="2026-10-06",
        dry_run=False,
        detail=captured["detail"],
        error_type=captured["error_type"],
    )
    assert "Orders: none. The run failed before sizing" in message
    assert "none proposed" in notify.subject_text(
        status="error", target_close="2026-10-06", dry_run=False, error_type="KeyError"
    )


def test_the_subject_counts_the_orders_a_failed_run_sent() -> None:
    """`EFB ERROR 2026-10-06 | 192 sent | UndefinedColumn`."""
    subject = notify.subject_text(
        status="error",
        target_close="2026-10-06",
        dry_run=False,
        orders=192,
        error_type="UndefinedColumn",
    )
    assert subject == "EFB ERROR 2026-10-06 | 192 sent | UndefinedColumn"


# --- the summary the evening reads -----------------------------------------


def test_both_summary_paths_return_the_same_keys() -> None:
    """`executed` says which path it was; nothing else may differ."""
    not_executed = morning_job.not_executed_summary("2026-10-06", reason="reject")
    assert not_executed["executed"] is False
    for key in CALLER_KEYS:
        assert key in not_executed, key
    assert not_executed["sent_notional"] == 0.0
    assert not_executed["no_asset"] == []
    assert not_executed["renamed"] == {}
    assert not_executed["complete"] is True


def test_the_executed_summary_carries_the_keys_the_caller_reads() -> None:
    """The three that were missing, computed from the run's own leg records."""
    records = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC"],
            "intended_notional": [1_000.0, 2_000.0, 50.0],
            "filled_notional": [0.0, 0.0, 0.0],
            "status": ["PASSED", "PASSED", "SKIPPED"],
            "reason_code": ["", "", "BELOW_MIN_NOTIONAL"],
            "client_order_id": ["a", "b", ""],
            "position_intent": ["buy_to_open", "buy_to_open", "buy_to_open"],
            "broker_order_id": ["id-1", "id-2", ""],
            "broker_symbol": ["", "SKYD", ""],
        }
    )
    assert morning_job.sent_notional(records) == pytest.approx(3_000.0)
    assert morning_job.renamed_symbols(records) == {"BBB": "SKYD"}
    no_asset = records.copy()
    no_asset.loc[2, "reason_code"] = "SYMBOL_NOT_FOUND"
    rows = morning_job.no_asset_rows(no_asset)
    assert [row["ticker"] for row in rows] == ["CCC"]
    assert rows[0]["reason_code"] == "SYMBOL_NOT_FOUND"
    # The size travels with the name, so the line is checkable against the leg.
    assert rows[0]["intended_notional"] == pytest.approx(50.0)
