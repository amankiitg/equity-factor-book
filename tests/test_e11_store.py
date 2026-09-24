"""Sprint E11 Part B: the direct-Postgres store and the dry-run resolution.

The store connects directly to Postgres under `EFB_SUPABASE_DB_URL` with
schema `EFB_DB_SCHEMA` (default `efb`), never PostgREST. Every SQL statement
is schema-qualified; nothing targets `public` or an unqualified name, so EFB
cannot touch credit-trading-lab's data in the shared project. The clock starts
only on the literal string "false" in `EFB_DRY_RUN`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from live import store
from scripts import run_live_daily

ROOT = Path(__file__).resolve().parents[1]


def _sql_statements(source: str) -> list[str]:
    """Every SQL statement the store issues, from the source text."""
    statements = []
    for match in re.findall(r'f?["\'](?:INSERT|SELECT)[^"\']*["\']', source):
        statements.append(match)
    # the upsert statement is assembled by _upsert_sql
    statements.append(source)
    return statements


def test_the_upsert_sql_is_schema_qualified() -> None:
    statement = store._upsert_sql("proposals", ["trade_date", "nav"])
    assert 'INSERT INTO "efb"."proposals"' in statement
    assert 'ON CONFLICT ("trade_date")' in statement
    assert "public" not in statement
    assert '"efb"' in statement


def test_the_upsert_sql_uses_the_configured_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EFB_DB_SCHEMA", "efb_test")
    statement = store._upsert_sql("orders", ["trade_date", "ticker", "status"])
    assert 'INSERT INTO "efb_test"."orders"' in statement
    assert '"public"' not in statement


def test_no_store_statement_targets_public_or_an_unqualified_name() -> None:
    source = (ROOT / "live" / "store.py").read_text()
    # the only place a table name is schema-qualified is the helper
    assert "def _qualified(table: str) -> str:" in source
    assert 'return f\'"{_schema()}"."{table}"\'' in source
    # the schema default is efb, never public
    assert 'DEFAULT_SCHEMA = "efb"' in source
    # every SQL statement goes through _qualified, never a raw name
    for line in source.splitlines():
        if "INSERT INTO" in line:
            assert "_qualified(table)" in line
            assert "public" not in line
        if "SELECT * FROM" in line:
            assert "_qualified(table)" in line
            assert "public" not in line


def test_the_schema_sql_targets_only_the_efb_schema() -> None:
    schema = (ROOT / "live" / "supabase_schema.sql").read_text()
    assert "create schema if not exists efb;" in schema
    for line in schema.splitlines():
        if line.startswith("create table"):
            assert "efb." in line
            assert "public" not in line


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("", True),
        ("   ", True),
        ("true", True),
        ("TRUE", True),
        ("True", True),
        ("yes", True),
        ("1", True),
        ("0", True),
        ("garbage", True),
        ("false", False),
        ("FALSE", False),
        ("False", False),
    ],
)
def test_dry_run_resolves_to_dry_run_unless_false(
    value: str | None, expected: bool
) -> None:
    assert run_live_daily.resolve_dry_run(value) is expected
