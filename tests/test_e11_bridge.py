"""The book bridge, computed from the stored 2026-10-05 session.

The fixture beside this test is that evening's own record, read out of the store:
the 201 names the account held when the evening read it, the 191-name book the run
published, the 233 legs it built (199 sent, 34 under the minimum), the fills the
morning reconciled, and the 188 positions the account held the next day. Nothing in
it is invented, which is what makes the eight numbers below assertions rather than
descriptions.

The identities are the point. Three sets on the page - the book, the orders, the
positions - are correct on their own and read as three disagreements without the
arithmetic that connects them, and an arithmetic that cannot be checked is a fourth
number to trust. So each one is checked here against the session's own numbers, and
the block reports the two sides of any that fails.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from live import bridge

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bridge_2026-10-05.json"


@pytest.fixture(scope="module")
def session() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text())


def _orders(session: dict[str, Any]) -> pd.DataFrame:
    """The evening's leg rows, in the shape the run hands the bridge."""
    return pd.DataFrame(
        [
            {
                "ticker": row["ticker"],
                "intended_notional": row["intended_notional"],
                "position_intent": row["position_intent"],
                "reason_code": row["reason_code"],
                "broker_order_id": "sent" if row["sent"] else "",
            }
            for row in session["orders"]
        ]
    )


def _evening(session: dict[str, Any]) -> dict[str, Any]:
    return bridge.evening(
        close=session["close"],
        held_before=session["held_before"],
        book=session["book"],
        orders=_orders(session),
        reversals=session["deferred_reversals"],
    )


def _complete(session: dict[str, Any], evening: dict[str, Any]) -> dict[str, Any]:
    return bridge.completed(
        evening,
        filled=session["fills"]["filled"],
        did_not_fill=session["fills"]["did_not_fill"],
        held_after=session["held_after"],
        book=session["book"],
        removed=session["removed_without_order"],
    )


def test_the_bridge_is_that_sessions_own_numbers(session: dict[str, Any]) -> None:
    """Every count, against the stored record rather than against a description."""
    block = _complete(session, _evening(session))

    assert block["held_before"] == 201
    assert block["book"] == 191
    assert block["in_both"] == 159
    assert block["opened"] == 32
    assert block["exited"] == 42
    assert block["changed"] == 125
    assert block["under_minimum"] == 34
    assert block["orders_sent"] == 199
    assert block["filled"] == 197
    assert block["did_not_fill"] == 2
    assert block["held_after"] == 188


@pytest.mark.parametrize(
    ("left", "right"),
    [
        # 159 + 32 = 191, and 159 + 42 = 201: the two sets meeting in the middle.
        ("in both + opened = the book", "in both + exited = held before trading"),
        # 125 + 34 = 159: every continuing name either traded or was left alone.
        (
            "changed + under the minimum = in both",
            "changed + opened + exited = orders sent",
        ),
        # 125 + 32 + 42 = 199 = 197 + 2: the legs and the fills are one set.
        (
            "orders sent = filled + did not fill",
            "held before - exited + opened - reversals and removals = held after",
        ),
    ],
)
def test_every_identity_holds_on_that_session(
    session: dict[str, Any], left: str, right: str
) -> None:
    """Four of the five, with the two sides the block itself reports.

    `201 - 42 - 2 + 32 - 1 = 188` is the fifth: the two names the evening closed to
    reopen the other side (INVH and SLB) and the one that left with no order behind
    it (PSKY) are the whole of the gap between the book and the account.
    """
    block = _complete(session, _evening(session))
    checks = {item["name"]: item for item in block["identities"]}

    assert block["holds"] is True
    for name in (left, right):
        assert checks[name]["holds"] is True, checks[name]
        assert checks[name]["left"] == checks[name]["right"]

    assert checks["in both + opened = the book"]["left"] == 191
    assert checks["in both + exited = held before trading"]["left"] == 201
    assert checks["changed + under the minimum = in both"]["left"] == 159
    assert checks["changed + opened + exited = orders sent"]["left"] == 199
    assert checks["orders sent = filled + did not fill"]["left"] == 199
    last = checks["held before - exited + opened - reversals and removals = held after"]
    assert last["left"] == 191
    assert last["right"] == 191


