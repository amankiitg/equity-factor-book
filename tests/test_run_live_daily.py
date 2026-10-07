"""Sprint E11: the daily cron script's run bookkeeping.

The loop is idempotent through the cron_runs table, so the first-ever run
(empty table) must still record without raising, and a re-run for the same
date must replace the row rather than duplicate it.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from live import staleness, store
from scripts import run_live_daily

ROOT = Path(__file__).resolve().parents[1]


def test_the_days_traded_dollars_come_from_its_own_legs() -> None:
    """Turnover per name, absolute, from the legs the evening built.

    The page's trades-by-reason table sums this beside the held dollars, and the
    two are different questions about one reason: what the run keeps, and what it
    did about those names. Absolute because it is turnover - a name the run trimmed
    and a name it opened are both dollars moved, and netting them would report less
    trading than happened.
    """
    execution = pd.DataFrame(
        {
            "ticker": ["DG", "AAA", "DG"],
            "intended_notional": [512.42, -1_000.0, 12.0],
        }
    )
    traded = run_live_daily.traded_by_name(execution)
    assert traded == {"DG": pytest.approx(524.42), "AAA": pytest.approx(1_000.0)}

    book = pd.DataFrame({"ticker": ["DG", "BBB"], "weight": [0.01, -0.02]})
    rows = run_live_daily.with_traded(book, traded)
    assert rows is not None
    # A name with no leg tonight is a zero, not a blank: the run traded nothing in
    # it, which is a fact about the evening rather than a missing measurement.
    assert list(rows["traded_notional"]) == [
        pytest.approx(524.42),
        pytest.approx(0.0),
    ]
    # A run with no book in hand keeps having none.
    assert run_live_daily.with_traded(None, traded) is None


def test_the_writer_publishes_the_traded_column_only_when_it_was_measured() -> None:
    """The page reads one number per reason, and a book published without the
    column must not be given invented trading."""
    from live import snapshot

    book = pd.DataFrame(
        {
            "ticker": ["DG", "AAA"],
            "weight": [0.01, -0.02],
            "side": ["long", "short"],
            "reason": ["alpha moved", "the hedge moved"],
            "traded_notional": [524.42, 0.0],
        }
    )
    manifest = {"as_of": "2026-09-21", "nav": 1_000_000.0}
    published = snapshot.build(
        run={"target_close": "2026-09-21"}, manifest=manifest, book=book
    )
    by_ticker = {name["ticker"]: name for name in published["book"]["names"]}
    assert by_ticker["DG"]["traded_notional"] == pytest.approx(524.42)
    assert by_ticker["AAA"]["traded_notional"] == pytest.approx(0.0)

    older = snapshot.build(
        run={"target_close": "2026-09-21"},
        manifest=manifest,
        book=book.drop(columns=["traded_notional"]),
    )
    assert all("traded_notional" not in name for name in older["book"]["names"])


def test_record_run_handles_an_empty_cron_runs_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path)
    run_live_daily.record_run("live_daily", "2026-09-23", "ok")
    frame = store.select("cron_runs")
    assert len(frame) == 1
    assert frame.iloc[0]["run_date"] == "2026-09-23"
    assert frame.iloc[0]["job"] == "live_daily"
    assert frame.iloc[0]["status"] == "ok"


def test_a_failed_evening_publishes_the_days_traded_dollars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failure path's own call site, and the borrowed book it publishes.

    An evening that dies after its orders are sent has no manifest of its own, so
    `finish_run` publishes the last book the store holds. That frame is the store's
    `positions` rows, which carry no `traded_notional` column, so the page's
    trades-by-reason table read a column of zeroes for a day that traded: 2026-10-06
    sent $355,251.19 and showed none of it. The same definition is now applied to the
    borrowed book, from `efb.orders` for that close rather than from the container's
    own log, because the failure path is exactly where the file may be gone with the
    container that wrote it.

    A store that cannot be read is the control: the column stays off rather than
    being filled with zeroes the page would read as a measured day. The page reads a
    missing key as zero either way, so the only thing the guard costs is the claim
    that the number was measured.
    """
    from live import notify
    from live import snapshot as snapshot_module

    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    # The day's legs, as the submission wrote them before the failure: two legs in
    # one name, one in another, and one the minimum left unsent. The last one counts
    # as traded dollars - it is a leg of the day - which is the success path's own
    # definition of turnover.
    store.replace_by_date(
        "orders",
        "2026-10-06",
        [
            {"trade_date": "2026-10-06", "ticker": "DG", "intended_notional": 512.42},
            {"trade_date": "2026-10-06", "ticker": "DG", "intended_notional": 12.0},
            {"trade_date": "2026-10-06", "ticker": "AAA", "intended_notional": -1000.0},
            {"trade_date": "2026-10-06", "ticker": "ZZZ", "intended_notional": 40.0},
            {"trade_date": "2026-10-05", "ticker": "OLD", "intended_notional": 9.0},
        ],
    )
    day = run_live_daily.stored_legs("2026-10-06")
    assert day is not None and sorted(day["ticker"]) == [
        "AAA",
        "DG",
        "DG",
        "ZZZ",
    ], "the day's legs, and only that day's"

    borrowed = pd.DataFrame(
        {
            "ticker": ["DG", "BBB"],
            "weight": [0.01, -0.02],
            "side": ["long", "long"],
            "reason": ["alpha moved", "the hedge moved"],
        }
    )
    manifest = {"as_of": "2026-10-06", "n_kept": 2}
    monkeypatch.setattr(
        snapshot_module, "previous_proposal", lambda: (manifest, borrowed, None)
    )
    captured: dict = {}

    def fake_write_snapshot(**kwargs):
        captured.update(kwargs)
        captured["document"] = snapshot_module.build(
            run=kwargs["run"],
            manifest=kwargs.get("manifest"),
            book=kwargs.get("book"),
            reconciliation=kwargs.get("reconciliation"),
            construction=kwargs.get("construction"),
            book_reason=kwargs.get("book_reason"),
            actual=kwargs.get("actual"),
        )
        return {"mode": "on", "written": ["latest.json"], "detail": "snapshot: on"}

    monkeypatch.setattr(snapshot_module, "write_snapshot", fake_write_snapshot)
    sent: list[dict] = []
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload)
    )
    monkeypatch.setenv(notify.API_KEY_ENV, "re_" + "test-key-value")
    monkeypatch.setenv(notify.TO_ENV, "owner@example.com")

    failed = {
        "job": "live_daily",
        "target_close": "2026-10-06",
        "status": "error",
        "inputs": {},
        "failures": [],
        "worst_input": None,
        "worst_sessions_behind": 0,
    }
    assert (
        run_live_daily.finish_run(
            run_date="2026-10-06",
            result=failed,
            status="error",
            dry_run=True,
            detail='UndefinedColumn: column "unexplained_adjustment" does not exist',
            orders=192,
            sent_notional=355_251.19,
        )
        == 1
    )

    names = {name["ticker"]: name for name in captured["document"]["book"]["names"]}
    assert names["DG"]["traded_notional"] == pytest.approx(524.42)
    # A name with no leg is a zero, not a blank.
    assert names["BBB"]["traded_notional"] == pytest.approx(0.0)
    # And it is the same arithmetic the success path does on the same legs: the
    # evening's own log and the store's rows are one set of legs, so the two paths
    # cannot disagree about the day's turnover.
    expected = run_live_daily.with_traded(borrowed, run_live_daily.traded_by_name(day))
    assert expected is not None
    assert list(names[t]["traded_notional"] for t in expected["ticker"]) == [
        pytest.approx(value) for value in expected["traded_notional"]
    ]

    # The control: a store that could not be read answers None, not an empty frame,
    # and the published book then carries no traded column rather than zeroes.
    def boom(*args, **kwargs):
        raise RuntimeError("the store is unreachable")

    monkeypatch.setattr(store, "select", boom)
    assert run_live_daily.stored_legs("2026-10-06") is None
    monkeypatch.setattr(run_live_daily, "stored_legs", lambda as_of: None)
    captured.clear()
    run_live_daily.finish_run(
        run_date="2026-10-06",
        result=failed,
        status="error",
        dry_run=True,
        detail="the store is unreachable",
        orders=192,
    )
    assert all(
        "traded_notional" not in name for name in captured["document"]["book"]["names"]
    ), "a day whose legs could not be read is not a day that traded nothing"


