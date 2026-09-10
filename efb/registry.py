"""Model registry (Sprint E2, Task 6).

data/models/registry.json is pre-registered with the champion rule and
family notes (written before any estimator existed) and then gains one
entry per model version. TS-v1 is family timeseries, diagnostic only and
ineligible for champion.

Schema per entry: version, family, parameters, universe_hash, data_hash,
built_at, champion, eligible_for_champion, walkthrough, deliverable,
results.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_CHAMPION_RULE = (
    "min mean |bias-1| across portfolio families; ties to fewer parameters; "
    "a champion must be refreshable daily from EFB's own data"
)
DEFAULT_FAMILY_NOTES = (
    "timeseries models on external factors are diagnostic only and ineligible "
    "for champion"
)


def file_hash(path: Path) -> str:
    """SHA-256 content hash of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_entry(
    version: str,
    family: str,
    parameters: dict[str, Any],
    universe_path: Path,
    data_paths: list[Path],
    walkthrough: str,
    deliverable: str,
    results: str,
    champion: bool = False,
    eligible_for_champion: bool = False,
) -> dict[str, Any]:
    """Build one registry entry with content hashes of its inputs."""
    return {
        "version": version,
        "family": family,
        "parameters": parameters,
        "universe_hash": file_hash(universe_path),
        "data_hash": (
            file_hash(data_paths[0])
            if len(data_paths) == 1
            else _combined_hash(data_paths)
        ),
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "champion": champion,
        "eligible_for_champion": eligible_for_champion,
        "walkthrough": walkthrough,
        "deliverable": deliverable,
        "results": results,
    }


def _combined_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(file_hash(path).encode())
    return digest.hexdigest()


def write_registry(path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    """Upsert one model entry, preserving the pre-registered rule and notes."""
    if path.exists():
        payload = json.loads(path.read_text())
    else:
        payload = {}
    payload.setdefault("note", "Model registry for the EFB.")
    payload.setdefault("champion_rule", DEFAULT_CHAMPION_RULE)
    payload.setdefault("family_notes", DEFAULT_FAMILY_NOTES)
    models = payload.setdefault("models", {})
    models[entry["version"]] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload
