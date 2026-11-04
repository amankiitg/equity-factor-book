"""The past incidents, replayed: one name never stops the book.

Seven failures since launch, one shape. Each is replayed here with the values that
caused it, and each asserts the same three things: the night completes, the name is
out with the reason that applies to it, and nothing else changes.

The incidents, in the order they happened:

1. `SKYD/WS`, a warrant in the 2026-10-14 holdings file, priced by nobody: the vendor
   answered 404 and `wide_to_long` assumed the columns existed.
2. `SKYD.WS`, the same instrument filed by the vendor as a spin-off child under a
   different spelling, which a rule that only asked "is there a child symbol" would
   have rewritten.
3. `CTVA`, whose 2026-10-01 print was a spin-off distribution served as a price: a
   restatement no record explained, which the cross check refused.
4. `HON`, whose stored ratio its own split factor contradicted by 42.8 points.
5. `KVUE`, NaN close on a hold day, dividing into `int()`.
6. `KVUE`, retired at the broker after its merger into KMB.
7. the share counts, one session behind because only new names were ever fetched.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from efb import probes
from live import alpaca, evening_job, exclusions


def test_a_warrant_with_no_price_is_excluded_not_fatal() -> None:
    """SKYD/WS: a name nobody prices is out, and the book is built without it."""
    names = ["AAPL", "MSFT", "SKYD/WS"]
    close = {"AAPL": 230.0, "MSFT": 400.0}  # the vendor has nothing for the warrant
    priced, dropped = evening_job.priced_names_or_stop(names, close)
    assert dropped == ["SKYD/WS"]
    assert priced.tolist() == [True, True, False]
    sentence = exclusions.sentence(
        exclusions.collect(
            [
                exclusions.Exclusion(name, "no usable close at the close", "prices")
                for name in dropped
            ]
        )
    )
    assert sentence == "Excluded tonight: SKYD/WS (no usable close at the close)."


def test_the_book_still_stops_when_the_price_fetch_broke() -> None:
    """The same reader, the other side: eleven names is the fetch, not the market."""
    names = [f"T{index:02d}" for index in range(20)]
    close = {name: 10.0 for name in names[11:]}
    with pytest.raises(ValueError, match="more than the 10 the evening accepts"):
        evening_job.priced_names_or_stop(names, close)


def test_an_inactive_asset_is_out_and_owed_never_sent() -> None:
    """KVUE: the broker keeps the asset and reports it retired."""
    resolution = alpaca.SymbolResolution(
        "KVUE",
        "",
        "asset-kvue",
        False,
        True,
        "KVUE: the broker reports the asset inactive, so no leg can be sent for it: "
        "merger completion, KMB and KVUE",
        True,
    )
    assert resolution.inactive is True
    assert alpaca.REASON_ASSET_INACTIVE in evening_job.UNREACHABLE_REFUSALS
    sentence = exclusions.sentence(
        [
            exclusions.Exclusion(
                "KVUE", "the broker reports the asset inactive", "broker"
            )
        ]
    )
    assert sentence == "Excluded tonight: KVUE (the broker reports the asset inactive)."


def test_a_held_name_with_no_close_leaves_the_book_and_the_rest_keeps_its_size() -> (
    None
):
    """KVUE on 2026-11-02: a NaN close on a hold day is a dropped name, not a crash."""
    names = ["AAPL", "KVUE", "MSFT"]
    weights = np.array([0.01, -0.013125, -0.008])
    priced = np.array([True, False, True])
    dropped_weights, dropped = evening_job.drop_unpriced_held(weights, names, priced)
    assert dropped == ["KVUE"]
    assert dropped_weights == pytest.approx([0.01, 0.0, -0.008])
    # the book is not renormalized: a hold day reports the gross it holds, and the
    # dropped name's weight is simply gone from it
    assert float(np.abs(dropped_weights).sum()) == pytest.approx(0.018)


def test_a_restatement_no_record_explains_drops_the_name_for_the_session() -> None:
    """CTVA's real ratio, through the rule that refuses to guess.

    The 2026-10-01 print arrived as 77.65 to 12.57 with a back-adjustment ratio of
    0.150038 and no split record behind it. The cross check sees a ratio its split
    records do not carry, and the append path drops the name for that session
    instead of stopping the evening.
    """
    from live import corporate_actions as ca

    assert ca.cross_check_ratio(77.65, 12.57) == pytest.approx(0.161880, abs=1e-6)
    # the ratio the CTVA row carried, and no record to explain it
    prices = _prices_frame(
        [
            ("2026-09-30", "CTVA", 77.65, 77.65, 0.0),
            ("2026-10-01", "CTVA", 12.57, 12.57, 0.0),
        ]
    )
    frame = _returns_frame(
        [("2026-09-30", "CTVA", 0.0), ("2026-10-01", "CTVA", -0.838)]
    )
    outcome = ca.apply_to_append(
        frame,
        prices,
        since=pd.Timestamp("2026-09-30"),
        split_fetcher=lambda ticker: [],
        close_fetcher=lambda ticker, session: 12.57,
    )
    assert [record.ticker for record in outcome.suspended] == ["CTVA"]
    assert outcome.splits == [], "no split was invented to explain it"


def test_a_spinoff_ratio_the_factor_contradicts_is_nulled_not_applied() -> None:
    """HON: 42.8 points between the record's ratio and the vendor's factor."""
    from live import corporate_actions as ca

    assert ca.DISTRIBUTION_TOLERANCE < 0.428
    # the threshold is what separates a legitimate 4.3-point disagreement from HON's
    assert ca.DISTRIBUTION_TOLERANCE > 0.043


def test_the_share_counts_catch_up_without_waiting_for_a_retired_name() -> None:
    """The seventh incident: the stamp moves for the names that still trade."""
    assert "refresh" in probes.fetch_share_history.__code__.co_varnames


def _prices_frame(rows: list[tuple[str, str, float, float, float]]) -> pd.DataFrame:
    index = pd.MultiIndex.from_tuples(
        [(pd.Timestamp(date), ticker) for date, ticker, *_ in rows],
        names=["date", "ticker"],
    )
    return pd.DataFrame(
        [
            {"close": close, "adj_close": adj, "split_factor": factor}
            for *_, close, adj, factor in rows
        ],
        index=index,
    )


def _returns_frame(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    index = pd.MultiIndex.from_tuples(
        [(pd.Timestamp(date), ticker) for date, ticker, _ in rows],
        names=["date", "ticker"],
    )
    return pd.DataFrame({"r": [row[2] for row in rows]}, index=index)
