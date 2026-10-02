"""The spin-off rule: the correction, the record, and the two controls.

A spin-off is the one corporate action that moves a parent's return on the ex-date
and that neither price vendor adjusts: CTVA closed 77.65 on 2026-09-30 and printed
12.57 the next day, a raw -83.81% that is not a loss, because the holder was also
given one VYLR share worth 68.26. `live/corporate_actions.py` corrects it in the
append path from the parent's and the child's raw closes and the vendor's own
spin-off record, before the fit reads the returns, and records it.

The numbers in the acceptance case are the measured ones, not invented ones: 77.65,
12.57 and 68.26 are the three closes, and the return they describe is
`(12.57 + 68.26) / 77.65 - 1` = +4.0953%, which rounds to the +4.10% the owner
checked by hand. The two controls are the moves that must NOT be corrected: MRNA's
+176.97% on 2026-08-19, which is a real move and stays raw and flagged, and a
2:1 split, which still takes the split path it already had.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from live import alpaca, notify, store
from live import corporate_actions as ca
from scripts import rehearse_preflip, run_live_daily
from tests.test_e11_corporate_actions import prices_frame, returns_frame

ROOT = Path(__file__).resolve().parents[1]

# The spin-off, as measured.
SESSION = pd.Timestamp("2026-10-01")
PRIOR = pd.Timestamp("2026-09-30")
CTVA_PREVIOUS_CLOSE = 77.65
CTVA_CLOSE = 12.57
VYLR_CLOSE = 68.26
RAW_PRINT = CTVA_CLOSE / CTVA_PREVIOUS_CLOSE - 1.0
TARGET_RETURN = 0.040953
# The other real move, from the stored panel: MRNA on 2026-08-19.
MRNA_SESSION = pd.Timestamp("2026-08-19")
MRNA_RETURN = 1.7696951623021624


def a_spinoff(*, parent: str = "CTVA", child: str = "VYLR") -> ca.Spinoff:
    return ca.Spinoff(
        parent=parent,
        child=child,
        ex_date=SESSION,
        child_per_parent=1.0,
        source_rate=1.0,
        new_rate=1.0,
    )


def ctva_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """The two rows the rule needs, in the artifacts' own layouts."""
    frame = returns_frame(
        [
            ("2026-09-30", "CTVA", 0.001),
            ("2026-10-01", "CTVA", RAW_PRINT),
            ("2026-10-01", "AAA", 0.02),
        ]
    )
    prices = prices_frame(
        [
            ("2026-09-30", "CTVA", CTVA_PREVIOUS_CLOSE, CTVA_PREVIOUS_CLOSE, 0.0),
            ("2026-10-01", "CTVA", CTVA_CLOSE, CTVA_CLOSE, 0.0),
        ]
    )
    return frame, prices


def test_the_ctva_spinoff_becomes_the_true_total_return():
    """+4.10%, from the three real closes, with the raw print kept and explained.

    This is the acceptance case. The cell the fit reads becomes the total return the
    session actually paid, the print it replaced is in the flag with its own value,
    the flag carries no `explained_by` of None so the run reports no unexplained
    move, and the stored session before it is untouched: nothing is restated.
    """
    frame, prices = ctva_frames()

    outcome = ca.apply_to_append(
        frame,
        prices,
        since=PRIOR,
        spinoffs={SESSION: [a_spinoff()]},
        child_close=lambda ticker, session: VYLR_CLOSE if ticker == "VYLR" else None,
    )

    value = float(frame.loc[(SESSION, "CTVA"), "r"])
    assert value == pytest.approx(TARGET_RETURN, abs=1e-6)
    assert f"{value * 100:+.2f}%" == "+4.10%", "the number the owner checked by hand"
    assert float(frame.loc[(PRIOR, "CTVA"), "r"]) == 0.001, "history was restated"
    assert float(frame.loc[(SESSION, "AAA"), "r"]) == 0.02, "another name moved"

    flags = {flag["ticker"]: flag for flag in outcome.flags}
    assert list(flags) == ["CTVA"]
    assert flags["CTVA"]["return"] == pytest.approx(RAW_PRINT)
    assert flags["CTVA"]["adjusted_return"] == pytest.approx(TARGET_RETURN, abs=1e-6)
    assert flags["CTVA"]["explained_by"] == "spinoff"
    assert flags["CTVA"]["flag"] == "spinoff: CTVA -> VYLR 1:1 applied"
    assert flags["CTVA"]["new_ticker"] == "VYLR"
    assert flags["CTVA"]["new_close"] == pytest.approx(VYLR_CLOSE)
    assert [flag for flag in outcome.flags if flag["explained_by"] is None] == []

    assert [event.spinoff.child_per_parent for event in outcome.spinoffs] == [1.0]
    assert ca.describe_spinoffs(outcome.spinoffs) == [
        "spinoff: CTVA -> VYLR 1:1 applied"
    ]
    assert ca.missing_child_notes(outcome.spinoffs) == []


