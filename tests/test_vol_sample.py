"""Tests for close-out task C7: the seeded GARCH sample (criterion F2.3c).

F2.3 and F2.3b were evaluated on the first names of a sorted ticker list,
which is the names starting with A and B rather than a sample of anything.
C7 draws from the names that can actually be scored, with a stored seed so
the draw is reproducible, and separately asks whether the trailing-wins
result survives a change of window.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from efb import vol


def _returns(tickers: list[str], periods: int = 600, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=periods)
    return pd.DataFrame(
        rng.normal(0.0, 0.01, size=(periods, len(tickers))),
        index=dates,
        columns=tickers,
    )


def test_covered_tickers_excludes_names_with_a_gap() -> None:
    frame = _returns(["AAA", "BBB"], periods=300)
    frame.loc[frame.index[250], "BBB"] = np.nan
    covered = vol.covered_tickers(frame, "2020-06-01")
    assert covered == ["AAA"]


def test_the_sample_is_seeded_random_not_alphabetical() -> None:
    # a name list whose alphabetical head is A and B only: a random draw of
    # 10 from 40 should not be the first ten of the sorted list
    tickers = [f"{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(40)]
    frame = _returns(tickers, periods=300)
    picked, seed = vol.garch_sample(frame, "2020-06-01", n=10, seed=7)
    assert seed == 7
    assert len(picked) == 10
    assert picked == sorted(picked)
    assert picked != sorted(tickers)[:10]
    # the same seed gives the same draw, a different seed does not
    again, _ = vol.garch_sample(frame, "2020-06-01", n=10, seed=7)
    assert again == picked
    other, _ = vol.garch_sample(frame, "2020-06-01", n=10, seed=8)
    assert other != picked


def test_the_sample_only_contains_fully_covered_names() -> None:
    frame = _returns(["AAA", "BBB", "CCC"], periods=300)
    frame.loc[frame.index[250], "CCC"] = np.nan
    picked, _ = vol.garch_sample(frame, "2020-06-01", n=3, seed=1)
    assert "CCC" not in picked
    assert set(picked) == {"AAA", "BBB"}


def test_a_sample_larger_than_the_universe_is_the_universe() -> None:
    frame = _returns(["AAA", "BBB"], periods=300)
    picked, _ = vol.garch_sample(frame, "2020-06-01", n=100, seed=1)
    assert picked == ["AAA", "BBB"]


def test_fit_garch_universe_reports_the_failures() -> None:
    # CCC is constant, so its variance is zero and the fit cannot converge
    frame = _returns(["AAA", "BBB"], periods=400)
    frame["CCC"] = 0.001
    short = _returns(["DDD"], periods=100)
    frame = pd.concat([frame, short], axis=1)
    frame = frame.fillna(0.0)
    params, failed = vol.fit_garch_universe(
        frame, ["AAA", "BBB", "CCC", "DDD"], split="2021-01-01"
    )
    assert {"AAA", "BBB"} <= set(params)
    assert "DDD" in failed or "CCC" in failed


def test_both_races_can_be_scored_on_one_name_list() -> None:
    frame = _returns([f"T{i:02d}" for i in range(12)], periods=700, seed=3)
    names = ["T00", "T05"]
    table = vol.vol_horse_race(
        frame, oos_start="2022-01-03", garch_names=names, garch_params=None
    )
    garch_rows = table.loc[table["method"] == "garch", "ticker"].unique()
    assert set(garch_rows) <= set(names)


def test_an_empty_name_list_disables_garch() -> None:
    # this is how the build runs without GARCH: an explicit empty list, not
    # a count of zero, so no fallback to the alphabetical head can happen
    frame = _returns([f"T{i:02d}" for i in range(12)], periods=700, seed=3)
    table = vol.aligned_horse_race(
        frame, oos_start="2022-01-03", garch_names=[], garch_params={}
    )
    assert "garch" not in set(table["method"])


def test_win_rate_by_year_counts_name_days_per_year() -> None:
    frame = _returns([f"T{i:02d}" for i in range(8)], periods=900, seed=5)
    rates = vol.win_rate_by_year(
        frame, oos_start="2020-01-04", method="ewma_097", baseline="trailing_252"
    )
    assert sum(rates["n_by_year"].values()) == rates["n_name_days"]
    assert set(rates["by_year"]) == set(rates["n_by_year"])
    assert 2020 in rates["by_year"]


def test_the_real_sample_is_seeded_and_fully_covered() -> None:
    """The stored artifact, when it exists, has to match its stored seed."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    table = root / "data" / "eval" / "vol_horse_race_aligned.parquet"
    if not table.exists():
        pytest.skip("E2 artifacts not built yet")
    import json

    registry = json.loads((root / "data" / "models" / "registry.json").read_text())
    params = registry["models"]["TS-v1"]["parameters"]
    if "garch_seed" not in params:
        pytest.skip("C7 not built into the registry yet")
    assert params["garch_seed"] == vol.GARCH_SEED
    assert params["garch_sample_size"] == vol.GARCH_SAMPLE
    assert len(params["garch_sample_tickers"]) == vol.GARCH_SAMPLE
    assert len(params["garch_not_converged"]) == params["garch_failed"]
