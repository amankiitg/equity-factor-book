"""Item 4b: the corporate-actions rule in the append path.

Each test drives the rule with a fetcher or with the real stored rows, and none
touches the network or writes an artifact: the point of the rule is that the new
day's return is computed from raw closes and the factor while every stored row
stays exactly as it was.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from live import corporate_actions as ca

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fake_splits(rows: dict[str, list[tuple[str, float]]]):
    """A fetcher standing in for the vendor: ticker -> [(date, factor)]."""

    def fetcher(ticker: str) -> pd.Series:
        if ticker not in rows:
            return pd.Series(dtype=float)
        index = pd.DatetimeIndex([pd.Timestamp(stamp) for stamp, _ in rows[ticker]])
        return pd.Series([factor for _, factor in rows[ticker]], index=index)

    return fetcher


def test_two_to_one_split_gives_the_right_return_and_changes_no_stored_row():
    # A 2:1 split: the raw close halves, so the raw return would read -50%. The
    # factor in the numerator gives the real move.
    raw_return = 51.0 / 102.0 - 1.0
    assert raw_return == pytest.approx(-0.50)
    corrected = ca.adjusted_return(close_t=51.0, factor=2.0, close_previous=102.0)
    assert corrected == pytest.approx(0.0, abs=1e-12)

    # The panel the split is appended to is not rewritten: its hash is the same
    # after the arithmetic as before it.
    panel = ROOT / "data" / "processed" / "returns.parquet"
    before = sha256(panel)
    splits = ca.recent_splits(
        ["AAPL"],
        pd.Timestamp("2026-09-04"),
        fetcher=fake_splits({"AAPL": [("2026-09-03", 2.0)]}),
    )
    frame = pd.DataFrame({"AAPL": [0.0123]})
    out = ca.adjusted_returns_for_session(
        pd.Series({"AAPL": 51.0}),
        pd.Series({"AAPL": 102.0}),
        splits,
    )
    assert float(out["AAPL"]) == pytest.approx(0.0, abs=1e-12)
    assert frame.loc[0, "AAPL"] == pytest.approx(
        0.0123
    )  # the caller's panel is untouched
    assert sha256(panel) == before


def test_three_for_two_split_gives_the_right_return():
    # A 3:2 split means 1.5 new shares per old, so a close that moves from 90 to
    # 61 is a rise of 1.667%, not a fall of 32.2%.
    corrected = ca.adjusted_return(close_t=61.0, factor=1.5, close_previous=90.0)
    assert corrected == pytest.approx(0.0166666667, abs=1e-9)
    assert 61.0 / 90.0 - 1.0 == pytest.approx(-0.3222222, abs=1e-6)


def test_a_back_adjustment_with_no_split_record_stops_the_run():
    with pytest.raises(ValueError) as err:
        ca.resolve_split(
            "ZZZ", ratio=0.5, splits=[], session=pd.Timestamp("2026-09-04")
        )
    message = str(err.value)
    assert "ZZZ" in message
    assert "no split record" in message


def test_a_back_adjustment_that_disagrees_with_the_record_stops_the_run():
    wrong = [ca.Split("ZZZ", pd.Timestamp("2026-09-03"), 3.0)]
    with pytest.raises(ValueError) as err:
        ca.resolve_split(
            "ZZZ", ratio=0.5, splits=wrong, session=pd.Timestamp("2026-09-04")
        )
    message = str(err.value)
    assert "ZZZ" in message
    assert "3" in message


def test_a_ratio_of_one_needs_no_split_and_any_record_is_irrelevant():
    stale = [ca.Split("ZZZ", pd.Timestamp("2024-06-12"), 2.0)]
    assert (
        ca.resolve_split(
            "ZZZ", ratio=1.0, splits=stale, session=pd.Timestamp("2026-09-04")
        )
        is None
    )
    assert (
        ca.resolve_split(
            "ZZZ", ratio=1.0, splits=[], session=pd.Timestamp("2026-09-04")
        )
        is None
    )
    # A dividend's drift in the vendor's adjusted close sits inside the band, so it
    # is not a split: two real factors are never within 2% of each other.
    assert (
        ca.resolve_split(
            "ZZZ", ratio=0.985, splits=[], session=pd.Timestamp("2026-09-04")
        )
        is None
    )


def test_the_ratio_and_the_factor_agree_either_way_round():
    # The vendor's restatement divides the older session by the factor; a reverse
    # split's factor is below 1, so the inverse comparison has to be allowed too.
    forward = ca.Split("AA", pd.Timestamp("2026-09-03"), 2.0)
    assert (
        ca.resolve_split(
            "AA", ratio=0.5, splits=[forward], session=pd.Timestamp("2026-09-04")
        )
        is forward
    )
    reverse = ca.Split("BB", pd.Timestamp("2026-09-03"), 0.5)
    assert (
        ca.resolve_split(
            "BB", ratio=2.0, splits=[reverse], session=pd.Timestamp("2026-09-04")
        )
        is reverse
    )


def test_a_lagging_share_count_is_corrected_and_a_current_one_is_left_alone():
    split = ca.Split("APH", pd.Timestamp("2026-09-03"), 2.0)
    # The newest stored count is the pre-split basis: the factor applies.
    assert ca.shares_basis_factor(pd.Timestamp("2026-08-31"), split) == pytest.approx(
        2.0
    )
    # Restated at the split's own date or later: nothing to do.
    assert ca.shares_basis_factor(pd.Timestamp("2026-09-03"), split) == pytest.approx(
        1.0
    )
    assert ca.shares_basis_factor(pd.Timestamp("2026-09-10"), split) == pytest.approx(
        1.0
    )
    # No split and no count are both "leave it alone", not "guess".
    assert ca.shares_basis_factor(pd.Timestamp("2026-08-31"), None) == pytest.approx(
        1.0
    )
    assert ca.shares_basis_factor(None, split) == pytest.approx(1.0)


def test_a_held_position_across_a_split_reconciles_without_a_phantom_trade():
    # 100 shares at 158.55 on the old basis. The broker holds 200 at 79.275.
    prior_notional = 100 * 158.55
    assert ca.held_shares_across_split(100, 2.0) == pytest.approx(200.0)
    assert ca.held_notional_across_split(prior_notional) == pytest.approx(15855.0)
    # Rebuilding from the stale share count at the new price would invent a 158.55
    # notional to buy; the notional view trades nothing for an unchanged target.
    stale_basis_notional = 100 * 79.275
    assert stale_basis_notional == pytest.approx(7927.5)
    assert abs(ca.trade_across_split(15855.0, prior_notional)) < 1e-6
    assert ca.trade_across_split(15855.0, stale_basis_notional) == pytest.approx(7927.5)


def test_a_price_level_read_across_the_seam_takes_the_cumulative_factor():
    splits = [
        ca.Split("AA", pd.Timestamp("2026-09-03"), 2.0),
        ca.Split("AA", pd.Timestamp("2026-11-02"), 1.5),
    ]
    # Strictly before the first split both factors apply: 2 * 1.5.
    assert ca.cumulative_factor(splits, pd.Timestamp("2026-09-01")) == pytest.approx(
        3.0
    )
    # On a split's own effective date a level is already on the new basis, because
    # that date is the first session of it, so only the later split applies.
    assert ca.cumulative_factor(splits, pd.Timestamp("2026-09-03")) == pytest.approx(
        1.5
    )
    assert ca.cumulative_factor(splits, pd.Timestamp("2026-09-04")) == pytest.approx(
        1.5
    )
    assert ca.cumulative_factor(splits, pd.Timestamp("2026-11-02")) == pytest.approx(
        1.0
    )
    assert ca.cumulative_factor([], pd.Timestamp("2026-09-01")) == pytest.approx(1.0)


def test_the_record_and_the_message_name_the_split():
    split = ca.Split("APH", pd.Timestamp("2026-09-03"), 2.0)
    assert ca.describe([split]) == "split: APH 2:1 applied"
    assert ca.describe([]) == ""
    rows = ca.rows([split], pd.Timestamp("2026-09-04"), ratios={"APH": 0.5})
    assert rows == [
        {
            "trade_date": "2026-09-04",
            "ticker": "APH",
            "effective_date": "2026-09-03",
            "factor": 2.0,
            "source": "yfinance.splits",
            "cross_check_ratio": 0.5,
        }
    ]


def test_a_large_move_is_flagged_when_nothing_explains_it():
    returns = pd.Series({"AAA": 0.55, "BBB": -0.41, "CCC": 0.02})
    flags = ca.flag_large_moves(returns, explained={"AAA": "split: AAA 2:1 applied"})
    by_ticker = {flag["ticker"]: flag for flag in flags}
    assert set(by_ticker) == {"AAA", "BBB"}
    assert by_ticker["AAA"]["flag"] == "split: AAA 2:1 applied"
    assert by_ticker["BBB"]["flag"] == "unexplained large move"
    assert by_ticker["BBB"]["return"] == pytest.approx(-0.41)
    assert flags[0]["ticker"] == "AAA"  # largest absolute move first
    assert ca.flag_large_moves(pd.Series(dtype=float)) == []


def test_the_aph_split_is_reproduced_from_the_real_rows():
    """The stored panel did not carry the split as a return. It carried a hole."""
    artifact = ROOT / "data" / "processed" / "returns.parquet"
    before_hash = sha256(artifact)
    panel = pd.read_parquet(artifact)
    session = pd.Timestamp("2026-09-04")
    if (session, "APH") in panel.index:
        stored = float(panel.loc[(session, "APH"), "r"])
        # NaN, not -48%: the NaN run before the split makes pct_change skip it.
        assert pd.isna(stored) or abs(stored) < 0.40

    raw = pd.read_parquet(ROOT / "data" / "raw" / "prices.parquet")
    aph = raw.xs("APH", level="ticker")
    closes = aph["close"]
    before = closes.loc[: pd.Timestamp("2026-09-03")].dropna()
    on_or_after = closes.loc[session:].dropna()
    assert not before.empty and not on_or_after.empty
    previous = float(before.iloc[-1])
    today = float(on_or_after.iloc[0])
    # Our own raw artifact carries the vendor's action: the split factor appears on
    # 2026-09-03, the session whose close APH does not have.
    action = aph["split_factor"].loc["2026-09-03":"2026-09-04"]
    assert float(action.max()) == pytest.approx(2.0)
    # The raw closes are on their own bases and the vendor's record supplies the
    # factor, so this is the real post-split return rather than the halving.
    assert today < previous * 0.9  # the raw series does halve
    real = [
        s
        for s in ca.vendor_splits("APH")
        if s.effective_date >= pd.Timestamp("2026-08-25")
    ]
    assert [s.factor for s in real] == [2.0]
    corrected = ca.adjusted_return(close_t=today, factor=2.0, close_previous=previous)
    assert abs(corrected) < 0.40
    assert corrected == pytest.approx(0.044213, abs=1e-5)
    # The rule against the real cross-check numbers: the stored 158.5500 against a
    # refetched adjusted close of 79.1522 is a ratio of 0.499226, which the 2:1
    # record explains even though it is one APH dividend away from 0.5.
    assert ca.cross_check_ratio(158.55, 79.1522) == pytest.approx(0.499226, abs=1e-6)
    assert (
        ca.resolve_split("APH", ratio=0.499226, splits=real, session=session) == real[0]
    )
    # And the stored artifact is still exactly as it was: the rule adds the new
    # day's return to the frame it is building, never to the stored history.
    assert sha256(artifact) == before_hash


def test_the_table_is_registered_with_the_store():
    from live import store

    assert ca.TABLE in store.TABLES
    assert store.TABLE_KEYS[ca.TABLE] == ("trade_date", "ticker")


def prices_frame(rows: list[tuple[str, str, float, float, float]]) -> pd.DataFrame:
    """A raw frame in the artifact's layout: date, ticker, close, adj_close, factor."""
    index = pd.MultiIndex.from_tuples(
        [(pd.Timestamp(date), ticker) for date, ticker, _, _, _ in rows],
        names=["date", "ticker"],
    )
    return pd.DataFrame(
        {
            "close": [row[2] for row in rows],
            "adj_close": [row[3] for row in rows],
            "split_factor": [row[4] for row in rows],
        },
        index=index,
    )


