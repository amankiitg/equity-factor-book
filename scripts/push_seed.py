"""Push the seed to R2, and measure it, from a machine that has the artifacts.

**This is the one command that writes to the seed bucket, and it is local only.**
It refuses where `RENDER` is set, so the cron cannot push even if it were given a
write token by mistake. The `EFB_SEED_R2_*` variables hold the owner's write token
in the local `.env`, and a read-only token on Render.

What it pushes is measured, not listed. The evening job is run in a throwaway run
tree with its reads recorded, and the manifest is exactly the files that run
opened inside `data/` which the pristine tree held before the run started, hashed
from the pristine tree so the run's own writes are not mistaken for the seed.
Every future run then verifies those hashes before it does anything else, which is
what makes a new input fail loudly rather than silently being absent.

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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from live import runroot, seed  # noqa: E402


def measure(*, quiet: bool = False) -> tuple[Path, list[str], list[str]]:
    """Run the job in a throwaway tree and report the files it read.

    The job runs as the cron runs it, with `EFB_SEED_SOURCE=local` so its tree is
    a copy of the repository's artifacts, and the store is the run's own. Its
    outcome does not matter to the manifest: what matters is which files it
    opened, and a run that stops early still names the files it got to.

    Returns the seed root, the reads the pristine tree held before the run, and
    the reads the run produced itself. The second list is empty on a day that
    fetches nothing new, and on an ordinary evening it names the session the run
    just fetched, which no seed can contain.

    The tree is pinned into a temporary directory before the run starts, because
    `main` prepares a tree of its own and reports which one through `adopt`. A
    measurement that prepared one and then compared against it would be comparing
    against a tree the run never used, and the first version of this function did
    exactly that and reported **zero files**, which is why a zero is an error here
    rather than a result.
    """
    from live import staleness
    from scripts import run_live_daily

    os.environ.setdefault(runroot.SEED_SOURCE_ENV, runroot.LOCAL_SOURCE)
    os.environ[runroot.RUN_ROOT_ENV] = str(
        Path(tempfile.mkdtemp(prefix="efb-seed-measure-")) / "data"
    )
    with seed.record_reads() as opened:
        run_live_daily.main()
    # `adopt`, inside the run, is what says which tree the run actually used.
    tree = Path(staleness.DATA_ROOT)
    rels = seed.relative_reads(tree, opened)
    if not rels:
        raise seed.SeedUnavailable(
            f"the run opened no files under {tree}, so it either stopped before "
            "reading anything or did not use the tree it was given; a seed cannot "
            "be measured from that run"
        )
    seed_root = runroot.DEFAULT_SEED_ROOT
    material, produced = seed.seed_material(seed_root, tree, opened)
    if not quiet:
        print(f"run tree: {tree}")
        print(f"files the run opened under data/: {len(rels)}")
        print(f"  seed material:      {len(material)}")
        print(f"  produced by the run: {len(produced)}")
        for rel in produced:
            print(f"    {rel}")
    return seed_root, material, produced


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
    print(
        f"total_bytes: {manifest['total_bytes']} ({manifest['total_bytes'] / 1e6:.2f} MB)"
    )
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
