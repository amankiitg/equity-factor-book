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

import logging
import math
import os
from dataclasses import dataclass
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
FILL_POLL_TIMEOUT_SECS = 30
FILL_POLL_INTERVAL_SECS = 1.0

# The time-in-force every order carries. `day`, not `opg`, and the reason is the
# cron's own hour.
#
# The cron fires at 22:30 UTC (render.yaml, "30 22 * * 1-5"), which is 18:30 ET
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
REASON_SHORT_CHECK_FAILED = "SHORTABLE_CHECK_FAILED"
REASON_NOT_TRADABLE = "ASSET_NOT_TRADABLE"
REASON_NOT_SHORTABLE = "ASSET_NOT_SHORTABLE"
REASON_NOT_EASY_TO_BORROW = "ASSET_NOT_EASY_TO_BORROW"

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


def _skipped(ticker: str, notional: float, code: str, detail: str) -> Fill:
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


def verify_account(client) -> dict[str, object]:
    """Read the paper account: its id and whether it holds anything."""
    account = client.get_account()
    account_id = str(getattr(account, "id", ""))
    positions = client.get_all_positions()
    return {
        "account_id": account_id,
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


def get_positions(client, dry_run: bool = DRY_RUN_DEFAULT) -> dict[str, float]:
    """{ticker: signed notional} for the current paper positions.

    Positive is long, negative is short, absent means flat. Dry run
    returns an empty dict without calling Alpaca.
    """
    if dry_run:
        return {}
    positions = client.get_all_positions()
    result: dict[str, float] = {}
    for pos in positions:
        market_value = abs(float(pos.market_value))
        if str(pos.side).lower() == "long":
            result[str(pos.symbol)] = market_value
        else:
            result[str(pos.symbol)] = -market_value
    return result


def submit_market_orders(
    orders,
    client,
    prices: dict[str, float],
    short_cache: dict[str, dict[str, bool]] | None = None,
) -> list[Fill]:
    """Submit market orders and wait for fills, one record per intended leg.

    Longs use notional orders; shorts use whole-share quantities because Alpaca
    paper rejects fractional sell-to-open orders. `prices` maps each ticker to its
    last close so a short notional can be quantized to whole shares. Each order is
    submitted, polled, and recorded as one Fill. A timeout is a recorded fill with
    status TIMEOUT, never a silently dropped order.

    Every short is checked against the broker's own `shortable` and
    `easy_to_borrow` flags before it is submitted, and a refused leg is recorded
    with its reason code rather than raising. A broker rejection (`APIError`) is
    recorded the same way and the book keeps trading; a transport-class failure
    halts the run and the legs after it are recorded `SKIPPED_AFTER_HALT`, because
    the order may or may not have arrived.

    Every order carries `NEXT_OPEN_TIF`: submitted at the cron's hour the order is
    queued and released for the next session, which is the next-open execution the
    loop wants. The reasoning and the doc citation are on the constant.
    """
    from alpaca.trading.enums import OrderSide, TimeInForce  # type: ignore
    from alpaca.trading.requests import MarketOrderRequest  # type: ignore

    time_in_force = TimeInForce(NEXT_OPEN_TIF)
    cache = {} if short_cache is None else short_cache
    fills: list[Fill] = []
    halted = False
    for order in orders:
        notional = abs(order.target_notional)
        if halted:
            fills.append(
                _skipped(
                    order.ticker,
                    notional,
                    REASON_SKIPPED_AFTER_HALT,
                    "the run halted on an unknown-state submit failure",
                )
            )
            continue
        side = OrderSide.BUY if order.target_notional >= 0 else OrderSide.SELL
        if order.target_notional < 0:
            refusal = short_refusal(client, order.ticker, cache)
            if refusal is not None:
                code, detail = refusal
                fills.append(_skipped(order.ticker, notional, code, detail))
                continue
            price = prices.get(order.ticker, 0.0)
            qty = int(notional / price) if price > 0 else 0
            if qty < 1:
                fills.append(
                    _skipped(
                        order.ticker,
                        notional,
                        REASON_QTY_ROUNDS_TO_ZERO,
                        f"{notional:.2f} at {price:.4f} rounds to zero shares",
                    )
                )
                continue
            request = MarketOrderRequest(
                symbol=order.ticker,
                qty=qty,
                side=side,
                time_in_force=time_in_force,
            )
        else:
            request = MarketOrderRequest(
                symbol=order.ticker,
                notional=round(notional, 2),
                side=side,
                time_in_force=time_in_force,
            )
        try:
            submitted = client.submit_order(order_data=request)
        except Exception as exc:  # noqa: BLE001 - classified, never propagated
            code, halts = classify_submit_failure(exc)
            fills.append(
                Fill(
                    ticker=order.ticker,
                    order_id="",
                    intended_notional=notional,
                    filled_notional=0.0,
                    fill_price=0.0,
                    status=SKIPPED,
                    reason_code=code,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )
            halted = halted or halts
            continue
        import time

        filled_notional = 0.0
        fill_price = 0.0
        deadline = time.time() + FILL_POLL_TIMEOUT_SECS
        status = "TIMEOUT"
        while time.time() < deadline:
            try:
                status_obj = client.get_order(submitted.id)
                if str(status_obj.status) in ("filled", "canceled", "rejected"):
                    status = str(status_obj.status).upper()
                    if status_obj.filled_avg_price is not None:
                        fill_price = float(status_obj.filled_avg_price)
                    if status_obj.filled_qty is not None:
                        filled_notional = float(status_obj.filled_qty) * fill_price
                    break
            except Exception:  # noqa: BLE001 - poll again
                pass
            time.sleep(FILL_POLL_INTERVAL_SECS)
        fills.append(
            Fill(
                ticker=order.ticker,
                order_id=str(submitted.id),
                intended_notional=notional,
                filled_notional=filled_notional,
                fill_price=fill_price,
                status=status,
            )
        )
    return fills
