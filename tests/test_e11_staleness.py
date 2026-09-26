"""Sprint E11, Part 3: staleness fails the run, counted in NYSE sessions.

The gate is measured on synthetic artifacts under a temporary root, and driven
end to end through the cron script, so "no proposal row and no order is
written" is asserted on the store rather than on the code path. The dashboard
tests render the real page with the real store and assert on the elements the
owner would see.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from live import appendix, evening_job, extend, morning_job, staleness, store
from scripts import run_live_daily

ROOT = Path(__file__).resolve().parents[1]
SESSION = "2026-09-22"
PRIOR = "2026-09-21"
FRIDAY = "2026-09-18"


def _fail_on_call(message: str):
    def _raise(*args, **kwargs):
        raise AssertionError(message)

    return _raise


def _index_frame(date: str) -> pd.DataFrame:
    index = pd.MultiIndex.from_product(
        [[pd.Timestamp(date)], ["AAA", "BBB"]], names=["date", "ticker"]
    )
    return pd.DataFrame({"close": [10.0, 20.0]}, index=index)


def _write_root(root: Path, dates: dict[str, str]) -> Path:
    """Write all nine artifacts, each dated as `dates` says.

    `dates` carries every input's content date, plus `shares_fetch` and
    `sectors_fetch` for the two gated on the fetch rather than the content.
    """
    for relative in ("raw", "processed", "models/XS-v1", "raw/spy_holdings"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    (root / "raw" / "wikipedia_constituents").mkdir(parents=True, exist_ok=True)
    _index_frame(dates["prices"]).to_parquet(root / "raw" / "prices.parquet")
    _index_frame(dates["factor_cov"]).to_parquet(root / "processed" / "returns.parquet")
    pd.DataFrame(
        {"date": [dates["descriptors"]], "ticker": ["AAA"], "value_z": [0.0]}
    ).to_parquet(root / "models" / "XS-v1" / "descriptors.parquet")
    pd.DataFrame(
        {"date": [dates["factor_returns"]], "factor": ["MKT"], "f": [0.0]}
    ).to_parquet(root / "models" / "XS-v1" / "factor_returns.parquet")
    pd.DataFrame(
        {
            "date": [dates["specific_returns"]],
            "ticker": ["AAA"],
            "specific_return": [0.0],
        }
    ).to_parquet(root / "models" / "XS-v1" / "specific_returns.parquet")
    pd.DataFrame(
        {"date": [dates["specific_var"]], "ticker": ["AAA"], "specific_var": [0.0]}
    ).to_parquet(root / "models" / "XS-v1" / "specific_var.parquet")
    # one success and one empty fetch: the empty one carries no date and must
    # not date the input
    fetched_at = f"{dates['shares_fetch']}T14:46:36"
    pd.DataFrame(
        {
            "ticker": ["AAA", "ABK"],
            "date": [dates["shares"], pd.NaT],
            "shares": [1.0, None],
            "source": ["yfinance_get_shares_full", "yfinance_get_shares_full"],
            "fetched_at": [fetched_at, fetched_at],
            "status": ["ok", "empty"],
        }
    ).to_parquet(root / "raw" / "shares_history.parquet")
    pd.DataFrame(
        {
            "ticker": ["AAA"],
            "gics_sector": ["Information Technology"],
            "gics_sub_industry": ["Semiconductors"],
            "source": ["wikipedia"],
            "as_of": [dates["sectors"]],
        }
    ).to_parquet(root / "processed" / "sectors.parquet")
    pd.DataFrame(
        {"ticker": ["AAA"], "weight": [1.0], "as_of": [dates["universe"]]}
    ).to_parquet(
        root / "raw" / "spy_holdings" / f"spy_holdings_{dates['universe']}.parquet"
    )
    pd.DataFrame(
        {"symbol": ["AAA"], "gics_sector": ["Information Technology"]}
    ).to_parquet(
        root
        / "raw"
        / "wikipedia_constituents"
        / f"wikipedia_constituents_{dates['sectors_fetch']}.parquet"
    )
    return root


def _all_at(session: str, fetch: str | None = None) -> dict[str, str]:
    """Every input dated at `session`, both fetch dates included."""
    dates = {name: session for name in staleness.INPUTS}
    dates["shares_fetch"] = fetch or session
    dates["sectors_fetch"] = fetch or session
    return dates


class _NoCorporateActions:
    """The stub outcome of the corporate-actions step: no split, no flags."""

    splits: list = []
    sessions: list = []
    ratios: dict = {}
    flags: list = []
    unchecked = 0


def _patch_no_work(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace every step of the run that would fetch, size or hash."""
    from live import corporate_actions

    for name in ("hydrate", "persist_new_sessions", "appendix_manifest"):
        monkeypatch.setattr(appendix, name, lambda *args, **kwargs: {})
    # The first-run guard has its own tests; here the store is already open.
    monkeypatch.setattr(appendix, "open_store", lambda *args, **kwargs: False)
    # The run tree is the repository's own data root: these tests stub every read
    # and write, and pin whichever root they need on the module itself.
    from live import runroot

    monkeypatch.setattr(runroot, "prepare", lambda *args, **kwargs: staleness.DATA_ROOT)
    # `adopt` moves every live module's DATA_ROOT for the rest of the process, so
    # each one is pinned through monkeypatch here and put back after the test.
    from live import reconcile, sanity

    for module in (
        appendix,
        evening_job,
        extend,
        morning_job,
        reconcile,
        sanity,
        staleness,
    ):
        monkeypatch.setattr(module, "DATA_ROOT", module.DATA_ROOT)
    for name in (
        "extend_archives",
        "extend_prices",
        "extend_shares",
        "extend_returns",
        "extend_model",
    ):
        monkeypatch.setattr(extend, name, lambda *a, **k: {})
    # No evidence stub: the run no longer calls `efb.evidence.snapshot`, which is
    # a local sprint-close step and not a cron one.
    # The corporate-actions rule has its own tests. It is stubbed here because it
    # reads and writes the price artifact: reached for real it would run against
    # whichever tree the run was pointed at, which is not what these tests are
    # about, and on the synthetic root its columns are thinner than it expects.
    monkeypatch.setattr(
        corporate_actions, "apply_to_artifact", lambda *a, **k: _NoCorporateActions()
    )


