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
import traceback
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

# The floor a leg has to clear to be worth an order. The message names it beside
# the legs it left untraded, from the one definition the morning job applies.
from live import alpaca as alpaca_mod

# The three answers the broker's activity feed gives, read for the sentence that
# reports a position leaving the account with nothing explaining it.
from live import positions as positions_mod

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
# How many legs that did not fill are named before the line counts instead: the
# list is the evidence, and a capped list that does not say it is capped reads as
# the whole list.
UNFILLED_LINES = 6
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


def scrub_traceback(exc: BaseException) -> str:
    """The exception's whole traceback, formatted, then scrubbed.

    The traceback is kept rather than trimmed to one line: without the frames a
    failure in the pricing path and a failure in the notification path read the
    same, and the log's whole purpose during a live window is to say where. What
    it must not keep is a credential, and a credential reaches a traceback the way
    it reaches a message: in the exception's own text (`URLError: <urlopen error
    ... EFB_SUPABASE_DB_URL=postgresql://...>`), in the source line of a frame that
    was reading it, or in a chained cause raised while handling the first failure.

    So the formatting happens first and the scrub second, which is the one order
    in which every frame, every local-source line and every chained cause is
    present in the text being scrubbed. `traceback.format_exception` renders the
    chain (`__cause__` and `__context__`), so nothing is walked by hand here.
    """
    return scrub("".join(traceback.format_exception(exc)).rstrip())


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


def _miss_line(fills: dict[str, Any] | None) -> str | None:
    """`Did not fill: ...` for the legs the broker did not fill, or None.

    The misses are capped and counted rather than truncated: a line that shows
    six of nine legs reads as if three legs are fine. Shared by the evening's
    fills lines and the morning's own message, so the two cannot drift.

    The legs the evening could not send at all are named on the same line and
    after the broker's own misses. A leg whose ticker the broker's feed carries
    under no symbol never filled either, and it is the one of those the reader has
    to act on - the name cannot be traded until the ticker is right - so the line
    carries its derived reason, `symbol_not_found`, rather than dropping it.
    """
    if not fills:
        return None
    misses = [str(line) for line in (fills.get("unfilled") or [])]
    misses += [str(line) for line in (fills.get("not_sent_lines") or [])]
    if not misses:
        return None
    shown = "; ".join(misses[:UNFILLED_LINES])
    if len(misses) > UNFILLED_LINES:
        shown += f"; and {len(misses) - UNFILLED_LINES} more"
    return f"Did not fill: {shown}."


def _unread_line(fills: dict[str, Any] | None) -> str | None:
    """`Could not be read back: ...`, or None.

    An order the broker will not answer about is a question to answer, not a leg
    that did not happen, so it is stated apart from the misses.
    """
    if not fills:
        return None
    unread = [
        f"{item.get('ticker', '?')} ({item.get('error', 'unknown')})"
        for item in (fills.get("unread") or [])
    ]
    return f"Could not be read back: {', '.join(unread)}." if unread else None


def _shares(value: float) -> str:
    """A share count as a reader writes it: `326.07`, or `12` when it is whole."""
    number = float(value)
    return f"{number:,.0f}" if number.is_integer() else f"{number:,.2f}"


def _rename_line(renames: dict[str, str] | None) -> str | None:
    """`Renamed at the broker: PSKY now trades as SKYD.`, or None.

    A renamed company is the one thing in an evening's message that explains why a
    name the owner holds appears in neither the book nor the broker's: the loop
    sized PSKY and the order went out as SKYD. Saying it in the message is what
    keeps the rename from reading as a name that went missing.
    """
    pairs = sorted((renames or {}).items())
    if not pairs:
        return None
    return (
        "Renamed at the broker: "
        + "; ".join(f"{ticker} now trades as {symbol}" for ticker, symbol in pairs)
        + "."
    )


