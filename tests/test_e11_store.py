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

import pandas as pd
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


def test_the_local_fallback_needs_an_explicit_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E11-F17: a missing URL is an error, not a quiet write to a local disk."""
    monkeypatch.delenv("EFB_SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("EFB_STORE", raising=False)
    with pytest.raises(store.StoreNotConfigured) as err:
        store.store_mode()
    assert "EFB_SUPABASE_DB_URL is not set" in str(err.value)
    # A write and a read both refuse, so the run cannot half-work either.
    with pytest.raises(store.StoreNotConfigured):
        store.upsert("nav", [{"trade_date": "2026-09-22", "nav": 1.0}])
    with pytest.raises(store.StoreNotConfigured):
        store.select("nav")
    # The request is what unlocks it.
    monkeypatch.setenv("EFB_STORE", "local")
    assert store.store_mode() == "local"
    assert store.is_supabase() is False


def test_local_mode_is_refused_where_render_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EFB_SUPABASE_DB_URL", raising=False)
    monkeypatch.setenv("EFB_STORE", "local")
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(store.StoreNotConfigured) as err:
        store.store_mode()
    assert "RENDER" in str(err.value)
    # And the label says so rather than pretending, because that line leads the
    # message the owner reads.
    monkeypatch.setenv("EFB_STORE", "local")
    assert store.store_label().startswith("ERROR ")


def test_a_connection_string_and_a_local_request_do_not_both_win(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EFB_SUPABASE_DB_URL", "postgresql://user:pw@host:5432/db")
    monkeypatch.setenv("EFB_STORE", "local")
    with pytest.raises(store.StoreNotConfigured) as err:
        store.store_mode()
    assert "set one of them" in str(err.value)
    # Either one alone is fine, and a URL alone means Postgres.
    monkeypatch.delenv("EFB_STORE")
    assert store.store_mode() == "postgres"
    assert store.is_supabase() is True
    monkeypatch.setenv("EFB_STORE", "local")
    monkeypatch.delenv("EFB_SUPABASE_DB_URL")
    assert store.store_mode() == "local"


def test_an_unknown_store_mode_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EFB_STORE", "parguet")
    monkeypatch.delenv("EFB_SUPABASE_DB_URL", raising=False)
    with pytest.raises(store.StoreNotConfigured) as err:
        store.store_mode()
    assert "is not a store mode" in str(err.value)


def test_the_store_label_names_the_store_or_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EFB_SUPABASE_DB_URL", raising=False)
    monkeypatch.setenv("EFB_STORE", "local")
    monkeypatch.delenv("RENDER", raising=False)
    assert store.store_label() == "local parquet (live/state/supabase)"
    monkeypatch.setenv("EFB_SUPABASE_DB_URL", "postgresql://user:pw@host:5432/db")
    monkeypatch.delenv("EFB_STORE")
    assert store.store_label() == "postgres/efb"
    monkeypatch.setenv("EFB_DB_SCHEMA", "efb_live")
    assert store.store_label() == "postgres/efb_live"


def test_json_text_has_no_nan_because_jsonb_refuses_it() -> None:
    # json.dumps writes a bare NaN, which is not JSON and which Postgres jsonb
    # rejects, so one NaN in a run's inputs would fail the whole row.
    import json
    import math

    raw = json.dumps({"r": float("nan")})
    assert "NaN" in raw
    safe = store.json_text({"r": float("nan"), "nested": [float("inf"), {"d": 1.5}]})
    assert "NaN" not in safe and "Infinity" not in safe
    assert json.loads(safe) == {"r": None, "nested": [None, {"d": 1.5}]}
    # A real value, a date and a string that looks like a number are untouched.
    stamp = pd.Timestamp("2026-09-24")
    assert json.loads(store.json_text({"d": stamp}))["d"] == stamp.isoformat()
    assert json.loads(store.json_text({"s": "7"}))["s"] == "7"
    assert math.isfinite(json.loads(store.json_text({"f": 0.1 + 0.2}))["f"])


def test_the_roundtrip_command_refuses_without_a_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It reads the real `efb` schema by design, so it refuses the fallback."""
    from scripts import verify_store_roundtrip

    monkeypatch.delenv("EFB_SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("EFB_STORE", raising=False)
    assert verify_store_roundtrip.main([]) == 2
    monkeypatch.setenv("EFB_STORE", "local")
    assert verify_store_roundtrip.main([]) == 2


def test_the_comparison_basis_normalises_dates_and_missing_values() -> None:
    """The appendix returns dates and the artifact timestamps: one basis, or the
    comparison would report a dtype difference as a data difference."""
    from scripts import verify_store_roundtrip

    theirs = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-09-04"), pd.Timestamp("2026-09-03")],
            "ticker": ["APH", "APH"],
            "specific_var": [float("nan"), 0.0006],
        }
    )
    ours = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-09-03"), pd.Timestamp("2026-09-04")],
            "ticker": ["APH", "APH"],
            "specific_var": [0.0006, None],
        }
    )
    left, right = verify_store_roundtrip.canonical(
        theirs
    ), verify_store_roundtrip.canonical(ours)
    assert left["date"].tolist() == ["2026-09-03", "2026-09-04"]
    assert verify_store_roundtrip.frame_hash(left) == verify_store_roundtrip.frame_hash(
        right
    )
    # And a real value difference is caught.
    other = ours.assign(specific_var=[0.0007, None])
    assert verify_store_roundtrip.frame_hash(left) != verify_store_roundtrip.frame_hash(
        verify_store_roundtrip.canonical(other)
    )


def test_no_test_leaks_the_store_directory_by_assignment() -> None:
    """The bug the full suite caught, pinned so the fast selection cannot hide it.

    `tests/test_e11_appendix.py` used to assign `store.LOCAL_DIR` directly. That
    test is marked slow, so `make test-fast` never ran it and never saw the leak,
    while a full run had every later test reading and writing a temporary
    directory. Monkeypatch is the only way this module's directory may move.
    """
    offenders = []
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("monkeypatch.setattr("):
                continue
            if re.search(r"\bstore\.LOCAL_DIR\s*=", stripped):
                offenders.append(f"{path.name}:{number}: {stripped}")
    assert not offenders, "assign store.LOCAL_DIR through monkeypatch: " + "; ".join(
        offenders
    )
