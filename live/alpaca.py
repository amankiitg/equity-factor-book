"""Sprint E11: the Alpaca paper execution layer.

Reuses the credit-trading-lab pattern: a `TradingClient` pointed at the
paper endpoint, notional market orders, fills captured and marked. The
credentials come from `EFB_ALPACA_PAPER_API_KEY` and
`EFB_ALPACA_PAPER_SECRET_KEY`, distinct from credit-trading-lab's names
so the two books cannot be crossed by a stale shell. Dry run is the
default: no key is read and no order leaves the process.

Account decision, resolved from Alpaca's own dashboard documentation:
the existing login supports several paper accounts ("Open New Paper
Account" in the account selector). EFB therefore uses a **separate paper
account under the existing login**, with its own API keys, so its
positions, cash, NAV and fill history are disjoint from
credit-trading-lab's without a second login.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import UTC
from typing import Any

import pandas as pd

# `APIError` is what tells an evaluated-and-declined order apart from a transport
# failure, and alpaca-py is an optional dependency, so the import is guarded: a
# missing library must not break module import, only the live path that needs it.
# Bound to an `Any`-typed name so the fallback needs no ignore of its own.
API_ERROR_CLS: Any
try:  # pragma: no cover - depends on the environment
    from alpaca.common.exceptions import (
        APIError as API_ERROR_CLS,  # type: ignore[import-not-found]
    )
except ImportError:  # pragma: no cover - alpaca-py is optional
    API_ERROR_CLS = None

logger = logging.getLogger(__name__)

PAPER_ENDPOINT = "https://paper-api.alpaca.markets"
# The effective REST base is PAPER_ENDPOINT/v2; alpaca-py appends the version
# itself, so url_override carries the base without the /v2 suffix.
DRY_RUN_DEFAULT = True
DELTA_MIN_NOTIONAL = 250.0

# Alpaca's own position intents, spelled exactly as its API takes them. Every
# order carries one, because the same side can mean open or close and the broker
# needs to be told which: a sell on a held long is a close, a sell on nothing is
# an open short, and they carry different margin, borrow and reporting treatment.
INTENT_BUY_TO_OPEN = "buy_to_open"
INTENT_BUY_TO_CLOSE = "buy_to_close"
INTENT_SELL_TO_OPEN = "sell_to_open"
INTENT_SELL_TO_CLOSE = "sell_to_close"


def position_intent(held: float, target: float) -> str:
    """The position intent for a leg from `held` to `target`, both signed dollars.

    A long increase opens long; a long decrease or a close sells to close; a new
    or larger short opens short; a short cover buys to close. A reversal never
    reaches here with both signs set, because it is split into a close tonight and
    an open the next evening, so the two sides never meet in one order.

    Returns an empty string when the leg does not move, which is not an order.
    """
    if held >= 0 and target > held:
        return INTENT_BUY_TO_OPEN
    if held > 0 and target < held:
        # A decrease and a full close are the same intent; only the size differs.
        return INTENT_SELL_TO_CLOSE
    if held <= 0 and target < held:
        return INTENT_SELL_TO_OPEN
    if held < 0 and target > held:
        return INTENT_BUY_TO_CLOSE
    return ""


# The time-in-force every order carries. `day`, not `opg`, and the reason is the
# cron's own hour.
#
# The evening cron fires at 22:30 UTC (render.yaml, `efb-live-daily`'s
# "30 15,22 * * 1-5"), which is 18:30 ET
# in summer and 17:30 ET in winter: after the 16:00 ET close and inside the
# 16:00-20:00 ET after-hours window. Alpaca's Time in Force table
# (https://docs.alpaca.markets/docs/orders-at-alpaca#time-in-force) says of `opg`:
# "OPG orders submitted after 9:28am but before 7:00pm ET will be rejected. OPG
# orders submitted after 7:00pm will be queued and routed to the following day's
# opening auction." Both spellings of the cron's slot fall inside the rejected
# window, so `opg` would be refused every evening. `cls` is the mirror image and
# is "rejected" between 3:50pm and 7:00pm ET.
#
# `day` is accepted at that hour and lands on the next session: "A day order is
# eligible for execution only on the day it is live. ... If submitted after the
# close, it is queued and submitted the following trading day." Under "Orders
# Submitted Outside of Eligible Trading Hours" the same page adds that an order
# not eligible for extended hours submitted after 4:00pm ET "will be queued up
# for release the next trading day", and a released market order fills in that
# session's opening auction, which is the next-open execution the loop wants: the
# proposal priced on Tuesday's close is executed at Wednesday's open.
#
# It is also the only TIF a notional order may carry. The Create Order schema
# says of `notional`: "dollar amount to trade. Cannot work with `qty`. Can only
# work for market order types and day for time in force."
#
# The smoke test that proves this against the real paper account is
# `scripts/smoke_order_timing.py`, and it refuses to run outside the cron's own
# window because the hour is the point.
NEXT_OPEN_TIF = "day"


@dataclass(frozen=True)
class Fill:
    """One submitted order and what came back.

    `reason_code` is set on every leg that never became a submitted order, and it
    is the durable record of that intent: Alpaca does not persist a submit-time
    rejection as an order record, so the code and its detail are the only evidence
    the leg was ever intended. See the reason-code block below.
    """

    ticker: str
    order_id: str
    intended_notional: float
    filled_notional: float
    fill_price: float
    status: str
    reason_code: str = ""
    detail: str = ""
    # The Alpaca position intent the leg carried, so the log says open vs close.
    intent: str = ""
    # The id the leg was sent with, so the row can be tied to the broker's own
    # order without a second lookup, and a rerun's rejection can be traced to the
    # id it collided with.
    client_order_id: str = ""
    # True when the broker already held an order under this leg's id and the run
    # resolved that order instead of submitting a second copy.
    resolved: bool = False


# ---------------------------------------------------------------- rate limiting
#
# Alpaca's trading API allows 200 requests per minute. This loop reads an asset
# per short open and then submits, so the submissions are spaced rather than the
# requests counted: a shared token bucket would need every caller to share a
# clock, and the interval is one number that is easy to read and to test. 0.35 s
# between submissions is about 171 a minute, which leaves room for the reads.
RATE_LIMIT_PER_MINUTE = 200
MIN_SUBMIT_INTERVAL_SECS = float(os.environ.get("EFB_MIN_SUBMIT_INTERVAL_SECS", "0.35"))


def client_order_id(close: Any, ticker: str, side: str, *, prefix: str = "efb") -> str:
    """A deterministic id for one leg, from the three things that define it.

    Alpaca requires `client_order_id` to be unique per account and refuses a
    repeat, so a rerun of the same evening cannot double-submit: the second
    attempt is rejected by the broker rather than sent. The id is recomputed from
    the proposal rather than stored, so it survives a wiped container and does not
    depend on the loop remembering anything.

    `prefix` keeps a different tool's ids from ever colliding with the book's: a
    smoke order sent under `efb-smoke` can never be mistaken for, or block, a real
    leg, even on the same close and ticker.
    """
    stamp = pd.Timestamp(close).date().isoformat() if close else "unknown"
    digest = hashlib.sha256(f"{stamp}|{ticker}|{side}".encode()).hexdigest()[:12]
    return f"{prefix}-{stamp}-{ticker}-{str(side)[:1].upper()}-{digest}"[:128]


class Throttle:
    """A minimum interval between submissions.

    `clock` and `sleep` are injectable so a test can prove the waiting happened
    without waiting for it, which is the only way to test a sleep.
    """

    def __init__(
        self,
        interval: float = MIN_SUBMIT_INTERVAL_SECS,
        clock: Any = time.monotonic,
        sleep: Any = time.sleep,
    ) -> None:
        self.interval = float(interval)
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> float:
        """Sleep if the last submission was recent, and return the slept time."""
        if self.interval <= 0:
            return 0.0
        now = self._clock()
        slept = 0.0
        if self._last is not None:
            remaining = self.interval - (now - self._last)
            if remaining > 0:
                self._sleep(remaining)
                slept = remaining
                now += remaining
        self._last = now
        return slept


# ---------------------------------------------------------------- reason codes
#
# Every leg that does not become a submitted order carries one of these. They are
# the audit trail, not decoration: Alpaca does not persist a submit-time rejection
# as an order record at all (credit-trading-lab v9.2 established this on
# 2026-09-24, after a rejected sell_to_open left no trace in the order history over
# a 30 day window), so the code and its detail are the only durable evidence that
# the leg was ever intended.
#
# The vocabulary and the policy are v9.2's. Order-level failures continue and log,
# because the broker evaluated the order and declined it: the state is known, and
# the rest of the book should still trade. A transport-class failure halts
# submission, because Alpaca may or may not have received the order and continuing
# would stack ambiguity on ambiguity.
REASON_ALPACA_ERROR = "ALPACA_API_ERROR"
REASON_SUBMIT_UNKNOWN = "SUBMIT_EXCEPTION_UNKNOWN_STATE"
REASON_SKIPPED_AFTER_HALT = "SKIPPED_AFTER_HALT"
REASON_QTY_ROUNDS_TO_ZERO = "QTY_ROUNDS_TO_ZERO"
# A short cover whose notional is worth less than one whole share. The run sized
# the cover, the floor to whole shares left nothing to send, and the short stays
# that much bigger than its target until the next evening. It is recorded like the
# minimum-notional skip - a leg with its reason, and not a failure of the run -
# because the alternative is a fractional cover whose rounding is the broker's.
REASON_COVER_UNDER_ONE_SHARE = "COVER_UNDER_ONE_SHARE"
# A leg whose change is smaller than an order is worth. The run chose not to send
# it, which is not a failure: it is recorded with this code and named in the
# email, and it does not make the run incomplete.
REASON_BELOW_MIN_NOTIONAL = "BELOW_MIN_NOTIONAL"
REASON_SHORT_CHECK_FAILED = "SHORTABLE_CHECK_FAILED"
REASON_NOT_TRADABLE = "ASSET_NOT_TRADABLE"
REASON_NOT_SHORTABLE = "ASSET_NOT_SHORTABLE"
REASON_NOT_EASY_TO_BORROW = "ASSET_NOT_EASY_TO_BORROW"
# A close whose size cannot be computed: no price and no broker quantity to take
# the whole position from. Guessing is worse than not sending.
REASON_CLOSE_QTY_UNKNOWN = "CLOSE_QUANTITY_UNKNOWN"

# The status a leg carries when it was never submitted. The code beside it says
# why, and the two are kept separate so a reader can group by either.
SKIPPED = "SKIPPED"


def classify_submit_failure(exc: Exception) -> tuple[str, bool]:
    """(reason_code, halts_run) for a submit that raised.

    An `APIError` means the broker evaluated the order and declined it, so the
    state is known, the leg is recorded and the book keeps trading. Anything else
    is transport-class: the order may have arrived, so submission halts and the
    remaining legs are recorded as not attempted.
    """
    if API_ERROR_CLS is not None and isinstance(exc, API_ERROR_CLS):
        return REASON_ALPACA_ERROR, False
    return REASON_SUBMIT_UNKNOWN, True


def asset_flags(
    client, symbol: str, cache: dict[str, dict[str, bool]] | None = None
) -> dict[str, bool]:
    """The broker's own flags for one symbol, read live once per run.

    Shortability is not static: the same name filled sell_to_open on three
    September days and reported `shortable=false` on the fourth (v9.2,
    2026-09-24), so a cached or hardcoded list would have been wrong. The cache
    here is per run and never persisted across runs.
    """
    held = {} if cache is None else cache
    key = str(symbol)
    if key not in held:
        asset = client.get_asset(key)
        held[key] = {
            "tradable": bool(getattr(asset, "tradable", False)),
            "shortable": bool(getattr(asset, "shortable", False)),
            "easy_to_borrow": bool(getattr(asset, "easy_to_borrow", False)),
        }
    return held[key]


def short_refusal(
    client, ticker: str, cache: dict[str, dict[str, bool]] | None = None
) -> tuple[str, str] | None:
    """Why a short leg may not be submitted, or None when it may.

    Both flags are checked, in the order tradable, shortable, easy_to_borrow, so
    the reason code names the first thing that was actually wrong rather than a
    convenient one. A check that itself fails is a refusal too, and says why: a
    short that could not be verified is not a short that may be sent.
    """
    try:
        flags = asset_flags(client, ticker, cache)
    except Exception as exc:  # noqa: BLE001 - a failed check is a refusal
        return REASON_SHORT_CHECK_FAILED, f"{type(exc).__name__}: {exc}"
    if not flags["tradable"]:
        return REASON_NOT_TRADABLE, f"{ticker} reports tradable=false"
    if not flags["shortable"]:
        return REASON_NOT_SHORTABLE, f"{ticker} reports shortable=false"
    if not flags["easy_to_borrow"]:
        return REASON_NOT_EASY_TO_BORROW, f"{ticker} reports easy_to_borrow=false"
    return None


def _skipped(
    ticker: str, notional: float, code: str, detail: str, intent: str = ""
) -> Fill:
    """A leg that was never submitted, with the code that says why."""
    return Fill(
        ticker=ticker,
        order_id="",
        intended_notional=notional,
        filled_notional=0.0,
        fill_price=0.0,
        status=SKIPPED,
        reason_code=code,
        detail=detail,
        intent=intent,
    )


def connect(dry_run: bool = DRY_RUN_DEFAULT):
    """The Alpaca paper client, or None in dry run.

    The live path reads paper keys from the environment, never from a
    file and never from the repo. `alpaca-py` is an optional dependency;
    a clear error names it when it is missing.
    """
    if dry_run:
        return None
    key = os.environ.get("EFB_ALPACA_PAPER_API_KEY")
    secret = os.environ.get("EFB_ALPACA_PAPER_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError(
            "Alpaca paper keys are required outside dry run and are read "
            "from EFB_ALPACA_PAPER_API_KEY and EFB_ALPACA_PAPER_SECRET_KEY only"
        )
    try:
        from alpaca.trading.client import TradingClient
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError(
            "the live Alpaca path needs alpaca-py; install it or run dry"
        ) from exc
    return TradingClient(
        api_key=key,
        secret_key=secret,
        paper=True,
        url_override=PAPER_ENDPOINT,
    )


def get_buying_power(client) -> float:
    """The account's available buying power, or a raised failure.

    No fallback, for the same reason `get_nav` has none: a read that silently
    restored a design default would report healthy while blind.
    """
    value = float(client.get_account().buying_power)
    if not math.isfinite(value) or value < 0:
        raise RuntimeError(f"invalid buying power: {value}")
    return value


def check_buying_power(client, orders) -> float:
    """Raise unless the run's traded notional fits inside available buying power.

    Alpaca applies a buying-power check to longs and to short sells alike and
    reduces available buying power by every open order, so a book that does not
    fit is rejected leg by leg and the run ends half-built. The check is on the
    whole run before any submission, and the bound is the traded notional, the
    same number the brake uses. A failure raises and no order is sent.
    """
    buying_power = get_buying_power(client)
    required = float(sum(abs(order.traded_notional) for order in orders))
    if required > buying_power:
        raise RuntimeError(
            f"the run needs {required:,.0f} of traded notional and the account "
            f"has {buying_power:,.0f} of buying power, so no order was sent"
        )
    return buying_power


def read_client():
    """A paper client for reading the account, or None without keys.

    Reading is free and read-only, so the evening reads the account even in dry
    run: `connect(dry_run=True)` returns None because it guards *submission*, and
    the question "what does the broker hold" has a real answer before the flip.
    No keys is not an error here; it is a question that could not be asked, and
    the caller says so rather than pretending the account is empty.
    """
    key = os.environ.get("EFB_ALPACA_PAPER_API_KEY", "").strip()
    secret = os.environ.get("EFB_ALPACA_PAPER_SECRET_KEY", "").strip()
    if not key or not secret:
        return None
    return connect(dry_run=False)


def get_nav(client) -> float:
    """The live account equity, or a raised failure.

    There is no fallback. Both guards are fractions of NAV, so a read that
    silently restored the design default would report healthy while blind,
    which is worse than no guard. A failed or invalid read raises and the
    run fails with no orders.
    """
    equity = float(client.get_account().equity)
    if not math.isfinite(equity) or equity <= 0:
        raise RuntimeError(f"invalid live account equity: {equity}")
    return equity


class AccountMismatch(RuntimeError):
    """The keys reach an account other than the one the owner named."""


# The account the keys are supposed to reach, as the owner reads it off Alpaca's
# dashboard: the `account_number` (the PA... value), not the internal `id`, which
# no dashboard shows and nobody can check by eye.
ACCOUNT_ID_ENV = "EFB_ALPACA_ACCOUNT_ID"


def account_number(account: Any) -> str:
    """The account's public number, the PA... value Alpaca shows.

    Alpaca calls this `account_number` and it is the identifier a human can read
    back from the dashboard. The internal `id` is a UUID, so a guard written on it
    could not be checked by the owner even though it would pass.
    """
    return str(getattr(account, "account_number", "") or "").strip()


def check_account_identity(number: str, expected: str | None) -> str:
    """Refuse unless the keys reach the account the owner named, and say so.

    The EFB keys are separate from the credit lab's, and both are paper accounts
    under one Alpaca login: a key pasted from the wrong project trades the wrong
    book, and every number after that is about somebody else's account. So the
    account is named in `EFB_ALPACA_ACCOUNT_ID` and every run compares the number
    the broker reports against it.

    Unset refuses rather than passes. There is nothing to compare against, and a
    guard that answers "I could not tell" by continuing is the guard this exists
    to replace; the refusal names the number it read, which is all the owner needs
    to set the variable. A read that failed is a different case and is answered by
    the caller, because an account that was never read cannot be the wrong
    account.
    """
    if not number:
        raise AccountMismatch(
            "the account's number could not be read, so the run cannot prove which "
            "account the keys reach and it stopped"
        )
    if not expected:
        raise AccountMismatch(
            f"the keys reach account {number}, and {ACCOUNT_ID_ENV} is not set, so "
            "the run cannot prove it is the account the owner named: set "
            f"{ACCOUNT_ID_ENV} to {number} on Render and in .env"
        )
    if number.strip() != str(expected).strip():
        raise AccountMismatch(
            f"the keys reach account {number} but {ACCOUNT_ID_ENV} names "
            f"{str(expected).strip()}: the run stopped before sizing a book or "
            "building any order"
        )
    return f"account {number} matches {ACCOUNT_ID_ENV}"


def open_orders(client) -> list[dict[str, str]]:
    """The account's working orders, as an id and a symbol each.

    An establishment evening buys the whole book from flat, so an order already
    working at the broker is a position that has not settled yet: establishing
    over it would buy names the account is in the middle of buying or selling, and
    the account's own answers (positions flat, orders busy) are the evidence. The
    read is made only when the run would establish, so an ordinary evening spends
    no request on it.
    """
    from alpaca.trading.enums import QueryOrderStatus  # type: ignore
    from alpaca.trading.requests import GetOrdersRequest  # type: ignore

    request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
    return [
        {
            "id": str(getattr(order, "id", "")),
            "symbol": str(getattr(order, "symbol", "")),
        }
        for order in client.get_orders(filter=request)
    ]


def account_figures(account: Any) -> dict[str, float | None]:
    """The account's own numbers: its equity and its cash, or None.

    Alpaca sends both as strings. A missing or unparseable figure answers None
    rather than zero: an account whose equity could not be read is not an account
    worth nothing, and a zero would size a book of no size at all. Equity is the
    account's whole value, cash plus positions, and it is the number the book is
    sized from.
    """
    return {
        "equity": _account_number(account, "equity"),
        "cash": _account_number(account, "cash"),
    }


def _account_number(account: Any, name: str) -> float | None:
    """One field of the account, as a finite float, or None."""
    value = getattr(account, name, None)
    if value is None:
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def verify_account(client) -> dict[str, object]:
    """Read the paper account: its number, its internal id and whether it holds.

    The number is printed by `scripts/verify_account.py` for the owner to copy
    into `EFB_ALPACA_ACCOUNT_ID`; the id is kept beside it because it is what the
    broker's own order records carry.
    """
    account = client.get_account()
    account_id = str(getattr(account, "id", ""))
    positions = client.get_all_positions()
    return {
        "account_number": account_number(account),
        "account_id": account_id,
        "matches_account_id_env": (
            account_number(account) == str(os.environ.get(ACCOUNT_ID_ENV, "")).strip()
        ),
        "n_positions": len(positions),
        "empty": len(positions) == 0,
    }


def require_empty_account(client) -> dict[str, object]:
    """Raise unless the paper account holds nothing.

    The first live order must start from a clean book, so the account is
    checked empty before any submission. A non-empty account would mix
    someone else's positions into EFB's attribution.
    """
    state = verify_account(client)
    if not state["empty"]:
        raise RuntimeError(
            f"refusing to trade: paper account {state['account_id']} already "
            f"holds {state['n_positions']} positions"
        )
    return state


def whole_share_quantization(
    rows: pd.DataFrame, prices: dict[str, float], nav: float
) -> dict[str, object]:
    """The whole-share rounding effect of one proposal.

    Shorts must be whole shares (Alpaca paper rejects fractional
    sell-to-open), so every target notional is quantized to integer shares
    at the proposal close. Returns the gross-weight error from rounding,
    the count of long targets rounding to zero shares, the same for shorts,
    and the per-name distribution: the error is driven by the smallest
    targets, so the zero-share count is reported against each weight decile
    rather than only as a total.
    """
    gross_error = 0.0
    long_zero = 0
    short_zero = 0
    per_name: list[dict[str, object]] = []
    for row in rows.itertuples(index=False):
        price = prices.get(str(row.ticker), 0.0)
        if price <= 0:
            continue
        target_notional = float(row.weight) * nav
        shares = int(abs(target_notional) / price)
        rounded_notional = shares * price * (1.0 if target_notional >= 0 else -1.0)
        error = abs(rounded_notional - target_notional)
        gross_error += error
        if shares == 0:
            if target_notional >= 0:
                long_zero += 1
            else:
                short_zero += 1
        per_name.append(
            {
                "ticker": str(row.ticker),
                "weight": float(row.weight),
                "target_notional": target_notional,
                "shares": shares,
                "rounding_error_usd": error,
                "rounding_error_pct_of_target": (
                    error / abs(target_notional) if target_notional else 0.0
                ),
                "rounds_to_zero": shares == 0,
            }
        )
    frame = pd.DataFrame(per_name)
    return {
        "nav": float(nav),
        "gross_weight_error": gross_error / nav if nav else 0.0,
        "gross_notional_error_usd": gross_error,
        "long_targets_rounding_to_zero": long_zero,
        "short_targets_rounding_to_zero": short_zero,
        "distribution": _quantization_distribution(frame),
    }


def _quantization_distribution(frame: pd.DataFrame) -> dict[str, object]:
    """The per-name rounding error and zero-share counts by weight decile."""
    if frame.empty:
        return {"n": 0}
    error = frame["rounding_error_usd"]
    decile = pd.qcut(frame["weight"].abs(), 10, labels=False, duplicates="drop") + 1
    zero_by_decile = {
        int(d): int(sub["rounds_to_zero"].sum()) for d, sub in frame.groupby(decile)
    }
    quantiles = (0.0, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0)
    return {
        "n": int(len(frame)),
        "rounding_error_usd_quantiles": {
            str(q): float(error.quantile(q)) for q in quantiles
        },
        "rounding_error_pct_of_target_quantiles": {
            str(q): float(frame["rounding_error_pct_of_target"].quantile(q))
            for q in quantiles
        },
        "zero_share_count_by_weight_decile": zero_by_decile,
    }


def enum_value(value: Any) -> Any:
    """The plain value behind an alpaca-py enum, or the value itself.

    alpaca-py returns pydantic enums: `PositionSide.SHORT`, `OrderSide.SELL`,
    `OrderStatus.ACCEPTED`. Their `str()` is "PositionSide.SHORT", not "short", so
    a comparison against a string silently fails. Reading `.value` is what makes
    the comparison work, and a plain string, a number, or None passes through
    unchanged, which is what the fake clients and the tests hand in.
    """
    return getattr(value, "value", value)


def position_book(
    client, dry_run: bool = DRY_RUN_DEFAULT
) -> tuple[dict[str, float], dict[str, float]]:
    """({ticker: signed notional}, {ticker: signed quantity}) in one read.

    Positive is long, negative is short, absent means flat. The sign comes from
    `side`, read by value (`getattr(x, "value", x)`, never `str(x)`), because that
    is the broker's own statement of the direction. A nonzero quantity that
    disagrees with the side raises rather than picking one: the two reads of the
    same position cannot both be right, and a sign taken from the wrong one flips
    every close. A zero quantity is not a disagreement, so a position reported
    with qty 0 still takes its sign from the side. A missing `market_value` raises
    too, because treating it as zero would size a close at nothing.

    The quantity is what a close is sized from: a full close must send the exact
    held quantity, and the broker's own position is the only place that number
    comes from. No quantity contributes zero, and a close then falls back to the
    trade's own notional over the close price.

    Dry run returns two empty dicts without calling Alpaca.
    """
    if dry_run:
        return {}, {}
    notional: dict[str, float] = {}
    quantity: dict[str, float] = {}
    for pos in client.get_all_positions():
        symbol = str(pos.symbol)
        side = str(enum_value(getattr(pos, "side", ""))).lower()
        if side not in ("long", "short"):
            raise ValueError(f"{symbol}: unknown position side {side!r}")
        sign = -1.0 if side == "short" else 1.0
        raw = getattr(pos, "qty", None)
        number = 0.0 if raw is None else float(raw)
        if number != 0.0 and (number > 0) != (sign > 0):
            raise ValueError(
                f"{symbol}: side {side!r} disagrees with quantity {number!r}"
            )
        market_value = getattr(pos, "market_value", None)
        if market_value is None:
            raise ValueError(f"{symbol}: the position carries no market_value")
        notional[symbol] = sign * abs(float(market_value))
        quantity[symbol] = sign * abs(number)
    return notional, quantity


def get_positions(client, dry_run: bool = DRY_RUN_DEFAULT) -> dict[str, float]:
    """{ticker: signed notional} for the current paper positions."""
    return position_book(client, dry_run)[0]


def _side_word(trade_notional: float) -> str:
    """The side an order's signed change implies: buys positive, sells negative."""
    return "buy" if trade_notional >= 0 else "sell"


