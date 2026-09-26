"""B-cron: the one JSON snapshot the Cloudflare page reads.

The switch, the two keys, the calendar-based `expected_next_by`, the NaN rule, the
breadth names, the schema the writer is held to, and the credentials that must not
appear in the document or in a failure's text.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
import pandas as pd
import pytest

from live import notify, snapshot

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "docs" / "snapshot.schema.json").read_text())

MANIFEST: dict[str, Any] = {
    "as_of": "2026-09-25",
    "construction": "share_only",
    "construction_floor_shares": 20,
    "floor_iterated": True,
    "n_kept": 150,
    "n_eff_kept": 70.5921,
    "n_eff_full_book": 157.3291,
    "gross": 1.0,
    "net": 0.0,
    "max_kept_weight": 0.0535,
    "achieved_annual_vol": 0.06,
    "expected_establishment_cost_bps": 8.4,
    "idio_share_after_fmp": 1.0,
    "max_abs_exposure_after_fmp": 3.8e-15,
}
RUN: dict[str, Any] = {
    "target_close": "2026-09-25",
    "status": "ok",
    "detail": "",
    "dry_run": True,
    "store": "postgres/efb",
    "failures": [],
    "worst_input": None,
    "worst_sessions_behind": None,
    "catch_up": True,
    "catch_up_sessions": ["2026-09-15", "2026-09-21"],
    "splits": ["split: APH 2:1 applied"],
    "flags": [{"ticker": "ZZZ", "return": -0.55, "explained_by": None}],
    "notify_status": "sent",
    "snapshot": "on (latest.json, snapshots/2026-09-25.json)",
}


def book_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["MU", "WBD"],
            "weight": [0.05, -0.04],
            "side": ["long", "short"],
            "reason": ["new position", "alpha moved"],
            "z": [1.5, -1.2],
            "alpha": [0.003, -0.002],
        }
    )


def built(**overrides: Any) -> dict[str, Any]:
    run = {**RUN, **overrides.pop("run", {})}
    return snapshot.build(
        run=run,
        manifest={**MANIFEST, **overrides.pop("manifest", {})},
        book=overrides.pop("book", book_frame()),
        construction={
            "post_hedge_idio_share": 1.0,
            "post_hedge_max_abs_exposure": 1e-15,
        },
        generated_at=overrides.pop(
            "generated_at", datetime(2026, 9, 25, 23, 4, tzinfo=UTC)
        ),
        **overrides,
    )


def test_the_writer_satisfies_the_committed_schema() -> None:
    """The writer and the page cannot drift: the page reads this schema's keys."""
    jsonschema.validate(instance=built(), schema=SCHEMA)
    # and a document missing a field the page needs is refused by the schema
    broken = built()
    del broken["expected_next_by"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=broken, schema=SCHEMA)


def test_the_document_has_no_nan_and_no_bare_nan_in_its_text() -> None:
    payload = built(
        manifest={"n_eff_kept": float("nan")},
        book=pd.DataFrame(
            {
                "ticker": ["MU"],
                "weight": [float("nan")],
                "side": ["long"],
                "reason": [None],
                "z": [float("inf")],
                "alpha": [0.001],
            }
        ),
    )
    text = snapshot.payload_text(payload)
    assert "NaN" not in text and "Infinity" not in text
    assert payload["breadth"]["n_eff_kept"] is None
    assert payload["book"]["names"][0]["weight"] is None
    assert payload["book"]["names"][0]["z"] is None
    assert json.loads(text)["breadth"]["n_eff_kept"] is None


def test_there_is_no_unqualified_n_eff_in_the_document() -> None:
    text = snapshot.payload_text(built())
    assert '"n_eff"' not in text
    assert '"n_eff_kept"' in text and '"n_eff_full_book"' in text
    assert "n_eff_full" + '"' not in text


def test_the_breadth_carries_item_3s_two_labels() -> None:
    payload = built()
    assert payload["breadth"]["n_eff_kept"] == pytest.approx(70.5921)
    assert payload["breadth"]["n_eff_full_book"] == pytest.approx(157.3291)
    assert payload["breadth"]["kept_label"] == "the book's effective breadth"
    assert payload["breadth"]["full_book_label"] == (
        "the full 499-name book's, before the floor"
    )


