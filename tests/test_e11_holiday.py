"""Sprint E11 pre-flip, item 2: a shut exchange is a message, not a run.

The cron schedule is "30 22 * * 1-5", so it fires on weekday holidays. There is
no close to price on those days, so the run does nothing at all: no seed
download, no extension, no gate, no book. The owner is told, because silence is
the alarm for a run that never started, and the day is recorded so a re-fire does
not send a second message.

`is_session` asks the NYSE calendar rather than a weekday test, and the closure
list below is the calendar's own 2026 answer, so a calendar that changes its mind
is visible here.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from live import notify, staleness, store
from scripts import run_live_daily

# Every 2026 weekday on which the NYSE does not open, read from
# `pandas_market_calendars` on 2026-09-26.
CLOSURES_2026 = [
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # Martin Luther King Jr. Day
    "2026-02-16",  # Washington's Birthday
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-06-19",  # Juneteenth
    "2026-07-03",  # Independence Day observed (the 4th is a Saturday)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving
    "2026-12-25",  # Christmas
]


def _fail_on_call(message: str):
    def _raise(*args, **kwargs):
        raise AssertionError(message)

    return _raise


def test_the_calendar_answers_and_the_2026_closures_are_the_ten_known_ones() -> None:
    weekdays = pd.date_range("2026-01-01", "2026-12-31", freq="B")
    found = [str(day.date()) for day in weekdays if not staleness.is_session(day)]
    assert found == CLOSURES_2026
    for day in CLOSURES_2026:
        assert staleness.is_session(day) is False
    # The negative controls: the Friday after Thanksgiving is a session, and a
    # weekend is not (the cron never fires at the weekend, but the answer matters).
    assert staleness.is_session("2026-11-27") is True
    assert staleness.is_session("2026-09-26") is False  # a Saturday
    assert staleness.is_session("2026-09-25") is True


def test_the_message_says_the_market_was_closed() -> None:
    message = notify.compose(
        status="market_closed",
        target_close="2026-11-26",
        dry_run=True,
        detail="there is no NYSE session on 2026-11-26",
        store="postgres/efb",
    )
    lines = message.splitlines()
    assert lines[1] == (
        "EFB live book 2026-11-26: market_closed, the exchange was shut"
    )
    assert "Orders: none. The exchange was shut" in message
    assert "Market: closed, there is no NYSE session on 2026-11-26." in message
    assert "0 orders" not in message
    subject = notify.subject_text(status="market_closed", target_close="2026-11-26")
    assert subject == "EFB CLOSED 2026-11-26 | none proposed | market closed"


def _pin_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[dict]:
    """A closed day, a local store, and the message captured instead of sent."""
    from live import runroot

    monkeypatch.setattr(staleness, "is_session", lambda day: False)
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    monkeypatch.setattr(run_live_daily, "already_ran", lambda job, day: False)
    # The run must not even look for a seed: if it does, this fails loudly rather
    # than downloading 600 MB on a day there is nothing to do.
    monkeypatch.setattr(
        runroot, "prepare", _fail_on_call("the seed was fetched on a closed day")
    )
    monkeypatch.setenv(notify.API_KEY_ENV, "re_" + "test-key-value")
    monkeypatch.setenv(notify.TO_ENV, "owner@example.com")
    sent: list[dict] = []
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent.append(payload)
    )
    return sent


def test_a_closed_day_sends_one_message_and_writes_no_book(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _pin_closed(monkeypatch, tmp_path)

    assert run_live_daily.main() == 0

    assert len(sent) == 1
    assert "market_closed" in str(sent[0]["text"])
    assert "there is no NYSE session" in str(sent[0]["text"])
    assert str(sent[0]["subject"]).startswith("EFB CLOSED")
    # Nothing was priced and nothing was written but the day's own record.
    assert store.select("proposals").empty
    assert store.select("orders").empty
    assert store.select("run_status").empty
    runs = store.select("cron_runs")
    assert len(runs) == 1
    assert runs.iloc[0]["status"] == "market_closed"
    assert runs.iloc[0]["job"] == "live_daily"


def test_a_refire_of_a_closed_day_sends_nothing_second(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cron retries on Render; a retry must not repeat the message."""
    recorded = run_live_daily.already_ran
    sent = _pin_closed(monkeypatch, tmp_path)
    assert run_live_daily.main() == 0
    assert len(sent) == 1

    # Put the real check back: the day is now recorded, so it must say so.
    monkeypatch.setattr(run_live_daily, "already_ran", recorded)
    sent_again: list[dict] = []
    monkeypatch.setattr(
        notify, "post", lambda url, payload, headers=None: sent_again.append(payload)
    )
    assert run_live_daily.main() == 0
    assert sent_again == []
    assert len(store.select("cron_runs")) == 1


def test_a_closed_day_still_says_so_when_the_store_is_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The message matters more than the record: a dead store is not a silence."""
    sent = _pin_closed(monkeypatch, tmp_path)
    monkeypatch.setattr(
        run_live_daily, "already_ran", _fail_on_call("the store was consulted")
    )
    monkeypatch.setattr(store, "store_label", _fail_on_call("the store label was read"))
    monkeypatch.setattr(
        run_live_daily, "record_run", _fail_on_call("the day was recorded")
    )

    assert run_live_daily.main() == 0

    assert len(sent) == 1
    assert "no store configured" in str(sent[0]["text"])
