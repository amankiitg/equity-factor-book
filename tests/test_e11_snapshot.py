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
GENERATED_AT = datetime(2026, 9, 25, 23, 4, tzinfo=UTC)
CONSTRUCTION: dict[str, Any] = {
    "post_hedge_idio_share": 1.0,
    "post_hedge_max_abs_exposure": 1e-15,
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
        construction=overrides.pop("construction", CONSTRUCTION),
        generated_at=overrides.pop("generated_at", GENERATED_AT),
        **overrides,
    )


def _settings(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """The four R2 variables and the switch, as the run sees them."""
    values = {
        "EFB_R2_ACCOUNT_ID": "account123",
        "EFB_R2_BUCKET": "efb-snapshots",
        "EFB_R2_ACCESS_KEY_ID": "test-access-key-id",
        "EFB_R2_SECRET_ACCESS_KEY": "test-secret-access-key",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, "on")
    return values


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


def test_the_reconciliation_block_carries_both_books_risk_figures() -> None:
    """The traded book's figures and the full book's, each under its own names.

    The row stores them as JSON text, the way `reconcile.daily_record` writes
    them, and the page reads objects: the traded book's volatility must not be
    labelled with the full book's breadth, and the two keys must be there for the
    page to read at all.
    """
    traded = {
        "forecast_annual_vol": 0.0459,
        "idio_share": 0.981,
        "max_abs_exposure": 0.0334,
        "gross": 0.94,
        "net": 0.0,
        "n_eff": 94.2573,
        "max_weight": 0.033448,
        "variance_share_cap_binds": False,
        "top_variance_shares": [{"ticker": "MU", "variance_share": 0.031}],
    }
    full = {
        "forecast_annual_vol": 0.06,
        "idio_share": 1.0,
        "max_abs_exposure": 3.8e-15,
        "gross": 1.0,
        "net": 0.0,
        "n_eff": 157.3291,
        "n_names": 499,
    }
    payload = built(
        reconciliation={
            "intended_notional": 1000.0,
            "filled_notional": 0.0,
            "realized_annual_vol": None,
            "expected_cost_bps": 8.4,
            "traded_risk": json.dumps(traded),
            "full_risk": json.dumps(full),
        }
    )

    block = payload["reconciliation"]
    assert block["traded_risk"] == traded
    assert block["full_risk"] == full
    assert block["traded_risk"]["forecast_annual_vol"] != (
        block["full_risk"]["forecast_annual_vol"]
    )
    jsonschema.validate(instance=payload, schema=SCHEMA)


def test_a_run_with_no_book_publishes_null_figures_not_missing_keys() -> None:
    """A stopped run has no traded book; the keys are there and null.

    The page reads the keys it knows, so an absent key would read as an unbuilt
    page rather than as the evening that refused to price a book.
    """
    payload = built(reconciliation={"intended_notional": None})

    block = payload["reconciliation"]
    assert "traded_risk" in block and block["traded_risk"] is None
    assert "full_risk" in block and block["full_risk"] is None
    assert json.loads(snapshot.payload_text(payload))["reconciliation"] == block


def test_the_actual_holdings_are_written_only_when_the_account_was_read() -> None:
    """The evening's own document is not the reconciler's: no key, not a null one.

    The evening job writes the target book and never reads the account, so its
    document must be the same bytes it always was; the 15:30 job adds this one
    section to the document already published. A key holding null would tell the
    page the account holds nothing, which is a stronger and false claim.
    """
    actual = {
        "as_of": "2026-09-26",
        "close": "2026-09-25",
        "n_names": 2,
        "gross_notional": 30200.0,
        "net_notional": 19400.0,
        "names": [
            {"ticker": "AAA", "side": "long", "notional": 24800.0, "weight": 0.0248},
            {"ticker": "DG", "side": "short", "notional": -5400.0, "weight": -0.0054},
        ],
        "fills": None,
    }

    without = built()
    assert "actual_holdings" not in without

    with_actual = built(actual=actual)
    block = with_actual["actual_holdings"]
    # the dates go in as the document's own ISO timestamps, like target_close
    assert str(block["close"]).startswith("2026-09-25")
    assert str(block["as_of"]).startswith("2026-09-26")
    assert block["names"] == actual["names"]
    assert block["gross_notional"] == actual["gross_notional"]
    assert block["net_notional"] == actual["net_notional"]
    assert block["n_names"] == 2
    assert block["fills"] is None
    # the target book is untouched, and the only difference is the new section
    assert with_actual["book"] == without["book"]
    assert with_actual["reconciliation"] == without["reconciliation"]
    stripped = {
        key: value for key, value in with_actual.items() if key != "actual_holdings"
    }
    assert stripped == without

    jsonschema.validate(instance=without, schema=SCHEMA)
    jsonschema.validate(instance=with_actual, schema=SCHEMA)


def test_the_actual_holdings_carry_the_fills_and_never_a_non_finite() -> None:
    """The section is read from the published text, so NaN and infinity are null.

    JSON cannot carry either, so a document that held one would either fail to
    serialize or disagree with its own text, and the page would read a weight of
    null as a name that had one.
    """
    actual = {
        "as_of": "2026-09-26",
        "close": "2026-09-25",
        "n_names": 1,
        "gross_notional": float("nan"),
        "net_notional": None,
        "names": [
            {
                "ticker": "DG",
                "side": "short",
                "notional": float("nan"),
                "weight": float("inf"),
            }
        ],
        "fills": {
            "trade_date": "2026-09-25",
            "n_orders": 1,
            "n_filled": 0,
            "n_unfilled": 1,
            "not_sent": 0,
            "realized_cost_bps": None,
            "expected_cost_bps": 8.4,
            "unfilled": ["DG sell_to_open 41 canceled 12:15 UTC"],
            "unread": [],
        },
    }
    payload = built(actual=actual)
    block = payload["actual_holdings"]

    assert block["names"][0]["notional"] is None
    assert block["names"][0]["weight"] is None
    assert block["gross_notional"] is None
    assert block["net_notional"] is None
    assert block["n_names"] == 1
    assert block["fills"]["unfilled"] == ["DG sell_to_open 41 canceled 12:15 UTC"]
    assert block["fills"]["n_filled"] == 0
    assert str(block["fills"]["trade_date"]).startswith("2026-09-25")
    assert "NaN" not in snapshot.payload_text(payload)
    assert "Infinity" not in snapshot.payload_text(payload)
    assert json.loads(snapshot.payload_text(payload))["actual_holdings"] == block
    jsonschema.validate(instance=payload, schema=SCHEMA)


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
        poster=lambda **kwargs: written.append(kwargs["Key"]),
    )
    assert result["mode"] == "off"
    assert written == []
    assert result["detail"] == "snapshot: off (dry run)"
    assert result["payload"]["run_status"]["snapshot"] == "off (dry run)"


