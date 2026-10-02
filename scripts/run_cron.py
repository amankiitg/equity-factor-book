"""One cron service, two jobs, and the New York clock decides which one runs.

The blueprint schedules this file once and Render starts it twice a weekday:
`"30 15,22 * * 1-5"`. A cron expression's hour field takes a list, so the one
service owns both slots -- `30 15,22 * * 1-5` means 15:30 and 22:30 UTC -- and this
router is what turns a start into the morning's work or the evening's. Render's own
documentation is the source: "The schedule to use for the cron job, defined as a
[cron expression]" (a link to the standard five-field syntax, whose hour field is a
list, a range, a step or a star), and "All day and time ranges use UTC."

The rule, in New York time because both jobs are defined by the exchange's clock:

* before noon: the fills reconciliation (`scripts/reconcile_fills.py`). 15:30 UTC is
  11:30 EDT and 10:30 EST, so it is before noon in both halves of the year, and it
  is after the 09:30 open in both, which is the whole point of the slot: a market
  DAY order from the previous evening has filled at that open or been cancelled by
  then.
* from 16:00: the evening run (`scripts/run_live_daily.py`), called exactly as the
  start command used to call it, with no argument the old path did not have. 22:30
  UTC is 18:30 EDT and 17:30 EST, inside the after-hours window the run refuses to
  work outside of, and the run's own window check is untouched.
* any other hour: nothing, logged, exit 0. A run at midday has no job to be -- the
  morning's reconciliation is done and the evening has not begun -- and it is not a
  failure, so it exits clean. Both thresholds are in New York, so an hour that is
  mid-afternoon in summer is late morning in winter and routes to the morning job;
  that is the rule stated, and `tests/test_week1_run_cron.py` pins it rather than
  leaving it to be discovered.

Two things the router deliberately does NOT do. It never imports the evening
*entry point* on the morning path (`scripts.run_live_daily` is imported inside the
evening branch only, so the evening run is reached exactly once and deliberately; the
morning's own module imports it for two read-only helpers, `already_ran` and
`record_run`, which is pre-existing and which `tests/test_week1_fills_cron.py` holds
by reading that module's syntax tree). And it makes no decision about *whether* a job
should run beyond the hour: the exchange's calendar, the store's idempotency key and
the run's own window guard are each where they were, so one service cannot make two
jobs disagree about a session.

Both jobs are idempotent by their own key (`fills_reconcile` and `live_daily`, one
`run_status` row each), so the extra start is safe: a second 15:30 start reconciles
the same close to the same rows, and a second evening start exits 0 without
trading. That is also why collapsing two services into one does not need a lock.

Environment: the service holds every key both jobs read, because there is one
service now and no environment group. `EFB_DRY_RUN` and the seed bucket's keys sit
on the same service as the morning job, which never reads them: the morning path
cannot trade, and the test that proves it watches the run rather than the file.
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Render runs this file as `python scripts/run_cron.py`, which puts scripts/ on
# sys.path and not the repository root.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live import staleness  # noqa: E402 - after the path is set

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("run_cron")

# The two routes, as labels the log and the tests can read.
MORNING = "fills"
EVENING = "evening"
IDLE = "idle"

# The schedule the blueprint carries, and the only copy of it in code. The two
# slots inside it are the jobs' own constants: the morning slot is
# `scripts.reconcile_fills.RUN_SLOT_UTC` and the evening one is
# `live.staleness.RUN_SLOT_UTC`, and the tests hold all three together, so a slot
# moved in one place and not the others is a failing test rather than a silent
# mismatch. Monday to Friday, as every service in this project has been.
SCHEDULE = "30 15,22 * * 1-5"

# The hour boundaries, in New York local time. The evening one is the after-hours
# window's own start, not a second copy of it; the morning one is this file's,
# because "before noon" is about the morning's reconciliation and not about the
# exchange.
MORNING_BEFORE_HOUR_ET = 12


def route(stamp: datetime) -> str:
    """Which job this instant is, decided on the New York clock.

    `stamp` may be any aware datetime: it is converted, never assumed. An hour
    that is neither before noon nor past the close is `IDLE`, and `IDLE` is a
    normal outcome rather than an error.
    """
    hour = stamp.astimezone(staleness.NEW_YORK).hour
    if hour < MORNING_BEFORE_HOUR_ET:
        return MORNING
    if hour >= staleness.WINDOW_START_HOUR_ET:
        return EVENING
    return IDLE


def main(*, now: datetime | None = None) -> int:
    """Run the job this hour belongs to. Returns the process exit code."""
    stamp = now if now is not None else datetime.now(UTC)
    local = stamp.astimezone(staleness.NEW_YORK)
    job = route(stamp)
    if job == MORNING:
        # Imported here so the idle and the evening paths never load it.
        from scripts import reconcile_fills

        logger.info(
            "%s UTC is %s in New York: the fills reconciliation",
            stamp.isoformat(timespec="seconds"),
            local.isoformat(timespec="seconds"),
        )
        # No argument of its own: a cron start command has none, and the empty
        # list is what the module's own `__main__` would pass.
        return reconcile_fills.main([])
    if job == EVENING:
        from scripts import run_live_daily

        logger.info(
            "%s UTC is %s in New York: the evening run",
            stamp.isoformat(timespec="seconds"),
            local.isoformat(timespec="seconds"),
        )
        # Unchanged: the same function the start command used to reach through
        # `raise SystemExit(main())`, reached here so the process exit code is the
        # same one, and with no argument that path did not have.
        return run_live_daily.main()
    logger.info(
        "nothing to do at %s UTC (%s in New York): the morning slot is before "
        "%02d:00 and the evening slot is from %02d:00",
        stamp.isoformat(timespec="seconds"),
        local.isoformat(timespec="seconds"),
        MORNING_BEFORE_HOUR_ET,
        staleness.WINDOW_START_HOUR_ET,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
