"""Sprint E11 pre-deploy, item 4b: the corporate-actions rule in the append path.

Two facts collide. The vendor's adjusted close back-adjusts history on a split,
while this pipeline only appends: no stored row may be restated. And E1's outlier
flag is 50%, so a split return of -48% would slip under it. Every future split
would therefore either produce a fake return on the new day or demand a restated
history, and the project forbids the second.

The rule, in the append path only:

1. **Detect.** The vendor's split record for the ticker is primary, and the
   cross-check is a refetch of the last stored session's adjusted close: a ratio
   that differs from 1 is a back-adjustment and it has to match the split factor.
   A mismatch between the two, or a back-adjustment with no split record, stops
   the run as an error naming the ticker. Nothing is guessed.
2. **Compute the new day's return with the factor**, never from the
   back-adjusted history: `r_t = close_t * factor / close_{t-1} - 1`, where the
   factor is new shares per old share. No stored row changes.
3. **Record the event** in `efb.e11_corporate_actions`: ticker, effective date,
   factor, source and the cross-check ratio. The run's `run_status` carries it and
   the notification names it, "split: APH 2:1 applied".
4. **Shares across a split.** The share-count fetch can lag. While the newest
   stored count predates the split's effective date it is on the old basis, so the
   factor applies. The lag is detected by date, never by guessing a plausible
   count.
5. **Held positions across a split, for the live phase.** The broker adjusts the
   share count and the price, so the position's notional is unchanged and the next
   day's trade for an unchanged target is zero. A loop that rebuilt the held
   position from a stored share count would think it held half and buy the other
   half, so the notional is what reconciles and the share count is scaled.
6. **Unexplained large moves are flagged, not blocked.** An appended return above
   40% in absolute value with no corporate action behind it goes into `run_status`
   and the notification. A real crash is a real return.
7. **Spin-offs are corrected from the vendor's own record, on the same terms.**
   A spin-off is the other action that moves one session's return and that neither
   price vendor adjusts: CTVA closed 77.65 on 2026-09-30 and printed 12.57 the next
   day (-83.81%) while the holder was also given one VYLR share worth 68.26. Each
   evening, before the fit reads the returns, the vendor's spin-offs whose ex-date
   is the appended session are read for the universe, and the parent's return is
   replaced by `(parent_close + ratio x child_close) / parent_prior_close - 1` from
   raw closes only. The event is recorded in `efb.e11_corporate_actions` with
   `explained_by` "spinoff", the print it replaced stays in the run's flag with its
   own value, and the row's own cell carries the correction, because that cell is
   the fit's input and the flag is the record. A child close that cannot be read
   nulls that one cell and is named in the message: the run does not stop, and the
   raw print is never left in the fit as if it were a return. A parent the panel
   does not carry, a record for another day and a record outside the universe are
   all dropped rather than guessed at, and a record for a name this book holds whose
   rates cannot be turned into a ratio stops the run the way an unexplained
   back-adjustment does.

The 2026-09-03 APH split, measured from the stored rows: the vendor's record says
2:1, the raw close halves from 158.55 on 2026-08-31 to 82.78 on 2026-09-04, and
the panel's APH return on 2026-09-04 is **NaN**, not -48%, because
`returns.compute_returns` uses `pct_change(fill_method=None)` and the four sessions
before it are NaN. The appendix therefore did not carry the split as a fake
return; it carried a hole. This module's rule is what stops the next split from
being a fake return, and it is also what fills that hole going forward without
rewriting a single stored row.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from live import store

logger = logging.getLogger(__name__)

TABLE = "e11_corporate_actions"
TABLE_KEY = ("trade_date", "ticker")
LARGE_MOVE = 0.40
# The cross-check reads the vendor's adjusted close, which carries dividends as
# well as splits, so a factor is matched within this band rather than exactly.
# Measured on the real case: APH's stored 158.5500 at 2026-08-31 against a
# refetched 79.1522 is a ratio of 0.499226, one APH quarterly dividend away from
# 0.5. Two real split factors are never within 2% of each other (3:2 against 2:1
# is 25% apart), so the band separates a dividend from a factor, and a deviation
# beyond it that no record explains stops the run.
CROSS_CHECK_TOLERANCE = 0.02
SPLIT_LOOKBACK_DAYS = 10


@dataclass(frozen=True)
class Split:
    """One vendor split record: effective date and new shares per old share."""

    ticker: str
    effective_date: pd.Timestamp
    factor: float
    source: str = "yfinance.splits"

    @property
    def ratio_label(self) -> str:
        """`2:1` style, for a message."""
        return f"{self.factor:g}:1"


def register_table() -> None:
    """Put the corporate-actions table into the store's registry."""
    if TABLE not in store.TABLES:
        store.TABLES = store.TABLES + (TABLE,)
    store.TABLE_KEYS[TABLE] = TABLE_KEY


register_table()


def _normalized(stamp: Any) -> pd.Timestamp:
    when = pd.Timestamp(stamp)
    return when.tz_localize(None).normalize() if when.tzinfo else when.normalize()


def vendor_splits(
    ticker: str, fetcher: Callable[[str], Any] | None = None
) -> list[Split]:
    """The vendor's split records for one ticker, oldest first.

    `fetcher` exists so a test drives the rule without the network; the default
    reads yfinance's `splits`, the same vendor the price and share fetches use.
    """
    if fetcher is None:

        def fetcher(name: str) -> Any:
            import yfinance as yf  # noqa: PLC0415 - the vendor, imported late

            return yf.Ticker(name).splits

    raw = fetcher(ticker)
    if raw is None or len(raw) == 0:
        return []
    out: list[Split] = []
    for stamp, factor in raw.items():
        when = pd.Timestamp(stamp)
        value = float(factor)
        if pd.isna(when) or not math.isfinite(value) or value <= 0:
            continue
        out.append(Split(ticker=ticker, effective_date=_normalized(when), factor=value))
    return sorted(out, key=lambda split: split.effective_date)


