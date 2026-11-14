"""The stop counts a standing name only when last night did not already list it.

The owner's rule of 2026-11-14: a standing-reason exclusion (no GICS row, no risk
estimate) still counts toward the stop when that name was *not* on the previous
evening's manifest. A name yesterday's manifest already carries, for the same
reason, is yesterday's news and does not count. Matching is per name and per
reason, so the same name out for a different reason tonight is new, and a name
that was not out at all is new.

The three cases the owner asked to see pinned:

- the ten standing names of 2026-11-13 count zero, because the 11-12 manifest
  carried all ten for the same reasons;
- fifty names losing a GICS row in one night stops the run;
- ten standing names plus one newly excluded name does not stop it.

The line the owner reads is unchanged: every name, standing or new, is on it.
"""

from __future__ import annotations

import pytest

from live import exclusions, notify

# The ten names on the 2026-11-13 "Excluded tonight" line, all standing.
STANDING = (
    ("2602335D", "no GICS row", "sectors"),
    ("BE", "no GICS row", "sectors"),
    ("ILMN", "no GICS row", "sectors"),
    ("P", "no GICS row", "sectors"),
    ("FDXF", "no risk estimate", "risk model"),
    ("HONA", "no risk estimate", "risk model"),
    ("OKTA", "no risk estimate", "risk model"),
    ("SKYD", "no risk estimate", "risk model"),
    ("TWLO", "no risk estimate", "risk model"),
    ("VYLR", "no risk estimate", "risk model"),
)


def _standing() -> list[exclusions.Exclusion]:
    return [
        exclusions.Exclusion(ticker, reason, source, transient=False)
        for ticker, reason, source in STANDING
    ]


def _yesterday() -> list[dict[str, object]]:
    """The 11-12 manifest rows: no `transient` flag, which is what it stored."""
    return [
        {"ticker": ticker, "reason": reason, "source": source}
        for ticker, reason, source in STANDING
    ]


def _new(
    ticker: str, reason: str = "no usable close at the close"
) -> exclusions.Exclusion:
    return exclusions.Exclusion(ticker, reason, "prices", transient=True)


def test_the_ten_standing_names_count_zero_when_yesterday_listed_them() -> None:
    """All ten were excluded the previous evening for the same reasons."""
    rows = exclusions.collect(_standing())
    counted = exclusions.novel(rows, _yesterday())
    assert counted == []
    exclusions.guard(rows, previous=_yesterday())  # no raise: nothing new


def test_fifty_names_newly_losing_a_gics_row_in_one_night_stop_the_run() -> None:
    """Standing is not a licence: fifty new no-GICS names are the fetch breaking."""
    newcomers = [
        exclusions.Exclusion(f"G{index:02d}", "no GICS row", "sectors", transient=False)
        for index in range(50)
    ]
    rows = exclusions.collect(_standing(), newcomers)
    counted = exclusions.novel(rows, _yesterday())
    assert len(counted) == 50
    with pytest.raises(exclusions.TooManyExclusions) as raised:
        exclusions.guard(rows, previous=_yesterday())
    message = str(raised.value)
    assert "50 names are newly excluded tonight" in message
    assert "G00" in message
    # And the ten carried-over names are still listed, just not counted.
    aside = "10 more names out for standing reasons are listed but not counted"
    assert aside in message


def test_ten_standing_plus_one_newly_excluded_does_not_stop() -> None:
    """The case the rule exists for: one new name on top of yesterday's ten."""
    rows = exclusions.collect(_standing(), [_new("AAPL")])
    counted = exclusions.novel(rows, _yesterday())
    assert [row.ticker for row in counted] == ["AAPL"]
    exclusions.guard(rows, previous=_yesterday())


def test_the_same_name_for_a_different_reason_is_new() -> None:
    """Matching is per name and per reason, not per name alone."""
    yesterday = [exclusions.Exclusion("BE", "no usable close at the close", "prices")]
    today = [exclusions.Exclusion("BE", "no GICS row", "sectors", transient=False)]
    assert exclusions.novel(today, yesterday) == today


def test_a_name_absent_from_yesterday_is_new() -> None:
    """No row yesterday, standing reason tonight: it counts."""
    today = [
        exclusions.Exclusion("NEWCO", "no risk estimate", "risk model", transient=False)
    ]
    assert exclusions.novel(today, _yesterday()) == today


def test_a_previous_evening_that_cannot_be_read_counts_every_name() -> None:
    """An unreadable yesterday is not evidence that tonight is new, so it stops."""
    rows = exclusions.collect(_standing(), [_new("AAPL")])
    assert len(exclusions.novel(rows, None)) == 11
    with pytest.raises(exclusions.TooManyExclusions):
        exclusions.guard(rows, previous=None)


def test_yesterdays_rows_are_read_through_the_same_reader() -> None:
    """A stored list with or without the flag matches the same way."""
    rows = exclusions.collect(_standing())
    yesterday = exclusions.as_rows(_standing())
    assert exclusions.novel(rows, yesterday) == []
    bare = [
        {"ticker": row["ticker"], "reason": row["reason"], "source": row["source"]}
        for row in yesterday
    ]
    assert exclusions.novel(rows, bare) == []


def test_the_email_line_still_lists_all_of_them() -> None:
    """Standing or new, every name out is named, and the wording is untouched."""
    rows = exclusions.collect(_standing()[:3], [_new("AAPL")])
    body = notify.compose(
        status="ok",
        target_close="2026-11-14",
        dry_run=True,
        excluded_tonight=exclusions.as_rows(rows),
    )
    assert (
        "Excluded tonight: 2602335D (no GICS row), "
        "AAPL (no usable close at the close), BE (no GICS row), "
        "ILMN (no GICS row)." in body
    )
