"""Every NOT NULL numeric column in the live schema, scanned for a NaN. Read-only.

`not null` in Postgres does not exclude a NaN: `select float8 'NaN' is not null` is
true, which is why the 2026-10-07 evening died at the write after the whole book had
been priced - the row for Q carried `float("nan")` as its `idio_vol`, the driver sent
a null, and the constraint fired. The schema therefore says nothing about whether a
column can hold a NaN; only the data and the code that writes it do.

This is the data half, and it is one read-only SELECT per column: the schema's own
NOT NULL numeric columns from `live/supabase_schema.sql`, and for each one the row
count, the count of NaN values and the count of nulls. A null in a NOT NULL column is
impossible unless the constraint was dropped, so a non-zero null count is reported as
its own finding rather than folded into the NaN one.

Runs against whatever the store resolves to: the live Postgres when
`EFB_SUPABASE_DB_URL` is set, the local parquet mirror otherwise (the tables the
mirror does not hold are reported as not read, never as clean).

    .venv/bin/python scripts/nov11_notnull_audit.py
    .venv/bin/python scripts/nov11_notnull_audit.py --out docs/nov11_notnull_audit.md

Exit codes: 0 when every column read is clean, 1 when any holds a NaN or a null, 2
when no column could be read at all (a report of nothing is not a pass).
"""

from __future__ import annotations

import argparse
import math
import pathlib
import re
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # render runs `python scripts/...`, so add the root
    sys.path.insert(0, str(ROOT))

DDL_PATH = ROOT / "live" / "supabase_schema.sql"

_TABLE_RE = re.compile(
    r"create\s+table\s+if\s+not\s+exists\s+(\S+)\s*\(", re.IGNORECASE
)
_NUMERIC_KINDS = ("double precision", "numeric", "real", "float", "integer", "bigint")


def _strip_comments(text: str) -> str:
    return "\n".join(line.split("--")[0] for line in text.splitlines())


def not_null_numeric_columns(
    path: pathlib.Path | None = None,
) -> dict[str, list[str]]:
    """{table: [column]} for the NOT NULL numeric columns the schema declares.

    Parsed from the DDL rather than asked of the live catalogue, so the list is the
    declaration this repo makes and a column added to the schema without a thought
    for the NaN it can hold shows up in the next audit. A foreign key or a
    composite-key clause is not a column: the commas inside them are stripped the
    way `live/preflight.py` strips them for the same reason.
    """
    text = _strip_comments((path or DDL_PATH).read_text())
    out: dict[str, list[str]] = {}
    for match in _TABLE_RE.finditer(text):
        table = match.group(1).split(".")[-1].strip('"')
        start = match.end()
        depth, index = 1, start
        while index < len(text) and depth:
            if text[index] == "(":
                depth += 1
            elif text[index] == ")":
                depth -= 1
            index += 1
        body = re.sub(
            r"(?is)\b(primary\s+key|unique|foreign\s+key|constraint|check)\b\s*\([^)]*\)",
            "",
            text[start : index - 1],
        )
        body = re.sub(r"(?is)\breferences\b\s+\S+\s*(\([^)]*\))?", "", body)
        for line in body.split(","):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            name = parts[0].strip('"').lower()
            if name in ("primary", "unique", "foreign", "constraint", "check"):
                continue
            kind = " ".join(parts[1:]).lower()
            if any(token in kind for token in _NUMERIC_KINDS) and "not null" in kind:
                out.setdefault(table, []).append(name)
    return out


