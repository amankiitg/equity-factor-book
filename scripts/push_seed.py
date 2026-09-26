"""Push the seed to R2, and measure it, from a machine that has the artifacts.

**This is the one command that writes to the seed bucket, and it is local only.**
It refuses where `RENDER` is set, so the cron cannot push even if it were given a
write token by mistake. The `EFB_SEED_R2_*` variables hold the owner's write token
in the local `.env`, and a read-only token on Render.

What it pushes is measured, not listed, and it is the union of every route the
loop can take rather than one pinned run: a first run that seeds the store, an
ordinary evening, an evening the gate stops, a split day, and the morning job. A
file read on only one of those routes is missing from a manifest built from
another, and that is the failure the manifest exists to prevent.

The manifest is exactly the files those runs opened inside `data/` which the
pristine tree held before they ran, hashed from the pristine tree so the runs' own
writes are not mistaken for the seed. Every future run then verifies those hashes
before it does anything else, which is what makes a new input fail loudly rather
than silently being absent.

The distinction matters on every single evening: the job fetches the new session's
SPY holdings and its prices and then reads them back, and those files are the run's
own output, not something the seed can hold. They are named in the output and left
out of the manifest. A read the pristine tree did not hold and the run did not
write is still refused.

Use:

    .venv/bin/python -m scripts.push_seed --dry-run     # measure and print only
    .venv/bin/python -m scripts.push_seed               # measure, then upload
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from live import runroot, seed, store  # noqa: E402

# The environment the measurement owns for its duration, and hands back afterwards.
# `EFB_SUPABASE_DB_URL` is in the list because the measurement forces a local store
# and `store.store_mode` refuses both being set, so a developer whose `.env` is
# sourced would fail at the first route instead of measuring anything.
_MEASURE_ENVS = (
    store.URL_ENV,
    store.LOCAL_MODE_ENV,
    store.INIT_STORE_ENV,
    runroot.SEED_SOURCE_ENV,
    runroot.RUN_ROOT_ENV,
)

PATHS = ("first_run", "normal_evening", "stopped_evening", "split_day", "morning")
# The paths that must read something under the tree, because they are the job
# itself: a zero there means the harness is wired to a tree the run never used,
# which is the mistake that once reported zero files. `split_day` and `morning`
# are steps rather than whole runs, and they may legitimately read nothing new:
# their contribution is reported and their absence from the union is a fact.
JOB_PATHS = ("first_run", "normal_evening", "stopped_evening")
PINNED_CLOSE = "2026-09-24"


def _passing_gate() -> dict[str, object]:
    """A gate result that lets the run through, for the paths that need one."""
    return {
        "job": "live_daily",
        "checked_at": "2026-09-25T02:30:00+00:00",
        "target_close": PINNED_CLOSE,
        "allowed_sessions_behind": {"prices": 0, "universe": 1},
        "inputs": {
            "prices": {
                "content": PINNED_CLOSE,
                "sessions_behind": 0,
                "allowed_sessions_behind": 0,
            }
        },
        "failures": [],
        "worst_input": "prices",
        "worst_sessions_behind": 0,
        "max_input_staleness_days": 0,
        "status": "ok",
    }


def _inject_split(tree: Path, session: pd.Timestamp) -> tuple[str, float]:
    """Put one synthetic split into a run tree, and return it with its factor.

    The shape is the one the corporate-actions tests use: the vendor's
    `split_factor` column marks the ticker on the session, and the adjusted close
    is back-adjusted by the same factor, which is the ratio the rule cross-checks.
    """
    path = tree / "raw" / "prices.parquet"
    frame = pd.read_parquet(path)
    block = frame.loc[session]
    ticker = str(block.index[0])
    factor = 2.0
    frame.loc[(session, ticker), "split_factor"] = factor
    frame.loc[(session, ticker), "adj_close"] = float(
        frame.loc[(session, ticker), "adj_close"]
    ) / factor
    frame.to_parquet(path)
    return ticker, factor


def _split_fetcher(session: pd.Timestamp, factor: float):
    """The vendor's record for the injected split, so no request is made."""

    def fetcher(name: str) -> pd.Series:
        return pd.Series([factor], index=pd.DatetimeIndex([session]), dtype=float)

    return fetcher