def test_the_record_is_the_parent_row_with_the_child_and_both_rates():
    """One row per spin-off, in the table splits already write to.

    The parent is the row's ticker because the parent is the name whose return
    changed, `factor` is the child's shares per parent share (the slot a split's
    factor occupies), and `explained_by` says which of the two kinds the row is.
    `source_rate` and `new_rate` are kept as the vendor gave them, so a later reader
    can see the 1:1 rather than only the ratio it reduced to.
    """
    events = [
        ca.SpinoffOutcome(a_spinoff(), SESSION, RAW_PRINT, TARGET_RETURN, VYLR_CLOSE)
    ]
    assert ca.spinoff_rows(events, SESSION) == [
        {
            "trade_date": "2026-10-01",
            "ticker": "CTVA",
            "effective_date": "2026-10-01",
            "factor": 1.0,
            "source": "alpaca.corporate_actions",
            "cross_check_ratio": None,
            "explained_by": "spinoff",
            "new_ticker": "VYLR",
            "source_rate": 1.0,
            "new_rate": 1.0,
        }
    ]
    # A 2:1 at source would be a factor of 2 and the child named in `source_rate`
    # terms: the ratio is what the rule applies, the rates are what the vendor said.
    two_for_one = ca.Spinoff(
        "CTVA", "VYLR", SESSION, 2.0, source_rate=1.0, new_rate=2.0
    )
    rows = ca.spinoff_rows(
        [ca.SpinoffOutcome(two_for_one, SESSION, RAW_PRINT, 0.05, VYLR_CLOSE)], SESSION
    )
    assert rows[0]["factor"] == 2.0
    assert rows[0]["new_rate"] == 2.0


def test_the_log_return_moves_with_the_simple_one():
    """`r` and `g = ln(1 + r)` stay one row's two halves of the same number.

    Measured on the stored panel: `|g - log1p(r)|` is exactly 0, so a rule that
    rewrote `r` and left `g` would publish a row that contradicts itself. Both paths
    write both columns, and a nulled cell is null in both.
    """
    import numpy as np

    frame, prices = ctva_frames()
    frame["g"] = np.log1p(frame["r"])

    ca.apply_to_append(
        frame,
        prices,
        since=PRIOR,
        spinoffs={SESSION: [a_spinoff()]},
        child_close=lambda ticker, session: VYLR_CLOSE,
    )

    row = frame.loc[(SESSION, "CTVA")]
    assert float(row["g"]) == pytest.approx(np.log1p(float(row["r"])), abs=1e-12)
    assert float(row["r"]) == pytest.approx(TARGET_RETURN, abs=1e-6)

    nulled, prices_again = ctva_frames()
    nulled["g"] = np.log1p(nulled["r"])
    ca.apply_to_append(
        nulled,
        prices_again,
        since=PRIOR,
        spinoffs={SESSION: [a_spinoff()]},
        child_close=lambda ticker, session: None,
    )
    assert pd.isna(nulled.loc[(SESSION, "CTVA"), "g"])
    assert pd.isna(nulled.loc[(SESSION, "CTVA"), "r"])
    # The split path writes both columns too, from the same helper.
    split_session = pd.Timestamp("2026-09-04")
    split_frame = returns_frame([("2026-09-04", "AAA", -0.49)])
    split_frame["g"] = np.log1p(split_frame["r"])
    ca.apply_to_append(
        split_frame,
        prices_frame(
            [
                ("2026-09-04", "AAA", 51.0, 51.0, 2.0),
                ("2026-09-03", "AAA", 100.0, 100.0, 1.0),
            ]
        ),
        since=pd.Timestamp("2026-09-03"),
        split_fetcher=lambda ticker: pd.Series([2.0], index=[split_session]),
        close_fetcher=lambda ticker, session: 100.0,
    )
    split_row = split_frame.loc[(split_session, "AAA")]
    assert float(split_row["g"]) == pytest.approx(
        np.log1p(float(split_row["r"])), abs=1e-12
    )


