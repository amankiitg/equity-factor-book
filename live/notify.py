"""Sprint E11, Part 3b: every run notifies the owner.

Two evenings of remembering to open a page is how a silent failure gets missed
on exactly the days that count, so the rule is one message per session, on
every run, including clean ones. Silence then means something: a run that never
started cannot send anything, so the absence of the evening message is the
alarm, and that is also why an outside heartbeat is worth offering.

The message carries three fields, in this order, each readable from a preview:

1. Did it run? `ok`, `stale_stopped` or `error`, with the target close.
2. Did the proposal produce orders? In dry run the line says so in full:
   "dry run: N orders proposed, $X gross, none sent". It never reads as
   "0 orders": when the run stopped before sizing, the line says that instead.
3. Staleness. The worst input and how many sessions it is behind, and on a
   stale stop every failing input.

The channel is email through Resend's HTTP API, copied from
credit-trading-lab's pattern (`execution/alerts.py` there): a bearer key in an
Authorization header, one POST to `https://api.resend.com/emails` with from, to,
subject and text, and a 15-second timeout. Not SMTP: Render blocks outbound SMTP
ports, and HTTPS is never blocked. The key is `EFB_RESEND_API_KEY`, EFB's own key
under the same Resend account with sending access only, so it cannot cross with
the credit lab's; sender and recipient come from `EFB_NOTIFY_EMAIL_FROM` and
`EFB_NOTIFY_EMAIL_TO`. None of the three is ever printed, logged or written to
`efb`, and every string that leaves this module is scrubbed first, because a
failed send raises with the key in its text and that text is what gets stored.

The key is a credential like any other, so `re_...`, the shape Resend issues, is
one of the patterns the scrub removes.

The message's first line names the store the run wrote to, so the one failure
that looks healthy from the outside is the first thing read.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from collections.abc import Callable
from typing import Any

# The store's own label, so the first line of every message names where the
# run's writes went, or says why they could not go anywhere.
from live import store as live_store

# The Resend HTTP API, the owner's three variables, and the sender fallback that
# needs no verified domain. `onboarding@resend.dev` is Resend's shared sender, and
# it can only deliver to the address that owns the Resend account, which is enough
# here because the recipient is the owner and says what a verified domain will
# lift.
RESEND_ENDPOINT = "https://api.resend.com/emails"
API_KEY_ENV = "EFB_RESEND_API_KEY"
FROM_ENV = "EFB_NOTIFY_EMAIL_FROM"
TO_ENV = "EFB_NOTIFY_EMAIL_TO"
DEFAULT_SENDER = "equity-factor-book <onboarding@resend.dev>"
RESEND_KEY_SHAPE = r"\bre_[A-Za-z0-9_-]{8,}\b"
TIMEOUT_SECONDS = 15.0
STATUS_SENT = "sent"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
REDACTION = "[redacted]"

# Every one of these has to survive a preview: the first line is the status.
STATUS_LABELS: dict[str, str] = {
    "ok": "ok, the run completed",
    "stale_stopped": "stale_stopped, the run refused to price a book",
    "error": "error, the run failed",
}

# Patterns that must never leave the process. The URL rule catches the webhook
# and any connection string; the token rules catch JWTs, long base64 and hex
# blobs; the last catches `password=...`, `api_key: ...` and their spellings.
_SCRUBS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"',;)]+"), REDACTION),
    # Resend's key shape, which is not long enough to be caught by the base64
    # rules and is not spelled `api_key=` by anything that raises it.
    (re.compile(RESEND_KEY_SHAPE), REDACTION),
    (re.compile(r"\beyJ[A-Za-z0-9._-]{10,}"), REDACTION),
    (re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b"), REDACTION),
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), REDACTION),
    (
        re.compile(
            r"(?i)\b(pass(?:word|wd)?|secret|token|api[_-]?key|access[_-]?key)"
            r"\s*[=:]\s*[^\s,;)\"]+"
        ),
        REDACTION,
    ),
)


def scrub(text: str) -> str:
    """A string with every URL, token and key=value secret replaced.

    Applied to anything that leaves the process: the one-line error reason that
    goes into the message and into `run_status`, and the send failure's own
    text, which raises with the webhook URL inside it.
    """
    cleaned = str(text)
    for pattern, replacement in _SCRUBS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def _money(value: float | None) -> str:
    return f"${float(value or 0.0):,.0f}"


def _sessions(value: Any) -> str:
    if value is None:
        return "no date at all"
    count = int(value)
    return "1 session behind" if count == 1 else f"{count} sessions behind"


def _failure_list(failures: list[dict[str, Any]]) -> str:
    parts = []
    for failure in failures:
        parts.append(f"{failure['input']} {_sessions(failure['sessions_behind'])}")
    return "; ".join(parts)


def compose(
    *,
    status: str,
    target_close: str | None,
    dry_run: bool = True,
    orders: int | None = None,
    gross: float | None = None,
    worst_input: str | None = None,
    worst_sessions_behind: int | None = None,
    failures: list[dict[str, Any]] | None = None,
    detail: str = "",
    error_type: str | None = None,
    catch_up_sessions: list[str] | None = None,
    splits: list[str] | None = None,
    flags: list[dict[str, Any]] | None = None,
    store: str | None = None,
    snapshot: str | None = None,
    cross_checks_capped: str | None = None,
) -> str:
    """The fields, in order, ready for a preview.

    The first line names the store every write went to, or says why it could not
    be used. A wrong store is the one failure that looks healthy from the
    outside, so it is the first thing the owner reads.
    """
    close = target_close or "unknown close"
    label = STATUS_LABELS.get(status, status)
    caught_up = len(catch_up_sessions or [])
    if caught_up > 1:
        label = f"{label} (catch-up of {caught_up} sessions)"
    store_line = store if store is not None else live_store.store_label()
    lines = [f"store: {store_line}", f"EFB live book {close}: {label}"]

    if status == "ok":
        if dry_run:
            lines.append(
                f"Orders: dry run: {int(orders or 0)} orders proposed, "
                f"{_money(gross)} gross, none sent"
            )
        else:
            lines.append(
                f"Orders: {int(orders or 0)} orders sent, {_money(gross)} gross"
            )
    elif status == "stale_stopped":
        lines.append(
            "Orders: none. The run stopped on staleness before sizing, so no "
            "book was priced and no order was built."
        )
    else:
        lines.append(
            "Orders: none. The run failed before sizing, so no book was priced."
        )

    if worst_input is None:
        lines.append("Staleness: no input failed the check.")
    else:
        lines.append(
            f"Staleness: worst input {worst_input}, "
            f"{_sessions(worst_sessions_behind)}."
        )
    if status == "stale_stopped" and failures:
        lines.append(f"Failing inputs: {_failure_list(failures)}.")
    # A split is named here because it moves a held position without a decision
    # being made, and an unexplained large move is named because it is the one
    # thing in the appended session a person has to look at.
    if cross_checks_capped:
        # A name left unchecked is a name whose split could pass as an
        # unexplained move, so the owner is told the moment the cap is hit.
        lines.append(f"{cross_checks_capped[:1].upper()}{cross_checks_capped[1:]}.")
    if snapshot:
        # Whether the page has this run is as much a part of "did it run" as the
        # status is, so a deliberate `off` says so rather than going unmentioned.
        lines.append(f"Snapshot: {snapshot}.")
    if splits:
        lines.append(f"Corporate actions: {', '.join(splits)}.")
    if flags:
        lines.append(f"Large moves: {_flag_list(flags)}.")
    if status == "error":
        reason = scrub(detail).strip() or "no reason recorded"
        prefix = error_type or "Exception"
        # the caller's one-line reason usually carries the type already
        if reason.startswith(f"{prefix}:"):
            lines.append(f"Error: {reason}")
        else:
            lines.append(f"Error: {prefix}: {reason}")

    return "\n".join(lines)


def _flag_list(flags: list[dict[str, Any]]) -> str:
    parts = []
    for flag in flags:
        move = flag.get("return")
        shown = (
            f"{float(move) * 100:+.1f}%" if isinstance(move, (int, float)) else "n/a"
        )
        parts.append(f"{flag.get('ticker')} {shown} ({flag.get('flag')})")
    return "; ".join(parts)


def subject_text(
    *,
    status: str,
    target_close: str | None,
    dry_run: bool = True,
    orders: int | None = None,
    worst_input: str | None = None,
    worst_sessions_behind: int | None = None,
    splits: list[str] | None = None,
    flags: list[dict[str, Any]] | None = None,
    error_type: str | None = None,
    catch_up_sessions: list[str] | None = None,
) -> str:
    """The inbox line: the status, then what was proposed, then staleness.

    Readable without opening the email, which is the whole point of it, so it
    carries the three things the owner checks from a phone: `EFB ok 2026-09-25 |
    150 proposed, none sent | stale 0`, `EFB STALE <close> | none proposed |
    stale 3 (prices)`, `EFB ERROR <close> | none proposed | <ExceptionType>`. A
    catch-up run says so beside the status, and a split or an unexplained move is
    appended rather than left for the body.
    """
    close = target_close or "unknown close"
    if status == "ok":
        word = "ok"
    elif status == "stale_stopped":
        word = "STALE"
    else:
        word = "ERROR"
    caught_up = len(catch_up_sessions or [])
    if caught_up > 1:
        word = f"{word} (catch-up {caught_up})"
    if status == "ok":
        middle = (
            f"{int(orders or 0)} proposed, none sent"
            if dry_run
            else f"{int(orders or 0)} sent"
        )
    else:
        middle = "none proposed"
    if status == "error":
        tail = error_type or "Exception"
    elif worst_sessions_behind is None:
        tail = "stale unknown"
    elif int(worst_sessions_behind) == 0:
        tail = "stale 0"
    else:
        tail = f"stale {int(worst_sessions_behind)} ({worst_input})"
    parts = [f"EFB {word} {close}", middle, tail]
    if splits:
        parts.append(_split_short(splits))
    unexplained = [flag for flag in flags or [] if flag.get("explained_by") is None]
    if unexplained:
        parts.append(f"flag {len(unexplained)}")
    return " | ".join(parts)


def _split_short(splits: list[str]) -> str:
    """`split APH 2:1` from the body's own wording, so the two cannot drift."""
    names = []
    for item in splits:
        short = str(item)
        if short.startswith("split: "):
            short = short[len("split: ") :]
        if short.endswith(" applied"):
            short = short[: -len(" applied")]
        names.append(short)
    return "split " + ", ".join(names)


