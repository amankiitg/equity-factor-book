"""Item 4b: prove the real Postgres round trip before a gate evening counts.

Every Postgres claim this project made before now was made against the store's
local parquet fallback, because no server was reachable from the build host:
Part 2's round-trip hashes, Part 3's gate and Part 4's typing probe all ran
locally. Nothing had exercised a single line of SQL. This command is what closes
that gap, and a gate evening counts only after it passes.

It runs against the real `efb` schema, from the owner's machine or the deployed
cron's box, and it does three things:

1. **Reads every appendix input back** and compares it with the local artifact
   at the same commit, over the sessions both hold, value by value and by hash.
2. **Checks type fidelity explicitly.** A NaN float, a JSON `null` where a NaN
   used to be, a date, a timestamp with a time zone and a small float are read
   back from Postgres itself. It also proves the negative control: a bare `NaN`
   in JSON is refused by `jsonb`, which is why `store.json_text` exists.
3. **Records the result** in `efb.run_status` with the per-input hashes, so the
   dashboard and the next reader see it without a terminal.
4. **Proves the `replace_by_date` delete** against the real store: two rows on a
   sentinel date, replaced by one, then cleared. That DELETE runs every evening
   (it is how the day's positions and orders are written), so a missing grant
   fails the first order-writing run; this proves it before a gate evening does.
   The sentinel date is 1900-01-01 and it is cleared before the command returns.

It writes one `run_status` row, plus the sentinel positions rows that are cleared
again, and it writes no row at all when the store has not been seeded yet:
`run_status.target_close` is NOT NULL and an empty appendix has no session to name,
so a row would be a row about nothing. That state is expected before the first run
and is reported as such rather than as a failure. It trades nothing and no
artifact is written.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from live import appendix, staleness, store  # noqa: E402

DATA = ROOT / "data"
PROBE_JOB = "store_roundtrip"


def artifact_frame(spec: appendix.InputSpec) -> pd.DataFrame:
    """The local artifact's rows for one input, in the appendix's own columns."""
    path = DATA / spec.path
    frame = pd.read_parquet(path)
    columns = [column for column in (*spec.key, *spec.value_columns) if column in frame]
    frame = frame.loc[:, columns]
    if spec.date_field and spec.date_field in frame.columns:
        frame = frame.assign(
            **{spec.date_field: pd.to_datetime(frame[spec.date_field]).dt.normalize()}
        )
    return frame


def canonical(frame: pd.DataFrame) -> pd.DataFrame:
    """One comparison basis: strings for dates, floats widened, columns sorted."""
    out = frame.copy()
    for column in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[column]):
            out[column] = pd.to_datetime(out[column]).dt.strftime("%Y-%m-%d")
        elif out[column].dtype == object:
            out[column] = out[column].map(
                lambda value: None if pd.isna(value) else str(value)
            )
    return out.sort_values(list(out.columns)).reset_index(drop=True)


def frame_hash(frame: pd.DataFrame) -> str:
    return hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest()


def compare_inputs() -> tuple[list[dict[str, Any]], list[str]]:
    """Every input, appendix against artifact, over the sessions both hold."""
    report: list[dict[str, Any]] = []
    problems: list[str] = []
    for spec in appendix.SPECS:
        row: dict[str, Any] = {"input": spec.name, "table": spec.table}
        try:
            theirs = appendix.read_appendix(spec)
        except Exception as exc:  # noqa: BLE001 - reported, never silent
            problems.append(f"{spec.name}: the appendix could not be read: {exc}")
            report.append({**row, "status": "unreadable", "detail": str(exc)[:200]})
            continue
        ours = artifact_frame(spec)
        if theirs.empty or ours.empty:
            detail = (
                "the appendix is empty" if theirs.empty else "the artifact is empty"
            )
            problems.append(f"{spec.name}: {detail}, so nothing could be compared")
            report.append({**row, "status": "empty", "detail": detail})
            continue
        both = list({*theirs.columns} & {*ours.columns})
        theirs, ours = theirs.loc[:, both], ours.loc[:, both]
        field = spec.date_field
        theirs, ours = canonical(theirs), canonical(ours)
        start = max(
            pd.to_datetime(theirs[field]).min(), pd.to_datetime(ours[field]).min()
        )
        end = min(
            pd.to_datetime(theirs[field]).max(), pd.to_datetime(ours[field]).max()
        )
        theirs_w = theirs.loc[
            (pd.to_datetime(theirs[field]) >= start)
            & (pd.to_datetime(theirs[field]) <= end)
        ]
        ours_w = ours.loc[
            (pd.to_datetime(ours[field]) >= start)
            & (pd.to_datetime(ours[field]) <= end)
        ]
        same_hash = frame_hash(theirs_w) == frame_hash(ours_w)
        same_rows = len(theirs_w) == len(ours_w)
        equal, differing = True, None
        if same_rows:
            for column in theirs_w.columns:
                left, right = theirs_w[column].reset_index(drop=True), ours_w[
                    column
                ].reset_index(drop=True)
                if not left.equals(right):
                    equal = False
                    differing = column
                    break
        else:
            equal = False
            differing = "row count"
        beyond = int((pd.to_datetime(theirs[field]) > end).sum())
        row.update(
            {
                "status": "match" if (same_hash and equal) else "MISMATCH",
                "rows": int(len(theirs_w)),
                "first": None if pd.isna(start) else str(start.date()),
                "last": None if pd.isna(end) else str(end.date()),
                "sha256": frame_hash(theirs_w),
                "appendix_rows": int(len(theirs)),
                "artifact_rows": int(len(ours)),
                "appendix_sessions_beyond_the_artifact": beyond,
            }
        )
        if not (same_hash and equal):
            problems.append(
                f"{spec.name}: the appendix and the local artifact disagree over "
                f"{start.date()} to {end.date()} ({differing})"
            )
        report.append(row)
    return report, problems


def type_probes() -> tuple[list[dict[str, Any]], list[str]]:
    """NaN in a float and in jsonb, a date, a timestamptz and float precision.

    One `SELECT`, so nothing is written and no temporary state is left on the
    shared project. The negative control runs on its own connection, because a
    failed statement aborts its transaction.
    """
    import psycopg

    url = store.os.environ[store.URL_ENV].strip()
    now = datetime(2026, 9, 25, 20, 30, 15, 123456, tzinfo=UTC)
    probes: list[dict[str, Any]] = []
    problems: list[str] = []
    tiny = 1.0e-17
    statement = (
        "SELECT %s::double precision, %s::jsonb, %s::date, %s::timestamptz, "
        "%s::double precision"
    )
    jsonb_text = store.json_text({"nan": float("nan"), "inf": float("inf"), "ok": 1.5})
    payload = (float("nan"), jsonb_text, now.date(), now, tiny)
    with psycopg.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(statement, payload)
            fetched = cursor.fetchone()
            if fetched is None:  # pragma: no cover - a SELECT always returns a row
                raise RuntimeError("the type probe returned no row")
            got_nan, got_json, got_date, got_ts, got_tiny = fetched
    for name, expected, actual in (
        ("nan floats", "nan", got_nan),
        ("jsonb has null not NaN", {"nan": None, "inf": None, "ok": 1.5}, got_json),
        ("dates", now.date(), got_date),
        ("timestamptz", now, got_ts),
        ("small float precision", tiny, got_tiny),
    ):
        ok = (
            (actual != actual and expected == "nan")
            if expected == "nan"
            else actual == expected
        )
        probes.append(
            {
                "probe": name,
                "expected": str(expected),
                "read_back": str(actual),
                "status": "ok" if ok else "MISMATCH",
            }
        )
        if not ok:
            problems.append(
                f"{name}: expected {expected!r}, Postgres returned {actual!r}"
            )
    # The negative control: the same NaN without the sanitizer is refused.
    refused = False
    detail = ""
    try:
        with psycopg.connect(url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT %s::jsonb", ('{"nan": NaN}',))
                refused = False
    except Exception as exc:  # noqa: BLE001 - the refusal is the result
        refused = True
        detail = str(exc).splitlines()[0][:160]
    probes.append(
        {
            "probe": "bare NaN in jsonb is refused (the negative control)",
            "expected": "an error",
            "read_back": detail or "accepted it",
            "status": "ok" if refused else "MISMATCH",
        }
    )
    if not refused:
        problems.append(
            "jsonb accepted a bare NaN, which means the sanitizer is not the reason "
            "the rows survive and the risk is somewhere else"
        )
    return probes, problems


# A date no live session and no build ever writes, so the round trip can write,
# replace and clear rows without touching a real evening's data.
ROUNDTRIP_DATE = "1900-01-01"


def _sentinel_position(ticker: str, notional: float, weight: float) -> dict[str, Any]:
    """One positions row carrying every NOT NULL column the table requires."""
    return {
        "trade_date": ROUNDTRIP_DATE,
        "ticker": ticker,
        "weight": weight,
        "signed_notional": notional,
        "side": "long" if notional >= 0 else "short",
        "z": 0.0,
        "alpha": 0.0,
        "rank": 1,
        "idio_vol": 0.0,
        "previous_weight": 0.0,
        "trade": 0.0,
        "reason": "store round trip probe",
        "kind": "probe",
    }


def _sentinel_rows() -> pd.DataFrame:
    """The rows the round trip left on the sentinel date, empty when it cleared them."""
    frame = store.select("positions")
    if frame.empty or "trade_date" not in frame.columns:
        return pd.DataFrame()
    dates = frame["trade_date"].astype(str).str.slice(0, 10)
    return frame.loc[dates == ROUNDTRIP_DATE]


def replace_by_date_roundtrip() -> tuple[list[dict[str, Any]], list[str]]:
    """Prove `replace_by_date` replaces a date instead of merging it.

    It writes two sentinel rows, replaces them with one, reads that row's value
    back (a merge would leave two rows and the old value), and clears the date.
    The DELETE is the point: `replace_by_date` erases a date before re-inserting
    it, and it runs every evening, so a missing privilege fails the first
    order-writing run rather than waiting for a rerun. The sentinel date is
    1900-01-01 and it is cleared even when a step raises.
    """
    probes: list[dict[str, Any]] = []
    problems: list[str] = []
    counts = (0, 0, 0)
    value = float("nan")
    try:
        store.replace_by_date(
            "positions",
            ROUNDTRIP_DATE,
            [
                _sentinel_position("ZZPROBE1", 1.0, 0.01),
                _sentinel_position("ZZPROBE2", 2.0, 0.02),
            ],
        )
        wrote = len(_sentinel_rows())
        store.replace_by_date(
            "positions", ROUNDTRIP_DATE, [_sentinel_position("ZZPROBE1", 9.0, 0.09)]
        )
        rows = _sentinel_rows()
        replaced = len(rows)
        if replaced:
            value = float(rows["signed_notional"].iloc[0])
        store.replace_by_date("positions", ROUNDTRIP_DATE, [])
        cleared = len(_sentinel_rows())
        counts = (wrote, replaced, cleared)
    except Exception as exc:  # noqa: BLE001 - reported, never silent
        problems.append(f"replace_by_date: {type(exc).__name__}: {exc}")
        probes.append(
            {
                "probe": "replace_by_date round trip",
                "expected": "2, 1, 0 rows and a surviving value of 9",
                "read_back": f"{type(exc).__name__}: {exc}",
                "status": "MISMATCH",
            }
        )
    finally:
        try:
            # A step that raised may have left the sentinel rows behind.
            store.replace_by_date("positions", ROUNDTRIP_DATE, [])
        except Exception:  # noqa: BLE001 - the clear above already reported
            pass
    if not problems:
        ok = counts == (2, 1, 0) and abs(value - 9.0) < 1e-9
        read_back = f"{counts[0]}, {counts[1]}, {counts[2]} rows; value {value:g}"
        probes.append(
            {
                "probe": "replace_by_date round trip (write 2, replace with 1, clear)",
                "expected": "2, 1, 0 rows; value 9",
                "read_back": read_back,
                "status": "ok" if ok else "MISMATCH",
            }
        )
        if not ok:
            problems.append(
                "replace_by_date did not replace the sentinel date: expected 2, 1, 0 "
                f"rows and a surviving value of 9, read {read_back}"
            )
    return probes, problems


def record(
    report: list[dict[str, Any]], probes: list[dict[str, Any]], ok: bool
) -> bool:
    """One `run_status` row: the hashes, the probes and the verdict.

    Returns whether it wrote one. `run_status.target_close` is NOT NULL, and an
    appendix with no rows has no session to name, so there is nothing honest to put
    in that column: a row would be a row about nothing. The caller says why instead,
    which is what turns a NotNullViolation into a sentence.
    """
    inputs = {
        row["input"]: {
            "sha256": row.get("sha256"),
            "rows": row.get("rows"),
            "status": row["status"],
        }
        for row in report
    }
    for probe in probes:
        inputs[f"probe:{probe['probe']}"] = {
            "status": probe["status"],
            "read_back": probe["read_back"],
        }
    latest = max(
        (row["last"] for row in report if row.get("last")),
        default=None,
    )
    if latest is None:
        return False
    matched = sum(1 for row in report if row["status"] == "match")
    passed = sum(1 for probe in probes if probe["status"] == "ok")
    result = {
        "job": PROBE_JOB,
        "target_close": latest,
        "status": "ok" if ok else "error",
        "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "inputs": inputs,
        "detail": (
            f"{matched}/{len(report)} inputs match, "
            f"{passed}/{len(probes)} probes ok"
        ),
    }
    staleness.write_run_status(
        result, run_date=datetime.now(UTC).date().isoformat(), dry_run=True
    )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-record",
        action="store_true",
        help="print the result without writing the run_status row",
    )
    args = parser.parse_args(argv)
    try:
        mode = store.store_mode()
    except store.StoreNotConfigured as exc:
        print(f"ERROR {exc}")
        print(
            "This command reads the real `efb` schema by design, so it refuses to run "
            "against the local fallback."
        )
        return 2
    if mode == store.LOCAL_MODE_VALUE:
        print("ERROR the store is in local mode, so there is no Postgres to verify")
        return 2
    print(f"store: {store.store_label()}")

    report, problems = compare_inputs()
    for row in report:
        extra = row.get("appendix_sessions_beyond_the_artifact") or 0
        print(
            f"  {row['input']:<18} {row['status']:<8} rows {row.get('rows')!s:<8} "
            f"{row.get('first')} to {row.get('last')} "
            f"hash {str(row.get('sha256'))[:12]}"
            + (f" (+{extra} appendix sessions beyond the artifact)" if extra else "")
        )
    probes, probe_problems = type_probes()
    for probe in probes:
        print(f"  {probe['probe']:<48} {probe['status']:<8} {probe['read_back']}")

    # The DELETE runs every evening, so it is proven here, on a sentinel date
    # that is cleared before the command returns.
    roundtrip_probes, roundtrip_problems = replace_by_date_roundtrip()
    for probe in roundtrip_probes:
        print(f"  {probe['probe']:<48} {probe['status']:<8} {probe['read_back']}")
    probes.extend(roundtrip_probes)
    probe_problems.extend(roundtrip_problems)

    problems.extend(probe_problems)
    if not any(row.get("last") for row in report):
        # Nothing was compared, which is the state before the first run: the
        # appendix is empty, so there is no session to name and no row to write.
        print()
        print(
            "STORE NOT SEEDED YET: the appendix holds no rows, so the 0 of "
            f"{len(report)} input matches above is expected and is not a failure. "
            "It is the state before the first run, and the first run is the one "
            "that seeds it, with EFB_INIT_STORE=true."
        )
        if probe_problems:
            print(f"but {len(probe_problems)} type probe(s) failed:")
            for problem in probe_problems:
                print(f"  {problem}")
            return 1
        print(
            "the type probes above are what can be checked before the seed, and "
            "they hold. NOTHING RECORDED: a run_status row needs a target_close, "
            "and an unseeded store has no session to name."
        )
        return 0
    ok = not problems
    if not args.no_record:
        record(report, probes, ok)
    print()
    if ok:
        print(
            f"ROUND TRIP OK: {len(report)} inputs read back from Postgres match "
            f"the local artifacts and {len(probes)} type probes hold."
        )
        return 0
    print(f"ROUND TRIP FAILED with {len(problems)} problem(s):")
    for problem in problems:
        print(f"  {problem}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
