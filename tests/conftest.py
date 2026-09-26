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

# `scripts/provision_supabase.py` loads the repository's `.env` into the process when
# it runs, and the tests drive its functions. Without this, a test run picks up the
# developer's real credentials, which is both a hygiene problem and a functional one:
# with a database URL and `EFB_STORE=local` both present the store refuses to choose,
# and every later test fails at `store_mode` with nothing to do with the change under
# test. The suite's documented invariant is that it writes only to the local
# fallback, so the credentials are removed before each test as well as after.
LIVE_CREDENTIALS = (
    "EFB_SUPABASE_DB_URL",
    "EFB_RESEND_API_KEY",
    "EFB_SEED_R2_ACCESS_KEY_ID",
    "EFB_SEED_R2_SECRET_ACCESS_KEY",
    "EFB_R2_ACCESS_KEY_ID",
    "EFB_R2_SECRET_ACCESS_KEY",
)


@pytest.fixture(autouse=True)
def _no_leaked_environment():
    """No test runs with, or leaves behind, the developer's own credentials.

    Also takes the read allowlist off, because a test that drives
    `run_live_daily.main()` installs one for real: left installed it would wrap
    every later test's reads, which is both slower and a false premise for the test
    that asserts the recorder cleans up after itself.
    """
    for name in LIVE_CREDENTIALS:
        os.environ.pop(name, None)
    yield
    seed.unwatch()
    for name in LIVE_CREDENTIALS:
        os.environ.pop(name, None)
