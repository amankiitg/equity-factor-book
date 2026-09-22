"""Provision the EFB live-series tables in Supabase.

Run once before the Render services:
    source .env
    python scripts/provision_supabase.py

Reads the schema from live/supabase_schema.sql and applies it through the
Supabase Management API (needs EFB_SUPABASE_ACCESS_TOKEN, a personal
access token from supabase.com, not the service role key). If the token
is absent, prints the SQL and the SQL editor URL instead.

Env vars:
    EFB_SUPABASE_URL            project URL (https://<ref>.supabase.co)
    EFB_SUPABASE_SECRET_KEY     service role key
    EFB_SUPABASE_ACCESS_TOKEN   personal access token, for the Management API
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "live" / "supabase_schema.sql"


def _load_env() -> None:
    dotenv = ROOT / ".env"
    if not dotenv.exists():
        return
    for line in dotenv.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    _load_env()
    url = os.environ.get("EFB_SUPABASE_URL", "")
    access_token = os.environ.get("EFB_SUPABASE_ACCESS_TOKEN", "")
    schema = SCHEMA_PATH.read_text()

    if not url:
        sys.exit("Set EFB_SUPABASE_URL first.")

    project_ref = url.removesuffix("/rest/v1/").removeprefix("https://").split(".")[0]

    if access_token:
        endpoint = f"https://api.supabase.com/v1/projects/{project_ref}/database/query"
        payload = json.dumps({"query": schema}).encode()
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
                print("Tables created:", response.read().decode()[:200])
            return 0
        except Exception as exc:  # noqa: BLE001 - fall back to manual
            print(f"Management API failed: {exc}")

    print("=" * 60)
    print("Manual table creation")
    print("=" * 60)
    print(f"SQL editor: https://supabase.com/dashboard/project/{project_ref}/sql/new")
    print(f"File: {SCHEMA_PATH}")
    print()
    print(schema)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
