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
import logging
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

# The floor a leg has to clear to be worth an order. The message names it beside
# the legs it left untraded, from the one definition the morning job applies.
from live import alpaca as alpaca_mod

# The store's own label, so the first line of every message names where the
# run's writes went, or says why they could not go anywhere.
from live import store as live_store

# How many skipped names the message spells out before it counts the rest.
MINIMUM_SKIP_NAMES = 12

# The Resend HTTP API, the owner's three variables, and the sender fallback that
# needs no verified domain. `onboarding@resend.dev` is Resend's shared sender, and
# it can only deliver to the address that owns the Resend account, which is enough
# here because the recipient is the owner and says what a verified domain will
# lift.
RESEND_ENDPOINT = "https://api.resend.com/emails"
# An explicit agent, because the library's default is `Python-urllib/3.x` and an
# endpoint behind a WAF is entitled to refuse that: the refusal then reads as a
# permissions problem in the log, which is a day of hunting for the wrong thing.
USER_AGENT = "efb-live-book/1.0"
logger = logging.getLogger(__name__)
API_KEY_ENV = "EFB_RESEND_API_KEY"
FROM_ENV = "EFB_NOTIFY_EMAIL_FROM"
TO_ENV = "EFB_NOTIFY_EMAIL_TO"
DEFAULT_SENDER = "equity-factor-book <onboarding@resend.dev>"
RESEND_KEY_SHAPE = r"\bre_[A-Za-z0-9_-]{8,}\b"
# boto3 raises with the service's own error text inside it, and an S3-compatible
# error body carries the access key id in XML. `AKIA`-style ids are 20 characters,
# below both the base64 and the hex length floors, so they need their own rule.
AWS_KEY_SHAPE = r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"
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
    # At least one leg was halted, left in an unknown state, refused or rejected.
    # The day is not done and will be retried, so it is neither ok nor a failure.
    "incomplete": "incomplete, a leg was not confirmed",
    # The exchange was shut: there was no close to price, so the run did nothing
    # and said so. Not a failure, and not a silent evening either.
    "market_closed": "market_closed, the exchange was shut",
}