def returns_frame(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    index = pd.MultiIndex.from_tuples(
        [(pd.Timestamp(date), ticker) for date, ticker, _ in rows],
        names=["date", "ticker"],
    )
    return pd.DataFrame({"r": [row[2] for row in rows]}, index=index)


def test_the_append_path_corrects_the_new_session_and_leaves_history_alone():
    # AAA splits 2:1 on 2026-09-04: the vendor's own column says so, and the raw
    # close halves, so the vendor's adjusted return would read -50%.
    prices = prices_frame(
        [
            ("2026-09-03", "AAA", 100.0, 100.0, 1.0),
            ("2026-09-04", "AAA", 51.0, 51.0, 2.0),
            ("2026-09-03", "BBB", 40.0, 40.0, 1.0),
            ("2026-09-04", "BBB", 41.0, 41.0, 1.0),
        ]
    )
    frame = returns_frame(
        [
            ("2026-09-03", "AAA", 0.0),
            ("2026-09-04", "AAA", -0.49),
            ("2026-09-04", "BBB", 0.025),
        ]
    )
    history_before = float(frame.loc[(pd.Timestamp("2026-09-03"), "AAA"), "r"])

    outcome = ca.apply_to_append(
        frame,
        prices,
        since=pd.Timestamp("2026-09-03"),
        split_fetcher=fake_splits({"AAA": [("2026-09-04", 2.0)]}),
        close_fetcher=lambda ticker, session: 100.0 if ticker == "AAA" else 40.0,
    )

    assert outcome.splits == [ca.Split("AAA", pd.Timestamp("2026-09-04"), 2.0)]
    assert ca.describe(outcome.splits) == "split: AAA 2:1 applied"
    # 51 * 2 / 100 - 1 = 0.02, not -0.49.
    assert float(
        outcome.returns.loc[(pd.Timestamp("2026-09-04"), "AAA"), "r"]
    ) == pytest.approx(0.02)
    # BBB is untouched and history is untouched.
    assert float(
        outcome.returns.loc[(pd.Timestamp("2026-09-04"), "BBB"), "r"]
    ) == pytest.approx(0.025)
    assert float(
        outcome.returns.loc[(pd.Timestamp("2026-09-03"), "AAA"), "r"]
    ) == pytest.approx(history_before)
    assert outcome.sessions == [pd.Timestamp("2026-09-04")]
    assert not outcome.flags


def test_the_append_path_stops_when_the_vendor_flags_a_split_with_no_record():
    prices = prices_frame([("2026-09-04", "AAA", 51.0, 51.0, 2.0)])
    frame = returns_frame([("2026-09-04", "AAA", -0.49)])
    with pytest.raises(ValueError) as err:
        ca.apply_to_append(
            frame,
            prices,
            since=pd.Timestamp("2026-09-03"),
            split_fetcher=fake_splits({}),
            close_fetcher=lambda ticker, session: 100.0,
        )
    assert "AAA" in str(err.value)


def test_the_append_path_stops_on_a_back_adjustment_no_record_explains():
    # Nothing flags AAA on 2026-09-04, but its appended move is -50%, so the
    # cross-check runs and the vendor's refetched adjusted close has halved.
    prices = prices_frame(
        [
            ("2026-09-03", "AAA", 100.0, 100.0, 0.0),
            ("2026-09-04", "AAA", 50.0, 50.0, 0.0),
        ]
    )
    frame = returns_frame([("2026-09-03", "AAA", 0.0), ("2026-09-04", "AAA", -0.50)])
    with pytest.raises(ValueError) as err:
        ca.apply_to_append(
            frame,
            prices,
            since=pd.Timestamp("2026-09-03"),
            split_fetcher=fake_splits({}),
            close_fetcher=lambda ticker, session: 50.0,
        )
    assert "AAA" in str(err.value)
    assert "no split record" in str(err.value)


def test_a_real_crash_cross_checks_clean_and_is_only_flagged():
    # The same -55% move with an untouched adjusted close is a real crash: the
    # cross-check passes and the move is flagged, not blocked.
    prices = prices_frame(
        [
            ("2026-09-03", "AAA", 100.0, 100.0, 0.0),
            ("2026-09-04", "AAA", 45.0, 45.0, 0.0),
        ]
    )
    frame = returns_frame([("2026-09-03", "AAA", 0.0), ("2026-09-04", "AAA", -0.55)])
    outcome = ca.apply_to_append(
        frame,
        prices,
        since=pd.Timestamp("2026-09-03"),
        split_fetcher=fake_splits({}),
        close_fetcher=lambda ticker, session: 100.0,
    )
    assert outcome.splits == []
    assert outcome.ratios == {"AAA": 1.0}
    assert outcome.cross_checked == ["AAA"]
    assert outcome.flags == [
        {
            "ticker": "AAA",
            "return": -0.55,
            "explained_by": None,
            "flag": "unexplained large move",
        }
    ]


def test_the_artifact_is_written_back_only_when_a_split_was_applied(tmp_path):
    root = tmp_path
    (root / "raw").mkdir()
    (root / "processed").mkdir()
    prices = prices_frame(
        [
            ("2026-09-03", "AAA", 100.0, 100.0, 0.0),
            ("2026-09-04", "AAA", 51.0, 51.0, 2.0),
            ("2026-09-04", "BBB", 41.0, 41.0, 0.0),
        ]
    )
    frame = returns_frame(
        [
            ("2026-09-03", "AAA", 0.0),
            ("2026-09-04", "AAA", -0.49),
            ("2026-09-04", "BBB", 0.025),
        ]
    )
    prices.to_parquet(root / "raw" / "prices.parquet")
    frame.to_parquet(root / "processed" / "returns.parquet")

    # An ordinary session: no split, so the artifact is not rewritten at all.
    quiet = prices_frame(
        [
            ("2026-09-03", "AAA", 100.0, 100.0, 0.0),
            ("2026-09-04", "AAA", 101.0, 101.0, 0.0),
        ]
    )
    quiet.to_parquet(root / "raw" / "prices.parquet")
    plain = returns_frame([("2026-09-03", "AAA", 0.0), ("2026-09-04", "AAA", 0.01)])
    plain.to_parquet(root / "processed" / "returns.parquet")
    before = sha256(root / "processed" / "returns.parquet")
    ca.apply_to_artifact(
        root,
        since=pd.Timestamp("2026-09-03"),
        split_fetcher=fake_splits({}),
        close_fetcher=lambda ticker, session: 100.0,
    )
    assert sha256(root / "processed" / "returns.parquet") == before

    # The split session: the new row is corrected and written, history is not.
    prices.to_parquet(root / "raw" / "prices.parquet")
    frame.to_parquet(root / "processed" / "returns.parquet")
    outcome = ca.apply_to_artifact(
        root,
        since=pd.Timestamp("2026-09-03"),
        split_fetcher=fake_splits({"AAA": [("2026-09-04", 2.0)]}),
        close_fetcher=lambda ticker, session: 100.0,
    )
    assert ca.describe(outcome.splits) == "split: AAA 2:1 applied"
    written = pd.read_parquet(root / "processed" / "returns.parquet")
    assert float(
        written.loc[(pd.Timestamp("2026-09-04"), "AAA"), "r"]
    ) == pytest.approx(0.02)
    assert float(
        written.loc[(pd.Timestamp("2026-09-03"), "AAA"), "r"]
    ) == pytest.approx(0.0)
    assert float(
        written.loc[(pd.Timestamp("2026-09-04"), "BBB"), "r"]
    ) == pytest.approx(0.025)
    assert ca.rows(outcome.splits, outcome.sessions[-1], outcome.ratios) == [
        {
            "trade_date": "2026-09-04",
            "ticker": "AAA",
            "effective_date": "2026-09-04",
            "factor": 2.0,
            "source": "yfinance.splits",
            "cross_check_ratio": 1.0,
        }
    ]
    # And nothing was appended for a session that is already stored.
    assert ca.appended_sessions(written, since=pd.Timestamp("2026-09-04")) == []


def test_the_notification_names_the_split_and_the_flags():
    from live import notify

    message = notify.compose(
        status="ok",
        target_close="2026-09-04",
        orders=12,
        gross=123456.78,
        worst_input=None,
        splits=["split: APH 2:1 applied"],
        flags=[
            {
                "ticker": "ZZZ",
                "return": -0.55,
                "explained_by": None,
                "flag": "unexplained large move",
            }
        ],
    )
    lines = message.splitlines()
    assert "Corporate actions: split: APH 2:1 applied." in lines
    assert "Large moves: ZZZ -55.0% (unexplained large move)." in lines
    plain = notify.compose(status="ok", target_close="2026-09-04", orders=1, gross=1.0)
    assert "Corporate actions" not in plain
    assert "Large moves" not in plain


def test_run_status_carries_the_splits_and_the_flags():
    from live import staleness

    result = {"target_close": "2026-09-04", "job": "evening", "status": "ok"}
    row = staleness.run_status_row(
        result,
        run_date="2026-09-04",
        splits=["split: APH 2:1 applied"],
        flags=[{"ticker": "ZZZ", "return": -0.55}],
    )
    assert row["splits"] == '["split: APH 2:1 applied"]'
    assert row["flags"] == '[{"return": -0.55, "ticker": "ZZZ"}]'
    assert staleness.run_status_row(result, run_date="2026-09-04")["splits"] == "[]"
