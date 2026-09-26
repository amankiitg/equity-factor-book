"""Sprint E11: why a weight moved, and what counts as a previous book.

Two things are pinned here. The first is the establishment day: with no earlier
book every row is a position being opened, so the reason is "new position" rather
than "alpha moved" - a reason that says something moved when nothing had ever been
there. The second is where the earlier book comes from: a fresh run tree holds no
earlier proposal file, so the reason column used to be constant, and the store's
own record of the last book is what it now compares against.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from live import store, trade_reasons
from scripts import run_live_daily


def _today() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC"],
            "weight": [0.02, -0.03, 0.01],
            "z": [1.0, -1.5, 0.5],
            "alpha": [1e-5, -2e-5, 3e-6],
        }
    )


def _specific() -> pd.Series:
    return pd.Series({"AAA": 0.02, "BBB": 0.03, "CCC": 0.025})


def test_the_establishment_day_opens_every_position() -> None:
    """No earlier book: every row is a new position, and none of them moved."""
    frame = trade_reasons.assign_trade_reasons(_today(), None, _specific(), None)

    assert list(frame["reason"]) == ["new position"] * 3
    assert list(frame["ticker"]) == ["AAA", "BBB", "CCC"]
    assert list(frame["weight"]) == [0.02, -0.03, 0.01]


def test_an_empty_earlier_book_is_also_no_earlier_book() -> None:
    """A store that hands back a columnless frame is the first evening, not a book."""
    frame = trade_reasons.assign_trade_reasons(
        _today(), pd.DataFrame(columns=["ticker", "weight", "z"]), _specific(), None
    )

    assert set(frame["reason"]) == {"new position"}


def test_the_previous_book_still_answers_the_moved_question() -> None:
    """The negative control: with a real earlier book nothing is a new position.

    AAA keeps its weight and its score, so nothing traded and the reason says so.
    CCC is new to a book that exists, which stays "alpha moved" - the first score
    of a name entering an existing book is what put it there. BBB's weight moved
    while its score and its risk did not, so under the documented precedence the
    only thing left that can have moved is the hedge. (The run passes the same
    specific standard deviation for both closes, so "risk moved" cannot be reached
    from `run_live_daily` as it stands; that is a finding for the owner, not
    something this test should paper over.)
    """
    previous = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "weight": [0.02, -0.01],
            "z": [1.0, -1.5],
        }
    )
    frame = trade_reasons.assign_trade_reasons(
        _today(), previous, _specific(), _specific()
    )

    reasons = dict(zip(frame["ticker"], frame["reason"], strict=True))
    assert reasons == {
        "AAA": "no trade",
        "BBB": "the hedge moved",
        "CCC": "alpha moved",
    }
    assert "new position" not in set(frame["reason"])

    # A weight that moved because its own score moved is an alpha move.
    moved = _today()
    moved.loc[moved["ticker"] == "AAA", "z"] = 2.0
    moved.loc[moved["ticker"] == "AAA", "weight"] = 0.03
    second = trade_reasons.assign_trade_reasons(
        moved, previous, _specific(), _specific()
    )
    assert (
        dict(zip(second["ticker"], second["reason"], strict=True))["AAA"]
        == "alpha moved"
    )


def test_the_previous_book_comes_from_the_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two earlier closes: the later one is the book, and tonight is not it."""
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    store.upsert(
        "positions",
        [
            {"trade_date": "2026-09-23", "ticker": "AAA", "weight": 0.01, "z": 0.4},
            {"trade_date": "2026-09-24", "ticker": "AAA", "weight": 0.02, "z": 1.0},
            {"trade_date": "2026-09-24", "ticker": "BBB", "weight": -0.02, "z": -1.0},
        ],
    )

    previous = run_live_daily.previous_book("2026-09-25", [])

    assert previous is not None
    assert list(previous["ticker"]) == ["AAA", "BBB"]
    assert list(previous["weight"]) == [0.02, -0.02]
    # Strictly before: tonight's own rows are never the comparison.
    assert run_live_daily.previous_book("2026-09-24", []) is not None
    assert len(run_live_daily.previous_book("2026-09-24", [])) == 1


def test_no_earlier_close_means_no_previous_book(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first evening, and a store holding only tonight, are both None."""
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")

    assert run_live_daily.previous_book("2026-09-25", []) is None

    store.upsert(
        "positions",
        [{"trade_date": "2026-09-25", "ticker": "AAA", "weight": 0.02, "z": 1.0}],
    )

    assert run_live_daily.previous_book("2026-09-25", []) is None


def test_a_previous_book_without_a_score_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row with no score cannot answer "did the alpha move", and must not raise.

    An older store, or a writer that dropped a column, would otherwise turn the
    reason column into a KeyError in the middle of an evening.
    """
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path / "store")
    store.upsert(
        "positions",
        [{"trade_date": "2026-09-24", "ticker": "AAA", "weight": 0.02}],
    )

    assert run_live_daily.previous_book("2026-09-25", []) is None
