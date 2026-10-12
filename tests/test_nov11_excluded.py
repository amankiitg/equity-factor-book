"""An excluded name carries its reason and its age, and the message says both."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from live import evening_job, notify


def test_the_three_causes_are_told_apart() -> None:
    # The runbook's own three groups: BE/ILMN/P have no GICS row and do have prices,
    # SKYD/TWLO/VYLR have neither, and DD is mapped and priced but absent from the
    # processed returns panel.
    assert (
        evening_job.exclusion_reason(
            "BE", in_sectors=False, in_returns=False, in_prices=True
        )
        == "no GICS row"
    )
    assert (
        evening_job.exclusion_reason(
            "SKYD", in_sectors=False, in_returns=False, in_prices=False
        )
        == "no GICS row and no price rows"
    )
    assert (
        evening_job.exclusion_reason(
            "DD", in_sectors=True, in_returns=False, in_prices=True
        )
        == "in the sectors file but absent from the processed returns panel"
    )


def test_the_age_is_the_trailing_run_of_stored_manifests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from live import store

    frame = pd.DataFrame(
        [
            {
                "trade_date": "2026-09-25",
                "manifest": json.dumps({"as_of": "2026-09-25", "excluded": ["BE"]}),
            },
            {
                "trade_date": "2026-09-29",
                "manifest": json.dumps(
                    {"as_of": "2026-09-29", "excluded": ["BE", "SKYD"]}
                ),
            },
            {
                "trade_date": "2026-10-01",
                "manifest": json.dumps(
                    {"as_of": "2026-10-01", "excluded": ["BE", "SKYD", "VYLR"]}
                ),
            },
        ]
    )
    monkeypatch.setattr(store, "select", lambda table: frame)
    history = evening_job.excluded_history("2026-10-09")
    assert history["BE"] == {
        "stored_sessions": 3,
        "since": "2026-09-25",
        "current": True,
    }
    # VYLR arrived on the newest manifest, so its run is one, not three.
    assert history["VYLR"] == {
        "stored_sessions": 1,
        "since": "2026-10-01",
        "current": True,
    }


def test_a_name_that_left_the_list_starts_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from live import store

    frame = pd.DataFrame(
        [
            {
                "trade_date": "2026-09-25",
                "manifest": json.dumps(
                    {"as_of": "2026-09-25", "excluded": ["BE", "ZZZ"]}
                ),
            },
            {
                "trade_date": "2026-09-29",
                "manifest": json.dumps({"as_of": "2026-09-29", "excluded": ["BE"]}),
            },
            {
                "trade_date": "2026-10-01",
                "manifest": json.dumps(
                    {"as_of": "2026-10-01", "excluded": ["BE", "ZZZ"]}
                ),
            },
        ]
    )
    monkeypatch.setattr(store, "select", lambda table: frame)
    history = evening_job.excluded_history("2026-10-09")
    assert history["ZZZ"]["stored_sessions"] == 1
    assert history["ZZZ"]["since"] == "2026-10-01"
    assert history["BE"]["stored_sessions"] == 3


def test_a_store_that_cannot_be_read_publishes_no_age(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from live import store

    def broken(table: str) -> Any:
        raise RuntimeError("no store")

    monkeypatch.setattr(store, "select", broken)
    # `None` is "the store could not be read", which is not the same answer as an
    # empty history: an empty history is a read that found no exclusions.
    assert evening_job.excluded_history("2026-10-09") is None
    details = evening_job.exclusion_details(
        ["BE"],
        in_sectors=set(),
        in_returns=set(),
        in_prices={"BE"},
        history=None,
        as_of="2026-10-09",
    )
    # The reason survives; the age is an absence rather than a nought.
    assert details[0]["reason"] == "no GICS row"
    assert details[0]["sessions"] is None
    assert details[0]["since"] is None


def test_tonight_is_counted_in_the_age() -> None:
    details = evening_job.exclusion_details(
        ["BE", "NEW"],
        in_sectors={"NEW"},
        in_returns=set(),
        in_prices={"BE", "NEW"},
        history={"BE": {"stored_sessions": 8, "since": "2026-09-25", "current": True}},
        as_of="2026-10-09",
    )
    by_ticker = {str(row["ticker"]): row for row in details}
    assert by_ticker["BE"]["sessions"] == 9
    assert by_ticker["BE"]["since"] == "2026-09-25"
    assert by_ticker["NEW"]["sessions"] == 1
    assert by_ticker["NEW"]["since"] == "2026-10-09"


def test_the_message_names_each_one_with_its_reason_and_age() -> None:
    message = notify.compose(
        status="ok",
        target_close="2026-10-09",
        dry_run=False,
        orders=193,
        sent_orders=171,
        gross=388_402.25,
        excluded=[
            {
                "ticker": "BE",
                "reason": "no GICS row",
                "sessions": 9,
                "since": "2026-09-25",
            },
            {
                "ticker": "DD",
                "reason": evening_job.EXCLUDED_NO_RETURNS,
                "sessions": None,
                "since": None,
            },
        ],
        store="postgres/efb",
    )
    line = next(text for text in message.splitlines() if text.startswith("Excluded"))
    assert "BE (no GICS row, 9 stored session(s) since 2026-09-25)" in line
    assert (
        "DD (in the sectors file but absent from the processed returns panel)" in line
    )
    # No invented age for the one whose store could not be read.
    assert "DD (0 " not in line


def test_the_manifest_carries_the_details(tmp_path: Path) -> None:
    # The manifest key is what the message and any later reader of the day see, and
    # the plain list stays exactly as it was for everything downstream.
    manifest = evening_job.build_proposal(
        data_root=Path("data"),
        as_of=pd.Timestamp("2026-09-21"),
        store=False,
    )
    assert manifest["excluded"] == [str(name) for name in manifest["excluded"]]
    assert manifest["n_excluded"] == len(manifest["excluded"])
    details = manifest["excluded_detail"]
    assert len(details) == manifest["n_excluded"]
    for row in details:
        assert str(row["ticker"]) in manifest["excluded"]
        assert row["reason"] in (
            evening_job.EXCLUDED_NO_GICS,
            evening_job.EXCLUDED_NO_GICS_NO_PRICES,
            evening_job.EXCLUDED_NO_RETURNS,
        )
