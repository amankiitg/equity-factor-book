"""Evidence snapshots: the fix for the class of failure E5 Task 0a demonstrated.

`data/**/*.parquet` is gitignored, so every artifact this project computes is
one run away from being unrecoverable, and E5 destroyed one: the E4 covariance
race carried the XS-v1 row that F4.3 was scored on, was rebuilt from a
derivation, and could not be restored because nothing tracked it. A content
hash in `data/VERSION.json` detects that a file changed; it cannot bring it
back.

This module writes a tracked, compressed snapshot of the artifacts a stored
criterion was scored on:

    evidence/<path>.gz            the compressed artifact
    evidence/MANIFEST.json        sha256 and size of the artifact and of its
                                  snapshot, plus the hash VERSION.json records

`verify` is the check that matters: it decompresses each snapshot, hashes it,
and compares against both the manifest and the manifest's record of what
`VERSION.json` says the artifact was. A snapshot that has drifted fails.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
MANIFEST = EVIDENCE / "MANIFEST.json"

# Every artifact scored on, from the sprint results files and the manifests
# they read. `data/processed` and `data/raw` are inputs rather than evidence
# and are excluded: they are large, and they are rebuildable from source.
EVIDENCE_GLOBS = (
    # E8 Task 0d: only the fetched inputs that make rebuild cannot
    # regenerate. Everything derived (eval, hedge, alpha, models,
    # processed) is rebuilt deterministically by make rebuild and is no
    # longer snapshotted; the previous per-sprint snapshots were dropped
    # from the tree in the same task. The raw parquet files are tracked
    # through Git LFS, recorded with its cost in docs/open_items.md.
    "data/raw/*.parquet",
    # the SPY holdings archive is the one fetched input whose whole value
    # is that it cannot be regenerated: SSGA serves only the current file,
    # so a dated file that is not snapshotted today is unrecoverable.
    "data/raw/spy_holdings/*.parquet",
    # the live Wikipedia constituents table changes daily and is archived
    # nowhere, so the same reasoning applies to its dated files.
    "data/raw/wikipedia_constituents/*.parquet",
)
EVIDENCE_FILES = ("data/models/registry.json", "data/VERSION.json")

# A snapshot is for the record, not for distribution. Anything above this is
# listed as skipped rather than committed, and the cost is reported. The cap
# sits above every fetched input except the E4 descriptor probe cache, which
# rebuild regenerates from the prices and factors that are themselves
# snapshotted.
MAX_BYTES = 64 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidates(data_root: Path = ROOT / "data") -> list[Path]:
    """Every evidence candidate, in a stable order."""
    root = data_root.parent if data_root.name == "data" else data_root
    found: list[Path] = []
    for pattern in EVIDENCE_GLOBS:
        found.extend(sorted(root.glob(pattern)))
    for rel in EVIDENCE_FILES:
        path = root / rel
        if path.exists():
            found.append(path)
    return [path for path in found if path.is_file()]


def recorded_hashes(data_root: Path = ROOT / "data") -> dict[str, str]:
    """What `VERSION.json` says each artifact's content hash is."""
    version = data_root / "VERSION.json"
    if not version.exists():
        return {}
    payload = json.loads(version.read_text())
    return {
        name: str(entry.get("sha256", ""))
        for name, entry in payload.get("artifacts", {}).items()
    }


def snapshot(
    data_root: Path = ROOT / "data",
    evidence_dir: Path = EVIDENCE,
    max_bytes: int = MAX_BYTES,
) -> dict[str, object]:
    """Write or refresh the evidence snapshot and return its manifest."""
    root = ROOT
    evidence_dir.mkdir(parents=True, exist_ok=True)
    recorded = recorded_hashes(data_root)
    entries: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for path in candidates(data_root):
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        if size > max_bytes:
            skipped.append({"path": rel, "bytes": size, "reason": "over the size cap"})
            continue
        target = evidence_dir / f"{rel}.gz"
        target.parent.mkdir(parents=True, exist_ok=True)
        with path.open("rb") as source, gzip.open(target, "wb", compresslevel=9) as out:
            shutil.copyfileobj(source, out)
        entries.append(
            {
                "path": rel,
                "sha256": sha256_file(path),
                "bytes": size,
                "snapshot": target.relative_to(root).as_posix(),
                "snapshot_sha256": sha256_file(target),
                "snapshot_bytes": target.stat().st_size,
                "version_json_sha256": recorded.get(Path(rel).name, ""),
            }
        )
    manifest = {
        "note": (
            "Tracked, compressed snapshots of the artifacts a stored criterion "
            "was scored on. Written by efb.evidence and verified by make "
            "verify-evidence against both this manifest and data/VERSION.json."
        ),
        "n_artifacts": len(entries),
        "total_bytes": int(sum(entry["bytes"] for entry in entries)),
        "total_snapshot_bytes": int(sum(entry["snapshot_bytes"] for entry in entries)),
        "skipped": skipped,
        "artifacts": entries,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def verify(data_root: Path = ROOT / "data", evidence_dir: Path = EVIDENCE) -> list[str]:
    """Every problem found comparing the snapshots with their hashes."""
    problems: list[str] = []
    if not MANIFEST.exists():
        return ["no evidence manifest: run make evidence"]
    manifest = json.loads(MANIFEST.read_text())
    recorded = recorded_hashes(data_root)
    for entry in manifest["artifacts"]:
        rel = str(entry["path"])
        target = ROOT / str(entry["snapshot"])
        if not target.exists():
            problems.append(f"{rel}: snapshot missing")
            continue
        with gzip.open(target, "rb") as handle:
            content = handle.read()
        digest = hashlib.sha256(content).hexdigest()
        if digest != entry["sha256"]:
            problems.append(f"{rel}: snapshot does not reproduce the hashed content")
        live = ROOT / rel
        if live.exists() and sha256_file(live) != entry["sha256"]:
            problems.append(f"{rel}: the artifact on disk has moved since the snapshot")
        recorded_hash = recorded.get(Path(rel).name, "")
        if recorded_hash and entry["version_json_sha256"] != recorded_hash:
            problems.append(f"{rel}: VERSION.json records a different hash now")
    return problems
