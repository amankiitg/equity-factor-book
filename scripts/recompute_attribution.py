"""Recompute the stored attribution rows with the B4 variance fix, dry run by default.

**Read-only unless `--apply` is passed.** The B4 fix (`nov11-b4-attribution-variance`,
on `main` since 2026-10-19) squares the stored `idio_vol` before it rebuilds the
pre-hedge book: `pre_hedge_weights` sizes on `alpha / sigma^2`, and the store's
`positions.idio_vol` is sigma, not sigma^2. Every attribution row written before the
fix carries a pre-hedge volatility built from the square root, so it overstates the
volatility the hedge removed.

    python scripts/recompute_attribution.py --root <live data tree>            # dry run
    python scripts/recompute_attribution.py --root <live data tree> --apply

Dry run: reads the stored `efb.attribution` rows, recomputes the days the current code
can rebuild, prints the stored value against the recomputed one per day, and checks
the four-term identity on each recomputed row. Nothing is written.

`--apply`: upserts the recomputed rows for the days that already exist. It never
creates a day the store did not have and never deletes one.

The data tree is the one the evening reads: the seed plus the appendix. On this
machine that is the cut tree from the nov11 merge
(`/tmp/nov11merge/cut-2026-10-19/data`); the owner's is the run tree on Render.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from live import attribution_job, store  # noqa: E402

# The four terms the row's identity is built from.
IDENTITY = ("pnl_total", "pnl_factor", "pnl_idio", "pnl_cost")


def _stored() -> pd.DataFrame:
    frame = store.select("attribution")
    if frame is None or frame.empty:
        return pd.DataFrame()
    frame = frame.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame.sort_values("trade_date")


def _recompute(root: pathlib.Path) -> pd.DataFrame:
    """Every stored day, recomputed, captured instead of written.

    `attributed_days` is emptied so the code does not skip the days that already have
    a row, and `store.upsert` is replaced by a list so a dry run cannot write. The
    caller decides whether the list ever reaches the store.
    """
    captured: list[pd.DataFrame] = []
    original_upsert = store.upsert
    original_days = attribution_job.attributed_days

    def capture(table: str, rows: Any) -> None:
        if table == "attribution":
            captured.append(pd.DataFrame(rows))

    store.upsert = capture  # type: ignore[assignment]
    attribution_job.attributed_days = lambda: set()  # type: ignore[assignment]
    try:
        outcome = attribution_job.run(root)
    finally:
        store.upsert = original_upsert  # type: ignore[assignment]
        attribution_job.attributed_days = original_days  # type: ignore[assignment]
    print(f"recompute: {outcome}")
    if not captured:
        return pd.DataFrame()
    frame = pd.concat(captured, ignore_index=True)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame


def _same(left: Any, right: Any) -> bool:
    """Equality that tolerates float reassociation and jsonb key ordering."""
    if left is None or (isinstance(left, float) and pd.isna(left)):
        return right is None or (isinstance(right, float) and pd.isna(right))
    if isinstance(left, float) and isinstance(right, float):
        return abs(left - right) <= 1e-12
    if isinstance(left, (dict, list)) or isinstance(right, (dict, list)):
        return _json_same(left, right)
    return str(left) == str(right)


def _json_same(left: Any, right: Any) -> bool:
    parsed = []
    for value in (left, right):
        if isinstance(value, str):
            try:
                parsed.append(json.loads(value))
            except json.JSONDecodeError:
                parsed.append(value)
        else:
            parsed.append(value)
    first, second = parsed
    if isinstance(first, dict) and isinstance(second, dict):
        if set(first) != set(second):
            return False
        return all(_same(first[k], second[k]) for k in first)
    if isinstance(first, list) and isinstance(second, list):
        return len(first) == len(second) and all(
            _same(a, b) for a, b in zip(first, second, strict=False)
        )
    return _same(first, second)


def _other_changes(old: Any, record: dict[str, Any]) -> str:
    """The columns, other than the vol pair, a full-row upsert would change.

    A recompute is only safe to write whole when this is empty: the stored row's
    `pnl_*`, `n_filled` and `realized_vol` were written against the fills and the
    price tree of that evening, and recomputing them now re-derives that history
    from today's store instead of fixing the volatility.
    """
    skip = {"trade_date", "written_at", "pre_hedge_vol", "hedged_vol"}
    changed = []
    for key in record:
        if key in skip:
            continue
        if old is not None and not _same(old.get(key), record.get(key)):
            changed.append(key)
    if not changed:
        return "0"
    names = ",".join(changed[:3]) + ("…" if len(changed) > 3 else "")
    return f"{len(changed)} ({names})"


def _changed_pairs(old: Any, record: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    """Every stored column whose value the recompute would change, with both values."""
    if old is None:
        return []
    changed = []
    for key in record:
        if key in {"trade_date", "written_at"}:
            continue
        if not _same(old.get(key), record.get(key)):
            changed.append((key, old.get(key), record.get(key)))
    return sorted(changed)


def _show_diff(day: pd.Timestamp, pairs: list[tuple[str, Any, Any]]) -> None:
    for key, was, now in pairs:
        if isinstance(was, float) or isinstance(now, float):
            shown = f"{_number(was):>14.8f} -> {_number(now):>14.8f}"
        else:
            shown = f"{str(was):>14} -> {str(now):>14}"
        print(f"    {str(day.date()):<12}{key:<22}{shown}")


def _number(value: Any) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _apply_only_pre_hedge_vol(updates: list[tuple[float, Any]], apply: bool) -> int:
    table = store._qualified("attribution")  # noqa: SLF001
    statement = (
        f'UPDATE {table} SET "pre_hedge_vol" = %s, "written_at" = now() '
        'WHERE "trade_date" = %s'
    )
    print(f"\n{statement}")
    if not updates:
        print("every day already holds the recomputed pre-hedge vol: nothing to write")
        return 0
    if not apply:
        print(
            f"\nDRY RUN (--only-pre-hedge-vol): {len(updates)} row(s) would have "
            "pre_hedge_vol updated and no other column touched. Nothing was written."
        )
        return 0
    connection = store.get_connection()
    with connection.cursor() as cursor:
        cursor.executemany(statement, updates)
    connection.commit()
    print(
        f"\nAPPLIED (--only-pre-hedge-vol): {len(updates)} row(s) updated in "
        "efb.attribution; only pre_hedge_vol and written_at changed"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="the live data tree")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="upsert the recomputed rows (default: dry run, nothing is written)",
    )
    parser.add_argument("--since", default=None, help="first close, YYYY-MM-DD")
    parser.add_argument("--through", default=None, help="last close, YYYY-MM-DD")
    parser.add_argument(
        "--diff",
        action="store_true",
        help=(
            "print, for every changed column, its stored and recomputed value. "
            "Read-only, and the table a review of a full-row apply is read from."
        ),
    )
    parser.add_argument(
        "--only-pre-hedge-vol",
        action="store_true",
        help=(
            "write only the pre_hedge_vol column, leaving every other column exactly "
            "as stored (default: upsert the whole recomputed row)"
        ),
    )
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()

    stored = _stored()
    if stored.empty:
        print("no stored attribution rows")
        return 0
    dates = [pd.Timestamp(value) for value in stored["trade_date"].unique()]
    if args.since:
        dates = [d for d in dates if d >= pd.Timestamp(args.since)]
    if args.through:
        dates = [d for d in dates if d <= pd.Timestamp(args.through)]
    wanted = set(dates)

    recomputed = _recompute(root)
    if recomputed.empty:
        print("nothing could be recomputed: no stored positions for any day")
        return 0
    recomputed = recomputed.loc[recomputed["trade_date"].isin(wanted)]

    before = stored.set_index("trade_date")
    rows: list[dict[str, Any]] = []
    updates: list[tuple[float, Any]] = []
    print(
        f"\n{'close':<12}{'pre-hedge before':>18}{'pre-hedge after':>18}"
        f"{'hedged before':>15}{'hedged after':>14}{'identity after':>16}"
        f"{'other cols':>12}"
    )
    for record in recomputed.sort_values("trade_date").to_dict("records"):
        day = pd.Timestamp(record["trade_date"])
        old = before.loc[day] if day in before.index else None
        old_pre = None if old is None else old.get("pre_hedge_vol")
        old_hedged = None if old is None else old.get("hedged_vol")
        residual = sum(
            float(record.get(key) or 0.0) * (1 if key == "pnl_total" else -1)
            for key in IDENTITY
        )
        others = _other_changes(old, record)
        print(
            f"{str(day.date()):<12}"
            f"{_pct(old_pre):>18}{_pct(record.get('pre_hedge_vol')):>18}"
            f"{_pct(old_hedged):>15}{_pct(record.get('hedged_vol')):>14}"
            f"{residual:>16.2e}{others:>12}"
        )
        if args.diff:
            pairs = _changed_pairs(old, record)
            if pairs:
                _show_diff(day, pairs)
        rows.append({key: record.get(key) for key in recomputed.columns})
        if args.only_pre_hedge_vol and old is not None:
            new_pre = record.get("pre_hedge_vol")
            if new_pre is not None and not _same(old.get("pre_hedge_vol"), new_pre):
                updates.append((float(new_pre), day.date()))

    missing = sorted(
        str(d.date()) for d in wanted if d not in set(recomputed["trade_date"])
    )
    if missing:
        print(f"\nnot recomputable (no stored positions): {', '.join(missing)}")

    if args.only_pre_hedge_vol:
        return _apply_only_pre_hedge_vol(updates, args.apply)
    if not args.apply:
        print(
            f"\nDRY RUN: {len(rows)} row(s) would be upserted. Nothing was written. "
            "Re-run with --apply to write them."
        )
        return 0
    store.upsert("attribution", rows)
    print(f"\nAPPLIED: {len(rows)} row(s) upserted into efb.attribution")
    print("verify: re-run without --apply and confirm every 'before' equals 'after'.")
    return 0


def _pct(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    return f"{float(value) * 100:.2f}%"


if __name__ == "__main__":
    raise SystemExit(main())
