"""Sprint E11: the live cost rules, and the ADV that feeds them.

Three things the owner set on 2026-09-26, each of which changes a number the
evening reports: ADV is the trailing quarter's median rather than a median over
sixteen years, a zero ADV is a missing ADV rather than a dollar of ADV, and the
impact is the cost of the trade rather than of the position.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from efb import costs as costs_mod
from live import evening_job


def _prices(volumes: dict[str, list[float]], close: float = 10.0) -> pd.DataFrame:
    """A price panel with one column per ticker, dated by row."""
    rows = []
    for ticker, series in volumes.items():
        for offset, volume in enumerate(series):
            rows.append(
                {
                    "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=offset),
                    "ticker": ticker,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": volume,
                }
            )
    frame = pd.DataFrame(rows).set_index(["date", "ticker"]).sort_index()
    return frame


def _write_root(tmp_path: Path, prices: pd.DataFrame) -> Path:
    root = tmp_path / "data"
    (root / "raw").mkdir(parents=True, exist_ok=True)
    prices.to_parquet(root / "raw" / "prices.parquet")
    # The spread schedule is a size-decile schedule, so it needs a market cap per
    # name: shares times close, from the same panel's own dates.
    tickers = sorted(prices.index.get_level_values("ticker").unique())
    shares = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-01-01"),
                "ticker": ticker,
                "shares": 1_000_000.0 * (position + 1),
            }
            for position, ticker in enumerate(tickers)
        ]
    )
    shares.to_parquet(root / "raw" / "shares_history.parquet")
    return root


def test_adv_is_the_trailing_quarter_not_the_whole_history(tmp_path: Path) -> None:
    """The median over sixteen years is not a statement about today's liquidity.

    SW has a zero dollar volume on 2,409 of its 4,204 sessions in the live panel,
    1,866 of them (77%) before 2020 and the last on 2024-07-05, so the
    full-history median is $0 while its trailing quarter traded $210M a day.
    """
    volumes = [0.0] * 300 + [1_000_000.0] * 63
    prices = _prices({"OLD": volumes, "LIVE": [2_000_000.0] * len(volumes)})

    trailing = costs_mod.trailing_adv(prices)
    history = costs_mod._adv_per_ticker(prices)

    assert history["OLD"] == 0.0, "the full-history median is the bug being pinned"
    assert trailing["OLD"] == 10_000_000.0
    # The negative control: a name that always traded is the same either way.
    assert trailing["LIVE"] == history["LIVE"] == 20_000_000.0


def test_a_zero_adv_is_missing_rather_than_a_dollar(tmp_path: Path) -> None:
    """A zero is filled from the median, exactly as an absent value is."""
    prices = _prices({"QUIET": [0.0] * 63, "BUSY": [5_000_000.0] * 63})
    root = _write_root(tmp_path, prices)

    trailing = costs_mod.trailing_adv(prices)
    assert pd.isna(trailing["QUIET"]), "zero dollar volume is a missing input"

    adv_map, raw, thin = evening_job._adv_maps(["QUIET", "BUSY"], root)

    assert np.isnan(raw[0])
    # The median of the panel stands in, rather than the $1 floor, which turned a
    # missing input into the worst liquidity there is.
    assert adv_map[0] == 50_000_000.0
    assert adv_map[1] == 50_000_000.0
    assert thin == [{"ticker": "QUIET", "adv_usd": None}]


def test_the_impact_is_the_trade_not_the_position(tmp_path: Path) -> None:
    """From flat the two are the same; from a book they are not.

    The establishment day trades the whole target, so its impact is unchanged.
    A rebalance that already holds the book trades nothing, and a cost function
    that charges for the position rather than the trade would charge the whole
    book for it.
    """
    prices = _prices({"AAA": [1_000_000.0] * 63, "BBB": [1_000_000.0] * 63})
    root = _write_root(tmp_path, prices)
    names = ["AAA", "BBB"]
    specific = np.array([4e-4, 4e-4])
    weights = np.array([0.5, -0.5])

    from_flat, _thin = evening_job._cost_decomposition(
        weights, names, specific, 1_000_000.0, root, None
    )
    no_change, _thin = evening_job._cost_decomposition(
        weights, names, specific, 1_000_000.0, root, weights.copy()
    )
    halved, _thin = evening_job._cost_decomposition(
        weights, names, specific, 1_000_000.0, root, np.array([0.25, -0.25])
    )

    assert from_flat["impact_bps"] > 0
    assert no_change["impact_bps"] == 0.0, "holding the book trades nothing"
    # Half the distance is not half the cost - impact goes as the square root -
    # but it is strictly less, which is the property that was missing.
    assert 0 < halved["impact_bps"] < from_flat["impact_bps"]
    # The other three components are the cost of owning the book and do not move.
    for key in ("spread_bps", "commission_bps", "borrow_bps"):
        assert no_change[key] == from_flat[key]
    assert from_flat["traded_notional"] == 1_000_000.0
    assert no_change["traded_notional"] == 0.0
    assert no_change["avg_trade_size"] == 0.0


def test_a_thin_name_is_named_with_its_own_numbers(tmp_path: Path) -> None:
    """The kept names whose cost is a median, and how thin they are."""
    prices = _prices({"AAA": [1_000_000.0] * 63, "THIN": [50_000.0] * 63})
    root = _write_root(tmp_path, prices)
    names = ["AAA", "THIN"]
    specific = np.array([4e-4, 4e-4])

    _cost, thin = evening_job._cost_decomposition(
        np.array([0.5, -0.5]), names, specific, 1_000_000.0, root, None
    )

    assert thin == [{"ticker": "THIN", "adv_usd": 500_000.0}]
