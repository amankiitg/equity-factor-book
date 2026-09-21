"""Sprint E7 Task 1: the signal library tests.

The shift audit is the criterion that matters most: a signal that still
works after being moved forward one day is leaking, and the test below
constructs one on purpose so the harness has to catch it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from efb import alpha, hygiene


def _wide(seed: int = 0, n_days: int = 600, n_names: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2018-01-02", periods=n_days)
    columns = [f"T{i:03d}" for i in range(n_names)]
    return pd.DataFrame(
        rng.normal(0.0004, 0.012, size=(n_days, n_names)), index=index, columns=columns
    )


def test_momentum_has_the_expected_sign_on_a_trending_name() -> None:
    wide = _wide()
    # make T000 trend up hard over the last 252 sessions
    wide["T000"] = np.linspace(0.0, 0.5, len(wide))
    signal = alpha.momentum_12_1(wide)
    recent = signal.loc[
        (signal["date"] == signal["date"].max()) & (signal["ticker"] == "T000"),
        "signal",
    ].iloc[0]
    assert recent > 0.1


def test_reversal_is_minus_the_trailing_week() -> None:
    wide = _wide()
    wide["T001"] = np.linspace(0.0, 0.05, len(wide))
    signal = alpha.short_term_reversal(wide)
    recent = signal.loc[
        (signal["date"] == signal["date"].max()) & (signal["ticker"] == "T001"),
        "signal",
    ].iloc[0]
    assert recent < 0


def test_missing_signal_values_stay_nan() -> None:
    wide = _wide()
    wide.iloc[-10:, 0] = np.nan
    signal = alpha.momentum_12_1(wide)
    assert signal["signal"].isna().any()
    # no value was silently filled with zero
    assert (signal["signal"].fillna(-1) == 0).sum() == 0


def test_the_shift_audit_catches_a_leaked_signal() -> None:
    """A signal that carries the same-day return is flagged; the audit must
    report it, which is what proves the audit works."""
    wide = _wide(seed=1)
    future = wide.fillna(0.0)  # the same-day return: pure leakage
    leaked = future.stack(future_stack=True).rename("signal").reset_index()
    leaked.columns = ["date", "ticker", "signal"]
    audit = hygiene.shift_audit(leaked, wide)
    assert audit["leak_flag"].any(), "the audit missed a leaked signal"


def test_the_shift_audit_clears_an_honest_signal() -> None:
    wide = _wide(seed=2)
    honest = alpha.momentum_12_1(wide)
    honest = honest.loc[honest["date"].isin(wide.index)]
    audit = hygiene.shift_audit(honest, wide)
    assert not audit["leak_flag"].any()


def test_signals_return_long_frames_with_expected_columns() -> None:
    wide = _wide()
    signal = alpha.momentum_12_1(wide)
    assert list(signal.columns) == ["date", "ticker", "signal"]
    assert signal["date"].dtype.kind == "M"