def test_a_missing_child_close_nulls_that_one_cell_and_names_it():
    """The one case that is not an error: a hole instead of a wrong number.

    The parent's return is nulled rather than left as a print that is not a return,
    the other names in the session are untouched, the run does not stop, and the
    event says which child was missing so the message can name it.
    """
    frame, prices = ctva_frames()

    outcome = ca.apply_to_append(
        frame,
        prices,
        since=PRIOR,
        spinoffs={SESSION: [a_spinoff()]},
        child_close=lambda ticker, session: None,
    )

    assert pd.isna(frame.loc[(SESSION, "CTVA"), "r"])
    assert float(frame.loc[(SESSION, "AAA"), "r"]) == 0.02
    assert float(frame.loc[(PRIOR, "CTVA"), "r"]) == 0.001
    assert ca.missing_child_notes(outcome.spinoffs) == ["VYLR (CTVA)"]
    flag = outcome.flags[0]
    assert flag["adjusted_return"] is None
    assert flag["new_close"] is None
    assert flag["explained_by"] == "spinoff"
    assert "missing" in flag["flag"] and "nulled" in flag["flag"]


def test_a_child_the_panel_already_prices_costs_no_request():
    """The common case: the spun-off ticker is in tonight's universe.

    The run's universe carries the child from the session it starts trading, so the
    panel answers and the vendor is not asked at all. A rule that fetched anyway
    would spend one request per spin-off for a value it already had.
    """
    frame, prices = ctva_frames()
    prices.loc[(SESSION, "VYLR"), "close"] = VYLR_CLOSE

    calls: list[str] = []
    ca.apply_to_append(
        frame,
        prices,
        since=PRIOR,
        spinoffs={SESSION: [a_spinoff()]},
        child_close=lambda ticker, session: calls.append(ticker),  # type: ignore[func-returns-value]
    )

    assert calls == [], "the panel priced VYLR and the vendor was asked anyway"
    assert float(frame.loc[(SESSION, "CTVA"), "r"]) == pytest.approx(
        TARGET_RETURN, abs=1e-6
    )


def test_the_mrna_move_stays_raw_and_flagged_unexplained():
    """The control: a real +177% is a real return, and nothing corrects it.

    The rule only touches the parent of a spin-off the vendor reported for that
    session. With no such record, the appended session's large move is what it
    always was: stored as it came, flagged as unexplained, and named in the message.
    The stored panel's own MRNA row is read and asserted unchanged, which is the
    other half of "no stored row is restated".
    """
    frame = returns_frame(
        [("2026-08-18", "MRNA", 0.01), ("2026-08-19", "MRNA", MRNA_RETURN)]
    )
    prices = prices_frame(
        [
            ("2026-08-18", "MRNA", 40.0, 40.0, 0.0),
            ("2026-08-19", "MRNA", 110.8, 110.8, 0.0),
        ]
    )

    outcome = ca.apply_to_append(
        frame,
        prices,
        since=pd.Timestamp("2026-08-18"),
        split_fetcher=lambda ticker: pd.Series(dtype=float),
        # The cross-check the split rule already makes, answered with the stored
        # close: a ratio of 1 says the vendor did not restate the session, so there
        # is no corporate action behind the move and nothing corrects it.
        close_fetcher=lambda ticker, session: 40.0,
        spinoffs={},
    )

    assert float(frame.loc[(MRNA_SESSION, "MRNA"), "r"]) == pytest.approx(MRNA_RETURN)
    assert outcome.spinoffs == []
    assert outcome.flags == [
        {
            "ticker": "MRNA",
            "return": pytest.approx(MRNA_RETURN),
            "explained_by": None,
            "flag": "unexplained large move",
        }
    ]
    assert notify.subject_text(
        status="ok", target_close="2026-08-19", flags=outcome.flags
    ).endswith("flag 1")

    panel = pd.read_parquet(ROOT / "data" / "processed" / "returns.parquet")
    assert float(panel.loc[(MRNA_SESSION, "MRNA"), "r"]) == pytest.approx(MRNA_RETURN)