def _departure_line(exits: list[dict[str, Any]] | None, feed: str | None) -> str | None:
    """`PSKY: 326.07 shares ($3,212) left the account with no order or ...`, or None.

    The line the morning sends when a position walked out of the account and
    nothing the loop did explains it: no order of the evening's filled, and - when
    the broker's activity feed answered - no activity of the broker's names the
    name either. The shares are the previous read's own quantity and the dollars
    its market value, so the line says what was lost rather than only that
    something was.

    With the feed unread the sentence says *less*, not more: the departure is
    still reported, because a removal no order explains is worth a look either
    way, and the reader is told the second explanation was not checked rather than
    being told it came back empty.
    """
    if not exits:
        return None
    items = ", ".join(
        f"{item.get('ticker')}: {_shares(float(item.get('quantity') or 0.0))} "
        f"shares ({_money(abs(float(item.get('notional') or 0.0)))})"
        for item in exits
    )
    if feed == positions_mod.FEED_READ:
        return f"{items} left the account with no order or activity."
    return (
        f"{items} left the account with no closing order, and the broker's "
        "activity feed could not be read."
    )


def _fills_lines(fills: dict[str, Any] | None, cost_bps: float | None) -> list[str]:
    """The lines the fills reconciliation adds, or none when there is nothing to say.

    Three statements, in the order a reader asks them: which legs did not fill,
    which orders the broker would not answer about, and what the fills cost
    against the close beside the cost that was expected. A leg that filled says
    nothing here: the count of orders is on the evening's line, and this message
    is sent only when there is something the reader has to do something about.
    """
    if not fills:
        return []
    out: list[str] = []
    for line in (_miss_line(fills), _unread_line(fills)):
        if line is not None:
            out.append(line)
    realized = fills.get("realized_cost_bps")
    filled_of = f"({fills.get('n_filled')} of {fills.get('n_orders')} orders filled)"
    expected = fills.get("expected_cost_bps", cost_bps)
    against = (
        f" against {float(expected):.2f} bps expected" if expected is not None else ""
    )
    if realized is not None:
        out.append(
            f"Realized cost: {float(realized):.2f} bps of NAV{against} {filled_of}."
        )
    elif expected is not None:
        # There is nothing to price, so there is no realized cost. "0.00 bps" would
        # read as a trade that cost nothing rather than as a trade that did not
        # happen, and the expectation is still what the reader compares against.
        what = (
            "no fill to price"
            if not fills.get("n_filled")
            else "no fill could be priced"
        )
        out.append(f"Realized cost: {what}{against} {filled_of}.")
    return out


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
    spinoffs: list[str] | None = None,
    spinoff_missing: list[str] | None = None,
    spinoff_unusable: list[str] | None = None,
    spinoff_lookup_failed: str | None = None,
    flags: list[dict[str, Any]] | None = None,
    store: str | None = None,
    snapshot: str | None = None,
    page_book: str | None = None,
    fills: dict[str, Any] | None = None,
    cross_checks_capped: str | None = None,
    no_price: list[str] | None = None,
    no_risk: list[dict[str, Any]] | None = None,
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
    skipped_borrow: list[dict[str, Any]] | None = None,
    no_asset: list[dict[str, Any]] | None = None,
    renames: dict[str, str] | None = None,
    exits: dict[str, Any] | None = None,
    sent_notional: float | None = None,
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
                f"{_money(gross)} sized, none sent"
            )
        else:
            lines.append(
                f"Orders: {int(orders or 0)} orders sent, "
                f"{_sized_sent(gross, sent_notional)}"
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
    elif status == "incomplete":
        # An incomplete day is not a day that did not trade. The book was priced
        # and the legs went out; one of them was not confirmed. "Orders: none"
        # beside a booked day is the message's own false statement, and the owner
        # reading it would look for a failure before sizing that never happened.
        lines.append(
            f"Orders: {int(orders or 0)} orders sent, "
            f"{_sized_sent(gross, sent_notional)}, at least one leg not confirmed"
        )
    elif status == "error" and orders:
        # An error is not the same as an empty evening. On 2026-10-06 the evening
        # sent 192 orders and then died on a missing column, and this line said
        # "Orders: none. The run failed before sizing, so no book was priced" - the
        # one sentence an owner must never be told when it is not true. A failed run
        # that sent orders says how many, from its own leg records, and says not to
        # re-run the close, because the legs are at the broker and a re-run after the
        # open is a different book.
        lines.append(
            f"Orders: {int(orders)} orders sent for the close of {close}, "
            f"{_sized_sent(gross, sent_notional)}."
        )
        lines.append("The run failed after they were sent: do not re-run this close.")
    elif fills:
        # A morning message. The book was priced and its legs went out the evening
        # before, so "the run failed before sizing" is this message's own false
        # statement too: what such a morning failed at is the write that follows the
        # reconciliation, and the reason is on the Error line below.
        lines.append(
            f"Orders: none from this job. The {int(orders or 0)} order(s) for the "
            f"close of {close} went out last evening."
        )
    else:
        lines.append(
            "Orders: none. The run failed before sizing, so no book was priced."
        )
    if status == "incomplete" and scrub(detail).strip():
        # Which leg and why: the count alone leaves the owner to open the store to
        # find out what to do about it, and the detail the run recorded already
        # says it.
        lines.append(f"{scrub(detail).strip().rstrip('.')}.")
    renamed = _rename_line(renames)
    if renamed:
        # A rename explains two names at once: the one the owner holds and the one
        # the order went out under. Said here, above everything else about the
        # book, because it is the answer to "where did PSKY go".
        lines.append(renamed)

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
    if no_risk:
        # The same statement about the same book, from the other end: these are the
        # names the risk model cannot measure, so they never reached the sizing.
        # Until 2026-10-08 they were sized on the cross-sectional median instead -
        # Q on EQT's own variance - and the run died storing the result. The names
        # are said out loud for the reason the line above gives.
        lines.append(
            f"Dropped for no risk estimate: {_no_risk_names(no_risk)} "
            "(out of the book before sizing)."
        )
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
    if page_book:
        # The list on the page is the one thing there that is not a number out of
        # the manifest, so it is the one thing that can go missing while every
        # number around it still reads right. The writer reads the object back
        # and this is where it says so out loud.
        lines.append(f"Page book: {page_book}.")
    for line in _fills_lines(fills, cost_bps):
        lines.append(line)
    if splits:
        lines.append(f"Corporate actions: {', '.join(splits)}.")
    if spinoffs:
        # A spin-off changes the book without a decision: the parent keeps trading
        # and the account is handed the child, so the next evening's delta has one
        # more name to close than the proposal has. Named here for the same reason
        # a split is.
        lines.append(f"Spin-offs: {', '.join(spinoffs)}.")
    if spinoff_missing:
        # The one cell the rule could not correct was nulled rather than left as a
        # print that is not a return, and that is a hole in the panel tonight: the
        # owner has to know which name, or the next surprising number has no
        # explanation.
        lines.append(
            "Spin-off close missing, so the parent's return was nulled: "
            f"{', '.join(spinoff_missing)}."
        )
    if spinoff_unusable:
        # The same hole for the other reason: the vendor's own record had no ratio
        # the rule could apply. Named with the reason, because "we could not use the
        # record" is not something the owner can take back to the vendor, and named
        # at all because the cell is null in a panel they will read tomorrow.
        lines.append(
            "Spin-off record unusable, so the parent's return was nulled: "
            f"{', '.join(spinoff_unusable)}."
        )
    if spinoff_lookup_failed:
        # The read behind every spin-off number failed, so no spin-off was applied
        # and the session's large moves are the raw prints the 40% flag names. The
        # run goes on either way, and this is the line that stops the run reading as
        # a clean evening: nobody else is looking for that session.
        lines.append(spinoff_lookup_failed.strip().rstrip(".") + ".")
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
    if skipped_borrow:
        # The short legs the borrow refused. The run called them skipped, so it did
        # not fail and the day is complete; that is exactly why the names have to
        # be here, because nothing else in the message would say that tonight's
        # book is a short leg short of its own target.
        lines.append(
            f"Not easy to borrow, so not opened: "
            f"{_borrow_skip_list(skipped_borrow)}."
        )
    if no_asset:
        # A ticker the broker's feed carries under no symbol under any spelling.
        # The leg is skipped rather than sent, because an order under a symbol the
        # broker does not have is refused every evening and buys nothing; and it is
        # named rather than only skipped, because the book is then one name short of
        # its own target and nothing else in the message would say so.
        lines.append(f"No broker asset, so not sent: {_no_asset_list(no_asset)}.")
    if exits and exits.get("exits"):
        # A position that left the account with nothing of the loop's to explain
        # it. The same sentence the morning sends, from the same read, because the
        # two runs see the same departure one day apart and a line that only one of
        # them printed would read as two different events.
        departure = _departure_line(exits.get("exits"), exits.get("feed"))
        if departure:
            lines.append(departure)
    if status == "error":
        reason = scrub(detail).strip() or "no reason recorded"
        # The body's order line above is written for a run that failed *before*
        # sizing, and on 2026-10-06 the evening failed after it: 192 orders went out
        # and the message said "Orders: none. The run failed before sizing", which is
        # the one thing an owner must never be told when it is not true. A run that
        # sent orders says so, from its own leg records, and the failure follows.

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


def _sized_sent(sized: float | None, sent: float | None) -> str:
    """`$429,218 sent of $433,480 sized`, or the sized figure alone.

    The evening used to call one number `gross`, and that one number counted every
    leg it sized, including the legs under the minimum that were never sent: the
    reader compared it against the morning's filled dollars and saw two emails
    disagreeing about the same trade. Two figures that name themselves cannot be
    read as the wrong one, and the difference between them is exactly the turnover
    that never happened.

    A caller with no sent figure keeps the old wording rather than being handed a
    zero: nothing measured is not nothing sent.
    """
    if sent is None:
        return f"{_money(sized)} gross"
    return f"{_money(sent)} sent of {_money(sized)} sized"


def _no_asset_list(rows: list[dict[str, Any]]) -> str:
    """The legs no order could be sent for, each with the size of its leg.

    A ticker the broker's feed carries under no symbol is not a name the run may
    trade under a guess, so the leg is skipped and named here. The size is what
    makes the line checkable against the book's own target for the name, the same
    way the borrow line is.
    """
    named = [
        f"{str(row.get('ticker'))} "
        f"{_money(abs(float(row.get('intended_notional') or 0.0)))}"
        for row in sorted(rows, key=lambda item: str(item.get("ticker")))
    ]
    return ", ".join(named)


def _borrow_skip_list(rows: list[dict[str, Any]]) -> str:
    """The shorts the borrow refused, each with the size of the leg it was.

    The size is what makes the line checkable: the reader knows the book's target
    for that name and can see how much of it went unopened. The broker's own
    sentence travels with the name when it is there, because "not easy to borrow"
    and "not shortable" are two different things to go and look at.
    """
    named = [
        f"{str(row.get('ticker'))} "
        f"{_money(abs(float(row.get('intended_notional') or 0.0)))}"
        + (f" ({str(row.get('reason'))})" if row.get("reason") else "")
        for row in sorted(rows, key=lambda item: str(item.get("ticker")))
    ]
    count = len(named)
    shown = "; ".join(named[:MINIMUM_SKIP_NAMES])
    if count > MINIMUM_SKIP_NAMES:
        shown += f"; and {count - MINIMUM_SKIP_NAMES} more"
    return shown


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


def _no_risk_names(rows: list[dict[str, Any]]) -> str:
    """The names the risk model cannot measure, as one comma-separated list.

    The reason travels in the manifest rather than in the line: tonight's reasons
    are almost always the same one, and a line that repeats it three times is
    harder to read than the three names beside it. The page and the store carry
    the reason per name for the reader who needs it.
    """
    names = sorted(str(row.get("ticker", "?")) for row in rows)
    return ", ".join(names)


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
    elif orders:
        # An error is not the same as an empty evening. The orders a failed run sent
        # are counted on the inbox line, because "none proposed" beside 192 sent
        # orders is the line that decides whether the owner looks.
        middle = f"{int(orders)} sent"
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


def _miss_phrase(fills: dict[str, Any] | None) -> str:
    """The leg(s) that did not fill, by the broker's own word: `2 rejected`.

    The morning subject's third field. The counts are by status rather than one
    "did not fill" number, because a cancellation is a working order the broker
    took back and a rejection is an order that never worked, and the owner reads
    the subject from a phone to decide whether to open the message. `nothing
    missed` when every leg filled, which is what a morning that only had a page
    write to report sends.
    """
    counts = (fills or {}).get("miss_statuses") or {}
    if isinstance(counts, dict) and counts:
        parts = [
            f"{int(count)} {str(word).lower().replace('_', ' ')}"
            for word, count in sorted(
                counts.items(), key=lambda item: (-int(item[1]), str(item[0]))
            )
        ]
        return ", ".join(parts)
    missed = int((fills or {}).get("n_unfilled") or 0)
    return "nothing missed" if not missed else f"{missed} did not fill"


def fills_subject(
    *, target_close: str | None, fills: dict[str, Any] | None, failed: bool = False
) -> str:
    """The morning's inbox line: what the last evening's orders did.

    Three fields, readable without opening the email, which is why it does not
    reuse the evening's subject: `EFB fills 2026-10-05 | 197 of 199 filled | 2
    rejected`. The denominator is the legs the evening **sent**, not every leg it
    sized - the legs under the minimum that were never sent are not orders the
    broker could have filled - and the last field names the misses by the broker's
    own status word. The evening's subject is about the evening (`EFB ok ... | 199
    sent | stale 0`); this one is about the trade, and neither can be read as the
    other.

    `failed` says the morning never got to a count at all, which is not the same
    statement as a count of zero: on 2026-10-07 the reconciliation died writing
    `efb.fills` and the subject `0 of 0 filled | nothing missed` would have read as
    a morning whose orders all filled. The two count fields are replaced rather
    than filled in, and the close is still the first name in the line.
    """
    if failed:
        return f"EFB fills {target_close or 'unknown close'} | not reconciled | ERROR"
    data = fills or {}
    filled = int(data.get("n_filled") or 0)
    sent = int(data.get("n_orders") or 0)
    return (
        f"EFB fills {target_close or 'unknown close'} | {filled} of {sent} "
        f"filled | {_miss_phrase(fills)}"
    )


def fills_message(
    *,
    target_close: str | None,
    fills: dict[str, Any] | None,
    status: str = "ok",
    store: str | None = None,
    snapshot: str | None = None,
    detail: str = "",
    sent_notional: float | None = None,
    unsent_notional: float | None = None,
    filled_notional: float | None = None,
    exits: dict[str, Any] | None = None,
    failed: bool = False,
) -> str:
    """The morning's own body: the trade the evening's orders did, and nothing else.

    Two of the evening's lines are deliberately absent. There is no staleness
    line, because this job reads no model input and the field would be a number
    about a different run; and there is no "the run completed", because the
    evening is the run and this morning only reports it.

    The notional is labelled, not fixed: `$425,740 filled of $429,218 sent` is two
    different numbers, and the evening's own `$433,480 gross` is a third - every
    leg it sized, including the legs under the $250 minimum that were never sent.
    Calling any of the three `gross` without saying which is what made the two
    emails look like they disagreed about the same trade.
    """
    data = fills or {}
    close = target_close or "unknown close"
    lines = [f"store: {store if store is not None else live_store.store_label()}"]
    if failed:
        # No count exists, so none is printed. "0 of 0 order(s) filled" is what a
        # crash would have said, and it is the one reading that is wrong. Everything
        # below it is a measurement this morning never took - the misses, the cost,
        # the departures - so the error is the whole of what the body can honestly
        # say, and it is said below.
        lines.append(f"EFB fills {close}: not reconciled")
    else:
        lines.append(
            f"EFB fills {close}: {int(data.get('n_filled') or 0)} of "
            f"{int(data.get('n_orders') or 0)} order(s) filled"
        )
        if filled_notional is not None or sent_notional is not None:
            notional = (
                f"Notional: {_money(filled_notional)} filled of "
                f"{_money(sent_notional)} sent"
            )
            not_sent = int(data.get("not_sent") or 0)
            if not_sent:
                notional += (
                    f"; {_money(unsent_notional)} in {not_sent} leg(s) under the "
                    f"{_money(alpaca_mod.DELTA_MIN_NOTIONAL)} minimum were never "
                    "sent"
                )
            lines.append(notional + ".")
        for detail_line in (_miss_line(data), _unread_line(data)):
            if detail_line is not None:
                lines.append(detail_line)
        if exits:
            # A position that left the account with nothing of the loop's to explain
            # it. It is on this message rather than only on the page because the page
            # can be read at leisure and this cannot: a position that vanished
            # overnight is the one thing here that nobody can reconstruct afterwards.
            line = _departure_line(exits.get("exits"), exits.get("feed"))
            if line:
                lines.append(line)
        realized = data.get("realized_cost_bps")
        expected = data.get("expected_cost_bps")
        against = (
            f" against {float(expected):.2f} bps expected"
            if expected is not None
            else ""
        )
        if realized is not None:
            lines.append(f"Realized cost: {float(realized):.2f} bps of NAV{against}.")
        elif expected is not None:
            # Nothing to price, so there is no realized cost. "0.00 bps" would read
            # as a trade that cost nothing rather than one that did not happen.
            lines.append(f"Realized cost: no fill could be priced{against}.")
        if snapshot:
            lines.append(f"Snapshot: {snapshot}.")
    if status != "ok":
        # The morning can fail its page write and still have reconciled the legs:
        # the error is what did not happen, and it is stated last so the trade
        # above is read first.
        reason = scrub(detail).strip() or "no reason recorded"
        lines.append(f"Error: {reason}")
    return "\n".join(lines)


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


def notify_refusal(reason: str, *, poster: Callable[..., Any] | None = None) -> dict:
    """The one-line message a refused run sends.

    A run outside the trading window does no work and records nothing, because it
    is not a run: the day is still owed its evening. That leaves the message as the
    only place the owner can learn the evening was refused, so the body is the
    refusal and its reason and nothing else. No store line, no status line: there
    is one thing to say, and padding it with the usual fields would make it read
    like a run that happened.
    """
    from live import staleness

    subject = (
        f"EFB refused | outside the "
        f"{staleness.WINDOW_START_HOUR_ET:02d}:00-"
        f"{staleness.WINDOW_END_HOUR_ET:02d}:00 New York window"
    )
    return send(subject, f"EFB live book: refused, {scrub(reason)}.", poster=poster)


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
    spinoffs: list[str] | None = None,
    spinoff_missing: list[str] | None = None,
    spinoff_unusable: list[str] | None = None,
    spinoff_lookup_failed: str | None = None,
    flags: list[dict[str, Any]] | None = None,
    store: str | None = None,
    snapshot: str | None = None,
    page_book: str | None = None,
    fills: dict[str, Any] | None = None,
    cross_checks_capped: str | None = None,
    no_price: list[str] | None = None,
    no_risk: list[dict[str, Any]] | None = None,
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
    skipped_borrow: list[dict[str, Any]] | None = None,
    no_asset: list[dict[str, Any]] | None = None,
    renames: dict[str, str] | None = None,
    exits: dict[str, Any] | None = None,
    sent_notional: float | None = None,
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
        spinoffs=spinoffs,
        spinoff_missing=spinoff_missing,
        spinoff_unusable=spinoff_unusable,
        spinoff_lookup_failed=spinoff_lookup_failed,
        flags=flags,
        no_price=no_price,
        no_risk=no_risk,
        thin_adv=thin_adv,
        store=store,
        snapshot=snapshot,
        page_book=page_book,
        fills=fills,
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
        skipped_borrow=skipped_borrow,
        no_asset=no_asset,
        renames=renames,
        exits=exits,
        sent_notional=sent_notional,
    )
    result = send(subject_line, message, poster=poster)
    result["text"] = message
    result["subject"] = subject_line
    return result


