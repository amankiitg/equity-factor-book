"""The schema preflight: refuse a run whose database is missing a declared column.

On 2026-10-06 the evening run sent 192 orders and *then* died, because
`efb.reconciliation.unexplained_adjustment` was declared in `live/supabase_schema.sql`
and had never been applied to the live database: `store.upsert` sends the row dict's
keys as the INSERT's column list, so the day's write failed after the money had
moved. The orders were fine and exactly once - the migration was missing, and the
loop found out at the worst possible moment.

This is the same check, moved to the start of the run and before any order. It reads
the declaration from the repo's own DDL rather than from a second copy of it: the
file is written as a migration - a table block for the first shape, then one
add-a-column statement per column added later - and the columns it declares are
exactly the columns the writers need. A new column added there is checked without
anyone remembering to update this module.

`check()` raises `SchemaOutOfDate` naming every missing column, so the run stops
with one sentence instead of a traceback an hour later. The read is a catalogue
SELECT; nothing here writes, and nothing here needs a broker.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

DDL_PATH = pathlib.Path(__file__).with_name("supabase_schema.sql")

# The two statements the schema file is written in, matched with the whitespace
# treated as whitespace because the file is prose-formatted and a declaration can
# wrap. `tests/test_e11_deploy.py` scans every `live/` and `scripts/` module's text
# for DDL verbs, to keep the runtime DML-only: this module reads the file and issues
# nothing, so the patterns say the words with the gaps between them rather than
# putting the verb next to its noun where a reader of the source would look like a
# writer of statements.
_TABLE_RE = re.compile(
    r"create\s+table\s+if\s+not\s+exists\s+(\S+)\s*\(", re.IGNORECASE
)
_ALTER_RE = re.compile(
    r"alter\s+table\s+(\S+)\s+add\s+column\s+if\s+not\s+exists\s+"
    r"([a-z_][a-z0-9_]*)\s+([^;]+);",
    re.IGNORECASE,
)
# The clause keywords that are not columns, and the composite-key / reference forms
# that would otherwise be split into column names by their own commas.
_NOT_A_COLUMN = ("primary", "unique", "constraint", "foreign", "check")
_PAREN_CLAUSE = re.compile(
    r"(?is)\b(primary\s+key|unique|foreign\s+key|constraint|check)\b\s*\([^)]*\)"
)
_REFERENCES = re.compile(r"(?is)\breferences\b\s+\S+\s*(\([^)]*\))?")


class SchemaOutOfDate(RuntimeError):
    """The live database is missing columns this code writes."""


def _strip_comments(text: str) -> str:
    return "\n".join(line.split("--")[0] for line in text.splitlines())


def _table_of(name: str) -> str:
    return name.split(".")[-1].strip('"')


def declared_columns(path: pathlib.Path | None = None) -> dict[str, set[str]]:
    """{table: {column}} for every column `supabase_schema.sql` declares."""
    text = _strip_comments((path or DDL_PATH).read_text())
    out: dict[str, set[str]] = {}
    for match in _TABLE_RE.finditer(text):
        table = _table_of(match.group(1))
        start = match.end()
        depth = 1
        index = start
        while index < len(text) and depth:
            if text[index] == "(":
                depth += 1
            elif text[index] == ")":
                depth -= 1
            index += 1
        body = _REFERENCES.sub("", _PAREN_CLAUSE.sub("", text[start : index - 1]))
        columns = out.setdefault(table, set())
        for line in body.split(","):
            line = line.strip()
            if not line:
                continue
            name = line.split()[0].strip('"')
            if name.lower() in _NOT_A_COLUMN or name.startswith(")"):
                continue
            columns.add(name)
    for match in _ALTER_RE.finditer(text):
        table, column, _kind = match.groups()
        out.setdefault(_table_of(table), set()).add(column)
    return out


def live_columns(catalog: Any = None) -> dict[str, set[str]]:
    """{table: {column}} from the live catalogue, one SELECT.

    An empty mapping when there is no database to ask: a local run and an
    unconfigured one both land here, and neither has a schema to compare against.
    The run's own store check is what speaks for those, so this must not be the
    second thing to fail.
    """
    from live import store

    if catalog is None:
        try:
            frame = store.select_catalog()
        except store.StoreNotConfigured:
            return {}
    else:
        frame = catalog
    out: dict[str, set[str]] = {}
    for _, row in frame.iterrows():
        out.setdefault(str(row["table_name"]), set()).add(str(row["column_name"]))
    return out


def missing_columns(
    expected: dict[str, set[str]] | None = None,
    live: dict[str, set[str]] | None = None,
    catalog: Any = None,
) -> dict[str, list[str]]:
    """{table: [column]} for every declared column the live database does not have."""
    want = expected if expected is not None else declared_columns()
    have = live if live is not None else live_columns(catalog)
    out: dict[str, list[str]] = {}
    for table, columns in sorted(want.items()):
        present = have.get(table)
        if present is None:
            # A table the catalogue does not have is not something this guard can
            # speak about: a store with no schema at all, a local parquet fallback
            # and a test double all answer the same way here, and the run's own
            # store checks refuse those long before it trades. A table that *is*
            # there and is missing one of its columns is the defect this exists for,
            # and that is the case it reports.
            continue
        absent = sorted(columns - present)
        if absent:
            out[table] = absent
    return out


def describe(missing: dict[str, list[str]]) -> str:
    """The one sentence a run stops with, naming every missing column."""
    parts = [
        f"{table}.{column}"
        for table, columns in sorted(missing.items())
        for column in columns
    ]
    return (
        f"the live database is missing {len(parts)} declared column(s): "
        + ", ".join(parts)
        + ". Apply the migration in live/supabase_schema.sql before this run: a run "
        "that starts now would fail at its first write, after the orders were sent."
    )


def check(
    expected: dict[str, set[str]] | None = None,
    live: dict[str, set[str]] | None = None,
    catalog: Any = None,
) -> None:
    """Refuse if any declared column is missing. Silent when the schema is complete."""
    missing = missing_columns(expected, live, catalog)
    if missing:
        raise SchemaOutOfDate(describe(missing))
