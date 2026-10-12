"""Item 18: a name the broker will not lend, checked before the sizing and not after."""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest

from live import alpaca, evening_job, notify


def test_the_flag_opens_only_on_the_exact_word() -> None:
    # The same convention as the trading window's override, and for the same reason:
    # a missing or mistyped variable must leave the book exactly as it is.
    assert evening_job.resolve_shortability_precheck("true") is True
    for value in (None, "", "True", "TRUE", "1", "yes", "on", " false"):
        assert evening_job.resolve_shortability_precheck(value) is False, value


def test_only_a_short_the_broker_refuses_is_dropped() -> None:
    names = ["LONG", "SHORT", "MIXED", "UNKNOWN"]
    weights = np.array([0.02, -0.02, 0.0, -0.01])
    flags = {"LONG": False, "SHORT": False, "MIXED": False}
    keep, dropped = evening_job.drop_not_shortable(names, weights, flags)
    assert keep.tolist() == [True, False, True, True]
    assert [row["ticker"] for row in dropped] == ["SHORT"]
    assert "shortable=false" in str(dropped[0]["reason"])
    # UNKNOWN is absent from the mapping: the feed did not answer for it, and an
    # unanswered read is not a refusal.
    assert "UNKNOWN" not in [row["ticker"] for row in dropped]


def test_the_bulk_read_maps_the_feed_and_omits_what_it_lacks() -> None:
    class _Asset:
        def __init__(self, shortable: bool) -> None:
            self.shortable = shortable

    class _Resolver:
        def __init__(self) -> None:
            self._by_symbol = {"AAA": _Asset(True), "BBB": _Asset(False)}

    assert alpaca.shortable_map(_Resolver()) == {"AAA": True, "BBB": False}
    assert alpaca.shortable_map(_Resolver(), ["BBB", "ZZZ"]) == {"BBB": False}
    # A resolver whose feed could not be read answers with nothing at all, rather
    # than with a False for every name.
    assert alpaca.shortable_map(object()) == {}


def test_the_message_names_the_names_and_the_flag() -> None:
    message = notify.compose(
        status="ok",
        target_close="2026-10-08",
        dry_run=False,
        orders=190,
        sent_orders=190,
        gross=380_000.0,
        no_short=[
            {"ticker": "SYY", "reason": "the broker's feed reports shortable=false"}
        ],
        store="postgres/efb",
    )
    line = next(
        text for text in message.splitlines() if text.startswith("Dropped before")
    )
    assert "SYY" in line
    assert "out of the book before the hedge" in line


@pytest.mark.slow
def test_the_book_is_unchanged_when_no_source_is_injected() -> None:
    """The identity proof: no source, no drop, the book identical weight for weight.

    `shortable=None` is the default and the whole of the off state, so this is the
    comparison that matters: the same construction built with no source and with the
    precheck's own helper given every name as shortable.
    """
    path = pathlib.Path(__file__).resolve().parents[1] / "data"
    as_of = pd.Timestamp("2026-09-21")
    off = evening_job.build_proposal(data_root=path, as_of=as_of, store=False)
    assert off["n_dropped_no_short"] == 0
    assert off["dropped_no_short"] == []
    kept = pd.DataFrame(off["kept_book"]).set_index("ticker")["weight"]
    with_source = evening_job.build_proposal(
        data_root=path,
        as_of=as_of,
        store=False,
        shortable={str(ticker): True for ticker in kept.index},
    )
    assert with_source["n_dropped_no_short"] == 0
    kept_with = pd.DataFrame(with_source["kept_book"]).set_index("ticker")["weight"]
    assert list(kept.index) == list(kept_with.index)
    assert float((kept - kept_with).abs().max()) == 0.0
    assert off["kept_gross"] == with_source["kept_gross"]
