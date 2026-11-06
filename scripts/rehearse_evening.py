"""Rehearse the real evening entry point for a past close, writes fail-closed.

Runs `run_live_daily.main()` with the clock pinned to a past close, the dry-run
flag on (orders are never sent), the out-of-hours window forced open, and the live
settings applied. The store and the broker are the production ones: reads stay real.
The dry run resolves each leg's asset read-only through a rehearsal-only broker
connect (`alpaca.read_only_client`), which fails closed when the keys are absent,
so a KVUE-type refusal shows in the rehearsal. Every store *write* is patched to
raise `RehearsalWrite`, so if the code path reaches a write the rehearsal fails
closed - nothing is written and the failure is loud, never a silent drop or an
overwrite of a close that already traded.

Usage (owner's machine, with the keys in the environment):

    python scripts/rehearse_evening.py 2026-10-29 2026-11-02 2026-11-03 2026-11-04 2026-11-05

This agent never runs it against the real store or broker and never loads .env;
the owner's main agent runs it. The tests patch `run_live_daily.main`, the store
and the clock, so nothing here reaches a network, a key or a store in a test.
"""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_live_daily  # noqa: E402

# The cron's evening slot in render.yaml is 22:30 UTC. Pinning the clock to that
# hour keeps the window check honest: the rehearsal claims to be the evening that
# would have run for that close.
EVENING_HOUR_UTC = 22
EVENING_MINUTE_UTC = 30

# Store methods that write. Patched to raise so a rehearsal can never move the
# real store. Reads (`select`, `select_catalog`, `seed_marker`) stay real.
STORE_WRITE_METHODS = (
    "upsert",
    "replace_by_date",
    "upsert_one",
    "write_seed_marker",
    "execute",
    "delete",
    "write_local",
)

# The live settings the evening runs under, so the rehearsal is the production shape.
LIVE_ENV = {
    "EFB_DRY_RUN": "true",
    "EFB_CADENCE": "21",
    "EFB_CADENCE_ANCHOR": "2026-10-23",
    "EFB_DRIFT_GUARD": "0.05",
    "EFB_SNAPSHOT": "off",
    "EFB_SHORTABILITY_PRECHECK": "true",
    "EFB_FORCE_HOUR": "true",
}


class RehearsalWrite(RuntimeError):
    """A store write was reached during a rehearsal; nothing was written."""


def pinned_now(close: str) -> datetime:
    """The close's own evening, inside the cron window, as a tz-aware datetime."""
    return datetime.fromisoformat(close).replace(
        hour=EVENING_HOUR_UTC, minute=EVENING_MINUTE_UTC, tzinfo=UTC
    )


class _FixedClock:
    """Stands in for the module's `datetime`: `.now` returns the pinned instant."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self, tz: object = None) -> datetime:
        return self._now


def _make_refuse(name: str):
    def _refuse(*args: object, **kwargs: object) -> None:
        raise RehearsalWrite(
            f"rehearsal reached a store write ({name}); nothing was written"
        )

    return _refuse


def _block_store_writes() -> ExitStack:
    """Patch every store write to raise; reads stay real. Restores on exit."""
    from live import store

    stack = ExitStack()
    for name in STORE_WRITE_METHODS:
        if getattr(store, name, None) is not None:
            stack.enter_context(patch.object(store, name, _make_refuse(name)))
    return stack


def _rehearsal_connect(dry_run: bool = False) -> object:
    """The rehearsal's read-only broker connect, ignoring `dry_run`.

    Fails closed: `alpaca.read_only_client()` raises when the paper keys are
    absent, so a rehearsal that cannot read the broker stops instead of running
    blind. The caller uses this client only for asset resolution; the order path
    stays in dry run, so nothing can be submitted through it.
    """
    from live import alpaca

    return alpaca.read_only_client()


def rehearse(close: str) -> int:
    """Run the real evening entry point for `close`, writes fail-closed.

    `already_ran` is defeated on purpose. A close that has already been filed is
    exactly the close a rehearsal wants to re-run - it is the night whose behaviour
    is being changed - and the runner's idempotence guard would otherwise return
    "already ran" before a single line of the evening executed, which proves
    nothing. Deleting the guard is safe here because the run is a dry run and every
    store write raises: nothing is recorded, so the real record cannot be disturbed
    by a rehearsal having looked at the same close twice.
    """
    from live import morning_job

    fixed = pinned_now(close)
    with (
        patch.object(run_live_daily, "datetime", _FixedClock(fixed)),
        patch.dict(os.environ, LIVE_ENV),
        patch.object(morning_job, "connect", _rehearsal_connect),
        patch.object(run_live_daily, "already_ran", lambda *a, **k: False),
    ):
        with _block_store_writes():
            return run_live_daily.main()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="rehearse the evening entry point for past closes, writes fail-closed"
    )
    parser.add_argument("closes", nargs="+", help="the closes to rehearse, oldest first")
    args = parser.parse_args(argv)
    for close in args.closes:
        try:
            datetime.fromisoformat(close)
        except ValueError:
            parser.error(f"not an ISO date: {close!r}")
    exit_code = 0
    for close in args.closes:
        print(f"rehearsing the evening for close {close} (dry run, writes fail-closed)")
        code = rehearse(close)
        print(f"close {close}: exit {code}")
        if code != 0:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
