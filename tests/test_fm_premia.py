"""Sprint E3 Task 6: Fama-MacBeth premia and the D2 tab.

The premia test is the one with content: a Newey-West standard error on a
known autocorrelated series, and the rule that a premium with a small t
statistic is reported as unpriced rather than dropped.

The D2 tests execute every panel builder against the current artifacts and
assert a non-empty frame, which is the check that would have caught the D1
defect where a long artifact was read as wide and the chart came back empty.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb.models import fundamental as fx

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def _factors(days: int = 400, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2019-01-01", periods=days)
    return pd.DataFrame(
        {
            "market": rng.normal(0.0004, 0.01, days),
            "size": rng.normal(0.0, 0.002, days),
            "momentum": rng.normal(0.0002, 0.003, days),
        },
        index=index,
    )


def test_fama_macbeth_recovers_a_known_premium() -> None:
    rng = np.random.default_rng(7)
    days = 3000
    series = rng.normal(0.0005, 0.002, days)
    frame = pd.DataFrame(
        {"market": series}, index=pd.bdate_range("2010-01-01", periods=days)
    )
    table = fx.fama_macbeth(frame)
    row = table.iloc[0]
    assert row["premium_daily"] == pytest.approx(series.mean())
    assert row["premium_annualized"] == pytest.approx(series.mean() * 252)
    # the standard error of the mean for i.i.d. data. The Newey-West
    # autocovariance terms are sample noise at this length, so the comparison
    # is to within a couple of percent rather than to machine precision.
    expected = series.std(ddof=0) / np.sqrt(days)
    assert row["nw_se"] == pytest.approx(expected, rel=0.05)
    assert row["n_days"] == days


def test_newey_west_widens_the_error_for_autocorrelated_returns() -> None:
    rng = np.random.default_rng(11)
    days = 2000
    noise = rng.normal(0, 0.002, days)
    series = np.zeros(days)
    for i in range(1, days):
        series[i] = 0.6 * series[i - 1] + noise[i]
    frame = pd.DataFrame(
        {"market": series}, index=pd.bdate_range("2010-01-01", periods=days)
    )
    table = fx.fama_macbeth(frame)
    naive = series.std(ddof=0) / np.sqrt(days)
    assert float(table["nw_se"].iloc[0]) > naive


def test_unpriced_premia_are_labelled_not_dropped() -> None:
    rng = np.random.default_rng(13)
    days = 500
    frame = pd.DataFrame(
        {
            "priced": rng.normal(0.002, 0.002, days),
            "unpriced": rng.normal(0.0, 0.02, days),
        },
        index=pd.bdate_range("2010-01-01", periods=days),
    )
    table = fx.fama_macbeth(frame).set_index("factor")
    assert len(table) == 2
    assert bool(table.loc["priced", "priced"]) is True
    assert bool(table.loc["unpriced", "priced"]) is False
    assert np.isfinite(table.loc["unpriced", "t_stat"])


def test_ewma_factor_covariance_is_symmetric_and_positive_semidefinite() -> None:
    frame = _factors(days=600)
    covariance = fx.ewma_factor_cov(frame, half_life=90, nw_lag=2)
    values = covariance.to_numpy()
    assert values == pytest.approx(values.T)
    eigenvalues = np.linalg.eigvalsh(values)
    assert eigenvalues.min() > -1e-18


def test_ewma_factor_covariance_weights_recent_data_more() -> None:
    """A loud patch at the end raises the estimate, at the start lowers it."""
    rng = np.random.default_rng(17)
    index = pd.bdate_range("2019-01-01", periods=600)
    quiet = pd.DataFrame(
        {"market": rng.normal(0, 0.001, 600), "size": rng.normal(0, 0.001, 600)},
        index=index,
    )
    loud_end = quiet.copy()
    loud_end.iloc[-60:] = loud_end.iloc[-60:] * 10.0
    loud_start = quiet.copy()
    loud_start.iloc[:60] = loud_start.iloc[:60] * 10.0
    equal_end = float(np.trace(loud_end.cov().to_numpy()))
    equal_start = float(np.trace(loud_start.cov().to_numpy()))
    fast_end = float(np.trace(fx.ewma_factor_cov(loud_end, half_life=20).to_numpy()))
    fast_start = float(
        np.trace(fx.ewma_factor_cov(loud_start, half_life=20).to_numpy())
    )
    assert fast_end > equal_end
    assert fast_start < equal_start


# --------------------------------------------------------------------------
# D2: every panel builder must return rows from the current artifacts
# --------------------------------------------------------------------------


def _read(rel: str) -> pd.DataFrame:
    path = DATA / rel
    if not path.exists():
        pytest.skip(f"{rel} not built yet")
    return pd.read_parquet(path)


@pytest.mark.integration
def test_d2_factor_return_panel_is_not_empty() -> None:
    from dashboard.tabs import d02_factor_risk as d2

    frame = _read("models/XS-v1/factor_returns.parquet")
    for factor in ("market", "momentum", "sector_10"):
        chart = d2.factor_return_chart(frame, factor)
        assert not chart.empty, factor
        assert {"daily", "cumulative"} <= set(chart.columns)


@pytest.mark.integration
def test_d2_premia_panel_is_not_empty() -> None:
    from dashboard.tabs import d02_factor_risk as d2

    frame = _read("eval/xs_fm_premia.parquet")
    for period in frame["period"].unique():
        table = d2.premia_table(frame, period)
        assert not table.empty, period
        assert "verdict" in table.columns


@pytest.mark.integration
def test_d2_quality_and_coverage_panels_are_not_empty() -> None:
    from dashboard.tabs import d02_factor_risk as d2

    quality = d2.r_squared_series(_read("models/XS-v1/xs_r2.parquet"))
    assert not quality.empty
    assert quality["running_mean"].notna().all()
    coverage = d2.descriptor_coverage(_read("models/XS-v1/descriptors.parquet"))
    assert not coverage.empty
    assert coverage.to_numpy().max() > 100


@pytest.mark.integration
def test_d2_covariance_and_fmp_panels_are_not_empty() -> None:
    from dashboard.tabs import d02_factor_risk as d2

    covariance = _read("models/XS-v1/factor_cov.parquet")
    correlation = d2.factor_correlation(covariance)
    assert correlation.shape == covariance.shape
    assert np.nanmax(np.abs(correlation.to_numpy())) <= 1.0 + 1e-9
    fmp = _read("models/XS-v1/fmp_weights.parquet")
    for kind in fmp["kind"].unique():
        table = d2.fmp_explorer(fmp, "size", kind)
        assert not table.empty, kind
        assert table["weight"].abs().sum() > 0


@pytest.mark.integration
def test_d2_risk_decomposition_panels_are_not_empty() -> None:
    from dashboard.tabs import d02_factor_risk as d2

    frame = _read("eval/xs_risk_decomposition.parquet")
    for book in frame["book"].unique():
        table = d2.risk_table(frame, book)
        assert not table.empty, book
        assert table.attrs["sigma_p"] > 0
        assert np.isfinite(table.attrs["residual_weight"])
        mcr = d2.mcr_chart(frame, book)
        assert not mcr.empty, book


@pytest.mark.integration
def test_d2_exposure_and_residual_panels_are_not_empty() -> None:
    from dashboard.tabs import d02_factor_risk as d2

    exposure = _read("eval/xs_exposure_timeseries.parquet")
    timing = d2.exposure_timing(exposure, "seed_mom_ls", "momentum")
    assert not timing.empty
    assert timing["momentum"].abs().max() > 0
    panel = d2.residual_covariance_panel(_read("eval/xs_residual_covariance.parquet"))
    assert not panel.empty
    assert panel.shape[0] == 2


def test_d2_panels_raise_when_a_read_is_empty() -> None:
    from dashboard.tabs import d02_factor_risk as d2

    empty = pd.DataFrame(columns=["date", "factor", "f"])
    with pytest.raises(ValueError):
        d2.factor_return_chart(empty, "market")
    with pytest.raises(ValueError):
        d2.factor_return_chart(
            pd.DataFrame({"date": [1], "factor": ["x"], "f": [0.0]}), "missing"
        )
    with pytest.raises(ValueError):
        d2.premia_table(pd.DataFrame(), "full_sample")
    with pytest.raises(ValueError):
        d2.factor_correlation(pd.DataFrame())
    with pytest.raises(ValueError):
        d2.descriptor_coverage(
            pd.DataFrame(
                {
                    "date": [1],
                    "ticker": ["A"],
                    "descriptor": ["size"],
                    "value_z": [np.nan],
                }
            )
        )


def test_d2_uploaded_weights_reads_ticker_and_weight() -> None:
    from dashboard.tabs import d02_factor_risk as d2

    class _Upload:
        def __init__(self, text: str) -> None:
            import io

            self._buffer = io.BytesIO(text.encode())

        def read(self, *args: object) -> bytes:
            return self._buffer.read(*args)

        def seek(self, *args: object) -> int:
            return self._buffer.seek(*args)

    from unittest.mock import patch

    csv = "ticker,weight\nAAPL,0.5\nMSFT,-0.5\n"
    with patch.object(
        pd,
        "read_csv",
        return_value=pd.DataFrame({"ticker": ["AAPL", "MSFT"], "weight": [0.5, -0.5]}),
    ):
        weights = d2.uploaded_weights(_Upload(csv))
    assert weights.sum() == pytest.approx(0.0)
    assert weights["AAPL"] == 0.5


@pytest.mark.integration
def test_d2_tab_is_registered_and_the_earlier_tabs_still_render() -> None:
    app = (ROOT / "dashboard" / "app.py").read_text()
    assert "D2 Factor Model and Risk" in app
    assert "d02_factor_risk.render()" in app
    for tab in ("D0 Data Health", "D1 Exposures", "Methodology"):
        assert tab in app