def recent_splits(
    tickers: list[str],
    session: pd.Timestamp,
    fetcher: Callable[[str], Any] | None = None,
    lookback_days: int = SPLIT_LOOKBACK_DAYS,
) -> list[Split]:
    """Every ticker's split records within the lookback of the appended session.

    Only the window that can matter is asked about: a split older than the stored
    history's last session cannot change the new day's return.
    """
    floor = _normalized(session) - pd.Timedelta(days=lookback_days)
    out: list[Split] = []
    for ticker in tickers:
        out.extend(
            split
            for split in vendor_splits(ticker, fetcher=fetcher)
            if split.effective_date >= floor
        )
    return sorted(out, key=lambda split: (split.effective_date, split.ticker))


def cross_check_ratio(stored_adjusted_close: float, refetched: float) -> float:
    """Refetched over stored, for the last stored session's adjusted close.

    A value that differs from 1 is a back-adjustment: the vendor has restated a
    session this pipeline already holds, which only a split does.
    """
    if not math.isfinite(stored_adjusted_close) or stored_adjusted_close <= 0:
        raise ValueError(
            "the stored adjusted close is not a usable price to cross-check against"
        )
    if not math.isfinite(refetched) or refetched <= 0:
        raise ValueError("the refetched adjusted close is not a usable price")
    return float(refetched) / float(stored_adjusted_close)


def _agrees(ratio: float, factor: float) -> bool:
    """Whether a back-adjustment ratio matches a split factor or its inverse.

    The vendor restates the older session, so the refetched value is the stored
    one divided by the factor; a factor below 1 (a reverse split) flips that.
    """
    return (
        abs(ratio * factor - 1.0) <= CROSS_CHECK_TOLERANCE
        or abs(ratio / factor - 1.0) <= CROSS_CHECK_TOLERANCE
    )


def resolve_split(
    ticker: str,
    ratio: float,
    splits: list[Split],
    session: pd.Timestamp | None = None,
    lookback_days: int = SPLIT_LOOKBACK_DAYS,
) -> Split | None:
    """The split the back-adjustment is, or an error naming the ticker.

    A ratio of 1 needs no split and any record is then irrelevant. A ratio that
    differs from 1 must be explained by a record near the session being appended;
    anything else stops the run rather than being guessed at.
    """
    if abs(ratio - 1.0) <= CROSS_CHECK_TOLERANCE:
        return None
    if not splits:
        raise ValueError(
            f"{ticker}: the vendor back-adjusted the last stored session "
            f"(ratio {ratio:.6f}) with no split record behind it, so the run stops "
            f"rather than guessing what happened"
        )
    if session is not None:
        floor = _normalized(session) - pd.Timedelta(days=lookback_days)
        near = [split for split in splits if split.effective_date >= floor]
        if near:
            splits = near
    matching = [split for split in splits if _agrees(ratio, split.factor)]
    if not matching:
        factors = ", ".join(f"{split.factor:g}" for split in splits)
        raise ValueError(
            f"{ticker}: the vendor back-adjusted the last stored session "
            f"(ratio {ratio:.6f}) but its split records say {factors}, so the run "
            f"stops rather than guessing which is right"
        )
    return matching[-1]


def adjusted_return(close_t: float, factor: float, close_previous: float) -> float:
    """The split-adjusted simple return of the first post-split session.

    `close_t * factor / close_{t-1} - 1`, with the factor in new shares per old
    share. Both closes are raw prices on their own basis, which is the point: the
    back-adjusted history is never the numerator.
    """
    if not math.isfinite(close_previous) or close_previous <= 0:
        raise ValueError("the previous close is not a usable price")
    if not math.isfinite(close_t) or close_t <= 0:
        raise ValueError("the session's close is not a usable price")
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError("the split factor must be a positive number")
    return float(close_t) * float(factor) / float(close_previous) - 1.0


# --- spin-offs ---------------------------------------------------------------
#
# A spin-off is the other corporate action that moves a return on one session, and
# it is not a split: the parent keeps trading and the shareholder is given shares
# of the company that was spun out. CTVA's Vylor spin-off on 2026-10-01 is the case
# this exists for: CTVA closed 77.65 on 2026-09-30 and printed 12.57 the next day,
# a raw -83.81% that is not a loss, because the holder also received one VYLR
# share worth 68.26. Neither the price vendor's adjusted close nor Alpaca's
# `adjustment=all` corrects it (measured: both carry the raw print), so the
# correction has to be applied here, from the parent's and the child's raw closes
# and the vendor's own spin-off record.
#
# The rule mirrors the split rule in every respect that matters: it applies to the
# appended session before the fit reads the returns, it computes from raw closes
# on their own bases, it restates no stored row, and it records the event.

SPINOFF_SOURCE = "alpaca.corporate_actions"