def test_record_run_replaces_the_same_date_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path)
    run_live_daily.record_run("live_daily", "2026-09-23", "ok")
    run_live_daily.record_run("live_daily", "2026-09-23", "failed", "boom")
    frame = store.select("cron_runs")
    assert len(frame) == 1
    assert frame.iloc[0]["status"] == "failed"
    assert frame.iloc[0]["detail"] == "boom"


def test_the_window_override_opens_only_on_the_exact_word() -> None:
    """The opposite default from the dry-run flag, and for the same reason.

    A dry-run flag left unset costs a rehearsal. A window left open costs an
    order at an hour the broker's DAY semantics do not hold for.
    """
    assert run_live_daily.resolve_force_hour("true") is True
    for value in (None, "", "TRUE ", " yes", "1", "false"):
        assert run_live_daily.resolve_force_hour(value) is False, value


def test_the_run_refuses_outside_the_window_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An evening at the wrong hour is not the evening, and the owner is told.

    The refusal is before the day's bookkeeping, so the day stays un-run and the
    in-window cron later that day still has its evening. Writing a row here would
    either mark the day done or need a status the page then has to explain. Since
    nothing is recorded and no page changes, the one-line message is the only
    place the owner can learn the evening did not run at that hour.
    """
    from live import notify

    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(run_live_daily, "datetime", _clock("2026-09-22T09:00:00+00:00"))
    monkeypatch.setattr(staleness, "is_session", lambda day: True)
    monkeypatch.delenv(run_live_daily.FORCE_HOUR_ENV, raising=False)
    monkeypatch.setenv(notify.API_KEY_ENV, "re_test_key")
    monkeypatch.setenv(notify.TO_ENV, "owner@example.com")
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload)
    )

    assert run_live_daily.main() == 1

    assert store.select("cron_runs").empty
    assert store.select("run_status").empty
    assert len(sent) == 1
    assert sent[0]["subject"] == (
        "EFB refused | outside the 16:00-20:00 New York window"
    )
    # one line, with the refusal and its reason: the instant, the New York hour
    # it is, and the window it fell outside
    body = str(sent[0]["text"])
    assert body.count("\n") == 0
    assert body.startswith("EFB live book: refused, ")
    assert "2026-09-22T09:00:00+00:00" in body
    assert "05:00:00-04:00 in New York" in body
    assert "16:00-20:00 window the loop trades in" in body


def test_a_refusal_with_no_channel_still_fails_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing to send with is not a reason to report success.

    The refusal exits nonzero either way: the evening did not run, and a run the
    owner was not told about is the case the exit code exists for.
    """
    from live import notify

    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(run_live_daily, "datetime", _clock("2026-09-22T09:00:00+00:00"))
    monkeypatch.setattr(staleness, "is_session", lambda day: True)
    monkeypatch.delenv(run_live_daily.FORCE_HOUR_ENV, raising=False)
    monkeypatch.delenv(notify.API_KEY_ENV, raising=False)
    monkeypatch.delenv(notify.TO_ENV, raising=False)

    assert run_live_daily.main() == 1

    assert store.select("run_status").empty


