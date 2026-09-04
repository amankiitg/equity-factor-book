"""Tests for Task 4: returns and stylized facts."""

import numpy as np
import pandas as pd
import pytest

from efb import returns


def _prices_frame(ticker: str, adj_close: list[float]) -> pd.DataFrame:
    idx = pd.MultiIndex.from_product(
        [pd.bdate_range("2026-07-01", periods=len(adj_close)), [ticker]],
        names=["date", "ticker"],
    )
    arr = np.asarray(adj_close, dtype=float)
    return pd.DataFrame(
        {
            "close": arr,
            "adj_close": arr,
            "dividend": 0.0,
            "split_factor": 0.0,
        },
        index=idx,
    )


def _rf(dates: pd.DatetimeIndex, rate: float = 0.0001) -> pd.Series:
    return pd.Series(rate, index=dates)


def test_compute_returns_hand_computed_match() -> None:
    px = [100.0, 101.0, 103.02, 102.0]
    frame = _prices_frame("AAA", px)
    out = returns.compute_returns(frame, _rf(pd.bdate_range("2026-07-01", periods=4)))
    r = out.loc[(pd.Timestamp("2026-07-03"), "AAA"), "r"]
    assert r == pytest.approx(103.02 / 101.0 - 1.0, abs=1e-12)
    g = out.loc[(pd.Timestamp("2026-07-03"), "AAA"), "g"]
    assert g == pytest.approx(np.log(103.02 / 101.0), abs=1e-12)
    excess = out.loc[(pd.Timestamp("2026-07-03"), "AAA"), "excess"]
    assert excess == pytest.approx(103.02 / 101.0 - 1.0 - 0.0001, abs=1e-12)
    # first day has no prior price
    assert np.isnan(out.loc[(pd.Timestamp("2026-07-01"), "AAA"), "r"])


def test_log_returns_add_over_time() -> None:
    px = [100.0, 101.0, 103.02, 102.0, 105.0]
    frame = _prices_frame("AAA", px)
    out = returns.compute_returns(frame, _rf(pd.bdate_range("2026-07-01", periods=5)))
    g = out.xs("AAA", level="ticker")["g"].dropna()
    assert g.sum() == pytest.approx(np.log(105.0 / 100.0), abs=1e-10)


def test_simple_returns_add_across_portfolio() -> None:
    px_a = [100.0, 101.0, 103.02, 102.0]
    px_b = [50.0, 50.5, 49.5, 50.0]
    frame = pd.concat([_prices_frame("AAA", px_a), _prices_frame("BBB", px_b)])
    out = returns.compute_returns(frame, _rf(pd.bdate_range("2026-07-01", periods=4)))
    r = out["r"].unstack("ticker")
    port = 0.5 * r["AAA"] + 0.5 * r["BBB"]
    per_day_ew = returns.equal_weight_universe_return(out, pd.DataFrame(True, index=port.index, columns=["AAA", "BBB"]))
    pd.testing.assert_series_equal(port.dropna(), per_day_ew.dropna(), check_names=False)


def test_stylized_facts_shape() -> None:
    rng = np.random.default_rng(7)
    n = 500
    series = pd.Series(rng.standard_t(4, size=n), index=pd.bdate_range("2020-01-02", periods=n))
    facts = returns.stylized_facts(series)
    assert set(facts) == {"kurtosis", "acf_r_lag1", "acf_r2_lag1", "acf_r2_lag5", "acf_r2_lag21"}
    assert facts["kurtosis"] > 3.0  # fat tails on t(4)
    assert -1.0 < facts["acf_r_lag1"] < 1.0


def test_index_alignment_report() -> None:
    px = [100.0, 101.0, 102.0]
    frame = _prices_frame("AAA", px)
    out = returns.compute_returns(frame, _rf(pd.bdate_range("2026-07-01", periods=3)))
    report = returns.index_alignment_report(out)
    assert report["duplicate_rows"] == 0
    assert report["infs"] == 0
    assert report["non_business_days"] == 0
