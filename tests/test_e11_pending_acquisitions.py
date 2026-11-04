"""The takeover warning: a held name's announced merger, said before it completes.

KVUE's deal was public for weeks. The evening learned about it on the day the asset
went inactive, from a 404 and a NaN close. This is the read that would have said so
earlier - one request, held symbols only, no trading change - and the one line it
puts in the mail.
"""

from __future__ import annotations

from typing import Any

from live import alpaca, notify


class _SubType:
    def __init__(self, value: str) -> None:
        self.value = value


class _Record:
    def __init__(
        self,
        target: str,
        acquirer: str = "",
        subtype: str = "merger_update",
        cash: float = 0.0,
        new_rate: float = 0.0,
    ) -> None:
        self.target_symbol = target
        self.initiating_symbol = acquirer
        self.ca_sub_type = _SubType(subtype)
        self.cash = cash
        self.new_rate = new_rate


class _Client:
    def __init__(self, records: list[_Record], fail: bool = False) -> None:
        self.records = records
        self.fail = fail
        self.calls = 0

    def get_corporate_announcements(self, request: Any = None) -> list[_Record]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("the feed is down")
        return list(self.records)


def test_a_held_target_with_an_announced_deal_is_named_with_its_terms() -> None:
    """The KVUE shape, one step earlier: the update record, before the completion."""
    client = _Client(
        [
            _Record("KVUE", "KMB", "merger_update", cash=3.50, new_rate=0.14625),
            _Record("OTHER", "NOPE", "merger_update"),
        ]
    )
    rows = alpaca.pending_acquisitions(["KVUE", "AAPL"], client=client)
    assert rows == [
        {
            "target": "KVUE",
            "acquirer": "KMB",
            "subtype": "merger_update",
            "terms": "0.14625 acquirer shares a share plus $3.50 a share in cash",
        }
    ]
    assert notify._pending_acquisition_lines(rows) == [
        "Pending acquisition: KVUE by KMB "
        "(0.14625 acquirer shares a share plus $3.50 a share in cash)."
    ]


def test_a_completion_is_not_pending() -> None:
    """The day it is done, the line is gone; the exclusion line takes over."""
    client = _Client([_Record("KVUE", "KMB", "merger_completion")])
    assert alpaca.pending_acquisitions(["KVUE"], client=client) == []


def test_the_terms_are_left_out_when_the_record_has_none() -> None:
    """The broker's KVUE record carried cash 0.0 and new_rate 0.0, so say so."""
    client = _Client([_Record("KVUE", "KMB", "merger_update")])
    rows = alpaca.pending_acquisitions(["KVUE"], client=client)
    assert rows[0]["terms"] == ""
    assert notify._pending_acquisition_lines(rows) == [
        "Pending acquisition: KVUE by KMB (terms not published)."
    ]


def test_an_acquiring_holding_is_named_too() -> None:
    """The book can hold the buyer: KMB was held while it was buying Kenvue."""
    client = _Client([_Record("KVUE", "KMB", "merger_update")])
    rows = alpaca.pending_acquisitions(["KMB"], client=client)
    assert [row["acquirer"] for row in rows] == ["KMB"]


def test_one_read_per_run_and_no_line_without_a_holding() -> None:
    client = _Client([_Record("KVUE", "KMB")])
    assert alpaca.pending_acquisitions(["AAPL", "MSFT"], client=client) == []
    assert client.calls == 1
    cache: dict[str, Any] = {}
    alpaca.pending_acquisitions(["KVUE"], client=client, cache=cache)
    alpaca.pending_acquisitions(["KVUE"], client=client, cache=cache)
    assert client.calls == 2, "the second call reuses the first's read"


def test_a_feed_that_fails_says_nothing_and_stops_nothing() -> None:
    """A note, never a step: no line, no exception, the evening goes on."""
    client = _Client([], fail=True)
    assert alpaca.pending_acquisitions(["KVUE"], client=client) == []
    body = notify.compose(
        status="ok", target_close="2026-11-03", dry_run=False, pending_acquisitions=[]
    )
    assert "Pending acquisition:" not in body


def test_the_line_sits_beside_the_exclusions_without_replacing_them() -> None:
    body = notify.compose(
        status="ok",
        target_close="2026-11-03",
        dry_run=False,
        pending_acquisitions=[
            {
                "target": "KVUE",
                "acquirer": "KMB",
                "subtype": "merger_update",
                "terms": "",
            }
        ],
        excluded_tonight=[
            {
                "ticker": "WBD",
                "reason": "no usable close at the close",
                "source": "prices",
            }
        ],
    )
    assert "Pending acquisition: KVUE by KMB (terms not published)." in body
    assert "Excluded tonight: WBD (no usable close at the close)." in body
    assert body.index("Pending acquisition:") < body.index("Excluded tonight:")