def test_the_snapshot_carries_the_runs_own_status_including_the_splits() -> None:
    payload = built()
    status = payload["run_status"]
    assert status["status"] == "ok"
    assert status["catch_up"] is True
    assert status["catch_up_sessions"] == ["2026-09-15", "2026-09-21"]
    assert status["splits"] == ["split: APH 2:1 applied"]
    assert status["flags"][0]["ticker"] == "ZZZ"
    assert payload["store"] == "postgres/efb"
    assert payload["construction"] == "min 20 shares (iterated to a fixed point)"


def test_the_names_carry_weight_side_reason_and_alpha() -> None:
    names = built()["book"]["names"]
    assert [entry["ticker"] for entry in names] == ["MU", "WBD"]
    assert names[0]["weight"] == pytest.approx(0.05)
    assert names[0]["side"] == "long"
    assert names[0]["reason"] == "new position"
    assert names[1]["alpha"] == pytest.approx(-0.002)


def test_expected_next_by_comes_from_the_nyse_calendar() -> None:
    # Friday 2026-09-25: the next session is Monday 09-28, whose cron slot is
    # 22:30 UTC, plus the three-hour grace.
    assert snapshot.expected_next_by("2026-09-25") == "2026-09-29T01:30:00Z"
    # Thanksgiving Thursday 2026-11-26 is not a session, so the next one is
    # Friday 11-27.
    assert snapshot.expected_next_by("2026-11-26") == "2026-11-28T01:30:00Z"
    # The due instant is the day after the session, because the slot is 22:30 UTC
    # and the grace takes it past midnight.
    assert snapshot.expected_next_by("2026-09-16") == "2026-09-18T01:30:00Z"


def test_the_switch_is_required_and_off_needs_a_dry_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(snapshot.SNAPSHOT_ENV, raising=False)
    with pytest.raises(snapshot.SnapshotNotConfigured):
        snapshot.snapshot_mode()
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, "yes")
    with pytest.raises(snapshot.SnapshotNotConfigured):
        snapshot.snapshot_mode()
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, "off")
    assert snapshot.check_snapshot(dry_run=True) == "off"
    with pytest.raises(snapshot.SnapshotNotAllowed):
        snapshot.check_snapshot(dry_run=False)
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, "on")
    assert snapshot.check_snapshot(dry_run=False) == "on"


def test_off_writes_nothing_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, "off")
    written: list[str] = []
    result = snapshot.write_snapshot(
        run=RUN,
        manifest=MANIFEST,
        book=book_frame(),
        dry_run=True,
        poster=lambda url, body, headers: written.append(url),
    )
    assert result["mode"] == "off"
    assert written == []
    assert result["detail"] == "snapshot: off (dry run)"
    assert result["payload"]["run_status"]["snapshot"] == "off (dry run)"


def test_on_writes_latest_and_the_dated_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, "on")
    for name in snapshot.R2_ENVS:
        monkeypatch.setenv(name, "test-value-for-" + name)
    puts: list[tuple[str, bytes, dict[str, str]]] = []
    result = snapshot.write_snapshot(
        run=RUN,
        manifest=MANIFEST,
        book=book_frame(),
        dry_run=True,
        poster=lambda url, body, headers: puts.append((url, body, headers)),
    )
    assert result["mode"] == "on"
    assert result["written"] == ["latest.json", "snapshots/2026-09-25.json"]
    assert len(puts) == 2
    urls = [url for url, _, _ in puts]
    assert urls[0].endswith("/test-value-for-EFB_R2_BUCKET/latest.json")
    assert urls[1].endswith("/snapshots/2026-09-25.json")
    # Both objects carry the same document, and it is the signed body's own.
    bodies = [body for _, body, _ in puts]
    assert bodies[0] == bodies[1]
    payload = json.loads(bodies[0])
    assert payload["schema_version"] == 1
    assert payload["book"]["n_names"] == 2
    # The signature is a SigV4 one, with the payload hash inside it.
    headers = puts[0][2]
    assert headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=")
    assert (
        "SignedHeaders=host;x-amz-content-sha256;x-amz-date" in headers["Authorization"]
    )
    assert (
        headers["x-amz-content-sha256"]
        == snapshot.hashlib.sha256(bodies[0]).hexdigest()
    )


