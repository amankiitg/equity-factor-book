"""The message's order count is the legs that became orders, not the legs built."""

from __future__ import annotations

import pandas as pd

from live import morning_job, notify


def records(rows: list[tuple[str, float, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ticker": ticker, "intended_notional": notional, "broker_order_id": broker}
            for ticker, notional, broker in rows
        ]
    )


def test_the_count_and_the_dollars_use_one_predicate():
    # 2026-10-08 in miniature: three legs built, two sent, one refused before
    # submission. The message said 204 sent while the broker held 202.
    frame = records([("AAA", 100.0, "id-1"), ("BBB", 200.0, "id-2"), ("SYY", 300.0, "")])
    assert morning_job.sent_orders(frame) == 2
    assert morning_job.sent_notional(frame) == 300.0


def test_an_empty_log_is_no_orders_rather_than_an_error():
    assert morning_job.sent_orders(pd.DataFrame()) == 0
    assert morning_job.sent_orders(pd.DataFrame({"ticker": ["AAA"]})) == 0


def test_the_message_says_sent_for_the_legs_that_were_sent():
    message = notify.compose(
        status="incomplete",
        target_close="2026-10-08",
        dry_run=False,
        orders=204,
        sent_orders=202,
        gross=506_978.0,
        sent_notional=496_341.0,
        detail="1 leg(s) not confirmed: SYY (ASSET_NOT_SHORTABLE)",
        store="postgres/efb",
    )
    assert "Orders: 202 orders sent" in message
    assert "$496,341 sent of $506,978 sized" in message
    assert "204 orders sent" not in message


def test_a_dry_run_still_counts_what_it_proposed():
    # Nothing was sent on a dry run, so the proposed count is the honest one.
    message = notify.compose(
        status="ok",
        target_close="2026-10-08",
        dry_run=True,
        orders=204,
        sent_orders=0,
        gross=506_978.0,
        store="postgres/efb",
    )
    assert "dry run: 204 orders proposed" in message


def test_the_subject_says_sent_for_the_legs_that_were_sent():
    subject = notify.subject_text(
        status="incomplete",
        target_close="2026-10-08",
        dry_run=False,
        orders=204,
        sent_orders=202,
    )
    assert "202 sent" in subject
    assert "204 sent" not in subject


def test_a_caller_that_does_not_pass_the_sent_count_keeps_the_old_reading():
    # Every existing caller and test keeps its meaning: the default is the built
    # count rather than a silent zero.
    message = notify.compose(
        status="ok", target_close="2026-10-08", dry_run=False, orders=12, store="x"
    )
    assert "Orders: 12 orders sent" in message
