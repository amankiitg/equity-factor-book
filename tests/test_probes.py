"""Tests for Task 0 probe helpers: parsing and report rendering, no network."""

import numpy as np
import pandas as pd
import pytest

from efb import factors
from efb.prices import clean_prices, wide_to_long
from efb.probes import ProbeReport
from efb.universe import _clean_ticker

FF5_TEXT = """F-F Research Data 5 Factors (2x3) daily

This file was created by using the 202607 CRSP database.
,Mkt-RF,SMB,HML,RMW,CMA,RF
20100104,    0.22,   -0.10,   -0.30,    0.40,   -0.11,    0.00
20100105,   -0.11,    0.05,   -0.02,    0.10,    0.03,    0.01
20100106,  -99.99,   -0.05,    0.02,    0.04,    0.02,    0.00

  Copyright 2026 Eugene F. Fama and Kenneth R. French
"""


def test_parse_french_csv_reads_header_dates_and_values() -> None:
    frame = factors.parse_french_csv(FF5_TEXT)
    assert list(frame.columns) == ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]
    assert len(frame) == 3
    assert frame.index[0] == pd.Timestamp("2010-01-04")
    assert frame.iloc[0, 0] == pytest.approx(0.22)
    assert frame.iloc[2, 0] == pytest.approx(-99.99)


def test_to_decimal_converts_sentinels_and_units() -> None:
    frame = factors.parse_french_csv(FF5_TEXT)
    dec = factors.to_decimal(frame)
    assert dec.iloc[0, 0] == pytest.approx(0.0022)
    assert np.isnan(dec.iloc[2, 0])
    assert not np.isnan(dec.iloc[2, 5])


def test_parse_french_csv_raises_without_header() -> None:
    with pytest.raises(ValueError):
        factors.parse_french_csv("no header anywhere\njust words\n")


def test_clean_ticker_normalization() -> None:
    assert _clean_ticker("AAPL") == "AAPL"
    assert _clean_ticker(" BF.B ") == "BF.B"
    assert _clean_ticker("Electronic Arts") is None
    assert _clean_ticker(float("nan")) is None
    assert _clean_ticker(None) is None


def test_probe_report_render() -> None:
    report = ProbeReport(
        source="test_source",
        status="ok",
        n_rows=12,
        first_date="2010-01-04",
        last_date="2026-09-03",
        coverage=0.9500,
        nan_share=0.0001,
        notes="synthetic",
    )
    text = report.render()
    assert "### test_source" in text
    assert "status: ok" in text
    assert "coverage: 0.9500" in text
    assert "ticker_coverage" in text


def _synthetic_wide() -> pd.DataFrame:
    idx = pd.bdate_range("2026-08-01", periods=4)
    cols = pd.MultiIndex.from_product(
        [
            ["AAPL", "XOM"],
            [
                "Open",
                "High",
                "Low",
                "Close",
                "Adj Close",
                "Volume",
                "Dividends",
                "Stock Splits",
            ],
        ],
        names=["ticker", "field"],
    )
    frame = pd.DataFrame(1.0, index=idx, columns=cols)
    frame[("AAPL", "Adj Close")] = [100.0, 101.0, 102.0, 103.0]
    frame[("XOM", "Adj Close")] = [50.0, 49.0, 49.0, 50.0]
    return frame


def test_wide_to_long_layout() -> None:
    long_df = wide_to_long(_synthetic_wide())
    assert list(long_df.index.names) == ["date", "ticker"]
    assert list(long_df.columns) == [
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "dividend",
        "split_factor",
    ]
    assert long_df.loc[
        (pd.Timestamp("2026-08-04"), "AAPL"), "adj_close"
    ] == pytest.approx(101.0)


def test_clean_prices_drops_weekends_and_duplicates() -> None:
    long_df = wide_to_long(_synthetic_wide())
    weekend = pd.Timestamp("2026-08-02")  # Sunday, not in bdate_range frame
    extra = long_df.loc[[long_df.index[0]]].copy()
    dirty = pd.concat([long_df, extra])
    cleaned = clean_prices(dirty)
    assert cleaned.index.is_unique
    assert weekend not in cleaned.index.get_level_values("date")
