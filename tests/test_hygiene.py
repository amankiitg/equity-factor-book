"""Tests for Task 6: hygiene detection rules and the event log.

Sprint E7 appends the alpha-harness tests: the harness is the deliverable,
so its pieces are tested on synthetic data with known answers.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb import hygiene


def _returns_frame(ticker: str, r: list[float]) -> pd.DataFrame:
    idx = pd.MultiIndex.from_product(
        [pd.bdate_range("2026-07-01", periods=len(r)), [ticker]],
        names=["date", "ticker"],
    )
    arr = np.asarray(r, dtype=float)
    return pd.DataFrame({"r": arr, "g": arr, "excess": arr}, index=idx)


def test_clean_returns_nans_flagged_rows_only() -> None:
    r = [0.01, 0.01, 95.4286, 0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    frame = hygiene.apply_flags(_returns_frame("MI", r))
    cleaned = hygiene.clean_returns(frame)
    # the 95x day and the stale run go NaN
    assert np.isnan(cleaned.iloc[2])
    assert cleaned.iloc[5:].isna().all()
    # the untouched days are unchanged
    assert cleaned.iloc[0] == 0.01 and cleaned.iloc[3] == 0.01
    # the raw column and the flags are never rewritten
    assert frame["r"].iloc[2] == 95.4286
    assert bool(frame["outlier"].iloc[2]) is True


def test_clean_returns_keeps_the_index_shape() -> None:
    frame = hygiene.apply_flags(_returns_frame("MI", [0.01, 0.02, 95.4286]))
    cleaned = hygiene.clean_returns(frame)
    assert cleaned.index.equals(frame.index)
    assert len(cleaned) == 3


def test_clean_returns_rejects_a_wide_frame() -> None:
    frame = hygiene.apply_flags(_returns_frame("MI", [0.01, 0.02]))
    wide = frame[["r"]].unstack("ticker").rename(columns={"MI": "X"})
    try:
        hygiene.clean_returns(wide)
    except TypeError as exc:
        assert "r column" in str(exc)
    else:  # pragma: no cover - the message is the point of the branch
        raise AssertionError("a wide frame should not pass as a returns frame")


def test_detect_stale_flags_zero_runs() -> None:
    r = [0.001, 0.0, 0.0, 0.0, 0.0, 0.0, 0.002, 0.0, 0.001, 0.0, 0.0]
    frame = _returns_frame("AAA", r)
    stale = hygiene.detect_stale(frame, min_run=5)
    by_date = stale.droplevel("ticker")
    # days 2..6 (index 1..5) are inside a run of 5 zeros
    assert by_date.iloc[1:6].all()
    assert not by_date.iloc[0]
    assert not by_date.iloc[6]
    # a run of 2 zeros is not stale
    assert not by_date.iloc[9]
    assert not by_date.iloc[10]


def test_detect_outliers_threshold() -> None:
    assert hygiene.is_outlier(0.60) is True
    assert hygiene.is_outlier(-0.51) is True
    assert hygiene.is_outlier(0.49) is False
    assert hygiene.is_outlier(np.nan) is False


def test_apply_flags_adds_columns() -> None:
    frame = _returns_frame("AAA", [0.001, 0.6, 0.0, 0.0, 0.0, 0.0, 0.0])
    out = hygiene.apply_flags(frame, min_run=5)
    assert {"stale", "outlier"} <= set(out.columns)
    assert bool(out.loc[(pd.Timestamp("2026-07-02"), "AAA"), "outlier"])
    assert bool(out.loc[(pd.Timestamp("2026-07-03"), "AAA"), "stale"])


def test_build_events_corporate_actions_and_flags() -> None:
    idx = pd.MultiIndex.from_product(
        [pd.bdate_range("2026-07-01", periods=4), ["AAA"]], names=["date", "ticker"]
    )
    prices = pd.DataFrame(
        {
            "close": [100.0, 102.0, 101.0, 50.0],
            "adj_close": [100.0, 102.0, 101.0, 50.0],
            "dividend": [0.0, 0.0, 1.5, 0.0],
            "split_factor": [0.0, 0.0, 0.0, 2.0],
        },
        index=idx,
    )
    ret = _returns_frame("AAA", [0.001, 0.02, 0.6, -0.0099])
    ret = hygiene.apply_flags(ret)
    events = hygiene.build_events(
        prices, ret, pd.DataFrame(columns=["date", "ticker", "event_type"])
    )
    types = events["event_type"].tolist()
    assert "dividend_large" in types  # 1.5 / 101.0 > 1%
    assert "split" in types  # split factor 2.0 on the last day
    assert "outlier" in types  # |r| = 0.6


# --------------------------------------------------------------------------
# Sprint E7: the alpha harness. The harness is the deliverable, so its pieces
# are tested on synthetic data with known answers before any real signal runs
# through it.
# --------------------------------------------------------------------------


def _wide(seed: int = 0, n_days: int = 500, n_names: int = 80) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2018-01-02", periods=n_days)
    columns = [f"T{i:03d}" for i in range(n_names)]
    return pd.DataFrame(
        rng.normal(0.0004, 0.012, size=(n_days, n_names)),
        index=index,
        columns=columns,
    )


def _long_signal(wide: pd.DataFrame) -> pd.DataFrame:
    """The same-day return as a signal: perfect, and a pure leak."""
    forward = wide.fillna(0.0)
    long = forward.stack(future_stack=True).rename("signal").reset_index()
    long.columns = ["date", "ticker", "signal"]
    return long


def test_spearman_ic_is_one_for_a_perfect_signal() -> None:
    wide = _wide()
    signal = _long_signal(wide)
    ic = hygiene.spearman_ic(signal, wide, horizon=1)
    assert ic.mean() > 0.99


def test_newey_west_t_is_large_for_a_perfect_signal() -> None:
    wide = _wide()
    signal = _long_signal(wide)
    ic = hygiene.spearman_ic(signal, wide, horizon=1)
    assert hygiene.newey_west_t(ic) > 20


def test_the_deflated_sharpe_sinks_as_trials_grow() -> None:
    one = hygiene.deflated_sharpe(2.0, 1, 500)["deflated_sharpe"]
    many = hygiene.deflated_sharpe(2.0, 1000, 500)["deflated_sharpe"]
    assert one > many


def test_the_bonferroni_threshold_grows_with_trials() -> None:
    assert hygiene.bonferroni_t_threshold(10) < hygiene.bonferroni_t_threshold(1000)


def test_regime_ic_returns_the_three_terciles_and_pooled() -> None:
    index = pd.bdate_range("2020-01-02", periods=400)
    ic = pd.Series(np.random.default_rng(2).normal(0.02, 0.1, size=400), index=index)
    vix = pd.Series(np.linspace(12, 45, 400), index=index)
    table = hygiene.regime_ic(ic, vix)
    assert set(table["regime"]) == {"pooled", "vix_low", "vix_mid", "vix_high"}


def test_write_ledger_is_append_only(tmp_path: Path) -> None:
    path = tmp_path / "ledger.md"
    row = {
        "run_id": 1,
        "signal": "s",
        "variant": "raw_h1",
        "horizon": 1,
        "ic_mean": 0.01,
        "t_stat": 1.2,
        "deflated_sharpe": -1.0,
        "hlz_t_hurdle": 1.2,
        "bonferroni_t": 2.5,
        "verdict": "NULL",
        "note": "below the hurdle",
    }
    hygiene.write_ledger([row], path)
    before = path.read_text()
    hygiene.write_ledger([dict(row, run_id=2, verdict="PASS", note="survives")], path)
    after = path.read_text()
    assert before in after
    assert sum(line.startswith("| 1 | s |") for line in after.splitlines()) == 1
    assert sum(line.startswith("| 2 | s |") for line in after.splitlines()) == 1
    assert "Append-only" in after


def test_fundamental_law_uses_the_stored_breadth() -> None:
    index = pd.bdate_range("2020-01-02", periods=300)
    ic = pd.Series(np.random.default_rng(3).normal(0.02, 0.1, size=300), index=index)
    law = hygiene.fundamental_law(ic, breadth=100)
    assert law["implied_ir"] == pytest.approx(law["mean_ic"] * np.sqrt(100))
    assert "breadth" in law