def find_existing_order(client: Any, ticket: str) -> Any | None:
    """The broker's order carrying this deterministic id, or None.

    A rerun must not place a second order for a leg the first attempt already
    sent. Alpaca would refuse the duplicate id, but that refusal is noise the run
    then has to explain; looking the id up first turns the rerun into a
    resolution of the order that already exists. A client that cannot be asked
    (no such method) answers None, which is the normal first attempt, and a
    lookup that raises is treated the same way: "not found" is the expected
    answer, not a failure.
    """
    lookup = getattr(client, "get_order_by_client_id", None)
    if lookup is None:
        return None
    try:
        return lookup(ticket)
    except Exception:  # noqa: BLE001 - not found is the normal answer
        return None


def read_order(client: Any, order_id: str) -> Any:
    """The broker's own record of one order, by the id the evening recorded.

    Read by `broker_order_id` rather than by the client ticket, because the two
    answer different questions: the ticket is the loop's name for a leg it meant
    to send, and the broker keeps it for the orders it accepted, while the id is
    the broker's own record of the order that arrived. A leg the loop refused at
    a guard or never sent has no id, and is not looked up at all.

    Unlike `find_existing_order` this raises, and the caller decides: a lookup
    for a rerun expects "not found", while an order whose fate cannot be read is
    a question to answer rather than an order that did not fill.
    """
    reader = getattr(client, "get_order_by_id", None)
    if reader is None:
        raise LookupError(f"the client cannot read an order by id ({order_id!r})")
    if not order_id:
        raise LookupError("no order id to read")
    return reader(order_id)


