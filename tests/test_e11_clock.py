"""Sprint E11: the continuous live clock, void, restart and registration.

Day 1 is not a date somebody types: registration refuses unless the date it is
given is the first live run and the first stored proposal, so the tests here drive
both the agreement and each way the records can disagree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from live import clock

# One set of records that agree on a day, used as the basis for the disagreements.
AGREED = {
    "run": ["2026-09-30", "2026-10-01"],
    "proposal": ["2026-09-30", "2026-10-01"],
    "filled": [],
}


def test_start_clock_records_day_1_and_the_end_date(tmp_path: Path) -> None:
    path = tmp_path / "clock.json"
    payload = clock.start_clock(
        "2026-09-30", trading_days=30, path=path, records=AGREED
    )
    assert payload["day_1"] == "2026-09-30"
    assert payload["trading_days"] == 30
    assert payload["started"] is True
    # 30 business days from 2026-09-30 inclusive lands on 2026-11-10
    assert payload["end_date"] == "2026-11-10"


def test_start_clock_records_the_open_ended_run_condition(tmp_path: Path) -> None:
    path = tmp_path / "clock.json"
    payload = clock.start_clock("2026-09-30", path=path, records=AGREED)
    assert payload["run_condition"] == "open_ended"
    assert payload["reporting_window_days"] == 30
    # the window end is a reporting slice, not the life of the loop
    assert payload["end_date"] == "2026-11-10"
    assert payload["day_1"] == "2026-09-30"


def test_registration_refuses_a_day_the_records_do_not_start_on(
    tmp_path: Path,
) -> None:
    """A day 1 that is not the first live run is refused, not recorded."""
    path = tmp_path / "clock.json"
    with pytest.raises(clock.RegistrationRefused, match="is not the first live run"):
        clock.start_clock("2026-10-01", path=path, records=AGREED)
    assert not path.exists(), "a refused registration still wrote a clock"


def test_registration_refuses_a_day_the_proposals_do_not_start_on(
    tmp_path: Path,
) -> None:
    """The run and the proposal have to agree: a proposal with no run behind it,
    or a run that stored no proposal, is not a first trading day."""
    records = {"run": ["2026-09-30"], "proposal": ["2026-10-01"], "filled": []}
    with pytest.raises(clock.RegistrationRefused, match="is not the first stored"):
        clock.start_clock("2026-09-30", path=tmp_path / "clock.json", records=records)


def test_registration_refuses_when_a_fill_precedes_the_day(
    tmp_path: Path,
) -> None:
    """Once the store keeps fills, the definition itself is checked."""
    records = {**AGREED, "filled": ["2026-09-29", "2026-09-30"]}
    with pytest.raises(clock.RegistrationRefused, match="whose orders filled"):
        clock.start_clock("2026-09-30", path=tmp_path / "clock.json", records=records)
    # the same date with a fill on it registers, so the check is not vacuous
    agreeing = {**AGREED, "filled": ["2026-09-30"]}
    payload = clock.start_clock(
        "2026-09-30", path=tmp_path / "clock.json", records=agreeing
    )
    assert payload["day_1"] == "2026-09-30"


def test_registration_refuses_before_any_live_run(tmp_path: Path) -> None:
    """Before the flip there is no day 1, which is the state the clock is in."""
    with pytest.raises(clock.RegistrationRefused, match="no live run is recorded"):
        clock.first_day({"run": [], "proposal": ["2026-09-30"], "filled": []})
    with pytest.raises(clock.RegistrationRefused, match="no stored proposal"):
        clock.first_day({"run": ["2026-09-30"], "proposal": [], "filled": []})


def test_only_a_live_run_counts_as_the_first_live_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dry-run evening is recorded and is not a live run.

    `run_status` carries both flags, so the set is read from them: the first date
    is the flip evening, and a dry-run evening that sent orders (there is no such
    evening, but the flag is what says so) is not it.
    """
    import pandas as pd

    from live import staleness, store

    frames = {
        staleness.TABLE: pd.DataFrame(
            {
                "target_close": ["2026-09-29", "2026-09-30"],
                "job": ["live_daily", "live_daily"],
                "dry_run": [True, False],
                "n_orders": [150, 151],
            }
        ),
        "proposals": pd.DataFrame({"trade_date": ["2026-09-30"]}),
        "orders": pd.DataFrame(
            {"trade_date": ["2026-09-30"], "filled_notional": [0.0]}
        ),
    }
    monkeypatch.setattr(
        store, "select", lambda table: frames.get(table, pd.DataFrame())
    )
    records = clock.records_from_store()
    assert records["run"] == ["2026-09-30"]
    assert records["proposal"] == ["2026-09-30"]
    assert records["filled"] == [], "an accepted order is not a fill"
    assert clock.first_day(records) == "2026-09-30"