@dataclass(frozen=True)
class Spinoff:
    """One vendor spin-off record: the parent, the child and the share ratio.

    `child_per_parent` is None when the record cannot be used at all, and
    `unusable_reason` then says in one phrase what is missing. A record like that is
    kept rather than dropped: the parent's cell still has to be nulled and the owner
    still has to be told the name, which is the same shape as a child whose close
    cannot be read.
    """

    parent: str
    child: str
    ex_date: pd.Timestamp
    child_per_parent: float | None
    source_rate: float = 1.0
    new_rate: float = 1.0
    source: str = SPINOFF_SOURCE
    unusable_reason: str | None = None

    @property
    def applicable(self) -> bool:
        """Whether the record carries a ratio the rule can apply."""
        return self.unusable_reason is None

    @property
    def ratio_label(self) -> str:
        """`1:1` style, for a message."""
        if self.child_per_parent is None:
            return "no ratio"
        return f"{self.child_per_parent:g}:1"

    @property
    def label(self) -> str:
        """`spinoff: CTVA -> VYLR 1:1 applied`, in the split line's own shape."""
        if not self.applicable:
            return (
                f"spinoff: {self.parent} -> {self.child or '?'} not applied: "
                f"{self.unusable_reason}"
            )
        return f"spinoff: {self.parent} -> {self.child} {self.ratio_label} applied"


@dataclass(frozen=True)
class SpinoffOutcome:
    """What the rule did to one parent's row, for the record and the flag.

    `raw_return` is the print the artifact carried before the rule touched it: it is
    what the 40% flag reads and what a person has to be able to find afterwards.
    `adjusted_return` is what the row now holds, or None when the cell was nulled
    instead, which happens for two reasons that have to stay apart: the child's close
    could not be read (`missing_child`), or the vendor's own record could not be used
    at all (`unusable_record`).
    """

    spinoff: Spinoff
    session: pd.Timestamp
    raw_return: float | None
    adjusted_return: float | None
    child_close: float | None

    @property
    def unusable_record(self) -> bool:
        """Whether the vendor's record itself carried no usable ratio."""
        return not self.spinoff.applicable

    @property
    def missing_child(self) -> bool:
        return self.child_close is None and not self.unusable_record

    @property
    def raises_flag(self) -> bool:
        """Whether the print this replaced is worth a flag of its own.

        The raw print above the large-move threshold is the event a reader looks
        for, and a nulled cell is always worth saying: the one thing that must not
        happen is a row that changed for a reason nothing records.
        """
        if self.missing_child or self.unusable_record:
            return True
        raw = self.raw_return
        return raw is not None and abs(raw) > LARGE_MOVE


def vendor_spinoffs(
    session: pd.Timestamp,
    universe: list[str],
    fetcher: Callable[[list[str], pd.Timestamp], list[dict[str, Any]]] | None = None,
) -> list[Spinoff]:
    """Every spin-off the vendor reports with `session` as its ex-date.

    Asked for the universe and filtered to the day, because the action is only
    relevant when its ex-date is the session being appended. A record for a name
    the book does not hold is dropped.

    A record for one it does hold that cannot be used, whether because it names no
    child symbol or because its rates cannot form a share ratio, is kept with
    `child_per_parent` None rather than raising. The evening goes on, that one cell
    is nulled so the raw print cannot be read as a return, and the phrase in
    `unusable_reason` is what the message names. Stopping the run would be worse than
    the hole: the orders are sent before this rule runs, and a vendor field coming
    back empty is not the book's problem to solve by refusing to price it.
    """
    names = sorted({str(ticker) for ticker in universe if str(ticker)})
    if not names:
        return []
    records = (fetcher or _default_spinoff_fetch)(names, _normalized(session))
    wanted = set(names)
    out: list[Spinoff] = []
    for record in records or []:
        parent = str(record.get("parent") or "").strip()
        if parent not in wanted:
            continue
        child = str(record.get("child") or "").strip()
        source_rate = float(record.get("source_rate") or 0.0)
        new_rate = float(record.get("new_rate") or 0.0)
        when = record.get("ex_date")
        ex_date = _normalized(session if when is None else when)
        unusable: str | None = None
        if not child:
            unusable = "no child symbol"
        elif (
            not math.isfinite(source_rate)
            or not math.isfinite(new_rate)
            or source_rate <= 0
            or new_rate <= 0
        ):
            unusable = (
                f"source_rate {source_rate!r} and new_rate {new_rate!r} cannot "
                f"form a share ratio"
            )
        out.append(
            Spinoff(
                parent=parent,
                child=child,
                ex_date=ex_date,
                child_per_parent=(
                    None if unusable is not None else new_rate / source_rate
                ),
                source_rate=source_rate,
                new_rate=new_rate,
                unusable_reason=unusable,
            )
        )
    return sorted(out, key=lambda spinoff: (spinoff.parent, spinoff.child))


def _default_spinoff_fetch(
    symbols: list[str], session: pd.Timestamp
) -> list[dict[str, Any]]:
    """The vendor's spin-offs for a list of names and a session, from Alpaca."""
    from live import alpaca  # noqa: PLC0415 - the vendor, imported late

    return alpaca.spin_offs(symbols, session)


def spinoff_return(
    parent_close: float,
    child_close: float,
    child_per_parent: float,
    parent_previous_close: float,
) -> float:
    """The parent's total return across the spin-off's ex-date.

    `(parent_close + ratio x child_close) / parent_previous_close - 1`, with the
    ratio in child shares per parent share: the holder ends the session with the
    parent it had plus the child it was given, so the two together are what the
    session paid, over the parent's own prior close. Every input is a raw close on
    its own basis, and no stored row is involved.
    """
    if not math.isfinite(parent_previous_close) or parent_previous_close <= 0:
        raise ValueError("the parent's previous close is not a usable price")
    if not math.isfinite(parent_close) or parent_close <= 0:
        raise ValueError("the parent's close is not a usable price")
    if not math.isfinite(child_close) or child_close <= 0:
        raise ValueError("the child's close is not a usable price")
    if not math.isfinite(child_per_parent) or child_per_parent <= 0:
        raise ValueError("the child's shares per parent share must be positive")
    return (float(parent_close) + float(child_per_parent) * float(child_close)) / float(
        parent_previous_close
    ) - 1.0