def _resolved_fill(order: Any, ticket: str, existing: Any, intent: str) -> Fill:
    """The record for a leg the broker already held under this id."""
    price = 0.0
    if getattr(existing, "filled_avg_price", None) is not None:
        price = float(existing.filled_avg_price)
    filled_notional = 0.0
    if getattr(existing, "filled_qty", None) is not None:
        filled_notional = abs(float(existing.filled_qty) * price)
    status = (
        str(enum_value(getattr(existing, "status", "")) or "").upper() or "ACCEPTED"
    )
    return Fill(
        ticker=order.ticker,
        order_id=str(getattr(existing, "id", "")),
        intended_notional=order.trade_notional,
        filled_notional=filled_notional,
        fill_price=price,
        status=status,
        detail="already submitted: resolved from the broker by client_order_id",
        intent=intent,
        client_order_id=ticket,
        resolved=True,
    )


def _close_quantity(order: Any, price: float, intent: str) -> float:
    """The shares a close leg sends.

    A full close sends the **exact held quantity** the broker reports, fractional
    included, so the position lands on zero rather than on a rounding remainder.

    A partial **cover** has no such quantity to take, so its size is the trade's
    own notional over the close price, rounded **down** to whole shares. Down, not
    nearest: a cover that buys one share more than the position holds does not
    reduce the short, it closes it and can leave the book long in a name whose
    target is still short, which is a position the run never chose. Whole shares,
    because a half-covered short is a size the sizing step never asked for and
    cannot reason about.

    A partial **long** decrease keeps the fractional size it has always had.
    Selling part of a share cannot turn the position into a short while the target
    still holds shares, and flooring a small trim would round it away entirely and
    skip a leg that should trade.
    """
    held = abs(float(order.held_quantity or 0.0))
    if order.target_notional == 0.0 and held:
        return held
    if price <= 0:
        return 0.0
    raw = abs(float(order.trade_notional)) / price
    if intent == INTENT_BUY_TO_CLOSE:
        return float(math.floor(raw))
    return raw


