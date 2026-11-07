"""Rehearse the real evening entry point for a past close, against a sandbox store.

Runs `run_live_daily.main()` with the clock pinned to a past close's evening, the
dry-run flag on (no order is ever sent), the out-of-hours window forced open, and
the live settings applied. The broker is the production one and read-only.

The store is a **sandbox**. Every live table - the appendix included - is read
from production and copied into a temporary directory, then the store is switched
to `EFB_STORE=local` against that directory with the production DSN removed from
the process. The evening then files for real: the proposal, positions, orders,
appendix and the cron row all land in the copy, which is what makes "ok and filed"
something the rehearsal can check rather than assert. The live store is unreachable
by construction, not by discipline.

Delivery is captured, never sent: `notify.send` is patched to keep the message and
answer `sent`. Answering `skipped` would be wrong - a skipped message is what a run
with no channel gets, and the runner rightly refuses to file a day the owner was
never told about.

Every part of that is installed before the run, and the rehearsal refuses to start
if any part cannot be: the sandbox unseeded, the mode still `postgres`, a DSN still
visible, delivery not captured, or the clock not pinned. A rehearsal that silently
ran against the live store and mailed the owner is the failure this shape prevents.

Usage (the owner's machine, with the keys in the environment):

    python scripts/rehearse_evening.py 2026-10-29 2026-11-02 2026-11-03

Tests patch `run_live_daily.main`, the store and the clock, so nothing here reaches
a network, a key or a store in a test.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from contextlib import ExitStack
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pandas as pd

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


SCALARS = (str, int, float, bool, bytes, type(None))


def _cell(value: object) -> object:
    """One cell the way parquet can hold it: a dict or an array as JSON, a date as ISO.

    Everything that is not a scalar goes through `json.dumps`, because a psycopg JSON
    column can come back as a wrapper type rather than a plain dict, and one such cell is
    enough to make pyarrow reject the whole column.
    """
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, SCALARS):
        return value
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def coerce_for_parquet(frame: pd.DataFrame) -> pd.DataFrame:
    """How to write one live table so the copy reads back as it reads live.

    Two shapes parquet cannot take as-is, both found by running it. A JSON column - the
    proposal manifest - is a dict in the frame, and writing it unmixed raises "cannot mix
    list and non-list". And a date column written as a date reads back as an integer width,
    which is what broke the cron row: the run appends `run_date` as text to a column that
    had become integers. Both are written as text, which is what the readers already parse.
    """
    coerced = frame.copy()
    for column in coerced.columns:
        series = coerced[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            continue
        if series.dtype != object:
            continue
        # A date object is stored by pyarrow as date32, which pandas reads back as an
        # integer width; a datetime is stored as a timestamp and reads back as one. So a
        # date column becomes a timestamp on the way in, and the copy then behaves like
        # the database for every append the run makes.
        sample = None
        for value in series:
            if value is None:
                continue
            try:
                if pd.isna(value):
                    continue
            except (TypeError, ValueError):  # an array-valued cell is not a date
                sample = value
                break
            sample = value
            break
        if isinstance(sample, date | datetime | pd.Timestamp):
            coerced[column] = pd.to_datetime(series, errors="coerce")
            continue
        # A `numeric` column arrives as `Decimal`, which pyarrow will only take as text;
        # the run then appends floats and the column refuses them ("could not convert
        # '7.917391' with type str: tried to convert to double"). A number is a number.
        if isinstance(sample, Decimal):
            coerced[column] = pd.to_numeric(series, errors="coerce")
            continue
        coerced[column] = series.map(_cell)
    return coerced


def restore_dates(frame: pd.DataFrame) -> pd.DataFrame:
    """Read a table back with its date columns as dates again.

    A parquet round-trip does not keep the shape psycopg gives: a `date` column comes back
    as an integer width, and a run that then appends its own `run_date` as text fails with
    "object of type str cannot be converted to int" - the exact failure the cron row hit.
    The copy is written as ISO text and read back here as timestamps, so everything the run
    reads looks the way it looks against Postgres.
    """
    restored = frame.copy()
    # A text copy comes back as object; a categorical column then cannot be concatenated
    # with the run's own rows ("values is not ordered"), so the copy is plain text by the
    # time the run sees it, which is what it sees against Postgres as well.
    for column in restored.columns:
        if str(restored[column].dtype) == "category":
            restored[column] = restored[column].astype(object)
    return restored


class RehearsalSandbox:
    """A local store holding a copy of the live tables, with no route back to them.

    Entering reads every live table through the production store and writes it into a
    temporary directory, then removes the production DSN from the environment and asks for
    `EFB_STORE=local` with `store.LOCAL_DIR` pointed at that directory. Leaving puts the
    environment and the module back exactly as they were.

    Fail-closed on installation, which is the property that matters: a table that cannot be
    copied, a mode that is still `postgres`, or a DSN still visible once the sandbox is in
    force all raise before the evening runs.

    Two write-shape details, both learned by running it. A JSON column (the proposal
    manifest) is a dict in the frame and parquet cannot hold one, so those cells are
    written as the JSON text the live readers already parse. And a date column written to
    parquet reads back as an integer width, which breaks `run_date` when the run appends its
    own cron row, so dates are written as ISO text and parsed back on the way in.
    """

    def __init__(self, close: str) -> None:
        self.close = close
        self.dir = Path(tempfile.mkdtemp(prefix=f"efb-rehearsal-store-{close}-"))
        self.tables = self.dir / "supabase"
        self.seeded: dict[str, int] = {}
        self._saved_env: dict[str, str | None] = {}
        self._stack = ExitStack()

    def __enter__(self) -> RehearsalSandbox:
        # The appendix registers its own tables into `store.TABLES` when it is imported,
        # and the evening opens that store before it prices anything, so a sandbox that
        # skipped them would fail at `open_store` with `StoreAppendixLost` - which is
        # exactly what the first attempt did.
        from live import appendix, store

        appendix.register_tables()

        self.tables.mkdir(parents=True, exist_ok=True)
        for table in store.TABLES:
            try:
                frame = store.select(table)
            except (
                Exception
            ) as exc:  # noqa: BLE001 - a table it cannot copy is a refusal
                raise RehearsalWrite(
                    f"the rehearsal could not read {table!r} to seed its sandbox "
                    f"({type(exc).__name__}: {exc}); it will not run against the live "
                    "store instead"
                ) from exc
            if frame is None or not len(frame):
                continue
            try:
                coerce_for_parquet(frame).to_parquet(
                    self.tables / f"{table}.parquet", index=False
                )
            except Exception as exc:  # noqa: BLE001 - report which table, then refuse
                raise RehearsalWrite(
                    f"the rehearsal could not copy {table!r} into its sandbox "
                    f"({type(exc).__name__}: {exc}); refusing rather than run against "
                    "the live store"
                ) from exc
            self.seeded[table] = int(len(frame))

        for name in (store.LOCAL_MODE_ENV, store.URL_ENV, store.RENDER_ENV):
            self._saved_env[name] = os.environ.get(name)
        os.environ[store.LOCAL_MODE_ENV] = store.LOCAL_MODE_VALUE
        os.environ.pop(store.URL_ENV, None)
        os.environ.pop(store.RENDER_ENV, None)
        self._stack.enter_context(patch.object(store, "LOCAL_DIR", self.tables))
        real_select = store.select

        def _select(table: str) -> pd.DataFrame:
            return restore_dates(real_select(table))

        self._stack.enter_context(patch.object(store, "select", _select))

        if store.store_mode() != store.LOCAL_MODE_VALUE or os.environ.get(
            store.URL_ENV
        ):
            self.__exit__(None, None, None)
            raise RehearsalWrite(
                "the sandbox store could not be installed, so the rehearsal would have "
                "run against the live store; refusing"
            )
        if not self.seeded:
            self.__exit__(None, None, None)
            raise RehearsalWrite(
                "the sandbox hold no rows at all, so the evening would price an empty "
                "store; refusing"
            )
        return self

    def __exit__(self, *exc: object) -> None:
        self._stack.close()
        for name, value in self._saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


DELIVERED: list[dict[str, str]] = []


class RehearsalDelivery:
    """The message composed and kept, never sent. Restores the real sender on exit."""

    def __enter__(self) -> RehearsalDelivery:
        from live import notify

        def _capture(subject: str, message: str, **kwargs: object) -> dict[str, str]:
            DELIVERED.append({"subject": subject, "message": message})
            return {
                "status": notify.STATUS_SENT,
                "detail": "rehearsal: composed, not delivered",
            }

        self._stack = ExitStack()
        self._stack.enter_context(patch.object(notify, "send", _capture))
        return self

    def __exit__(self, *exc: object) -> None:
        self._stack.close()


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
    """Run the real evening entry point for `close`, against a sandbox store.

    Three things are installed before the evening starts, and the run refuses to begin if
    any of them is not: the store sandbox (copied tables, local mode, production DSN gone),
    the delivery capture (the message composed, nothing sent), and the pinned clock.

    `already_ran` is defeated on purpose. A close that has already been filed is exactly
    the close a rehearsal wants to re-run - it is the night whose behaviour is being
    changed - and the runner's idempotence guard would otherwise return "already ran"
    before a single line of the evening executed, which proves nothing. Defeating it is
    safe because the writes go to the sandbox: the real record cannot be disturbed by a
    rehearsal looking at the same close twice.
    """
    from live import morning_job, staleness

    fixed = pinned_now(close)
    DELIVERED.clear()
    with (
        patch.object(run_live_daily, "datetime", _FixedClock(fixed)),
        # `staleness.check()` takes no target: it reads the clock in its own module, and
        # that is where the close the message names comes from. Pinning only the runner
        # left the rehearsal pricing today's close, which is how the first attempt
        # produced an 11-05 subject for a 10-29 request.
        patch.object(staleness, "datetime", _FixedClock(fixed)),
        patch.dict(os.environ, LIVE_ENV),
        patch.object(morning_job, "connect", _rehearsal_connect),
        patch.object(run_live_daily, "already_ran", lambda *a, **k: False),
        RehearsalDelivery(),
        RehearsalSandbox(close) as sandbox,
    ):
        if (
            run_live_daily.datetime.now(UTC) != fixed
            or staleness.datetime.now(UTC) != fixed
        ):
            raise RehearsalWrite(
                "the clock is not pinned, so the rehearsal would price today's close "
                "instead of the one it was asked for; refusing"
            )
        code = run_live_daily.main()
    print(
        f"sandbox {sandbox.dir}: {len(sandbox.seeded)} table(s), "
        f"{sum(sandbox.seeded.values())} row(s) copied; nothing was written to the live store"
    )
    for message in DELIVERED:
        print(f"--- subject: {message['subject']}")
        print(message["message"])
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="rehearse the evening entry point for past closes, writes fail-closed"
    )
    parser.add_argument(
        "closes", nargs="+", help="the closes to rehearse, oldest first"
    )
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
