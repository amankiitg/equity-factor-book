"""Provision the EFB schema and roles in Supabase, once, before the Render services.

**The primary path needs no token.** The script prints the SQL editor link and
the two files to run, in order:

    source .env
    python scripts/provision_supabase.py

  1. `live/supabase_schema.sql` creates schema `efb` and its 18 tables.
  2. `live/supabase_roles.sql` creates `efb_writer` and `efb_reader` and grants
     them, on schema `efb` and nowhere else.

The roles step must come second: a grant on a schema that does not exist yet
fails.

**The alternative path applies the same SQL through the Supabase Management
API**, which needs `EFB_SUPABASE_ACCESS_TOKEN`, an account-wide personal access
token:

    python scripts/provision_supabase.py --apply

The token is only for this one-time step and is never set on either Render
service, and the store issues no DDL at runtime, so a DML-only write role is
enough.

Env vars:
    EFB_SUPABASE_PROJECT_URL   project URL, for the SQL editor link
    EFB_SUPABASE_ACCESS_TOKEN  only with --apply
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "live" / "supabase_schema.sql"
ROLES_PATH = ROOT / "live" / "supabase_roles.sql"


def _load_env() -> None:
    dotenv = ROOT / ".env"
    if not dotenv.exists():
        return
    for line in dotenv.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def _project_ref(url: str) -> str:
    return url.removesuffix("/rest/v1/").removeprefix("https://").split(".")[0]


def _instructions(project_ref: str) -> None:
    """The owner's path, printed first and always."""
    editor = f"https://supabase.com/dashboard/project/{project_ref}/sql/new"
    print("=" * 70)
    print("Provision EFB in the SQL editor (no token needed)")
    print("=" * 70)
    print(f"1. Open {editor}")
    print("2. Paste and run, in this order:")
    print(f"     {SCHEMA_PATH}   (schema efb and its 18 tables)")
    print(f"     {ROLES_PATH}    (efb_writer and efb_reader, schema efb only)")
    print("3. In the roles file, replace both password placeholders first. One")
    print("   way to make one:")
    print('     python -c "import secrets; print(secrets.token_urlsafe(32))"')
    print()
    print("The roles step is second on purpose: a grant on a schema that does")
    print("not exist yet fails, which is the order the earlier steps had wrong.")
    print()


def _apply(project_ref: str, access_token: str) -> int:
    """The alternative path: the same SQL through the Management API."""
    sql = SCHEMA_PATH.read_text() + "\n" + ROLES_PATH.read_text()
    endpoint = f"https://api.supabase.com/v1/projects/{project_ref}/database/query"
    payload = json.dumps({"query": sql}).encode()
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            print("Applied:", response.read().decode()[:200])
    except Exception as exc:  # noqa: BLE001 - fall back to the printed steps
        print(f"Management API failed: {exc}")
        print("Use the SQL editor steps printed above instead.")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    _load_env()
    url = os.environ.get("EFB_SUPABASE_PROJECT_URL", "")
    access_token = os.environ.get("EFB_SUPABASE_ACCESS_TOKEN", "")

    if not url:
        sys.exit("Set EFB_SUPABASE_PROJECT_URL first.")

    project_ref = _project_ref(url)
    _instructions(project_ref)

    if "--apply" in args:
        if not access_token:
            print("--apply needs EFB_SUPABASE_ACCESS_TOKEN. Nothing was sent.")
            return 1
        return _apply(project_ref, access_token)

    print("Nothing was sent: pass --apply to use the Management API instead.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