def test_the_gap_is_itemised_into_a_reversal_a_removal_and_nothing_else(
    session: dict[str, Any],
) -> None:
    """The three names the book has and the account does not, each explained.

    INVH and SLB are the evening's own deferred reversals: closed tonight so the
    other side can open tomorrow. PSKY is the removal - no closing leg filled and no
    activity names it - and the bridge says which of the two it is rather than
    folding all three into one "missing" count, because they are three different
    things to do something about.
    """
    block = _complete(session, _evening(session))

    assert sorted(block["reversals_pending"]) == ["INVH", "SLB"]
    assert [item["ticker"] for item in block["removed_without_order"]] == ["PSKY"]
    assert block["removed_without_order"][0]["quantity"] == pytest.approx(326.072572039)
    assert block["removed_without_order"][0]["notional"] == pytest.approx(3211.814835)
    assert block["unexplained"] == []
    assert bridge.gap_names(block) == ["INVH", "PSKY", "SLB"]


def test_the_two_rejected_legs_are_the_two_that_did_not_fill(
    session: dict[str, Any],
) -> None:
    """PSKY's close and WBD's flip, both rejected at the open.

    WBD is a continuing name whose leg was a single `sell_to_open` that flipped it
    from long to short; the broker refused it, so the name is still a long in the
    account and the count does not move. PSKY's close was refused too, and the
    position left the account anyway, which is what makes it the removal rather than
    a miss like WBD's.
    """
    misses = {item["ticker"]: item for item in session["fills"]["misses"]}
    assert sorted(misses) == ["PSKY", "WBD"]
    assert all(item["status"] == "REJECTED" for item in misses.values())
    assert all(item["filled_quantity"] == 0.0 for item in misses.values())

    legs = {row["ticker"]: row for row in session["orders"]}
    assert legs["PSKY"]["position_intent"] == "sell_to_close"
    assert legs["WBD"]["position_intent"] == "sell_to_open"
    both = set(session["held_before"]) & set(session["book"])
    assert {"PSKY", "WBD"} <= both


def test_an_evening_block_says_only_what_the_evening_knew(
    session: dict[str, Any],
) -> None:
    """Half a bridge, checked in full and claiming no more than it has.

    The evening has no fills and no account after its own orders, so those three
    fields are null rather than zero - a zero would read as a morning on which
    nothing filled - and the two checks that need them are not run. Losing the
    morning's half must not turn the evening's half into a failure.
    """
    block = _evening(session)

    assert block["seen_by"] == "evening"
    assert block["filled"] is None
    assert block["did_not_fill"] is None
    assert block["held_after"] is None
    assert block["holds"] is True
    assert len(block["identities"]) == 4
    assert {item["name"] for item in block["identities"]} == {
        "in both + opened = the book",
        "in both + exited = held before trading",
        "changed + under the minimum = in both",
        "changed + opened + exited = orders sent",
    }


def test_a_bridge_that_does_not_add_up_says_which_two_numbers_disagree(
    session: dict[str, Any],
) -> None:
    """The self-check, on the case it exists for: a position nobody accounted for.

    One name is taken out of the account that nothing in the block explains. The
    arithmetic then fails rather than quietly reporting a smaller book, and it names
    both sides of the check so the reader can see which end is wrong.
    """
    evening = _evening(session)
    # A name the account holds today and the book has: the bridge sees it as gone and
    # nothing in the block claims it, which is the failure mode the check is for.
    victim = sorted(set(session["book"]) & set(session["held_after"]))[0]
    held_after = [name for name in session["held_after"] if name != victim]
    block = bridge.completed(
        evening,
        filled=session["fills"]["filled"],
        did_not_fill=session["fills"]["did_not_fill"],
        held_after=held_after,
        book=session["book"],
        removed=session["removed_without_order"],
    )

    assert block["unexplained"] == [victim]
    assert block["holds"] is False
    failed = [item for item in block["identities"] if not item["holds"]]
    assert [item["name"] for item in failed] == [
        "held before - exited + opened - reversals and removals = held after"
    ]
    # The check's own two sides: the book on the left, and on the right the account
    # with only the two kinds the loop can account for added back. One name short,
    # which is the disappearance.
    assert failed[0]["left"] == 191
    assert failed[0]["right"] == 190


