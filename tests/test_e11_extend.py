"""Sprint E11 live: incremental extension integrity.

Rows dated on or before 2026-09-03 in descriptors, factor_returns and
specific_returns are frozen invariants: every extension appends new
sessions without touching them. The pre-cutoff block hashes are recorded
here and asserted, and the extension must have added sessions after the
frozen as-of.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from efb import prices
from live import corporate_actions as ca
from live import extend

ROOT = Path(__file__).resolve().parents[1]
XS = ROOT / "data" / "models" / "XS-v1"

# recorded before the first extension, and unchanged after it
BASELINE = {
    "descriptors": ("8f93968f67f31cd33453a7fad13685d74748f3f480f17406954459fdd31caafa"),
    "factor_returns": (
        "42a31d64e0cb7619f09669cfdac217085172ccd577ee37c304da6bab3246700a"
    ),
    "specific_returns": (
        "176dc4b39fb75f1dae6afd0f6afea3b14c64bd6ebcc855450d392d46bd9d489a"
    ),
}


def test_block_hash_is_deterministic() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2026-09-01", "2026-09-02"],
            "ticker": ["A", "A"],
            "descriptor": ["size", "size"],
            "value": [1.0, 2.0],
        }
    )
    assert extend._block_hash(frame, pd.Timestamp("2026-09-03")) == extend._block_hash(
        frame, pd.Timestamp("2026-09-03")
    )


@pytest.mark.integration
@pytest.mark.slow
def test_pre_cutoff_blocks_are_byte_identical() -> None:
    if not (XS / "factor_returns.parquet").exists():
        pytest.skip("XS-v1 artifacts not built")
    current = extend.incremental_integrity()
    for name, expected in BASELINE.items():
        assert current[name] == expected, name


@pytest.mark.integration
def test_sessions_after_the_frozen_as_of_were_appended() -> None:
    for name in ("descriptors", "factor_returns", "specific_returns"):
        frame = pd.read_parquet(XS / f"{name}.parquet")
        last = pd.to_datetime(frame["date"]).max()
        assert last > pd.Timestamp("2026-09-03"), name


@pytest.mark.integration
@pytest.mark.slow
def test_identity_drops_do_not_reappear_in_the_extension() -> None:
    """The extension applies the E1 identity exclusions, so a reused
    symbol does not come back with another company's history. DD is the
    one dropped ticker the sector file maps, so it is the one the buggy
    extension put back into returns and specific_returns.
    """
    returns_frame = pd.read_parquet(ROOT / "data" / "processed" / "returns.parquet")
    specific = pd.read_parquet(XS / "specific_returns.parquet")
    assert "DD" not in set(returns_frame.index.get_level_values("ticker"))
    assert "DD" not in set(specific["ticker"])


def _live_tree(root: Path) -> None:
    """A tree with a four-name panel and a two-name universe."""
    (root / "raw" / "spy_holdings").mkdir(parents=True)
    (root / "processed").mkdir(parents=True)
    pd.DataFrame(
        {"ticker": ["LIVE1", "LIVE2", "DELISTED", "HELD"], "gics_sector": ["Tech"] * 4}
    ).to_parquet(root / "processed" / "sectors.parquet")
    index = pd.MultiIndex.from_product(
        [[pd.Timestamp("2026-09-21")], ["LIVE1", "LIVE2", "DELISTED", "HELD"]],
        names=["date", "ticker"],
    )
    pd.DataFrame({"ret": [0.1] * 4}, index=index).to_parquet(
        root / "processed" / "returns.parquet"
    )
    pd.DataFrame(
        {"ticker": ["LIVE1", "LIVE2"], "as_of": ["2026-09-21"] * 2}
    ).to_parquet(root / "raw" / "spy_holdings" / "spy_holdings_2026-09-21.parquet")


def test_the_fetch_is_the_live_universe_and_the_book_not_the_frozen_panel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The panel is every name the history ever held, and most are delisted.

    Asking the vendor about the panel every evening produced 206 failures a night,
    which bury the one failure that would matter. Nothing outside the universe and
    the held book can reach the book being priced, so nothing else is asked for.
    """
    from live import snapshot

    root = tmp_path / "data"
    _live_tree(root)
    book = pd.DataFrame({"ticker": ["HELD"], "weight": [1.0]})
    monkeypatch.setattr(snapshot, "previous_proposal", lambda: (None, book, None))

    # the held name is outside the universe and is still fetched
    assert extend._live_tickers(root) == ["HELD", "LIVE1", "LIVE2"]

    # a store that cannot answer leaves the universe, which is what the run needs
    # to price: the held names are a convenience, not a requirement
    def explode() -> None:
        raise RuntimeError("the store is unreachable")

    monkeypatch.setattr(snapshot, "previous_proposal", explode)
    assert extend._live_tickers(root) == ["LIVE1", "LIVE2"]

    # and the frozen panel still exists for the callers that ask for it
    assert extend._frozen_tickers(root) == ["DELISTED", "HELD", "LIVE1", "LIVE2"]