def submit_market_orders(
    orders,
    client,
    prices: dict[str, float],
    short_cache: dict[str, dict[str, bool]] | None = None,
    close: Any = None,
    throttle: Throttle | None = None,
    id_prefix: str = "efb",
) -> list[Fill]:
    """Submit market orders, one record per intended leg, and do not poll.

    Each leg carries an Alpaca **position intent**, derived from held and target
    when the caller did not set one: `BUY_TO_OPEN` for a long increase (a notional
    order), `SELL_TO_CLOSE` for a long decrease or close (a quantity order),
    `SELL_TO_OPEN` for a new or larger short (whole shares), and `BUY_TO_CLOSE` for
    a short cover (a quantity order). The long decrease and every close send a
    quantity, and a full close sends the broker's exact held quantity. The
    `shortable` and `easy_to_borrow` checks run only on `SELL_TO_OPEN`: a sell that
    closes a long is not a short.

    Nothing polls for a fill. Submitted after the close, a DAY order the broker
    accepts stays accepted or new until the next open, and that acceptance is
    success: the leg's record is the broker's own status, and the fills are
    reconciled the next evening from the broker's positions. A refusal or rejection
    is recorded with its reason code and makes the run incomplete; a broker
    rejection (`APIError`) lets the book keep trading, while a transport-class
    failure halts and the legs after it are recorded `SKIPPED_AFTER_HALT`.

    Every leg carries a deterministic `client_order_id`, under `id_prefix` so a
    smoke order can never collide with the book's. A rerun looks every leg's id up
    first and resolves the orders the broker already holds, before it submits
    anything. Submissions are spaced by `throttle` to stay under the rate limit.
    """
    from alpaca.trading.enums import (  # type: ignore
        OrderSide,
        PositionIntent,
        TimeInForce,
    )
    from alpaca.trading.requests import MarketOrderRequest  # type: ignore

    intent_enum = {
        INTENT_BUY_TO_OPEN: PositionIntent.BUY_TO_OPEN,
        INTENT_BUY_TO_CLOSE: PositionIntent.BUY_TO_CLOSE,
        INTENT_SELL_TO_OPEN: PositionIntent.SELL_TO_OPEN,
        INTENT_SELL_TO_CLOSE: PositionIntent.SELL_TO_CLOSE,
    }
    time_in_force = TimeInForce(NEXT_OPEN_TIF)
    cache = {} if short_cache is None else short_cache
    pace = throttle if throttle is not None else Throttle()

    def _intent_for(order: Any) -> str:
        # The held book is derivable from the leg itself: trade = target - held.
        held = order.target_notional - order.trade_notional
        return order.intent or position_intent(held, order.target_notional)

    # The deterministic ticket for every leg, and the broker's answer for it. All
    # lookups happen before the first submission: that is what "resolve the rerun
    # first" buys, a crash after one leg can never lead a later pass to send a
    # second copy of an earlier one. The lookups are requests to the same API and
    # are paced like the submissions, or a large book's rerun would spend its
    # rate-limit budget before it sent a leg.
    tickets = {
        order.ticker: client_order_id(
            close, order.ticker, _side_word(order.trade_notional), prefix=id_prefix
        )
        for order in orders
    }
    existing: dict[str, Any | None] = {}
    for order in orders:
        pace.wait()
        existing[order.ticker] = find_existing_order(client, tickets[order.ticker])

    fills: list[Fill] = []
    halted = False
    for order in orders:
        trade = order.trade_notional
        notional = abs(trade)
        ticket = tickets[order.ticker]
        intent = _intent_for(order)
        if not intent:
            # The leg does not move: it is not an order, so there is nothing to
            # record. `target_orders` never emits one.
            continue
        if existing[order.ticker] is not None:
            fills.append(_resolved_fill(order, ticket, existing[order.ticker], intent))
            continue
        if halted:
            fills.append(
                _skipped(
                    order.ticker,
                    trade,
                    REASON_SKIPPED_AFTER_HALT,
                    "the run halted on an unknown-state submit failure",
                    intent,
                )
            )
            continue
        price = prices.get(order.ticker, 0.0)
        if intent == INTENT_BUY_TO_OPEN:
            request = MarketOrderRequest(
                symbol=order.ticker,
                notional=round(notional, 2),
                side=OrderSide.BUY,
                time_in_force=time_in_force,
                client_order_id=ticket,
                position_intent=intent_enum[intent],
            )
        elif intent in (INTENT_SELL_TO_CLOSE, INTENT_BUY_TO_CLOSE):
            qty = _close_quantity(order, price, intent)
            if qty <= 0:
                # A cover that rounds down to no whole share cannot be sent as the
                # fractional size it was sized at, and it must not be rounded up to
                # the one share that would close more than the run asked for.
                if intent == INTENT_BUY_TO_CLOSE and price > 0:
                    fills.append(
                        _skipped(
                            order.ticker,
                            trade,
                            REASON_COVER_UNDER_ONE_SHARE,
                            f"{notional:.2f} at {price:.4f} is under one whole "
                            "share, so the cover cannot be sent without "
                            "covering more of the short than was sized",
                            intent,
                        )
                    )
                    continue
                fills.append(
                    _skipped(
                        order.ticker,
                        trade,
                        REASON_CLOSE_QTY_UNKNOWN,
                        "no price and no broker quantity to size the close",
                        intent,
                    )
                )
                continue
            request = MarketOrderRequest(
                symbol=order.ticker,
                qty=qty,
                side=(
                    OrderSide.SELL if intent == INTENT_SELL_TO_CLOSE else OrderSide.BUY
                ),
                time_in_force=time_in_force,
                client_order_id=ticket,
                position_intent=intent_enum[intent],
            )
        elif intent == INTENT_SELL_TO_OPEN:
            refusal = short_refusal(client, order.ticker, cache)
            if refusal is not None:
                code, detail = refusal
                fills.append(_skipped(order.ticker, trade, code, detail, intent))
                continue
            qty = int(notional / price) if price > 0 else 0
            if qty < 1:
                fills.append(
                    _skipped(
                        order.ticker,
                        trade,
                        REASON_QTY_ROUNDS_TO_ZERO,
                        f"{notional:.2f} at {price:.4f} rounds to zero shares",
                        intent,
                    )
                )
                continue
            request = MarketOrderRequest(
                symbol=order.ticker,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=time_in_force,
                client_order_id=ticket,
                position_intent=intent_enum[intent],
            )
        else:  # pragma: no cover - the four intents above are exhaustive
            raise RuntimeError(f"unknown position intent {intent!r}")
        pace.wait()
        try:
            submitted = client.submit_order(order_data=request)
        except Exception as exc:  # noqa: BLE001 - classified, never propagated
            code, halts = classify_submit_failure(exc)
            fills.append(
                Fill(
                    ticker=order.ticker,
                    order_id="",
                    intended_notional=trade,
                    filled_notional=0.0,
                    fill_price=0.0,
                    status=SKIPPED,
                    reason_code=code,
                    detail=f"{type(exc).__name__}: {exc}",
                    intent=intent,
                    client_order_id=ticket,
                )
            )
            halted = halted or halts
            continue

        # The broker's own status is the record. Accepted or new is success: the
        # order is queued for the next open, and there is nothing to poll for. A
        # fill only if the broker filled it on the spot.
        status = (
            str(enum_value(getattr(submitted, "status", "")) or "").upper()
            or "ACCEPTED"
        )
        fill_price = 0.0
        filled_notional = 0.0
        if status == "FILLED":
            if getattr(submitted, "filled_avg_price", None) is not None:
                fill_price = float(submitted.filled_avg_price)
            if getattr(submitted, "filled_qty", None) is not None:
                filled_notional = abs(float(submitted.filled_qty) * fill_price)
        fills.append(
            Fill(
                ticker=order.ticker,
                order_id=str(getattr(submitted, "id", "")),
                intended_notional=trade,
                filled_notional=filled_notional,
                fill_price=fill_price,
                status=status,
                intent=intent,
                client_order_id=ticket,
            )
        )
    return fills


