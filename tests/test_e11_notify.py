"""Sprint E11, Part 3b: every run notifies the owner.

The message is tested for the three fields in order, for the dry-run line that
must never read as "0 orders", and for the scrub that keeps a connection string
out of it. The run-level tests drive the cron script and assert the record the
owner and the dashboard actually see.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from live import (
    alpaca,
    appendix,
    evening_job,
    extend,
    morning_job,
    notify,
    staleness,
    store,
)
from scripts import run_live_daily

ROOT = Path(__file__).resolve().parents[1]
SESSION = "2026-09-22"
FAKE_DB_URL = (
    "postgresql://postgres.omnsjnosbaiqkrmnknqw:supersecretpassword@"
    "aws-0-us-east-1.pooler.supabase.com:6543/postgres"
)
FAKE_KEY = "re_" + "AbCdEf123456_ghIJKl7890"
FAKE_TO = "owner@example.com"

# The account number the fake broker reports. The evening checks the account
# it is trading before it sizes anything, so a fake read has to name the same
# account `EFB_ALPACA_ACCOUNT_ID` does.
ACCOUNT_NUMBER = "PAFAKE0002"


def test_the_message_leads_with_the_status_and_the_target_close() -> None:
    message = notify.compose(
        status="ok",
        target_close=SESSION,
        dry_run=True,
        orders=152,
        gross=2_014_000.0,
        worst_input="prices",
        worst_sessions_behind=0,
    )
    store_line, first, second, third = message.splitlines()
    assert store_line.startswith("store: ")
    assert first == f"EFB live book {SESSION}: ok, the run completed"
    assert second == (
        "Orders: dry run: 152 orders proposed, $2,014,000 gross, none sent"
    )
    assert third == "Staleness: worst input prices, 0 sessions behind."
    # the field the rule names explicitly: never "0 orders"
    assert "0 orders" not in message


def test_a_live_run_says_orders_were_sent() -> None:
    message = notify.compose(
        status="ok",
        target_close=SESSION,
        dry_run=False,
        orders=12,
        gross=250_000.0,
        worst_input="shares",
        worst_sessions_behind=1,
    )
    assert "Orders: 12 orders sent, $250,000 gross" in message
    assert "dry run" not in message


def test_a_stale_stop_names_every_failing_input() -> None:
    failures = [
        {
            "input": "prices",
            "sessions_behind": 3,
            "content": "2026-09-21",
            "gated_by": "content",
        },
        {
            "input": "shares",
            "sessions_behind": 2,
            "content": "2026-09-22",
            "gated_by": "fetch",
        },
        {
            "input": "sectors",
            "sessions_behind": None,
            "content": None,
            "gated_by": "fetch",
        },
    ]
    message = notify.compose(
        status="stale_stopped",
        target_close=SESSION,
        dry_run=True,
        worst_input="sectors",
        worst_sessions_behind=None,
        failures=failures,
        detail="sectors has no date at all; prices is 3 sessions behind",
    )
    assert message.splitlines()[1] == (
        f"EFB live book {SESSION}: stale_stopped, the run refused to price a book"
    )
    assert "Orders: none. The run stopped on staleness before sizing" in message
    assert "Staleness: worst input sectors, no date at all." in message
    assert (
        "Failing inputs: prices 3 sessions behind; shares 2 sessions behind; "
        "sectors no date at all." in message
    )
    assert "0 orders" not in message


def test_the_staleness_line_states_each_inputs_allowance() -> None:
    """An allowance is only readable beside the distance it applies to.

    The universe sits one session behind and is allowed one, so a run that
    passes still names it as the worst input, with its allowance beside it; a
    stale stop states the allowance on every failing input, so a two-session
    universe reads as over its allowance rather than as an unexplained number.
    """
    clean = notify.compose(
        status="ok",
        target_close=SESSION,
        dry_run=True,
        orders=150,
        gross=2_000_000.0,
        inputs={
            "prices": {"sessions_behind": 0, "allowed_sessions_behind": 0},
            "universe": {"sessions_behind": 1, "allowed_sessions_behind": 1},
        },
    )
    assert "Staleness: worst input universe, 1 session behind (allowed 1)." in clean

    failures = [
        {
            "input": "universe",
            "sessions_behind": 2,
            "allowed_sessions_behind": 1,
            "gated_by": "content",
        },
        {
            "input": "prices",
            "sessions_behind": 1,
            "allowed_sessions_behind": 0,
            "gated_by": "content",
        },
    ]
    stopped = notify.compose(
        status="stale_stopped",
        target_close=SESSION,
        dry_run=True,
        worst_input="universe",
        worst_sessions_behind=2,
        failures=failures,
        inputs={"universe": {"sessions_behind": 2, "allowed_sessions_behind": 1}},
    )
    assert "Staleness: worst input universe, 2 sessions behind (allowed 1)." in stopped
    assert (
        "Failing inputs: universe 2 sessions behind (allowed 1); "
        "prices 1 session behind (allowed 0)." in stopped
    )


def test_the_subject_names_the_worst_input_when_the_run_passed() -> None:
    """A clean evening still has an input behind the close, inside an allowance.

    The gate reports no failures on a clean run, so the subject's staleness field
    had nothing to name and read "stale unknown" on every evening that passed. It
    names the same worst input the body does, derived from the gate's own inputs
    mapping: the universe, one session behind and allowed one.
    """
    subject = notify.subject_text(
        status="ok",
        target_close="2026-09-25",
        orders=150,
        inputs={
            "prices": {"sessions_behind": 0, "allowed_sessions_behind": 0},
            "universe": {"sessions_behind": 1, "allowed_sessions_behind": 1},
        },
    )
    assert subject == "EFB ok 2026-09-25 | 150 proposed, none sent | stale 1 (universe)"
    # The negative control: with no mapping there is nothing to name, and an
    # error run still names its type rather than a staleness.
    assert (
        notify.subject_text(status="ok", target_close="2026-09-25", orders=1)
        == "EFB ok 2026-09-25 | 1 proposed, none sent | stale unknown"
    )
    assert (
        notify.subject_text(
            status="error", target_close="2026-09-25", error_type="ValueError"
        )
        == "EFB ERROR 2026-09-25 | none proposed | ValueError"
    )


def test_an_error_message_names_the_type_and_scrubs_the_reason() -> None:
    message = notify.compose(
        status="error",
        target_close=SESSION,
        dry_run=True,
        detail=f"OperationalError: could not connect to {FAKE_DB_URL}",
        error_type="OperationalError",
    )
    assert message.splitlines()[1] == f"EFB live book {SESSION}: error, the run failed"
    assert "Orders: none. The run failed before sizing" in message
    assert "Staleness: no input failed the check." in message
    assert "Error: OperationalError:" in message
    assert "[redacted]" in message
    assert "supersecretpassword" not in message
    assert "pooler.supabase.com" not in message
    assert "postgresql://" not in message


def test_scrub_removes_urls_tokens_and_key_values() -> None:
    text = (
        f"post to {notify.RESEND_ENDPOINT} with key {FAKE_KEY} and token "
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abcdefghijklmnop and "
        "password=hunter2 api_key: 9f8e7d6c5b4a39281706f5e4d3c2b1a0 and "
        f"db={FAKE_DB_URL}"
    )
    cleaned = notify.scrub(text)
    assert FAKE_KEY not in cleaned
    assert "eyJ" not in cleaned
    assert "hunter2" not in cleaned
    assert "9f8e7d6c5b4a39281706f5e4d3c2b1a0" not in cleaned
    assert "supersecretpassword" not in cleaned
    assert cleaned.count("[redacted]") >= 5


def test_send_without_a_channel_is_skipped_not_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (notify.API_KEY_ENV, notify.TO_ENV):
        monkeypatch.delenv(name, raising=False)
    result = notify.send("a subject", "hello")
    assert result["status"] == notify.STATUS_SKIPPED
    assert notify.API_KEY_ENV in result["detail"]


def test_a_send_failure_is_recorded_without_the_key() -> None:
    def _refuse(url: str, payload: dict[str, Any], headers: Any = None) -> None:
        raise RuntimeError(f"HTTP 404 for {url} with {headers}")

    result = notify.send(
        "subject", "hello", api_key=FAKE_KEY, to=FAKE_TO, poster=_refuse
    )
    assert result["status"] == notify.STATUS_FAILED
    assert FAKE_KEY not in result["detail"]
    assert "[redacted]" in result["detail"]
    assert "RuntimeError" in result["detail"]


def test_a_boto3_error_carrying_a_credential_is_scrubbed() -> None:
    """boto3 raises with the service's own text, and R2's XML carries the key id."""
    access_key = "AKIAIOSFODNN7EXAMPLE"
    secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    message = (
        "An error occurred (InvalidAccessKeyId) when calling the PutObject "
        f"operation: <Error><AWSAccessKeyId>{access_key}</AWSAccessKeyId>"
        f"<Message>aws_secret_access_key={secret}</Message></Error>"
    )

    cleaned = notify.scrub(message)

    assert access_key not in cleaned
    assert secret not in cleaned
    assert "[redacted]" in cleaned


class _NoCorporateActions:
    """The corporate-actions stub: no split, no flags, no spin-off."""

    splits: list = []
    sessions: list = []
    ratios: dict = {}
    flags: list = []
    unchecked = 0
    spinoffs: list = []


def _no_work(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace every step that would fetch, size or hash."""
    for name in ("hydrate", "persist_new_sessions", "appendix_manifest"):
        monkeypatch.setattr(appendix, name, lambda *args, **kwargs: {})
    # The first-run guard decides whether the store may be used at all, and its
    # four cases have their own tests; here the store is simply already open.
    monkeypatch.setattr(appendix, "open_store", lambda *args, **kwargs: False)
    # Every read and write the run makes is stubbed in these tests, so the run
    # tree is the repository's own data root rather than a 876 MB copy of it.
    from live import runroot

    monkeypatch.setattr(
        runroot, "prepare", lambda *args, **kwargs: runroot.DEFAULT_SEED_ROOT
    )
    # The corporate-actions rule reads and writes the price artifact of whichever
    # tree the run is pointed at, and it has its own tests.
    from live import corporate_actions

    monkeypatch.setattr(
        corporate_actions, "apply_to_artifact", lambda *a, **k: _NoCorporateActions()
    )
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
    monkeypatch.setattr(run_live_daily, "already_ran", lambda job, day: False)
    # The suite runs whenever it runs, and the evening refuses outside the
    # 16:00-20:00 New York window it trades in. These tests are about the run, so
    # the window is overridden exactly as a rehearsal does. The refusal itself is
    # pinned in tests/test_run_live_daily.py and here.
    monkeypatch.setenv(run_live_daily.FORCE_HOUR_ENV, "true")
    # The suite runs whatever day it happens to, and the cron correctly does
    # nothing at all on a day the exchange is shut (tests/test_e11_holiday.py).
    # These tests are about the evening, so the day is declared a session.
    monkeypatch.setattr(staleness, "is_session", lambda day: True)
    monkeypatch.setattr(run_live_daily, "store_proposal", lambda *a, **k: None)
    monkeypatch.setattr(run_live_daily, "store_orders", lambda *a, **k: None)
    monkeypatch.setattr(run_live_daily, "store_reconciliation", lambda *a, **k: None)


