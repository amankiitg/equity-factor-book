"""Week 1, item 2: a short needs both flags, and a refused short is named.

The rule is shortable **and** easy_to_borrow. The reason it is not shortable
alone: `shortable` says the name *can* be sold short, `easy_to_borrow` says the
shares are actually there to borrow, and a short opened on the first flag alone
is a short that gets bought in. So the second flag is a gate on every
`sell_to_open`, the skip is recorded with the code that names it, the message
says which name and how much of it went unopened, and the day is complete: the
evening did what it should have, and the next evening's delta tries the name
again because it is still in the target book.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from live import alpaca, morning_job, notify

SESSION = "2026-10-01"


class _Asset:
    """The three flags the broker reports, and nothing else."""

    def __init__(
        self, *, tradable: bool, shortable: bool, easy_to_borrow: bool
    ) -> None:
        self.tradable = tradable
        self.shortable = shortable
        self.easy_to_borrow = easy_to_borrow


class _Client:
    """A client that answers `get_asset` and would know if it were asked to trade."""

    def __init__(self, flags: dict[str, _Asset]) -> None:
        self._flags = flags
        self.submitted: list[Any] = []

    def get_asset(self, symbol: str) -> _Asset:
        return self._flags[symbol]

    def submit_order(self, request: object) -> object:  # pragma: no cover - a guard
        self.submitted.append(request)
        raise AssertionError("no order may be sent in these tests")


def _flag_rows(codes: list[str]) -> pd.DataFrame:
    """Execution rows, as `submit_orders` records them for refused legs."""
    return pd.DataFrame(
        [
            {
                "ticker": f"AA{index:02d}",
                "intended_notional": -4100.0 - index,
                "filled_notional": 0.0,
                "status": alpaca.SKIPPED,
                "reason": f"AA{index:02d} reports easy_to_borrow=false",
                "reason_code": code,
                "client_order_id": "",
                "position_intent": alpaca.INTENT_SELL_TO_OPEN,
                "broker_order_id": "",
            }
            for index, code in enumerate(codes)
        ]
    )


def test_a_short_needs_easy_to_borrow_not_only_shortable() -> None:
    """The whole of the rule: shortable is necessary and not sufficient.

    The negative control is in the same test, and it is the case that matters: a
    name the broker calls shortable but not easy to borrow is refused, so a
    version of this that checked `shortable` alone would fail here.
    """
    client = _Client(
        {
            "NWSA": _Asset(tradable=True, shortable=True, easy_to_borrow=False),
            "DG": _Asset(tradable=True, shortable=True, easy_to_borrow=True),
        }
    )

    refusal = alpaca.short_refusal(client, "NWSA")
    assert refusal is not None
    code, detail = refusal
    assert code == alpaca.REASON_NOT_EASY_TO_BORROW
    assert detail == "NWSA reports easy_to_borrow=false"

    # the name that is both flags passes the same gate
    assert alpaca.short_refusal(client, "DG") is None


@pytest.mark.parametrize(
    ("flags", "code"),
    [
        (
            {"tradable": False, "shortable": True, "easy_to_borrow": True},
            "NOT_TRADABLE",
        ),
        (
            {"tradable": True, "shortable": False, "easy_to_borrow": True},
            "NOT_SHORTABLE",
        ),
        (
            {"tradable": True, "shortable": True, "easy_to_borrow": False},
            "NOT_EASY_TO_BORROW",
        ),
    ],
)
def test_the_code_names_the_first_thing_that_is_wrong(
    flags: dict[str, bool], code: str
) -> None:
    """Three refusals, three codes: the code is what the reader acts on."""
    client = _Client({"CTVA": _Asset(**flags)})
    refusal = alpaca.short_refusal(client, "CTVA")
    assert refusal is not None
    assert refusal[0] == f"ASSET_{code}"


def test_a_borrow_skip_does_not_make_the_run_incomplete() -> None:
    """Skipped, not incomplete: the day is filed and the leg is named.

    An incomplete day is not filed and the next tick retries it. A name whose
    borrow is not there would be retried every tick to the same answer, and the
    evening would never be recorded as done, so the borrow skip is an expected
    skip -- while a name that is not tradable or not shortable stays a data
    problem that must not be filed.
    """
    records = _flag_rows([alpaca.REASON_NOT_EASY_TO_BORROW])
    assert morning_job.incomplete_legs(records) == []

    # the negative control: the same leg, refused for a reason that is not a skip
    for code in (alpaca.REASON_NOT_TRADABLE, alpaca.REASON_NOT_SHORTABLE):
        assert morning_job.incomplete_legs(_flag_rows([code])), code


def test_the_refused_short_is_recorded_and_reported_by_name() -> None:
    """The name, the size of the leg, and the broker's own sentence."""
    records = _flag_rows([alpaca.REASON_NOT_EASY_TO_BORROW])
    skips = morning_job.borrow_skips(records)

    assert [row["ticker"] for row in skips] == ["AA00"]
    assert float(skips[0]["intended_notional"]) == -4100.0
    assert skips[0]["reason_code"] == alpaca.REASON_NOT_EASY_TO_BORROW

    message = notify.compose(
        status="ok",
        target_close=SESSION,
        dry_run=False,
        orders=1,
        gross=0.0,
        store="postgres/efb",
        skipped_borrow=skips,
    )
    assert (
        "Not easy to borrow, so not opened: AA00 $4,100 "
        "(AA00 reports easy_to_borrow=false)." in message
    )


def test_a_run_with_no_borrow_skip_says_nothing_about_one() -> None:
    """The line is evidence, not boilerplate: an ordinary evening has none."""
    message = notify.compose(
        status="ok",
        target_close=SESSION,
        dry_run=False,
        orders=1,
        gross=1000.0,
        store="postgres/efb",
        skipped_borrow=[],
    )
    assert "borrow" not in message
    assert "Orders: 1 orders sent" in message


def test_an_incomplete_message_says_the_orders_went_out_and_names_the_leg() -> None:
    """An incomplete day traded: the message must not deny it.

    Before this, an incomplete run's line read "Orders: none. The run failed
    before sizing, so no book was priced" -- on a day that had priced a book and
    sent twelve orders, with the legs named nowhere in the message at all. The
    owner's next move after reading it is wrong either way.
    """
    message = notify.compose(
        status="incomplete",
        target_close=SESSION,
        dry_run=False,
        orders=12,
        gross=350000.0,
        detail="1 leg(s) not confirmed: DG (ASSET_NOT_EASY_TO_BORROW)",
        store="postgres/efb",
    )
    assert "Orders: 12 orders sent, $350,000 gross, at least one leg not confirmed" in (
        message
    )
    assert "1 leg(s) not confirmed: DG (ASSET_NOT_EASY_TO_BORROW)." in message
    assert "failed before sizing" not in message
