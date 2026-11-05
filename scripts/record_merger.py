"""Record a cash-and-stock merger in the appendix, so the returns rebuild puts it back.

Why a record and not a price edit: 'extend_returns' recomputes every session from the
stored prices, and neither price vendor adjusts history for a merger, so the
completion-session total return has to be re-applied from its record every evening. The
KVUE -> KMB merger completed 2026-11-02: each KVUE share converted into 0.14625 KMB
shares plus $3.50 cash (KMB's Form 8-K Item 2.01). KVUE's last print was 2026-10-30
($19.31) and KMB closed $108.25 on 2026-11-02, so the true total return is
(0.14625 x 108.25 + 3.50) / 19.31 - 1 = +11.17 bp.

The row this writes is the row the append path writes, field for field, so
'live.corporate_actions.mergers_from_rows' reads it back as the same record:

    trade_date       the completion session
    ticker           the target
    effective_date   the completion date
    factor           the acquirer's shares per target share
    explained_by     "merger", which is what makes it a merger and not a split/spin-off
    new_ticker       the acquirer
    cash_per_share   the cash leg per target share

Nothing is typed in: the target's prior close and the acquirer's completion close are
read from the same two places the rebuild reads them from - the seed artifact and the
appendix, with the appendix winning - and 'live.corporate_actions.merger_return' does
the arithmetic. The return printed here is therefore the return the rebuild writes.

Idempotent: the key is '(trade_date, ticker)', so running it twice leaves one row.

Dry run by default. '--apply' writes to the store named by 'EFB_SUPABASE_DB_URL', which
is a DML role: the 'cash_per_share' column is added by the migration
('docs/migrations/e11_merger_cash.sql'), not from here.

    source .env
    python scripts/record_merger.py                 # what it would write
    python scripts/record_merger.py --apply         # the record
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

appendix.register_tables()

SEED_PRICES = ROOT / "data" / "raw" / "prices.parquet"
PRICES_TABLE = "e11_prices"
# The case this script was written for, from KMB's Form 8-K Item 2.01.
TARGET, ACQUIRER, COMPLETION = "KVUE", "KMB", "2026-11-02"
RATIO = 0.14625
CASH = 3.50


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
    """The appendix's raw closes by (session, ticker), which win where both have one."""
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


def closes(session: pd.Timestamp, target: str, acquirer: str) -> dict[str, Any]:
    """The two closes the return needs, and where each one came from.

    The target's prior close is the last stored session before the completion date,
    which is the same rule 'corporate_actions._stored_pair' applies. The acquirer's
    close is its completion-session close.
    """
    appendix_closes = _appendix_closes()
    seed = _seed_closes()
    merged = {**seed, **appendix_closes}
    if (session, acquirer) not in merged:
        raise SystemExit(
            f"{acquirer} has no stored close for {session.date()}: the completion "
            "date has to be a session the seed or the appendix carries"
        )
    earlier = sorted(day for day, ticker in merged if ticker == target and day < session)
    if not earlier:
        raise SystemExit(
            f"{target} has no stored close before {session.date()}, so the return "
            "has no denominator"
        )
    previous_session = earlier[-1]
    return {
        "target_previous_close": merged[(previous_session, target)],
        "target_previous_session": previous_session,
        "acquirer_close": merged[(session, acquirer)],
        "appendix_sessions": len({day for day, _ in appendix_closes}),
    }


def the_record(
    target: str, acquirer: str, session: pd.Timestamp, ratio: float, cash: float
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The row to write and the arithmetic behind it, both derived from closes."""
    detail = closes(session, target, acquirer)
    value = corporate_actions.merger_return(
        target_previous_close=detail["target_previous_close"],
        acquirer_close=detail["acquirer_close"],
        acquirer_per_target=ratio,
        cash_per_share=cash,
    )
    row = {
        "trade_date": session.date().isoformat(),
        "ticker": target,
        "effective_date": session.date().isoformat(),
        "factor": float(ratio),
        "source": "manual.record",
        "cross_check_ratio": None,
        "explained_by": "merger",
        "new_ticker": acquirer,
        "source_rate": 1.0,
        "new_rate": float(ratio),
        "cash_per_share": float(cash),
    }
    detail.update(
        {
            "return": value,
            "return_percent": f"{value * 100:+.2f}%",
        }
    )
    return row, detail


def existing(session: pd.Timestamp, target: str) -> dict[str, Any] | None:
    """The row already recorded for this key, if any, so a re-run says so."""
    frame = store.select(corporate_actions.TABLE)
    if frame.empty or "effective_date" not in frame.columns:
        return None
    if "explained_by" not in frame.columns:
        raise SystemExit(
            "efb.e11_corporate_actions has no explained_by column yet: add the "
            "columns first (live/supabase_schema.sql), the writer role cannot"
        )
    keys = (pd.to_datetime(frame["trade_date"]).dt.normalize() == session) & (
        frame["ticker"].astype(str) == target
    )
    rows = frame.loc[keys]
    if rows.empty:
        return None
    return {str(key): value for key, value in rows.iloc[-1].to_dict().items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", default=TARGET, help="the name whose return moves")
    parser.add_argument("--acquirer", default=ACQUIRER, help="the name it converts into")
    parser.add_argument("--session", default=COMPLETION, help="the completion date, YYYY-MM-DD")
    parser.add_argument("--ratio", type=float, default=RATIO, help="acquirer shares per target share")
    parser.add_argument("--cash", type=float, default=CASH, help="cash per target share")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the row to the store; otherwise print what would be written",
    )
    args = parser.parse_args(argv)

    session = pd.Timestamp(args.session).normalize()
    row, detail = the_record(args.target, args.acquirer, session, args.ratio, args.cash)
    already = existing(session, args.target)
    cash_label = "$" + f"{args.cash:g}"
    named = (
        f"{args.target} -> {args.acquirer} {args.ratio:g} shares + "
        f"{cash_label} cash on {session.date()}"
    )
    print(f"record: {named}")
    print(
        json.dumps(
            {
                "closes": {
                    "target_previous_close": detail["target_previous_close"],
                    "target_previous_session": str(
                        detail["target_previous_session"].date()
                    ),
                    "acquirer_close": detail["acquirer_close"],
                },
                "derived_total_return": detail["return"],
                "derived_total_return_percent": detail["return_percent"],
                "already_recorded": already is not None,
            },
            indent=2,
            default=str,
        )
    )
    print(json.dumps({"row": row}, indent=2, default=str))
    if not args.apply:
        print()
        print("dry run: nothing was written; pass --apply to record it")
        return 0
    if not store.is_supabase():
        raise SystemExit(
            "EFB_SUPABASE_DB_URL is not set, so this would write the local fallback "
            "instead of the store: the rebuild reads the store"
        )
    store.upsert(corporate_actions.TABLE, [row])
    after = existing(session, args.target)
    print()
    print(f"written: {named}")
    print(
        "the store now holds one row for this key: "
        f"{json.dumps(after, default=str) if after else 'no - check the write'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