def _framed_store(monkeypatch: pytest.MonkeyPatch, *, with_fills: bool) -> None:
    import pandas as pd

    from live import staleness, store

    frames = {
        staleness.TABLE: pd.DataFrame(
            {
                "target_close": ["2026-09-30"],
                "job": ["live_daily"],
                "dry_run": [False],
                "n_orders": [178],
            }
        ),
        "proposals": pd.DataFrame({"trade_date": ["2026-09-30"]}),
        "orders": pd.DataFrame(
            {
                "trade_date": ["2026-09-30"],
                "ticker": ["AAA"],
                "filled_notional": [0.0],
                "broker_order_id": ["b-1"],
            }
        ),
        "fills": pd.DataFrame(
            {
                "trade_date": ["2026-09-30"] if with_fills else [],
                "ticker": ["AAA"] if with_fills else [],
                "filled_notional": [1_000.0] if with_fills else [],
                "status": ["FILLED"] if with_fills else [],
            }
        ),
    }
    monkeypatch.setattr(
        store, "select", lambda table: frames.get(table, pd.DataFrame())
    )


def test_a_start_registers_on_a_close_with_fills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fills are read from `efb.fills`, so a reconciled close registers."""
    _framed_store(monkeypatch, with_fills=True)
    records = clock.records_from_store()
    assert records["filled"] == ["2026-09-30"]
    assert records["ordered"] == ["2026-09-30"]
    assert clock.first_day(records) == "2026-09-30"


def test_a_start_is_refused_on_a_close_with_orders_and_no_fills(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An order nobody has reconciled is not a session whose orders filled.

    `efb.orders.filled_notional` is 0 in every row the live table holds, so a reader
    of that column made this check pass on any close at all. The leg is in the store
    and the fill is not, which is exactly the state the check has to refuse.
    """
    _framed_store(monkeypatch, with_fills=False)
    records = clock.records_from_store()
    assert records["filled"] == []
    assert records["ordered"] == ["2026-09-30"]
    path = tmp_path / "clock.json"
    with pytest.raises(clock.RegistrationRefused, match="no fill for it"):
        clock.start_clock("2026-09-30", path=path, records=records)
    assert not path.exists(), "a refused registration still wrote a clock"


def test_a_rehearsal_proposal_is_not_a_live_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The proposal set is scoped by `run_status`, not read whole.

    The loop stores a proposal on a dry run at a close before the flip. Read
    unscoped, that rehearsal became the first proposal and no day-1 date could
    agree with it; scoped, the set starts on the first close the live series ran on.
    """
    import pandas as pd

    from live import staleness, store

    frames = {
        staleness.TABLE: pd.DataFrame(
            {
                "target_close": ["2026-09-25", "2026-09-30"],
                "job": ["live_daily", "live_daily"],
                "dry_run": [True, False],
                "n_orders": [150, 178],
            }
        ),
        "proposals": pd.DataFrame({"trade_date": ["2026-09-25", "2026-09-30"]}),
        "orders": pd.DataFrame({"trade_date": [], "broker_order_id": []}),
        "fills": pd.DataFrame({"trade_date": [], "status": []}),
    }
    monkeypatch.setattr(
        store, "select", lambda table: frames.get(table, pd.DataFrame())
    )
    records = clock.records_from_store()
    assert records["proposal"] == ["2026-09-30"]
    assert records["run"] == ["2026-09-30"]


def test_a_hold_day_proposal_is_a_live_close(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hold day sends no order and is still a live close, and its proposal counts.

    The `run` set requires an order, because a close that traded is what day 1 is;
    the scope the proposal is read through must not inherit that condition or the
    proposal set would skip every hold day between rebalances.
    """
    import pandas as pd

    from live import staleness, store

    frames = {
        staleness.TABLE: pd.DataFrame(
            {
                "target_close": ["2026-10-23", "2026-10-26", "2026-10-27"],
                "job": ["live_daily"] * 3,
                "dry_run": [False] * 3,
                "n_orders": [208, 13, 0],
            }
        ),
        "proposals": pd.DataFrame(
            {"trade_date": ["2026-10-23", "2026-10-26", "2026-10-27"]}
        ),
        "orders": pd.DataFrame({"trade_date": [], "broker_order_id": []}),
        "fills": pd.DataFrame({"trade_date": [], "status": []}),
    }
    monkeypatch.setattr(
        store, "select", lambda table: frames.get(table, pd.DataFrame())
    )
    records = clock.records_from_store()
    assert records["proposal"] == ["2026-10-23", "2026-10-26", "2026-10-27"]
    assert records["run"] == ["2026-10-23", "2026-10-26"]


