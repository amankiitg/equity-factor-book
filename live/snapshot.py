"""B-cron: the one JSON snapshot the Cloudflare page reads.

Render keeps running one service, the evening cron, and that cron writes a single
JSON document every run and uploads it to Cloudflare R2. The browser never reaches
R2 and never reaches Supabase: a Worker reads the object through a binding on an
Access-protected hostname and serves it, so the bucket stays private and the
positions stay behind Access.

**Written on every run, including `stale_stopped` and `error`.** A page that shows
nothing when the run fails is worse than no page, because it looks like a quiet
evening. The snapshot carries the run's own status, so the failure is the news.

**`EFB_SNAPSHOT` is required, `on` or `off`, and the two are not symmetric.**

| `EFB_SNAPSHOT` | `dry_run` | what happens |
| --- | --- | --- |
| `on` | either | the snapshot is written and uploaded; a failed upload fails the run |
| `off` | true | nothing is uploaded, and the run records `snapshot: off` in
`run_status` and in the email, because the gate evenings run before the page
exists |
| `off` | false | an `error`: the flip cannot happen without a working page |

**JSON has no NaN.** Every float goes through `store.json_text`, which turns NaN and
infinity into `null`, and a test asserts the serialized document contains no bare
`NaN`.

**`expected_next_by`** is computed here from the NYSE calendar, the cron's own slot
and a stated grace, so the browser needs no calendar of its own: it compares the
current time with the instant the next snapshot should already exist by.

**No unqualified `n_eff`.** The breadth keys are `n_eff_kept` for the book that
trades and `n_eff_full_book` for the 499-name book before the floor, with the same
labels item 3 put on both pages.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd

from live import breadth, construction_table, staleness, store

SCHEMA_VERSION = 1
SNAPSHOT_ENV = "EFB_SNAPSHOT"
ON = "on"
OFF = "off"
LATEST_KEY = "latest.json"
ROOT_PROPOSALS = Path(__file__).resolve().parents[1] / "live" / "proposals"
DATED_TEMPLATE = "snapshots/{close}.json"

R2_ENVS = (
    "EFB_R2_ACCOUNT_ID",
    "EFB_R2_BUCKET",
    "EFB_R2_ACCESS_KEY_ID",
    "EFB_R2_SECRET_ACCESS_KEY",
)
R2_REGION = "auto"


class SnapshotNotConfigured(RuntimeError):
    """The snapshot cannot be written as configured, so the run has to stop."""


class SnapshotNotAllowed(RuntimeError):
    """`EFB_SNAPSHOT` is off where it has to be on."""


def snapshot_mode() -> str:
    """`on` or `off`, and never a default.

    The switch is required, because both of its defaults are wrong somewhere: an
    unasked-for `off` would let a live run skip the page, and an unasked-for `on`
    would make the gate evenings depend on a bucket that does not exist yet.
    """
    value = os.environ.get(SNAPSHOT_ENV, "").strip().lower()
    if value not in (ON, OFF):
        raise SnapshotNotConfigured(
            f"{SNAPSHOT_ENV} must be {ON!r} or {OFF!r} and it is "
            f"{value!r}; it is required because neither default is safe"
        )
    return value


def check_snapshot(dry_run: bool, mode: str | None = None) -> str:
    """The mode, after refusing `off` on a live run."""
    resolved = mode or snapshot_mode()
    if resolved == OFF and not dry_run:
        raise SnapshotNotAllowed(
            f"{SNAPSHOT_ENV}={OFF} while dry_run is false: the flip cannot happen "
            f"before the page can show a real snapshot"
        )
    return resolved


def expected_next_by(target_close: Any) -> str:
    """The UTC instant by which the next run's snapshot should exist.

    One source for the browser's expectation and for the gate's late window:
    `live.staleness.expected_next_by`, which reads the cron's own slot from
    render.yaml's schedule and the grace that sits beside it.
    """
    return staleness.expected_next_by(target_close)


def _iso(value: Any) -> str | None:
    """A date or timestamp as an ISO string, or None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return pd.Timestamp(value).isoformat()


def construction_label(manifest: dict[str, Any] | None) -> str:
    """The construction, generated only from the artifact's own fields."""
    return construction_table.construction_label(manifest or {})