def test_a_split_still_takes_the_split_path():
    """The other control: the rule that was already there is untouched.

    A 2:1 on the appended session is corrected by the split pass, recorded with
    `explained_by` "split", and a spin-off for a different ticker in the same session
    does not disturb it. Both actions in one session is the case worth pinning: a
    spin-off pass that swallowed the split pass would be invisible otherwise.
    """
    frame = returns_frame(
        [
            ("2026-09-03", "AAA", 0.0),
            ("2026-09-04", "AAA", -0.49),
            ("2026-10-01", "CTVA", RAW_PRINT),
        ]
    )
    prices = prices_frame(
        [
            ("2026-09-03", "AAA", 100.0, 100.0, 1.0),
            ("2026-09-04", "AAA", 51.0, 51.0, 2.0),
            ("2026-09-30", "CTVA", CTVA_PREVIOUS_CLOSE, CTVA_PREVIOUS_CLOSE, 0.0),
            ("2026-10-01", "CTVA", CTVA_CLOSE, CTVA_CLOSE, 0.0),
        ]
    )

    outcome = ca.apply_to_append(
        frame,
        prices,
        since=pd.Timestamp("2026-09-03"),
        split_fetcher=lambda ticker: (
            pd.Series([2.0], index=[pd.Timestamp("2026-09-04")])
            if ticker == "AAA"
            else pd.Series(dtype=float)
        ),
        close_fetcher=lambda ticker, session: 100.0,
        spinoffs={SESSION: [a_spinoff()]},
        child_close=lambda ticker, session: VYLR_CLOSE,
    )

    assert [split.ticker for split in outcome.splits] == ["AAA"]
    assert float(frame.loc[(pd.Timestamp("2026-09-04"), "AAA"), "r"]) == pytest.approx(
        0.02
    )
    assert float(frame.loc[(SESSION, "CTVA"), "r"]) == pytest.approx(
        TARGET_RETURN, abs=1e-6
    )
    rows = ca.rows(outcome.splits, pd.Timestamp("2026-09-04"), outcome.ratios)
    assert rows[0]["explained_by"] == "split"
    assert rows[0]["new_ticker"] is None


def test_a_record_for_another_day_or_another_name_is_dropped():
    """Only the session's own parents, in the book's own universe.

    The endpoint answers over a window, so a record for a neighbouring day would be
    applied to the wrong session if it were kept, and a parent this book does not
    hold has no return here to correct.
    """
    records = [
        {
            "parent": "CTVA",
            "child": "VYLR",
            "ex_date": "2026-10-01",
            "source_rate": 1.0,
            "new_rate": 1.0,
        },
        {
            "parent": "ELSE",
            "child": "OTHR",
            "ex_date": "2026-10-01",
            "source_rate": 1.0,
            "new_rate": 1.0,
        },
    ]
    found = ca.vendor_spinoffs(SESSION, ["CTVA", "AAA"], fetcher=lambda s, d: records)
    assert [spinoff.parent for spinoff in found] == ["CTVA"]
    assert found[0].child_per_parent == 1.0
    assert ca.vendor_spinoffs(SESSION, [], fetcher=lambda s, d: records) == []


