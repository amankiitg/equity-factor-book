"""Sprint E11, Part 4: the owner's deploy steps, and what the runtime does.

Two things are pinned here rather than asserted in prose: the roles SQL grants
nothing outside schema `efb`, and the live runtime issues no DDL, so a DML-only
write role is enough. The provisioning script's primary path is the SQL editor,
which needs no account-wide token, and the token path needs `--apply`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts import provision_supabase

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


def test_the_roles_file_grants_only_on_efb() -> None:
    assert "create role efb_writer login" in ROLES
    assert "create role efb_reader login" in ROLES
    assert ROLES.count("grant usage on schema efb") == 2
    assert ROLES.count("alter default privileges in schema efb") == 2
    assert "schema public" not in ROLES
    assert "on database" not in ROLES
    assert "superuser" not in ROLES
    assert "bypassrls" not in ROLES
    # the write role gets DML, the read role only SELECT
    assert "grant select, insert, update, delete on all tables in schema efb" in ROLES
    assert "grant select on all tables in schema efb" in ROLES
    assert "alter default privileges in schema efb" in ROLES


def test_the_roles_file_carries_placeholders_not_passwords() -> None:
    for password in re.findall(r"password '([^']+)'", ROLES):
        assert password.startswith("REPLACE_WITH_"), password


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
    source = (ROOT / "live" / "store.py").read_text()
    statements = re.findall(r"cursor\.(?:execute|executemany)\((.{0,60})", source)
    assert len(statements) == 2
    assert "SELECT * FROM" in statements[1]
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
