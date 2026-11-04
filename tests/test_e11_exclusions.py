"""One name never stops the book, and one line says which names are out.

Every failure since launch was the same shape: one name's data stopped the whole
evening. The SKYD warrant with no price, SKYD.WS read as a spin-off child, CTVA's
vendor restatement, HON's contradicted spin ratio, KVUE's NaN close on a hold day,
KVUE retired at the broker. Each was answered where it was found, with its own list
and its own threshold; these tests pin the one mechanism that now carries them all,
and the one line the owner reads.
"""

from __future__ import annotations

import pytest

from live import exclusions, notify


def _row(ticker: str, reason: str, source: str = "test") -> dict[str, str]:
    return {"ticker": ticker, "reason": reason, "source": source}


def test_the_line_names_every_reader_and_says_each_name_once() -> None:
    """Four readers, one sentence, and a name two of them saw is said once.

    The 2026-11-02 evening is the case: KVUE had no close (prices) and was retired
    at the broker, and saying it twice reads as two problems rather than one.
    """
    rows = exclusions.collect(
        [_row("EFG", "not in the fitted set", "universe")],
        [_row("KVUE", "no usable close at the close", "prices")],
        [_row("KVUE", "the broker reports the asset inactive", "broker")],
        [_row("BE", "no risk estimate", "risk model")],
    )
    assert [row.ticker for row in rows] == ["BE", "EFG", "KVUE"]
    assert rows[2].reason == "no usable close at the close", "the first reader wins"
    sentence = exclusions.sentence(rows)
    assert sentence == (
        "Excluded tonight: BE (no risk estimate), EFG (not in the fitted set), "
        "KVUE (no usable close at the close)."
    )


def test_nothing_out_says_nothing() -> None:
    assert exclusions.sentence(exclusions.collect([], [])) == ""
    assert notify._excluded_tonight_line([]) == ""
    assert notify._excluded_tonight_line(None) == ""


def test_ten_names_out_is_a_night_and_eleven_is_a_broken_input() -> None:
    """The stop is one number, and it is the number the two drops already drew."""
    assert exclusions.MAX_EXCLUSIONS == 10
    ten = [
        exclusions.Exclusion(f"T{i:02d}", "no usable close", "prices")
        for i in range(10)
    ]
    exclusions.guard(ten)  # inside the line: the book trades
    eleven = [*ten, exclusions.Exclusion("T10", "no usable close", "prices")]
    with pytest.raises(exclusions.TooManyExclusions, match="more than the 10"):
        exclusions.guard(eleven)


def test_five_price_drops_and_five_risk_drops_are_one_night_too_many() -> None:
    """The case neither reader sees: each inside its own limit, the night over the line.

    `priced_names_or_stop` and `risk_names_or_stop` each allow ten. A night with six
    names missing a price and six missing a variance is twelve names out of a book of
    a few hundred, and the shared guard is what says the input is the suspect.
    """
    prices = [
        exclusions.Exclusion(f"P{i}", "no usable close", "prices") for i in range(6)
    ]
    risk = [
        exclusions.Exclusion(f"R{i}", "no risk estimate", "risk model")
        for i in range(6)
    ]
    merged = exclusions.collect(prices, risk)
    assert len(merged) == 12
    with pytest.raises(exclusions.TooManyExclusions):
        exclusions.guard(merged)


def test_the_message_carries_one_line_for_every_name_out() -> None:
    """The owner's ask: one sentence, every name, with the reason beside it."""
    body = notify.compose(
        status="ok",
        target_close="2026-11-03",
        dry_run=False,
        excluded=[_row("DD", "symbol reused", "universe")],
        excluded_tonight=[
            _row("DD", "symbol reused", "universe"),
            _row("KVUE", "no usable close at the close", "prices"),
        ],
    )
    assert body.count("Excluded tonight:") == 1
    assert (
        "Excluded tonight: DD (symbol reused), KVUE (no usable close at the close)."
        in body
    )
    # the universe's own line is not printed beside it: same fact, same night
    assert "Excluded from the universe:" not in body


def test_a_manifest_without_the_merged_list_still_says_what_it_knows() -> None:
    """An older manifest has only the universe's list, and that line still prints."""
    body = notify.compose(
        status="ok",
        target_close="2026-10-30",
        dry_run=False,
        excluded=[_row("DD", "symbol reused", "universe")],
    )
    assert "Excluded from the universe:" in body
    assert "Excluded tonight:" not in body