def test_realized_pnl_is_the_change_in_the_accounts_equity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tonight's P&L is the move in the account's own equity, measured.

    The previous stored NAV row is the reading it is measured against, taken
    strictly before this close so a re-run cannot measure against itself, and the
    first evening records zero because there is no earlier equity to compare with.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")

    # the establishment evening: no earlier row, so nothing to measure against
    assert run_live_daily.realized_pnl("2026-09-22", 1_000_000.0) == 0.0

    store.upsert(
        "nav", [{"trade_date": "2026-09-21", "nav": 999_000.0, "realized_pnl": 0.0}]
    )
    assert run_live_daily.realized_pnl("2026-09-22", 1_002_500.0) == pytest.approx(
        3_500.0
    )

    # strictly before: tonight's own row is not the baseline
    store.upsert(
        "nav",
        [{"trade_date": "2026-09-22", "nav": 1_002_500.0, "realized_pnl": 3_500.0}],
    )
    assert run_live_daily.realized_pnl("2026-09-22", 1_002_500.0) == pytest.approx(
        3_500.0
    )
    assert run_live_daily.realized_pnl("2026-09-23", 1_010_000.0) == pytest.approx(
        7_500.0
    )
    # the latest earlier row is the baseline, so a loss is a negative number
    # rather than a smaller gain
    store.upsert(
        "nav",
        [{"trade_date": "2026-09-23", "nav": 1_010_000.0, "realized_pnl": 7_500.0}],
    )
    assert run_live_daily.realized_pnl("2026-09-24", 1_000_000.0) == pytest.approx(
        -10_000.0
    )


