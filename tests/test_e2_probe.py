"""Tests for Task 0: point-in-time coverage by year and MODEL_START."""

import numpy as np
import pandas as pd
import pytest

from efb.probes import coverage_by_year, select_model_start


def _members(columns: list[str], periods: int = 252, start: str = "2010-01-01") -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=periods)
    return pd.DataFrame(True, index=idx, columns=columns)


def _prices(adj: pd.DataFrame) -> pd.DataFrame:
    """Long price frame from a wide adjusted-close frame (NaNs kept)."""
    out = adj.stack().rename("adj_close").to_frame()
    out.index.names = ["date", "ticker"]
    return out


def test_coverage_by_year_counts_members_with_data() -> None:
    dates = pd.bdate_range("2010-01-01", "2011-12-31")
    n = len(dates)
    wide = pd.DataFrame(
        {
            "AAA": np.where(dates.year == 2010, 1.0, np.nan),
            "BBB": np.where(dates.year == 2010, 1.0, 1.0),
            "CCC": np.nan,
        },
        index=dates,
    )
    members = pd.DataFrame(
        {
            "AAA": dates.year == 2010,
            "BBB": True,
            "CCC": True,
        },
        index=dates,
    )
    table = coverage_by_year(members, _prices(wide))
    row_2010 = table.loc[table["year"] == 2010].iloc[0]
    assert row_2010["n_members"] == 3
    assert row_2010["n_covered"] == 2  # AAA and BBB, not CCC
    row_2011 = table.loc[table["year"] == 2011].iloc[0]
    assert row_2011["n_members"] == 2  # AAA left after 2010
    assert row_2011["n_covered"] == 1  # only BBB


def test_coverage_uses_membership_window_denominator() -> None:
    dates = pd.bdate_range("2010-01-01", periods=252)
    wide = pd.DataFrame({"AAA": 1.0}, index=dates)
    # AAA is a member only in the second half of the year but fully covered there
    members = pd.DataFrame({"AAA": dates >= dates[len(dates) // 2]}, index=dates)
    table = coverage_by_year(members, _prices(wide))
    assert table.loc[table["year"] == 2010, "n_covered"].iloc[0] == 1


def test_select_model_start_first_year_above_threshold() -> None:
    table = pd.DataFrame(
        {
            "year": [2010, 2011, 2012],
            "n_members": [400, 400, 400],
            "n_covered": [250, 310, 350],
        }
    )
    assert select_model_start(table, min_names=300) == 2011


def test_select_model_start_raises_when_never_reached() -> None:
    table = pd.DataFrame({"year": [2010], "n_members": [10], "n_covered": [5]})
    with pytest.raises(ValueError):
        select_model_start(table, min_names=300)