def test_a_record_we_cannot_use_nulls_that_one_cell_and_names_it():
    """A vendor field that cannot become a ratio is neither guessed at nor fatal.

    Leaving the print is the one thing that must not happen: a -84% in the fit
    because a rate came back empty is a number nobody can explain and no flag would
    catch. Stopping the run is the other thing that must not happen, and it is the
    worse of the two: the evening's orders are sent before this rule runs, so an
    empty vendor field would turn a bad record into a lost evening. So the parent's
    cell is nulled, the record is named in the message with its own reason, and the
    run goes on - the same shape as the missing-child rule beside it.

    The control is in the same test: the same frames with a usable record still get
    the corrected cell, so the two paths are not one path wearing two names.
    """
    bad = [
        {
            "parent": "CTVA",
            "child": "VYLR",
            "ex_date": "2026-10-01",
            "source_rate": 0.0,
            "new_rate": 0.0,
        }
    ]
    found = ca.vendor_spinoffs(SESSION, ["CTVA"], fetcher=lambda s, d: bad)

    assert len(found) == 1
    assert not found[0].applicable
    assert found[0].child_per_parent is None
    assert found[0].ratio_label == "no ratio"
    assert found[0].unusable_reason == (
        "source_rate 0.0 and new_rate 0.0 cannot form a share ratio"
    )

    frame, prices = ctva_frames()
    outcome = ca.apply_to_append(
        frame,
        prices,
        since=PRIOR,
        spinoffs={SESSION: found},
        child_close=lambda ticker, session: VYLR_CLOSE,
    )

    assert pd.isna(frame.loc[(SESSION, "CTVA"), "r"])
    assert float(frame.loc[(SESSION, "AAA"), "r"]) == 0.02
    assert float(frame.loc[(PRIOR, "CTVA"), "r"]) == 0.001
    # Named with the rate and not with the child: a close is not what is wrong here,
    # and the note has to be specific enough to act on.
    assert ca.unusable_spinoff_notes(outcome.spinoffs) == [
        "CTVA (source_rate 0.0 and new_rate 0.0 cannot form a share ratio)"
    ]
    assert ca.missing_child_notes(outcome.spinoffs) == []
    # Nothing was applied with it, so there is no action to record and no line
    # claiming one was.
    assert ca.describe_spinoffs(outcome.spinoffs) == []
    assert ca.spinoff_rows(outcome.spinoffs, SESSION) == []
    assert (
        notify.compose(
            status="ok",
            target_close="2026-10-01",
            spinoff_unusable=ca.unusable_spinoff_notes(outcome.spinoffs),
        ).count(
            "Spin-off record unusable, so the parent's return was nulled: CTVA "
            "(source_rate 0.0 and new_rate 0.0 cannot form a share ratio)."
        )
        == 1
    )
    flag = outcome.flags[0]
    assert flag["ticker"] == "CTVA"
    assert flag["adjusted_return"] is None
    assert flag["explained_by"] == "spinoff"
    assert "not applied" in flag["flag"] and "nulled" in flag["flag"]

    # A record that names no child is unusable for its own reason and takes the same
    # path: nulled, named, and not fatal.
    no_child = ca.vendor_spinoffs(
        SESSION,
        ["CTVA"],
        fetcher=lambda s, d: [
            {
                "parent": "CTVA",
                "child": "",
                "ex_date": "2026-10-01",
                "source_rate": 1.0,
                "new_rate": 1.0,
            }
        ],
    )
    assert no_child[0].unusable_reason == "no child symbol"
    assert no_child[0].label == "spinoff: CTVA -> ? not applied: no child symbol"
    quiet, quiet_prices = ctva_frames()
    quiet_outcome = ca.apply_to_append(
        quiet,
        quiet_prices,
        since=PRIOR,
        spinoffs={SESSION: no_child},
        child_close=lambda ticker, session: VYLR_CLOSE,
    )
    assert pd.isna(quiet.loc[(SESSION, "CTVA"), "r"])
    assert ca.unusable_spinoff_notes(quiet_outcome.spinoffs) == [
        "CTVA (no child symbol)"
    ]

    # The control: usable rates in the same frames still correct the cell.
    good, good_prices = ctva_frames()
    ca.apply_to_append(
        good,
        good_prices,
        since=PRIOR,
        spinoffs={SESSION: [a_spinoff()]},
        child_close=lambda ticker, session: VYLR_CLOSE,
    )
    assert float(good.loc[(SESSION, "CTVA"), "r"]) == pytest.approx(
        TARGET_RETURN, abs=1e-6
    )


class _ActionsClient:
    """A corporate-actions client that answers and records what it was asked."""

    def __init__(self, payload: dict[str, list[Any]]) -> None:
        self.payload = payload
        self.requests: list[Any] = []

    def get_corporate_actions(self, request: Any) -> Any:
        self.requests.append(request)
        payload = self.payload

        class _Response:
            data = payload

        return _Response()


def _bars_response(bars: dict[str, list[tuple[str, float]]]) -> Any:
    """One vendor bars response, in the shape `get_stock_bars` returns."""
    from datetime import datetime

    class _Bar:
        def __init__(self, timestamp: datetime, close: float) -> None:
            self.timestamp = timestamp
            self.close = close

    class _Response:
        data = {
            symbol: [
                _Bar(datetime.fromisoformat(stamp), close)
                for stamp, close in symbol_bars
            ]
            for symbol, symbol_bars in bars.items()
        }

    return _Response()


class _BarsClient:
    """A bars client that answers with a fixed frame per symbol."""

    def __init__(self, bars: dict[str, list[tuple[str, float]]]) -> None:
        self.bars = bars
        self.requests: list[Any] = []

    def get_stock_bars(self, request: Any) -> Any:
        self.requests.append(request)
        return _bars_response(self.bars)