def test_the_fetch_asks_for_the_runs_own_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The window has to include the session the run is pricing.

    yfinance's `end` is exclusive, and `extend_prices` passed the run's own date as
    it, so the same-day close could never come back. On a weekday evening, whose
    previous close is already stored, the fetch then returned nothing new at all and
    the gate stopped the run one session behind its own target close, which is what
    Monday 2026-09-28 did: "prices 1 session behind the 2026-09-28 close". The vendor
    answered `start='2026-09-25', end='2026-09-28'` with 2026-09-25 alone, and with
    `end='2026-09-29'` with both, so the data was there and the window was wrong.

    The fake below is the vendor's contract rather than a convenience: it drops the
    end date, so a window that stops at the run date appends nothing and this test
    fails on the cause rather than on a mock's opinion.
    """
    from efb import prices

    root = tmp_path / "data"
    _live_tree(root)
    index = pd.MultiIndex.from_product(
        [[pd.Timestamp("2026-09-25")], ["LIVE1", "LIVE2"]], names=["date", "ticker"]
    )
    pd.DataFrame({"close": [1.0, 2.0]}, index=index).to_parquet(
        root / "raw" / "prices.parquet"
    )
    seen: dict[str, object] = {}

    def _vendor(  # noqa: ANN001
        tickers, start=None, end=None, progress=False, prewarm=False, threads=True
    ):
        seen["start"], seen["end"] = start, end
        days = pd.bdate_range(start, pd.Timestamp(end))
        frame = pd.DataFrame(
            {field: 1.0 for field in prices.FIELDS},
            index=pd.MultiIndex.from_product(
                [days, list(tickers)], names=["date", "ticker"]
            ),
        )
        # the vendor's own contract: the end date is exclusive
        return frame[frame.index.get_level_values("date") < pd.Timestamp(end)]

    monkeypatch.setattr(extend.prices, "download_prices", _vendor)

    added = extend.extend_prices(root, end="2026-09-28")

    assert seen == {"start": "2026-09-25", "end": "2026-09-29"}, seen
    assert added == 1, "the run's own close was not fetched"
    panel = pd.read_parquet(root / "raw" / "prices.parquet")
    assert str(panel.index.get_level_values("date").max().date()) == "2026-09-28"


def _long_frame(
    tickers: list[str], days: pd.DatetimeIndex, blank: list[str] | None = None
) -> pd.DataFrame:
    """A vendor-shaped long frame, with the named tickers carrying no prices."""
    frame = pd.DataFrame(
        {field: 1.0 for field in prices.FIELDS},
        index=pd.MultiIndex.from_product(
            [days, list(tickers)], names=["date", "ticker"]
        ),
    )
    for ticker in blank or []:
        frame.loc[(slice(None), ticker), ["close", "adj_close"]] = float("nan")
    return frame


def test_a_name_the_bulk_fetch_missed_is_retried_once_single_threaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The threaded pass can lose a symbol, and a lost symbol is retried.

    yfinance reports a symbol whose price fetch failed as a failed download rather
    than as an error, so the frame arrives carrying that symbol's rows and no prices
    and the evening never learns it lost a name: on 2026-09-29 that is how CSGP
    reached the book with no close. One retry, single-threaded, tells a lost race
    apart from a name that is genuinely gone: the retry is never repeated, so a
    vendor that answers for nothing costs one request per missing name and no more,
    and what it could not recover is what the book's drop rule then sees.
    """
    from efb import prices

    days = pd.bdate_range("2026-09-28", periods=2)
    calls: list[tuple[list[str], bool]] = []

    def _vendor(  # noqa: ANN001
        tickers, start=None, end=None, progress=False, prewarm=False, threads=True
    ):
        calls.append((list(tickers), threads))
        # the bulk pass loses LIVE2 and DELISTED; the single-threaded retry gets
        # LIVE2 back and never gets DELISTED, which is a name that is really gone
        blank = ["LIVE2", "DELISTED"] if threads else ["DELISTED"]
        return _long_frame(list(tickers), days, blank=blank)

    monkeypatch.setattr(extend.prices, "download_prices", _vendor)
    frame, report = extend.retry_missing_closes(
        _long_frame(["LIVE1", "LIVE2", "DELISTED"], days, blank=["LIVE2", "DELISTED"]),
        ["LIVE1", "LIVE2", "DELISTED"],
        start="2026-09-28",
        end="2026-09-30",
        session="2026-09-28",
    )

    assert calls == [(["DELISTED", "LIVE2"], False)], calls
    assert report == {
        "requested": 3,
        "session": "2026-09-28",
        "missing": ["DELISTED", "LIVE2"],
        "recovered": ["LIVE2"],
        "still_missing": ["DELISTED"],
    }
    # the recovered name carries a price and the one that is really gone does not,
    # so the book sees exactly the drop it should
    assert prices.missing_tickers(frame, ["LIVE1", "LIVE2"], session="2026-09-28") == []
    assert prices.missing_tickers(frame, ["DELISTED"], session="2026-09-28") == [
        "DELISTED"
    ]
    closes = frame.xs(pd.Timestamp("2026-09-28"), level="date")["adj_close"]
    assert not pd.isna(closes["LIVE2"]) and pd.isna(closes["DELISTED"])


