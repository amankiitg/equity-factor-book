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

The stop counts only the names out for a *new* reason tonight: a price, a return, a
share count, a corporate action, or a broker status that changed with this close.
A standing reason - a name the risk model has not fitted yet, a name with no GICS
row (the `BE`/`ILMN`/`P` hold-list among them), an asset already recorded as
retired - is a fact about the book that was true last night and will be true
tomorrow, and ten of those is the universe being the universe, not the fetch having
broken. Standing names stay on the line and in the manifest exactly as before; they
are only kept out of the arithmetic that decides whether the evening can run, and
only when the previous evening's manifest already carried that name for that same
reason. A standing name that was *not* there last night is a new fact about the
universe - fifty names losing a GICS row in one night is the fetch having broken -
so it counts, and so does the same name out for a different reason. A row that does
not say which it is, or a previous evening that could not be read, is counted,
because the safe direction for a stop is to stop.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# The same line the two existing drops drew, now the line for all of them.
MAX_EXCLUSIONS = 10

# Reasons that are a fact about tonight's data rather than about the universe, said
# here so the classification has one home. The readers still set the flag on each
# row (they know which fact they saw); these are the strings a reader that cannot
# classify can be checked against, and what the module's tests pin.
STANDING_REASONS: tuple[str, ...] = (
    "no risk estimate",
    "no GICS row",
)
# A retired asset is recorded once, in `UNREACHABLE_REFUSALS`, and is not a new fact
# on the evenings that follow. If a broker reason ever reaches this list, these
# markers are what keep it out of the count.
RETIRED_MARKERS: tuple[str, ...] = ("asset inactive", "retired", "merger completion")


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
    # Counted toward the stop only when the reason is a fact of tonight's data.
    # Default is to count: a reader that cannot say is treated as a new fault.
    transient: bool = True


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
        transient=_as_flag(item.get("transient")),
    )


def _as_flag(value: object) -> bool:
    """A row's `transient` cell, with an absent or unreadable value counting."""
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() not in {"false", "0", "no", "standing"}


def reason_is_transient(reason: str, source: str = "") -> bool:
    """Whether a reason describes tonight's data (counted) or a standing fact.

    The readers decide this themselves and set `transient` on the row; this is for
    the one reader whose reason text can be either (the broker), and it is the rule
    `STANDING_REASONS` and `RETIRED_MARKERS` describe.
    """
    text = reason.casefold()
    if any(marker in text for marker in RETIRED_MARKERS):
        return False
    if source and source.casefold() in {"risk model", "sectors"}:
        return False
    return not any(standing in text for standing in STANDING_REASONS)


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


def exclusion_key(row: Exclusion) -> tuple[str, str]:
    """The name and the reason, in the form two evenings are compared in.

    The ticker is upper-cased and the reason is stripped of surrounding and repeated
    whitespace, because the same fact is written by the same reader on both nights
    and only the punctuation of the sentence should be allowed to differ.
    """
    return (
        row.ticker.strip().upper(),
        " ".join(str(row.reason).split()).casefold(),
    )


def previous_keys(
    rows: Iterable[Exclusion | Mapping[str, object]] | None,
) -> set[tuple[str, str]]:
    """The (name, reason) pairs of an earlier evening's list.

    `as_rows` writes the same shape, so a stored manifest is read back through the
    same reader the live list uses. An absent list is an empty set: that evening
    named nothing, so every name out tonight is novel.
    """
    keys: set[tuple[str, str]] = set()
    for item in rows or ():
        row = _as_exclusion(item)
        if row is not None:
            keys.add(exclusion_key(row))
    return keys


def novel(
    rows: Iterable[Exclusion],
    previous: Iterable[Exclusion | Mapping[str, object]] | None,
) -> list[Exclusion]:
    """The rows tonight's stop counts.

    A `transient` row is always counted: tonight's price or broker fact is the
    thing the stop exists for. A standing row is counted only when the previous
    evening's list did not carry the same name for the same reason. `previous`
    of `None` means yesterday could not be read, and then every row counts: an
    unreadable record is not evidence that tonight is new.
    """
    rows = list(rows)
    if previous is None:
        return rows
    seen = previous_keys(previous)
    return [row for row in rows if row.transient or exclusion_key(row) not in seen]


def guard(
    rows: Iterable[Exclusion],
    limit: int = MAX_EXCLUSIONS,
    previous: Iterable[Exclusion | Mapping[str, object]] | None = None,
) -> None:
    """Refuse the night when tonight's *new* exclusions are longer than that.

    Only `transient` rows and standing rows absent from the previous evening's
    manifest count (see `novel`). A standing reason carried over from last night -
    no risk estimate yet, no GICS row, an asset already recorded as retired - is
    listed and kept, but the evening is not stopped for it: those names were out
    last night too, and counting them is how a single new exclusion became the
    eleventh name and stopped the 2026-11-23 rebalance.
    """
    rows = list(rows)
    counted = novel(rows, previous)
    if len(counted) <= limit:
        return
    shown = ", ".join(row.ticker for row in counted[:10])
    rest = "" if len(counted) <= 10 else f" and {len(counted) - 10} more"
    standing = len(rows) - len(counted)
    aside = (
        f" ({standing} more name{'' if standing == 1 else 's'} out for standing "
        f"reasons are listed but not counted)"
        if standing
        else ""
    )
    raise TooManyExclusions(
        f"{len(counted)} names are newly excluded tonight, more than the {limit} a "
        f"single evening's data can explain before the input is the suspect rather "
        f"than the names: {shown}{rest}{aside}"
    )


def as_rows(rows: Iterable[Exclusion]) -> list[dict[str, object]]:
    """The manifest's own record: one row per name, with its reason and reader.

    `transient` travels too, so a stored list can be read back and judged the way
    the live list was judged. The sentence the owner reads ignores it.
    """
    return [
        {
            "ticker": row.ticker,
            "reason": row.reason,
            "source": row.source,
            "transient": row.transient,
        }
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
