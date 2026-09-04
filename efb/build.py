"""One-command rebuild of the E1 data layer (Sprint E1, Task 7).

`python -m efb.build` (alias: make rebuild-e1) rebuilds every E1 artifact
from its sources, writes data/VERSION.json with a content hash per
artifact, and stores the F1 criteria in sprints/E1/RESULTS.json.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from efb import factors, hygiene, prices, returns, universe

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
START = "2010-01-04"
WARMUP_START = "2009-12-15"

ARTIFACTS = [
    "raw/prices.parquet",
    "raw/factors_ff.parquet",
    "processed/returns.parquet",
    "processed/universe_membership.parquet",
    "processed/sectors.parquet",
    "processed/events.parquet",
]


def hash_file(path: Path) -> str:
    """SHA-256 content hash of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_version(artifact_paths: list[Path], out_path: Path, note: str) -> dict:
    """Write data/VERSION.json with a content hash of every artifact."""
    artifacts: dict[str, dict[str, object]] = {}
    for path in sorted(artifact_paths):
        artifacts[path.name] = {
            "sha256": hash_file(path),
            "bytes": path.stat().st_size,
        }
    payload = {
        "note": note,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "artifacts": artifacts,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def rebuild(
    data_root: Path = DATA_ROOT,
    start: str = START,
    end: str | None = None,
    as_of: str | None = None,
) -> dict[str, object]:
    """Rebuild all E1 artifacts from sources and version them."""
    as_of = as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    end = end or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw_dir = data_root / "raw"
    processed_dir = data_root / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    # 1. Universe sources
    constituents = universe.fetch_constituents()
    changes = universe.fetch_changes()
    tickers = universe.all_tickers(constituents, changes)

    # 2. Prices
    cache_path = raw_dir / "yf_cache.parquet"
    raw_prices = prices.load_or_download(tickers, cache_path, start=WARMUP_START, end=end)
    prices_artifact = prices.build_prices_artifact(raw_prices, start=start)
    prices.save_prices(prices_artifact, raw_dir / "prices.parquet")

    # 3. Universe membership and sectors
    members = universe.build_membership(changes, constituents, start=start, end=end)
    members.to_parquet(processed_dir / "universe_membership.parquet")
    sectors = universe.build_sectors(constituents, as_of=as_of)
    sectors.to_parquet(processed_dir / "sectors.parquet", index=False)

    # 4. Factors
    frames = factors.load_french_factors()
    factors_artifact = factors.build_factors_artifact(frames, start=start)
    factors_artifact.to_parquet(raw_dir / "factors_ff.parquet")

    # 5. Returns and hygiene flags
    returns_frame = returns.compute_returns(prices_artifact, factors_artifact["rf"])
    returns_frame = hygiene.apply_flags(returns_frame)
    returns_frame.to_parquet(processed_dir / "returns.parquet")

    # 6. Event log
    membership_events = universe.membership_changes(members)
    events = hygiene.build_events(prices_artifact, returns_frame, membership_events)
    events.to_parquet(processed_dir / "events.parquet")

    # 7. Version file
    artifact_paths = [data_root / rel for rel in ARTIFACTS]
    payload = write_version(
        artifact_paths,
        data_root / "VERSION.json",
        note="Built by make rebuild-e1 (Sprint E1). Every data artifact carries a content hash here; the dashboard sidebar shows this version.",
    )
    return {"n_steps": 7, "version": payload, "n_tickers": len(tickers)}


def main() -> None:
    summary = rebuild()
    print(json.dumps({"n_steps": summary["n_steps"], "n_tickers": summary["n_tickers"]}, indent=2))


if __name__ == "__main__":
    main()