def test_a_name_that_answered_for_the_earlier_sessions_is_retried_for_the_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retry has to fire on the close, not on the window, and this is why.

    2026-09-29, in the run that carried the prewarm and the retry: CSGP answered for
    the earlier sessions of the fetched window and had no bar for the close being
    priced. The window-wide check called it covered, the retry never ran, and the
    book dropped the name. The gap is the session the book is priced from, so that is
    what the retry now asks about, and a name recovered that way keeps its place.
    """
    days = pd.bdate_range("2026-09-25", "2026-09-29")
    calls: list[tuple[list[str], bool]] = []

    def _vendor(  # noqa: ANN001
        tickers, start=None, end=None, progress=False, prewarm=False, threads=True
    ):
        calls.append((list(tickers), threads))
        frame = _long_frame(list(tickers), days)
        # the bulk pass answered for the earlier sessions and not for the close; the
        # single-threaded retry is answered for the close, as the vendor would be.
        # GONE is not answered for on either pass, which is a name that is really
        # gone rather than a name that was lost.
        gone = ("CSGP", "GONE") if threads else ("GONE",)
        for ticker in gone:
            if ticker in frame.index.get_level_values("ticker"):
                frame.loc[
                    (pd.Timestamp("2026-09-29"), ticker), ["close", "adj_close"]
                ] = float("nan")
        return frame

    monkeypatch.setattr(extend.prices, "download_prices", _vendor)
    frame, report = extend.retry_missing_closes(
        _vendor(["CSGP", "GONE", "AAPL"], threads=True),
        ["CSGP", "GONE", "AAPL"],
        start="2026-09-25",
        end="2026-09-30",
        session="2026-09-29",
    )

    assert calls == [
        (["CSGP", "GONE", "AAPL"], True),
        (["CSGP", "GONE"], False),
    ], calls
    assert report["session"] == "2026-09-29"
    assert report["missing"] == ["CSGP", "GONE"]
    assert report["recovered"] == ["CSGP"]
    assert report["still_missing"] == ["GONE"]
    assert prices.missing_tickers(
        frame, ["CSGP", "GONE", "AAPL"], session="2026-09-29"
    ) == ["GONE"]


def test_a_fetch_that_answered_for_everything_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retry is for a gap, not a habit: a complete fetch makes no second call.

    Every evening would otherwise spend one more request per name on a vendor that
    was fine, and the second pass is the one that has to be single-threaded, so an
    unconditional retry would slow the run to buy nothing.
    """
    days = pd.bdate_range("2026-09-28", periods=2)
    calls: list[list[str]] = []

    def _vendor(tickers, **kwargs):  # noqa: ANN001
        calls.append(list(tickers))
        return _long_frame(list(tickers), days)

    monkeypatch.setattr(extend.prices, "download_prices", _vendor)
    frame, report = extend.retry_missing_closes(
        _long_frame(["LIVE1", "LIVE2"], days),
        ["LIVE1", "LIVE2"],
        start="2026-09-28",
        end="2026-09-30",
        session="2026-09-28",
    )

    assert calls == []
    assert report["missing"] == [] and report["recovered"] == []
    assert prices.missing_tickers(frame, ["LIVE1", "LIVE2"], session="2026-09-28") == []


