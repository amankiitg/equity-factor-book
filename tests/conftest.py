"""Test-suite environment.

The suite writes only to the store's local parquet fallback under `live/state/`,
and it says so explicitly: `EFB_STORE=local` is the one way to reach that
fallback (live/store.py). A connection string left in the environment is removed
here as well, because a test run must never write a row to the project shared
with credit-trading-lab. A test that needs a connection string to exercise the
Postgres path sets it itself with monkeypatch.
"""

import os

import pytest

# What the developer's shell held before this file took it away. A gate run in a
# shell where `.env` has been sourced is exactly how a test fixture once landed in the
# live database (`oid-dg`, DG, 2026-10-01, written by the fills-cron test's own order
# through `store.upsert`), so the suite refuses to run at all in that shell rather than
# quietly redirecting every write to the local fallback.
LIVE_AT_START = {
    name: os.environ[name]
    for name in (
        "EFB_SUPABASE_DB_URL",
        "EFB_ALPACA_PAPER_API_KEY",
        "EFB_ALPACA_PAPER_SECRET_KEY",
        "EFB_R2_ACCOUNT_ID",
        "EFB_R2_ACCESS_KEY_ID",
        "EFB_R2_SECRET_ACCESS_KEY",
        "EFB_SEED_R2_ACCESS_KEY_ID",
        "EFB_SEED_R2_SECRET_ACCESS_KEY",
        "EFB_RESEND_API_KEY",
    )
    if os.environ.get(name, "").strip()
}

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

# The evening refuses outside the 16:00-20:00 New York window it trades in, and
# the suite runs at whatever hour it is run. Every test that drives
# `run_live_daily.main()` therefore needs the window open, exactly as a rehearsal
# does; without this the suite's result would depend on the clock, and a test
# written at 18:00 would fail at 15:00. The refusal itself is tested by deleting
# this variable for the test, so the guard is still exercised in both directions.
os.environ["EFB_FORCE_HOUR"] = "true"


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
    # The paper keys are here because the evening now reads the account even in
    # dry run: without this a test run with a developer's shell would call the
    # real paper API, and a test must never touch it.
    "EFB_ALPACA_PAPER_API_KEY",
    "EFB_ALPACA_PAPER_SECRET_KEY",
    # The account the keys have to reach. Every run compares it against the number
    # the broker reports and refuses when the two disagree or when this is unset,
    # so a developer's own account number in the shell would decide which fakes
    # pass. A test that fakes the read names the account itself.
    "EFB_ALPACA_ACCOUNT_ID",
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


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Fail every test that could write, when the shell holds live credentials.

    The suite's invariant is that it writes only to the local fallback, and the
    environment is scrubbed below so that it does. Scrubbing alone is not enough: a
    write that would have gone to the live store is then silently a write somewhere
    else, and the run looks green. Measured on 2026-10-29, a `efb.fills` row for DG
    (`oid-dg`, 2026-10-01, $517.42) was in the live database with the exact values the
    fills-cron test builds, which is a test fixture that reached the live store.

    So: with any live credential present, a test without the `live_readonly` marker
    fails here, before it runs, naming what is set. A read-only live check opts in and
    takes the `live_store_env` fixture to get its credential back for the length of
    the test.
    """
    if not LIVE_AT_START:
        return
    if item.get_closest_marker("live_readonly") is not None:
        return
    names = ", ".join(sorted(LIVE_AT_START))
    pytest.fail(
        "the environment holds live credentials ("
        f"{names}) so this test could write to the live store, the broker or R2; "
        "run the suite in a fresh shell that has not sourced .env, or mark the test "
        "live_readonly if it only reads",
        pytrace=False,
    )


@pytest.fixture
def live_store_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """The shell's live credentials, restored for one marked read-only test.

    Empty without a `.env` in the shell, which is why a read-only live check skips
    rather than fails in a normal gate: it cannot reach the store it wants to read.
    """
    for name, value in LIVE_AT_START.items():
        monkeypatch.setenv(name, value)
    # This module forces the local store for every other test; leaving it set would
    # give `store_mode()` the pair it refuses.
    monkeypatch.delenv("EFB_STORE", raising=False)
    return dict(LIVE_AT_START)