def _patch_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The gate's own tests live elsewhere; here it is pinned to a clean pass."""
    gate = {
        "job": "live_daily",
        "checked_at": "2026-09-22T22:30:00+00:00",
        "target_close": SESSION,
        "allowed_sessions_behind": {"prices": 0, "universe": 1},
        "inputs": {
            "prices": {
                "content": SESSION,
                "sessions_behind": 0,
                "allowed_sessions_behind": 0,
            },
            "universe": {
                "content": "2026-09-21",
                "sessions_behind": 1,
                "allowed_sessions_behind": 1,
            },
        },
        "failures": [],
        "worst_input": None,
        "worst_sessions_behind": None,
        "max_input_staleness_days": 0,
        "status": "ok",
    }
    monkeypatch.setattr(staleness, "check", lambda *a, **k: gate)
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")


def _patch_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        evening_job,
        "build_proposal",
        lambda *a, **k: {"as_of": SESSION, "n_kept": 150},
    )
    monkeypatch.setattr(
        morning_job,
        "run_morning",
        lambda *a, **k: {
            "orders": 152,
            "intended_notional": 2_014_000.0,
            "dry_run": True,
        },
    )
    from live import reconcile

    monkeypatch.setattr(reconcile, "daily_record", lambda *a, **k: {"dry_run": True})


