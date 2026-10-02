"""Sprint E11, Part 4: the owner's deploy steps, and what the runtime does.

Three things are pinned here rather than asserted in prose: the roles SQL grants
nothing outside schema `efb` and covers every verb the store issues, the live
runtime issues no DDL, so a DML write role is enough, and applying the schema file
leaves row level security off on every `efb` table, because a table with it on and
no policy behind it refuses the writer. The provisioning script's primary path is
the SQL editor, which needs no account-wide token, and the token path needs
`--apply`.
"""

from __future__ import annotations

import re
from pathlib import Path

import psycopg
import pytest

from live import store
from scripts import provision_supabase, verify_store_roundtrip

ROOT = Path(__file__).resolve().parents[1]
ROLES = (ROOT / "live" / "supabase_roles.sql").read_text()
SCHEMA = (ROOT / "live" / "supabase_schema.sql").read_text()

# any statement that would need more than DML. The privilege keyword is part of
# the pattern so that prose ("a grant on a schema that does not exist yet") in a
# printed instruction is not mistaken for a statement.
DDL = re.compile(
    r"(?i)\b(create\s+(?:table|schema|role|index|sequence)|alter\s+(?:table|default)|"
    r"grant\s+(?:usage|select|insert|update|delete|all|execute)|revoke\s+\w|"
    r"drop\s+(?:table|schema|role))\b"
)


def _replace_by_date_tables() -> set[str]:
    """Every table any `replace_by_date` caller names, read from the source.

    The grant has to follow the callers, so the set is derived rather than
    pinned: a new `replace_by_date` caller that adds a table fails this until the
    roles file grants delete on it.
    """
    tables: set[str] = set()
    for folder in ("live", "scripts"):
        for path in sorted((ROOT / folder).glob("*.py")):
            for match in re.finditer(
                r"replace_by_date\(\s*[\"']([a-z_]+)[\"']", path.read_text()
            ):
                tables.add(match.group(1))
    return tables


def test_the_roles_cover_every_verb_the_store_issues() -> None:
    """The writer's grants have to cover the store's own verb set.

    The store issues INSERT and UPDATE (the upsert), SELECT (every read), and
    DELETE (`replace_by_date`, which erases a date before re-inserting it, every
    evening). The old test asserted the grant was `select, insert, update` and that
    `delete` appeared nowhere, while the store's own delete path was exercised
    elsewhere: the DELETE runs on the first evening that writes a book, so a
    missing grant fails immediately. The check is the store's verb set, not a
    hand-copied string, and it fails the day the store issues a verb the role does
    not hold.
    """
    source = (ROOT / "live" / "store.py").read_text()
    verbs = {
        verb.upper()
        for verb in re.findall(
            r"\b(?:INSERT|SELECT|DELETE|UPDATE)\b", source, re.IGNORECASE
        )
    }
    assert {"INSERT", "SELECT", "DELETE", "UPDATE"} <= verbs, sorted(verbs)
    # The broad grant covers insert, select and update on every efb table.
    assert re.search(
        r"(?i)grant\s+select,\s*insert,\s*update\s+on all tables in schema efb",
        ROLES,
    ), "the broad grant does not cover insert, select and update"
    # DELETE is granted on exactly the tables replace_by_date is called on. The
    # set comes from the callers and is compared to the file, not to a pinned
    # list: a pinned list fails on a correct new caller (it did, when the fills
    # job became the fourth) while telling the reader nothing the derived set
    # does not already say.
    callers = _replace_by_date_tables()
    assert callers, "no replace_by_date caller was found to trace"
    match = re.search(
        r"(?i)grant\s+delete\s+on\s+([a-z_.\s,]+?)\s+to\s+efb_writer", ROLES
    )
    assert match, "the roles file grants no delete"
    granted = {item.strip().split(".")[-1] for item in match.group(1).split(",")}
    assert granted == callers, (granted, callers)
    # the fills date is the morning cron's, and it is not optional: the delete in
    # `replace_by_date` is what makes a re-run of the same morning converge
    assert "fills" in granted
    # Still scoped to efb and to one role.
    assert "create role efb_writer login" in ROLES
    assert "create role efb_reader login" not in ROLES
    assert "create role efb_archiver login" not in ROLES
    assert ROLES.count("grant usage on schema efb") == 1
    assert ROLES.count("alter default privileges in schema efb") == 1
    assert "schema public" not in ROLES
    assert "on database" not in ROLES
    assert "superuser" not in ROLES
    assert "bypassrls" not in ROLES
    assert "grant select on all tables in schema efb" not in ROLES


def test_the_roles_file_carries_placeholders_not_passwords() -> None:
    for password in re.findall(r"password '([^']+)'", ROLES):
        assert password.startswith("REPLACE_WITH_"), password


