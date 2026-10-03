"""Record a spin-off in the appendix, so the returns rebuild puts it back.

Why a record and not a price edit: `extend_returns` recomputes every session from
the stored prices, and neither price vendor adjusts history for a spin-off, so a
correction that is not recorded is gone by the next evening. CTVA closed 77.65 on
2026-09-30 and printed 12.57 on 2026-10-01 (-83.81%) while the holder was also
given one VYLR share worth 68.26. The 2026-10-01 run had no record for it, flagged
the print as an unexplained large move, and fitted the whole 2026-10-02
cross-section from it.

The row this writes is the row the append path writes, field for field, so
`live.corporate_actions.spinoffs_from_rows` reads it back as the same record:

    trade_date       the session the parent's return belongs to
    ticker           the parent
    effective_date   the ex-date
    factor           the child's shares per parent share
    explained_by     "spinoff", which is what makes it a spin-off and not a split
    new_ticker       the child
    source_rate      the vendor's own source rate
    new_rate         the vendor's own new rate

Nothing is typed in: the closes are read from the same two places the rebuild reads
them from - the seed artifact and the appendix, with the appendix winning - and
`live.corporate_actions.spinoff_return` does the arithmetic. The return printed here
is therefore the return the rebuild writes, and the raw print it replaces is printed
next to it so the two can be checked against the run that flagged it.

Idempotent: the key is `(trade_date, ticker)`, so running it twice leaves one row.

Dry run by default. `--write` writes to the store named by `EFB_SUPABASE_DB_URL`,
which is a DML role: the four columns this row needs are added to the table by the
admin path, not from here.

    source .env
    python scripts/record_spinoff.py                 # what it would write
    python scripts/record_spinoff.py --write         # the record
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live import appendix, corporate_actions, store  # noqa: E402

# The appendix's own tables are what the prices are read from, and the store only
# knows them once the appendix has registered them.
appendix.register_tables()

SEED_PRICES = ROOT / "data" / "raw" / "prices.parquet"
PRICES_TABLE = "e11_prices"
# The case this script was written for, as the vendor reported it.
CTVA, VYLR, EX_DATE = "CTVA", "VYLR", "2026-10-01"


def _seed_closes() -> dict[tuple[pd.Timestamp, str], float]:
    """The seed's raw closes by (session, ticker), empty when there is no seed."""
    if not SEED_PRICES.exists():
        return {}
    frame = pd.read_parquet(SEED_PRICES, columns=["close"])
    out: dict[tuple[pd.Timestamp, str], float] = {}
    for (session, ticker), close in frame["close"].items():
        if not pd.isna(close):
            out[(pd.Timestamp(session).normalize(), str(ticker))] = float(close)
    return out


def _appendix_closes() -> dict[tuple[pd.Timestamp, str], float]:
    """The appendix's raw closes by (session, ticker), which win where both have one.

    The appendix is authoritative after the cutoff, exactly as `appendix.hydrate`
    treats it, and a spun-off child is usually only there: VYLR starts trading on
    the ex-date, so the seed cannot carry it.
    """
    frame = store.select(PRICES_TABLE)
    if frame.empty:
        return {}
    out: dict[tuple[pd.Timestamp, str], float] = {}
    for row in frame.itertuples(index=False):
        close = getattr(row, "close", None)
        if close is None or pd.isna(close):
            continue
        session = pd.Timestamp(row.trade_date).normalize()
        out[(session, str(row.ticker))] = float(close)
    return out


def closes(session: pd.Timestamp, parent: str, child: str) -> dict[str, Any]:
    """The three closes the return needs, and where each one came from.

    The parent's prior close is the last stored session before the ex-date, which is
    the same rule `corporate_actions._stored_pair` applies, so the number here is
    the number the rebuild derives.
    """
    appendix = _appendix_closes()
    seed = _seed_closes()
    merged = {**seed, **appendix}
    if (session, parent) not in merged:
        raise SystemExit(
            f"{parent} has no stored close for {session.date()}: the ex-date has to "
            "be a session the seed or the appendix carries"
        )
    if (session, child) not in merged:
        raise SystemExit(
            f"{child} has no stored close for {session.date()}: the return is "
            "derived from the child's close on the ex-date and cannot be guessed"
        )
    earlier = sorted(
        day for day, ticker in merged if ticker == parent and day < session
    )
    if not earlier:
        raise SystemExit(
            f"{parent} has no stored close before {session.date()}, so the return "
            "has no denominator"
        )
    previous_session = earlier[-1]
    return {
        "parent_previous_close": merged[(previous_session, parent)],
        "parent_previous_session": previous_session,
        "parent_close": merged[(session, parent)],
        "child_close": merged[(session, child)],
        "appendix_sessions": len({day for day, _ in appendix}),
    }