def measure(*, quiet: bool = False) -> tuple[Path, list[str], list[str]]:
    """Measure the union in the measurement's own environment, then restore it.

    The database URL is removed from the process for the duration: the measurement
    forces a local store, and the store refuses to be both local and pointed at
    Postgres, so a developer whose `.env` is sourced would otherwise fail at the
    first route rather than measure anything. Every variable the measurement sets is
    put back afterwards, so its environment is unchanged whatever the measurement
    does with it.
    """
    saved = {name: os.environ.get(name) for name in _MEASURE_ENVS}
    os.environ.pop(store.URL_ENV, None)
    try:
        return _measure_paths(quiet=quiet)
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _measure_paths(*, quiet: bool = False) -> tuple[Path, list[str], list[str]]:
    """Every path the loop can take, and the union of what they read.

    One pinned run is not the seed. The loop takes different routes, and a file
    read on only one of them is missing from a manifest built from another, which
    is exactly the failure the manifest exists to prevent: a path the seed does
    not hold, discovered on Render. So the five routes are all measured, in one
    throwaway store, and the seed is their union.

    The routes, and why the order matters:

    - `first_run`: an empty store with `EFB_INIT_STORE=true`, which is what the
      deploy sets for its first evening. It hydrates the appendix from the
      artifacts and writes the seed marker.
    - `normal_evening`: the same store again, now seeded, with the flag off. The
      second run sees the marker, so this is the ordinary route.
    - `stopped_evening`: the real gate, not a pinned pass, so the run stops and
      reports the last book the store holds. It reads the store's last proposal
      and stops before the build.
    - `split_day`: the corporate-actions rule with a synthetic 2:1 split injected
      into the run tree, which is the branch an ordinary evening never takes.
    - `morning`: the morning job against the tree the evening left.

    Three sandbox bounds, all of them the measurement harness's rather than the
    loop's: the per-ticker share fetch is a no-op, the target close is pinned to
    2026-09-24 because the sandbox clock is 09-25 while the vendors' latest
    session is 09-24, and `already_ran` is forced false so the routes can run one
    after another. The owner's own run on a fresh evening has none of them.
    """
    from efb import probes
    from live import corporate_actions, morning_job, staleness, store
    from scripts import run_live_daily

    # The measurement must never reach the store the developer's .env points at.
    # It runs the whole job three times, which writes run rows, so a store that is
    # not local would take them. Forced rather than defaulted, for that reason.
    os.environ[store.LOCAL_MODE_ENV] = "local"
    original_check = staleness.check
    os.environ.setdefault(runroot.SEED_SOURCE_ENV, runroot.LOCAL_SOURCE)
    os.environ[store.INIT_STORE_ENV] = "true"
    os.environ[runroot.RUN_ROOT_ENV] = str(
        Path(tempfile.mkdtemp(prefix="efb-seed-paths-")) / "data"
    )
    store.LOCAL_DIR = Path(tempfile.mkdtemp(prefix="efb-seed-paths-")) / "state"
    probes.fetch_share_history = lambda *a, **k: pd.DataFrame()
    staleness.target_close = lambda now=None: pd.Timestamp(PINNED_CLOSE)
    run_live_daily.already_ran = lambda *a, **k: False

    reads: dict[str, set[str]] = {}
    writes: dict[str, set[str]] = {}

    def capture(name: str, call: Callable[[], Any]) -> None:
        with seed.record_reads() as opened:
            call()
        reads[name] = set(opened)
        writes[name] = set(opened.writes)

    staleness.check = lambda *a, **k: _passing_gate()
    capture("first_run", run_live_daily.main)
    os.environ[store.INIT_STORE_ENV] = "false"
    capture("normal_evening", run_live_daily.main)
    staleness.check = original_check
    capture("stopped_evening", run_live_daily.main)

    tree = Path(staleness.DATA_ROOT)
    session = pd.Timestamp("2026-09-24")
    ticker, factor = _inject_split(tree, session)
    capture(
        "split_day",
        lambda: corporate_actions.apply_to_artifact(
            tree,
            since=session - pd.Timedelta(days=5),
            split_fetcher=_split_fetcher(session, factor),
        ),
    )
    capture(
        "morning",
        lambda: morning_job.run_morning(
            session.strftime("%Y-%m-%d"), dry_run=True, data_root=tree
        ),
    )

    seed_root = runroot.DEFAULT_SEED_ROOT
    material: list[str] = []
    produced: set[str] = set()
    for name in PATHS:
        rels = seed.relative_reads(tree, reads[name])
        if not rels and name in JOB_PATHS:
            raise seed.SeedUnavailable(
                f"the {name} path opened no files under {tree}, so it either stopped "
                "before reading anything or did not use the tree it was given; a seed "
                "cannot be measured from that path"
            )
        path_material, path_produced = seed.seed_material(
            seed_root, tree, _with_writes(reads[name], writes[name])
        )
        material.extend(path_material)
        produced.update(path_produced)
        if not quiet:
            print(f"  {name:15} {len(path_material):4} seed file(s)")
            for rel in path_material:
                print(f"      {rel}")
    union = sorted(set(material))
    return seed_root, union, sorted(produced)


def _with_writes(reads: set[str], writes: set[str]) -> seed.Reads:
    """A `Reads` for one path, so `seed_material` can tell its own writes apart."""
    merged = seed.Reads()
    merged.update(reads)
    merged.writes.update(writes)
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="measure and print the manifest without uploading anything",
    )
    parser.add_argument(
        "--seed-root",
        default=str(runroot.DEFAULT_SEED_ROOT),
        help="the tree the files are hashed from and pushed from",
    )
    args = parser.parse_args(argv)
    if os.environ.get("RENDER", "").strip():
        print("ERROR this command pushes the seed and never runs on Render")
        return 2

    seed_root = Path(args.seed_root)
    seed_root, material, produced = measure()
    manifest = seed.manifest_for(seed_root, material)
    print(f"seed root: {seed_root}")
    print(f"n_files: {manifest['n_files']}")
    megabytes = manifest["total_bytes"] / 1e6
    print(f"total_bytes: {manifest['total_bytes']} ({megabytes:.2f} MB)")
    print(f"data_hash: {manifest['data_hash']}")
    for entry in manifest["files"]:
        print(f"  {entry['path']:<58} {entry['bytes']:>12}  {entry['sha256'][:12]}")
    if produced:
        print(
            f"{len(produced)} file(s) the run produced and read back are the run's "
            "own output, so they are not pushed:"
        )
        for rel in produced:
            print(f"  {rel}")
    if args.dry_run:
        print("dry run: nothing uploaded")
        return 0

    written = seed.upload(seed_root, manifest)
    print(
        f"uploaded {len(written)} objects to {seed.seed_settings()[seed.SEED_ENVS[1]]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