def test_the_client_points_at_the_accounts_r2_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R2 is S3-compatible: boto3 against the account's endpoint, region auto."""
    import boto3

    values = {
        "EFB_R2_ACCOUNT_ID": "account123",
        "EFB_R2_BUCKET": "efb-snapshots",
        "EFB_R2_ACCESS_KEY_ID": "test-access-key-id",
        "EFB_R2_SECRET_ACCESS_KEY": "test-secret-access-key",
    }
    captured: dict[str, Any] = {}

    def _client(name: str, **kwargs: Any) -> object:
        captured["name"] = name
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(boto3, "client", _client)

    snapshot.r2_client(values)

    assert snapshot.r2_endpoint(values) == (
        "https://account123.r2.cloudflarestorage.com"
    )
    assert captured["name"] == "s3"
    assert captured["endpoint_url"] == snapshot.r2_endpoint(values)
    assert captured["region_name"] == "auto"
    assert captured["aws_access_key_id"] == "test-access-key-id"
    assert captured["aws_secret_access_key"] == "test-secret-access-key"


def test_on_writes_latest_and_the_dated_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    """One put per key, through a real client, with a checksum over the body."""
    from botocore.stub import Stubber

    values = _settings(monkeypatch)
    client = snapshot.r2_client(values)
    body = snapshot.payload_text(built()).encode()
    stubber = Stubber(client)
    for key in ("latest.json", "snapshots/2026-09-25.json"):
        stubber.add_response(
            "put_object",
            {},
            {
                "Bucket": values["EFB_R2_BUCKET"],
                "Key": key,
                "Body": body,
                "ContentType": "application/json",
                "ChecksumSHA256": snapshot.checksum_sha256(body),
            },
        )
    stubber.activate()

    result = snapshot.write_snapshot(
        run=RUN,
        manifest=MANIFEST,
        book=book_frame(),
        construction=CONSTRUCTION,
        dry_run=True,
        poster=client.put_object,
        generated_at=GENERATED_AT,
    )

    stubber.assert_no_pending_responses()
    assert result["mode"] == "on"
    assert result["written"] == ["latest.json", "snapshots/2026-09-25.json"]
    payload = json.loads(body)
    assert payload["schema_version"] == 1
    assert payload["book"]["n_names"] == 2


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
    _settings(monkeypatch)

    def _refuse(**kwargs: Any) -> None:
        raise RuntimeError(
            "An error occurred (AccessDenied) when calling the PutObject "
            f"operation: {kwargs['Key']}"
        )

    with pytest.raises(RuntimeError):
        snapshot.write_snapshot(
            run=RUN, manifest=MANIFEST, book=book_frame(), dry_run=True, poster=_refuse
        )