def _spin_off_record(**overrides: Any) -> Any:
    """A vendor spin-off object, in the shapes alpaca-py returns."""

    class _Record:
        source_symbol = "CTVA"
        new_symbol = "VYLR"
        ex_date = date(2026, 10, 1)
        source_rate = "1"
        new_rate = "1"
        cusip = "22052L104"

    for key, value in overrides.items():
        setattr(_Record, key, value)
    return _Record


def test_the_vendor_read_asks_once_and_keeps_only_its_own_ex_dates():
    """One request for the universe, filtered by the day the endpoint was asked for.

    The window is widened by a day so a timezone boundary cannot hide the event, and
    the filter here is what makes that safe: a record dated the next day is dropped
    rather than applied to tonight's session.
    """
    client = _ActionsClient({"spin_offs": [_spin_off_record()]})

    found = alpaca.spin_offs(["CTVA", "AAA"], SESSION, client=client)

    assert len(client.requests) == 1
    request = client.requests[0]
    assert list(request.symbols) == ["AAA", "CTVA"]
    assert request.start.isoformat() == "2026-09-30"
    assert request.end.isoformat() == "2026-10-02"
    assert found == [
        {
            "parent": "CTVA",
            "child": "VYLR",
            "ex_date": date(2026, 10, 1),
            "source_rate": 1.0,
            "new_rate": 1.0,
        }
    ]

    other_day_record = _spin_off_record(ex_date=date(2026, 10, 2))
    other_day = _ActionsClient({"spin_offs": [other_day_record]})
    assert alpaca.spin_offs(["CTVA"], SESSION, client=other_day) == []


def test_the_child_close_read_is_one_request_and_only_the_session():
    """The bars read, which is only spent when the panel cannot answer.

    One request for every child that is missing, the session's own bar only (the
    endpoint's `end` is exclusive, which is why the request asks for the next day),
    and a symbol the vendor does not answer for is absent rather than zero.
    """
    client = _BarsClient(
        {
            "VYLR": [
                ("2026-10-01T04:00:00+00:00", VYLR_CLOSE),
                ("2026-10-02T04:00:00+00:00", 70.0),
            ],
            "OTHR": [],
        }
    )

    closes = alpaca.closes_on(["VYLR", "OTHR"], SESSION, client=client)

    assert len(client.requests) == 1
    request = client.requests[0]
    assert list(request.symbol_or_symbols) == ["OTHR", "VYLR"]
    # The vendor's request model normalizes both timestamps to naive UTC, so the
    # day is what this asserts: the session, and the next day as the exclusive end
    # (measured: asking for the session alone returns 19 of 20 sessions).
    assert request.start.date().isoformat() == "2026-10-01"
    assert request.end.date().isoformat() == "2026-10-02"
    assert closes == {"VYLR": VYLR_CLOSE}


def test_the_artifact_is_written_only_when_something_was_applied(tmp_path: Path):
    """The write-back, on a tree that holds the two artifacts.

    An evening with no corporate action must leave `returns.parquet` byte-identical,
    and an evening with a spin-off must carry the corrected value into the file the
    fit reads. Both are asserted on the bytes of the file, not on the frame.
    """
    from live.corporate_actions import apply_to_artifact

    root = tmp_path / "data"
    (root / "processed").mkdir(parents=True)
    (root / "raw").mkdir(parents=True)
    frame, prices = ctva_frames()
    returns_path = root / "processed" / "returns.parquet"
    frame.to_parquet(returns_path)
    prices.to_parquet(root / "raw" / "prices.parquet")

    quiet = apply_to_artifact(
        root,
        since=PRIOR,
        spinoff_fetcher=lambda symbols, session: [],
    )
    assert quiet.spinoffs == []
    assert (
        hashlib.sha256(returns_path.read_bytes()).hexdigest()
        == hashlib.sha256(frame.to_parquet() and returns_path.read_bytes()).hexdigest()
    )
    assert float(pd.read_parquet(returns_path).loc[(SESSION, "CTVA"), "r"]) == (
        pytest.approx(RAW_PRINT)
    )

    applied = apply_to_artifact(
        root,
        since=PRIOR,
        spinoff_fetcher=lambda symbols, session: [
            {
                "parent": "CTVA",
                "child": "VYLR",
                "ex_date": SESSION,
                "source_rate": 1.0,
                "new_rate": 1.0,
            }
        ],
        child_closes_fetcher=lambda children, session: {"VYLR": VYLR_CLOSE},
    )

    assert len(applied.spinoffs) == 1
    assert float(pd.read_parquet(returns_path).loc[(SESSION, "CTVA"), "r"]) == (
        pytest.approx(TARGET_RETURN, abs=1e-6)
    )