def test_a_monday_run_on_fridays_close_passes(tmp_path: Path) -> None:
    """Sessions, not calendar days: Friday's close is fresh on Monday."""
    root = _write_root(tmp_path / "data", _all_at(FRIDAY))
    before_the_open = pd.Timestamp("2026-09-21T11:00:00Z")  # Monday 07:00 ET
    result = staleness.check(root=root, now=before_the_open)
    assert result["target_close"] == FRIDAY
    assert result["status"] == "ok"
    assert result["failures"] == []
    # The negative control: the same nine artifacts, read after Monday's close,
    # are one session stale. A calendar-day rule would have called them fresh.
    after_the_close = pd.Timestamp("2026-09-21T21:00:00Z")  # Monday 17:00 ET
    late = staleness.check(root=root, now=after_the_close)
    assert late["target_close"] == PRIOR
    assert late["status"] == "stale_stopped"
    assert late["worst_input"] == "prices"
    assert late["worst_sessions_behind"] == 1


def test_a_holiday_is_handled(tmp_path: Path) -> None:
    """Labor Day is not a session, so the target close stays on Friday."""
    labor_day = "2026-09-07"
    week = [str(day.date()) for day in staleness.sessions("2026-09-04", "2026-09-08")]
    assert labor_day not in week
    assert staleness.sessions_behind("2026-09-04", "2026-09-08") == 1
    holiday_evening = pd.Timestamp("2026-09-07T22:30:00Z")
    assert str(staleness.target_close(holiday_evening).date()) == "2026-09-04"
    root = _write_root(tmp_path / "data", _all_at("2026-09-04"))
    assert staleness.check(root=root, now=holiday_evening)["status"] == "ok"
    # and the same artifacts after the next session's close are one behind,
    # where calendar days would say four
    tuesday = pd.Timestamp("2026-09-08T22:30:00Z")
    late = staleness.check(root=root, now=tuesday)
    assert late["status"] == "stale_stopped"
    assert late["worst_sessions_behind"] == 1