def _store_proposal(trade_date: str, tickers: list[str]) -> None:
    """One proposal and its rows in the store, in the shape the run writes them."""
    from live import store

    store.upsert(
        "proposals",
        [
            {
                "trade_date": trade_date,
                "signal": "idio_momentum",
                "as_of": trade_date,
                "manifest": json.dumps({**MANIFEST, "as_of": trade_date}),
            }
        ],
    )
    store.upsert(
        "positions",
        [
            {
                "trade_date": trade_date,
                "ticker": ticker,
                "weight": 0.05 if index == 0 else -0.04,
                "side": "long" if index == 0 else "short",
                "z": 1.5 if index == 0 else -1.2,
                "alpha": 0.003,
                "reason": "alpha moved",
            }
            for index, ticker in enumerate(tickers)
        ],
    )


@pytest.fixture
def stored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty store under the local fallback, which is the whole of `efb`."""
    from live import store

    where = tmp_path / "store"
    monkeypatch.setattr(store, "LOCAL_DIR", where)
    return where


def test_a_stopped_run_reads_the_book_from_the_store(stored: Path) -> None:
    """The page must not blank on the evening the loop refused to price one."""
    _store_proposal("2026-09-25", ["MU", "WBD"])

    manifest, frame, reason = snapshot.previous_proposal()

    assert reason is None
    assert manifest is not None and manifest["as_of"] == "2026-09-25"
    assert frame is not None and list(frame["ticker"]) == ["MU", "WBD"]
    payload = snapshot.build(
        run={**RUN, "status": "stale_stopped"},
        manifest=manifest,
        book=frame,
        book_reason=reason,
    )
    jsonschema.validate(instance=payload, schema=SCHEMA)
    assert payload["run_status"]["status"] == "stale_stopped"
    assert payload["book"]["n_names"] == 2
    assert payload["book"]["reason"] is None
    assert str(payload["book_as_of"]).startswith("2026-09-25")


def test_the_store_beats_anything_on_disk(stored: Path) -> None:
    """On Render the disk is the deploy image, so it must not be read at all."""
    on_disk = json.loads(
        (ROOT / "live" / "proposals" / "proposal_2026-09-21.json").read_text()
    )
    _store_proposal("2026-09-25", ["MU", "WBD"])

    manifest, frame, _ = snapshot.previous_proposal()

    assert manifest is not None and frame is not None
    assert manifest["as_of"] == "2026-09-25" > on_disk["as_of"]
    assert list(frame["ticker"]) == ["MU", "WBD"]


def test_an_empty_store_shows_no_book_and_says_why(stored: Path) -> None:
    """A book that was never proposed is not a book the owner holds."""
    manifest, frame, reason = snapshot.previous_proposal()

    assert manifest is None and frame is None
    assert reason == snapshot.NO_STORED_BOOK
    payload = snapshot.build(
        run={**RUN, "status": "stale_stopped"},
        manifest=manifest,
        book=frame,
        book_reason=reason,
    )
    jsonschema.validate(instance=payload, schema=SCHEMA)
    # the committed proposal is on disk, and none of it reaches the page
    assert (ROOT / "live" / "proposals" / "proposal_2026-09-21.json").exists()
    assert payload["book"]["n_names"] == 0
    assert payload["book"]["names"] == []
    assert payload["book"]["reason"] == snapshot.NO_STORED_BOOK
    assert payload["book_as_of"] is None


def test_a_stored_proposal_with_no_rows_says_so(stored: Path) -> None:
    from live import store

    store.upsert(
        "proposals",
        [{"trade_date": "2026-09-25", "as_of": "2026-09-25", "manifest": "{}"}],
    )

    manifest, frame, reason = snapshot.previous_proposal()

    assert manifest == {}
    assert frame is None
    assert reason == snapshot.STORED_BOOK_HAS_NO_ROWS


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
    # and the book the exposures were taken from is the stored one. The breadth
    # moved from 70.5921 to 96.3664 when the 10% variance-share cap joined the
    # sizing: levelling the few names that carried most of the residual risk raises
    # raises the effective breadth of the book. It moved again, to 94.2573, when
    # the hedge started using the design for the session the book is held over
    # rather than the row dated the close: the two designs differ in the size of
    # the book they produce, not only in the exposures they zero. It moved once
    # more, to 131.9175, when the alpha contract stopped multiplying the specific
    # variance where the specific volatility belongs (S1): the old spelling gave
    # every alpha an extra factor of the name's own volatility, so the book leaned
    # on the volatile names, and the corrected contract spreads the same signal
    # across more of the cross-section. It moved once more, to 150.7020, on the
    # frozen-panel propagation pass: the panel those two corrections are read off
    # gained the corporate-action repairs and lost the reused-ticker series, so
    # the cross-section the same signal spreads over is a different set of names.
    assert manifest["n_eff_kept"] == pytest.approx(150.7020, abs=1e-3)


def test_the_headline_gross_is_the_book_that_trades() -> None:
    """`gross` is the kept book's, and the 499-name book keeps its own name.

    The manifest's `gross` is the full 499-name book after sizing and the cap,
    before the floor - 0.9008 on 2026-09-25 while the book that trades was
    renormalized to exactly 1.0 and $1,000,000. Publishing the first as "the
    gross" told the owner their book was 90% invested when it was fully invested.
    """
    payload = built(
        manifest={
            "gross": 0.9008172332573943,
            "kept_gross": 1.0,
            "notional": 1_000_000.0,
        }
    )

    assert payload["book"]["gross"] == 1.0
    assert payload["book"]["gross_notional"] == 1_000_000.0
    assert payload["book"]["full_book_gross"] == 0.9008172332573943


def test_the_books_net_and_forecast_vol_are_the_traded_books() -> None:
    """The page's unqualified net and forecast vol describe the book it holds.

    The same rule as the gross: the 499-name book keeps its own names beside them.
    A page that showed the 499-name book's forecast volatility as the book's would
    put a number about a book nobody holds on the front of the one they do.
    """
    payload = built(
        manifest={
            "kept_net": -3.3e-16,
            "kept_achieved_annual_vol": 0.0316,
            "net": 0.004,
            "achieved_annual_vol": 0.0246,
        }
    )

    book = payload["book"]
    assert book["net"] == pytest.approx(-3.3e-16)
    assert book["full_book_net"] == pytest.approx(0.004)
    assert book["achieved_annual_vol"] == pytest.approx(0.0316)
    assert book["full_book_achieved_annual_vol"] == pytest.approx(0.0246)
    assert book["achieved_annual_vol"] != book["full_book_achieved_annual_vol"]
    jsonschema.validate(instance=payload, schema=SCHEMA)


def test_a_manifest_without_a_kept_gross_still_states_one() -> None:
    """An older proposal has only the full-book gross, which is what it gets."""
    payload = built(manifest={"gross": 0.9712, "kept_gross": None})

    assert payload["book"]["gross"] == 0.9712
    assert payload["book"]["full_book_gross"] == 0.9712


def test_the_settings_are_checked_before_the_run_rather_than_at_the_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The switch and the four R2 variables, as the start of a run reads them.

    `write_snapshot` makes the same check when the evening is over, which is the
    wrong place to find a missing credential: the book is sized and the orders are
    sent by then, and the page is where the owner sees the book.
    """
    # no switch at all: neither default is safe, so the run cannot start
    monkeypatch.delenv(snapshot.SNAPSHOT_ENV, raising=False)
    with pytest.raises(snapshot.SnapshotNotConfigured):
        snapshot.check_snapshot_config(dry_run=True)

    # off, which a dry run may do, and no credentials are needed for it
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, "off")
    assert snapshot.check_snapshot_config(dry_run=True) == "off"
    # and off on a live run is the flip's own refusal
    with pytest.raises(snapshot.SnapshotNotAllowed):
        snapshot.check_snapshot_config(dry_run=False)

    # on, with the credentials unset: the error names the missing variables
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, "on")
    for name in snapshot.R2_ENVS:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(snapshot.SnapshotNotConfigured) as missing:
        snapshot.check_snapshot_config(dry_run=True)
    assert all(name in str(missing.value) for name in snapshot.R2_ENVS)

    # on, with them set: the mode the writer will use
    for name in snapshot.R2_ENVS:
        monkeypatch.setenv(name, "test-value")
    assert snapshot.check_snapshot_config(dry_run=False) == "on"


