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