def test_the_live_fetch_asks_for_the_prewarm_and_applies_the_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`extend_prices` is where both steps have to happen, on the real panel path.

    The prewarm is the fetch's own first step (`download_prices(prewarm=True)`)
    rather than a call beside it, so a caller that replaces the fetch cannot leave
    the prewarm behind and a caller that uses the fetch cannot forget it. The gap
    this test leaves is the one that failed on 2026-09-29: the name answers for the
    earlier session of the window and has no bar for the close being priced, which is
    a gap only if the retry is asked about that close. Dropping the session from the
    call here leaves the panel without the price, so the wiring is pinned by the
    failing case rather than by a name that is missing everywhere.
    """
    from live import snapshot

    root = tmp_path / "data"
    _live_tree(root)
    monkeypatch.setattr(snapshot, "previous_proposal", lambda: (None, None, None))
    index = pd.MultiIndex.from_product(
        [[pd.Timestamp("2026-09-25")], ["LIVE1", "LIVE2"]], names=["date", "ticker"]
    )
    pd.DataFrame({"close": [1.0, 2.0]}, index=index).to_parquet(
        root / "raw" / "prices.parquet"
    )
    calls: list[tuple[list[str], bool, bool]] = []
    days = pd.bdate_range("2026-09-25", "2026-09-28")

    def _vendor(  # noqa: ANN001
        tickers, start=None, end=None, progress=False, prewarm=False, threads=True
    ):
        calls.append((list(tickers), threads, prewarm))
        frame = _long_frame(list(tickers), days)
        # the bulk pass answered for the earlier session and not for the close; the
        # single-threaded retry is answered for the close, as the vendor would be
        if threads:
            frame.loc[(pd.Timestamp("2026-09-28"), "LIVE2"), ["close", "adj_close"]] = (
                float("nan")
            )
        # the fake vendor keeps the exclusive-end contract of the real one
        return frame[frame.index.get_level_values("date") < pd.Timestamp(end)]

    monkeypatch.setattr(extend.prices, "download_prices", _vendor)

    added = extend.extend_prices(root, end="2026-09-28")

    assert calls == [
        (["LIVE1", "LIVE2"], True, True),
        (["LIVE2"], False, False),
    ], calls
    assert added == 1
    panel = pd.read_parquet(root / "raw" / "prices.parquet")
    session = panel.xs(pd.Timestamp("2026-09-28"), level="date")
    # the name the bulk pass missed on the close is in the panel with a real price,
    # because the retry's row replaced the empty one
    assert not pd.isna(session.loc["LIVE2", "close"])


# --- recorded spin-offs, put back by the returns rebuild ------------------------
#
# A spin-off moves one session's return and neither vendor adjusts history for it,
# so the stored prices alone always produce the raw print: CTVA closed 77.65 on
# 2026-09-30 and printed 12.57 the next day (-83.81%) while the holder was also
# given a VYLR share worth 68.26. The cell was corrected by the append path and
# then recomputed away, which is what the 2026-10-01 run did: it flagged the print
# as an unexplained large move and the whole 2026-10-02 cross-section was built from
# it. `extend_returns` recomputes every session from those prices, so the correction
# has to be re-applied from its record every evening.

CTVA = "CTVA"
VYLR = "VYLR"
BEFORE = pd.Timestamp("2026-09-29")
PRIOR = pd.Timestamp("2026-09-30")
EX_DATE = pd.Timestamp("2026-10-01")
NEXT = pd.Timestamp("2026-10-02")
# the closes the appendix carries, to the last bit
BEFORE_CLOSE = 77.870002746582
PARENT_PREVIOUS_CLOSE = 77.6500015258789
PARENT_CLOSE = 12.5699996948242
CHILD_CLOSE = 68.2600021362305
PARENT_NEXT_CLOSE = 11.9200000762939
CHILD_NEXT_CLOSE = 67.2600021362305
# 12.57 / 77.65 - 1: what the fit read as a return before this rule existed
RAW_PRINT = PARENT_CLOSE / PARENT_PREVIOUS_CLOSE - 1.0
# the same session's own return, which must not move
PRIOR_RETURN = PARENT_PREVIOUS_CLOSE / BEFORE_CLOSE - 1.0
# (12.57 + 1 x 68.26) / 77.65 - 1, which prints as +4.10%
TOTAL_RETURN = (PARENT_CLOSE + CHILD_CLOSE) / PARENT_PREVIOUS_CLOSE - 1.0


def _returns_tree(root: Path) -> None:
    """A tree `extend_returns` can run on, carrying the real spin-off closes."""
    (root / "raw").mkdir(parents=True)
    (root / "processed").mkdir(parents=True)
    rows = [
        (BEFORE, CTVA, BEFORE_CLOSE),
        (PRIOR, CTVA, PARENT_PREVIOUS_CLOSE),
        (EX_DATE, CTVA, PARENT_CLOSE),
        (NEXT, CTVA, PARENT_NEXT_CLOSE),
        (EX_DATE, VYLR, CHILD_CLOSE),
        (NEXT, VYLR, CHILD_NEXT_CLOSE),
        (PRIOR, "AAA", 50.0),
        (EX_DATE, "AAA", 51.0),
        (NEXT, "AAA", 52.0),
    ]
    index = pd.MultiIndex.from_tuples(
        [(day, ticker) for day, ticker, _ in rows], names=["date", "ticker"]
    )
    prices_frame = pd.DataFrame(
        {"close": [close for *_, close in rows], "adj_close": [row[2] for row in rows]},
        index=index,
    )
    prices_frame.to_parquet(root / "raw" / "prices.parquet")
    pd.DataFrame(
        {"rf": 0.0}, index=pd.DatetimeIndex([BEFORE, PRIOR, EX_DATE, NEXT])
    ).to_parquet(root / "raw" / "factors_ff.parquet")
    # the returns file the rebuild reads its "sessions before" count from
    pd.DataFrame(
        {"r": [PRIOR_RETURN]},
        index=pd.MultiIndex.from_tuples([(PRIOR, CTVA)], names=["date", "ticker"]),
    ).to_parquet(root / "processed" / "returns.parquet")
    pd.DataFrame(columns=["action"]).to_parquet(
        root / "processed" / "ticker_identity.parquet"
    )


def _record(**overrides: object) -> pd.DataFrame:
    """One row of `efb.e11_corporate_actions`, in the shape the rule writes."""
    row: dict[str, object] = {
        "trade_date": "2026-10-01",
        "ticker": CTVA,
        "effective_date": "2026-10-01",
        "factor": 1.0,
        "source": "alpaca.corporate_actions",
        "cross_check_ratio": None,
        "explained_by": "spinoff",
        "new_ticker": VYLR,
        "source_rate": 1.0,
        "new_rate": 1.0,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _rebuilt(root: Path) -> pd.DataFrame:
    return pd.read_parquet(root / "processed" / "returns.parquet")


def test_the_rebuild_puts_the_recorded_spinoff_back_from_the_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cell becomes the total return, derived from the stored closes.

    Nothing is typed in: the record supplies the ratio and the five closes come from
    the panel, so the number is `spinoff_return`'s and the session before it is the
    arithmetic it already was.
    """
    root = tmp_path / "data"
    _returns_tree(root)
    monkeypatch.setattr(extend.store, "select", lambda table: _record())

    assert extend.extend_returns(root) == 3

    frame = _rebuilt(root)
    value = float(frame.loc[(EX_DATE, CTVA), "r"])
    assert value == pytest.approx(TOTAL_RETURN, abs=1e-12)
    assert value == pytest.approx(0.04095299733015434, abs=1e-12)
    assert f"{value * 100:+.2f}%" == "+4.10%", "the number the owner checked by hand"
    assert float(frame.loc[(EX_DATE, CTVA), "g"]) == pytest.approx(math.log1p(value))
    # the next session's return is a ratio of two stored closes, and it did not move
    moved = float(frame.loc[(NEXT, CTVA), "r"])
    assert moved == pytest.approx(PARENT_NEXT_CLOSE / PARENT_CLOSE - 1.0)
    assert f"{moved * 100:+.3f}%" == "-5.171%"
    # the session before the spin-off and another name are exactly as computed
    assert float(frame.loc[(PRIOR, CTVA), "r"]) == pytest.approx(PRIOR_RETURN)
    assert float(frame.loc[(EX_DATE, "AAA"), "r"]) == pytest.approx(51.0 / 50.0 - 1.0)