def test_a_leg_count_that_does_not_match_the_fills_fails_the_bridge(
    session: dict[str, Any],
) -> None:
    """The other end: a bridge whose orders are not the orders that filled."""
    block = bridge.completed(
        _evening(session),
        filled=197,
        did_not_fill=0,
        held_after=session["held_after"],
        book=session["book"],
        removed=session["removed_without_order"],
    )

    assert block["holds"] is False
    checks = {item["name"]: item for item in block["identities"]}
    assert checks["orders sent = filled + did not fill"] == {
        "name": "orders sent = filled + did not fill",
        "left": 199,
        "right": 197,
        "holds": False,
    }


def test_a_morning_with_no_evening_block_completes_to_nothing() -> None:
    """No bridge to complete is not a bridge of zeroes.

    A stopped run publishes none, and the morning after one has no arithmetic to
    state: an invented block would describe an evening nobody ran.
    """
    empty = bridge.completed(None, filled=0, did_not_fill=0, held_after=[], book=[])
    assert empty == {}


def test_the_under_minimum_legs_carry_their_own_reasons(
    session: dict[str, Any],
) -> None:
    """34 legs were built and not sent, and the block says why.

    They are the names whose change was under the $250 line, so the bridge's
    "under the minimum" count is that reason and not a bucket of unrelated skips:
    the count is checkable against the run's own order rows.
    """
    block = _evening(session)

    assert block["under_minimum"] == 34
    assert block["skipped_reasons"] == {"BELOW_MIN_NOTIONAL": 34}
    assert block["under_minimum_usd"] == 250.0
    sent = [row for row in session["orders"] if row["sent"]]
    assert len(sent) == block["orders_sent"]
    assert all(row["reason_code"] == "" for row in sent)


# --- the two writers -------------------------------------------------------
#
# The block is only worth publishing if the runs publish their own halves of it,
# so the two writers are exercised here as well as the arithmetic: the evening's
# through `snapshot.write_snapshot`, which is where a parameter that is not
# declared is a `NameError` rather than a page with no panel, and the morning's
# through `reconcile_fills.publish`, which is the only place the morning's half
# can reach the document the evening put up.


def _block(session: dict[str, Any]) -> dict[str, Any]:
    return _complete(session, _evening(session))


def _r2(monkeypatch: pytest.MonkeyPatch) -> None:
    """The four variables an upload needs, none of them real."""
    monkeypatch.setenv("EFB_R2_ACCOUNT_ID", "account123")
    monkeypatch.setenv("EFB_R2_BUCKET", "efb-snapshots")
    monkeypatch.setenv("EFB_R2_ACCESS_KEY_ID", "test-access-key-id")
    monkeypatch.setenv("EFB_R2_SECRET_ACCESS_KEY", "test-secret-access-key")