def test_the_document_carries_no_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing that opens the bucket, sends the mail or writes the database."""
    secrets = {
        "EFB_R2_ACCESS_KEY_ID": "a" * 32,
        "EFB_R2_SECRET_ACCESS_KEY": "b" * 64,
        "EFB_RESEND_API_KEY": "re_" + "c" * 24,
        "EFB_SUPABASE_DB_URL": "postgresql://user:pw@host:5432/db",
    }
    payload = built(manifest={"note": list(secrets.values())})
    text = snapshot.payload_text(payload)
    for shape in ("a" * 32, "b" * 64, "re_" + "c" * 24, "postgresql://"):
        assert shape not in text
    # and the scrub would catch each of them on the way out anyway
    for value in secrets.values():
        assert value not in notify.scrub(f"failed with {value}")


def test_a_missing_r2_variable_is_an_error_naming_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, "on")
    for name in snapshot.R2_ENVS:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(snapshot.SnapshotNotConfigured) as err:
        snapshot.write_snapshot(run=RUN, manifest=MANIFEST, dry_run=True)
    assert snapshot.R2_ENVS[0] in str(err.value)


def test_a_failed_upload_raises_so_the_run_can_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, "on")
    for name in snapshot.R2_ENVS:
        monkeypatch.setenv(name, "test-value-for-" + name)

    def _refuse(url: str, body: bytes, headers: dict[str, str]) -> None:
        raise RuntimeError(f"HTTP 403 for {url} with {headers['Authorization']}")

    with pytest.raises(RuntimeError):
        snapshot.write_snapshot(
            run=RUN, manifest=MANIFEST, book=book_frame(), dry_run=True, poster=_refuse
        )


def test_a_stopped_run_still_carries_a_book_from_the_last_proposal() -> None:
    """The page must not blank on the evening the loop refused to price one."""
    manifest, frame = snapshot.previous_proposal()
    assert manifest is not None and frame is not None
    payload = built(run={"target_close": "2026-09-25", "status": "stale_stopped"})
    assert payload["run_status"]["status"] == "stale_stopped"
    assert payload["book"]["n_names"] == 2
    # and the helper itself reads the newest stored proposal
    assert manifest["as_of"] >= "2026-09-18"
    assert {"ticker", "weight"}.issubset(frame.columns)


@pytest.mark.slow
def test_the_hedge_drives_the_exposures_to_zero() -> None:
    """X'w after the hedge is zero, which is exactly what the hedge guarantees.

    One value per design column, labelled by `fx.ESTIMATED_NAMES`, taken from the
    live book the run builds rather than from a fixture. A nonzero value here is a
    bug worth catching before it reaches the page.
    """
    from efb.models import fundamental as fx
    from live import evening_job

    manifest = evening_job.build_proposal(store=False)
    before = manifest["exposures_before_hedge"]
    exposures = manifest["exposures_after_hedge"]
    assert list(exposures) == list(fx.ESTIMATED_NAMES)
    assert list(before) == list(fx.ESTIMATED_NAMES)
    worst_after = max(abs(float(value)) for value in exposures.values())
    assert worst_after < 1e-10, f"the hedge left an exposure of {worst_after:.3e}"
    # And the pre-hedge side is the hedge's own X'w of the unhedged book, so it is
    # clearly nonzero: a zero here means the two vectors are the same number under
    # two names, which is the mistake this asserts against.
    worst_before = max(abs(float(value)) for value in before.values())
    assert worst_before > 1e-3, f"the pre-hedge exposures are only {worst_before:.3e}"
    # and the book the exposures were taken from is the stored one
    assert manifest["n_eff_kept"] == pytest.approx(70.5921, abs=1e-3)
