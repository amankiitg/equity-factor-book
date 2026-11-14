"""The stop counts tonight's new exclusions, not the standing ones.

2026-11-13 carried ten names on the "Excluded tonight" line and every one of them
was a standing fact: four with no GICS row (2602335D, BE, ILMN, P, the last three
the hold-list parked until 2026-11-24) and six with no risk estimate yet (FDXF,
HONA, OKTA, SKYD, TWLO, VYLR). Ten is the line, so the night ran. One new name on
any of the evenings that followed would have made eleven and stopped the run,
including the 2026-11-23 rebalance.

These tests pin the rule the owner asked for: a standing reason is listed and kept
but is not counted toward the stop; a new reason is counted. The line the owner
reads does not change at all.
"""

from __future__ import annotations

import pytest

from live import exclusions, notify

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


def _new(
    ticker: str, reason: str = "no usable close at the close"
) -> exclusions.Exclusion:
    return exclusions.Exclusion(ticker, reason, "prices", transient=True)


def test_ten_standing_exclusions_plus_one_new_name_does_not_stop_the_run() -> None:
    """The 2026-11-13 line plus one new name: the evening still trades."""
    rows = exclusions.collect(_standing(), [_new("AAPL")])
    assert len(rows) == 11
    assert len([row for row in rows if row.transient]) == 1
    exclusions.guard(rows)  # no raise: one new name is one new name


def test_eleven_new_exclusions_still_stops_the_run() -> None:
    """The other side: eleven names out is the fetch having broken, not the market."""
    rows = exclusions.collect([_new(f"T{index:02d}") for index in range(11)])
    assert len(rows) == 11
    with pytest.raises(exclusions.TooManyExclusions, match="more than the 10"):
        exclusions.guard(rows)


def test_ten_standing_exclusions_do_not_stop_the_run_on_their_own() -> None:
    """The line as 2026-11-13 actually was: ten standing names, nothing new."""
    rows = exclusions.collect(_standing())
    assert len(rows) == 10
    assert not any(row.transient for row in rows)
    exclusions.guard(rows)


def test_standing_names_still_appear_in_the_email_line() -> None:
    """The line is unchanged: every name out is named, standing or new."""
    rows = exclusions.collect(_standing()[:3], [_new("AAPL")])
    body = notify.compose(
        status="ok",
        target_close="2026-11-14",
        dry_run=True,
        excluded_tonight=exclusions.as_rows(rows),
    )
    assert body.count("Excluded tonight:") == 1
    assert (
        "Excluded tonight: 2602335D (no GICS row), "
        "AAPL (no usable close at the close), BE (no GICS row), "
        "ILMN (no GICS row)." in body
    )


def test_the_full_line_keeps_its_own_display_cap() -> None:
    """Ten standing names and one new one read exactly as they read today."""
    rows = exclusions.collect(_standing(), [_new("AAPL")])
    line = notify._excluded_tonight_line(exclusions.as_rows(rows))
    assert "Excluded tonight:" in line
    assert "BE (no GICS row)" in line
    assert line.endswith("; and 3 more.")
    # The classification is not part of the sentence: the same rows without the
    # flag produce the same string, so the line the owner reads has not changed.
    unclassified = [
        {"ticker": row.ticker, "reason": row.reason, "source": row.source}
        for row in rows
    ]
    assert notify._excluded_tonight_line(unclassified) == line


def test_a_row_that_does_not_say_which_it_is_counts() -> None:
    """A reader that cannot classify is treated as a new fault, not a standing one."""
    rows = exclusions.collect(
        [
            {"ticker": f"T{index:02d}", "reason": "something new"}
            for index in range(11)
        ]
    )
    assert all(row.transient for row in rows)
    with pytest.raises(exclusions.TooManyExclusions):
        exclusions.guard(rows)


def test_the_classification_survives_the_manifest_round_trip() -> None:
    """`as_rows` writes the flag and `collect` reads it back, so a stored list
    suppresses the stop the same way the live list did."""
    rows = exclusions.collect(_standing(), [_new("AAPL")])
    stored = exclusions.as_rows(rows)
    assert {row["ticker"]: row["transient"] for row in stored}["BE"] is False
    assert {row["ticker"]: row["transient"] for row in stored}["AAPL"] is True
    again = exclusions.collect(stored)
    assert [(row.ticker, row.transient) for row in again] == [
        (row.ticker, row.transient) for row in rows
    ]
    exclusions.guard(again)
    # And the stored list still carries every name, standing and new.
    assert len(again) == 11


def test_the_stop_names_only_the_new_names() -> None:
    """The message names the new names, and says how many standing ones are aside."""
    new = [_new(f"N{index:02d}") for index in range(11)]
    rows = exclusions.collect(_standing(), new)
    with pytest.raises(exclusions.TooManyExclusions) as raised:
        exclusions.guard(rows)
    message = str(raised.value)
    assert "11 names are newly excluded tonight" in message
    assert "N00" in message
    assert "BE" not in message
    assert (
        "10 more names out for standing reasons are listed but not counted" in message
    )