def test_the_evening_publishes_its_half_under_bridge(
    session: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`write_snapshot(bridge_block=...)` reaches the uploaded document."""
    from live import snapshot

    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, "on")
    _r2(monkeypatch)
    written: list[dict[str, Any]] = []
    result = snapshot.write_snapshot(
        run={"status": "ok", "dry_run": False},
        bridge_block=_block(session),
        dry_run=False,
        poster=lambda **kwargs: written.append(kwargs),
    )
    assert result["mode"] == "on"
    assert [item["Key"] for item in written] == [
        "latest.json",
        "snapshots/unknown.json",
    ]
    payload = json.loads(written[0]["Body"])
    assert payload["bridge"]["held_before"] == 201
    assert payload["bridge"]["held_after"] == 188
    assert payload["bridge"]["holds"] is True
    # The block the page draws is the one the schema declares.
    assert set(payload["bridge"]) == {
        "close",
        "seen_by",
        "book",
        "held_before",
        "in_both",
        "opened",
        "exited",
        "changed",
        "under_minimum",
        "orders_sent",
        "filled",
        "did_not_fill",
        "held_after",
        "under_minimum_usd",
        "reversals_pending",
        "removed_without_order",
        "unexplained",
        "identities",
        "holds",
    }


def test_a_run_that_built_no_bridge_publishes_no_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Absent, not null: an evening that failed before its read moved nothing."""
    from live import snapshot

    payload = snapshot.build(run={"status": "error", "dry_run": False})
    assert "bridge" not in payload


def test_the_morning_completes_the_half_it_read_back(
    session: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`publish` writes the completed block over the evening's half."""
    import scripts.reconcile_fills as reconcile_fills
    from live import snapshot

    _r2(monkeypatch)
    evening = _evening(session)
    published: dict[str, Any] = {
        "target_close": "2026-10-05",
        "book": {"names": [{"ticker": name} for name in session["book"]]},
        "bridge": evening,
    }
    monkeypatch.setattr(
        snapshot, "get_object_text", lambda *a, **k: json.dumps(published)
    )
    written: list[dict[str, Any]] = []

    keys = reconcile_fills.publish(
        {"as_of": "2026-10-06T15:30:04+00:00"},
        bridge_block=_complete(session, evening),
        poster=lambda **kwargs: written.append(kwargs),
    )

    assert keys == ["latest.json", "snapshots/2026-10-05.json"]
    document = json.loads(written[0]["Body"])
    assert document["bridge"]["seen_by"] == "morning"
    assert document["bridge"]["filled"] == 197
    assert document["bridge"]["held_after"] == 188
    assert document["bridge"]["holds"] is True
    # The evening's own bytes are republished, not rebuilt: the book the run
    # traded is still the book on the page.
    assert document["book"] == published["book"]


def test_the_evening_builds_its_half_from_the_runs_own_objects() -> None:
    """The evening's call site, on a small book whose arithmetic closes.

    Three names held, two of them kept (one resized, one left alone under the
    minimum) and one closed, with one name opened: 3 legs, and every identity that
    does not need the morning holds. The leg rows are what the run writes - a broker
    id means sent, its absence means the run decided against it.
    """
    import scripts.run_live_daily as run_live_daily

    orders = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC", "DDD"],
            "reason_code": ["", "BELOW_MIN_NOTIONAL", "", ""],
            "broker_order_id": ["id-1", "", "id-2", "id-3"],
        }
    )
    block = run_live_daily.evening_bridge(
        "2026-10-05",
        dry_run=False,
        holdings={"broker": {"AAA": 600.0, "BBB": 250.0, "CCC": -900.0}},
        book=pd.DataFrame({"ticker": ["AAA", "BBB", "DDD"]}),
        legs=orders,
        reversals=[{"ticker": "CCC"}],
    )

    assert block is not None
    assert block["held_before"] == 3
    assert block["book"] == 3
    assert block["in_both"] == 2
    assert block["opened"] == 1
    assert block["exited"] == 1
    assert block["changed"] == 1
    assert block["under_minimum"] == 1
    assert block["orders_sent"] == 3
    assert block["seen_by"] == "evening"
    # The three the morning owns are null, not zero: an evening has no fills and no
    # account after its own orders.
    assert block["filled"] is None
    assert block["did_not_fill"] is None
    assert block["held_after"] is None
    assert block["reversals_pending"] == ["CCC"]
    assert block["under_minimum_usd"] == 250.0
    assert block["holds"] is True
    assert len(block["identities"]) == 4


def test_a_dry_run_publishes_no_bridge_at_all() -> None:
    """Nothing was sent, so there is no arithmetic to state.

    `sent` counts only legs the broker took, and a dry run's legs all carry no
    broker id: the block would report 0 orders against a book that holds every
    name, and the page would draw a broken bridge every time the run is rehearsed.
    None is the honest answer, and the page hides the panel for it.
    """
    import scripts.run_live_daily as run_live_daily

    block = run_live_daily.evening_bridge(
        "2026-10-05",
        dry_run=True,
        holdings={"broker": {"AAA": 600.0}},
        book=pd.DataFrame({"ticker": ["AAA"]}),
        legs=pd.DataFrame(
            {
                "ticker": ["AAA"],
                "reason_code": ["DRY_RUN"],
                "broker_order_id": [""],
            }
        ),
        reversals=[],
    )
    assert block is None