# Patterns that must never leave the process. The URL rule catches the webhook
# and any connection string; the token rules catch JWTs, long base64 and hex
# blobs; the last catches `password=...`, `api_key: ...` and their spellings.
_SCRUBS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"',;)]+"), REDACTION),
    # Resend's key shape, which is not long enough to be caught by the base64
    # rules and is not spelled `api_key=` by anything that raises it.
    (re.compile(RESEND_KEY_SHAPE), REDACTION),
    # The same reasoning for an S3 access key id, which arrives inside boto3's
    # message rather than as a header.
    (re.compile(AWS_KEY_SHAPE), REDACTION),
    (re.compile(r"\beyJ[A-Za-z0-9._-]{10,}"), REDACTION),
    (re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b"), REDACTION),
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), REDACTION),
    (
        # No plain `\b`: the shape that matters most is `aws_secret_access_key=`,
        # where `access_key` sits inside a word, so a word boundary never fires
        # and the value would sail through. `_` is allowed to precede it and a
        # letter or digit is not.
        re.compile(
            r"(?i)(?<![A-Za-z0-9])(pass(?:word|wd)?|secret|token|api[_-]?key|"
            r"access[_-]?key)\s*[=:]\s*[^\s,;)\"<]+"
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


def _allowed_for(inputs: dict[str, Any] | None, name: str | None) -> int | None:
    """The allowance the gate recorded for one input, when it recorded one."""
    entry = (inputs or {}).get(name) if name is not None else None
    if isinstance(entry, dict):
        value = entry.get("allowed_sessions_behind")
        if value is not None:
            return int(value)
    return None


def _allowance_suffix(allowed: int | None) -> str:
    """` (allowed 1)` beside a distance, or nothing when none was recorded."""
    return "" if allowed is None else f" (allowed {int(allowed)})"


def _worst_from_inputs(
    inputs: dict[str, Any] | None,
) -> tuple[str | None, int | None]:
    """The input furthest behind, from the gate's own inputs mapping.

    Used when the run passed, so no input failed and `worst_input` is unset: an
    allowance is only worth reading beside the distance sitting inside it, and
    that is precisely the case this names. An undated input outranks any count,
    matching the gate's own ordering.
    """
    ranked = [
        (str(name), entry.get("sessions_behind"))
        for name, entry in (inputs or {}).items()
        if isinstance(entry, dict)
    ]
    if not ranked:
        return None, None
    ranked.sort(key=lambda item: (item[1] is None, item[1] or 0), reverse=True)
    return ranked[0]


def _failure_list(
    failures: list[dict[str, Any]], inputs: dict[str, Any] | None = None
) -> str:
    parts = []
    for failure in failures:
        name = str(failure["input"])
        allowed = failure.get("allowed_sessions_behind")
        if allowed is None:
            allowed = _allowed_for(inputs, name)
        parts.append(
            f"{name} {_sessions(failure['sessions_behind'])}"
            f"{_allowance_suffix(None if allowed is None else int(allowed))}"
        )
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
    inputs: dict[str, Any] | None = None,
    detail: str = "",
    error_type: str | None = None,
    catch_up_sessions: list[str] | None = None,
    splits: list[str] | None = None,
    flags: list[dict[str, Any]] | None = None,
    store: str | None = None,
    snapshot: str | None = None,
    cross_checks_capped: str | None = None,
    no_price: list[str] | None = None,
    thin_adv: list[dict[str, Any]] | None = None,
    init: bool = False,
    establishment: bool = False,
    cost_label: str | None = "rebalance",
    cost_bps: float | None = None,
    cost_breakdown: dict[str, float] | None = None,
    brake_limit: float | None = None,
    positions_check: dict[str, Any] | None = None,
    deferred_reversals: list[dict[str, Any]] | None = None,
    skipped_minimum: list[dict[str, Any]] | None = None,
) -> str:
    """The fields, in order, ready for a preview.

    The first line names the store every write went to, or says why it could not
    be used. A wrong store is the one failure that looks healthy from the
    outside, so it is the first thing the owner reads.

    A first run says so on that first line and beside the status. The flag is
    removed after it, so a run that seeded the appendix is an event worth reading
    at a glance rather than a detail of the row.

    `inputs` is the gate's own inputs mapping. Each input's allowance is stated
    beside how far behind it is, so a non-zero distance inside its allowance
    (the universe, one session) does not read as a failure and a stale stop shows
    what was allowed rather than only what broke.
    """
    close = target_close or "unknown close"
    label = STATUS_LABELS.get(status, status)
    caught_up = len(catch_up_sessions or [])
    qualifiers = []
    if caught_up > 1:
        qualifiers.append(f"catch-up of {caught_up} sessions")
    if init:
        qualifiers.append("first run, the store was seeded")
    if qualifiers:
        label = f"{label} ({', '.join(qualifiers)})"
    store_line = store if store is not None else live_store.store_label()
    if init:
        store_line = f"{store_line}, first run"
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
    elif status == "market_closed":
        lines.append(
            "Orders: none. The exchange was shut, so there was no close to price "
            "and no book was built."
        )
    else:
        lines.append(
            "Orders: none. The run failed before sizing, so no book was priced."
        )

    if worst_input is None and inputs:
        # A run that passed still has inputs behind the close: the universe sits
        # inside its one-session allowance most evenings, and that allowance is
        # only readable beside the distance it applies to.
        worst_input, worst_sessions_behind = _worst_from_inputs(inputs)
    if worst_input is None:
        lines.append("Staleness: no input failed the check.")
    else:
        allowance = _allowed_for(inputs, worst_input)
        lines.append(
            f"Staleness: worst input {worst_input}, "
            f"{_sessions(worst_sessions_behind)}"
            f"{_allowance_suffix(allowance)}."
        )
    if status == "stale_stopped" and failures:
        lines.append(f"Failing inputs: {_failure_list(failures, inputs)}.")
    if status == "market_closed":
        reason = scrub(detail).strip()
        lines.append("Market: closed" + (f", {reason}" if reason else "") + ".")
    if no_price:
        # A member with no price leaves the book by construction, and a book quietly
        # smaller than the index is a book nobody can check, so the names are said
        # out loud rather than left to be noticed.
        lines.append(f"Dropped for no price: {', '.join(sorted(no_price))}.")
    if thin_adv:
        # The impact term is a function of each name's dollar volume, and a name
        # whose own ADV is missing or below $1M has that volume filled from the
        # panel's median. The cost is then partly a stand-in, and where it happens
        # is the difference between a number to read and a number to trust.
        lines.append(f"Liquidity: {_thin_adv_list(thin_adv)}")
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
    # The day's kind, in the owner's own terms. An establishment day creates the
    # book, so its ceiling is the book itself and the throughput brake is not yet
    # the instrument in force; from the second trading day it is. The cost label
    # travels with the number, because the proposal's cost is the cost of building
    # the book from flat and a rebalance cost would be a different number.
    if establishment:
        lines.append(
            "Establishment: the first trading day, so this run creates the book "
            "and may trade up to the full book"
            + (f" (${float(brake_limit):,.0f} of gross)" if brake_limit else "")
            + "; the daily brake starts on the second trading day."
        )
    elif brake_limit:
        lines.append(
            f"Day: rebalance. The absolute traded-notional brake of "
            f"${float(brake_limit):,.0f} applies, because the account already "
            "holds a book."
        )
    if cost_bps is not None:
        lines.append(_cost_line(float(cost_bps), cost_label, cost_breakdown))
    # The broker's book against the store's, every evening. A difference is the
    # one thing that makes every traded leg wrong in the same direction, so it is
    # stated even when the answer is "they match".
    if positions_check:
        lines.append(f"Positions: {positions_check.get('note', 'not read')}.")
    if deferred_reversals:
        # A target that reverses is closed tonight and opened tomorrow, in two
        # orders, because Alpaca refuses to cross zero in one. Naming the names
        # mid-reversal is what makes the shorter trade list read correctly.
        lines.append(
            "Reversals deferred: "
            + "; ".join(
                f"{item['ticker']} closed tonight, "
                f"{'short' if float(item['target_notional']) < 0 else 'long'} "
                f"{_money(abs(float(item['target_notional'])))} opens next evening"
                for item in deferred_reversals
            )
            + "."
        )
    if skipped_minimum:
        # A name in tonight's book that did not move: its target and its holding
        # differ by less than an order is worth, so nothing was sent for it. A book
        # quietly a few names short of its own target is a book nobody can check,
        # so the names and their sizes are stated rather than left to be inferred
        # from a shorter trade list.
        floor = _money(alpaca_mod.DELTA_MIN_NOTIONAL)
        lines.append(
            f"Under the {floor} minimum, left untraded: "
            f"{_skipped_minimum_list(skipped_minimum)}."
        )
    if status == "error":
        reason = scrub(detail).strip() or "no reason recorded"
        prefix = error_type or "Exception"
        # the caller's one-line reason usually carries the type already
        if reason.startswith(f"{prefix}:"):
            lines.append(f"Error: {reason}")
        else:
            lines.append(f"Error: {prefix}: {reason}")

    return "\n".join(lines)


def _cost_line(
    total_bps: float, cost_label: str | None, breakdown: dict[str, float] | None
) -> str:
    """The day's cost, and the four parts it is made of.

    A total on its own is one number to trust; the parts are four to check. They
    sum to the total by construction (`evening_job._cost_decomposition` adds
    exactly these four), so the message states them and, when they do not add up,
    says that too rather than presenting a broken total as a whole one. Borrow is
    the short leg's annual rate over one 21-session horizon, not a year.

    A day with no kind of its own (a closed day, which prices nothing and so has
    no cost line at all) has no label either; if a cost is ever stated beside one,
    it is stated as a cost rather than as a kind it does not have.
    """
    line = f"Cost: {cost_label or 'cost'}, {total_bps:.2f} bps of NAV"
    parts = [
        (name, breakdown[name])
        for name in ("spread", "impact", "commission", "borrow")
        if breakdown and breakdown.get(name) is not None
    ]
    if not parts:
        return line + "."
    stated = " + ".join(f"{name} {float(value):.2f}" for name, value in parts)
    line += f" ({stated})"
    if len(parts) == 4 and abs(sum(value for _, value in parts) - total_bps) > 0.05:
        # Above a hundredth of a basis point of rounding, the four are not the
        # total and the message must not read as if they were.
        parts_bps = sum(value for _, value in parts)
        line += f", which sum to {parts_bps:.2f}, not {total_bps:.2f}"
    return line + "."


def _skipped_minimum_list(rows: list[dict[str, Any]]) -> str:
    """The names the minimum left untraded, each with the size of its leg.

    The size is the point: "the change was $84" is a fact the reader can check
    against the minimum, where the name alone is not.
    """
    named = [
        f"{str(row.get('ticker'))} "
        f"{_money(abs(float(row.get('intended_notional') or 0.0)))}"
        for row in sorted(rows, key=lambda item: str(item.get("ticker")))
    ]
    count = len(named)
    shown = ", ".join(named[:MINIMUM_SKIP_NAMES])
    if count > MINIMUM_SKIP_NAMES:
        shown += f", and {count - MINIMUM_SKIP_NAMES} more"
    return f"{count} name(s) ({shown})"


def _thin_adv_list(rows: list[dict[str, Any]]) -> str:
    """The kept names whose own liquidity is unknown or thin, and its size.

    A name with no ADV at all is stated as such rather than as a zero: the median
    stood in for it, and the reader has to know which of the two happened.
    """
    named = []
    for row in sorted(rows, key=lambda item: str(item.get("ticker"))):
        ticker = str(row.get("ticker", "?"))
        value = row.get("adv_usd")
        named.append(
            f"{ticker} no ADV" if value is None else f"{ticker} ${float(value):,.0f}"
        )
    count = len(named)
    # Mirrors `costs.ADV_WINDOW`, which is the window the run priced the impact
    # with. Written here rather than imported because this module composes text
    # from what the run hands it and imports no model code.
    window = "63"
    return (
        f"{count} kept name(s) whose own trailing {window}-session dollar volume is "
        f"unknown or under $1M, so the panel median stands in: "
        + "; ".join(named)
        + "."
    )


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
    init: bool = False,
    inputs: dict[str, Any] | None = None,
) -> str:
    """The inbox line: the status, then what was proposed, then staleness.

    Readable without opening the email, which is the whole point of it, so it
    carries the three things the owner checks from a phone: `EFB ok 2026-09-25 |
    150 proposed, none sent | stale 1 (universe)`, `EFB STALE <close> | none
    proposed | stale 3 (prices)`, `EFB ERROR <close> | none proposed |
    <ExceptionType>`. A catch-up run says so beside the status, and a split or an
    unexplained move is appended rather than left for the body.

    `inputs` is the gate's own inputs mapping, and the staleness field names the
    same worst input the body does. Without it a clean run has no failures and so
    no worst input, and the field would read `stale unknown` on every evening the
    gate passed, including the clean ones: the universe sits inside its allowance
    most evenings, and the worst input on a clean run is that, not a mystery.
    """
    close = target_close or "unknown close"
    if status == "ok":
        word = "ok"
    elif status == "stale_stopped":
        word = "STALE"
    elif status == "market_closed":
        word = "CLOSED"
    else:
        word = "ERROR"
    caught_up = len(catch_up_sessions or [])
    qualifiers = []
    if caught_up > 1:
        qualifiers.append(f"catch-up {caught_up}")
    if init:
        qualifiers.append("first run")
    if qualifiers:
        word = f"{word} ({', '.join(qualifiers)})"
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
    elif status == "market_closed":
        tail = "market closed"
    else:
        if worst_input is None and inputs:
            # The same worst input the body names, so the two cannot disagree.
            worst_input, worst_sessions_behind = _worst_from_inputs(inputs)
        if worst_sessions_behind is None:
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


