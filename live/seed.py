"""The seed: the artifact files a run cannot compute, kept in R2 and verified.

Render's deploy image has no model inputs at all. Every parquet under `data/` is
gitignored, `render.yaml`'s build is two pip installs, and the only tracked
artifact data is the evidence snapshot, which covers the fetched raw files and
nothing derived. So `data/raw/prices.parquet` does not exist on a fresh container
and the first run's seed read fails. The owner's answer is a private R2 bucket,
`efb-seed`, separate from the snapshot bucket: the frozen history is pushed there
once from the machine that has the artifacts, and every run downloads it with a
read-only token and verifies it before anything else happens.

**The manifest is a measurement, not a list.** `record_reads` watches the calls
the loop reads through and records every path it opens inside the tree, and the
manifest is what a real run came out with, one SHA-256 per file. That is why a
new input cannot be added silently: a run that reads a file the seed does not
hold fails the hash check rather than starting from a tree nobody has described.

**The run never writes to the bucket.** `upload` exists for the local command
only, and it refuses where `RENDER` is set, so "no write path into history" is
structural rather than a promise.

What "through" means for the recording is stated rather than implied: pandas'
readers are wrapped, and Python's `open` is wrapped for its reading modes.
pyarrow's own C++ file opens do not raise Python-level events, which is exactly
why `read_parquet` itself is wrapped rather than relying on `open`.

**A run reads what it just produced, and that is not seed material.** The evening
job fetches the session's SPY holdings and its prices and then reads them back, so
a read the pristine root does not hold is not automatically a gap in the seed.
pyarrow's writers raise no Python-level events either, so `to_parquet` is wrapped
as well and the paths a run creates are known: a missing read the run wrote is its
own output, reported as such and left out of the manifest, while a missing read it
did not write is still refused. A write through a path this does not wrap fails in
that loud direction rather than being quietly accepted.
"""

from __future__ import annotations

import builtins
import hashlib
import io
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

MANIFEST_KEY = "seed_manifest.json"
MANIFEST_VERSION = 1
DEFAULT_BUCKET = "efb-seed"
SEED_ENVS = (
    "EFB_SEED_R2_ACCOUNT_ID",
    "EFB_SEED_R2_BUCKET",
    "EFB_SEED_R2_ACCESS_KEY_ID",
    "EFB_SEED_R2_SECRET_ACCESS_KEY",
)
SEED_REGION = "auto"
SEED_ENDPOINT_TEMPLATE = "https://{account}.r2.cloudflarestorage.com"
CHUNK = 1 << 20


class SeedNotConfigured(RuntimeError):
    """The seed bucket is not usable as configured."""


class SeedMismatch(RuntimeError):
    """A downloaded file, or the tree's version file, is not what the manifest says."""


class SeedUnavailable(RuntimeError):
    """The seed cannot be supplied at all, so the run must not start."""


def configured() -> bool:
    """Whether the seed can be reached, without raising when it cannot.

    The same rule `seed_settings` applies, so the two can never disagree about
    whether a bucket is configured: the bucket name itself has a default.
    """
    try:
        seed_settings()
    except SeedNotConfigured:
        return False
    return True


def seed_settings() -> dict[str, str]:
    """The seed variables, or an error naming the missing ones.

    The bucket defaults to `efb-seed`, because it is a name the owner chose and
    not a secret. The other three are required: an account id, and the token
    that is read-only on Render and write-capable in the local `.env`.
    """
    required = (SEED_ENVS[0], SEED_ENVS[2], SEED_ENVS[3])
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        raise SeedNotConfigured(
            f"the seed bucket needs {', '.join(missing)} and "
            f"{'it is' if len(missing) == 1 else 'they are'} not set"
        )
    return {
        SEED_ENVS[0]: os.environ[SEED_ENVS[0]].strip(),
        SEED_ENVS[1]: os.environ.get(SEED_ENVS[1], "").strip() or DEFAULT_BUCKET,
        SEED_ENVS[2]: os.environ[SEED_ENVS[2]].strip(),
        SEED_ENVS[3]: os.environ[SEED_ENVS[3]].strip(),
    }


def seed_endpoint(settings: dict[str, str] | None = None) -> str:
    """The account's S3-compatible endpoint."""
    values = settings or seed_settings()
    return SEED_ENDPOINT_TEMPLATE.format(account=values[SEED_ENVS[0]])


