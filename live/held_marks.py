"""Which price the held book is marked at, and the switch that would change it.

The evening reads the account and divides the broker's `market_value` by the
account's equity to get the held weights (`live/positions.py`). `market_value` is
the last trade the broker saw, which on a 22:55 UTC run includes the extended
session: on 2026-10-29 that marked INTC at $71.16 against an official close of
$92.07, after earnings. The held weights feed the drift guard, so the mark source
decides what the guard reads.

`EFB_HELD_MARKS=close` values each position at the newest vendor close the tree
holds for it times the broker's quantity, instead. The default is `broker`, which
is what the evening does today; the switch exists because the owner asked for the
alternative to be buildable and measurable, not because it is adopted. See
`docs/research/mark_source.md` for the five-day comparison and the recommendation,
which is not to switch: the vendor's daily bar for the current session is not
printed at 22:55 UTC, so "close x quantity" carries a one-session lag, and the
extended-hours print the broker reports was the better forecast of the next open in
the one earnings case that mattered.

Either way the choice is recorded with the run: `at_close` returns the mark each
name was valued at and the names it could not value, and an unvalued name keeps the
broker's number rather than dropping out of the book.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable, Mapping
from typing import Any

logger = logging.getLogger(__name__)

HELD_MARKS_ENV = "EFB_HELD_MARKS"
MODE_BROKER = "broker"
MODE_CLOSE = "close"

_provider: Callable[[Iterable[str]], Mapping[str, float]] | None = None


def mode() -> str:
    """The mark source this process is configured for, `broker` unless asked."""
    raw = os.environ.get(HELD_MARKS_ENV, "").strip().lower()
    if not raw:
        return MODE_BROKER
    if raw == MODE_CLOSE:
        return MODE_CLOSE
    if raw == MODE_BROKER:
        return MODE_BROKER
    raise ValueError(
        f"{HELD_MARKS_ENV}={raw!r} is not a mark source: use {MODE_BROKER!r} or "
        f"{MODE_CLOSE!r}, or leave it unset for {MODE_BROKER!r}"
    )


def configure(provider: Callable[[Iterable[str]], Mapping[str, float]] | None) -> None:
    """Set the function that answers closes for a set of tickers, or clear it.

    The run configures it once, where the tree it reads is known, so that the
    positions module does not have to carry a data root through every call.
    """
    global _provider
    _provider = provider


def marks_for(names: Iterable[str]) -> dict[str, float]:
    """{ticker: close} from the configured provider, empty when there is none."""
    if _provider is None:
        logger.warning(
            "%s=%s but no close provider is configured: the book is marked at the "
            "broker's market values",
            HELD_MARKS_ENV,
            MODE_CLOSE,
        )
        return {}
    try:
        answered = _provider(sorted({str(name) for name in names}))
    except Exception as exc:  # a mark source that fails must not stop the evening
        logger.warning("could not read close marks: %s", type(exc).__name__)
        return {}
    out: dict[str, float] = {}
    for name, value in (answered or {}).items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0 and number == number:  # finite and positive
            out[str(name)] = number
    return out


def at_close(
    notional: Mapping[str, float],
    quantities: Mapping[str, float],
    closes: Mapping[str, float],
) -> tuple[dict[str, float], dict[str, Any]]:
    """Value each held name at its close times its quantity, where a close exists.

    The broker's notional is kept for a name with no close: a missing mark must not
    silently remove a position from the book the guard measures. The summary names
    both sets so the run can say which names it could not re-mark.
    """
    remark: dict[str, float] = {}
    kept: list[str] = []
    for ticker, value in notional.items():
        name = str(ticker)
        quantity = float(quantities.get(name, 0.0) or 0.0)
        close = float(closes.get(name, 0.0) or 0.0)
        if quantity == 0.0 or close <= 0.0:
            remark[name] = float(value)
            kept.append(name)
        else:
            remark[name] = quantity * close
    moved = {
        name: round(remark[name] - float(notional[name]), 2)
        for name in remark
        if name not in kept
    }
    largest = max(moved.items(), key=lambda item: abs(item[1])) if moved else None
    return remark, {
        "mode": MODE_CLOSE,
        "n_remark": len(moved),
        "n_kept_broker": len(kept),
        "kept_broker": sorted(kept),
        "largest_move": (
            None if largest is None else {"ticker": largest[0], "usd": largest[1]}
        ),
    }


def tree_closes(
    root: Any, as_of: str | None = None
) -> Callable[[Iterable[str]], dict[str, float]]:
    """A provider that answers the newest close at or before `as_of` from the tree.

    The vendor's daily bar for the current session is not printed at 22:55 UTC, so
    on a live evening this answers the previous session's close for most names and
    the current one for any name whose bar has already printed. That lag is the
    reason the switch is not adopted: `docs/research/mark_source.md` measures it.
    """
    from pathlib import Path

    import pandas as pd

    path = Path(root) / "raw" / "prices.parquet"

    def provider(names: Iterable[str]) -> dict[str, float]:
        wanted = {str(name) for name in names}
        if not wanted:
            return {}
        frame = pd.read_parquet(path, columns=["close"])
        frame = frame.reset_index()
        frame = frame.loc[frame["ticker"].astype(str).isin(wanted)]
        if as_of:
            dates = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
            frame = frame.loc[dates <= as_of]
        frame = frame.dropna(subset=["close"])
        if frame.empty:
            return {}
        frame = frame.assign(day=pd.to_datetime(frame["date"]))
        newest = frame.sort_values("day").groupby(frame["ticker"].astype(str)).tail(1)
        return {str(row.ticker): float(row.close) for row in newest.itertuples()}

    return provider
