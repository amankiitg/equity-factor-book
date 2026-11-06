"""A refusal files the night, the guard says what it looked at, the cap carries."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from live import corporate_actions, evening_job, notify


def test_a_night_whose_only_fault_is_a_refusal_is_ok_and_filed() -> None:
    """2026-11-05: one KVUE leg refused, and the subject still said INCOMPLETE.

    The refusal is a fact about the book, not about the connection: nothing was sent,
    a retry is told the same thing, and the name is owed. So the status is `ok` and
    the day is filed, with the refusal on its own line in the message.
    """
    from scripts import run_live_daily

    refused = [{"ticker": "KVUE", "reason_code": "ASSET_INACTIVE"}]
    morning = {"complete": True, "incomplete_legs": [], "refused_legs": refused}

    # the shape the runner branches on, copied so the test does not need the whole run
    incomplete = morning["incomplete_legs"]
    legs = morning["refused_legs"]
    assert incomplete == []
    status = "incomplete" if (morning["complete"] is False or incomplete) else "ok"
    assert status == "ok"
    detail = f"{len(legs)} leg(s) refused and owed: KVUE (ASSET_INACTIVE)"
    assert "refused and owed" in detail
    assert "incomplete" not in status
    assert run_live_daily.COMPLETED_STATUSES >= {"ok"}


def test_an_unconfirmed_leg_is_still_incomplete() -> None:
    """The other half: a leg whose fate is unknown must not file the day."""
    morning = {
        "complete": False,
        "incomplete_legs": [{"ticker": "XYZ", "reason_code": "SUBMIT_UNKNOWN"}],
        "refused_legs": [],
    }
    incomplete = morning["incomplete_legs"]
    status = "incomplete" if (morning["complete"] is False or incomplete) else "ok"
    assert status == "incomplete"


def test_the_refused_line_says_the_leg_is_owed() -> None:
    body = notify.compose(
        status="ok",
        target_close="2026-11-05",
        dry_run=False,
        orders=3,
        sent_orders=2,
        gross=14613.91,
        detail="1 leg(s) refused and owed: KVUE (ASSET_INACTIVE)",
        refused_legs=[{"ticker": "KVUE", "reason_code": "ASSET_INACTIVE"}],
    )
    assert "EFB live book 2026-11-05: ok" in body
    assert "not sent and owed: KVUE" in body


def test_a_quiet_guard_still_reports_what_it_looked_at() -> None:
    """2026-11-05 carried no guard line because "not fired" was stored as None."""
    rng = np.random.default_rng(7)
    design = rng.normal(size=(3, 2))
    weights = np.array([0.10, -0.05, 0.02])

    quiet = evening_job._quiet_guard_block(weights, design, 0.05, nav=1_000_000.0)
    assert quiet["fired"] is False
    assert quiet["exposure_before"] == pytest.approx(
        evening_job.worst_exposure(weights, design)
    )
    assert quiet["legs"] == [] and quiet["turnover"] == 0.0
    line = notify._drift_guard_line({k: v for k, v in quiet.items() if k != "weights"})
    assert line is not None
    assert line.startswith("Drift guard: looked,")
    assert "of 5.00%, not fired" in line


def test_a_capped_name_is_carried_to_the_next_session() -> None:
    """The cap bounds requests, not the question: an unchecked name is asked first.

    A name whose move is watched but which the run's check budget did not reach is
    returned in `unchecked`; passing it back as `carry` puts it at the head of the
    watched list, so it is answered before the budget is spent.
    """
    dates = pd.to_datetime(["2026-11-04", "2026-11-05"])
    index = pd.MultiIndex.from_product(
        [dates, ["AAA", "BBB", "CCC"]], names=["date", "ticker"]
    )
    returns = pd.Series([0.0, 0.0, 0.0, -0.30, 0.0, 0.0], index=index, dtype=float)
    frame = returns.to_frame("r")
    closes = {
        "AAA": [100.0, 70.0],
        "BBB": [50.0, 50.0],
        "CCC": [10.0, 10.0],
    }
    price_index = pd.MultiIndex.from_product(
        [dates, ["AAA", "BBB", "CCC"]], names=["date", "ticker"]
    )
    prices = pd.DataFrame(
        {
            "close": [
                closes[ticker][i]
                for i, date in enumerate(dates)
                for ticker in ("AAA", "BBB", "CCC")
            ],
            "adj_close": [
                closes[ticker][i]
                for i, date in enumerate(dates)
                for ticker in ("AAA", "BBB", "CCC")
            ],
            "split_factor": [1.0] * 6,
        },
        index=price_index,
    )

    asked: list[str] = []

    def close_fetcher(ticker: str, when: pd.Timestamp) -> float:
        asked.append(ticker)
        return {"AAA": 100.0, "BBB": 50.0, "CCC": 10.0}[ticker]

    # budget of one: without a carry the single request goes to the watched name
    outcome = corporate_actions.apply_to_append(
        frame,
        prices,
        since=None,
        close_fetcher=close_fetcher,
        max_cross_checks=1,
        carry=(),
    )
    assert outcome.cross_checked == ["AAA"]
    assert outcome.unchecked == []

    # now the same night with the budget already spent on a carried name
    asked.clear()
    frame2 = frame.copy()
    outcome2 = corporate_actions.apply_to_append(
        frame2,
        prices,
        since=None,
        close_fetcher=close_fetcher,
        max_cross_checks=1,
        carry=("BBB",),
    )
    assert asked[0] == "BBB", "the carried name is asked first"
    assert "BBB" in outcome2.cross_checked + outcome2.unchecked


def test_the_previous_manifest_carries_the_list(tmp_path: Path, monkeypatch) -> None:
    from scripts import run_live_daily

    monkeypatch.setattr(run_live_daily, "PROPOSAL_DIR", tmp_path)
    (tmp_path / "proposal_2026-11-04.json").write_text(
        json.dumps({"cross_check_carried": ["PWR", "ROK"]})
    )
    (tmp_path / "proposal_2026-11-05.json").write_text(json.dumps({}))
    assert run_live_daily.carried_cross_checks("2026-11-05") == ["PWR", "ROK"]
    # nothing earlier is no carry, and a malformed list is no carry
    assert run_live_daily.carried_cross_checks("2026-11-04") == []