@pytest.mark.parametrize(
    "source", ["manual.record", "alpaca.corporate_actions", "anything.else"]
)
def test_the_source_column_does_not_gate_a_recorded_spinoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    """A row the rule reads is a row `explained_by` "spinoff", whatever wrote it.

    The live CTVA row is `manual.record`, written by `scripts/record_spinoff.py` for
    the case where the vendor's own table had nothing to apply. `recorded_spinoffs`
    reads the table and hands the rows to `spinoffs_from_rows`, which selects on
    `explained_by` and carries `source` into the record for the message without ever
    comparing it. So the correction lands from any source, and the cell holds the
    session's total return, +4.10%, rather than the -83.81% raw print.
    """
    root = tmp_path / "data"
    _returns_tree(root)
    record = _record(source=source)
    monkeypatch.setattr(extend.store, "select", lambda table: record)

    recorded = extend.recorded_spinoffs()
    assert [entry.source for entry in recorded] == [source]
    assert recorded[0].applicable, "a manual row is as usable as the vendor's"

    extend.extend_returns(root)

    frame = _rebuilt(root)
    value = float(frame.loc[(EX_DATE, CTVA), "r"])
    assert value == pytest.approx(TOTAL_RETURN, abs=1e-12)
    assert value == pytest.approx(0.04095299733015434, abs=1e-12)
    assert f"{value * 100:+.2f}%" == "+4.10%"
    assert value != pytest.approx(RAW_PRINT), "the raw print is what this removes"
    assert f"{RAW_PRINT * 100:+.2f}%" == "-83.81%"
    assert float(frame.loc[(EX_DATE, CTVA), "g"]) == pytest.approx(math.log1p(value))