def _close_before(
    prices_frame: pd.DataFrame, ticker: str, session: pd.Timestamp
) -> float | None:
    """The last stored close before `session`, which is the prior close."""
    _, close, _ = _stored_pair(prices_frame, ticker, session)
    return close


def _set_return(
    frame: pd.DataFrame, session: pd.Timestamp, ticker: str, value: float
) -> None:
    """Write one row's return, keeping the log column consistent with it.

    `processed/returns.parquet` carries `r` and `g = ln(1 + r)` in the same row
    (measured: `|g - log1p(r)|` is exactly 0 over the stored panel), so a rule that
    rewrote `r` alone would leave the row internally inconsistent. A null is
    written to both, which is what `log1p` of a null is.
    """
    frame.loc[(session, ticker), "r"] = value
    if "g" in getattr(frame, "columns", []):
        frame.loc[(session, ticker), "g"] = (
            float("nan") if pd.isna(value) else math.log1p(float(value))
        )


def _apply_spinoff(
    frame: pd.DataFrame,
    prices_frame: pd.DataFrame,
    spinoff: Spinoff,
    child_close: Callable[[str, pd.Timestamp], float | None] | None,
) -> SpinoffOutcome | None:
    """Correct the parent's appended return, or null the one cell.

    Returns None when there is no row to correct, which is the ordinary case for a
    parent outside tonight's panel. Two things null the cell rather than leaving the
    raw print in the fit, because a null is a hole the hygiene layer reports and the
    raw print is a number that is wrong: a child whose close cannot be read, and a
    record the rule cannot use at all (no ratio to apply). The second is checked
    before a single price is looked up, because there is nothing to compute with.
    """
    session = spinoff.ex_date
    parent = spinoff.parent
    if (session, parent) not in frame.index:
        return None
    raw = frame.loc[(session, parent), "r"]
    raw_value = None if pd.isna(raw) else float(raw)
    ratio = spinoff.child_per_parent
    if ratio is None:
        # The vendor's own record carried no usable ratio, so there is nothing to
        # compute with: the cell is nulled before a single price is looked up.
        _set_return(frame, session, parent, float("nan"))
        return SpinoffOutcome(spinoff, session, raw_value, None, None)
    previous = _close_before(prices_frame, parent, session)
    parent_close = _close_on(prices_frame, parent, session)
    child = _close_on(prices_frame, spinoff.child, session)
    if child is None and child_close is not None:
        child = child_close(spinoff.child, session)
    if child is None or parent_close is None or previous is None:
        _set_return(frame, session, parent, float("nan"))
        return SpinoffOutcome(spinoff, session, raw_value, None, None)
    value = spinoff_return(
        parent_close=parent_close,
        child_close=float(child),
        child_per_parent=float(ratio),
        parent_previous_close=previous,
    )
    _set_return(frame, session, parent, value)
    return SpinoffOutcome(spinoff, session, raw_value, value, float(child))


def spinoff_flags(
    events: list[SpinoffOutcome], session: pd.Timestamp
) -> list[dict[str, Any]]:
    """One flag per spin-off applied to `session`, in the large-move shape.

    `return` is the raw print, because that is the move the threshold is about and
    the number the owner has to be able to find again; `adjusted_return` is what the
    row holds now. `explained_by` is "spinoff", so the message counts no unexplained
    move for a return the rule corrected.
    """
    out: list[dict[str, Any]] = []
    for event in events:
        if event.session != session or not event.raises_flag:
            continue
        label = event.spinoff.label
        if event.unusable_record:
            label = f"{label}, so the return was nulled"
        elif event.missing_child:
            label = (
                f"{label}, the {event.spinoff.child} close is missing so the "
                f"return was nulled"
            )
        out.append(
            {
                "ticker": event.spinoff.parent,
                "return": event.raw_return,
                "adjusted_return": event.adjusted_return,
                "new_ticker": event.spinoff.child,
                "new_close": event.child_close,
                "explained_by": "spinoff",
                "flag": label,
            }
        )
    return out


def spinoff_rows(
    events: list[SpinoffOutcome], trade_date: pd.Timestamp
) -> list[dict[str, Any]]:
    """The appendix rows for the spin-offs applied to one session.

    `factor` is the child's shares per parent share, the slot a split's factor
    occupies, and `explained_by` says which of the two the row is. The
    cross-check ratio is null: a spin-off is not a back-adjustment, so there is
    nothing to cross-check it against.

    Only records that were applied get a row: a record whose rates cannot form a
    ratio has no factor to write, and nothing was applied with it. It is not
    silent - the flag carries it and the message names the parent - but it does not
    belong in a table of corporate actions the rule used.
    """
    stamp = pd.Timestamp(trade_date).date().isoformat()
    rows: list[dict[str, Any]] = []
    for event in events:
        ratio = event.spinoff.child_per_parent
        if ratio is None:
            continue
        rows.append(
            {
                "trade_date": stamp,
                "ticker": event.spinoff.parent,
                "effective_date": event.spinoff.ex_date.date().isoformat(),
                "factor": float(ratio),
                "source": event.spinoff.source,
                "cross_check_ratio": None,
                "explained_by": "spinoff",
                "new_ticker": event.spinoff.child,
                "source_rate": float(event.spinoff.source_rate),
                "new_rate": float(event.spinoff.new_rate),
            }
        )
    return rows


