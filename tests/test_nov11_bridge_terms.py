"""The bridge names the legs it did not send and the positions nobody ordered."""

from __future__ import annotations

import pandas as pd

from live import bridge


def legs(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    """The evening's own leg records: ticker, broker id, reason code."""
    return pd.DataFrame(
        [
            {"ticker": ticker, "broker_order_id": broker, "reason_code": reason}
            for ticker, broker, reason in rows
        ]
    )


def test_a_name_that_exited_with_no_leg_sent_is_named_and_the_identity_holds() -> None:
    # 2026-10-08 in miniature: WBD left the book, its buy_to_close was skipped for a
    # missing symbol, and the fourth identity read 203 against 202 - the failure the
    # item is about. With the term named it holds, and the reason travels with it.
    orders = legs([("AAA", "oid-1", ""), ("WBD", "", "SYMBOL_NOT_FOUND")])
    block = bridge.evening(
        close="2026-10-08",
        held_before=["AAA", "WBD"],
        book=["AAA"],
        orders=orders,
    )
    assert block["exited"] == 1
    assert [item["ticker"] for item in block["exited_without_order"]] == ["WBD"]
    assert block["exited_without_order"][0]["reason"] == "SYMBOL_NOT_FOUND"
    checks = {item["name"]: item for item in block["identities"]}
    fourth = checks["changed + opened + exited - the legs not sent = orders sent"]
    assert fourth["holds"] is True
    # held before - exited + opened = 2 - 1 + 0, against the one leg sent plus the
    # one leg that could not be sent.
    assert fourth["left"] == 2 and fourth["right"] == 2


def test_under_the_minimum_counts_only_the_minimum() -> None:
    # 2026-10-08: 24 continuing names had no leg sent, 23 because of the $250 floor
    # and the twenty-fourth because the broker would not lend SYY. `under_minimum`
    # used to report 24 and tell the reader the wrong reason for one name.
    orders = legs(
        [
            ("AAA", "oid-1", ""),
            ("BBB", "", "BELOW_MIN_NOTIONAL"),
            ("SYY", "", "ASSET_NOT_SHORTABLE"),
        ]
    )
    block = bridge.evening(
        close="2026-10-08",
        held_before=["AAA", "BBB", "SYY"],
        book=["AAA", "BBB", "SYY"],
        orders=orders,
    )
    assert block["in_both"] == 3
    assert block["changed"] == 1
    assert block["not_sent_continuing"] == 2
    assert block["under_minimum"] == 1
    assert block["under_minimum_tickers"] == ["BBB"]
    assert block["skipped_continuing"] == [
        {"ticker": "SYY", "reason": "ASSET_NOT_SHORTABLE"}
    ]
    checks = {item["name"]: item for item in block["identities"]}
    assert checks["changed + the continuing legs not sent = in both"]["holds"] is True


def test_a_position_that_arrived_with_no_order_is_named_on_the_morning_half() -> None:
    # 2026-10-06: the account held SKYD - the PSKY position, returned by the
    # broker's late rename - and neither the evening's read nor the book held it, so
    # the last identity read 195 against 196 on a day nothing was wrong with.
    evening = bridge.evening(
        close="2026-10-06",
        held_before=["AAA", "BBB"],
        book=["AAA"],
        orders=legs([("AAA", "oid-1", ""), ("BBB", "oid-2", "")]),
    )
    block = bridge.completed(
        evening,
        filled=2,
        did_not_fill=0,
        held_after=["AAA", "SKYD"],
        book=["AAA"],
    )
    assert [item["ticker"] for item in block["arrived_without_order"]] == ["SKYD"]
    checks = {item["name"]: item for item in block["identities"]}
    last = checks[
        "held before - exited + opened - reversals and removals + arrived = held after"
    ]
    assert last["holds"] is True
    # held before - exited + opened = 2 - 1, against the two names the account holds
    # less the one that arrived from outside the loop's own book.
    assert last["left"] == 1 and last["right"] == 1
    # The name is in the gap's own list, so the page can draw it.
    assert "SKYD" in bridge.gap_names(block)


def test_a_normal_morning_names_no_arrivals() -> None:
    evening = bridge.evening(
        close="2026-10-08",
        held_before=["AAA"],
        book=["AAA", "BBB"],
        orders=legs([("AAA", "oid-1", ""), ("BBB", "oid-2", "")]),
    )
    block = bridge.completed(
        evening,
        filled=2,
        did_not_fill=0,
        held_after=["AAA", "BBB"],
        book=["AAA", "BBB"],
    )
    assert block["arrived_without_order"] == []
    assert block["holds"] is True