def _postgres_rows(
    connection: Any, table: str, column: str, schema: str
) -> dict[str, Any] | None:
    """The four counts for one column, or None when the read fails."""
    sql = (
        f"select count(*) as n, "
        f"count(*) filter (where {column} <> {column}) as nans, "
        f"count(*) filter (where {column} is null) as nulls "
        f"from {schema}.{table}"
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            row = cursor.fetchone()
    except Exception:
        return None
    if row is None:
        return None
    return {"n": int(row[0]), "nans": int(row[1]), "nulls": int(row[2])}


def _local_rows(
    table: str, column: str, *, reader: Any = None
) -> dict[str, Any] | None:
    """The same counts off the local parquet mirror, or None when it has no table.

    `reader` is `store.select` by default, so a test drives the scan without a store.
    """
    import pandas as pd

    from live import store

    try:
        frame = (reader or store.select)(table)
    except Exception:
        return None
    if frame.empty:
        return None
    if column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce")
    # `errors="coerce"` is not used as the NaN detector here: a value that is not a
    # number at all is a finding too, and it would be silently NaN under coercion.
    not_number = 0
    nans = 0
    for item in frame[column].tolist():
        try:
            number = float(item)
        except (TypeError, ValueError):
            not_number += 1
            continue
        if math.isnan(number):
            nans += 1
    return {
        "n": int(len(frame)),
        "nans": nans,
        "nulls": int(values.isna().sum()) - nans - not_number,
        "not_number": not_number,
    }


def audit(
    *,
    ddl_path: pathlib.Path | None = None,
    connection: Any = None,
    local: bool = False,
) -> list[dict[str, Any]]:
    """One row per NOT NULL numeric column: its counts, or why it could not be read."""
    from live import store

    schema = "efb"
    try:
        schema = store._schema()
    except Exception:  # noqa: BLE001 - the default schema is the only fallback
        pass
    if connection is None and not local:
        try:
            connection = store.get_connection()
        except Exception:  # noqa: BLE001 - a local run has no database, by design
            connection = None
    rows: list[dict[str, Any]] = []
    for table, columns in sorted(not_null_numeric_columns(ddl_path).items()):
        for column in sorted(columns):
            counts = (
                _local_rows(table, column)
                if connection is None
                else _postgres_rows(connection, table, column, schema)
            )
            if counts is None:
                rows.append(
                    {
                        "table": table,
                        "column": column,
                        "read": False,
                        "n": None,
                        "nans": None,
                        "nulls": None,
                        "not_number": None,
                    }
                )
                continue
            not_number = int(counts.get("not_number") or 0)
            nans = int(counts["nans"]) + not_number
            nulls = int(counts["nulls"])
            rows.append(
                {
                    "table": table,
                    "column": column,
                    "read": True,
                    "n": int(counts["n"]),
                    "nans": nans,
                    "nulls": nulls,
                    "not_number": not_number,
                }
            )
    return rows


def verdict(row: dict[str, Any]) -> str:
    """One word per row: clean, or what it holds, or that it was not read."""
    if not row.get("read"):
        return "not read"
    if row["nans"]:
        return "NaN"
    if row["nulls"]:
        return "nulls"
    return "clean"


def report(rows: list[dict[str, Any]], *, source: str) -> str:
    """The audit as markdown: a table per answer, and the counts it rests on."""
    clean = [row for row in rows if verdict(row) == "clean"]
    bad = [row for row in rows if verdict(row) in ("NaN", "nulls")]
    unread = [row for row in rows if verdict(row) == "not read"]
    lines = [
        "| table | column | rows | NaN | null | verdict |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['table']}` | `{row['column']}` | "
            f"{row['n'] if row['n'] is not None else '—'} | "
            f"{row['nans'] if row['nans'] is not None else '—'} | "
            f"{row['nulls'] if row['nulls'] is not None else '—'} | "
            f"{verdict(row)} |"
        )
    head = [
        "# The NOT NULL NaN audit",
        "",
        f"Source: {source}. {len(rows)} NOT NULL numeric column(s) in "
        f"`live/supabase_schema.sql`: {len(clean)} clean, {len(bad)} with a NaN or a "
        f"null, {len(unread)} not read.",
        "",
        "`not null` does not exclude a NaN in Postgres, so this is a claim about the "
        "data and not about the constraint. A column the source does not hold is "
        "`not read`, which is not a pass.",
        "",
    ]
    return "\n".join(head + lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    from live import store

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path, default=None)
    parser.add_argument(
        "--local",
        action="store_true",
        help="scan the local parquet mirror even when a database is reachable",
    )
    args = parser.parse_args(argv)
    rows = audit(local=args.local)
    mode = store.store_mode()
    source = f"`{store.store_label()}` (mode `{mode}`)"
    text = report(rows, source=source)
    if args.out is not None:
        args.out.write_text(text)
    else:
        print(text)
    read = [row for row in rows if row["read"]]
    if not read:
        print(
            "no column could be read: a report of nothing is not a pass",
            file=sys.stderr,
        )
        return 2
    return 1 if any(verdict(row) in ("NaN", "nulls") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
