"""The start-of-run router: one service, two slots, and the New York clock.

`render.yaml` starts `scripts/run_cron.py` at `"30 15,22 * * 1-5"`, so the one
service owns both slots and the hour in New York decides which job a start becomes.
These tests are the proof of the three things that claim rests on:

* the two slots land on the two jobs on **both sides of the daylight-time change**,
  and the morning slot is still after the open the previous evening's orders fill at;
* an hour between them does **nothing at all** -- no broker read, no write, no
  message -- and exits 0;
* the morning route cannot reach a sizing or submit entry point, now that it shares
  a service (and therefore an environment) with the evening run, which is the thing
  two services used to guarantee by construction.

The fakes are the fills cron's own (`tests/test_week1_fills_cron.py`): one harness,
so the morning path cannot be tested against a different morning than the one that
job is tested against. What this file adds around it is the clock and the route.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from live import staleness, store
from scripts import reconcile_fills, run_cron, run_live_daily
from tests.test_week1_fills_cron import CLOSE, TODAY, _install, _order

ROOT = Path(__file__).resolve().parents[1]
NEW_YORK = ZoneInfo("America/New_York")

# Two Mondays, one on each side of the change: 2026-10-05 is UTC-4, 2026-11-16 is
# UTC-5. The offsets are asserted rather than assumed, so a test that silently ran
# on two days of the same season would fail instead of passing quietly.
EDT_DAY, EDT_OFFSET = "2026-10-05", -4
EST_DAY, EST_OFFSET = "2026-11-16", -5
DAYS = [
    pytest.param(EDT_DAY, EDT_OFFSET, id="EDT"),
    pytest.param(EST_DAY, EST_OFFSET, id="EST"),
]


def _at(day: str, hour: int, minute: int) -> datetime:
    """An aware UTC instant, from a UTC hour as the blueprint's schedule reads."""
    return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00+00:00")


def _local(day: str, hour: int, minute: int = 0) -> datetime:
    """An aware instant from a *New York* wall clock, for the dead-zone cases."""
    return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00").replace(
        tzinfo=NEW_YORK
    )


def _slots(schedule: str) -> tuple[str, list[str], str]:
    """The minute, the hour field's list and the day field of a cron schedule."""
    minute, hour, day_of_month, month, day_of_week = schedule.split()
    assert day_of_month == "*" and month == "*"
    return minute, hour.split(","), day_of_week


def test_the_blueprints_two_slots_are_the_two_jobs_own_slots() -> None:
    """One string in the blueprint, and three constants that have to agree.

    A cron hour field takes a list, so the one service carries both starts. The
    morning slot is the reconciliation's own `RUN_SLOT_UTC`, the evening slot is the
    evening run's (`live.staleness.RUN_SLOT_UTC`, which the staleness gate and the
    page's countdown read too), and this test is what keeps a slot moved in one
    place from passing unnoticed in the others.
    """
    minute, hours, day_of_week = _slots(run_cron.SCHEDULE)
    morning_hour, morning_minute = reconcile_fills.RUN_SLOT_UTC
    evening_hour, evening_minute = staleness.RUN_SLOT_UTC
    assert hours == [str(morning_hour), str(evening_hour)]
    assert minute == f"{morning_minute:02d}" == f"{evening_minute:02d}"
    assert day_of_week == "1-5", "the jobs are weekday jobs"

    render = (ROOT / "render.yaml").read_text()
    assert f'schedule: "{run_cron.SCHEDULE}"' in render
    assert "startCommand: python scripts/run_cron.py" in render