# The real morning job, saved before the harness replaces it: a test that is about
# the day's own legs puts it back.
_real_run_morning = morning_job.run_morning


def test_a_member_with_no_price_is_named_in_the_message() -> None:
    """A book quietly smaller than the index is a book nobody can check.

    The member drops out by construction, because the model needs its return. What
    the message must not do is leave the owner to notice the gap.
    """
    from live import notify

    fields = {
        "status": "ok",
        "target_close": "2026-09-21",
        "dry_run": True,
        "orders": 3,
        "gross": 1000.0,
    }
    message = notify.compose(**fields, no_price=["WBA", "EA"])

    assert "Dropped for no price: EA, WBA." in message
    assert "Dropped for no price" not in notify.compose(**fields)


def test_a_refused_send_keeps_the_reason_and_names_itself(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A 403 arrived as "HTTP Error 403: Forbidden", with the body thrown away.

    Resend's answer says why, in JSON, and that reason is the whole value of the
    failure: "the domain is not verified" is actionable, "403" is not. The request
    also had no agent of its own, and the library's default is `Python-urllib/3.x`,
    which an endpoint behind a WAF is entitled to refuse.
    """
    import io
    import urllib.error

    from live import notify

    key = "re_abcdefghijklmnopqrstuvwxyz"
    seen: list[Any] = []

    def refuse(request: Any, timeout: float | None = None) -> Any:
        seen.append(request)
        raise urllib.error.HTTPError(
            notify.RESEND_ENDPOINT,
            403,
            "Forbidden",
            {},  # type: ignore[arg-type]
            io.BytesIO(
                b'{"statusCode":403,"name":"validation_error",'
                b'"message":"The example.com domain is not verified"}'
            ),
        )

    monkeypatch.setattr(notify.urllib.request, "urlopen", refuse)
    monkeypatch.setenv(notify.API_KEY_ENV, key)
    monkeypatch.setenv(notify.TO_ENV, "owner@example.com")
    monkeypatch.setenv(notify.FROM_ENV, "EFB <efb@example.com>")

    with caplog.at_level("WARNING"):
        result = notify.send("subject", "body")

    assert result["status"] == notify.STATUS_FAILED
    assert "the endpoint answered 403" in result["detail"]
    assert "example.com domain is not verified" in result["detail"]
    # the key is stripped wherever the reason goes
    assert key not in result["detail"]
    assert key not in caplog.text
    # and the run log carries the same reason as the row
    assert "example.com domain is not verified" in caplog.text
    # an explicit agent, rather than the library's own
    assert seen, "no request was made"
    assert seen[0].get_header("User-agent") == notify.USER_AGENT


def test_an_errored_run_does_not_mark_the_day_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed run must leave no `cron_runs` row, or the retry is a no-op.

    The first Render evening recorded the day from a run that died at the email, and
    every later attempt that day exited "already ran" without sending anything: a day
    nothing was produced on, filed as finished. Only a run that completes marks the
    day done.
    """
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)

    def refuse(url: str, payload: dict, headers: dict | None = None) -> None:
        raise RuntimeError("the endpoint answered 403: the domain is not verified")

    monkeypatch.setattr(notify, "post", refuse)

    assert run_live_daily.main() == 1
    assert store.select("cron_runs").empty
    # and the failure is still on the record, where it belongs
    assert not store.select("run_status").empty


def _clock(instant: str):
    """A `datetime` pinned to one instant, for the run's own window check."""

    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206 - the stdlib signature
            return datetime.fromisoformat(instant)

    return _Fixed


class _AccountBroker:
    """An account read: what it holds and what it is worth, from one request."""

    def get_account(self) -> Any:
        class _Account:
            account_number = ACCOUNT_NUMBER
            id = "paper-account"
            equity = "1234567.89"
            cash = "23456.78"

        return _Account()

    def get_all_positions(self) -> list[Any]:
        class _Position:
            def __init__(self, symbol: str, value: float, side: str) -> None:
                self.symbol = symbol
                self.market_value = str(abs(value))
                self.side = side
                # signed the way the broker signs it, so the read's own check
                # that the side and the quantity agree has something to check
                self.qty = str(value / 100.0)

        return [
            _Position("AAA", 500.0, "long"),
            _Position("BBB", -250.0, "short"),
        ]

    def get_orders(self, filter: Any = None) -> list[Any]:
        """No working orders: this account holds a book, so it is a rebalance."""
        return []