def test_the_proposals_row_states_the_traded_books_figures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`gross`, `net` and `achieved_annual_vol` on the proposal row are the
    traded book's, with the 499-name book beside them under `full_book_*`.

    The row is read by the dashboard and by anything asking what the loop holds,
    and a row whose gross was the 499-name book read as the gross of the book the
    owner holds. The two pairs are asserted to differ, so a row that quietly kept
    one book in both would fail here.
    """
    import json

    import pandas as pd

    proposals = tmp_path / "proposals"
    proposals.mkdir()
    manifest = {
        "signal": "idio_momentum",
        "n_names": 499,
        "n_excluded": 2,
        "gross": 0.9008,
        "net": 0.004,
        "kept_gross": 1.0,
        "kept_net": -3.3e-16,
        "n_eff_kept": 131.9,
        "n_eff_full_book": 268.7,
        "target_annual_vol": 0.10,
        "achieved_annual_vol": 0.0246,
        "kept_achieved_annual_vol": 0.0316,
        "idio_share_after_fmp": 1.0,
        "max_abs_exposure_after_fmp": 3.8e-15,
        "gross_cap_bound": True,
        "nav": 1_000_000.0,
        "expected_establishment_cost_bps": 14.5,
        "cost_breakdown_bps": {"total": 14.5},
        "notional": 1_000_000.0,
        "avg_trade_size": 6_666.67,
        "input_as_of": {},
        "max_input_staleness_days": 0,
        "universe_source": "spy_holdings",
        "universe_as_of": "2026-09-21",
    }
    (proposals / "proposal_2026-09-21.json").write_text(json.dumps(manifest))
    pd.DataFrame(
        {
            "ticker": ["AAA"],
            "weight": [1.0],
            "side": ["long"],
            "z": [1.0],
            "alpha": [1e-06],
        }
    ).to_parquet(proposals / "proposal_2026-09-21.parquet", index=False)
    root = tmp_path / "data"
    (root / "models" / "XS-v1").mkdir(parents=True)
    pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-09-21")],
            "ticker": ["AAA"],
            "specific_var": [0.0004],
        }
    ).to_parquet(root / "models" / "XS-v1" / "specific_var.parquet", index=False)
    monkeypatch.setattr(run_live_daily, "PROPOSAL_DIR", proposals)
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")

    run_live_daily.store_proposal("2026-09-21", data_root=root, dry_run=True)

    row = store.select("proposals").iloc[0]
    assert row["gross"] == pytest.approx(1.0)
    assert row["net"] == pytest.approx(-3.3e-16)
    assert row["achieved_annual_vol"] == pytest.approx(0.0316)
    assert row["full_book_gross"] == pytest.approx(0.9008)
    assert row["full_book_net"] == pytest.approx(0.004)
    assert row["full_book_achieved_annual_vol"] == pytest.approx(0.0246)
    assert row["gross"] != row["full_book_gross"]
    assert row["achieved_annual_vol"] != row["full_book_achieved_annual_vol"]


def test_a_rebalance_snapshot_carries_its_per_name_book(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The names the page lists are the rows the proposal wrote.

    The snapshot's per-name list is built from the frame `store_proposal` returns,
    and that function returned nothing while its docstring promised the rows. So on
    every evening the loop priced its own proposal the page read "The book: 0
    name(s)" beside a gross of 100%, a correct hedge and the day's orders: those
    numbers come from the manifest, and only the names come from the frame. The
    control is the same payload built with no frame, which is what the page showed.
    """
    import json

    import pandas as pd

    from live import snapshot as snapshot_module

    proposals = tmp_path / "proposals"
    proposals.mkdir()
    manifest = {
        "signal": "idio_momentum",
        "as_of": "2026-09-21",
        "n_names": 4,
        "n_excluded": 1,
        "n_kept": 3,
        "gross": 0.9008,
        "net": 0.004,
        "kept_gross": 1.0,
        "kept_net": -3.3e-16,
        "n_eff_kept": 2.9,
        "n_eff_full_book": 3.8,
        "target_annual_vol": 0.10,
        "achieved_annual_vol": 0.0246,
        "kept_achieved_annual_vol": 0.0316,
        "idio_share_after_fmp": 1.0,
        "max_abs_exposure_after_fmp": 3.8e-15,
        "gross_cap_bound": True,
        "nav": 1_000_000.0,
        "expected_establishment_cost_bps": 14.5,
        "cost_breakdown_bps": {"total": 14.5},
        "notional": 1_000_000.0,
        "avg_trade_size": 333_333.33,
        "input_as_of": {},
        "max_input_staleness_days": 0,
        "universe_source": "spy_holdings",
        "universe_as_of": "2026-09-21",
    }
    (proposals / "proposal_2026-09-21.json").write_text(json.dumps(manifest))
    # A rebalance's book: two longs and a short, and the page lists them largest
    # absolute weight first.
    pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC"],
            "weight": [0.6, 0.35, -0.05],
            "side": ["long", "long", "short"],
            "z": [1.2, 0.4, -0.3],
            "alpha": [3e-06, 1e-06, -2e-06],
        }
    ).to_parquet(proposals / "proposal_2026-09-21.parquet", index=False)
    root = tmp_path / "data"
    (root / "models" / "XS-v1").mkdir(parents=True)
    pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-09-21")] * 3,
            "ticker": ["AAA", "BBB", "CCC"],
            "specific_var": [0.0004, 0.0009, 0.0001],
        }
    ).to_parquet(root / "models" / "XS-v1" / "specific_var.parquet", index=False)
    monkeypatch.setattr(run_live_daily, "PROPOSAL_DIR", proposals)
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")

    # A rebalance evening: the account already holds a book, so the reasons are
    # classified against it.
    previous = pd.DataFrame(
        {"ticker": ["AAA", "BBB"], "weight": [0.5, 0.4], "z": [1.0, 0.3]}
    )
    rows = run_live_daily.store_proposal(
        "2026-09-21",
        data_root=root,
        dry_run=False,
        previous=previous,
        prior_settled=True,
    )

    assert rows is not None, "the snapshot was handed no book and listed no names"
    assert list(rows["ticker"]) == ["AAA", "BBB", "CCC"]
    assert set(rows["ticker"]) == set(store.select("positions")["ticker"])
    assert "reason" in rows.columns

    run = {
        "job": "live_daily",
        "target_close": "2026-09-21",
        "status": "ok",
        "dry_run": False,
    }
    payload = snapshot_module.build(run=run, manifest=manifest, book=rows)
    assert payload["book"]["n_names"] == manifest["n_kept"] == 3
    assert [entry["ticker"] for entry in payload["book"]["names"]] == [
        "AAA",
        "BBB",
        "CCC",
    ]
    assert payload["book"]["names"][2]["side"] == "short"
    assert all(entry["reason"] for entry in payload["book"]["names"])

    # The control: with no frame, the same payload has the same numbers and no
    # names, which is what the page showed.
    empty = snapshot_module.build(run=run, manifest=manifest, book=None)
    assert empty["book"]["n_names"] == 0
    assert empty["book"]["names"] == []
    assert empty["book"]["gross"] == pytest.approx(1.0)
    assert empty["book"]["n_kept"] == manifest["n_kept"]


