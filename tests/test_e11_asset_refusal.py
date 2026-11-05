"""A retired asset's rejection is a refusal, and the close files.

2026-11-04, the real values: the evening built 196 legs, 139 of them drift-guard
legs, and one KVUE `sell_to_close` of $13,615.45 that the broker answered

    APIError: {"code":40010001,"message":"asset KVUE is not active"}

The order never existed (the broker assigned no id), so nothing could fill and
nothing could be duplicated - but the run recorded the leg as ALPACA_API_ERROR,
`_leg_incomplete` counted that as *not confirmed*, the close was left unfiled, and
the job kept reporting an error. A definitive 4xx that says the security cannot be
traded is a refusal that files the close; only transport uncertainty is "not
confirmed".
"""

from __future__ import annotations

import pandas as pd
import pytest

from live import alpaca, evening_job, morning_job, notify

KVUE_MESSAGE = 'APIError: {"code":40010001,"message":"asset KVUE is not active"}'


class _APIError(Exception):
    """What alpaca-py raises for a 4xx: the message carries the broker's body."""


@pytest.fixture(autouse=True)
def _api_error_class(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(alpaca, "API_ERROR_CLS", _APIError)


def test_the_brokers_own_words_are_classified_as_a_definitive_refusal() -> None:
    code, halts = alpaca.classify_submit_failure(_APIError(KVUE_MESSAGE))
    assert code == alpaca.REASON_ASSET_INACTIVE
    assert halts is False, "a refusal does not halt the rest of the book"


def test_a_refusal_files_the_close_and_an_uncertainty_does_not() -> None:
    """The difference the whole night turned on."""
    assert morning_job._leg_incomplete("SKIPPED", alpaca.REASON_ASSET_INACTIVE) is False
    assert morning_job._leg_incomplete("SKIPPED", alpaca.REASON_NOT_TRADABLE) is False
    # the old classification, for a 4xx that says nothing about the security
    assert morning_job._leg_incomplete("SKIPPED", alpaca.REASON_ALPACA_ERROR) is True
    # and genuine transport uncertainty is still uncertainty
    assert morning_job._leg_incomplete("SKIPPED", alpaca.REASON_SUBMIT_UNKNOWN) is True


def test_a_4xx_that_is_not_about_the_asset_stays_a_plain_broker_refusal() -> None:
    code, halts = alpaca.classify_submit_failure(
        _APIError('{"code":40310000,"message":"insufficient buying power"}')
    )
    assert code == alpaca.REASON_ALPACA_ERROR
    assert halts is False


def test_tonights_close_files_and_the_other_legs_are_untouched() -> None:
    """196 legs, KVUE refused, the rest as they were, and the day is done."""
    from live import exclusions

    legs = pd.DataFrame(
        {
            "trade_date": [pd.Timestamp("2026-11-04")] * 3,
            "ticker": ["AAPL", "KVUE", "MSFT"],
            "intended_notional": [1_000.0, -13_615.454307, -2_000.0],
            "filled_notional": [0.0, 0.0, 0.0],
            "status": ["ACCEPTED", "SKIPPED", "ACCEPTED"],
            "reason_code": ["", alpaca.REASON_ASSET_INACTIVE, ""],
            "broker_order_id": ["b1", "", "b2"],
        }
    )
    incomplete = morning_job.incomplete_legs(legs)
    refused = morning_job.refused_legs(legs)
    assert [row["ticker"] for row in incomplete] == [], "nothing is unconfirmed"
    assert [row["ticker"] for row in refused] == ["KVUE"]
    # the two accepted legs keep their own record
    assert set(legs.loc[legs["status"] == "ACCEPTED", "ticker"]) == {"AAPL", "MSFT"}

    # owed, and never carried to the next evening
    carried, unreachable = evening_job.carried_forward(
        legs[["trade_date", "ticker", "intended_notional", "reason_code"]],
        None,
        pd.DataFrame({"ticker": ["AAPL", "KVUE", "MSFT"], "weight": [0.001, -0.014, -0.002]}),
        None,
        as_of=pd.Timestamp("2026-11-05"),
        minimum=250.0,
    )
    assert carried == {}
    assert [row["ticker"] for row in unreachable] == ["KVUE"]

    body = notify.compose(
        status="ok",
        target_close="2026-11-04",
        dry_run=False,
        refused_legs=refused,
        excluded_tonight=[
            {"ticker": "KVUE", "reason": "the broker reports the asset inactive", "source": "broker"}
        ],
        unconfirmed_legs=0,
    )
    assert "not confirmed" not in body
    assert "Excluded tonight: KVUE (the broker reports the asset inactive)." in body
    assert "Refused by the broker, so not sent: KVUE (ASSET_INACTIVE)" in body
    # the exclusions line and the refusal line are the same fact told once each way
    assert exclusions.sentence(
        [exclusions.Exclusion("KVUE", "the broker reports the asset inactive", "broker")]
    ) in body


def test_a_feed_that_cannot_be_read_is_a_name_by_name_check_with_a_visible_reason() -> None:
    """The degraded mode says so, in the mail and in the manifest's own record."""
    summary = {
        "feed": "unreadable",
        "reason": "ValidationError: 10 validation errors for list[Asset]",
        "checked_one_by_one": 196,
    }
    assert notify._asset_check_line(summary) == (
        "Broker asset list unreadable tonight (ValidationError: 10 validation errors "
        "for list[Asset]); 196 names checked one by one."
    )
    body = notify.compose(
        status="ok", target_close="2026-11-04", dry_run=False, asset_check=summary
    )
    assert "Broker asset list unreadable tonight" in body
    # a healthy check prints nothing at all
    assert notify._asset_check_line({"feed": "ok", "reason": "", "checked_one_by_one": 0}) == ""
    assert "Broker asset list unreadable" not in notify.compose(
        status="ok",
        target_close="2026-11-04",
        dry_run=False,
        asset_check={"feed": "ok", "reason": "", "checked_one_by_one": 0},
    )