def test_the_target_close_is_the_last_session_that_has_closed() -> None:
    """A run before the open prices yesterday's close, never today's."""
    early = pd.Timestamp("2026-09-22T11:00:00Z")
    assert str(staleness.target_close(early).date()) == PRIOR
    late = pd.Timestamp("2026-09-22T22:30:00Z")  # 18:30 ET, the cron's slot
    assert str(staleness.target_close(late).date()) == SESSION


def test_the_row_carries_every_content_date_and_both_fetch_dates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dates = _all_at(SESSION)
    dates["sectors"] = "2026-09-11"  # the research snapshot's real age
    root = _write_root(tmp_path / "data", dates)
    result = staleness.check(root=root, now=pd.Timestamp("2026-09-22T22:30:00Z"))
    assert result["status"] == "ok"
    # shares and sectors are gated on the fetch and pass on it, while their
    # content dates are reported beside it
    for name in ("shares", "sectors"):
        entry = result["inputs"][name]
        assert entry["gated_by"] == "fetch"
        assert entry["sessions_behind"] == 0
    assert result["inputs"]["shares"]["content_sessions_behind"] == 0
    assert result["inputs"]["sectors"]["content"] == "2026-09-11"
    assert result["inputs"]["sectors"]["content_sessions_behind"] == 7
    for name in staleness.INPUTS:
        assert result["inputs"][name]["content"] is not None
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    staleness.write_run_status(result, run_date="2026-09-22", dry_run=True)
    stored = store.select("run_status")
    assert len(stored) == 1
    row = stored.iloc[0]
    assert row["status"] == "ok"
    assert row["target_close"] == SESSION
    assert row["n_inputs"] == len(staleness.INPUTS)
    assert row["max_input_staleness_days"] == 11
    # the sectors snapshot's content age is reported in the row even though no
    # input failed: the number is stored, the gate did not read it
    assert '"sectors"' in row["inputs"]
    assert row["failures"] == "[]"


def test_a_stale_fetch_fails_even_when_the_content_is_fresh(tmp_path: Path) -> None:
    """What must not age is the check: an old fetch stops the run."""
    root = _write_root(tmp_path / "data", _all_at(SESSION, fetch=PRIOR))
    result = staleness.check(root=root, now=pd.Timestamp("2026-09-22T22:30:00Z"))
    assert result["status"] == "stale_stopped"
    assert result["worst_input"] in ("shares", "sectors")
    assert result["worst_sessions_behind"] == 1
    assert result["inputs"]["shares"]["content_sessions_behind"] == 0
    assert result["inputs"]["shares"]["fetch_sessions_behind"] == 1


def test_an_undated_input_is_stale_and_outranks_a_count(tmp_path: Path) -> None:
    """An input with no date cannot be fresh, and it is named as the worst."""
    dates = _all_at(SESSION)
    dates["prices"] = PRIOR  # a count of one, which must not outrank it
    root = _write_root(tmp_path / "data", dates)
    (root / "models" / "XS-v1" / "specific_var.parquet").unlink()
    result = staleness.check(root=root, now=pd.Timestamp("2026-09-22T22:30:00Z"))
    assert result["status"] == "stale_stopped"
    assert result["inputs"]["specific_var"]["content"] is None
    assert result["worst_input"] == "specific_var"
    assert result["worst_sessions_behind"] is None
    described = staleness.describe_failures(result["failures"])
    assert "specific_var has no date at all" in described
    assert "prices is 1 session behind" in described