def describe_spinoffs(events: list[SpinoffOutcome]) -> list[str]:
    """`spinoff: CTVA -> VYLR 1:1 applied` per applied spin-off, for the message."""
    return [event.spinoff.label for event in events if event.spinoff.applicable]


def missing_child_notes(events: list[SpinoffOutcome]) -> list[str]:
    """`VYLR (CTVA)` per spin-off whose child close could not be read."""
    return [
        f"{event.spinoff.child} ({event.spinoff.parent})"
        for event in events
        if event.missing_child
    ]


def unusable_spinoff_notes(events: list[SpinoffOutcome]) -> list[str]:
    """`CTVA (no child symbol)` per record whose own fields could not be used.

    The parent is named because the parent is the row that was nulled, and the
    reason is named because "we could not use it" is not something the owner can
    take to the vendor.
    """
    return [
        f"{event.spinoff.parent} ({event.spinoff.unusable_reason})"
        for event in events
        if event.unusable_record
    ]


def resolve_spinoffs(
    sessions: list[pd.Timestamp],
    universe: list[str],
    prices_frame: pd.DataFrame,
    fetcher: Callable[[list[str], pd.Timestamp], list[dict[str, Any]]] | None = None,
    child_closes_fetcher: (
        Callable[[list[str], pd.Timestamp], dict[str, float]] | None
    ) = None,
) -> tuple[dict[pd.Timestamp, list[Spinoff]], dict[tuple[str, pd.Timestamp], float]]:
    """The spin-offs of each appended session, and the child closes we lack.

    A child the panel already prices costs no request at all, which is the common
    case: the run's universe carries the spun-off ticker from the session it starts
    trading. The ones it does not price are asked for together, one request per
    session, because the alternative is a nulled return for a name the vendor can
    answer for.
    """
    found: dict[pd.Timestamp, list[Spinoff]] = {
        session: vendor_spinoffs(session, universe, fetcher=fetcher)
        for session in sessions
    }
    fetched: dict[tuple[str, pd.Timestamp], float] = {}
    for session, spinoffs in sorted(found.items()):
        children = sorted(
            {
                spinoff.child
                for spinoff in spinoffs
                if _close_on(prices_frame, spinoff.child, session) is None
            }
        )
        if not children:
            continue
        values = (child_closes_fetcher or _default_child_closes)(children, session)
        for name, value in (values or {}).items():
            fetched[(str(name), session)] = float(value)
    return found, fetched


def _default_child_closes(
    symbols: list[str], session: pd.Timestamp
) -> dict[str, float]:
    """The children's raw closes for one session, from the vendor."""
    from live import alpaca  # noqa: PLC0415 - the vendor, imported late

    return alpaca.closes_on(symbols, session)


def child_close_lookup(
    prices_frame: pd.DataFrame, fetched: dict[tuple[str, pd.Timestamp], float]
) -> Callable[[str, pd.Timestamp], float | None]:
    """A lookup that prefers the panel and falls back to what was fetched."""

    def lookup(child: str, session: pd.Timestamp) -> float | None:
        value = _close_on(prices_frame, child, session)
        if value is not None:
            return value
        return fetched.get((str(child), pd.Timestamp(session)))

    return lookup


def adjusted_returns_for_session(
    raw_closes: pd.Series, previous_closes: pd.Series, splits: list[Split]
) -> pd.Series:
    """The raw-close returns of one session, with the factor applied per split.

    This is what replaces the back-adjusted arithmetic for the affected tickers on
    the appended session. Every other ticker keeps the vendor's own adjusted
    return, and no stored row is touched.
    """
    out: dict[str, float] = {}
    for split in splits:
        ticker = split.ticker
        if ticker not in raw_closes.index or ticker not in previous_closes.index:
            continue
        out[ticker] = adjusted_return(
            close_t=float(raw_closes[ticker]),
            factor=float(split.factor),
            close_previous=float(previous_closes[ticker]),
        )
    return pd.Series(out, dtype=float)


CROSS_CHECK_MOVE = 0.10
MAX_CROSS_CHECKS = 30


@dataclass(frozen=True)
class Outcome:
    """What the append path did, for the run's record and for its message."""

    returns: pd.DataFrame
    splits: list[Split]
    ratios: dict[str, float]
    flags: list[dict[str, Any]]
    cross_checked: list[str]
    sessions: list[pd.Timestamp]
    # The names the request cap stopped the cross-check from reaching. Never an
    # error, and never invisible: the run records them and the message says so.
    unchecked: list[str]
    # The spin-offs applied to the appended sessions, one record per parent row the
    # rule corrected (or nulled, when the child's close could not be read).
    spinoffs: list[SpinoffOutcome] = field(default_factory=list)


def appended_sessions(
    frame: pd.DataFrame, since: pd.Timestamp | None
) -> list[pd.Timestamp]:
    """The sessions in `frame` newer than the last one already held."""
    dates = {pd.Timestamp(d) for d in frame.index.get_level_values("date").unique()}
    if since is None:
        return sorted(dates)
    floor = pd.Timestamp(since)
    return sorted(date for date in dates if date > floor)


