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

# The first-run flag seeds the store and is removed after it, so a stray value in
# a developer's shell must not decide whether a test run seeds. A test that wants
# the flag sets it itself with monkeypatch.
os.environ.pop("EFB_INIT_STORE", None)

# The snapshot switch is required, and the suite must never upload: `off` is
# allowed while dry_run is true, which is what every test run is. A test that
# wants the upload path sets EFB_SNAPSHOT=on and a fake poster itself.
os.environ["EFB_SNAPSHOT"] = "off"


import pytest  # noqa: E402 - after the environment, which must be set first

from live import seed  # noqa: E402


@pytest.fixture(autouse=True)
def _no_leaked_watchers():
    """The run installs a read allowlist on itself; no test may leave one on.

    A test that drives `run_live_daily.main()` installs the guard for real. Left
    installed it would wrap every later test's reads, which is both slower and a
    false premise for the test that asserts the recorder cleans up after itself.
    """
    yield
    seed.unwatch()