@pytest.mark.parametrize("day,offset", DAYS)
def test_both_slots_route_to_their_job_on_both_sides_of_the_dst_change(
    day: str, offset: int
) -> None:
    """15:30 UTC is the morning in EST and in EDT, 22:30 UTC the evening in both.

    The rule is stated in New York hours, so the same two UTC instants have to keep
    their meanings after the clocks move. The morning slot is also checked against
    the exchange's own open, because the reason it is late morning rather than early
    is that the previous evening's DAY orders fill at that open.
    """
    minute, hours, _ = _slots(run_cron.SCHEDULE)
    morning = _at(day, int(hours[0]), int(minute))
    evening = _at(day, int(hours[1]), int(minute))

    local_morning = morning.astimezone(NEW_YORK)
    local_evening = evening.astimezone(NEW_YORK)
    assert local_morning.utcoffset() == timedelta(hours=offset)
    assert local_evening.utcoffset() == timedelta(hours=offset)

    assert run_cron.route(morning) == run_cron.MORNING
    assert local_morning.hour < run_cron.MORNING_BEFORE_HOUR_ET
    # After the open the orders fill at, which is the whole point of the hour.
    opened = (
        staleness.calendar()
        .schedule(start_date=day, end_date=day, tz="UTC")["market_open"]
        .iloc[0]
    )
    assert morning > opened, f"{day}: the morning slot is before the open"

    assert run_cron.route(evening) == run_cron.EVENING
    assert staleness.in_cron_window(evening), "the evening slot is outside the window"
    assert local_evening.hour >= staleness.WINDOW_START_HOUR_ET


def test_the_route_reads_new_york_and_not_utc() -> None:
    """The same UTC hour is two different jobs on two different days.

    16:30 UTC is 12:30 New York in summer, which is the dead zone, and 11:30 New
    York in winter, which is the morning. A router written on UTC hours -- the
    tempting simplification, since the two scheduled slots happen to fall the right
    way in both seasons -- would call both of them the evening. This is the case
    that tells the two implementations apart.
    """
    assert run_cron.route(_at(EDT_DAY, 16, 30)) == run_cron.IDLE
    assert run_cron.route(_at(EST_DAY, 16, 30)) == run_cron.MORNING