def _read_the_account(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the evening's account read at the fake, under the account it names.

    The run compares the number the broker reports against `EFB_ALPACA_ACCOUNT_ID`
    before it sizes anything, so a test that fakes the read has to act like the
    owner who set the variable.
    """
    monkeypatch.setenv(alpaca.ACCOUNT_ID_ENV, ACCOUNT_NUMBER)
    monkeypatch.setattr(alpaca, "read_client", _AccountBroker)


def test_a_clean_run_sends_the_message_and_stores_what_it_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[dict[str, Any]] = []
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload)
    )

    assert run_live_daily.main() == 0

    assert len(sent) == 1
    body = str(sent[0]["text"])
    assert f"EFB live book {SESSION}: ok" in body
    assert "dry run: 152 orders proposed, $2,014,000 gross, none sent" in body
    # the gate's own inputs mapping reaches the message: the universe is one
    # session behind and allowed one, and both the body's line and the subject's
    # staleness field say so
    assert "Staleness: worst input universe, 1 session behind (allowed 1)." in body
    assert sent[0]["subject"] == (
        f"EFB ok {SESSION} | 152 proposed, none sent | stale 1 (universe)"
    )
    row = store.select("run_status").iloc[0]
    assert row["status"] == "ok"
    assert row["notify_status"] == notify.STATUS_SENT
    assert row["notify_failed"] == False or not row["notify_failed"]  # noqa: E712
    assert row["n_orders"] == 152
    assert row["gross_notional"] == 2_014_000.0
    assert store.select("cron_runs").iloc[0]["status"] == "ok"


def test_the_evening_stores_the_brokers_book_and_the_accounts_equity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The day's row carries the account's own equity, and the broker's book.

    The store's own position row is what the loop meant to hold. The account's
    answer is a different question and is stored apart, so a run that reads a book
    back can tell the two apart. The NAV the book is sized from and the names the
    broker reports come from one read of one account.
    """
    real_store_reconciliation = run_live_daily.store_reconciliation
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    # The harness stubs the day's rows away; this test is about them.
    monkeypatch.setattr(
        run_live_daily, "store_reconciliation", real_store_reconciliation
    )
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        evening_job,
        "build_proposal",
        lambda *a, **k: seen.update(k) or {"as_of": SESSION, "n_kept": 150},
    )
    _read_the_account(monkeypatch)
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)
    monkeypatch.setattr(notify, "post", lambda url, payload, headers=None: None)

    assert run_live_daily.main() == 0

    nav_row = store.select("nav").iloc[0]
    assert nav_row["nav"] == pytest.approx(1_234_567.89)
    assert nav_row["cash"] == pytest.approx(23_456.78)
    book = store.select("broker_positions")
    assert sorted(book["ticker"]) == ["AAA", "BBB"]
    aaa = book.loc[book["ticker"] == "AAA"].iloc[0]
    assert aaa["side"] == "long"
    assert aaa["market_value"] == pytest.approx(500.0)
    # the weight is the name's share of the account's own equity, not of a
    # constant
    assert aaa["weight"] == pytest.approx(500.0 / 1_234_567.89)
    # and the book itself was sized from that same number
    assert seen["nav"] == pytest.approx(1_234_567.89)
    assert "the account's own equity" in str(seen["nav_source"])


def test_the_evening_records_the_equity_move_as_the_days_pnl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The nav row's P&L is tonight's equity less the last stored equity.

    Read from the account, not asserted: the run writes the difference between the
    equity it just read and the previous stored NAV row, so the day's P&L is a
    measurement of the account rather than a zero that says the book made nothing.
    """
    real_store_reconciliation = run_live_daily.store_reconciliation
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setattr(
        run_live_daily, "store_reconciliation", real_store_reconciliation
    )
    store.upsert(
        "nav",
        [
            {
                "trade_date": "2026-09-21",
                "nav": 1_230_000.0,
                "realized_pnl": 0.0,
                "cash": 1_230_000.0,
            }
        ],
    )
    _read_the_account(monkeypatch)
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)
    monkeypatch.setattr(notify, "post", lambda url, payload, headers=None: None)

    assert run_live_daily.main() == 0

    rows = store.select("nav").sort_values("trade_date")
    tonight = rows.loc[rows["trade_date"].astype(str) == SESSION].iloc[0]
    assert tonight["nav"] == pytest.approx(1_234_567.89)
    assert tonight["realized_pnl"] == pytest.approx(1_234_567.89 - 1_230_000.0)
    # the earlier row is untouched: a P&L is measured, not carried forward
    earlier = rows.loc[rows["trade_date"].astype(str) == "2026-09-21"].iloc[0]
    assert earlier["realized_pnl"] == pytest.approx(0.0)


def test_the_run_compares_against_the_book_before_tonight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The check is handed the close being priced, and compares against what came
    before it.

    The store here holds a row for a date after tonight's close, which is the
    state a run that got ahead of itself leaves behind, and the account holds the
    book of the close before. The note naming the earlier row is what proves the
    date reached the check: unpinned, the latest row is the future one and every
    name in it would be reported missing at the broker.
    """
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    store.upsert(
        "positions",
        [
            {"trade_date": "2026-09-21", "ticker": "AAA", "signed_notional": 500.0},
            {"trade_date": "2026-09-23", "ticker": "BBB", "signed_notional": 700.0},
        ],
    )
    _read_the_account(monkeypatch)
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)
    monkeypatch.setattr(notify, "post", lambda url, payload, headers=None: None)

    assert run_live_daily.main() == 0

    row = store.select("run_status").iloc[0]
    note = str(row["positions_check"])
    assert "the 2026-09-21 position row" in note
    assert "2026-09-23" not in note
    # the negative control, at the level of the store: the row the check would
    # have used without the date is the later one
    assert store.select("positions")["trade_date"].max() == "2026-09-23"


def test_the_window_override_lets_an_out_of_hours_run_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same evening, at 05:00 New York, runs with the override and refuses
    without it.

    The override is the only way past the window, and the refusal has to come
    before any work: an evening that fired at the wrong hour has not priced the
    close, so it must leave the day un-run for the in-window cron.
    """
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setattr(run_live_daily, "datetime", _clock("2026-09-22T09:00:00+00:00"))
    monkeypatch.setattr(notify, "post", lambda url, payload, headers=None: None)
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)
    assert staleness.in_cron_window(
        run_live_daily.datetime.now(run_live_daily.UTC)
    ) is (False)

    assert run_live_daily.main() == 0
    assert not store.select("run_status").empty

    # the negative control: the same harness, the same instant, no override
    monkeypatch.delenv(run_live_daily.FORCE_HOUR_ENV)
    assert run_live_daily.main() == 1


def test_the_recorded_run_states_both_books_risk_figures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The day's row carries the traded book's figures and the full book's.

    Both come from the manifest the evening built, so the row the page reads and
    the row the reconciliation stores cannot describe two different books. Each
    figure keeps the name that says which book it is.
    """
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setattr(
        evening_job,
        "build_proposal",
        lambda *a, **k: {
            "as_of": SESSION,
            "n_kept": 150,
            "kept_achieved_annual_vol": 0.0459,
            "kept_idio_share": 0.981,
            "kept_max_abs_exposure": 0.0334,
            "kept_gross": 0.94,
            "kept_net": 0.0,
            "n_eff_kept": 94.2573,
            "max_kept_weight": 0.033448,
            "variance_share_cap_binds": False,
            "top_variance_shares": [{"ticker": "AAA", "variance_share": 0.031}],
            "achieved_annual_vol": 0.06,
            "idio_share_after_fmp": 1.0,
            "max_abs_exposure_after_fmp": 3.8e-15,
            "gross": 1.0,
            "net": 0.0,
            "n_eff_full_book": 157.3,
            "n_names": 499,
        },
    )
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)
    monkeypatch.setattr(notify, "post", lambda url, payload, headers=None: None)

    assert run_live_daily.main() == 0

    row = store.select("run_status").iloc[0]
    traded = json.loads(row["traded_risk"])
    full = json.loads(row["full_risk"])
    assert traded["forecast_annual_vol"] == pytest.approx(0.0459)
    assert full["forecast_annual_vol"] == pytest.approx(0.06)
    assert traded["gross"] == pytest.approx(0.94)
    assert full["gross"] == pytest.approx(1.0)
    assert traded["n_eff"] == pytest.approx(94.2573)
    assert full["n_names"] == 499
    assert traded["variance_share_cap_binds"] is False
    assert traded["top_variance_shares"] == [{"ticker": "AAA", "variance_share": 0.031}]