def test_the_replace_by_date_roundtrip_replaces_rather_than_merges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verify command's sentinel check, on the local store.

    It must see a replacement (two rows become one, carrying the new value), not a
    merge (two rows, the old value), and it must clear the sentinel date before it
    returns. This is the DELETE path the role's new grant exists for.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(store, "get_connection", lambda: None)

    probes, problems = verify_store_roundtrip.replace_by_date_roundtrip()

    assert problems == []
    assert len(probes) == 1 and probes[0]["status"] == "ok"
    assert "2, 1, 0 rows" in probes[0]["read_back"]
    frame = store.select("positions")
    if not frame.empty:
        dates = frame["trade_date"].astype(str).str.slice(0, 10)
        left = frame.loc[dates == verify_store_roundtrip.ROUNDTRIP_DATE]
        assert left.empty, f"the round trip left {len(left)} sentinel row(s)"


def test_the_roles_step_comes_after_the_schema_step() -> None:
    """A grant on a schema that does not exist yet fails: the order the earlier
    steps had wrong."""
    assert "after live/supabase_schema.sql" in ROLES.lower()
    assert "create schema if not exists efb" in SCHEMA
    # the schema file creates the tables; the roles file grants on them
    assert DDL.search(SCHEMA)
    assert not re.search(r"(?i)\bcreate table\b", ROLES)


def test_the_live_runtime_issues_no_ddl() -> None:
    """Every statement the store runs is DML, so a DML-only role is enough.

    The one-time schema file is applied by the provisioning script or the SQL
    editor, never by a run.
    """
    offenders: list[str] = []
    for folder in ("live", "scripts"):
        for path in sorted((ROOT / folder).glob("*.py")):
            source = path.read_text()
            for match in DDL.finditer(source):
                offenders.append(f"{path.name}: {match.group(0)!r}")
    assert offenders == []


def test_the_store_runs_only_dml_statements() -> None:
    """DML and SELECT only, never DDL.

    The count of `cursor.execute` calls is deliberately **not** pinned. It was two
    until `replace_by_date` added the delete-then-insert pair inside its own
    transaction, at which point this test failed on a correct change: pinning a
    count says nothing about whether the statements are DML, and the suite did not
    run between that change and the next sprint close, so the failure sat there.
    What the test is for is the verb set, and that is what it asserts.
    """
    source = (ROOT / "live" / "store.py").read_text()
    verbs = {
        verb.upper()
        for verb in re.findall(
            r"\b(?:INSERT|SELECT|DELETE|UPDATE|CREATE|DROP|ALTER|TRUNCATE)\b",
            source,
            flags=re.IGNORECASE,
        )
    }
    assert verbs <= {
        "INSERT",
        "SELECT",
        "DELETE",
        "UPDATE",
    }, f"the store issues a statement that is not DML or SELECT: {sorted(verbs)}"
    # And it does issue the three the live series needs, so the assertion above
    # cannot pass by the store having stopped writing anything.
    assert {"INSERT", "SELECT", "DELETE"} <= verbs, sorted(verbs)
    # the insert statement is built by _upsert_sql, which is DML only
    assert "INSERT INTO" in source
    assert "ON CONFLICT" in source
    assert DDL.search(source) is None


def test_the_provisioning_script_prints_the_editor_path_first(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(
        "EFB_SUPABASE_PROJECT_URL", "https://omnsjnosbaiqkrmnknqw.supabase.co"
    )
    monkeypatch.delenv("EFB_SUPABASE_ACCESS_TOKEN", raising=False)

    def _no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("nothing may be sent without --apply")

    monkeypatch.setattr(provision_supabase.urllib.request, "urlopen", _no_network)

    assert provision_supabase.main([]) == 0

    printed = capsys.readouterr().out
    assert "sql/new" in printed
    assert "omnsjnosbaiqkrmnknqw" in printed
    assert printed.index("supabase_schema.sql") < printed.index("supabase_roles.sql")
    assert "Nothing was sent" in printed


def test_the_token_path_needs_the_apply_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(
        "EFB_SUPABASE_PROJECT_URL", "https://omnsjnosbaiqkrmnknqw.supabase.co"
    )
    monkeypatch.setenv("EFB_SUPABASE_ACCESS_TOKEN", "sbp_FAKE_ACCOUNT_WIDE_TOKEN")
    sent: list[object] = []

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'[{"ok": true}]'

    def _capture(request: object, *args: object, **kwargs: object) -> Response:
        sent.append(request)
        return Response()

    monkeypatch.setattr(provision_supabase.urllib.request, "urlopen", _capture)

    # without --apply, nothing is sent even though the token is present
    assert provision_supabase.main([]) == 0
    assert sent == []
    assert "sbp_FAKE_ACCOUNT_WIDE_TOKEN" not in capsys.readouterr().out

    assert provision_supabase.main(["--apply"]) == 0
    assert len(sent) == 1
    request = sent[0]
    body = getattr(request, "data", b"").decode()
    assert "create schema if not exists efb" in body
    assert "create role efb_writer login" in body
    printed = capsys.readouterr().out
    assert "Applied:" in printed
    assert "sbp_FAKE_ACCOUNT_WIDE_TOKEN" not in printed


def test_apply_without_a_token_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(
        "EFB_SUPABASE_PROJECT_URL", "https://omnsjnosbaiqkrmnknqw.supabase.co"
    )
    monkeypatch.delenv("EFB_SUPABASE_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(
        provision_supabase.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("nothing may be sent")),
    )

    assert provision_supabase.main(["--apply"]) == 1

    assert "--apply needs EFB_SUPABASE_ACCESS_TOKEN" in capsys.readouterr().out