def test_a_vendor_read_that_fails_leaves_the_print_and_the_flag():
    """The fetch is the one piece here that can fail without the run failing.

    The rule is skipped for that session, which leaves exactly the position the loop
    was in before it existed: the raw print in the panel, and a flag above the 40%
    threshold that names it as an unexplained large move in the message. Visible
    rather than silent, and nothing is guessed.
    """
    from live.corporate_actions import apply_to_artifact

    root = Path("/tmp") / "efb-spinoff-read-failure"
    (root / "processed").mkdir(parents=True, exist_ok=True)
    (root / "raw").mkdir(parents=True, exist_ok=True)
    frame, prices = ctva_frames()
    frame.to_parquet(root / "processed" / "returns.parquet")
    prices.to_parquet(root / "raw" / "prices.parquet")

    def failing(symbols: list[str], session: pd.Timestamp) -> list[dict[str, Any]]:
        raise RuntimeError("the endpoint is down")

    outcome = apply_to_artifact(root, since=PRIOR, spinoff_fetcher=failing)

    assert outcome.spinoffs == []
    assert float(
        pd.read_parquet(root / "processed" / "returns.parquet").loc[
            (SESSION, "CTVA"), "r"
        ]
    ) == pytest.approx(RAW_PRINT)
    flag = {item["ticker"]: item for item in outcome.flags}["CTVA"]
    assert flag["explained_by"] is None
    assert flag["flag"] == "unexplained large move"


def test_the_message_names_the_spinoff_and_a_missing_child_close():
    """The two lines the owner reads, and the subject that must not cry wolf.

    A corrected return is explained, so the subject carries no flag count for it; a
    nulled cell is a hole in the panel that only the message can explain, so it is
    named there.
    """
    text = notify.compose(
        status="ok",
        target_close="2026-10-01",
        spinoffs=["spinoff: CTVA -> VYLR 1:1 applied"],
        spinoff_missing=["VYLR (CTVA)"],
        flags=[
            {
                "ticker": "CTVA",
                "return": RAW_PRINT,
                "adjusted_return": None,
                "explained_by": "spinoff",
                "flag": "spinoff: CTVA -> VYLR 1:1 applied, the VYLR close is "
                "missing so the return was nulled",
            }
        ],
    )
    assert "Spin-offs: spinoff: CTVA -> VYLR 1:1 applied." in text
    assert (
        "Spin-off close missing, so the parent's return was nulled: VYLR (CTVA)."
        in text
    )
    assert "Large moves: CTVA -83.8% (spinoff: CTVA -> VYLR 1:1 applied" in text
    subject = notify.subject_text(
        status="ok",
        target_close="2026-10-01",
        flags=[
            {
                "ticker": "CTVA",
                "return": RAW_PRINT,
                "explained_by": "spinoff",
                "flag": "spinoff: CTVA -> VYLR 1:1 applied",
            }
        ],
    )
    assert "flag" not in subject, subject


def test_the_rule_runs_after_the_append_and_before_the_fit():
    """The position in the evening, read from the runner's own source.

    "Before the new session's returns enter the fit" is a statement about order in
    `scripts/run_live_daily.py`: the returns are appended, then the corporate actions
    are applied, then the model is extended. A rule that ran after the fit would
    correct tomorrow's artifact and leave tonight's book priced on the print.
    """
    source = (ROOT / "scripts" / "run_live_daily.py").read_text()
    appended = source.index("extend.extend_returns()")
    applied = source.index("corporate_actions.apply_to_artifact(")
    fitted = source.index("extend.extend_model()")
    assert appended < applied < fitted