def test_a_stale_input_stops_the_run_with_no_proposal_and_no_orders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The promise, on the store: a stale input writes neither a book nor an order."""
    dates = _all_at(SESSION)
    dates["prices"] = PRIOR  # one session behind the target close
    root = _write_root(tmp_path / "data", dates)
    monkeypatch.setattr(staleness, "DATA_ROOT", root)
    monkeypatch.setattr(
        staleness, "target_close", lambda now=None: pd.Timestamp(SESSION)
    )
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    _patch_no_work(monkeypatch)
    monkeypatch.setattr(
        evening_job,
        "build_proposal",
        _fail_on_call("sizing ran: the gate must stop the run before it"),
    )
    monkeypatch.setattr(
        morning_job,
        "run_morning",
        _fail_on_call("execution ran: the gate must stop the run before it"),
    )
    monkeypatch.setattr(run_live_daily, "already_ran", lambda job, day: False)

    assert run_live_daily.main() == 1

    assert store.select("proposals").empty
    assert store.select("orders").empty
    status = store.select("run_status")
    assert len(status) == 1
    row = status.iloc[0]
    assert row["status"] == "stale_stopped"
    assert row["target_close"] == SESSION
    assert row["worst_input"] == "prices"
    assert row["worst_sessions_behind"] == 1
    assert '"input": "prices"' in row["failures"]
    # the stored row says what the owner will see, in the page's own words
    state = staleness.run_state(dict(row), now=pd.Timestamp("2026-09-22T22:30:00Z"))
    assert not state["clean"]
    assert "prices is 1 session behind" in state["message"]
    cron = store.select("cron_runs")
    assert cron.iloc[0]["status"] == "stale_stopped"
    assert cron.iloc[0]["detail"] == "prices is 1 session behind"


def test_a_fresh_run_reaches_sizing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control for the stop: a fresh gate lets the run through."""
    root = _write_root(tmp_path / "data", _all_at(SESSION))
    monkeypatch.setattr(staleness, "DATA_ROOT", root)
    monkeypatch.setattr(
        staleness, "target_close", lambda now=None: pd.Timestamp(SESSION)
    )
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    _patch_no_work(monkeypatch)
    reached: list[str] = []

    def _record_then_fail(*args, **kwargs):
        reached.append("sizing")
        raise AssertionError("reached sizing")

    monkeypatch.setattr(evening_job, "build_proposal", _record_then_fail)
    monkeypatch.setattr(run_live_daily, "already_ran", lambda job, day: False)

    assert run_live_daily.main() == 1

    assert reached == ["sizing"]
    assert store.select("proposals").empty
    # the gate passed and wrote a clean row; the later failure then replaces it
    # with the error, which is what the dashboard must show
    status = store.select("run_status")
    assert len(status) == 1
    assert status.iloc[0]["status"] == "error"
    assert "reached sizing" in status.iloc[0]["detail"]
    assert "reached sizing" in store.select("cron_runs").iloc[0]["detail"]


def _dashboard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rows: list[dict]):
    """Render the live dashboard against a store holding exactly `rows`."""
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    if rows:
        store.upsert("run_status", rows)
    st.cache_data.clear()
    page = AppTest.from_file(
        str(ROOT / "live" / "dashboard_app.py"), default_timeout=120
    )
    page.run()
    assert not page.exception
    return page


def _rows(status: str, target_close: str, **extra) -> list[dict]:
    row = {
        "job": "live_daily",
        "run_date": target_close,
        "target_close": target_close,
        "status": status,
        "checked_at": f"{target_close}T22:30:00+00:00",
        "max_input_staleness_days": 0,
        "worst_input": None,
        "worst_sessions_behind": 0,
        "n_inputs": 9,
        "inputs": "{}",
        "failures": "[]",
        "detail": "",
        "notify_status": "sent",
        "notify_failed": False,
        "n_orders": None,
        "gross_notional": None,
        "dry_run": True,
    }
    row.update(extra)
    return [row]


def test_the_dashboard_shows_the_failure_state_for_a_stale_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = staleness.target_close().date().isoformat()
    failures = (
        '[{"content": "2026-09-21", "gated_by": "content", "input": "prices", '
        '"sessions_behind": 1}]'
    )
    page = _dashboard(
        tmp_path,
        monkeypatch,
        _rows("stale_stopped", expected, worst_input="prices", failures=failures),
    )
    messages = " ".join(element.value for element in page.error)
    assert "STALE STOP" in messages
    assert "prices is 1 session behind" in messages
    assert "not current" in messages


def test_the_dashboard_shows_the_failure_state_for_a_missing_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = _dashboard(tmp_path, monkeypatch, [])
    messages = " ".join(element.value for element in page.error)
    assert "Run status: no run recorded at all" in messages