def test_the_schema_file_ends_by_disabling_row_level_security() -> None:
    """Applying the schema file has to leave RLS off on every table in `efb`.

    Supabase turns row level security on for the tables its SQL editor is asked to
    create, and an RLS table with no policy refuses everything: re-applying the
    file left the writer role unable to write and the appendix unreadable. The
    file now ends with one block that turns the flag off for the whole schema, and
    the check is that the block is last, that it reads the table names from the
    catalog rather than listing them (so a table added above it cannot be missed),
    and that nothing in the file turns the flag on.
    """
    tail = SCHEMA.split("do $$")[-1]
    assert "disable row level security" in tail
    assert "pg_class" in tail and "pg_namespace" in tail
    assert "'efb'" in tail, "the block does not name the efb schema"
    assert "relrowsecurity" in tail, "the block does not test the flag itself"
    # The block is the last thing the file does, so it runs after every table is
    # created and no statement can turn the flag back on afterwards.
    assert SCHEMA.rstrip().endswith("$$;")
    assert not re.search(r"(?i)\benable\s+row\s+level\s+security", SCHEMA)
    assert SCHEMA.count("disable row level security") == 1


def test_the_schema_block_comes_after_every_table() -> None:
    """The guarantee is about order, not only presence.

    A block that disables RLS before a table exists leaves that table's flag on,
    so the block has to follow every `create table` and every `alter table` in the
    file, which is what "at the end" buys.
    """
    block_at = SCHEMA.index("do $$")
    before, after = SCHEMA[:block_at], SCHEMA[block_at:]
    assert re.search(r"(?m)^create table", before), "the file creates no tables"
    assert re.search(r"(?m)^alter table", before)
    assert not re.search(r"(?m)^(?:create|alter)\s+table", after)


class _FakeCursor:
    """A psycopg cursor that answers one catalog SELECT with these rows."""

    def __init__(self, rows: list[tuple[str, bool]]) -> None:
        self._rows = rows
        self.statement = ""

    def execute(self, statement: str) -> None:
        self.statement = statement

    def fetchall(self) -> list[tuple[str, bool]]:
        return list(self._rows)

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _FakeConnection:
    """A psycopg connection whose cursor answers with these rows."""

    def __init__(self, rows: list[tuple[str, bool]]) -> None:
        self.cursor_object = _FakeCursor(rows)

    def cursor(self) -> _FakeCursor:
        return self.cursor_object

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _rls_probe_with(
    rows: list[tuple[str, bool]], monkeypatch: pytest.MonkeyPatch
) -> tuple[list[dict[str, object]], list[str]]:
    """The verify command's RLS probe, answered from these catalog rows."""
    monkeypatch.setenv(store.URL_ENV, "postgresql://probe/efb")
    monkeypatch.setattr(psycopg, "connect", lambda url: _FakeConnection(rows))
    return verify_store_roundtrip.row_level_security_probe()


def test_the_rls_probe_passes_when_the_flag_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes, problems = _rls_probe_with(
        [("proposals", False), ("orders", False)], monkeypatch
    )
    assert problems == []
    assert [probe["status"] for probe in probes] == ["ok"]
    assert probes[0]["read_back"] == "2 tables, 0 with RLS on"


def test_the_rls_probe_fails_when_one_table_has_it_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One table with the flag on is the failure the writer would hit."""
    probes, problems = _rls_probe_with(
        [("proposals", False), ("orders", True)], monkeypatch
    )
    assert [probe["status"] for probe in probes] == ["MISMATCH"]
    assert len(problems) == 1
    assert "orders" in problems[0]
    assert "supabase_schema.sql" in problems[0]
    assert "proposals" not in problems[0]


def test_the_rls_probe_fails_on_a_schema_with_no_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pass on an empty catalog would be a pass on nothing."""
    probes, problems = _rls_probe_with([], monkeypatch)
    assert [probe["status"] for probe in probes] == ["MISMATCH"]
    assert probes[0]["read_back"] == "no tables in schema efb"
    assert "not been provisioned" in problems[0]


def test_the_verify_command_runs_the_rls_probe() -> None:
    """A probe nobody calls is not a check, so the call site is pinned."""
    source = (ROOT / "scripts" / "verify_store_roundtrip.py").read_text()
    body = source.split("def main(")[1]
    assert "row_level_security_probe()" in body
    assert "probe_problems.extend(rls_problems)" in body
    assert "row level security is off on every efb table" in source