def test_an_incomplete_run_is_not_ok_and_is_not_marked_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused or rejected leg leaves the day unfinished.

    The run is not ok: at least one leg was not confirmed, so no `cron_runs` row is
    written and the next tick retries. The run_status row and the message still go
    out, naming the leg and the code, so the owner can see what happened.
    """
    sent: list[dict[str, Any]] = []
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setattr(
        morning_job,
        "run_morning",
        lambda *a, **k: {
            "orders": 1,
            "intended_notional": 50_000.0,
            "complete": False,
            "incomplete_legs": [
                {
                    "ticker": "BBB",
                    "status": "SKIPPED",
                    "reason_code": "ASSET_NOT_SHORTABLE",
                }
            ],
        },
    )
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload)
    )

    assert run_live_daily.main() == 1

    row = store.select("run_status").iloc[0]
    assert row["status"] == "incomplete"
    assert "BBB" in str(row["detail"]) and "ASSET_NOT_SHORTABLE" in str(row["detail"])
    # the day is not done: the next tick retries it
    assert store.select("cron_runs").empty
    assert "incomplete, a leg was not confirmed" in str(sent[0]["text"])


def test_a_refused_snapshot_upload_fails_the_run_and_is_named_in_the_email(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused put fails the run, and the email says which failure it was."""
    from live import snapshot

    access_key = "AKIAIOSFODNN7EXAMPLE"
    secret = "test-secret-access-key"
    sent: list[str] = []
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload["text"])
    )
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, "on")
    for name in snapshot.R2_ENVS:
        monkeypatch.setenv(name, "test-value-for-" + name)

    def _refuse(key: str, text: str, *, poster: Any = None) -> None:
        raise RuntimeError(
            "An error occurred (AccessDenied) when calling the PutObject "
            f"operation: <AWSAccessKeyId>{access_key}</AWSAccessKeyId> "
            f"secret_access_key={secret}"
        )

    monkeypatch.setattr(snapshot, "put_object", _refuse)

    assert run_live_daily.main() == 1

    assert len(sent) == 1
    assert "snapshot failed" in sent[0]
    assert "RuntimeError" in sent[0]
    assert access_key not in sent[0]
    assert secret not in sent[0]
    assert "[redacted]" in sent[0]
    row = store.select("run_status").iloc[0]
    assert row["status"] == "error"
    assert "snapshot failed" in str(row["detail"])
    assert str(row["snapshot"]).startswith("snapshot failed")
    assert access_key not in str(row["snapshot"])


def test_a_failed_send_is_recorded_and_the_run_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)

    def _refuse(url: str, payload: dict[str, Any], headers: Any = None) -> None:
        raise RuntimeError(f"HTTP 500 for {url}")

    monkeypatch.setattr(notify, "post", _refuse)

    assert run_live_daily.main() == 1

    # the run itself is recorded as ok: the book was built and no order moved
    row = store.select("run_status").iloc[0]
    assert row["status"] == "ok"
    assert bool(row["notify_failed"])
    assert row["notify_status"] == notify.STATUS_FAILED
    assert "152" not in str(row["detail"])
    # the day is not marked done, so the next tick runs again and tries to tell the
    # owner again: a run whose message never arrived did not do its job
    assert store.select("cron_runs").empty
    # the dashboard shows the notification failure rather than a clean run
    state = staleness.run_state(
        {str(key): value for key, value in row.items()},
        now=pd.Timestamp("2026-09-22T22:30:00Z"),
    )
    assert not state["clean"]
    assert state["state"] == "notify_failed"


def test_a_run_with_no_channel_is_loud_about_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.delenv(notify.API_KEY_ENV, raising=False)
    monkeypatch.delenv(notify.TO_ENV, raising=False)

    assert run_live_daily.main() == 1

    row = store.select("run_status").iloc[0]
    assert row["notify_status"] == notify.STATUS_SKIPPED
    state = staleness.run_state(
        {str(key): value for key, value in row.items()},
        now=pd.Timestamp("2026-09-22T22:30:00Z"),
    )
    assert state["state"] == "notify_not_configured"
    assert "no notification channel is set" in state["message"]
    assert notify.API_KEY_ENV in state["message"]