def email_payload(
    *, subject: str, body: str, sender: str, recipient: str
) -> dict[str, Any]:
    """The Resend request body, in the shape credit-trading-lab's sender uses."""
    return {"from": sender, "to": [recipient], "subject": subject, "text": body}


def post(
    endpoint: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: float = TIMEOUT_SECONDS,
):
    """POST the payload. Raises on anything but a 2xx answer."""
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if not 200 <= int(response.status) < 300:  # pragma: no cover - urllib raises
            raise RuntimeError(f"the endpoint answered {int(response.status)}")


def send(
    subject: str,
    message: str,
    *,
    api_key: str | None = None,
    to: str | None = None,
    sender: str | None = None,
    poster: Callable[..., Any] | None = None,
) -> dict[str, str]:
    """Deliver one email, and never raise.

    Returns `sent`, `failed` or `skipped`. `skipped` means no channel is
    configured: the run still happened, but nothing was delivered, so the caller
    records it and fails the run, because a run the owner was not told about did
    not do its job. Neither the key nor the address is part of the result, and
    the failure text is scrubbed before it is.
    """
    key = (api_key if api_key is not None else os.environ.get(API_KEY_ENV, "")).strip()
    recipient = (to if to is not None else os.environ.get(TO_ENV, "")).strip()
    from_addr = (
        sender if sender is not None else os.environ.get(FROM_ENV, "")
    ).strip() or DEFAULT_SENDER
    if not key or not recipient:
        return {
            "status": STATUS_SKIPPED,
            "detail": (
                f"{API_KEY_ENV} and {TO_ENV} are not both set, so no email was sent"
            ),
        }
    payload = email_payload(
        subject=subject, body=message, sender=from_addr, recipient=recipient
    )
    deliver = poster or post
    try:
        deliver(
            RESEND_ENDPOINT,
            payload,
            {"Authorization": f"Bearer {key}"},
        )
    except Exception as exc:  # noqa: BLE001 - a failed send is never fatal here
        return {
            "status": STATUS_FAILED,
            "detail": scrub(f"{type(exc).__name__}: {exc}")[:200],
        }
    return {"status": STATUS_SENT, "detail": ""}


