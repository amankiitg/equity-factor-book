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


def declare_champion(path: Path, version: str) -> dict[str, Any]:
    """Set `champion: true` on exactly one entry and clear every other flag.

    The champion rule and the family notes are carried, never edited. The
    declared version must already be registered and eligible, which is how an
    ineligible diagnostic version can never become champion through this door.
    """
    payload = load(path)
    models = payload.setdefault("models", {})
    if version not in models:
        raise ValueError(f"{version} is not registered")
    if not models[version].get("eligible_for_champion"):
        raise ValueError(f"{version} is ineligible for champion")
    for name, entry in models.items():
        entry["champion"] = name == version
    Path(path).write_text(json.dumps(payload, indent=2) + "\n")
    return payload


# Registry v1 (Sprint E4, Task 5). The schema is validated rather than assumed,
# and the champion flag is read through one function so no tab or report can
# invent its own answer. The champion rule itself is never edited here.

SCHEMA_VERSION = 1

REQUIRED_KEYS = (
    "version",
    "family",
    "parameters",
    "universe_hash",
    "data_hash",
    "built_at",
    "champion",
    "eligible_for_champion",
)

FAMILIES = ("timeseries", "fundamental", "statistical", "blend")


def load(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def versions(payload: dict[str, Any]) -> list[str]:
    """Every registered version, in registration order."""
    return list(payload.get("models", {}))


def validate(payload: dict[str, Any]) -> list[str]:
    """Schema check. Returns the problems; an empty list means the registry is valid."""
    problems: list[str] = []
    for key in ("note", "champion_rule", "family_notes", "models"):
        if key not in payload:
            problems.append(f"missing top-level key {key}")
    models = payload.get("models", {})
    if not models:
        problems.append("no models registered")
    for name, entry in models.items():
        for key in REQUIRED_KEYS:
            if key not in entry:
                problems.append(f"{name}: missing {key}")
        if entry.get("family") not in FAMILIES:
            problems.append(
                f"{name}: family {entry.get('family')!r} is not one of {FAMILIES}"
            )
        if entry.get("version") != name:
            problems.append(
                f"{name}: version field {entry.get('version')!r} does not match its key"
            )
        if not isinstance(entry.get("champion"), bool):
            problems.append(f"{name}: champion must be a boolean")
        if not isinstance(entry.get("eligible_for_champion"), bool):
            problems.append(f"{name}: eligible_for_champion must be a boolean")
        if entry.get("champion") and not entry.get("eligible_for_champion"):
            problems.append(f"{name}: an ineligible model cannot be champion")
    champions = [name for name, entry in models.items() if entry.get("champion")]
    if len(champions) > 1:
        problems.append(f"more than one champion declared: {champions}")
    return problems


def champion(payload: dict[str, Any]) -> str | None:
    """The declared champion, or None. No champion is declared in E4."""
    models = payload.get("models", {})
    for name, entry in models.items():
        if entry.get("champion"):
            return name
    return None


def eligible(payload: dict[str, Any]) -> list[str]:
    return [
        name
        for name, entry in payload.get("models", {}).items()
        if entry.get("eligible_for_champion")
    ]


def family_of(payload: dict[str, Any], version: str) -> str:
    return str(payload.get("models", {}).get(version, {}).get("family", ""))


def engine_tag(version: str) -> str:
    """The lowercase tag the evaluation engine uses for a registry version.

    Registry names are spelled like XS-v2; the engine's stored tables tag the
    same versions xs_v2, so every comparison between the two goes through here.
    """
    return version.replace("-", "_").lower()


def parameters_of(payload: dict[str, Any], version: str) -> dict[str, Any]:
    return dict(payload.get("models", {}).get(version, {}).get("parameters", {}))


def min_position_dollars(payload: dict[str, Any], version: str) -> float:
    """The minimum position size in dollars, from the registry.

    E11 Addition 4: names whose target notional is below this dollar size are
    dropped rather than held at a badly rounded weight. It is stored with the
    model version so a later sprint can see what the book was run under, and
    it is applied against the actual NAV so it works at any NAV. Zero means
    no minimum: no name is dropped on size.
    """
    live = payload.get("models", {}).get(version, {}).get("live", {})
    return float(live.get("min_position_dollars", 0.0))


def per_family_alternative(data_root: Path | None = None) -> dict[str, str]:
    """The per-portfolio-family best-calibrated model in E5's family table.

    Fixed by E8 Task 0b as the alternative every later
    champion-against-alternative comparison uses. For families whose
    best-calibrated entry is the champion itself the comparison degenerates
    to identity, and that is recorded where it happens, never papered over.
    """
    import pandas as pd

    root = (
        Path(data_root)
        if data_root is not None
        else Path(__file__).resolve().parents[1] / "data"
    )
    table = pd.read_parquet(root / "eval" / "e5_family_bias.parquet")
    pooled = table.loc[table["portfolio"] == "pooled"].copy()
    pooled["gap"] = (pooled["bias"] - 1.0).abs()
    return {
        str(row["family"]): str(row["version"])
        for row in pooled.loc[pooled.groupby("family")["gap"].idxmin()].to_dict(
            orient="records"
        )
    }