def test_an_unexpected_error_notifies_with_a_scrubbed_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload["text"])
    )

    def _explode(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ConnectionError(f"could not reach {FAKE_DB_URL}")

    monkeypatch.setattr(evening_job, "build_proposal", _explode)

    assert run_live_daily.main() == 1

    assert len(sent) == 1
    assert sent[0].splitlines()[1] == (
        f"EFB live book {SESSION}: error, the run failed"
    )
    assert "Error: ConnectionError:" in sent[0]
    assert "supersecretpassword" not in sent[0]
    assert "postgresql://" not in sent[0]
    row = store.select("run_status").iloc[0]
    assert row["status"] == "error"
    assert "supersecretpassword" not in str(row["detail"])
    assert "[redacted]" in str(row["detail"])
    # nothing wrote a proposal or an order on the way down
    assert store.select("proposals").empty
    assert store.select("orders").empty


def test_a_catch_up_run_says_so_in_the_first_line() -> None:
    """The first deploy appends several sessions at once; the preview must say so,
    because a catch-up run is never one of the gate's two closes."""
    sessions = ["2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21"]
    message = notify.compose(
        status="ok",
        target_close="2026-09-21",
        dry_run=True,
        orders=150,
        gross=2_000_000.0,
        worst_input="prices",
        worst_sessions_behind=0,
        catch_up_sessions=sessions,
    )
    assert message.splitlines()[1] == (
        "EFB live book 2026-09-21: ok, the run completed " "(catch-up of 4 sessions)"
    )
    # one session is a normal evening, not a catch-up
    single = notify.compose(
        status="ok",
        target_close="2026-09-21",
        dry_run=True,
        orders=150,
        gross=2_000_000.0,
        worst_input="prices",
        worst_sessions_behind=0,
        catch_up_sessions=["2026-09-21"],
    )
    assert "catch-up" not in single


def test_the_appended_sessions_are_measured_from_the_calendar() -> None:
    """Every session the panel holds after the close, weekends excluded.

    The expected list is read from the panel the function itself reads rather
    than typed: the panel's last session moves with every rebuild, and the
    measurement is the sessions between the two dates, not a fixed count.
    """
    before = pd.Timestamp("2026-09-15")
    sessions = run_live_daily._catch_up_sessions(before)
    after = extend.last_price_session()
    assert after is not None
    expected = [
        day.date().isoformat()
        for day in staleness.sessions(before + pd.Timedelta(days=1), after)
    ]
    assert sessions == expected
    # and the measurement is a calendar one: the first entry is the next
    # session, and no weekend day is in the list
    assert sessions[0] == "2026-09-16"
    assert not any(
        pd.Timestamp(day).dayofweek >= 5 for day in sessions
    ), "a weekend day is not a session"


def test_a_one_session_run_is_not_a_catch_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gate close is a run whose target close is the only session it appended."""
    panel = iter([pd.Timestamp("2026-09-18"), pd.Timestamp("2026-09-21")])
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)
    monkeypatch.setattr(
        extend,
        "last_price_session",
        lambda *a, **k: next(panel, pd.Timestamp("2026-09-21")),
    )
    sent: list[str] = []
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload["text"])
    )

    assert run_live_daily.main() == 0

    row = store.select("run_status").iloc[0]
    assert bool(row["catch_up"]) is False
    assert row["catch_up_sessions"] == '["2026-09-21"]'
    assert "catch-up" not in sent[0]


def test_a_multi_session_run_is_recorded_as_a_catch_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel = iter([pd.Timestamp("2026-09-15"), pd.Timestamp("2026-09-21")])
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)
    monkeypatch.setattr(
        extend,
        "last_price_session",
        lambda *a, **k: next(panel, pd.Timestamp("2026-09-21")),
    )
    sent: list[str] = []
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload["text"])
    )

    assert run_live_daily.main() == 0

    row = store.select("run_status").iloc[0]
    assert bool(row["catch_up"]) is True
    assert row["catch_up_sessions"] == (
        '["2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21"]'
    )
    assert "(catch-up of 4 sessions)" in sent[0]


def test_the_subject_reads_from_the_inbox_the_way_the_owner_asked() -> None:
    """Five formats, one per thing the owner checks from a phone."""
    ok = notify.subject_text(
        status="ok", target_close="2026-09-25", orders=150, worst_sessions_behind=0
    )
    assert ok == "EFB ok 2026-09-25 | 150 proposed, none sent | stale 0"
    live = notify.subject_text(
        status="ok",
        target_close="2026-09-25",
        dry_run=False,
        orders=150,
        worst_sessions_behind=0,
    )
    assert live == "EFB ok 2026-09-25 | 150 sent | stale 0"
    stale = notify.subject_text(
        status="stale_stopped",
        target_close="2026-09-25",
        worst_input="prices",
        worst_sessions_behind=3,
    )
    assert stale == "EFB STALE 2026-09-25 | none proposed | stale 3 (prices)"
    error = notify.subject_text(
        status="error", target_close="2026-09-25", error_type="ValueError"
    )
    assert error == "EFB ERROR 2026-09-25 | none proposed | ValueError"
    catch_up = notify.subject_text(
        status="ok",
        target_close="2026-09-22",
        orders=150,
        worst_sessions_behind=0,
        catch_up_sessions=["2026-09-15", "2026-09-16", "2026-09-17", "2026-09-21"],
    )
    assert catch_up == (
        "EFB ok (catch-up 4) 2026-09-22 | 150 proposed, none sent | stale 0"
    )
    # a split and an unexplained move are appended, and an explained move is not
    flagged = notify.subject_text(
        status="ok",
        target_close="2026-09-25",
        orders=12,
        worst_sessions_behind=0,
        splits=["split: APH 2:1 applied"],
        flags=[
            {"ticker": "ZZZ", "return": -0.55, "explained_by": None},
            {"ticker": "APH", "return": 0.04, "explained_by": "split: APH 2:1 applied"},
        ],
    )
    assert flagged == (
        "EFB ok 2026-09-25 | 12 proposed, none sent | stale 0 | split APH 2:1 | flag 1"
    )
    # the body still leads with the store, and the subject is carried beside it
    sent: list[dict[str, Any]] = []
    result = notify.send(
        ok,
        "body",
        api_key=FAKE_KEY,
        to=FAKE_TO,
        poster=lambda url, payload, headers=None: sent.append(payload),
    )
    assert result["status"] == notify.STATUS_SENT
    assert sent[0]["subject"] == ok
    assert sent[0]["to"] == [FAKE_TO]
    assert sent[0]["text"] == "body"


def test_the_resend_key_shape_is_scrubbed() -> None:
    """It is a credential, and nothing else in the scrub rules matches it."""
    cleaned = notify.scrub(f"Resend refused: {FAKE_KEY}")
    assert FAKE_KEY not in cleaned
    assert "[redacted]" in cleaned
    # The endpoint is not a secret, but the URL rule redacts every URL on the way
    # out, which is the right side to err on.
    assert notify.scrub(notify.RESEND_ENDPOINT) == "[redacted]"


def test_the_cost_line_carries_the_four_parts_it_is_made_of() -> None:
    """The establishment day's cost, as the arithmetic it actually is.

    These are the real numbers of the rehearsed proposal: 53.7338 bp of NAV =
    5.3558 spread + 39.0447 impact + 1.0 commission + 8.3333 borrow. One total
    asks to be trusted; four parts can be added up by the person reading them.
    """
    from live import notify

    text = notify.compose(
        status="ok",
        target_close="2026-09-22",
        dry_run=True,
        orders=150,
        gross=1_000_000.0,
        establishment=True,
        cost_label="establishment",
        cost_bps=53.7338,
        cost_breakdown={
            "spread": 5.3558,
            "impact": 39.0447,
            "commission": 1.0,
            "borrow": 8.3333,
            "total": 53.7338,
        },
    )

    assert (
        "Cost: establishment, 53.73 bps of NAV "
        "(spread 5.36 + impact 39.04 + commission 1.00 + borrow 8.33)." in text
    )


def test_the_cost_line_says_so_when_the_parts_are_not_the_total() -> None:
    """A breakdown that does not add up is a bug, and the message is where it shows."""
    from live import notify

    text = notify.compose(
        status="ok",
        target_close="2026-09-22",
        cost_label="establishment",
        cost_bps=75.3,
        cost_breakdown={
            "spread": 12.3,
            "impact": 30.0,
            "commission": 2.0,
            "borrow": 6.0,
            "total": 75.3,
        },
    )

    assert "which sum to 50.30, not 75.30" in text


def test_the_cost_line_stands_without_a_breakdown() -> None:
    """An older proposal has a total and no parts, and the line still reads."""
    from live import notify

    text = notify.compose(
        status="ok", target_close="2026-09-22", cost_label="rebalance", cost_bps=12.0
    )

    assert "Cost: rebalance, 12.00 bps of NAV." in text
    assert "(" not in text.split("Cost:")[1].split("\n")[0]


def test_the_email_names_the_names_whose_liquidity_is_a_median() -> None:
    """A cost that is partly a stand-in says which part.

    SW's own trailing dollar volume is unknown, so the panel median stood in for
    it; the owner can only judge the day's cost if they know whose cost was
    measured and whose was assumed.
    """
    from live import notify

    thin = [
        {"ticker": "SW", "adv_usd": None},
        {"ticker": "XYZ", "adv_usd": 420_000.0},
    ]
    me = notify.compose(
        status="ok",
        target_close="2026-09-25",
        dry_run=True,
        orders=150,
        cost_label="establishment",
        cost_bps=16.49,
        thin_adv=thin,
    )

    assert (
        "Liquidity: 2 kept name(s) whose own trailing 63-session dollar volume is "
        "unknown or under $1M, so the panel median stands in: SW no ADV; "
        "XYZ $420,000." in me
    )
    # The negative control: a book whose liquidity was measured says nothing.
    clean = notify.compose(
        status="ok", target_close="2026-09-25", dry_run=True, orders=150
    )
    assert "Liquidity:" not in clean


def test_the_email_names_the_kept_names_the_minimum_left_untraded() -> None:
    """A kept name that did not move is named, with the size of its leg.

    The name is in tonight's book and nothing was sent for it: its target and its
    holding differ by less than an order is worth. Saying which names and by how
    much is what makes a short trade list read as a book that stood still rather
    than as a book that lost a name.
    """
    from live import notify

    skipped = [
        {"ticker": "AAA", "intended_notional": 84.0},
        {"ticker": "BBB", "intended_notional": -121.5},
    ]

    message = notify.compose(
        status="ok",
        target_close="2026-09-25",
        dry_run=True,
        orders=150,
        skipped_minimum=skipped,
    )

    assert (
        "Under the $250 minimum, left untraded: 2 name(s) (AAA $84, BBB $122)."
        in message
    )
    # The negative control: a book that moved in full says nothing about the floor.
    clean = notify.compose(
        status="ok", target_close="2026-09-25", dry_run=True, orders=150
    )
    assert "minimum" not in clean


def test_the_email_counts_the_rest_when_many_names_are_under_the_minimum() -> None:
    """A long list is counted rather than spilled into the message."""
    from live import notify

    skipped = [
        {"ticker": f"T{index:03d}", "intended_notional": float(index)}
        for index in range(20)
    ]

    message = notify.compose(
        status="ok",
        target_close="2026-09-25",
        dry_run=True,
        orders=5,
        skipped_minimum=skipped,
    )

    assert "20 name(s) (T000 $0, T001 $1, " in message
    assert ", and 8 more)" in message


def test_a_run_with_a_name_under_the_minimum_records_the_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The skipped leg reaches the day's leg log and the message, and the day is ok.

    The leg is not an order (the order count does not move), it is on the record
    with the code that says why, it does not make the run incomplete, and the
    message names it. A run that quietly traded 149 of its 150 names and said
    "ok, 149 orders" is the failure this pins.
    """
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    # This test is about the legs the run writes, so the morning job is the real
    # one; the harness's stub for it is put back. The day's log is captured
    # instead of written, because the repository already holds a log for this
    # session and `store_orders` reads that file, not the run's own frame.
    monkeypatch.setattr(morning_job, "run_morning", _real_run_morning)
    proposal = pd.DataFrame({"ticker": ["BIG", "TINY"], "weight": [0.10, 0.0001]})
    monkeypatch.setattr(morning_job, "load_proposal", lambda *a, **k: proposal)
    monkeypatch.setattr(
        morning_job, "_close_prices", lambda *a, **k: {"BIG": 100.0, "TINY": 100.0}
    )
    monkeypatch.setattr(morning_job, "connect", lambda dry_run: None)
    monkeypatch.setattr(morning_job.state, "write_positions", lambda *a, **k: None)
    logged: dict[str, pd.DataFrame] = {}
    monkeypatch.setattr(
        morning_job,
        "_write_execution_log",
        lambda as_of, records: logged.update({as_of: records}),
    )
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: captured.append(payload)
    )
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)

    assert run_live_daily.main() == 0

    frame = logged[SESSION]
    by_ticker = {row["ticker"]: row for row in frame.to_dict("records")}
    assert sorted(by_ticker) == ["BIG", "TINY"]
    assert by_ticker["BIG"]["status"] == "DRY_RUN"
    assert by_ticker["TINY"]["status"] == "SKIPPED"
    assert by_ticker["TINY"]["reason_code"] == "BELOW_MIN_NOTIONAL"
    assert "$100.00" in str(by_ticker["TINY"]["reason"])
    assert "$250 minimum" in str(by_ticker["TINY"]["reason"])
    # the day is not unfiled and the order count is the orders, not the legs
    assert store.select("cron_runs").iloc[0]["status"] == "ok"
    row = store.select("run_status").iloc[0]
    assert row["status"] == "ok"
    assert int(row["n_orders"]) == 1
    body = str(captured[0]["text"])
    assert "1 orders proposed" in body
    assert "left untraded: 1 name(s) (TINY $100)" in body