def notify_run(
    *,
    status: str,
    target_close: str | None,
    dry_run: bool = True,
    orders: int | None = None,
    gross: float | None = None,
    worst_input: str | None = None,
    worst_sessions_behind: int | None = None,
    failures: list[dict[str, Any]] | None = None,
    detail: str = "",
    error_type: str | None = None,
    catch_up_sessions: list[str] | None = None,
    splits: list[str] | None = None,
    flags: list[dict[str, Any]] | None = None,
    store: str | None = None,
    snapshot: str | None = None,
    cross_checks_capped: str | None = None,
    api_key: str | None = None,
    poster: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Compose and deliver one run's message, returning both parts."""
    subject_line = subject_text(
        status=status,
        target_close=target_close,
        dry_run=dry_run,
        orders=orders,
        worst_input=worst_input,
        worst_sessions_behind=worst_sessions_behind,
        splits=splits,
        flags=flags,
        error_type=error_type,
        catch_up_sessions=catch_up_sessions,
    )
    message = compose(
        status=status,
        target_close=target_close,
        dry_run=dry_run,
        orders=orders,
        gross=gross,
        worst_input=worst_input,
        worst_sessions_behind=worst_sessions_behind,
        failures=failures,
        detail=detail,
        error_type=error_type,
        catch_up_sessions=catch_up_sessions,
        splits=splits,
        flags=flags,
        store=store,
        snapshot=snapshot,
        cross_checks_capped=cross_checks_capped,
    )
    result = send(subject_line, message, poster=poster)
    result["text"] = message
    result["subject"] = subject_line
    return result
