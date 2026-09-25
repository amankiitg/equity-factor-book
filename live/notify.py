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

The webhook URL is a credential: it comes from `EFB_NOTIFY_SLACK_WEBHOOK_URL`,
it is set on the cron service only, and it is never printed, logged or written
to `efb`. Every string that leaves this module is scrubbed first, because a
failed send raises with the URL in its text and that text is what gets stored.

Email is behind the same interface on purpose and is not built: a channel is a
function from a message to a side effect, so adding SMTP later is one function
and one set of owner credentials, and nothing else changes.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from collections.abc import Callable
from typing import Any

CHANNEL_ENV = "EFB_NOTIFY_SLACK_WEBHOOK_URL"
TIMEOUT_SECONDS = 10.0
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
) -> str:
    """The fields, in order, ready for a preview."""
    close = target_close or "unknown close"
    label = STATUS_LABELS.get(status, status)
    caught_up = len(catch_up_sessions or [])
    if caught_up > 1:
        label = f"{label} (catch-up of {caught_up} sessions)"
    lines = [f"EFB live book {close}: {label}"]

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


def slack_payload(message: str) -> dict[str, str]:
    """The incoming-webhook body. One text field, so the preview shows it."""
    return {"text": message}


def post(webhook: str, payload: dict[str, Any], timeout: float = TIMEOUT_SECONDS):
    """POST the payload. Raises on anything but a 2xx answer."""
    request = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if not 200 <= int(response.status) < 300:  # pragma: no cover - urllib raises
            raise RuntimeError(f"the webhook answered {int(response.status)}")


def send(
    message: str,
    *,
    webhook: str | None = None,
    poster: Callable[[str, dict[str, Any]], Any] | None = None,
) -> dict[str, str]:
    """Deliver one message, and never raise.

    Returns `sent`, `failed` or `skipped`. `skipped` means no channel is
    configured: the run still happened, but nothing was delivered, so the
    caller records and reports it rather than pretending the owner was told.
    The webhook URL is never part of the result.
    """
    url = (webhook if webhook is not None else os.environ.get(CHANNEL_ENV, "")).strip()
    if not url:
        return {
            "status": STATUS_SKIPPED,
            "detail": f"{CHANNEL_ENV} is not set, so no message was sent",
        }
    deliver = poster or post
    try:
        deliver(url, slack_payload(message))
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
    webhook: str | None = None,
    poster: Callable[[str, dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Compose and deliver one run's message, returning both parts."""
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
    )
    result = send(message, webhook=webhook, poster=poster)
    result["text"] = message
    return result