# --- corporate actions and a close, from the market-data API -----------------
#
# The same paper keys reach the market-data endpoints, so the corporate-actions
# read and the one-session close read authenticate exactly as the trading client
# does and never from a file. Both are reads, so neither is behind the dry-run
# guard that protects *submission*: an evening that is not trading still has to
# know a spin-off happened, because it decides what the appended session's return
# is.


def data_credentials() -> tuple[str, str]:
    """The paper key and secret, or a named error when one is missing."""
    key = os.environ.get("EFB_ALPACA_PAPER_API_KEY", "").strip()
    secret = os.environ.get("EFB_ALPACA_PAPER_SECRET_KEY", "").strip()
    if not key or not secret:
        raise RuntimeError(
            "the Alpaca market-data read needs EFB_ALPACA_PAPER_API_KEY and "
            "EFB_ALPACA_PAPER_SECRET_KEY"
        )
    return key, secret


def corporate_actions_client():
    """The corporate-actions read client, from the paper keys."""
    key, secret = data_credentials()
    try:
        from alpaca.data.historical.corporate_actions import CorporateActionsClient
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError(
            "the corporate-actions read needs alpaca-py; install it"
        ) from exc
    return CorporateActionsClient(api_key=key, secret_key=secret)


def bars_client():
    """The historical-bars read client, from the paper keys."""
    key, secret = data_credentials()
    try:
        from alpaca.data.historical import StockHistoricalDataClient
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError("the bars read needs alpaca-py; install it") from exc
    return StockHistoricalDataClient(api_key=key, secret_key=secret)