def build(
    *,
    run: dict[str, Any],
    manifest: dict[str, Any] | None = None,
    book: pd.DataFrame | None = None,
    reconciliation: dict[str, Any] | None = None,
    construction: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """The document the page reads, assembled from what the run already knows.

    Nothing here is recomputed: every number comes from the proposal's manifest,
    the proposal's own rows with their trade reasons, the construction table's
    chosen row and the run's own status, so the page cannot disagree with the book
    the owner confirmed.
    """
    proposal = manifest or {}
    rows = book if book is not None else pd.DataFrame()
    chosen = construction or {}
    stamp = generated_at or datetime.now(UTC)
    target_close = _iso(run.get("target_close")) or proposal.get("as_of")
    names: list[dict[str, Any]] = []
    if len(rows):
        ordered = rows.reindex(rows["weight"].abs().sort_values(ascending=False).index)
        for entry in ordered.to_dict("records"):
            names.append(
                {
                    "ticker": str(entry.get("ticker")),
                    "weight": _number(entry.get("weight")),
                    "side": str(entry.get("side") or ""),
                    "reason": entry.get("reason"),
                    "z": _number(entry.get("z")),
                    "alpha": _number(entry.get("alpha")),
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": stamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "target_close": target_close,
        # The close of the proposal the book came from. On a run that proposed one
        # it is the target close; on a stopped run it is the close of the book the
        # page is still showing, so the page can never show a book without its date.
        "book_as_of": proposal.get("as_of"),
        "expected_next_by": expected_next_by(target_close) if target_close else None,
        "dry_run": bool(run.get("dry_run", True)),
        "store": run.get("store"),
        "run_status": {
            "status": run.get("status"),
            "detail": run.get("detail") or "",
            "failing_inputs": _json_value(run.get("failures"), []),
            "worst_input": run.get("worst_input"),
            "worst_sessions_behind": run.get("worst_sessions_behind"),
            "catch_up": bool(run.get("catch_up", False)),
            "catch_up_sessions": _json_value(run.get("catch_up_sessions"), []),
            "splits": _json_value(run.get("splits"), []),
            "flags": _json_value(run.get("flags"), []),
            "notify_status": run.get("notify_status"),
            "snapshot": run.get("snapshot"),
        },
        "construction": construction_table.construction_label(proposal),
        "breadth": {
            "n_eff_kept": _number(proposal.get("n_eff_kept")),
            "n_eff_full_book": _number(proposal.get("n_eff_full_book")),
            "kept_label": breadth.BOOK_LABEL,
            "full_book_label": breadth.FULL_BOOK_LABEL,
        },
        "book": {
            "n_names": len(names),
            "n_kept": _number(proposal.get("n_kept")),
            "n_long": _number(chosen.get("n_long")),
            "n_short": _number(chosen.get("n_short")),
            "gross": _number(proposal.get("gross")),
            "net": _number(proposal.get("net")),
            "max_kept_weight": _number(proposal.get("max_kept_weight")),
            "achieved_annual_vol": _number(proposal.get("achieved_annual_vol")),
            "expected_cost_bps": _number(
                proposal.get("expected_establishment_cost_bps")
            ),
            "names": names,
        },
        # One value per design column, named by fx.ESTIMATED_NAMES, after the
        # hedge. The hedge itself stays in `hedge` beside them.
        "exposures_before_hedge": _numbers(proposal.get("exposures_before_hedge")),
        "exposures_after_hedge": _numbers(proposal.get("exposures_after_hedge")),
        "hedge": {
            "idio_share_after_fmp": _number(proposal.get("idio_share_after_fmp")),
            "max_abs_exposure_after_fmp": _number(
                proposal.get("max_abs_exposure_after_fmp")
            ),
            "post_hedge_idio_share": _number(chosen.get("post_hedge_idio_share")),
            "post_hedge_max_abs_exposure": _number(
                chosen.get("post_hedge_max_abs_exposure")
            ),
        },
        "exposures": {
            "realized_market_beta": _number(chosen.get("realized_market_beta")),
            "realized_market_beta_shrunk": _number(
                chosen.get("realized_market_beta_shrunk")
            ),
            "residual_exposure_shrunk": _number(chosen.get("residual_exposure_shrunk")),
            "residual_exposure_winsor": _number(chosen.get("residual_exposure_winsor")),
        },
        "reconciliation": {
            key: _number((reconciliation or {}).get(key))
            for key in (
                "intended_notional",
                "filled_notional",
                "realized_annual_vol",
                "expected_cost_bps",
            )
        },
    }


def _number(value: Any) -> Any:
    """A float, an int, or None. Never a NaN or an infinity.

    JSON cannot carry either, so the document and its text would disagree if this
    let them through: `null` is the one way to say the run did not have a number.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):  # pragma: no cover - arrays and the like
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _json_value(value: Any, fallback: Any) -> Any:
    """A stored JSON string read back, or the fallback."""
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _numbers(value: Any) -> dict[str, Any]:
    """A dict of numbers with the non-finite ones nulled, or an empty dict."""
    if not isinstance(value, dict):
        return {}
    return {str(key): _number(item) for key, item in value.items()}


def payload_text(payload: dict[str, Any]) -> str:
    """The JSON text: sorted keys, no NaN, no bare NaN anywhere."""
    return store.json_text(payload, sort_keys=True) + "\n"


def r2_settings() -> dict[str, str]:
    """The four R2 variables, or an error naming what is missing."""
    missing = [name for name in R2_ENVS if not os.environ.get(name, "").strip()]
    if missing:
        raise SnapshotNotConfigured(
            f"the snapshot is on but {', '.join(missing)} "
            f"{'is' if len(missing) == 1 else 'are'} not set, so it cannot be uploaded"
        )
    return {name: os.environ[name].strip() for name in R2_ENVS}


def object_url(key: str, settings: dict[str, str] | None = None) -> str:
    """The S3-compatible URL for one object, path-style."""
    values = settings or r2_settings()
    account = values["EFB_R2_ACCOUNT_ID"]
    return (
        f"https://{account}.r2.cloudflarestorage.com/"
        f"{values['EFB_R2_BUCKET']}/{quote(key, safe='/')}"
    )


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


def signing_headers(
    url: str,
    body: bytes,
    settings: dict[str, str],
    *,
    now: datetime | None = None,
) -> dict[str, str]:
    """The headers for one signed `PUT`, in AWS SigV4 as R2 requires it.

    Written by hand rather than with a client library: one object, one verb, and
    no dependency worth carrying for it. The signature covers the payload hash, so
    a truncated body is rejected by the server rather than stored.
    """
    stamp = (now or datetime.now(UTC)).astimezone(UTC)
    amz_date = stamp.strftime("%Y%m%dT%H%M%SZ")
    day = stamp.strftime("%Y%m%d")
    host = url.split("/", 3)[2]
    path = "/" + url.split("/", 3)[3]
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical_headers = (
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join(
        ["PUT", path, "", canonical_headers, signed, payload_hash]
    )
    scope = f"{day}/{R2_REGION}/s3/aws4_request"
    to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )
    key = _sign(
        _sign(
            _sign(
                _sign(f"AWS4{settings['EFB_R2_SECRET_ACCESS_KEY']}".encode(), day),
                R2_REGION,
            ),
            "s3",
        ),
        "aws4_request",
    )
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "Host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={settings['EFB_R2_ACCESS_KEY_ID']}/{scope}, "
            f"SignedHeaders={signed}, Signature={signature}"
        ),
        "Content-Type": "application/json",
    }


def put_object(
    key: str,
    text: str,
    *,
    settings: dict[str, str] | None = None,
    poster: Callable[..., Any] | None = None,
) -> None:
    """One single-object PUT. Raises on anything but a 2xx answer."""
    values = settings or r2_settings()
    url = object_url(key, values)
    body = text.encode()
    headers = signing_headers(url, body, values)
    if poster is not None:
        poster(url, body, headers)
        return
    import urllib.request  # noqa: PLC0415 - only the real upload needs it

    request = urllib.request.Request(url, data=body, headers=headers, method="PUT")
    with urllib.request.urlopen(request, timeout=30) as response:
        if not 200 <= int(response.status) < 300:  # pragma: no cover - urllib raises
            raise RuntimeError(f"R2 answered {int(response.status)}")


def keys_for(close: Any) -> list[str]:
    """`latest.json` and the dated copy, in that order."""
    stamp = pd.Timestamp(close).date().isoformat() if close else "unknown"
    return [LATEST_KEY, DATED_TEMPLATE.format(close=stamp)]


def write_snapshot(
    *,
    run: dict[str, Any],
    manifest: dict[str, Any] | None = None,
    book: pd.DataFrame | None = None,
    reconciliation: dict[str, Any] | None = None,
    construction: dict[str, Any] | None = None,
    dry_run: bool = True,
    mode: str | None = None,
    poster: Callable[..., Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build and upload the snapshot, or record that it is deliberately off.

    Returns the summary the run stores and the message quotes: `snapshot: on
    (latest.json, snapshots/<close>.json)` or `snapshot: off (dry run)`.
    """
    resolved = check_snapshot(dry_run, mode)
    payload = build(
        run=run,
        manifest=manifest,
        book=book,
        reconciliation=reconciliation,
        construction=construction,
        generated_at=generated_at,
    )
    if resolved == OFF:
        payload["run_status"]["snapshot"] = f"{OFF} (dry run)"
        return {
            "mode": OFF,
            "written": [],
            "detail": f"snapshot: {OFF} (dry run)",
            "payload": payload,
        }
    text = payload_text(payload)
    written = keys_for(payload.get("target_close"))
    for key in written:
        put_object(key, text, poster=poster)
    return {
        "mode": ON,
        "written": written,
        "detail": f"snapshot: {ON} ({', '.join(written)})",
        "payload": payload,
    }


def chosen_row(manifest: dict[str, Any] | None, root: Any = None) -> dict[str, Any]:
    """The construction table's row for this manifest's construction.

    The table holds one row per candidate construction, so the row is selected by
    the name the manifest records rather than by position or by best number.
    """
    from pathlib import Path

    path = (
        Path(root) / "construction_table.parquet"
        if root is not None
        else Path(__file__).resolve().parents[1] / "live" / "construction_table.parquet"
    )
    if not path.exists():
        return {}
    table = pd.read_parquet(path)
    if table.empty or "construction" not in table.columns:
        return {}
    wanted = str((manifest or {}).get("construction") or "")
    if not wanted:
        return {}
    # The table names its rows by kind and floor ("share_only_20shares"), while
    # the manifest records the kind and the floor as fields, so the row is found
    # by the kind and then by the floor. An ambiguous match returns nothing
    # rather than a plausible row: the page shows the book without the table's
    # derived numbers instead of another construction's.
    rows = table.loc[table["construction"].astype(str).str.startswith(wanted)]
    floor = (manifest or {}).get("construction_floor_dollars")
    if floor and len(rows) > 1:
        rows = rows.loc[
            rows["construction"].astype(str).str.contains(f"_{int(floor)}", regex=False)
        ]
    n_kept = (manifest or {}).get("n_kept")
    if n_kept is not None and len(rows) > 1 and "n_kept" in rows.columns:
        rows = rows.loc[rows["n_kept"] == n_kept]
    if len(rows) != 1:
        return {}
    return {
        str(key): value
        for key, value in rows.iloc[-1].to_dict().items()
        if value is not None
    }


def previous_proposal() -> tuple[dict[str, Any] | None, pd.DataFrame | None]:
    """The last proposal on disk, so a stopped run still has a book to show.

    A stopped evening has no manifest of its own, and blanking the page on the
    evening the run refused to price a book would hide the book the owner is
    still holding. The rows carry no trade reasons: those belong to the evening
    that proposed them, and inventing them for a night that traded nothing is the
    kind of guess this pipeline does not make.
    """
    directory = ROOT_PROPOSALS
    if not directory.exists():  # pragma: no cover - before the first run
        return None, None
    manifests = sorted(directory.glob("proposal_*.json"))
    if not manifests:  # pragma: no cover - before the first run
        return None, None
    manifest = json.loads(manifests[-1].read_text())
    frame_path = manifests[-1].with_suffix(".parquet")
    frame = pd.read_parquet(frame_path) if frame_path.exists() else None
    return manifest, frame