def split_factor_of(value: Any) -> float | None:
    """The factor when the vendor's column marks a split, else None.

    The vendor writes `0.0` for a session with no split and `NaN` for one it has no
    row for, both of which mean none; `1.0` is not a split either; and a negative or
    non-finite value cannot be a share ratio. Everything else is the factor, in new
    shares per old share, which is how `2.0` sits on APH's 2026-09-03 row beside the
    raw close that halves the next session.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):  # pragma: no cover - a non-scalar cell
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0 or abs(number - 1.0) <= 1e-9:
        return None
    return number


def _cell(
    prices_frame: pd.DataFrame, session: pd.Timestamp, ticker: str, column: str
) -> Any:
    """One cell of the price frame, or None when there is no such row."""
    try:
        return prices_frame.loc[(session, ticker), column]
    except (KeyError, IndexError):
        return None


def split_flag_tickers(prices_frame: pd.DataFrame, session: pd.Timestamp) -> list[str]:
    """Tickers the vendor's own action column marks as splitting on this session.

    `raw/prices.parquet` carries the vendor's `split_factor` per row, so the primary
    detection needs no request at all: every split the vendor reports for the
    sessions being appended is already visible in the frame.
    """
    if "split_factor" not in prices_frame.columns:
        return []
    dates = prices_frame.index.get_level_values("date")
    if session not in set(dates):
        return []
    block = prices_frame.loc[session]
    if "split_factor" not in getattr(block, "columns", []):
        return []
    flagged: list[str] = []
    for ticker, value in block["split_factor"].items():
        if split_factor_of(value) is not None:
            flagged.append(str(ticker))
    return sorted(flagged)


def _stored_pair(
    prices_frame: pd.DataFrame, ticker: str, session: pd.Timestamp
) -> tuple[pd.Timestamp | None, float | None, float | None]:
    """The last stored session before `session` with a close, and both its values.

    Returns the date, that session's raw close and its adjusted close. The raw
    close is what a split-adjusted return divides by; the adjusted close is what
    the cross-check compares against a refetch, because only a corporate action
    moves it.
    """
    tickers = prices_frame.index.get_level_values("ticker")
    if ticker not in set(tickers):
        return None, None, None
    block = prices_frame.xs(ticker, level="ticker")
    earlier = block.loc[block.index < session]
    if earlier.empty:
        return None, None, None
    earlier = earlier.dropna(subset=["close"])
    if earlier.empty:
        return None, None, None
    when = pd.Timestamp(earlier.index[-1])
    row = earlier.iloc[-1]
    adjusted = row.get("adj_close")
    return when, float(row["close"]), None if pd.isna(adjusted) else float(adjusted)


def _close_on(
    prices_frame: pd.DataFrame, ticker: str, session: pd.Timestamp
) -> float | None:
    tickers = prices_frame.index.get_level_values("ticker")
    if ticker not in set(tickers) or session not in set(
        prices_frame.index.get_level_values("date")
    ):
        return None
    value = prices_frame.loc[(session, ticker), "close"]
    if value is None or pd.isna(value):
        return None
    return float(value)


def _default_refetch(ticker: str, session: pd.Timestamp) -> float:
    """The vendor's adjusted close for one session, refetched today."""
    import yfinance as yf  # noqa: PLC0415 - the vendor, imported late

    start = pd.Timestamp(session).date().isoformat()
    end = (pd.Timestamp(session) + pd.Timedelta(days=1)).date().isoformat()
    history = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
    if history.empty:
        raise ValueError(f"{ticker}: the vendor returned no adjusted close for {start}")
    return float(history["Close"].iloc[0])


def cap_note(unchecked: list[str]) -> str:
    """The line that says the cap was hit, or an empty string.

    It is never an error: the names are still flagged, and a move above 40% is
    still reported. What it must never be is invisible.
    """
    if not unchecked:
        return ""
    return (
        f"cross-check capped: {len(unchecked)} unchecked "
        f"({', '.join(unchecked[:5])})"
    )


def _check_one(
    ticker: str,
    session: pd.Timestamp,
    prices_frame: pd.DataFrame,
    split_fetcher: Callable[[str], Any] | None,
    close_fetcher: Callable[[str, pd.Timestamp], float] | None,
    patch: bool,
    frame: pd.DataFrame,
) -> tuple[Split | None, float | None, bool]:
    """Cross-check one ticker against the vendor and resolve what it means.

    Returns the split (when there is one), the ratio and whether a request was
    spent. A ratio away from 1 that no record explains stops the run, naming the
    ticker, rather than being guessed at. A ticker the vendor's own column flags is
    resolved first, so a split is recorded even when the session before it has no
    close to compute a return against.
    """
    factor = split_factor_of(_cell(prices_frame, session, ticker, "split_factor"))
    when, previous_close, stored_adjusted = _stored_pair(prices_frame, ticker, session)
    records = vendor_splits(ticker, fetcher=split_fetcher) if factor is not None else []
    ratio: float | None = None
    spent = False
    if stored_adjusted is not None:
        refetched = (
            _default_refetch(ticker, when)
            if close_fetcher is None
            else float(close_fetcher(ticker, when))
        )
        spent = True
        ratio = cross_check_ratio(stored_adjusted, refetched)
    if ratio is not None and abs(ratio - 1.0) > CROSS_CHECK_TOLERANCE:
        split = resolve_split(ticker, ratio, records, session=session)
    elif factor is not None:
        near = [
            record
            for record in records
            if record.effective_date >= session - pd.Timedelta(days=SPLIT_LOOKBACK_DAYS)
        ]
        if not near:
            raise ValueError(
                f"{ticker}: the vendor's split factor {factor:g} on "
                f"{session.date()} has no split record behind it, so the run stops "
                f"rather than guessing"
            )
        split = near[-1]
    else:
        return None, ratio, spent
    if split is None:
        return None, ratio, spent
    if patch and previous_close is not None and (session, ticker) in frame.index:
        today = _close_on(prices_frame, ticker, session)
        if today is not None:
            _set_return(
                frame,
                session,
                ticker,
                adjusted_return(
                    close_t=today, factor=split.factor, close_previous=previous_close
                ),
            )
    return split, ratio, spent