@pytest.mark.parametrize("day,offset", DAYS)
@pytest.mark.parametrize("hour", [12, 13, 14, 15])
def test_a_midday_start_does_nothing_and_exits_clean(
    day: str,
    offset: int,
    hour: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Between the slots there is no job, and no job means no side effect.

    Not an error and not a fallback to either job: the morning's reconciliation is
    done and the evening has not begun, so the run records nothing, reads no order,
    writes no table and sends no message, and the process exits 0 so Render does not
    report a failed day.
    """
    harness = _install(
        monkeypatch,
        tmp_path,
        broker_orders={"oid-dg": _order("filled")},
        now=f"{TODAY}T15:30:00+00:00",
    )
    stamp = _local(day, hour, 30)
    assert run_cron.route(stamp) == run_cron.IDLE

    code = run_cron.main(now=stamp)

    assert code == 0
    assert harness.broker.asked == []
    assert harness.broker.submitted == []
    assert harness.written == []
    assert harness.recorded == []
    assert harness.sent == []
    assert harness.published == []


@pytest.mark.parametrize("day,offset", DAYS)
def test_the_morning_route_reconciles_and_cannot_reach_the_evening_run(
    day: str,
    offset: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At a morning start the fills run, and the evening entry point is not entered.

    The strong statement, and the one that matters now that both jobs share an
    environment: the broker here refuses to be sent anything, `store_proposal` is
    patched to fail, and the evening's own `main` fails the test if it is called at
    all. The morning still exits 0 and has written the fills row, so the run really
    happened and really did nothing else.
    """
    harness = _install(
        monkeypatch,
        tmp_path,
        broker_orders={"oid-dg": _order("filled")},
        now=f"{TODAY}T15:30:00+00:00",
    )
    monkeypatch.setattr(
        run_live_daily,
        "main",
        lambda: pytest.fail("the morning route entered the evening run"),
    )

    minute, hours, _ = _slots(run_cron.SCHEDULE)
    code = run_cron.main(now=_at(day, int(hours[0]), int(minute)))

    assert code == 0
    assert harness.broker.submitted == [], "the morning sent an order"
    assert harness.recorded == [(reconcile_fills.JOB, TODAY, "ok")]
    stored = store.select("fills")
    assert list(stored["ticker"]) == ["DG"]
    assert str(stored.iloc[0]["trade_date"])[:10] == CLOSE
    assert set(harness.written) == {"fills", "run_status"}


def test_the_morning_route_ignores_the_services_evening_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`EFB_DRY_RUN=false` and the seed keys are on the service, and do not matter.

    One service means the morning job's environment is the evening's, including the
    switch that makes a run trade and the four keys of the history bucket. The
    morning path must be blind to all of them: the seeding entry point is patched to
    fail, so a morning that read `EFB_INIT_STORE` would stop here rather than quietly
    download a seed nobody asked for.
    """
    monkeypatch.setenv("EFB_DRY_RUN", "false")
    monkeypatch.setenv("EFB_INIT_STORE", "true")
    for key in (
        "EFB_SEED_R2_ACCOUNT_ID",
        "EFB_SEED_R2_BUCKET",
        "EFB_SEED_R2_ACCESS_KEY_ID",
        "EFB_SEED_R2_SECRET_ACCESS_KEY",
    ):
        monkeypatch.setenv(key, "set-for-the-evening-path")
    monkeypatch.setattr(
        store,
        "init_store_flag",
        lambda: pytest.fail("the morning route read the seed request"),
    )
    monkeypatch.setattr(
        run_live_daily,
        "main",
        lambda: pytest.fail("the morning route entered the evening run"),
    )
    harness = _install(
        monkeypatch,
        tmp_path,
        broker_orders={"oid-dg": _order("filled")},
        now=f"{TODAY}T15:30:00+00:00",
    )

    code = run_cron.main(now=_at(EDT_DAY, *reconcile_fills.RUN_SLOT_UTC))

    assert code == 0
    assert harness.recorded == [(reconcile_fills.JOB, TODAY, "ok")]
    assert set(harness.written) == {"fills", "run_status"}
    assert harness.broker.submitted == []
    assert store.select("fills").iloc[0]["close_price"] == 12.5


def test_the_evening_route_is_the_call_the_start_command_used_to_make(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The evening run, reached exactly as before: no argument, same exit code.

    The behaviour, the environment and the outputs of the evening are what this
    change had to leave alone, and the code is the evidence: one call, no
    positional or keyword argument, and the return value passed straight out as the
    process exit code, which is what `raise SystemExit(main())` did before.
    """
    _install(
        monkeypatch,
        tmp_path,
        broker_orders={"oid-dg": _order("filled")},
        now=f"{TODAY}T22:30:00+00:00",
    )
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def recorder(*args: Any, **kwargs: Any) -> int:
        calls.append((args, kwargs))
        return 7

    monkeypatch.setattr(run_live_daily, "main", recorder)

    code = run_cron.main(now=_at(EDT_DAY, *staleness.RUN_SLOT_UTC))

    assert code == 7, "the evening's exit code has to survive the router"
    assert calls == [((), {})], "the evening run is called with no argument"


def test_the_routers_own_source_names_no_sizing_or_submit_entry_point() -> None:
    """The router's own names, read from the syntax tree.

    The same strongest form the fills job is held to, applied to the file that now
    decides between the jobs: it names no sizing, no proposal and no submit entry
    point of its own, so it cannot grow one by accident. The negative control is the
    evening's script, which does name them, so this is a check on the file and not
    on the word list.
    """
    source = (ROOT / "scripts" / "run_cron.py").read_text()
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
            if node.module:
                names.add(node.module.split(".")[-1])
        elif isinstance(node, ast.Import):
            names.update(alias.name.split(".")[-1] for alias in node.names)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)

    forbidden = {
        "submit_market_orders",
        "submit_order",
        "MarketOrderRequest",
        "store_proposal",
        "build_proposal",
        "target_orders",
        "minimum_skips",
        "run_morning",
        "evening_job",
        "morning_job",
        "guards",
        "sizing",
        "optimize",
        "allocate",
    }
    assert not (names & forbidden), f"the router names {names & forbidden}"

    evening = (ROOT / "scripts" / "run_live_daily.py").read_text()
    for present in ("store_proposal", "run_morning", "morning_job"):
        assert present in evening, "the negative control no longer holds"

    # What it does name: the two entry points, reached through their own branches.
    assert "reconcile_fills" in names and "run_live_daily" in names
