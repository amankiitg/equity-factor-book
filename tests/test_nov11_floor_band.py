"""Item 12's floor band: off means the book is unchanged, weight for weight."""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest

from live import evening_job


def test_the_flag_is_off_when_unset_and_refuses_anything_unreadable() -> None:
    # The safe direction for a switch that changes which names the book holds: a
    # mistyped variable leaves the book exactly as it is.
    for value in (None, "", "   ", "off", "nope", "0.2", "1.5", "nan", "1.0"):
        assert evening_job.resolve_floor_release(value) == 1.0, value
    assert evening_job.resolve_floor_release("0.75") == 0.75
    assert evening_job.resolve_floor_release(" 0.5 ") == 0.5


def test_the_release_mask_is_the_full_floor_when_the_band_is_off() -> None:
    # The mask arithmetic is what the fix rests on: at `release=1.0` (and with no
    # sticky set at all) `_releasable` returns the same array it was given, so no
    # code path downstream can see a difference.
    shares = np.array([10, 200], dtype=int)
    prices = np.array([10.0, 10.0], dtype=float)
    below = evening_job.below_floor(shares, prices, 1_500.0, 20)
    idx = np.array([0, 1], dtype=int)
    assert below.tolist() == [True, False]
    for release, sticky in ((1.0, np.array([True, True])), (0.75, None)):
        masked = evening_job._releasable(
            below, idx, shares, prices, sticky, release, 1_500.0, 20
        )
        assert masked.tolist() == below.tolist()


def test_a_held_name_inside_the_band_is_not_released() -> None:
    # The band's own case: 120 shares at $10 is $1,200 - below the $1,500 dollar floor
    # and above 0.75 of it ($1,125) - so a name the book *holds* stays and a name it
    # does not is still dropped.
    shares = np.array([120], dtype=int)
    prices = np.array([10.0], dtype=float)
    idx = np.array([0], dtype=int)
    below = evening_job.below_floor(shares, prices, 1_500.0, 20)
    assert below.tolist() == [True]
    held = evening_job._releasable(
        below, idx, shares, prices, np.array([True]), 0.75, 1_500.0, 20
    )
    assert held.tolist() == [False]
    new_name = evening_job._releasable(
        below, idx, shares, prices, np.array([False]), 0.75, 1_500.0, 20
    )
    assert new_name.tolist() == [True]
    # And a held name that has shrunk below the band ($1,000 against $1,125) is
    # released like any other.
    small = np.array([100], dtype=int)
    below_small = evening_job.below_floor(small, prices, 1_500.0, 20)
    assert evening_job._releasable(
        below_small, idx, small, prices, np.array([True]), 0.75, 1_500.0, 20
    ).tolist() == [True]


def test_a_misaligned_held_mask_is_refused_rather_than_guessed() -> None:
    # A mask shorter than the book would silently protect the wrong names.
    with pytest.raises(ValueError, match="cannot be aligned"):
        evening_job._releasable(
            np.array([True]),
            np.array([5]),
            np.array([10], dtype=int),
            np.array([10.0]),
            np.array([True, True]),
            0.75,
            1_500.0,
            20,
        )


@pytest.mark.slow
def test_the_default_book_is_identical_weight_for_weight() -> None:
    """The identity proof: the flag off changes nothing the book trades.

    Two builds of the same live construction - one with the band unset (the default),
    one with it explicitly off - and the kept book is compared name for name and
    weight for weight, the same way the e12 sizing proof does it. The band's own state
    travels on the manifest, so a reader can always tell which book this is.
    """
    path = pathlib.Path(__file__).resolve().parents[1] / "data"
    as_of = pd.Timestamp("2026-09-21")
    book = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "weight": [0.01, -0.01],
        }
    )
    previous = book.set_index("ticker")["weight"]
    off = evening_job.build_proposal(
        data_root=path, as_of=as_of, store=False, previous=previous
    )
    explicit = evening_job.build_proposal(
        data_root=path, as_of=as_of, store=False, previous=previous, floor_release=1.0
    )
    assert off["n_kept"] == explicit["n_kept"]
    kept_off = pd.DataFrame(off["kept_book"]).set_index("ticker")["weight"]
    kept_explicit = pd.DataFrame(explicit["kept_book"]).set_index("ticker")["weight"]
    assert list(kept_off.index) == list(kept_explicit.index)
    assert float((kept_off - kept_explicit).abs().max()) == 0.0
    assert off["kept_gross"] == explicit["kept_gross"]
    # The band's own state travels on the manifest, so a later reader can tell a book
    # built with it from one built without.
    assert off["floor_release"] == 1.0