def spin_offs(
    symbols: list[str],
    session: Any,
    client: Any | None = None,
    window_days: int = 1,
) -> list[dict[str, Any]]:
    """Every spin-off the vendor reports with `session` as its ex-date.

    One request for the whole list, then filtered here to the exact day: the
    endpoint takes a window, and the ex-date is what decides whether the action has
    happened to tonight's session. Each record is a plain dict, so nothing outside
    this module has to know the vendor's object shapes.

    A record whose ex-date is not the session is dropped rather than returned: a
    window that catches a neighbouring day must not be applied to this one.
    """
    names = sorted({str(name) for name in symbols if str(name)})
    if not names:
        return []
    from datetime import timedelta

    day = _as_date(session)
    request_data = {
        "symbols": names,
        "start": day - timedelta(days=window_days),
        "end": day + timedelta(days=window_days),
    }
    try:
        from alpaca.data.requests import (  # type: ignore[import-not-found]
            CorporateActionsRequest,
        )
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError(
            "the corporate-actions read needs alpaca-py; install it"
        ) from exc
    response = (client or corporate_actions_client()).get_corporate_actions(
        CorporateActionsRequest(**request_data)
    )
    records: list[dict[str, Any]] = []
    for item in (getattr(response, "data", None) or {}).get("spin_offs") or []:
        ex_date = _as_date(getattr(item, "ex_date", None))
        if ex_date != day:
            continue
        records.append(
            {
                "parent": str(getattr(item, "source_symbol", "") or ""),
                "child": str(getattr(item, "new_symbol", "") or ""),
                "ex_date": ex_date,
                "source_rate": float(getattr(item, "source_rate", 0.0) or 0.0),
                "new_rate": float(getattr(item, "new_rate", 0.0) or 0.0),
            }
        )
    return sorted(records, key=lambda record: (record["parent"], record["child"]))


