"""Test-suite environment.

The suite writes only to the store's local parquet fallback under `live/state/`,
and it says so explicitly: `EFB_STORE=local` is the one way to reach that
fallback (live/store.py). A connection string left in the environment is removed
here as well, because a test run must never write a row to the project shared
with credit-trading-lab. A test that needs a connection string to exercise the
Postgres path sets it itself with monkeypatch.
"""

import os

os.environ["EFB_STORE"] = "local"
os.environ.pop("EFB_SUPABASE_DB_URL", None)

# The snapshot switch is required, and the suite must never upload: `off` is
# allowed while dry_run is true, which is what every test run is. A test that
# wants the upload path sets EFB_SNAPSHOT=on and a fake poster itself.
os.environ["EFB_SNAPSHOT"] = "off"