class _Body:
    """A get_object body, as boto3 hands one back."""

    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> bytes:
        return self._text.encode()


def _reader(text: str, seen: list[dict[str, Any]] | None = None) -> Any:
    """A get callable answering one object, and recording what it was asked."""

    def get(**kwargs: Any) -> dict[str, Any]:
        if seen is not None:
            seen.append(kwargs)
        return {"Body": _Body(text)}

    return get


def _document(names: list[dict[str, Any]], **book: Any) -> str:
    return json.dumps({"book": {"n_names": len(names), "names": names, **book}})


NAMES_THREE = [{"ticker": ticker, "weight": 0.1} for ticker in ("AAA", "BBB", "CCC")]


def test_the_writer_reads_its_own_object_back_and_counts_the_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The check asks the bucket for the key the page fetches, and counts it."""
    values = _settings(monkeypatch)
    seen: list[dict[str, Any]] = []
    verdict, line = snapshot.check_published_book(
        expected=3, getter=_reader(_document(NAMES_THREE), seen)
    )
    assert verdict == snapshot.PAGE_BOOK_MATCH
    assert line == "", "a book that carries the run's names says nothing"
    assert seen == [{"Bucket": values["EFB_R2_BUCKET"], "Key": snapshot.LATEST_KEY}]


def test_an_empty_published_book_is_reported_against_the_kept_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 2026-10-01 shape: every number right and the list empty."""
    _settings(monkeypatch)
    verdict, line = snapshot.check_published_book(
        expected=188, getter=_reader(_document([]))
    )
    assert verdict == snapshot.PAGE_BOOK_EMPTY
    assert "empty" in line
    assert "188" in line and snapshot.LATEST_KEY in line