def notify_fills(
    *,
    target_close: str | None,
    fills: dict[str, Any] | None,
    status: str = "ok",
    store: str | None = None,
    snapshot: str | None = None,
    detail: str = "",
    sent_notional: float | None = None,
    unsent_notional: float | None = None,
    filled_notional: float | None = None,
    exits: dict[str, Any] | None = None,
    failed: bool = False,
    poster: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Compose and deliver the morning's message, returning both parts.

    Its own subject and body rather than the evening's composer with a flag: the
    two messages answer different questions, and a field-by-field reuse would
    drag the evening's staleness, cost and establishment lines into a morning
    that has none of them.

    `failed` is the morning that crashed before it had anything to report, which is
    the one case this job used to leave the owner with silence. It suppresses the
    counts - there are none - and states the error instead.
    """
    if failed:
        # The ERROR field is the whole subject's third field rather than an appended
        # one, so the line does not read as a count that was reported.
        subject_line = fills_subject(
            target_close=target_close, fills=fills, failed=True
        )
    else:
        subject_line = fills_subject(target_close=target_close, fills=fills)
    if status != "ok" and not failed:
        # The status word is appended rather than made the first field: the count
        # that filled is still what the owner reads first, and a message that
        # begins "ERROR" reads as a morning on which nothing traded.
        subject_line = f"{subject_line} | {status.upper()}"
    message = fills_message(
        target_close=target_close,
        fills=fills,
        status=status,
        store=store,
        snapshot=snapshot,
        detail=detail,
        sent_notional=sent_notional,
        unsent_notional=unsent_notional,
        filled_notional=filled_notional,
        exits=exits,
        failed=failed,
    )
    result = send(subject_line, message, poster=poster)
    result["text"] = message
    result["subject"] = subject_line
    return result
