"""Sprint E11, Part 3b: every run notifies the owner.

The message is tested for the three fields in order, for the dry-run line that
must never read as "0 orders", and for the scrub that keeps a connection string
out of it. The run-level tests drive the cron script and assert the record the
owner and the dashboard actually see.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from live import appendix, evening_job, extend, morning_job, notify, staleness, store
from scripts import run_live_daily

ROOT = Path(__file__).resolve().parents[1]
SESSION = "2026-09-22"
FAKE_DB_URL = (
    "postgresql://postgres.omnsjnosbaiqkrmnknqw:supersecretpassword@"
    "aws-0-us-east-1.pooler.supabase.com:6543/postgres"
)
FAKE_KEY = "re_" + "AbCdEf123456_ghIJKl7890"
FAKE_TO = "owner@example.com"


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


def _no_work(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace every step that would fetch, size or hash."""
    from efb import evidence

    for name in ("hydrate", "persist_new_sessions", "appendix_manifest"):
        monkeypatch.setattr(appendix, name, lambda *args, **kwargs: {})
    # The first-run guard decides whether the store may be used at all, and its
    # four cases have their own tests; here the store is simply already open.
    monkeypatch.setattr(appendix, "open_store", lambda *args, **kwargs: False)
    for name in (
        "extend_archives",
        "extend_prices",
        "extend_shares",
        "extend_returns",
        "extend_model",
        "refresh_version",
    ):
        monkeypatch.setattr(extend, name, lambda *a, **k: {})
    monkeypatch.setattr(evidence, "snapshot", lambda *a, **k: None)
    monkeypatch.setattr(run_live_daily, "already_ran", lambda job, day: False)
    monkeypatch.setattr(run_live_daily, "store_proposal", lambda as_of: None)
    monkeypatch.setattr(run_live_daily, "store_orders", lambda as_of, dry: None)
    monkeypatch.setattr(run_live_daily, "store_reconciliation", lambda as_of, row: None)


def _patch_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The gate's own tests live elsewhere; here it is pinned to a clean pass."""
    gate = {
        "job": "live_daily",
        "checked_at": "2026-09-22T22:30:00+00:00",
        "target_close": SESSION,
        "allowed_sessions_behind": 0,
        "inputs": {"prices": {"content": SESSION, "sessions_behind": 0}},
        "failures": [],
        "worst_input": "prices",
        "worst_sessions_behind": 0,
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


def test_a_clean_run_sends_the_message_and_stores_what_it_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []
    _no_work(monkeypatch)
    _patch_gate(monkeypatch, tmp_path)
    _patch_success(monkeypatch)
    monkeypatch.setenv(notify.API_KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(notify.TO_ENV, FAKE_TO)
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload["text"])
    )

    assert run_live_daily.main() == 0

    assert len(sent) == 1
    assert f"EFB live book {SESSION}: ok" in sent[0]
    assert "dry run: 152 orders proposed, $2,014,000 gross, none sent" in sent[0]
    row = store.select("run_status").iloc[0]
    assert row["status"] == "ok"
    assert row["notify_status"] == notify.STATUS_SENT
    assert row["notify_failed"] == False or not row["notify_failed"]  # noqa: E712
    assert row["n_orders"] == 152
    assert row["gross_notional"] == 2_014_000.0
    assert store.select("cron_runs").iloc[0]["status"] == "ok"


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
    # the failure is visible in the cron record, and never the URL
    cron = store.select("cron_runs").iloc[0]
    assert cron["status"] == "ok"
    assert "notification failed" in cron["detail"]
    assert "hooks.slack.com" not in cron["detail"]
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
    """Four sessions across a weekend and a Monday, from the price panel."""
    sessions = run_live_daily._catch_up_sessions(pd.Timestamp("2026-09-15"))
    assert sessions == ["2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21"]


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