def test_a_snapshot_misconfiguration_stops_the_run_before_any_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch is read at the start, so a missing credential costs no trade.

    The writer checks the same settings when the evening is over. By then the book
    is sized and the orders have been sent, and a run that traded and cannot
    publish is a run that traded invisibly: the page is the only place the owner
    sees the book. The morning job must not be reached at all.
    """
    from live import snapshot

    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setattr(
        morning_job,
        "run_morning",
        lambda *a, **k: pytest.fail("an order was built with no page to show it"),
    )
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, "on")
    for name in snapshot.R2_ENVS:
        monkeypatch.delenv(name, raising=False)
    sent: list[str] = []
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload["text"])
    )
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)

    assert run_live_daily.main() == 1

    assert store.select("orders").empty
    assert len(sent) == 1
    assert "EFB_R2_ACCOUNT_ID" in sent[0]
    row = store.select("run_status").iloc[0]
    assert row["status"] == "error"
    assert "EFB_R2_ACCOUNT_ID" in str(row["detail"])


def test_a_configured_snapshot_reaches_the_morning_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control: the same run with the four variables set goes on.

    Without this the check above would pass on a build that refused every evening.
    """
    from live import snapshot

    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    reached: list[str] = []
    monkeypatch.setattr(
        morning_job,
        "run_morning",
        lambda *a, **k: reached.append("called")
        or {"orders": 152, "intended_notional": 2_014_000.0, "dry_run": True},
    )
    monkeypatch.setattr(snapshot, "put_object", lambda *a, **k: None)
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, "on")
    for name in snapshot.R2_ENVS:
        monkeypatch.setenv(name, "test-value")
    monkeypatch.setattr(notify, "post", lambda url, payload, headers=None: None)
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)

    assert run_live_daily.main() == 0

    assert reached == ["called"]