def _refusal_body(exc: Any) -> str:
    """What the endpoint said, from the JSON body it sent with the refusal.

    Resend answers a refused send with JSON carrying a `message`, and the status
    alone - "HTTP Error 403: Forbidden" - discards the one thing that says what to
    fix. The text is scrubbed: it leaves the process, and a key must never be in it.
    """
    try:
        raw = exc.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - a body is a bonus, never a failure itself
        return "no body"
    try:
        parsed = json.loads(raw)
    except ValueError:
        return scrub(raw)[:300]
    if isinstance(parsed, dict):
        for field in ("message", "error", "name"):
            if parsed.get(field):
                return scrub(str(parsed[field]))[:300]
    return scrub(raw)[:300]


def post(
    endpoint: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: float = TIMEOUT_SECONDS,
):
    """POST the payload. Raises on anything but a 2xx answer, with the reason."""
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            **(headers or {}),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if not 200 <= int(response.status) < 300:  # pragma: no cover - raises
                raise RuntimeError(f"the endpoint answered {int(response.status)}")
    except urllib.error.HTTPError as exc:
        # The refusal's own words, not just its number.
        raise RuntimeError(
            f"the endpoint answered {exc.code}: {_refusal_body(exc)}"
        ) from exc


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
        detail = scrub(f"{type(exc).__name__}: {exc}")[:400]
        # The one failure the owner cannot read off the row alone is the one where
        # the message never arrives, so the reason goes into the run log as well as
        # into `run_status`.
        logger.warning("the notification was not sent: %s", detail)
        return {"status": STATUS_FAILED, "detail": detail}
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
    inputs: dict[str, Any] | None = None,
    detail: str = "",
    error_type: str | None = None,
    catch_up_sessions: list[str] | None = None,
    splits: list[str] | None = None,
    flags: list[dict[str, Any]] | None = None,
    store: str | None = None,
    snapshot: str | None = None,
    cross_checks_capped: str | None = None,
    no_price: list[str] | None = None,
    thin_adv: list[dict[str, Any]] | None = None,
    init: bool = False,
    establishment: bool = False,
    cost_label: str | None = "rebalance",
    cost_bps: float | None = None,
    cost_breakdown: dict[str, float] | None = None,
    brake_limit: float | None = None,
    positions_check: dict[str, Any] | None = None,
    deferred_reversals: list[dict[str, Any]] | None = None,
    skipped_minimum: list[dict[str, Any]] | None = None,
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
        init=init,
        inputs=inputs,
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
        inputs=inputs,
        detail=detail,
        error_type=error_type,
        catch_up_sessions=catch_up_sessions,
        splits=splits,
        flags=flags,
        no_price=no_price,
        thin_adv=thin_adv,
        store=store,
        snapshot=snapshot,
        cross_checks_capped=cross_checks_capped,
        init=init,
        establishment=establishment,
        cost_label=cost_label,
        cost_bps=cost_bps,
        cost_breakdown=cost_breakdown,
        brake_limit=brake_limit,
        positions_check=positions_check,
        deferred_reversals=deferred_reversals,
        skipped_minimum=skipped_minimum,
    )
    result = send(subject_line, message, poster=poster)
    result["text"] = message
    result["subject"] = subject_line
    return result