def seed_client(settings: dict[str, str] | None = None) -> Any:
    """A boto3 client for the seed bucket, with the token this machine has.

    On Render that is a read-only token scoped to the bucket, so the same code
    cannot push anything even if it tried. Locally the owner's write token is in
    the same variables; `upload` is the only caller that puts an object.
    """
    values = settings or seed_settings()
    import boto3  # noqa: PLC0415 - only a seed transfer needs the client

    return boto3.client(
        "s3",
        endpoint_url=seed_endpoint(values),
        region_name=SEED_REGION,
        aws_access_key_id=values[SEED_ENVS[2]],
        aws_secret_access_key=values[SEED_ENVS[3]],
    )


def sha256_file(path: Path) -> str:
    """The file's SHA-256, read in chunks so a 58 MB parquet does not sit in RAM."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


class Reads(set[str]):
    """The paths a run opened, and which of them it created.

    A `set` subclass, so a caller that only wants the reads still has a set;
    `writes` is the second fact that separates a read of a file the run produced
    this session from a read of an input the seed has to hold.
    """

    def __init__(self) -> None:
        super().__init__()
        self.writes: set[str] = set()


class SeedReadNotAllowed(SeedMismatch):
    """The run opened a file under its tree that the seed did not supply."""


def _relative_under(path: Any, tree: Path) -> str | None:
    """The path relative to the tree, or None when it is not under it at all."""
    candidate = Path(str(path))
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    try:
        return candidate.resolve().relative_to(Path(tree).resolve()).as_posix()
    except ValueError:
        return None


def _was_written(path: Any, opened: Reads) -> bool:
    """Whether this run created the file itself earlier in the same run."""
    candidate = Path(str(path))
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    resolved = str(candidate.resolve())
    return any(str(Path(item).resolve()) == resolved for item in opened.writes)


def _watch(
    tree: Path | None = None, allowed: set[str] | None = None
) -> tuple[Reads, Callable[[], None]]:
    """Install the readers and writers, and return what they record and how to stop.

    One installer for both callers: the measurement records without enforcing, and
    the run enforces the allowlist as it records.
    """
    opened = Reads()
    armed = True
    original_parquet = pd.read_parquet
    original_to_parquet = pd.DataFrame.to_parquet
    original_open = builtins.open
    original_io_open = io.open

    def _before(path: Any) -> None:
        """Refuse a read of the tree that the seed did not supply.

        The allowlist is the tree as it stood when the run started, which is what
        the seed supplied. A read outside it is a file the loop needs and the seed
        does not hold, so the run stops here and names it rather than reaching
        Render and dying on a missing file the message cannot explain.

        The check disarms itself as it raises: the run's failure handling still has
        to read the store and the tree to send the mail, and a second refusal there
        would lose the message entirely.
        """
        nonlocal armed
        if not armed or tree is None or allowed is None:
            return
        rel = _relative_under(path, tree)
        if rel is None or rel in allowed or _was_written(path, opened):
            return
        armed = False
        raise SeedReadNotAllowed(
            f"{rel} is not a file the seed holds, so the run stops before reading "
            "it; the seed manifest is what the run may read under data/"
        )

    def _parquet(path: Any, *args: Any, **kwargs: Any) -> Any:
        _before(path)
        opened.add(str(path))
        return original_parquet(path, *args, **kwargs)

    def _to_parquet(self: Any, path: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(path, (str, os.PathLike)):
            opened.writes.add(str(path))
        return original_to_parquet(self, path, *args, **kwargs)

    def _open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if not any(flag in str(mode) for flag in "wax+"):
            _before(file)
            opened.add(str(file))
        return original_open(file, mode, *args, **kwargs)

    def _io_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if not any(flag in str(mode) for flag in "wax+"):
            _before(file)
            opened.add(str(file))
        return original_io_open(file, mode, *args, **kwargs)

    pd.read_parquet = _parquet  # type: ignore[assignment]
    # pyarrow writes without a Python-level `open`, so the one write path that
    # would otherwise be invisible is wrapped by name.
    pd.DataFrame.to_parquet = _to_parquet  # type: ignore[method-assign]
    builtins.open = _open  # type: ignore[assignment]
    # `pathlib.Path.read_text` and `Path.open` call `io.open` rather than
    # `builtins.open`, so both names have to be wrapped to see a text read.
    io.open = _io_open  # type: ignore[assignment]

    def uninstall() -> None:
        pd.read_parquet = original_parquet  # type: ignore[assignment]
        pd.DataFrame.to_parquet = original_to_parquet  # type: ignore[method-assign]
        builtins.open = original_open  # type: ignore[assignment]
        io.open = original_io_open  # type: ignore[assignment]

    return opened, uninstall


@contextmanager
def record_reads() -> Iterator[Reads]:
    """Record every path the wrapped readers open while the block runs.

    The set holds whatever was passed in, which for the layer under test is a
    `Path`; callers make it relative to their tree. A write goes into `writes` and
    not into the reads: a path the run both wrote and read is its own output, and
    keeping the two apart is what `seed_material` does.
    """
    opened, uninstall = _watch()
    try:
        yield opened
    finally:
        uninstall()


def enforce_reads(tree: Path, allowed: set[str]) -> Reads:
    """Install the allowlist for the rest of the process, and record as it goes.

    Not a context manager on purpose: the run's own failure handling has to keep
    reading after a refusal, so the refusal disarms the check itself rather than
    the caller unwinding a `with` block. The watchers stay installed for the
    process's life, which for the cron is the whole run.
    """
    opened, _uninstall = _watch(Path(tree), allowed)
    return opened


def guard(tree: Path) -> int:
    """Allow the run to read the tree as the seed left it, and nothing else.

    The allowlist is the tree as it stood when the run adopted it, which is what
    the seed supplied: the bucket's manifest files on the deploy path, the copied
    files on the local one. Called once, before the first read, and returns how
    many paths it allows so the run can log what it is holding itself to.
    """
    root = Path(tree)
    allowed = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    enforce_reads(root, allowed)
    return len(allowed)


def relative_reads(tree: Path, opened: set[str]) -> list[str]:
    """The recorded reads that live inside the tree, as sorted relative paths.

    Anything outside the tree is dropped: the run reads its own code, the store
    and the notification module, and none of that is seed material.
    """
    root = Path(tree).resolve()
    found: set[str] = set()
    for item in opened:
        candidate = Path(item)
        try:
            found.add(candidate.resolve().relative_to(root).as_posix())
        except ValueError:
            continue
    return sorted(found)


def seed_material(
    seed_root: Path, tree: Path, opened: Reads
) -> tuple[list[str], list[str]]:
    """The reads that are seed material, and the reads that are the run's own work.

    The two are told apart by the tree, not by a list. A read the pristine root
    holds is an input the seed supplies. A read it does not hold is acceptable
    only when the run created that file itself in the same run, because the
    evening job fetches the session's SPY holdings and prices before reading them
    back, and those are outputs rather than inputs. Anything else the root does
    not hold is a gap in the seed, and the run that measured it refuses here
    rather than pushing a manifest no later run could start from.
    """
    root = Path(seed_root)
    inside = Path(tree).resolve()
    written = {str(Path(path).resolve()) for path in opened.writes}
    material: list[str] = []
    produced: list[str] = []
    for rel in relative_reads(tree, opened):
        if (root / rel).exists():
            material.append(rel)
        elif str(inside / rel) in written:
            produced.append(rel)
        else:
            raise SeedUnavailable(
                f"the run read {rel}, which the seed root {root} does not hold and "
                "the run did not write either, so the seed cannot be described"
            )
    return material, produced


def manifest_for(seed_root: Path, rels: list[str]) -> dict[str, Any]:
    """A manifest of the seed's own bytes for the files a run read.

    Hashed from the pristine seed root rather than from the run tree: the run
    rewrites the files it reads, so the tree's copies are not the seed.
    """
    root = Path(seed_root)
    files = []
    total = 0
    for rel in rels:
        path = root / rel
        if not path.exists():
            raise SeedUnavailable(
                f"the run read {rel}, which the seed root {root} does not hold; the "
                "seed cannot be described"
            )
        size = path.stat().st_size
        total += size
        files.append({"path": rel, "bytes": size, "sha256": sha256_file(path)})
    version = root / "VERSION.json"
    return {
        "manifest_version": MANIFEST_VERSION,
        "written_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "bucket": DEFAULT_BUCKET,
        "n_files": len(files),
        "total_bytes": total,
        "data_hash": (
            json.loads(version.read_text()).get("data_hash")
            if version.exists()
            else None
        ),
        "files": files,
    }


def manifest_text(manifest: dict[str, Any]) -> str:
    """The manifest as text, sorted, so a re-run that changes nothing matches."""
    return json.dumps(manifest, indent=1, sort_keys=True) + "\n"


def upload(
    seed_root: Path,
    manifest: dict[str, Any],
    *,
    client: Any = None,
    settings: dict[str, str] | None = None,
) -> list[str]:
    """Push every manifest file and the manifest itself. Local command only."""
    values = settings or seed_settings()
    s3 = client or seed_client(values)
    bucket = values[SEED_ENVS[1]]
    written: list[str] = []
    for entry in manifest["files"]:
        path = Path(seed_root) / entry["path"]
        body = path.read_bytes()
        s3.put_object(
            Bucket=bucket,
            Key=entry["path"],
            Body=body,
            ContentType="application/octet-stream",
            ChecksumSHA256=checksum_sha256(body),
        )
        written.append(entry["path"])
    s3.put_object(
        Bucket=bucket,
        Key=MANIFEST_KEY,
        Body=manifest_text(manifest).encode(),
        ContentType="application/json",
    )
    written.append(MANIFEST_KEY)
    return written


def checksum_sha256(body: bytes) -> str:
    """The base64 SHA-256 R2 verifies a body against, so a truncated push is refused."""
    import base64

    return base64.b64encode(hashlib.sha256(body).digest()).decode()


def fetch_manifest(
    *, client: Any = None, settings: dict[str, str] | None = None
) -> dict[str, Any]:
    """The bucket's manifest, or an error naming what is missing."""
    values = settings or seed_settings()
    s3 = client or seed_client(values)
    bucket = values[SEED_ENVS[1]]
    try:
        payload = s3.get_object(Bucket=bucket, Key=MANIFEST_KEY)
    except Exception as exc:  # noqa: BLE001 - reported as a seed failure
        raise SeedUnavailable(
            f"the seed bucket {bucket} holds no {MANIFEST_KEY}: {type(exc).__name__}"
        ) from exc
    body = payload["Body"].read()
    parsed = json.loads(body)
    if not isinstance(parsed, dict) or "files" not in parsed:
        raise SeedUnavailable(f"{MANIFEST_KEY} in {bucket} is not a seed manifest")
    return parsed


