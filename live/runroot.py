"""The run's own copy of the artifact tree.

Render's disk is the deploy image, and the repository's `data/` holds history the
loop must not rewrite. That is measured, not theoretical: a local measurement run
rewrote four raw artifacts and narrowed the SPY archive from nine columns to six,
and `make verify-evidence` was the only thing that caught it. So a run
materializes its own tree, every live module's default resolves to that tree for
the length of the run, and nothing under `data/` is written at all.

`prepare` builds the tree and `adopt` points the modules at it. A module's
`data_root` argument defaults to `None`, which means "the module's own
`DATA_ROOT`", and that global is read at call time rather than bound at import,
which is what lets `adopt` redirect a run that is already in progress.

Where the tree comes from is a separate question, and it is answered by the seed
bucket: on Render there is nothing under `data/` (every parquet is gitignored), so
the tree is downloaded and verified by `live/seed.py`. On a machine that has the
artifacts, it is copied. `EFB_SEED_ROOT` and `EFB_RUN_ROOT` pin the two ends, so a
measurement works in a fixed directory instead of a fresh temporary one.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED_ROOT_ENV = "EFB_SEED_ROOT"
RUN_ROOT_ENV = "EFB_RUN_ROOT"
SEED_SOURCE_ENV = "EFB_SEED_SOURCE"
LOCAL_SOURCE = "local"
BUCKET_SOURCE = "r2"
DEFAULT_SEED_ROOT = ROOT / "data"

# Two files whose absence means the tree is not a tree: the price panel and the
# descriptor artifact. Without them nothing downstream can run, so a seed that
# lacks them is refused here rather than three steps later.
REQUIRED = ("raw/prices.parquet", "models/XS-v1/descriptors.parquet")


class RunRootUnavailable(RuntimeError):
    """No tree can be supplied for this run, so it must not start."""


def seed_root() -> Path:
    """Where the artifacts to copy come from, from the environment or the repo."""
    value = os.environ.get(SEED_ROOT_ENV, "").strip()
    return Path(value) if value else DEFAULT_SEED_ROOT


def pinned_root() -> Path | None:
    """The run tree when one is named explicitly, else None for a temporary one."""
    value = os.environ.get(RUN_ROOT_ENV, "").strip()
    return Path(value) if value else None


def destination(dest: Path | None = None) -> tuple[Path, bool]:
    """The tree to build into, and whether this call owns it.

    A pinned tree is not owned: the caller asked for it and may look inside it
    afterwards, which is what the seed command and the measurement do. A
    temporary one is owned, because nothing else knows its name.
    """
    target = Path(dest) if dest is not None else pinned_root()
    if target is not None:
        return target, False
    return Path(tempfile.mkdtemp(prefix="efb-run-")) / "data", True


def prepare(*, seed: Path | None = None, dest: Path | None = None) -> Path:
    """Materialize the run's tree and return it.

    The tree starts as the seed: downloaded and verified from the bucket, or a
    copy of the local tree when `EFB_SEED_SOURCE=local` says so. It is then the
    only place the run reads or writes under `data/`, so a run that appends a
    session, refits a model or rehashes `VERSION.json` leaves the repository's
    artifact tree untouched. The copy is 876 MB on this checkout and takes 2.4
    seconds; the two big caches that only the E4 and E2 rebuild paths read are
    left behind.
    """
    target, _owned = destination(dest)
    if seed_source() == LOCAL_SOURCE:
        source = Path(seed) if seed is not None else seed_root()
        if not source.exists():
            raise RunRootUnavailable(
                f"the seed root {source} does not exist, so the run has no "
                "artifacts to start from; set EFB_SEED_ROOT, or use the bucket"
            )
        copy_tree(source, target)
    else:
        from live import seed as seed_module

        seed_module.install(target)
    missing = [rel for rel in REQUIRED if not (target / rel).exists()]
    if missing:
        raise RunRootUnavailable(
            f"the run tree holds no {', '.join(missing)}, so a run cannot start "
            "from it; on Render the seed comes from the bucket, never from the "
            "deploy image"
        )
    return target


def seed_source() -> str:
    """`local` or `r2`, decided rather than guessed.

    The bucket is the deploy's source and the default when its variables are set.
    A local tree is the developer's, and it is refused where `RENDER` is set,
    because the deploy image holds no artifacts: a run that quietly copied an
    empty tree there would fail later with a missing file instead of here with
    the reason.
    """
    value = os.environ.get(SEED_SOURCE_ENV, "").strip().lower()
    if value not in ("", LOCAL_SOURCE):
        raise RunRootUnavailable(
            f"{SEED_SOURCE_ENV}={value!r} is not a seed source: set it to "
            f"{LOCAL_SOURCE!r}, or leave it unset to use the bucket"
        )
    if value == LOCAL_SOURCE:
        if os.environ.get("RENDER", "").strip():
            raise RunRootUnavailable(
                f"{SEED_SOURCE_ENV}=local is refused where RENDER is set: the "
                "deploy image holds no artifacts, so the seed has to come from "
                "the bucket"
            )
        return LOCAL_SOURCE
    from live import seed as seed_module

    if seed_module.configured():
        return BUCKET_SOURCE
    raise RunRootUnavailable(
        "no seed source: set "
        f"{seed_module.SEED_ENVS[0]}, {seed_module.SEED_ENVS[2]} and "
        f"{seed_module.SEED_ENVS[3]} for the bucket, or set "
        f"{SEED_SOURCE_ENV}={LOCAL_SOURCE} on a machine that has the artifacts"
    )


def copy_tree(source: Path, target: Path) -> None:
    """Copy the seed into the run tree, leaving the two big caches behind.

    `raw/e4_raw_descriptors.parquet` (228 MB) and `raw/yf_cache.parquet` (58 MB)
    are read by `efb.probes`' E4 and E2 rebuild paths, not by the evening loop,
    whose only share-cache read goes through `efb.probes::SHARES_CACHE` and is
    passed explicitly by `live.extend::extend_shares`.
    """
    shutil.copytree(
        source,
        target,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("e4_raw_descriptors.parquet", "yf_cache.parquet"),
    )


def adopt(root: Path) -> None:
    """Point every live module's tree at the run's own tree.

    Called once, after `prepare`. The modules read their own globals at call time
    rather than through default arguments bound at import, which is why this is
    enough and why no call site has to change. The proposal directory moves with
    the tree, so a run does not add a proposal file to the repository either.
    """
    from live import (
        appendix,
        evening_job,
        extend,
        morning_job,
        reconcile,
        sanity,
        staleness,
    )

    # Assigned one by one rather than in a loop: a loop over a union of module
    # types cannot be type-checked, and seven explicit lines say exactly which
    # modules read the tree.
    appendix.DATA_ROOT = root
    evening_job.DATA_ROOT = root
    extend.DATA_ROOT = root
    morning_job.DATA_ROOT = root
    reconcile.DATA_ROOT = root
    sanity.DATA_ROOT = root
    staleness.DATA_ROOT = root
    proposals = Path(root).parent / "proposals"
    evening_job.PROPOSAL_DIR = proposals
    morning_job.PROPOSAL_DIR = proposals
    reconcile.PROPOSAL_DIR = proposals
    # sanity reads evening_job's, so it follows this one.
