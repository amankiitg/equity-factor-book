"""The E3 contract revision: a stale cell is not a return.

The fit reads `returns_clean`, so a zero-return run leaves every estimation window
without the row losing its value or its flag in the file. These tests pin both
halves of that sentence.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from efb import hygiene, probes

STALE_NAME = "FRZN"


def tree(tmp_path):
    """A minimal root with a stale run in it."""
    (tmp_path / "processed").mkdir(parents=True, exist_ok=True)
    (tmp_path / "raw").mkdir(parents=True, exist_ok=True)
    dates = pd.bdate_range("2020-01-01", periods=12)
    close = pd.DataFrame(
        {
            "MRKT": [100.0 + index for index in range(len(dates))],
            "LIVE": 50.0 + 0.1 * np.arange(len(dates)),
            STALE_NAME: [10.0] * len(dates),
        },
        index=dates,
    )
    long_close = close.stack().rename("close").to_frame()
    long_close["adj_close"] = long_close["close"]
    long_close["volume"] = 1_000_000.0
    long_close.index.names = ["date", "ticker"]
    long_close.to_parquet(tmp_path / "raw" / "prices.parquet")
    returns = close.pct_change()
    returns[STALE_NAME] = 0.0
    returns = returns.iloc[1:]
    long_returns = returns.stack().rename("r").to_frame()
    long_returns["g"] = np.log1p(long_returns["r"])
    long_returns["excess"] = np.nan
    long_returns.index.names = ["date", "ticker"]
    long_returns = hygiene.apply_flags(
        long_returns.reset_index().set_index(["date", "ticker"])
    )
    long_returns.to_parquet(tmp_path / "processed" / "returns.parquet")
    pd.DataFrame(
        {
            "ticker": ["MRKT", "LIVE", STALE_NAME],
            "gics_sector": ["Industrials", "Industrials", "Industrials"],
        }
    ).to_parquet(tmp_path / "processed" / "sectors.parquet", index=False)
    pd.DataFrame(
        {
            "date": list(dates),
            "ticker": ["MRKT"] * len(dates),
            "member": [True] * len(dates),
        }
    ).to_parquet(tmp_path / "processed" / "universe_membership.parquet", index=False)
    return tmp_path


def test_the_loader_returns_both_panels_and_only_the_flagged_rows_differ(
    tmp_path,
) -> None:
    inputs = probes.load_panel(tree(tmp_path))
    raw = inputs["returns"]
    clean = inputs["returns_clean"]
    assert raw.shape == clean.shape
    assert list(raw.columns) == list(clean.columns)

    # the stale name: a zero-return run of five or more sessions
    stale_days = int(
        hygiene.detect_stale(
            pd.read_parquet(tmp_path / "processed" / "returns.parquet")
        ).sum()
    )
    assert stale_days >= 5, "the fixture has to actually produce a stale run"
    assert (raw[STALE_NAME] == 0.0).all()
    assert clean[STALE_NAME].isna().all()
    assert int(clean[STALE_NAME].isna().sum()) == stale_days

    # a real move is kept, and the raw panel is untouched
    assert clean["LIVE"].notna().all()
    assert raw["LIVE"].equals(clean["LIVE"])
    assert (raw[STALE_NAME] == 0.0).all(), "the file keeps the value the flag describes"


def test_the_cleaned_panel_is_the_raw_panel_with_the_flags_applied(tmp_path) -> None:
    inputs = probes.load_panel(tree(tmp_path))
    frame = pd.read_parquet(tmp_path / "processed" / "returns.parquet")
    expected = hygiene.clean_returns(frame).unstack("ticker")
    expected = expected.reindex(
        index=inputs["returns"].index, columns=inputs["returns"].columns
    )
    assert inputs["returns_clean"].equals(expected)


def test_the_contract_names_the_three_clauses() -> None:
    """The revised contract is stated where the model's rules live."""
    from efb.models import fundamental

    text = fundamental.__doc__ or ""
    assert "stale cell is not a return" in text
    assert "real move is kept" in text
    assert "corrected at the source" in text


def test_the_build_fits_on_the_cleaned_panel() -> None:
    """The call site is pinned: a build that went back to the raw panel would fail."""
    import inspect

    from efb import build as build_module

    source = inspect.getsource(build_module.build_e3_artifacts)
    assert 'inputs["returns_clean"]' in source
    assert 'returns = inputs["returns"]' not in source


@pytest.mark.parametrize("flag", ["outlier", "stale"])
def test_a_flagged_row_is_masked_and_an_unflagged_one_is_not(flag: str) -> None:
    index = pd.MultiIndex.from_tuples(
        [(pd.Timestamp("2020-01-02"), "A"), (pd.Timestamp("2020-01-03"), "A")],
        names=["date", "ticker"],
    )
    frame = pd.DataFrame(
        {
            "r": [0.01, 0.9],
            flag: [True, False],
        },
        index=index,
    )
    masked = hygiene.clean_returns(frame)
    assert np.isnan(masked.iloc[0]), "the flagged row is masked"
    assert masked.iloc[1] == 0.9, "an unflagged one is kept"


def test_a_repaired_cell_survives_the_flag_that_describes_it(tmp_path) -> None:
    """The exception: a corrected spin-off cell is masked by nothing."""
    index = pd.MultiIndex.from_product(
        [[pd.Timestamp("2020-01-02")], ["A"]], names=["date", "ticker"]
    )
    frame = pd.DataFrame(
        {"r": [0.04], "outlier": [True], "corrected": [True]}, index=index
    )
    assert hygiene.clean_returns(frame).iloc[0] == 0.04
    frame["corrected"] = False
    assert np.isnan(hygiene.clean_returns(frame).iloc[0])
