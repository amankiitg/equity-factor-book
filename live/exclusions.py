"""One name never stops the book, and one line says which names are out.

Every failure since launch has been the same shape: one name's data stopped the
whole evening. The SKYD warrant with no price, SKYD.WS read as a spin-off child,
CTVA's vendor restatement, HON's contradicted spin ratio, KVUE's NaN close on a
hold day, KVUE retired at the broker, and the share counts one name's silence made
stale. Each was answered where it was found, with its own list, its own wording and
its own threshold, so the same class of fault had to be rediscovered each time.

This module is the one place that answers it. A name whose data cannot support an
order leaves the book for the night, the reason is recorded with the name, and the
evening's message carries a single sentence naming them. A held position is not
quietly dropped: it is owed, and the code that reports what is owed reads the same
records (`UNREACHABLE_REFUSALS` in `live.evening_job`).

The stop is still there, and it is now one number rather than three. More names out
than `MAX_EXCLUSIONS` is not a market with a few holes in it; it is an input that
failed for the panel, and the run stops and says so instead of trading a book the
model did not ask for. Ten of roughly five hundred is the line the no-price and
no-risk drops already drew (`MAX_PRICE_DROPS`, `MAX_RISK_DROPS`), and it is kept
here for the same reason: a handful is a halt, a delisting or a vendor gap, and ten
at once is the fetch having broken.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# The same line the two existing drops drew, now the line for all of them.
MAX_EXCLUSIONS = 10


@dataclass(frozen=True)
class Exclusion:
    """One name out of tonight's book, and why.

    `reason` is written for the owner, not for a log parser: "no usable close", "no
    risk estimate", "the broker reports the asset inactive". `source` says which
    reader decided it, so a reason that looks wrong can be traced to one place.
    """

    ticker: str
    reason: str
    source: str


class TooManyExclusions(ValueError):
    """More names out than one night's data can explain."""


def _as_exclusion(item: Exclusion | Mapping[str, object]) -> Exclusion | None:
    if isinstance(item, Exclusion):
        return item
    ticker = str(item.get("ticker") or "").strip()
    if not ticker:
        return None
    return Exclusion(
        ticker=ticker,
        reason=str(item.get("reason") or "excluded"),
        source=str(item.get("source") or ""),
    )


def collect(*groups: Iterable[Exclusion | Mapping[str, object]]) -> list[Exclusion]:
    """Every exclusion from every reader, one per name, first reason wins.

    A name can be excluded twice for the same fact - the no-price drop and the
    held-name drop both see a name that did not print - and saying it twice in one
    sentence reads as two problems. The first reader to see it names it; the others
    are dropped, because the name is already out.
    """
    seen: dict[str, Exclusion] = {}
    for group in groups:
        for item in group or ():
            row = _as_exclusion(item)
            if row is None:
                continue
            seen.setdefault(row.ticker.upper(), row)
    return [seen[ticker] for ticker in sorted(seen)]


def guard(rows: Iterable[Exclusion], limit: int = MAX_EXCLUSIONS) -> None:
    """Refuse the night when the list is longer than a night of data can explain."""
    rows = list(rows)
    if len(rows) <= limit:
        return
    shown = ", ".join(row.ticker for row in rows[:10])
    rest = "" if len(rows) <= 10 else f" and {len(rows) - 10} more"
    raise TooManyExclusions(
        f"{len(rows)} names are excluded tonight, more than the {limit} a single "
        f"evening's data can explain before the input is the suspect rather than "
        f"the names: {shown}{rest}"
    )


def as_rows(rows: Iterable[Exclusion]) -> list[dict[str, str]]:
    """The manifest's own record: one row per name, with its reason and reader."""
    return [
        {"ticker": row.ticker, "reason": row.reason, "source": row.source}
        for row in rows
    ]


def sentence(rows: Iterable[Exclusion], limit: int = 8) -> str:
    """The one line the message carries, or "" when nothing is out.

    `Excluded tonight: KVUE (the broker reports the asset inactive), BE (no risk
    estimate).` The reason travels with the name because "excluded" alone leaves
    the owner to open the manifest to find out whether it was a price, a risk row
    or a merger.
    """
    rows = list(rows)
    if not rows:
        return ""
    named = [f"{row.ticker} ({row.reason})" for row in rows[:limit]]
    tail = "" if len(rows) <= limit else f"; and {len(rows) - limit} more"
    return f"Excluded tonight: {', '.join(named)}{tail}."