def closes_on(
    symbols: list[str], session: Any, client: Any | None = None
) -> dict[str, float]:
    """The close each symbol printed on one session, from the bars endpoint.

    One request for the whole list. The adjustment is RAW and the feed is SIP: a
    spun-off ticker's first session has no history to adjust, and the consolidated
    close is the official one (measured against the price vendor's own official
    closes on 99.9% of name-days, while the IEX feed differs by 2.2 bp at the
    median). A symbol the vendor does not answer for is simply absent, which the
    caller reads as a missing close rather than as a zero.
    """
    names = sorted({str(name) for name in symbols if str(name)})
    if not names:
        return {}
    from datetime import datetime, timedelta

    try:
        from alpaca.data.enums import Adjustment, DataFeed  # type: ignore[import]
        from alpaca.data.requests import (  # type: ignore[import-not-found]
            StockBarsRequest,
        )
        from alpaca.data.timeframe import TimeFrame  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError("the bars read needs alpaca-py; install it") from exc
    day = _as_date(session)
    response = (client or bars_client()).get_stock_bars(
        StockBarsRequest(
            symbol_or_symbols=names,
            timeframe=TimeFrame.Day,
            start=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
            # Exclusive, as measured: the session being asked for needs the day
            # after it, or it is the one session missing from the answer.
            end=datetime.combine(
                day + timedelta(days=1), datetime.min.time(), tzinfo=UTC
            ),
            feed=DataFeed.SIP,
            adjustment=Adjustment.RAW,
        )
    )
    out: dict[str, float] = {}
    for symbol, bars in (getattr(response, "data", None) or {}).items():
        for bar in bars or []:
            stamp = getattr(bar, "timestamp", None)
            if stamp is None or _as_date(stamp) != day:
                continue
            close = float(bar.close)
            if math.isfinite(close) and close > 0:
                out[str(symbol)] = close
    return out


def _as_date(value: Any) -> Any:
    """`datetime.date` from a date, a datetime or an ISO string."""
    from datetime import date, datetime

    if value is None:
        raise ValueError("no date given")
    if isinstance(value, datetime):
        return value.astimezone(UTC).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    stamp = pd.Timestamp(str(value))
    return stamp.date()
