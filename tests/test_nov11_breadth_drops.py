"""The names that never reached the book are published, with the reason each left."""

from __future__ import annotations

from live import snapshot


def test_the_breadth_block_carries_the_names_and_their_reasons():
    document = snapshot.build(
        run={"target_close": "2026-10-09"},
        manifest={
            "n_dropped_no_risk": 2,
            "dropped_no_risk": [
                {"ticker": "AAA", "reason": "no specific variance"},
                {"ticker": "BBB", "reason": "short history"},
                {"ticker": "", "reason": "a row with no name is not a name"},
            ],
        },
    )
    breadth = document["breadth"]
    assert breadth["n_dropped_no_risk"] == 2
    assert breadth["dropped_no_risk"] == [
        {"ticker": "AAA", "reason": "no specific variance"},
        {"ticker": "BBB", "reason": "short history"},
    ]


def test_a_manifest_without_the_key_publishes_an_empty_list_not_a_missing_one():
    # The page reads the key's shape, so a document that carries no drops carries an
    # empty list rather than nothing at all.
    document = snapshot.build(run={}, manifest={})
    assert document["breadth"]["dropped_no_risk"] == []
    assert document["breadth"]["n_dropped_no_risk"] is None