def the_record(
    parent: str, child: str, session: pd.Timestamp, source_rate: float, new_rate: float
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The row to write and the arithmetic behind it, both derived from closes."""
    detail = closes(session, parent, child)
    ratio = new_rate / source_rate
    value = corporate_actions.spinoff_return(
        parent_close=detail["parent_close"],
        child_close=detail["child_close"],
        child_per_parent=ratio,
        parent_previous_close=detail["parent_previous_close"],
    )
    raw_print = detail["parent_close"] / detail["parent_previous_close"] - 1.0
    row = {
        "trade_date": session.date().isoformat(),
        "ticker": parent,
        "effective_date": session.date().isoformat(),
        "factor": float(ratio),
        "source": "manual.record",
        "cross_check_ratio": None,
        "explained_by": "spinoff",
        "new_ticker": child,
        "source_rate": float(source_rate),
        "new_rate": float(new_rate),
    }
    detail.update(
        {
            "ratio": ratio,
            "return": value,
            "raw_print": raw_print,
            "raw_print_percent": f"{raw_print * 100:+.2f}%",
            "return_percent": f"{value * 100:+.2f}%",
        }
    )
    return row, detail


def existing(session: pd.Timestamp, parent: str) -> dict[str, Any] | None:
    """The row already recorded for this key, if any, so a re-run says so."""
    frame = store.select(corporate_actions.TABLE)
    if frame.empty or "effective_date" not in frame.columns:
        return None
    if "explained_by" not in frame.columns:
        raise SystemExit(
            "efb.e11_corporate_actions has no explained_by column yet: add the four "
            "columns first (live/supabase_schema.sql), the writer role cannot"
        )
    keys = (pd.to_datetime(frame["trade_date"]).dt.normalize() == session) & (
        frame["ticker"].astype(str) == parent
    )
    rows = frame.loc[keys]
    if rows.empty:
        return None
    return {str(key): value for key, value in rows.iloc[-1].to_dict().items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--parent", default=CTVA, help="the name whose return moves")
    parser.add_argument("--child", default=VYLR, help="the number it was given for it")
    parser.add_argument("--session", default=EX_DATE, help="the ex-date, YYYY-MM-DD")
    parser.add_argument("--source-rate", type=float, default=1.0)
    parser.add_argument("--new-rate", type=float, default=1.0)
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the row to the store; otherwise print what would be written",
    )
    args = parser.parse_args(argv)

    session = pd.Timestamp(args.session).normalize()
    row, detail = the_record(
        args.parent, args.child, session, args.source_rate, args.new_rate
    )
    already = existing(session, args.parent)
    named = f"{args.parent} -> {args.child} {detail['ratio']:g}:1 on {session.date()}"
    print(f"record: {named}")
    print(
        json.dumps(
            {
                "closes": {
                    "parent_previous_close": detail["parent_previous_close"],
                    "parent_previous_session": str(
                        detail["parent_previous_session"].date()
                    ),
                    "parent_close": detail["parent_close"],
                    "child_close": detail["child_close"],
                },
                "raw_print_the_prices_give": detail["raw_print"],
                "raw_print_percent": detail["raw_print_percent"],
                "derived_total_return": detail["return"],
                "derived_total_return_percent": detail["return_percent"],
                "already_recorded": already is not None,
            },
            indent=2,
            default=str,
        )
    )
    print(json.dumps({"row": row}, indent=2, default=str))
    if not args.write:
        print()
        print("dry run: nothing was written; pass --write to record it")
        return 0
    if not store.is_supabase():
        raise SystemExit(
            "EFB_SUPABASE_DB_URL is not set, so this would write the local fallback "
            "instead of the store: the rebuild reads the store"
        )
    store.upsert(corporate_actions.TABLE, [row])
    after = existing(session, args.parent)
    print()
    print(f"written: {named}")
    print(
        "the store now holds one row for this key: "
        f"{json.dumps(after, default=str) if after else 'no - check the write'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