def test_a_traceback_is_scrubbed_before_it_is_logged() -> None:
    """The frames stay, the credential inside them does not.

    A traceback reaches the log with whatever the failing frame was reading, and a
    chain reaches it too: an exception raised while handling another carries the
    first one with it. Formatting first and scrubbing second is the one order in
    which every frame, every source line and every chained cause are in the text
    being scrubbed, which is what this pins.
    """
    secret = (
        "postgresql://postgres.abcdef:sup3rSecret@aws-0-us-east-1.pooler"
        ".supabase.com:6543/postgres"
    )
    try:
        try:
            raise RuntimeError(f"could not connect to {secret}")
        except RuntimeError as cause:
            raise ValueError("the seed could not be read") from cause
    except ValueError as exc:
        text = notify.scrub_traceback(exc)

    assert text.startswith("Traceback (most recent call last)")
    assert "sup3rSecret" not in text
    assert "postgresql://" not in text
    assert notify.REDACTION in text
    # The frames and both ends of the chain are kept: a trimmed one-line reason
    # would not say where the failure happened, which is the log's whole job.
    assert "ValueError: the seed could not be read" in text
    assert "RuntimeError: could not connect to" in text
    assert "The above exception was the direct cause" in text


def test_a_resend_key_inside_a_traceback_is_scrubbed() -> None:
    """A key arrives in a message rather than as a header, and the shape is caught."""
    exc = RuntimeError(f"send failed for key {FAKE_KEY}")
    text = notify.scrub_traceback(exc)
    assert FAKE_KEY not in text
    assert notify.REDACTION in text


def test_the_run_logs_a_scrubbed_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The failure's frames are logged and the credential inside them is not.

    The account read is where a connection string lives, and the cause chained
    beneath the failure carries it too. This drives the run to that failure and
    reads the log the cron writes, so both paths out of the process are covered:
    the reason in the message and the row, and the traceback in the log.
    """
    from live import positions

    secret = (
        "postgresql://postgres.abcdef:sup3rSecret@aws-0-us-east-1.pooler"
        ".supabase.com:6543/postgres"
    )

    def _leaky(*args: object, **kwargs: object) -> dict[str, object]:
        try:
            raise RuntimeError(f"could not connect to {secret}")
        except RuntimeError as cause:
            raise ValueError(f"the store was unreachable through {secret}") from cause

    sent: list[dict[str, Any]] = []
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(positions, "check", _leaky)
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload)
    )

    with caplog.at_level("ERROR"):
        assert run_live_daily.main() == 1

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "live daily failed" in logged
    assert "Traceback (most recent call last)" in logged
    # Both ends of the chain are on the record, with the secret taken out of both.
    assert "the store was unreachable through" in logged
    assert "could not connect to" in logged
    assert "sup3rSecret" not in logged
    assert "postgresql://" not in logged
    # The message the owner reads is scrubbed by the same rule.
    assert sent
    assert "sup3rSecret" not in str(sent[0]["text"])
    assert notify.REDACTION in str(sent[0]["text"])
