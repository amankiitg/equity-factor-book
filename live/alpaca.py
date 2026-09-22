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
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PAPER_ENDPOINT = "https://paper-api.alpaca.markets"
PAPER_NAV_DEFAULT = 100_000.0
DRY_RUN_DEFAULT = True
DELTA_MIN_NOTIONAL = 250.0
FILL_POLL_TIMEOUT_SECS = 30
FILL_POLL_INTERVAL_SECS = 1.0


@dataclass(frozen=True)
class Fill:
    """One submitted order and what came back."""

    ticker: str
    order_id: str
    intended_notional: float
    filled_notional: float
    fill_price: float
    status: str


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
    """The live account equity, falling back to the paper default.

    Used to anchor the NAV-relative position cap to the actual book size.
    The fallback only guards the guard: the cap still runs when the
    account read fails.
    """
    try:
        equity = float(client.get_account().equity)
        if equity <= 0:
            raise ValueError(f"non-positive equity: {equity}")
        return equity
    except Exception as exc:  # noqa: BLE001 - a guard fallback, not a skip
        logger.warning(
            "get_nav failed, falling back to %.0f: %s", PAPER_NAV_DEFAULT, exc
        )
        return PAPER_NAV_DEFAULT


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


def submit_market_orders(orders, client, prices: dict[str, float]) -> list[Fill]:
    """Submit market orders and wait for fills.

    Longs use notional orders; shorts use whole-share quantities because
    Alpaca paper rejects fractional sell-to-open orders. `prices` maps
    each ticker to its last close so a short notional can be quantized to
    whole shares. Each order is submitted, polled, and recorded as one
    Fill. A timeout is a recorded fill with status TIMEOUT, never a
    silently dropped order.
    """
    from alpaca.trading.enums import OrderSide, TimeInForce  # type: ignore
    from alpaca.trading.requests import MarketOrderRequest  # type: ignore

    fills: list[Fill] = []
    for order in orders:
        notional = abs(order.target_notional)
        side = OrderSide.BUY if order.target_notional >= 0 else OrderSide.SELL
        if order.target_notional < 0:
            price = prices.get(order.ticker, 0.0)
            qty = int(notional / price) if price > 0 else 0
            if qty < 1:
                fills.append(
                    Fill(
                        ticker=order.ticker,
                        order_id="",
                        intended_notional=notional,
                        filled_notional=0.0,
                        fill_price=0.0,
                        status="SKIPPED_NO_PRICE",
                    )
                )
                continue
            request = MarketOrderRequest(
                symbol=order.ticker,
                qty=qty,
                side=side,
                time_in_force=TimeInForce.DAY,
            )
        else:
            request = MarketOrderRequest(
                symbol=order.ticker,
                notional=round(notional, 2),
                side=side,
                time_in_force=TimeInForce.DAY,
            )
        try:
            submitted = client.submit_order(order_data=request)
        except Exception as exc:  # noqa: BLE001 - recorded, not skipped
            fills.append(
                Fill(
                    ticker=order.ticker,
                    order_id="",
                    intended_notional=notional,
                    filled_notional=0.0,
                    fill_price=0.0,
                    status=f"REJECTED_ALPACA: {type(exc).__name__}",
                )
            )
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