def test_the_writer_names_columns_the_table_has():
    """The column-fit check, for both kinds of row.

    `e11_corporate_actions` was created for splits and a provisioned database has
    only those columns until the additive block is applied, so the two writers are
    checked against the schema file itself: every column they name is one the file
    creates or adds. This is the check that would have caught the missing
    `position_intent` on `efb.fills` before the first live run rather than after it.
    """
    schema = (ROOT / "live" / "supabase_schema.sql").read_text()
    block = re.search(
        r"create table if not exists efb\.e11_corporate_actions \((.*?)\n\);",
        schema,
        re.DOTALL,
    )
    assert block is not None, "the corporate-actions table is not in the schema"
    columns = {
        line.strip().split()[0]
        for line in block.group(1).splitlines()
        if line.strip() and not line.strip().startswith("--")
    }
    columns -= {"primary", "key"}
    added = set(
        re.findall(
            r"alter table efb\.e11_corporate_actions\s+add column if not exists (\w+)",
            schema,
        )
    )
    for name in ("explained_by", "new_ticker", "source_rate", "new_rate"):
        assert name in columns, f"{name} is not in the create block"
        assert name in added, f"{name} has no additive alter for a live database"

    split_row = ca.rows([ca.Split("APH", SESSION, 2.0)], SESSION, {"APH": 0.5})[0]
    spinoff_row = ca.spinoff_rows(
        [ca.SpinoffOutcome(a_spinoff(), SESSION, RAW_PRINT, TARGET_RETURN, VYLR_CLOSE)],
        SESSION,
    )[0]
    assert set(split_row) <= columns, set(split_row) - columns
    assert set(spinoff_row) <= columns, set(spinoff_row) - columns
    assert ca.TABLE in store.TABLES
    assert store.TABLE_KEYS[ca.TABLE] == ("trade_date", "ticker")


def test_the_next_evening_closes_a_spun_off_child_long_and_short(
    monkeypatch: pytest.MonkeyPatch,
):
    """The book half of the rule, against the strict fake broker.

    A held parent is spun into a child the model has never heard of, so the next
    evening's proposal does not mention it and the delta has to close it. The long
    parent's child is sold to close and the short parent's child is bought to close:
    the fake broker refuses a leg that would cross zero, so the two intents are its
    own rule rather than an assumption about it.
    """
    prices = {"EEE": 100.0, "FFF": 50.0, "GGG": 20.0}
    monkeypatch.setattr(rehearse_preflip, "PRICES", dict(prices))
    # The account guard runs inside every rehearsal day, and the suite's fixture
    # removes the variable it compares against.
    monkeypatch.setenv(alpaca.ACCOUNT_ID_ENV, rehearse_preflip.ACCOUNT_NUMBER)
    broker = rehearse_preflip.FakeBroker(dict(prices))

    rehearse_preflip.run_day("2026-09-25", {"EEE": 0.08, "FFF": -0.08}, broker)
    broker.settle_open()
    broker.spinoff("EEE", "ZEE", 1.0, 25.0)
    broker.spinoff("FFF", "ZFF", 1.0, 10.0)
    assert broker.holdings["ZEE"] > 0 and broker.holdings["ZFF"] < 0

    _held, _quantities, summary, records = rehearse_preflip.run_day(
        "2026-09-28", {"GGG": 0.08}, broker
    )

    assert summary["complete"], summary["incomplete_legs"]
    intents = {
        str(row.ticker): str(row.position_intent)
        for row in records.itertuples(index=False)
    }
    assert intents["ZEE"] == alpaca.INTENT_SELL_TO_CLOSE, intents
    assert intents["ZFF"] == alpaca.INTENT_BUY_TO_CLOSE, intents
    assert intents["EEE"] == alpaca.INTENT_SELL_TO_CLOSE, intents
    assert intents["FFF"] == alpaca.INTENT_BUY_TO_CLOSE, intents
    # The children are closed to zero by the next open, and the parents with them.
    for _ in range(1):
        broker.settle_open()
    assert abs(broker.holdings.get("ZEE", 0.0)) < 1e-9
    assert abs(broker.holdings.get("ZFF", 0.0)) < 1e-9


def test_the_evening_runner_passes_the_labels_through():
    """The runner's own wiring, from the source: the message gets all three lists."""
    source = (ROOT / "scripts" / "run_live_daily.py").read_text()
    assert "corporate_actions.spinoff_rows(" in source
    assert "corporate_actions.describe_spinoffs(" in source
    assert "corporate_actions.missing_child_notes(" in source
    assert "corporate_actions.unusable_spinoff_notes(" in source
    assert "spinoff_missing=spinoff_missing," in source
    assert "spinoff_unusable=spinoff_unusable," in source
    import inspect

    for name in ("spinoffs", "spinoff_missing", "spinoff_unusable"):
        assert name in inspect.signature(run_live_daily.finish_run).parameters
        assert name in inspect.signature(notify.notify_run).parameters
        assert name in inspect.signature(notify.compose).parameters