def apply_to_append(
    returns_frame: pd.DataFrame,
    prices_frame: pd.DataFrame,
    since: pd.Timestamp | None,
    split_fetcher: Callable[[str], Any] | None = None,
    close_fetcher: Callable[[str, pd.Timestamp], float] | None = None,
    max_cross_checks: int = MAX_CROSS_CHECKS,
    spinoffs: dict[pd.Timestamp, list[Spinoff]] | None = None,
    child_close: Callable[[str, pd.Timestamp], float | None] | None = None,
) -> Outcome:
    """Apply the corporate-actions rule to the sessions this run is appending.

    Two passes over each appended session. The vendor's own `split_factor` column
    names the tickers that split, which costs no request; then the tickers whose
    appended move is large are cross-checked as well, which is the only cover for a
    split the vendor restates without reporting. Both paths start from a refetch of
    the last stored session's adjusted close, and a ratio no record explains stops
    the run before any artifact is written.

    Spin-offs are the third pass and a different animal: they are not detected from
    the frame at all, they are handed in per session as the vendor's own records,
    and the parent's return is computed from the parent's and the child's raw closes
    plus the share ratio. `child_close` is where a child the panel does not price is
    read from. Neither of the two things that can go wrong here stops the run: a
    child close that cannot be read, and a record the rule cannot use at all, each
    null that one cell, and the message names the name and the reason.
    """
    sessions = appended_sessions(returns_frame, since)
    if not sessions:
        return Outcome(returns_frame, [], {}, [], [], [], [])
    splits: list[Split] = []
    ratios: dict[str, float] = {}
    cross_checked: list[str] = []
    events: list[SpinoffOutcome] = []
    frame = returns_frame
    for session in sessions:
        for ticker in split_flag_tickers(prices_frame, session):
            split, ratio, spent = _check_one(
                ticker, session, prices_frame, split_fetcher, close_fetcher, True, frame
            )
            if ratio is not None:
                ratios[ticker] = ratio
            if spent:
                cross_checked.append(ticker)
            if split is not None:
                splits.append(split)
        for spinoff in (spinoffs or {}).get(session, []):
            event = _apply_spinoff(frame, prices_frame, spinoff, child_close)
            if event is not None:
                events.append(event)
        if session not in frame.index:
            continue
        row = frame.loc[session, "r"]
        watched = [
            str(ticker)
            for ticker, value in row.items()
            if not pd.isna(value) and abs(float(value)) > CROSS_CHECK_MOVE
        ]
        for ticker in watched[:max_cross_checks]:
            if ticker in cross_checked:
                continue
            split, ratio, spent = _check_one(
                ticker,
                session,
                prices_frame,
                split_fetcher,
                close_fetcher,
                False,
                frame,
            )
            if ratio is not None:
                ratios[ticker] = ratio
            if spent:
                cross_checked.append(ticker)
    last = sessions[-1]
    tail = frame.loc[last, "r"] if last in frame.index else pd.Series(dtype=float)
    explained = {split.ticker: describe([split]) for split in splits}
    explained.update(
        {
            event.spinoff.parent: event.spinoff.label
            for event in events
            if event.session == last and event.spinoff.applicable
        }
    )
    flags = flag_large_moves(tail, explained=explained)
    # The spin-off's own flag replaces whatever the post-correction move produced for
    # that name, because the print worth recording is the one the rule replaced.
    corrected = {event.spinoff.parent for event in events if event.session == last}
    flags = [flag for flag in flags if flag["ticker"] not in corrected]
    flags.extend(spinoff_flags(events, last))
    flags.sort(key=lambda flag: abs(flag.get("return") or 0.0), reverse=True)
    watched_last = [
        str(ticker)
        for ticker, value in tail.items()
        if not pd.isna(value) and abs(float(value)) > CROSS_CHECK_MOVE
    ]
    unchecked = [ticker for ticker in watched_last if ticker not in cross_checked]
    return Outcome(
        frame, splits, ratios, flags, cross_checked, sessions, unchecked, events
    )