def _clock(instant: str):
    """A `datetime` pinned to one instant, for the run's own window check."""

    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206 - the stdlib signature
            return datetime.fromisoformat(instant)

    return _Fixed


def test_a_failed_row_still_allows_a_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a completed status marks the day done.

    A row left by a failed or incomplete attempt is exactly what the next tick has
    to retry. Counting any row as "already ran" would file a day nothing was
    produced on as finished; the earlier `already_ran` did exactly that.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path)
    for status in ("failed", "error", "incomplete", "stale_stopped"):
        store.upsert(
            "cron_runs",
            [
                {
                    "run_date": "2026-09-23",
                    "job": "live_daily",
                    "status": status,
                    "detail": "boom",
                    "started_at": "",
                    "finished_at": "",
                }
            ],
        )
        assert run_live_daily.already_ran("live_daily", "2026-09-23") is False, status

    store.upsert(
        "cron_runs",
        [
            {
                "run_date": "2026-09-23",
                "job": "live_daily",
                "status": "ok",
                "detail": "",
                "started_at": "",
                "finished_at": "",
            }
        ],
    )
    assert run_live_daily.already_ran("live_daily", "2026-09-23") is True


def test_the_cron_script_makes_live_importable_from_any_cwd() -> None:
    """Render runs `python scripts/run_live_daily.py`, which puts scripts/ on
    sys.path, not the repo root; the module must add the root itself so the
    `live` package is reachable."""
    path = ROOT / "scripts" / "run_live_daily.py"
    spec = importlib.util.spec_from_file_location("_run_live_daily_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # executing the module body runs the sys.path fix without running main
    spec.loader.exec_module(module)
    from live import evening_job  # noqa: PLC0415 - imported after the fix

    assert evening_job.DATA_ROOT.name == "data"


def test_the_prior_book_is_the_accounts_book_not_the_stores() -> None:
    """Cost, turnover and the reason column are measured against what was held.

    The store's position row is the loop's intention: on a dry-run evening it names
    a book the account has never held, so a trade computed from it prices trades
    that never happened. Weights come from the account over its own equity; the
    store's row is read for the z-scores the reason classifier compares, because z
    is a model input rather than a position.
    """
    holdings = {
        "account_read": True,
        "establishment": False,
        "nav": 1_000_000.0,
        "broker": {"AAA": 60_000.0, "BBB": -20_000.0},
    }
    intentions = pd.DataFrame(
        {
            "trade_date": ["2026-09-25", "2026-09-25"],
            "ticker": ["AAA", "BBB"],
            "z": [1.5, -0.5],
            "weight": [0.9, 0.1],
        }
    )

    prior = run_live_daily.prior_book(holdings, intentions)

    assert prior is not None
    weights = prior.set_index("ticker")["weight"]
    assert weights["AAA"] == pytest.approx(0.06)
    assert weights["BBB"] == pytest.approx(-0.02)
    # the store's own weights never appear: its z does
    scores = prior.set_index("ticker")["z"]
    assert scores["AAA"] == pytest.approx(1.5)
    assert str(prior["trade_date"].iloc[0]) == "2026-09-25"

    # An establishment evening has no previous book at all: from flat every
    # previous weight is zero, which is what a missing book means to the callers.
    assert (
        run_live_daily.prior_book({**holdings, "establishment": True}, intentions)
        is None
    )
    # A name the account holds that the previous proposal never carried scores
    # zero rather than a missing value.
    unheld_score = run_live_daily.prior_book(
        {**holdings, "broker": {"CCC": 10_000.0}}, intentions
    )
    assert unheld_score is not None
    assert float(unheld_score["z"].iloc[0]) == 0.0
    # With no stored proposal the date is unknown, so the caller's close stands in
    # and the risk comparison degrades rather than failing the run.
    assert "trade_date" not in run_live_daily.prior_book(holdings, None).columns


def test_store_orders_carries_the_broker_id_and_the_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The evening that reconciles fills needs the broker's own keys on the row.

    A fill arrives as an activity against an order id, and the deterministic ticket
    is only unique among the orders this loop sends, so the id has to be stored
    while the broker is answering. The intent says open or close without anyone
    re-deriving it from the sign of a notional.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    # `store_orders` reads the day's log from the run tree's own `live/logs`, so
    # the repository root is moved to the temporary tree rather than the path
    # being passed in: that is the path the cron uses.
    monkeypatch.setattr(run_live_daily, "ROOT", tmp_path)
    log_dir = tmp_path / "live" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "trade_date": "2026-09-30",
                "ticker": "AAA",
                "intended_notional": 50_000.0,
                "filled_notional": 0.0,
                "status": "ACCEPTED",
                "reason": "accepted after the close",
                "reason_code": "",
                "client_order_id": "efb-2026-09-30-AAA-buy",
                "position_intent": "buy_to_open",
                "broker_order_id": "6f1d2c3b-aaaa-bbbb-cccc-1234567890ab",
            },
            {
                "trade_date": "2026-09-30",
                "ticker": "BBB",
                "intended_notional": -20_000.0,
                "filled_notional": 0.0,
                "status": "REJECTED_CAP",
                "reason": "guard rejected the order",
                "reason_code": "REJECTED_CAP",
                "client_order_id": "",
                "position_intent": "sell_to_open",
                "broker_order_id": "",
            },
        ]
    ).to_parquet(log_dir / "execution_2026-09-30.parquet", index=False)

    run_live_daily.store_orders("2026-09-30", dry_run=False)

    rows = store.select("orders").set_index("ticker")
    assert rows.loc["AAA", "broker_order_id"] == "6f1d2c3b-aaaa-bbbb-cccc-1234567890ab"
    assert rows.loc["AAA", "position_intent"] == "buy_to_open"
    # A leg that never became an order has no broker id to record, and an empty
    # string is the answer rather than a missing column.
    assert rows.loc["BBB", "broker_order_id"] == ""
    assert rows.loc["BBB", "position_intent"] == "sell_to_open"