def test_the_dashboard_shows_the_failure_state_for_an_older_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run for a session that is not the latest one is not a current book."""
    expected = staleness.target_close().date().isoformat()
    older = str(pd.Timestamp(expected) - pd.Timedelta(days=7))
    page = _dashboard(tmp_path, monkeypatch, _rows("ok", older))
    messages = " ".join(element.value for element in page.error)
    assert "no run for the most recent close" in messages
    assert expected in messages


def test_the_dashboard_is_clean_when_the_latest_run_is_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control: a clean run shows no failure at all."""
    expected = staleness.target_close().date().isoformat()
    page = _dashboard(tmp_path, monkeypatch, _rows("ok", expected))
    assert not page.error
    assert "Run status: clean" in " ".join(element.value for element in page.success)


def test_the_dashboard_reads_no_research_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The page judges the run from the stored row and the calendar alone.

    `live.staleness` can read research parquets, but only in `check` and
    `input_dates`, which the page never calls: the gate runs on the cron, and
    the page must keep touching no file over 5 MB.
    """

    def _boom(*args, **kwargs):
        raise AssertionError("the page read a research artifact")

    monkeypatch.setattr(staleness, "input_dates", _boom)
    monkeypatch.setattr(staleness, "check", _boom)
    expected = staleness.target_close().date().isoformat()
    page = _dashboard(tmp_path, monkeypatch, _rows("ok", expected))
    assert not page.exception
    assert not page.error


def test_a_gate_close_is_an_evening_of_that_close() -> None:
    """The owner's rule in full: one session, and fetched on its own evening."""
    row = {
        "target_close": "2026-09-25",
        "status": "ok",
        "catch_up": False,
        "catch_up_sessions": ["2026-09-25"],
    }
    on_time = staleness.gate_close({**row, "started_at": "2026-09-25T22:30:00+00:00"})
    assert on_time["counts"] is True
    assert "2026-09-25" in on_time["reason"] and "close" in on_time["reason"]
    # The grace is inside the window.
    assert (
        staleness.gate_close({**row, "started_at": "2026-09-26T01:00:00+00:00"})[
            "counts"
        ]
        is True
    )
    # A run delayed into the next morning appended exactly one session and is
    # still not the evening of this close.
    late = staleness.gate_close({**row, "started_at": "2026-09-28T13:00:00+00:00"})
    assert late["counts"] is False
    assert "own evening" in late["reason"]
    # Nor is a run before the close.
    early = staleness.gate_close({**row, "started_at": "2026-09-25T19:00:00+00:00"})
    assert early["counts"] is False and "before the" in early["reason"]
    # A catch-up is never a gate close, and neither is a failed run.
    assert (
        staleness.gate_close(
            {
                **row,
                "catch_up": True,
                "catch_up_sessions": ["2026-09-24", "2026-09-25"],
                "started_at": "2026-09-25T22:30:00+00:00",
            }
        )["counts"]
        is False
    )
    assert (
        staleness.gate_close(
            {
                **row,
                "status": "stale_stopped",
                "started_at": "2026-09-25T22:30:00+00:00",
            }
        )["counts"]
        is False
    )
    # And a run that records no start time cannot show its own evening.
    no_start = staleness.gate_close(row)
    assert no_start["counts"] is False and "no start time" in no_start["reason"]


def test_the_gate_window_is_the_closes_own_evening_not_the_next_runs_deadline() -> None:
    """Two different questions, two different instants, one source of the slot."""
    window = staleness.gate_window_end("2026-09-25")
    expectation = pd.Timestamp(staleness.expected_next_by("2026-09-25"))
    assert window == pd.Timestamp("2026-09-26T01:30:00+00:00")
    assert expectation == pd.Timestamp("2026-09-29T01:30:00+00:00")
    assert window < expectation
    # Friday's window ends on Saturday morning UTC, which is Friday evening in
    # New York: still the close's own evening.
    assert staleness.gate_window_end("2026-09-18") == pd.Timestamp(
        "2026-09-19T01:30:00+00:00"
    )


def test_the_run_records_when_it_started() -> None:
    result = {"target_close": "2026-09-25", "job": "evening", "status": "ok"}
    row = staleness.run_status_row(
        result, run_date="2026-09-25", started_at="2026-09-25T22:30:41+00:00"
    )
    assert row["started_at"] == "2026-09-25T22:30:41+00:00"
    assert row["gate_close"] is None if "gate_close" in row else True
    assert staleness.run_status_row(result, run_date="2026-09-25")["started_at"] is None
