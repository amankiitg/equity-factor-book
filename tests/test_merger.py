"""The third corporate-action shape: a cash-and-stock merger.

A merger ends the target's series: one completion-session total return, computed from
the acquirer's close and the cash leg, and no row after it. These are the tests for
merger_return, mergers_from_rows and apply_recorded_mergers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from live import corporate_actions as ca

KVUE, KMB = "KVUE", "KMB"
BEFORE = pd.Timestamp("2026-10-30")
COMPLETION = pd.Timestamp("2026-11-02")
NEXT = pd.Timestamp("2026-11-03")
KVUE_PREV_CLOSE = 19.31
KMB_CLOSE = 108.25
RATIO = 0.14625
CASH = 3.50
# (0.14625 x 108.25 + 3.50) / 19.31 - 1 = +11.17 bp, the doc's measured numbers
TOTAL_RETURN = (RATIO * KMB_CLOSE + CASH) / KVUE_PREV_CLOSE - 1.0


def test_merger_return_is_the_consideration_over_the_prior_close() -> None:
    value = ca.merger_return(
        target_previous_close=KVUE_PREV_CLOSE,
        acquirer_close=KMB_CLOSE,
        acquirer_per_target=RATIO,
        cash_per_share=CASH,
    )
    assert value == pytest.approx(0.0011166, abs=1e-6)
    assert f"{value * 100:+.2f}%" == "+0.11%"


def test_merger_return_refuses_a_bad_input() -> None:
    with pytest.raises(ValueError, match="previous close"):
        ca.merger_return(0.0, KMB_CLOSE, RATIO, CASH)
    with pytest.raises(ValueError, match="acquirer's close"):
        ca.merger_return(KVUE_PREV_CLOSE, 0.0, RATIO, CASH)
    with pytest.raises(ValueError, match="shares per target share"):
        ca.merger_return(KVUE_PREV_CLOSE, KMB_CLOSE, 0.0, CASH)
    with pytest.raises(ValueError, match="cash per share"):
        ca.merger_return(KVUE_PREV_CLOSE, KMB_CLOSE, RATIO, -1.0)


def _record(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "trade_date": "2026-11-02",
        "ticker": KVUE,
        "effective_date": "2026-11-02",
        "factor": RATIO,
        "source": "manual.record",
        "cross_check_ratio": None,
        "explained_by": "merger",
        "new_ticker": KMB,
        "source_rate": 1.0,
        "new_rate": RATIO,
        "cash_per_share": CASH,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_the_reader_takes_the_rows_the_rule_writes() -> None:
    records = ca.mergers_from_rows(_record())
    assert [r.target for r in records] == [KVUE]
    assert records[0].acquirer == KMB
    assert records[0].completion_date == COMPLETION
    assert records[0].acquirer_per_target == RATIO
    assert records[0].cash_per_share == CASH
    assert records[0].applicable

    # a frame without the explained_by column reads as no records, not as splits
    assert ca.mergers_from_rows(_record().drop(columns=["explained_by"])) == []

    # a record that cannot form a ratio is kept, so the target's cell is nulled
    unusable = ca.mergers_from_rows(_record(new_ticker=None))
    assert unusable[0].acquirer_per_target is None
    assert unusable[0].unusable_reason == "no acquirer symbol"

    # a missing cash column reads as zero, not as a refusal
    assert ca.mergers_from_rows(_record(cash_per_share=None))[0].cash_per_share == 0.0


def test_the_row_writer_and_the_reader_agree() -> None:
    merger = ca.Merger(KVUE, KMB, COMPLETION, RATIO, CASH)
    outcome = ca.MergerOutcome(merger, COMPLETION, None, TOTAL_RETURN, KMB_CLOSE)
    rows = ca.merger_rows([outcome], COMPLETION)
    records = ca.mergers_from_rows(pd.DataFrame(rows))
    assert records[0].target == KVUE
    assert records[0].acquirer == KMB
    assert records[0].acquirer_per_target == RATIO
    assert records[0].cash_per_share == CASH


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.MultiIndex.from_tuples(
        [
            (BEFORE, KVUE),
            (COMPLETION, KVUE),
            (NEXT, KVUE),
            (COMPLETION, KMB),
            (NEXT, KMB),
        ],
        names=["date", "ticker"],
    )
    prices = pd.DataFrame(
        {
            "close": [KVUE_PREV_CLOSE, float("nan"), float("nan"), KMB_CLOSE, 109.0],
            "adj_close": [
                KVUE_PREV_CLOSE,
                float("nan"),
                float("nan"),
                KMB_CLOSE,
                109.0,
            ],
            "split_factor": [1.0, 1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )
    returns = pd.DataFrame(
        {"r": [0.0, float("nan"), float("nan"), 0.0, 0.0]}, index=index
    )
    returns["g"] = np.log1p(returns["r"])
    return returns, prices


def test_the_completion_return_is_the_total_return_and_later_rows_are_nulled() -> None:
    frame, prices = _frames()
    merger = ca.Merger(KVUE, KMB, COMPLETION, RATIO, CASH)
    outcomes = ca.apply_recorded_mergers(frame, prices, [merger])

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.adjusted_return == pytest.approx(TOTAL_RETURN, abs=1e-12)
    assert outcome.raw_return is None, "the close disappeared, so there was no print"
    assert outcome.nulled_after == 1
    assert float(frame.loc[(COMPLETION, KVUE), "r"]) == pytest.approx(
        TOTAL_RETURN, abs=1e-12
    )
    assert float(frame.loc[(COMPLETION, KVUE), "g"]) == pytest.approx(
        np.log1p(TOTAL_RETURN)
    )
    assert pd.isna(frame.loc[(NEXT, KVUE), "r"]), "no series to continue"


def test_a_merger_whose_acquirer_close_is_missing_nulls_the_one_cell() -> None:
    frame, prices = _frames()
    prices.loc[(COMPLETION, KMB), "close"] = float("nan")
    merger = ca.Merger(KVUE, KMB, COMPLETION, RATIO, CASH)
    outcomes = ca.apply_recorded_mergers(frame, prices, [merger])

    assert len(outcomes) == 1
    assert outcomes[0].adjusted_return is None
    assert outcomes[0].missing_close
    assert pd.isna(frame.loc[(COMPLETION, KVUE), "r"])


def test_a_merger_the_panel_does_not_carry_is_dropped() -> None:
    frame, prices = _frames()
    frame = frame.loc[frame.index.get_level_values("ticker") != KVUE]
    merger = ca.Merger(KVUE, KMB, COMPLETION, RATIO, CASH)
    assert ca.apply_recorded_mergers(frame, prices, [merger]) == []


def _merger() -> ca.Merger:
    return ca.Merger(KVUE, KMB, COMPLETION, RATIO, CASH)


def test_the_comparison_explains_a_merger_conversion() -> None:
    from live import positions

    believed = {"KVUE": 10000.0, "KMB": 5000.0}
    broker = {"KMB": 15000.0}  # KVUE converted into KMB with no order behind it
    result = positions.compare(broker, believed, mergers=[_merger()])

    assert result["matches"] is True
    assert result["missing_at_broker"] == []
    assert result["drift"] == {}
    assert len(result["merger_notes"]) == 1
    assert "KVUE -> KMB" in result["merger_notes"][0]


def test_a_merger_whose_conversion_differs_from_the_stale_mark_still_explains() -> None:
    from live import positions

    believed = {"KVUE": 10000.0, "KMB": 5000.0}
    broker = {"KMB": 15015.0}  # a few dollars of consideration above the stale mark
    result = positions.compare(broker, believed, mergers=[_merger()])

    assert result["matches"] is False
    assert result["missing_at_broker"] == [], "the disappearance is explained"
    assert "KMB" in result["drift"], "the residual is reported, not hidden"
    assert len(result["merger_notes"]) == 1