def apply_to_artifact(
    data_root: Any,
    since: pd.Timestamp | None,
    split_fetcher: Callable[[str], Any] | None = None,
    close_fetcher: Callable[[str, pd.Timestamp], float] | None = None,
    max_cross_checks: int = MAX_CROSS_CHECKS,
    spinoff_fetcher: (
        Callable[[list[str], pd.Timestamp], list[dict[str, Any]]] | None
    ) = None,
    child_closes_fetcher: (
        Callable[[list[str], pd.Timestamp], dict[str, float]] | None
    ) = None,
) -> Outcome:
    """Apply the rule to the artifact's appended sessions and write it back.

    Only the sessions this run appended are touched, and inside them only the
    tickers a corporate action moved, so every stored row keeps its value. The
    frame is written back only when a split or a spin-off was actually applied,
    which is what keeps an ordinary evening's artifact byte-identical.

    The spin-off request is the one thing here that can fail without the run
    failing: a vendor read that raises is logged and the rule is skipped for that
    session, which leaves the raw print in place where the 40% flag names it as an
    unexplained large move. That is the same position the loop was in before this
    rule existed, and it is visible rather than silent.
    """
    from pathlib import Path

    root = Path(data_root)
    returns_path = root / "processed" / "returns.parquet"
    frame = pd.read_parquet(returns_path)
    prices_frame = pd.read_parquet(
        root / "raw" / "prices.parquet", columns=["close", "adj_close", "split_factor"]
    )
    sessions = appended_sessions(frame, since)
    found: dict[pd.Timestamp, list[Spinoff]] = {}
    fetched: dict[tuple[str, pd.Timestamp], float] = {}
    if sessions:
        universe = sorted(
            {str(ticker) for ticker in prices_frame.index.get_level_values("ticker")}
        )
        try:
            found, fetched = resolve_spinoffs(
                sessions,
                universe,
                prices_frame,
                fetcher=spinoff_fetcher,
                child_closes_fetcher=child_closes_fetcher,
            )
        except Exception as exc:  # noqa: BLE001 - a read that may fail, named
            logger.warning(
                "could not read the vendor's spin-offs for %s: %s: %s",
                ", ".join(str(session.date()) for session in sessions),
                type(exc).__name__,
                exc,
            )
            found, fetched = {}, {}
    outcome = apply_to_append(
        frame,
        prices_frame,
        since,
        split_fetcher=split_fetcher,
        close_fetcher=close_fetcher,
        max_cross_checks=max_cross_checks,
        spinoffs=found,
        child_close=child_close_lookup(prices_frame, fetched),
    )
    if outcome.splits or outcome.spinoffs:
        outcome.returns.to_parquet(returns_path)
    return outcome


def cumulative_factor(splits: list[Split], since: pd.Timestamp) -> float:
    """The factor to apply to a price level read from before `since`.

    For a consumer that reads *levels* across the seam. Returns do not need it:
    they are computed within each basis.
    """
    factor = 1.0
    floor = pd.Timestamp(since)
    for split in splits:
        if split.effective_date > floor:
            factor *= float(split.factor)
    return factor


def shares_basis_factor(
    newest_share_date: pd.Timestamp | None, split: Split | None
) -> float:
    """The factor to apply to a share count, or 1.0 when it is already restated.

    The lag is detected by date: while the newest stored count predates the
    split's effective date the count is on the old basis and the factor applies.
    Nothing is inferred from the size of the number.
    """
    if split is None or newest_share_date is None or pd.isna(newest_share_date):
        return 1.0
    newest = pd.Timestamp(newest_share_date)
    return 1.0 if newest >= split.effective_date else float(split.factor)


def held_notional_across_split(prior_notional: float) -> float:
    """A held position's notional across a split: unchanged.

    The broker doubles the share count and halves the price, so the money is the
    same. Rebuilding the position from the share count would double the trade.
    """
    return float(prior_notional)


def held_shares_across_split(prior_shares: float, factor: float) -> float:
    """A held share count across a split, in post-split shares."""
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError("the split factor must be a positive number")
    return float(prior_shares) * float(factor)


def trade_across_split(target_notional: float, prior_notional: float) -> float:
    """The traded leg for a target held through a split: the difference only."""
    return abs(float(target_notional) - held_notional_across_split(prior_notional))


def large_moves(returns: pd.Series, threshold: float = LARGE_MOVE) -> pd.DataFrame:
    """Appended name-days above the threshold, largest first."""
    if len(returns) == 0:
        return pd.DataFrame(columns=["ticker", "return"])
    values = returns.dropna()
    big = values.loc[values.abs() > threshold]
    frame = big.rename("return").reset_index()
    return frame.sort_values("return", key=lambda s: s.abs(), ascending=False)


def flag_large_moves(
    returns: pd.Series,
    explained: dict[str, str] | None = None,
    threshold: float = LARGE_MOVE,
) -> list[dict[str, Any]]:
    """Every large move with its explanation, or flagged as unexplained.

    A real crash is a real return, so an unexplained move is reported rather than
    blocked: the owner reads it in the message and in `run_status`.
    """
    explained = explained or {}
    flags: list[dict[str, Any]] = []
    # positional unpacking: the second column is named `return`, which is a
    # keyword and so cannot be reached as an attribute
    for ticker, move in large_moves(returns, threshold).itertuples(
        index=False, name=None
    ):
        name = str(ticker)
        reason = explained.get(name)
        flags.append(
            {
                "ticker": name,
                "return": float(move),
                "explained_by": reason,
                "flag": "unexplained large move" if reason is None else reason,
            }
        )
    return flags


def rows(
    splits: list[Split],
    trade_date: pd.Timestamp,
    ratios: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """The appendix rows for the splits applied to one session."""
    ratios = ratios or {}
    stamp = pd.Timestamp(trade_date).date().isoformat()
    return [
        {
            "trade_date": stamp,
            "ticker": split.ticker,
            "effective_date": split.effective_date.date().isoformat(),
            "factor": float(split.factor),
            "source": split.source,
            "cross_check_ratio": ratios.get(split.ticker),
            "explained_by": "split",
            "new_ticker": None,
            "source_rate": None,
            "new_rate": None,
        }
        for split in splits
    ]


def events(trade_date: pd.Timestamp) -> pd.DataFrame:
    """The splits recorded for one session, read back from the appendix."""
    frame = store.select(TABLE)
    if frame.empty:
        return frame
    stamp = pd.Timestamp(trade_date).date().isoformat()
    return frame.loc[frame["trade_date"].astype(str) == stamp]


def describe(splits: list[Split]) -> str:
    """`split: APH 2:1 applied`, or an empty string when nothing happened."""
    if not splits:
        return ""
    parts = [f"{split.ticker} {split.ratio_label}" for split in splits]
    return "split: " + ", ".join(parts) + " applied"