def download(
    tree: Path,
    *,
    manifest: dict[str, Any] | None = None,
    client: Any = None,
    settings: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Write every manifest file into the tree, then verify all of them."""
    values = settings or seed_settings()
    s3 = client or seed_client(values)
    described = manifest if manifest is not None else fetch_manifest(client=s3)
    bucket = values[SEED_ENVS[1]]
    for entry in described["files"]:
        target = Path(tree) / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = s3.get_object(Bucket=bucket, Key=entry["path"])
        body = payload["Body"].read()
        if hashlib.sha256(body).hexdigest() != entry["sha256"]:
            raise SeedMismatch(
                f"{entry['path']} came back with the wrong hash, so the download is "
                "not the seed that was pushed"
            )
        target.write_bytes(body)
    verify(tree, described)
    return described


def verify(tree: Path, manifest: dict[str, Any]) -> None:
    """Refuse the run unless every seed file, and the version file, match.

    The version file is checked against the manifest's `data_hash`, which is what
    ties the seed to the artifacts E1 to E10 were scored on: a tree whose
    VERSION.json says something else is a different dataset, and a run on it
    would produce numbers nobody can place.
    """
    root = Path(tree)
    problems: list[str] = []
    for entry in manifest["files"]:
        path = root / entry["path"]
        if not path.exists():
            problems.append(f"{entry['path']} is missing")
            continue
        if path.stat().st_size != entry["bytes"]:
            problems.append(
                f"{entry['path']} is {path.stat().st_size} bytes, not {entry['bytes']}"
            )
            continue
        if sha256_file(path) != entry["sha256"]:
            problems.append(f"{entry['path']} does not match its hash")
    expected_hash = manifest.get("data_hash")
    version = root / "VERSION.json"
    if expected_hash:
        if not version.exists():
            problems.append(
                "VERSION.json is missing, so the seed's data hash is unknown"
            )
        else:
            actual = json.loads(version.read_text()).get("data_hash")
            if actual != expected_hash:
                problems.append(
                    f"VERSION.json records {actual}, but the seed was pushed from "
                    f"{expected_hash}"
                )
    if problems:
        raise SeedMismatch(
            "the seed does not match its manifest, so the run refuses to start: "
            + "; ".join(problems[:8])
        )


def install(tree: Path, *, client: Any = None) -> dict[str, Any]:
    """Put the seed into the tree and verify it, which is a run's first step."""
    return download(tree, client=client)
