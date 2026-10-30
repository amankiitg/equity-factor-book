"""Replace the `monthly` key of an already-published close, and nothing else.

The anchored block grows as the panels do, and a new field cannot appear on the live
page until a document carries it. Waiting for the next evening is wrong: the readers of
a hold day are reading *this* close. Running the evening again is worse: it would size
and could trade.

So this rewrites one key of one document. Everything else in the object is kept exactly
as published - the run summary, the book, the reconciliation, the attribution - and the
`monthly` block is rebuilt from the store the way the evening builds it, from the same
tables and the same proposal row. Both keys the page reads (`latest.json` and
`snapshots/<close>.json`) are written, as the evening writes them.

Read-only by default: without `--apply` it prints what it would write and, with `--out`,
writes the document to a path so a fixture can be built from it. `--apply` refuses
without `--backup`, saves the objects as they were to that directory, records them in
the manifest, and reads both back to prove the bytes landed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # so the script runs from anywhere
    sys.path.insert(0, str(ROOT))

from live import monthly_view, snapshot, store  # noqa: E402


BUCKET = "efb-snapshots"
WEB = ROOT / "web"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _r2_configured() -> bool:
    """Whether this shell can talk to R2 with the bucket's own credentials."""
    return all(os.environ.get(name, "").strip() for name in snapshot.R2_ENVS)


def _wrangler(*args: str) -> str:
    """One `wrangler r2 object` call against the remote bucket, and its output."""
    if not (WEB / "wrangler.jsonc").exists():
        raise SystemExit(f"no wrangler config under {WEB}")
    result = subprocess.run(
        ["npx", "wrangler", "r2", "object", *args, "--remote"],
        cwd=WEB,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"wrangler {args[0]} failed: {result.stderr.strip()}")
    return result.stdout


def read_object(key: str) -> str:
    """One object's text, through the bucket's credentials or the wrangler CLI.

    The evening has the four R2 variables; a shell on the owner's machine has wrangler
    authenticated instead, which is the same bucket by a different door. One of the two
    is always available where this script is run.
    """
    if _r2_configured():
        return snapshot.get_object_text(key)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "object"
        _wrangler("get", f"{BUCKET}/{key}", f"--file={path}")
        return path.read_text()


def write_object(key: str, text: str) -> None:
    if _r2_configured():
        snapshot.put_object(key, text)
        return
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "object"
        path.write_text(text)
        _wrangler(
            "put",
            f"{BUCKET}/{key}",
            f"--file={path}",
            "--content-type=application/json",
        )


def proposal_row(close: str) -> dict[str, Any]:
    """The close's own proposal row: the manifest the block is measured from."""
    frame = store.select("proposals")
    frame["trade_date"] = frame["trade_date"].astype(str).str.slice(0, 10)
    rows = frame.loc[frame["trade_date"] == close]
    if rows.empty:
        raise SystemExit(f"the store holds no proposal for {close}")
    row = rows.iloc[-1].to_dict()
    manifest = row.get("manifest")
    if isinstance(manifest, str):
        manifest = json.loads(manifest)
    row["manifest"] = manifest if isinstance(manifest, dict) else {}
    return row


def nav_of(row: dict[str, Any]) -> float | None:
    """The NAV the proposal was sized on, from the manifest, then the row."""
    for source in (row.get("manifest") or {}, row):
        for key in ("nav", "nav_source"):
            try:
                number = float(source.get(key))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if number > 0:
                return number
    return None