def test_a_stopped_run_does_not_borrow_the_previous_books_cost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused evening has no cost of its own, and must not print last night's.

    The reporting path fills the book from the last stored proposal so the page is
    not blank on the evening the loop refused to price one. That borrowed manifest
    used to supply the day's cost as well, so a stale stop printed the previous
    book's establishment cost beside tonight's refusal, which reads as a number
    about tonight. The cost and the risk figures now come only from the manifest the
    run itself built, and the control below keeps that from being a change that
    simply removed the line everywhere.
    """
    from live import notify, staleness
    from live import snapshot as snapshot_module

    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(
        snapshot_module,
        "write_snapshot",
        lambda **kwargs: {"detail": "snapshot: pinned for the test"},
    )
    sent: list[dict] = []
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload)
    )
    monkeypatch.setenv(notify.API_KEY_ENV, "re_" + "test-key-value")
    monkeypatch.setenv(notify.TO_ENV, "owner@example.com")

    previous = {
        "trade_date": "2026-09-25",
        "expected_establishment_cost_bps": 15.0945,
        "cost_breakdown_bps": {
            "spread": 1.0,
            "impact": 13.5,
            "commission": 0.5,
            "borrow": 0.0945,
        },
    }
    book = pd.DataFrame({"ticker": ["AAA"], "weight": [1.0]})
    monkeypatch.setattr(
        snapshot_module,
        "previous_proposal",
        lambda: (previous, book, "the previous evening's book"),
    )
    stopped = {
        "job": "live_daily",
        "target_close": "2026-09-28",
        "status": "stale_stopped",
        "inputs": {"prices": {"content": "2026-09-25", "sessions_behind": 1}},
        "failures": [
            {"input": "prices", "sessions_behind": 1, "content": "2026-09-25"}
        ],
        "worst_input": "prices",
        "worst_sessions_behind": 1,
    }

    # The real path: `main` stops on the gate and calls `finish_run` with no
    # manifest of its own and no cost label.
    code = run_live_daily.finish_run(
        run_date="2026-09-28",
        result=stopped,
        status="stale_stopped",
        dry_run=True,
        detail="prices 1 session behind the 2026-09-28 close",
    )

    assert code == 1
    text = str(sent[0]["text"])
    assert "stale_stopped" in text
    assert "1 session behind" in text
    assert "Cost:" not in text, "the previous book's cost was printed as tonight's"
    assert "bps" not in text
    row = store.select(staleness.TABLE).iloc[0]
    assert row["status"] == "stale_stopped"
    # The risk figures are last night's book too, so they stay empty rather than
    # describing tonight's row with another evening's numbers.
    assert row["traded_risk"] is None and row["full_risk"] is None

    # The control: the run's own manifest still prints its own cost.
    own = dict(previous, trade_date="2026-09-28")
    sent.clear()
    run_live_daily.finish_run(
        run_date="2026-09-28",
        result={**stopped, "status": "ok", "failures": [], "worst_input": None},
        status="ok",
        dry_run=True,
        manifest=own,
        book=book,
        cost_label="establishment",
    )
    text = str(sent[0]["text"])
    assert "Cost: establishment, 15.09 bps of NAV" in text


class _Published:
    """A get callable answering one published document, as boto3 does."""

    def __init__(self, names: int) -> None:
        self.names = names
        self.asked: list[dict] = []

    def __call__(self, **kwargs):
        import json

        entries = [
            {"ticker": f"N{index}", "weight": 0.1} for index in range(self.names)
        ]
        text = json.dumps(
            {"book": {"n_names": len(entries), "names": entries}}
        ).encode()
        self.asked.append(kwargs)
        return {"Body": type("Body", (), {"read": lambda _self: text})()}


def test_the_evening_says_so_when_the_published_book_is_not_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The page's list is read back, and named in the message when it is missing.

    `book.names` is the only field the page draws that comes from a frame rather
    than from the manifest, and on 2026-10-01 it was empty beside a gross of 100%,
    a correct hedge and 188 orders. The writer now reads its own object back and
    compares the list with the run's own `n_kept`, and the evening's message says
    so. Nothing here may fail the run: the orders are already sent by this point,
    and the control shows the same evening silent when the list is the run's own.
    """
    from live import notify
    from live import snapshot as snapshot_module

    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(
        snapshot_module,
        "write_snapshot",
        lambda **kwargs: {
            "detail": f"snapshot: on ({snapshot_module.LATEST_KEY})",
            "written": [snapshot_module.LATEST_KEY],
            "payload": {},
        },
    )
    sent: list[dict] = []
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload)
    )
    monkeypatch.setenv(notify.API_KEY_ENV, "re_" + "test-key-value")
    monkeypatch.setenv(notify.TO_ENV, "owner@example.com")
    # The same four the writer needs to read its own object back. They name the
    # bucket; the read itself goes through the injected getter below.
    for name in snapshot_module.R2_ENVS:
        monkeypatch.setenv(name, "test-value")

    manifest = {"as_of": "2026-09-21", "n_kept": 3, "kept_gross": 1.0}
    book = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC"],
            "weight": [0.5, 0.3, 0.2],
            "side": ["long"] * 3,
        }
    )
    result = {
        "job": "live_daily",
        "target_close": "2026-09-21",
        "status": "ok",
        "failures": [],
        "inputs": {},
    }

    # The failure shape: the object is there and carries no names.
    empty = _Published(0)
    code = run_live_daily.finish_run(
        run_date="2026-09-21",
        result=result,
        status="ok",
        dry_run=True,
        manifest=manifest,
        book=book,
        snapshot_getter=empty,
    )
    assert code == 0, "the page's book cannot fail a run that has already traded"
    assert empty.asked and empty.asked[0]["Key"] == snapshot_module.LATEST_KEY
    text = str(sent[0]["text"])
    assert "Page book: empty (0 of the 3 kept names are in latest.json)" in text

    # The control: the run's own names, and the line is not there at all.
    sent.clear()
    good = _Published(3)
    code = run_live_daily.finish_run(
        run_date="2026-09-21",
        result=result,
        status="ok",
        dry_run=True,
        manifest=manifest,
        book=book,
        snapshot_getter=good,
    )
    assert code == 0
    assert "Page book" not in str(sent[0]["text"])