def test_running_the_rebuild_again_writes_the_same_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Twice writes one number, because the value is never read back.

    This is the whole point of doing it here: the evening after the correction, the
    rebuild recomputes the session from prices, so a correction that compounded or
    that was kept only in the returns file would either drift or vanish.
    """
    root = tmp_path / "data"
    _returns_tree(root)
    monkeypatch.setattr(extend.store, "select", lambda table: _record())

    extend.extend_returns(root)
    first = _rebuilt(root)
    extend.extend_returns(root)
    second = _rebuilt(root)

    first_value = float(first.loc[(EX_DATE, CTVA), "r"])
    assert first_value == pytest.approx(TOTAL_RETURN)
    assert first_value == float(second.loc[(EX_DATE, CTVA), "r"])
    pd.testing.assert_frame_equal(first, second)


def test_without_a_record_the_raw_print_is_what_the_rebuild_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: -83.81%, which is the move the 2026-10-01 run flagged.

    A store with nothing recorded leaves the arithmetic alone, so what the test above
    measures is the record and not the fixture.
    """
    root = tmp_path / "data"
    _returns_tree(root)
    monkeypatch.setattr(extend.store, "select", lambda table: pd.DataFrame())

    extend.extend_returns(root)

    frame = _rebuilt(root)
    value = float(frame.loc[(EX_DATE, CTVA), "r"])
    assert value == pytest.approx(RAW_PRINT)
    assert f"{value * 100:+.2f}%" == "-83.81%"
    assert bool(frame.loc[(EX_DATE, CTVA), "outlier"]), "the move the run had to flag"