def test_a_short_published_book_is_not_called_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A list of the wrong length is its own fact, stated as itself."""
    _settings(monkeypatch)
    verdict, line = snapshot.check_published_book(
        expected=188, getter=_reader(_document(NAMES_THREE[:2]))
    )
    assert verdict == snapshot.PAGE_BOOK_SHORT
    assert "2 of the 188 kept names" in line


def test_a_read_that_cannot_be_made_is_unread_not_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bucket this run cannot read is a bucket to check, not an empty book.

    The line names the exception's type and not its message: a bucket error's text
    can carry the request that was signed, and the document and the message are
    both read by people.
    """

    def refused(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("AccessDenied for bucket efb-snapshots")

    _settings(monkeypatch)
    verdict, line = snapshot.check_published_book(expected=3, getter=refused)
    assert verdict == snapshot.PAGE_BOOK_UNREAD
    assert "RuntimeError" in line
    assert "empty" not in line
    assert "AccessDenied" not in line


def test_the_check_never_raises_on_a_body_that_is_not_a_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A truncated or foreign object is reported, and cannot fail a run."""
    _settings(monkeypatch)
    verdict, line = snapshot.check_published_book(
        expected=3, getter=_reader("<html>sign in</html>")
    )
    assert verdict == snapshot.PAGE_BOOK_UNREAD
    assert line


def test_a_manifest_with_no_kept_count_still_reports_an_empty_book(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An older manifest cannot say what the list should be, but says empty."""
    _settings(monkeypatch)
    empty, empty_line = snapshot.check_published_book(
        expected=None, getter=_reader(_document([]))
    )
    assert empty == snapshot.PAGE_BOOK_EMPTY
    assert empty_line
    carried, carried_line = snapshot.check_published_book(
        expected=None, getter=_reader(_document(NAMES_THREE))
    )
    assert carried == snapshot.PAGE_BOOK_MATCH
    assert carried_line == ""
