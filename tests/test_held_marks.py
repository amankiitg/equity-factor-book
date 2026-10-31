"""The held-book mark source, and the switch that changes it (P1a, 2026-10-31)."""

from __future__ import annotations

import pandas as pd
import pytest

from live import held_marks


def _tree(tmp_path, rows: list[tuple[str, str, float]]):
    """A tree with a raw/prices.parquet holding just these (date, ticker, close)."""
    (tmp_path / "raw").mkdir()
    frame = pd.DataFrame(rows, columns=["date", "ticker", "close"])
    frame["open"] = frame["close"]
    frame["high"] = frame["close"]
    frame["low"] = frame["close"]
    frame["adj_close"] = frame["close"]
    frame["volume"] = 1_000.0
    frame["dividend"] = 0.0
    frame["split_factor"] = 1.0
    frame = frame.set_index(["date", "ticker"]).sort_index()
    frame.to_parquet(tmp_path / "raw" / "prices.parquet")
    return tmp_path


def test_unset_is_the_broker_and_that_is_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(held_marks.HELD_MARKS_ENV, raising=False)
    assert held_marks.mode() == held_marks.MODE_BROKER
    monkeypatch.setenv(held_marks.HELD_MARKS_ENV, "broker")
    assert held_marks.mode() == held_marks.MODE_BROKER
    monkeypatch.setenv(held_marks.HELD_MARKS_ENV, "close")
    assert held_marks.mode() == held_marks.MODE_CLOSE


def test_a_mode_that_is_not_a_mark_source_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(held_marks.HELD_MARKS_ENV, "mid")
    with pytest.raises(ValueError, match="is not a mark source"):
        held_marks.mode()


def test_a_held_name_is_valued_at_its_close_times_its_quantity() -> None:
    notional = {"INTC": 711.60, "AAPL": -2_841.00}
    quantities = {"INTC": 10.0, "AAPL": -17.0}
    closes = {"INTC": 92.07, "AAPL": 167.12}
    valued, summary = held_marks.at_close(notional, quantities, closes)
    assert valued["INTC"] == pytest.approx(920.70)
    assert valued["AAPL"] == pytest.approx(-2_841.04)
    assert summary["mode"] == held_marks.MODE_CLOSE
    assert summary["n_remark"] == 2
    assert summary["n_kept_broker"] == 0
    # The reported move is the dollar difference the mark source makes.
    assert summary["largest_move"]["ticker"] == "INTC"
    assert summary["largest_move"]["usd"] == pytest.approx(209.10, abs=0.01)


def test_a_name_with_no_close_keeps_the_brokers_number_and_is_named() -> None:
    notional = {"INTC": 711.60, "ZZZ": 100.0}
    quantities = {"INTC": 10.0, "ZZZ": 1.0}
    valued, summary = held_marks.at_close(notional, quantities, {"INTC": 92.07})
    assert valued["ZZZ"] == 100.0, "a missing mark must not drop the position"
    assert summary["kept_broker"] == ["ZZZ"]
    assert summary["n_kept_broker"] == 1


def test_the_provider_answers_the_newest_close_not_a_later_one(tmp_path) -> None:
    root = _tree(
        tmp_path,
        [
            ("2026-10-28", "INTC", 90.00),
            ("2026-10-29", "INTC", 92.07),
            ("2026-10-30", "INTC", 65.88),
            ("2026-10-29", "ZZZ", 10.0),
        ],
    )
    answer = held_marks.tree_closes(root, "2026-10-29")(["INTC", "ZZZ", "MISSING"])
    assert answer == {"INTC": pytest.approx(92.07), "ZZZ": pytest.approx(10.0)}


def test_a_provider_that_fails_leaves_the_book_at_the_brokers_marks(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    def _boom(_names):
        raise RuntimeError("no tree")

    held_marks.configure(_boom)
    try:
        assert held_marks.marks_for(["INTC"]) == {}
    finally:
        held_marks.configure(None)
