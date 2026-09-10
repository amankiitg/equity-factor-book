"""Tests for Task 5: seed portfolios and the risk decomposition."""

import numpy as np
import pandas as pd
import pytest

from efb import portfolios as pf


def _members(
    tickers: list[str], periods: int = 60, start: str = "2024-01-02"
) -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=periods)
    return pd.DataFrame(True, index=idx, columns=tickers)


def test_ew_seed_weights_sum_to_one_and_follow_membership() -> None:
    members = _members(["AAA", "BBB", "CCC"])
    members.loc[members.index[-1], "CCC"] = False
    w = pf.ew_seed_weights(members)
    assert w.sum(axis=1).dropna().eq(1.0).all()
    assert w.loc[members.index[-1], "CCC"] == 0.0
    assert w.loc[members.index[-1], "AAA"] == pytest.approx(0.5)


def test_ew_seed_carries_survivorship_caveat() -> None:
    members = _members(["AAA", "BBB"])
    long_frame = pf.to_long_weights(pf.ew_seed_weights(members), caveat=True)
    assert bool(long_frame["survivorship_caveat"].all())
    ls_frame = pf.to_long_weights(pf.ew_seed_weights(members), caveat=False)
    assert not bool(ls_frame["survivorship_caveat"].any())


def test_momentum_ls_is_dollar_and_sector_neutral() -> None:
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2023-01-02", periods=500)
    # AAA and CCC have strong upward drift, BBB and DDD strongly negative
    r = pd.DataFrame(
        {
            "AAA": rng.normal(0.003, 0.01, len(dates)),
            "BBB": rng.normal(-0.003, 0.01, len(dates)),
            "CCC": rng.normal(0.002, 0.01, len(dates)),
            "DDD": rng.normal(-0.002, 0.01, len(dates)),
        },
        index=dates,
    )
    members = pd.DataFrame(True, index=dates, columns=r.columns)
    sectors = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC", "DDD"],
            "gics_sector": ["Tech", "Tech", "Energy", "Energy"],
        }
    )
    w = pf.momentum_ls_weights(
        r, members, sectors, lookback=126, quantile=0.5, min_names=4
    )
    active = w.loc[w.abs().sum(axis=1) > 0]
    assert not active.empty
    assert active.sum(axis=1).abs().max() < 1e-9  # dollar neutral
    for names in (["AAA", "BBB"], ["CCC", "DDD"]):
        sector_net = active[names].sum(axis=1)
        assert sector_net.abs().max() < 1e-9  # sector neutral
    # the momentum winners are long, losers short
    last = active.iloc[-1]
    assert last["AAA"] > 0 and last["CCC"] > 0
    assert last["BBB"] < 0 and last["DDD"] < 0


def test_risk_decomposition_matches_hand_computation() -> None:
    w = pd.Series({"AAA": 0.6, "BBB": 0.4})
    B = pd.DataFrame({"mkt_rf": [1.0, 0.5], "smb": [0.0, 0.5]}, index=["AAA", "BBB"])
    F = pd.DataFrame(
        np.eye(2) * 0.0004, index=["mkt_rf", "smb"], columns=["mkt_rf", "smb"]
    )
    idio_var = pd.Series({"AAA": 0.0009, "BBB": 0.0001})
    out = pf.risk_decomposition(w, B, F, idio_var)
    beta_p = B.T @ w
    factor_var = float(beta_p @ F.to_numpy() @ beta_p)
    idio = float((w**2 * idio_var).sum())
    assert out["factor_variance"] == pytest.approx(factor_var, rel=1e-12)
    assert out["idio_variance"] == pytest.approx(idio, rel=1e-12)
    assert out["total_variance"] == pytest.approx(factor_var + idio, rel=1e-12)
    assert out["factor_share"] == pytest.approx(
        factor_var / (factor_var + idio), rel=1e-12
    )
    assert out["portfolio_beta_mkt_rf"] == pytest.approx(0.8, rel=1e-12)


def test_risk_decomposition_rejects_wrong_idio_type() -> None:
    w = pd.Series({"AAA": 1.0})
    B = pd.DataFrame({"mkt_rf": [1.0]}, index=["AAA"])
    F = pd.DataFrame({"mkt_rf": [0.0004]}, index=["mkt_rf"], columns=["mkt_rf"])
    with pytest.raises(ValueError, match="idio_var"):
        pf.risk_decomposition(w, B, F, pd.DataFrame({"AAA": [0.1]}, index=["AAA"]))


def test_risk_decomposition_handles_missing_names() -> None:
    w = pd.Series({"AAA": 0.5, "BBB": 0.5})
    B = pd.DataFrame({"mkt_rf": [1.0, np.nan]}, index=["AAA", "BBB"])
    F = pd.DataFrame({"mkt_rf": [0.0004]}, index=["mkt_rf"], columns=["mkt_rf"])
    idio_var = pd.Series({"AAA": 0.0001, "BBB": 0.0001})
    out = pf.risk_decomposition(w, B, F, idio_var)
    # the name without a loading contributes only its idio variance
    assert out["idio_variance"] == pytest.approx(0.5**2 * 0.0001 + 0.5**2 * 0.0001)
    assert np.isfinite(out["total_variance"])


def test_predict_portfolio_vol_known_numbers() -> None:
    w = pd.Series({"AAA": 0.5, "BBB": 0.5})
    betas = pd.Series({"AAA": 1.0, "BBB": 0.0})
    idio_var = pd.Series({"AAA": 0.0004, "BBB": 0.0004})
    vol, factor_var, idio_var_out = pf.predict_portfolio_vol(w, betas, 0.0004, idio_var)
    assert factor_var == pytest.approx((0.5 * 1.0) ** 2 * 0.0004, rel=1e-12)
    assert idio_var_out == pytest.approx(0.25 * 0.0004 + 0.25 * 0.0004, rel=1e-12)
    assert vol == pytest.approx(np.sqrt((factor_var + idio_var_out) * 252), rel=1e-12)


def test_portfolio_risk_history_bias_ratio() -> None:
    dates = pd.bdate_range("2023-01-02", periods=400)
    rng = np.random.default_rng(5)
    r = pd.DataFrame(
        {
            "AAA": rng.normal(0, 0.01, len(dates)),
            "BBB": rng.normal(0, 0.01, len(dates)),
        },
        index=dates,
    )
    weights = pd.DataFrame(0.5, index=dates, columns=["AAA", "BBB"])
    betas = pd.DataFrame(1.0, index=dates, columns=["AAA", "BBB"])
    factor_var = pd.Series(0.0001, index=dates)
    idio_var = pd.DataFrame(0.0001, index=dates, columns=["AAA", "BBB"])
    history = pf.portfolio_risk_history(
        weights, r, betas, factor_var, idio_var, forward=63
    )
    assert not history.empty
    assert {
        "predicted_vol_ann",
        "realized_vol_ann",
        "bias_ratio",
        "factor_share",
    } <= set(history.columns)
    # with no factor structure the idio term dominates and bias is finite
    assert np.isfinite(history["bias_ratio"]).all()
