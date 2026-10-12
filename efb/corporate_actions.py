"""The research record of vendor spin-offs (E1 -> E3 and downstream).

Sprint E11 taught that a spin-off moves exactly one session's return and that
neither price vendor adjusts history for it, so the stored prices alone can never
produce the right number: the correction is a recorded fact rather than a derived
one. The research panel had no such record, so its returns build read the price
vendor's own arithmetic and, on the sessions where that arithmetic is wrong, fitted
the wrong number. Measured before this module existed: 30 vendor records over the
panel's life, the outlier filter catching none of them, and one session (APTV,
2026-04-01) carrying a -10.58% print where the true total return was +2.78%.

Two halves, kept apart on purpose:

- `collect` asks the vendor for the records and for each child's ex-date close, and
  writes them to `processed/corporate_actions.parquet`. It is the only part that
  talks to a network.
- `recorded` and `apply` read that table and put the correction back into the
  returns frame. They touch no network, so the fit stays reproducible from the
  artifacts on disk.

The rule itself is not restated here. `live/corporate_actions.py` owns it - the
arithmetic, the null-instead-of-a-wrong-number choice, the raw print that stays in
the flag - and this module calls it, because two implementations of the same rule
is how the research panel and the live book would come to disagree.

**The vendor's table is incomplete and it is not stable.** Measured on 2026-10-03:
the same per-year read returned 30 records in the morning and 28 in the afternoon,
and a single wide window over 2018-2026 returned 2. Two known spin-offs -
Tulip's `FTI -> THNPF` (2021-02-16, Technip Energies) and `EXC -> CEG`
(2022-02-02, Constellation Energy) - were in the first read and are in none of the
later ones, including a read that asks for those two symbols alone. The table is
therefore a dated snapshot rather than a complete history, `recorded_at` says when
it was taken, and `summary` reports where it starts and stops so a gap is visible
instead of being read as "no spin-offs happened then".
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    # The rule and its record types belong to `live/corporate_actions.py` and are
    # imported lazily at every call site, because this module is the research side
    # and must not make the live package a hard dependency of the build. The
    # annotations still name them: a `list[object]` here would hide the fact that
    # these are the live rule's own records.
    from live.corporate_actions import Spinoff, SpinoffOutcome

logger = logging.getLogger(__name__)

TABLE = "processed/corporate_actions.parquet"

# The columns the table carries. `new_ticker` is the symbol the rule prices,
# `vendor_symbol` is the symbol the vendor named: they differ for a when-issued
# line, which is the same security under a temporary suffix and has no bars of its
# own to read. A reader needs both or they cannot tell an alias from a rename.
COLUMNS = [
    "first_seen",
    "last_seen",
    "ticker",
    "effective_date",
    "new_ticker",
    "vendor_symbol",
    "factor",
    "source_rate",
    "new_rate",
    "child_close",
    "parent_close",
    "parent_prior_close",
    "prior_session",
    "action_kind",
    "source",
    "explained_by",
    "cross_check_ratio",
]

# What identifies one economic event across reads: the parent and the ex-date. The
# child symbol is carried on the row and refreshed from the latest read, but it is not
# part of the key - a vendor that renames a temporary line must not turn one event
# into two rows.
KEY = ("ticker", "effective_date")

# The fields a read supplies from the vendor's bars rather than from the record. A
# later read that does not carry them leaves the stored ones alone.
PRICE_PAYLOAD = (
    "factor",
    "child_close",
    "parent_close",
    "parent_prior_close",
    "prior_session",
)

# A *when-issued* line (`-WI`) is the same security under a temporary symbol, so the
# bars endpoint prices the base symbol and the rule is handed that. A *warrant* line
# (`-WS`) is a different instrument altogether: stripping the suffix would price the
# parent's own symbol as if it were the distribution and double-count it, which is
# measured - it turned GME's 2025-10-03 session from -6.8 percent into +2.6 percent.
# A warrant record is kept, priced on no symbol, and the rule nulls the one cell
# rather than leaving a print that ignores what the holder was paid.
TEMPORARY_SUFFIXES = (".WI",)
WARRANT_SUFFIX = ".WS"


def _vendor_imports() -> object:
    """The vendor modules, imported late.

    `live.alpaca` reads credentials and imports alpaca-py, so importing it at
    module scope would make `import efb.corporate_actions` a network-shaped
    dependency for every caller, including the tests that only read a table.
    """
    from live import alpaca

    return alpaca


def priceable_symbol(vendor_symbol: str) -> tuple[str, str]:
    """The symbol to price and the kind of action, from the vendor's own symbol.

    A `-WI` (when issued) line is the same distribution under a temporary symbol, so
    the suffix is stripped and the base symbol is priced. A `-WS` (warrant) line is
    kept as it stands: it is not the parent, the vendor does not price it, and the
    record says so rather than being applied to the wrong security.
    """
    symbol = str(vendor_symbol or "").strip().upper()
    for suffix in TEMPORARY_SUFFIXES:
        if symbol.endswith(suffix):
            return symbol[: -len(suffix)], suffix.strip(".")
    if symbol.endswith(WARRANT_SUFFIX):
        return symbol, WARRANT_SUFFIX.strip(".")
    return symbol, "share_distribution"


def _panel_span(root: Path) -> tuple[object | None, object | None]:
    """The panel's first and last session, from whichever panel is on disk.

    The returns table is the panel of record; a root that has only been through
    the price download answers with the raw panel instead, and a root with neither
    answers with nothing rather than raising, because the caller may have passed
    its own years.
    """
    for rel in ("processed/returns.parquet", "raw/prices.parquet"):
        path = root / rel
        if not path.exists():
            continue
        dates = pd.read_parquet(path).index.get_level_values("date")
        return dates.min(), dates.max()
    return None, None


def collect(
    data_root: Path,
    *,
    universe: list[str] | None = None,
    years: tuple[int, ...] | None = None,
    spin_off_fetcher: Callable[..., Any] | None = None,
    close_fetcher: Callable[..., Any] | None = None,
    parent_fetcher: Callable[..., Any] | None = None,
    store: bool = True,
    seen_at: str | None = None,
) -> pd.DataFrame:
    """Ask the vendor for every spin-off over the panel's universe, and store it.

    One request per year for the records, then one per record for the child's
    ex-date close. The close is written into the table rather than fetched at build
    time so the returns build can be re-run from the artifacts alone; the column is
    null for a child the vendor will not price, and the rule turns that into a hole
    rather than into a raw print read as a return.

    `universe` defaults to every ticker in the stored price panel, which is what
    makes this the panel's own history rather than the index's. The vendor's
    spin-off table has a floor - measured at 2019-02-25 for these names, with
    nothing at all in 2012-2018 - so this cannot reach the early panel, and the
    recorded rows say so by where they start.
    """
    root = Path(data_root)
    prices_path = root / "raw" / "prices.parquet"
    if universe is None:
        prices = pd.read_parquet(prices_path)
        universe = sorted(prices.index.get_level_values("ticker").unique().tolist())
    names = sorted({str(name) for name in universe if str(name)})
    first, last = _panel_span(root)
    if years is None and (first is None or last is None):
        raise ValueError(
            "no returns or prices panel in this root, so the years to ask for "
            "cannot be derived: pass `years`"
        )
    wanted = (
        years
        if years is not None
        else tuple(range(pd.Timestamp(first).year, pd.Timestamp(last).year + 1))
    )
    fetch = spin_off_fetcher or _vendor_spin_offs
    records: list[dict[str, Any]] = []
    for year in wanted:
        for record in fetch(names, year) or []:
            when = pd.Timestamp(record.get("ex_date"))
            if when.year != year:
                continue
            records.append(dict(record))
    rows: list[dict[str, Any]] = []
    started = seen_at or pd.Timestamp.now().isoformat(timespec="seconds")
    for record in sorted(
        records, key=lambda item: (str(item.get("ex_date")), str(item.get("parent")))
    ):
        vendor_symbol = str(record.get("child") or "").strip()
        child, kind = priceable_symbol(vendor_symbol)
        source_rate = float(record.get("source_rate") or 0.0)
        new_rate = float(record.get("new_rate") or 0.0)
        ratio = new_rate / source_rate if source_rate and new_rate else None
        if kind == "WS":
            # A warrant distribution has no child share to price, so there is no
            # ratio to apply: the record stays and the cell is nulled by the rule.
            ratio = None
        ex_date = pd.Timestamp(record.get("ex_date"))
        close = None
        if child and kind != "WS":
            close = _child_close(
                close_fetcher or _vendor_close, child, ex_date, source_rate
            )
        # The parent's own two closes come from the vendor's bars as well, and for a
        # reason that is easy to miss: a *research* panel is delivered back-adjusted,
        # so its close for the session before the ex-date already has the child's
        # value taken out of it. The rule wants raw closes on both sides, so feeding
        # it the panel's restated close double-counts the distribution - measured on
        # GE's 2024-04-02 GE Vernova spin-off, the panel's prior close is 139.95
        # against the vendor's raw 175.36, and the rule on the panel's own numbers
        # gives +22.5 percent for a session the stock fell in.
        parent_close, prior_close, prior_session = _parent_closes(
            parent_fetcher or _vendor_parent_closes,
            str(record.get("parent") or ""),
            ex_date,
        )
        rows.append(
            {
                "first_seen": started,
                "last_seen": started,
                "ticker": str(record.get("parent") or ""),
                "effective_date": ex_date.date().isoformat(),
                "new_ticker": child,
                "vendor_symbol": vendor_symbol,
                "factor": ratio,
                "source_rate": source_rate,
                "new_rate": new_rate,
                "child_close": close,
                "parent_close": parent_close,
                "parent_prior_close": prior_close,
                "prior_session": (
                    prior_session.date().isoformat()
                    if prior_session is not None
                    else None
                ),
                "action_kind": kind,
                "source": "alpaca.corporate_actions",
                "explained_by": "spinoff",
                "cross_check_ratio": None,
            }
        )
    frame = pd.DataFrame(rows, columns=COLUMNS)
    merged = merge_frame(read(data_root), frame)
    if store:
        (root / "processed").mkdir(parents=True, exist_ok=True)
        merged.to_parquet(root / TABLE, index=False)
    return merged


def merge_frame(stored: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    """The union of the stored table and one read, keyed on the event.

    Every read is kept. A record the vendor reports today is refreshed and its
    `last_seen` moves; a record it has stopped reporting keeps everything it had
    and stays applied, because the correction it carries is a fact about the
    security and not about the vendor's current answer. This is measured, not
    defensive: the same per-year read returned 30 records in the morning and 28 in
    the afternoon, and two real spin-offs - `FTI -> THNPF` and `EXC -> CEG` - were in
    the first and in none of the later reads, including one that asked for those two
    symbols alone. Replacing the table on every read would have silently dropped
    them and reverted two sessions to the vendor's own arithmetic.
    """
    if stored is None or len(stored) == 0:
        return fresh.reset_index(drop=True)
    if fresh is None or len(fresh) == 0:
        return stored.reset_index(drop=True)
    stored = stored.copy()
    fresh = fresh.copy()
    for frame in (stored, fresh):
        for column in COLUMNS:
            if column not in frame.columns:
                frame[column] = None
    keys = [tuple(str(row[column]) for column in KEY) for _, row in fresh.iterrows()]
    fresh = fresh.set_index(pd.Index(keys, tupleize_cols=False, name="_key"))
    stored_keys = [
        tuple(str(row[column]) for column in KEY) for _, row in stored.iterrows()
    ]
    stored = stored.set_index(pd.Index(stored_keys, tupleize_cols=False, name="_key"))
    kept_first = stored["first_seen"]
    kept_last = stored["last_seen"]
    updated = fresh.join(
        kept_first.rename("stored_first_seen"), how="left", on="_key"
    ).join(kept_last.rename("stored_last_seen"), how="left", on="_key")
    updated["first_seen"] = updated["stored_first_seen"].where(
        updated["stored_first_seen"].notna(), updated["first_seen"]
    )
    # The clock only moves forward: folding a read taken this morning into a table
    # that has already seen this afternoon's must not date the record backwards.
    updated["last_seen"] = [
        max(str(older), str(newer))
        for older, newer in zip(
            updated["stored_last_seen"], updated["last_seen"], strict=True
        )
    ]
    updated = updated.drop(columns=["stored_first_seen", "stored_last_seen"])
    # A read may carry less than the table already knows - a cached answer taken
    # before the closes were read is the case that matters - so the price payload is
    # refreshed where the read has it and kept where it does not. Blanking it would
    # turn an applied correction back into a nulled cell.
    for column in PRICE_PAYLOAD:
        stored_column = stored[column].reindex(updated.index)
        updated[column] = updated[column].where(updated[column].notna(), stored_column)
    untouched = stored.loc[~stored.index.isin(set(updated.index))]
    out = pd.concat([updated, untouched])
    out = out.reset_index(drop=True)
    return (
        out[COLUMNS]
        .sort_values(["effective_date", "ticker", "vendor_symbol"], kind="stable")
        .reset_index(drop=True)
    )


def merge(
    data_root: Path,
    records: list[dict[str, Any]],
    *,
    seen_at: str,
    source: str = "alpaca.corporate_actions",
    store: bool = True,
    close_fetcher: Callable[..., Any] | None = None,
    parent_fetcher: Callable[..., Any] | None = None,
) -> pd.DataFrame:
    """Fold a read that was taken earlier into the table.

    For a read somebody already has - a cached answer from a script, a copy taken
    before a rebuild - so it can be on the record with the date it was seen rather
    than being lost or re-dated. A record whose read carried no closes has them read
    from the vendor at merge time: a record that cannot be applied is a nulled cell,
    and the point of keeping a dropped record is that its correction still lands.
    """
    rows: list[dict[str, Any]] = []
    for record in records:
        vendor_symbol = str(record.get("new_symbol") or record.get("child") or "")
        child, kind = priceable_symbol(vendor_symbol)
        source_rate = float(record.get("source_rate") or 0.0)
        new_rate = float(record.get("new_rate") or 0.0)
        ratio = new_rate / source_rate if source_rate and new_rate else None
        if kind == "WS":
            ratio = None
        ex_date = pd.Timestamp(record["ex_date"])
        close = record.get("child_close")
        if close is None and child and kind != "WS":
            close = _child_close(
                close_fetcher or _vendor_close, child, ex_date, source_rate
            )
        parent_close = record.get("parent_close")
        prior_close = record.get("parent_prior_close")
        prior_session = record.get("prior_session")
        if parent_close is None or prior_close is None:
            parent_close, prior_close, prior_session = _parent_closes(
                parent_fetcher or _vendor_parent_closes,
                str(record.get("parent") or record.get("source_symbol") or ""),
                ex_date,
            )
        rows.append(
            {
                "first_seen": seen_at,
                "last_seen": seen_at,
                "ticker": str(
                    record.get("parent") or record.get("source_symbol") or ""
                ),
                "effective_date": ex_date.date().isoformat(),
                "new_ticker": child,
                "vendor_symbol": vendor_symbol,
                "factor": ratio,
                "source_rate": source_rate,
                "new_rate": new_rate,
                "child_close": None if pd.isna(close) else close,
                "parent_close": None if pd.isna(parent_close) else parent_close,
                "parent_prior_close": None if pd.isna(prior_close) else prior_close,
                "prior_session": (
                    pd.Timestamp(prior_session).date().isoformat()
                    if prior_session is not None and not pd.isna(prior_session)
                    else None
                ),
                "action_kind": kind,
                "source": source,
                "explained_by": "spinoff",
                "cross_check_ratio": None,
            }
        )
    frame = merge_frame(read(data_root), pd.DataFrame(rows, columns=COLUMNS))
    if store:
        (Path(data_root) / "processed").mkdir(parents=True, exist_ok=True)
        frame.to_parquet(Path(data_root) / TABLE, index=False)
    return frame


def _vendor_spin_offs(symbols: list[str], year: int) -> list[dict[str, Any]]:
    """One year's records from the vendor's corporate-actions endpoint.

    `live.alpaca.spin_offs` answers for one session - it takes a window and then
    keeps only the records whose ex-date is that exact day - so it cannot be asked
    for a year. This is the same endpoint read the same way, one request per year,
    and it returns the same record shape so the two readers cannot disagree about
    what a field means.
    """
    from datetime import date, timedelta  # noqa: PLC0415 - only this call needs it

    alpaca = _vendor_imports()
    client = alpaca.corporate_actions_client()  # type: ignore[attr-defined]
    try:
        from alpaca.data.requests import (  # type: ignore[import-not-found]
            CorporateActionsRequest,
        )
    except ImportError as exc:  # pragma: no cover - the vendor is optional
        raise RuntimeError(
            "the corporate-actions read needs alpaca-py; install it"
        ) from exc
    names = sorted({str(name) for name in symbols if str(name)})
    if not names:
        return []
    response = client.get_corporate_actions(
        CorporateActionsRequest(
            symbols=names,
            start=date(year, 1, 1),
            end=date(year, 12, 31) + timedelta(days=1),
        )
    )
    out: list[dict[str, Any]] = []
    for item in (getattr(response, "data", None) or {}).get("spin_offs") or []:
        ex_date = getattr(item, "ex_date", None)
        if ex_date is None:
            continue
        out.append(
            {
                "parent": str(getattr(item, "source_symbol", "") or ""),
                "child": str(getattr(item, "new_symbol", "") or ""),
                "ex_date": pd.Timestamp(ex_date),
                "source_rate": float(getattr(item, "source_rate", 0.0) or 0.0),
                "new_rate": float(getattr(item, "new_rate", 0.0) or 0.0),
            }
        )
    return sorted(out, key=lambda record: (record["parent"], str(record["ex_date"])))


def _vendor_close(
    symbol: str, session: pd.Timestamp, source_rate: float = 0.0
) -> float | None:
    """One child's raw ex-date close from the vendor's bars."""
    alpaca = _vendor_imports()
    answers = alpaca.closes_on(  # type: ignore[attr-defined]
        [symbol], pd.Timestamp(session)
    )
    return answers.get(symbol)


def _child_close(
    fetcher: object,
    symbol: str,
    session: pd.Timestamp,
    source_rate: float,
) -> float | None:
    try:
        return fetcher(symbol, session, source_rate)  # type: ignore[operator]
    except TypeError:
        return fetcher(symbol, session)  # type: ignore[operator]


def _vendor_parent_closes(
    symbol: str, session: pd.Timestamp
) -> tuple[float | None, float | None, pd.Timestamp | None]:
    """The parent's raw ex-date close, its prior raw close and that session.

    Read from the vendor's bars over a short window around the ex-date, so the
    prior session is the vendor's own previous session rather than whichever row the
    panel happens to hold.
    """
    from datetime import datetime, timedelta  # noqa: PLC0415 - one call

    alpaca = _vendor_imports()
    try:
        from alpaca.data.enums import Adjustment, DataFeed  # type: ignore[import]
        from alpaca.data.requests import (  # type: ignore[import-not-found]
            StockBarsRequest,
        )
        from alpaca.data.timeframe import TimeFrame  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - the vendor is optional
        raise RuntimeError("the bars read needs alpaca-py; install it") from exc
    quoted = pd.Timestamp(session)
    start = quoted - timedelta(days=10)
    for feed in (DataFeed.SIP, DataFeed.IEX):
        try:
            response = alpaca.bars_client().get_stock_bars(  # type: ignore[attr-defined]
                StockBarsRequest(
                    symbol_or_symbols=[symbol],
                    timeframe=TimeFrame.Day,
                    start=datetime.combine(
                        start.date(), datetime.min.time(), tzinfo=UTC
                    ),
                    end=datetime.combine(
                        (quoted + timedelta(days=2)).date(),
                        datetime.min.time(),
                        tzinfo=UTC,
                    ),
                    feed=feed,
                    adjustment=Adjustment.RAW,
                )
            )
            break
        except Exception:  # noqa: BLE001 - the free plan refuses recent SIP
            continue
    else:
        return None, None, None
    closes: dict[pd.Timestamp, float] = {}
    for _symbol, series in (getattr(response, "data", None) or {}).items():
        for bar in series or []:
            stamp = pd.Timestamp(getattr(bar, "timestamp", None)).tz_localize(None)
            closes[stamp.normalize()] = float(bar.close)
    if not closes:
        return None, None, None
    ordered = sorted(closes)
    on_the_day = [day for day in ordered if day == quoted.normalize()]
    earlier = [day for day in ordered if day < quoted.normalize()]
    close = closes[on_the_day[-1]] if on_the_day else None
    prior = closes[earlier[-1]] if earlier else None
    prior_session = pd.Timestamp(earlier[-1]) if earlier else None
    return close, prior, prior_session


def _parent_closes(
    fetcher: object, symbol: str, session: pd.Timestamp
) -> tuple[float | None, float | None, pd.Timestamp | None]:
    if not symbol:
        return None, None, None
    try:
        return fetcher(symbol, session)  # type: ignore[operator]
    except Exception:  # noqa: BLE001 - a missing close becomes a nulled cell
        logger.warning("the parent's raw closes could not be read", exc_info=True)
        return None, None, None


def read(data_root: Path) -> pd.DataFrame:
    """The stored table, or an empty frame with the right columns.

    A root with no table reads as no records rather than as an error: a test tree
    and a fresh container have no vendor history behind them, and a build that
    refused to run without one could not be reproduced from its own artifacts.
    """
    path = Path(data_root) / TABLE
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    frame = pd.read_parquet(path)
    return frame


def ensure(data_root: Path, *, collect_missing: bool = False) -> pd.DataFrame:
    """The table, or an empty record when there is none.

    The read path the build takes. Collecting is a separate, explicit step
    (`collect`, and `scripts/collect_corporate_actions.py`) rather than something a
    rebuild does behind the caller's back: a build that silently reached the vendor
    would make the same command produce different numbers on different days, which
    is the property the artifact set exists to prevent. With `collect_missing` the
    E1 build may fetch it once; without it, a root with no table builds and says so.
    """
    frame = read(data_root)
    if not frame.empty or not collect_missing:
        return frame
    try:
        return collect(data_root)
    except Exception:  # noqa: BLE001 - the build goes on with no records
        logger.warning("the vendor's spin-off records could not be read", exc_info=True)
        return frame


def recorded(data_root: Path) -> list[Spinoff]:
    """The stored rows as the rule's own records.

    `live.corporate_actions.spinoffs_from_rows` is the reader, so the research table
    and the live appendix cannot drift apart in what a row means.
    """
    from live import corporate_actions

    return corporate_actions.spinoffs_from_rows(read(data_root))


def priced_frame(data_root: Path, prices_frame: pd.DataFrame) -> pd.DataFrame:
    """The price frame the rule reads, with the children's own closes added.

    A spun-off child usually is not in the panel at all - that is what makes it a
    spin-off - so the rule would find no close to price it with and would null the
    parent's cell instead of correcting it. The table carries that close, recorded
    from the vendor's bars, and this adds the one row per child the rule looks up.
    Nothing already in the frame is touched: a child the panel does price keeps the
    panel's own close, which is the same raw number.
    """
    frame = read(data_root)
    if frame.empty:
        return prices_frame
    overrides: list[tuple[pd.Timestamp, str, float]] = []
    for row in frame.to_dict("records"):
        when = pd.Timestamp(row["effective_date"])
        child = str(row.get("new_ticker") or "")
        child_close = row.get("child_close")
        if child and child_close is not None and not pd.isna(child_close):
            overrides.append((when, child, float(child_close)))
        # The parent's own two closes are overridden, not added: the panel's are
        # back-adjusted and the rule is written for raw ones. Only the ex-date and
        # its prior session are touched, so nothing else the rule reads moves.
        parent = str(row.get("ticker") or "")
        parent_close = row.get("parent_close")
        if parent and parent_close is not None and not pd.isna(parent_close):
            overrides.append((when, parent, float(parent_close)))
        prior_close = row.get("parent_prior_close")
        prior_session = row.get("prior_session")
        if (
            parent
            and prior_close is not None
            and not pd.isna(prior_close)
            and prior_session is not None
        ):
            overrides.append((pd.Timestamp(prior_session), parent, float(prior_close)))
    if not overrides:
        return prices_frame
    # Only `close` moves, which is the one column the rule reads. Building a whole
    # row instead would throw away the panel's other columns for those two sessions.
    keys = pd.MultiIndex.from_tuples(
        [(when, ticker) for when, ticker, _ in overrides], names=["date", "ticker"]
    )
    values = np.array([value for _, _, value in overrides], dtype=float)
    out = prices_frame.copy()
    present = keys.isin(out.index)
    out.loc[keys[present], "close"] = values[present]
    added = keys[~present]
    if len(added) == 0:
        return out
    extra = pd.DataFrame(
        {column: pd.NA for column in out.columns}, index=added, dtype=object
    )
    extra.index.names = ["date", "ticker"]
    extra["close"] = values[~present]
    return pd.concat([out, extra.astype(out.dtypes.to_dict(), errors="ignore")])


def apply(
    returns_frame: pd.DataFrame,
    prices_frame: pd.DataFrame,
    data_root: Path,
) -> tuple[pd.DataFrame, list[SpinoffOutcome]]:
    """Put the recorded spin-offs back into a returns frame.

    The caller passes the frame the build just computed and gets it back with the
    parent's own cell corrected on each recorded ex-date - nulled where the record
    cannot price the child - and the list of outcomes, so the log can name what
    moved. `apply_recorded` is the live rule, called rather than restated.
    """
    from live import corporate_actions

    records = recorded(data_root)
    if not records:
        return returns_frame, []
    frame = returns_frame.copy()
    outcomes = corporate_actions.apply_recorded(
        frame, priced_frame(data_root, prices_frame), records
    )
    if "corrected" not in frame.columns:
        frame["corrected"] = False
    for outcome in outcomes:
        key = (outcome.session, outcome.spinoff.parent)
        if key in frame.index:
            # The flag columns were computed on the vendor's numbers and are left
            # alone; this is the column that says the cell no longer holds one of
            # them, so a reader can tell a repaired cell from an untouched one and
            # `hygiene.clean_returns` knows not to mask what was just repaired.
            frame.loc[key, "corrected"] = True
        logger.info(
            "re-applied %s: the %s return on %s is %s where the prices alone give %s",
            outcome.spinoff.label,
            outcome.spinoff.parent,
            outcome.session.date(),
            outcome.adjusted_return,
            outcome.raw_return,
        )
    return frame, outcomes


def summary(data_root: Path) -> dict[str, object]:
    """What the table records, for the criterion's stored numbers.

    `records` is the union of every read, so it is not the vendor's current answer:
    the two differ wherever the vendor has dropped a record, and `stale_reads` names
    the rows that are on the record but were not in the latest one.
    """
    frame = read(data_root)
    if frame.empty:
        return {
            "records": 0,
            "first_ex_date": None,
            "last_ex_date": None,
            "applied": 0,
            "unpriced_children": [],
            "reads": [],
        }
    unpriced = frame.loc[
        frame["child_close"].isna(), ["ticker", "effective_date", "vendor_symbol"]
    ]
    latest = frame["last_seen"].max() if "last_seen" in frame.columns else None
    not_latest = (
        frame.loc[frame["last_seen"] != latest, ["ticker", "effective_date"]]
        if latest is not None
        else frame.iloc[0:0]
    )
    return {
        "records": int(len(frame)),
        "first_ex_date": str(frame["effective_date"].min()),
        "last_ex_date": str(frame["effective_date"].max()),
        "applied": int(frame["child_close"].notna().sum()),
        "unpriced_children": [
            f"{row['ticker']}->{row['vendor_symbol']} {row['effective_date']}"
            for row in unpriced.to_dict("records")
        ],
        "kinds": {
            str(kind): int(count)
            for kind, count in frame["action_kind"].value_counts().items()
        },
        # The read instants the table has seen: a row's `last_seen` is the read that
        # last carried it, so this is every read that touched the table rather than
        # every read that carried each row.
        "reads": (
            sorted(str(value) for value in frame["last_seen"].dropna().unique())
            if "last_seen" in frame.columns
            else []
        ),
        "latest_read": None if latest is None else str(latest),
        "not_in_the_latest_read": [
            f"{row['ticker']} {row['effective_date']}"
            for row in not_latest.to_dict("records")
        ],
    }


def as_json(data_root: Path) -> str:
    """The summary as a JSON string, for a stored criterion."""
    return json.dumps(summary(data_root), sort_keys=True)