def test_a_split_row_is_not_re_applied_as_a_spinoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A factor in this table is not evidence of a spin-off: `explained_by` says which.

    The split path computes with the raw close on the appended session, so treating
    its row as a spin-off here would divide a prior close by a child that does not
    exist. The parent's cell is left to the arithmetic the run already did.
    """
    root = tmp_path / "data"
    _returns_tree(root)
    split = _record(explained_by="split", factor=2.0, new_ticker=None)
    monkeypatch.setattr(extend.store, "select", lambda table: split)

    extend.extend_returns(root)

    assert float(_rebuilt(root).loc[(EX_DATE, CTVA), "r"]) == pytest.approx(RAW_PRINT)


def test_the_ratio_comes_from_the_record_rather_than_from_a_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 1:2 record is a different total return, and the record is what decides it."""
    root = tmp_path / "data"
    _returns_tree(root)
    monkeypatch.setattr(
        extend.store,
        "select",
        lambda table: _record(factor=0.5, source_rate=2.0, new_rate=1.0),
    )

    extend.extend_returns(root)

    value = float(_rebuilt(root).loc[(EX_DATE, CTVA), "r"])
    assert value == pytest.approx(
        (PARENT_CLOSE + 0.5 * CHILD_CLOSE) / PARENT_PREVIOUS_CLOSE - 1.0, abs=1e-12
    )
    assert value != pytest.approx(TOTAL_RETURN), "the ratio was assumed"


def test_a_record_whose_child_close_is_missing_nulls_that_one_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hole the hygiene layer reports, rather than the raw print left standing."""
    root = tmp_path / "data"
    _returns_tree(root)
    panel = pd.read_parquet(root / "raw" / "prices.parquet")
    missing_child = (panel.index.get_level_values("date") == EX_DATE) & (
        panel.index.get_level_values("ticker") == VYLR
    )
    panel.loc[~missing_child].to_parquet(root / "raw" / "prices.parquet")
    monkeypatch.setattr(extend.store, "select", lambda table: _record())

    extend.extend_returns(root)

    frame = _rebuilt(root)
    assert pd.isna(frame.loc[(EX_DATE, CTVA), "r"])
    assert pd.isna(frame.loc[(EX_DATE, CTVA), "g"])
    assert pd.isna(frame.loc[(EX_DATE, CTVA), "r"]), "the print would be a lie"
    assert float(frame.loc[(NEXT, CTVA), "r"]) == pytest.approx(
        PARENT_NEXT_CLOSE / PARENT_CLOSE - 1.0
    ), "only the one cell is the rule's business"


def test_the_reader_takes_the_rows_the_rule_writes() -> None:
    """`spinoff_rows` writes them and this reads them back, field for field."""
    records = ca.spinoffs_from_rows(_record())

    assert [record.parent for record in records] == [CTVA]
    assert records[0].child == VYLR
    assert records[0].ex_date == EX_DATE
    assert records[0].child_per_parent == 1.0
    assert records[0].source == "alpaca.corporate_actions"
    assert records[0].applicable

    # a store that predates the column reads as no records, not as a table of splits
    assert ca.spinoffs_from_rows(_record().drop(columns=["explained_by"])) == []

    # a row that cannot form a ratio is kept, so its parent's cell is nulled
    unusable = ca.spinoffs_from_rows(_record(new_ticker=None))
    assert unusable[0].child_per_parent is None
    assert unusable[0].unusable_reason == "no child symbol"
    assert ca.spinoffs_from_rows(_record(factor=None))[0].unusable_reason == (
        "factor None cannot form a share ratio"
    )


def test_a_store_that_cannot_answer_stops_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rebuild's own record is not what the evening prices: warn and carry on."""

    def explode(table: str) -> None:
        raise RuntimeError("the store is unreachable")

    monkeypatch.setattr(extend.store, "select", explode)

    assert extend.recorded_spinoffs() == []