def test_the_real_store_refuses_day_1_on_the_fills_it_does_not_hold() -> None:
    """Measured on the live store on 2026-10-28, read-only.

    Scoping the proposal set moved its first date from the 2026-09-25 rehearsal to
    2026-09-30 and `first_day()` still refuses, now on the fills: the store holds
    orders for the 2026-09-29 and 2026-09-30 closes and no fill row for either, so
    "day 1 is the first session whose orders filled" cannot be established from it.
    That is a reconciliation gap, not a reader bug, and the assertion says so.
    """
    from live import store

    if store.store_mode() != "supabase":  # pragma: no cover - local runs have no store
        pytest.skip("the live store is not configured")

    records = clock.records_from_store()
    assert records["proposal"][0] == "2026-09-30", records["proposal"][:3]
    assert records["run"][0] == "2026-09-30"
    with pytest.raises(clock.RegistrationRefused) as refused:
        clock.first_day(records)
    assert "not the first session whose orders filled" in str(refused.value)
    assert records["filled"][0] == "2026-10-01"


def test_records_from_an_unseeded_store_are_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty frame has no columns, and that is an empty record rather than a
    crash: it is the state before the first run."""
    import pandas as pd

    from live import store

    monkeypatch.setattr(store, "select", lambda table: pd.DataFrame())
    assert clock.records_from_store() == {
        "run": [],
        "proposal": [],
        "filled": [],
        "ordered": [],
    }


def test_run_condition_is_open_ended() -> None:
    condition = clock.run_condition()
    assert condition["run_condition"] == "open_ended"
    assert "reporting window" in condition["reason"]
    assert condition["reporting_window_days"] == 30


def test_void_start_records_the_reason_and_leaves_the_clock_stopped(
    tmp_path: Path,
) -> None:
    path = tmp_path / "clock.json"
    clock.start_clock("2026-09-30", path=path, records=AGREED)
    payload = clock.void_start("2026-09-30", "static days on a frozen close", path=path)
    assert payload["started"] is False
    assert payload["day_1"] is None
    assert len(payload["history"]) == 1
    entry = payload["history"][0]
    assert entry["status"] == "void"
    assert entry["day_1"] == "2026-09-30"
    assert entry["reason"] == "static days on a frozen close"


def test_restart_after_a_void_keeps_both_starts_on_the_record(tmp_path: Path) -> None:
    path = tmp_path / "clock.json"
    clock.start_clock("2026-09-30", path=path, records=AGREED)
    clock.void_start("2026-09-30", "static days", path=path)
    later = {
        "run": ["2026-10-01", "2026-10-02"],
        "proposal": ["2026-10-01"],
        "filled": [],
    }
    payload = clock.start_clock("2026-10-01", path=path, records=later)
    assert payload["started"] is True
    assert payload["day_1"] == "2026-10-01"
    assert [entry["status"] for entry in payload["history"]] == ["void"]
    assert payload["history"][0]["day_1"] == "2026-09-30"


def test_load_clock_fails_before_it_has_started(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no clock"):
        clock.load_clock(tmp_path / "clock.json")


def test_the_stored_clock_is_not_started() -> None:
    """The repository's own clock carries no day 1 until a session fills.

    Day 1 is the first session whose orders filled after the flip. The earlier
    start was voided and stays on the record, and every other start the file has
    ever held is on it too, so the history is what shows the clock was restarted
    rather than quietly edited.
    """
    payload = clock.load_clock()
    assert payload["started"] is False
    assert payload["day_1"] is None and payload["end_date"] is None
    assert payload["trading_days"] == 30
    history = payload["history"]
    assert history, "the voided start is not on the record"
    assert all(entry["status"] == "void" for entry in history)