def rebuilt(
    close: str, guard_threshold: float | None = None
) -> tuple[dict[str, Any], str, str]:
    """The close's published document with a freshly built `monthly` block.

    Returns `(payload, text, block_state)` where the state is the line the email
    carries: built with its anchor, or not built and why. The published object is read
    first and kept: this is a rewrite of one key, not a rebuild of the document.
    """
    published = read_object(snapshot.DATED_TEMPLATE.format(close=close))
    payload = json.loads(published)
    as_published = json.loads(published)
    row = proposal_row(close)
    block = monthly_view.from_store(
        today=close,
        tonight_manifest=row.get("manifest"),
        nav=nav_of(row),
        sector_of=monthly_view.sector_map_from_store(),
        # The guard's threshold is a setting on the evening (`EFB_DRIFT_GUARD`), not
        # something a quiet manifest records, so a rebuild here must be given it or
        # the strip loses the "5.00%" it is measured against.
        guard_threshold=guard_threshold
        if guard_threshold is not None
        else monthly_view.guard_threshold_from_env(),
    )
    if block is None:
        payload.pop("monthly", None)
        state = "not built: the store could not answer"
    elif not block:
        payload.pop("monthly", None)
        state = "not built: the close has no proposal row"
    else:
        payload["monthly"] = block
        anchor = (block.get("anchor") or {}).get("close")
        state = f"built (anchor {anchor})"
    text = _restyle(payload, published)
    changed = differs_only_in_monthly(as_published, json.loads(text))
    if changed not in ([], ["monthly"]):
        raise SystemExit(f"the rewrite would change more than the monthly key: {changed}")
    return payload, text, state


def _restyle(payload: dict[str, Any], original: str) -> str:
    """The document in its own formatting, so only the rewritten key changes bytes.

    A published object is either the writer's compact text or the indented copy a
    hand republish leaves behind; rewriting one key must not restyle the other
    twenty, or the "only the monthly key changed" claim stops being checkable.
    """
    if original.startswith("{\n  "):
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
    return snapshot.payload_text(payload)


def differs_only_in_monthly(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """The top-level keys whose value changed, so a rewrite can be proved narrow."""
    changed = [key for key in set(before) | set(after) if before.get(key) != after.get(key)]
    return sorted(changed)


def backup(objects: dict[str, str], directory: Path, manifest_path: Path) -> Path:
    """Save the objects as they were, and say where and what they hashed to."""
    directory.mkdir(parents=True, exist_ok=True)
    entries = []
    for key, text in objects.items():
        path = directory / key.replace("/", "_")
        path.write_text(text)
        entries.append(
            {
                "key": key,
                "file": str(path),
                "bytes": len(text.encode()),
                "sha256": _sha256(text),
            }
        )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {"taken_at": datetime.now(timezone.utc).isoformat(), "entries": entries},
            indent=1,
        )
        + "\n"
    )
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="republish one close's monthly block")
    parser.add_argument("--close", required=True, help="the close to republish")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the document here instead of publishing it",
    )
    parser.add_argument(
        "--apply", action="store_true", help="upload both keys (needs --backup)"
    )
    parser.add_argument("--backup", type=Path, default=None, help="backup directory")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="where the backup manifest goes (default: inside --backup)",
    )
    parser.add_argument(
        "--drift-guard",
        type=float,
        default=None,
        help="EFB_DRIFT_GUARD as the evening had it (default: this shell's value)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="read both keys back and compare them to what was written",
    )
    args = parser.parse_args(argv)

    close = str(args.close)[:10]
    payload, text, state = rebuilt(close, args.drift_guard)
    block = payload.get("monthly") or {}
    anchored = block.get("sectors") or {}
    print(f"monthly view: {state}")
    print(f"document: {len(text.encode())} bytes, {len(payload)} top-level keys")
    print(
        "sectors: "
        + (
            f"{len(anchored.get('rows', []))} rows, one side "
            f"{anchored.get('one_side_usd', 0):,.2f}, both sides "
            f"{anchored.get('both_sides_usd', 0):,.2f}"
            if anchored
            else "absent"
        )
    )
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        print(f"written: {args.out}")

    if not args.apply:
        print("read-only: nothing uploaded (pass --apply and --backup to publish)")
        return 0

    if args.backup is None:
        raise SystemExit("--apply needs --backup: the objects as published come first")

    keys = snapshot.keys_for(close)
    before = {key: read_object(key) for key in keys}
    manifest_path = args.manifest or (args.backup / "manifest.json")
    print(f"backup manifest: {backup(before, args.backup, manifest_path)}")

    for key in keys:
        write_object(key, text)
        print(f"put: {key} {len(text.encode())} bytes")

    if args.verify:
        for key in keys:
            read_back = read_object(key)
            if read_back != text:
                raise SystemExit(f"{key} does not read back as written")
            print(f"verified: {key} {_sha256(read_back)[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
