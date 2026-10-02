"""Sprint E7 Task 1: the signal library tests.

The shift audit is the criterion that matters most: a signal that still
works after being moved forward one day is leaking, and the test below
constructs one on purpose so the harness has to catch it.
"""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

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
    lagged = wide.shift(1).fillna(0.0)  # one day earlier: nothing left
    leaked = future.stack(future_stack=True).rename("signal").reset_index()
    leaked.columns = ["date", "ticker", "signal"]
    lagged_long = lagged.stack(future_stack=True).rename("signal").reset_index()
    lagged_long.columns = ["date", "ticker", "signal"]
    audit = hygiene.shift_audit(leaked, lagged_long, wide)
    assert audit["leak_flag"].any(), "the audit missed a leaked signal"


def test_the_shift_audit_clears_an_honest_signal() -> None:
    wide = _wide(seed=2)
    honest = alpha.momentum_12_1(wide)
    honest = honest.loc[honest["date"].isin(wide.index)]
    lagged = alpha.lagged_signal("momentum_12_1", wide, alpha.DATA_ROOT)
    audit = hygiene.shift_audit(honest, lagged, wide)
    assert not audit["leak_flag"].any()


def test_signals_return_long_frames_with_expected_columns() -> None:
    wide = _wide()
    signal = alpha.momentum_12_1(wide)
    assert list(signal.columns) == ["date", "ticker", "signal"]
    assert signal["date"].dtype.kind == "M"


def test_every_wide_based_builder_is_point_in_time() -> None:
    """Perturbing the returns row at t must not change the signal at t."""
    wide = _wide(seed=3)
    for name in ("momentum_12_1", "short_term_reversal"):
        signal = alpha._signal_for(name, wide, alpha.DATA_ROOT)
        perturbed = wide.copy()
        perturbed.iloc[-1] = perturbed.iloc[-1] + 0.05
        signal_perturbed = alpha._signal_for(name, perturbed, alpha.DATA_ROOT)
        before = signal.loc[signal["date"] == signal["date"].max()].set_index("ticker")[
            "signal"
        ]
        after = signal_perturbed.loc[
            signal_perturbed["date"] == signal_perturbed["date"].max()
        ].set_index("ticker")["signal"]
        assert np.allclose(before, after, equal_nan=True), name


def test_the_contract_multiplies_the_specific_volatility() -> None:
    """alpha_i = IC x sqrt(variance_i) x z_i x kappa, to the digit.

    The model publishes a specific variance and the contract multiplies a
    volatility. A 0.04 variance is a 0.20 volatility, so the answer is
    IC x 0.20 x z x kappa and not IC x 0.04 x z x kappa: the second number is
    five times smaller here and, worse, of a different shape across the
    cross-section.
    """
    alpha_vec = alpha.alpha_from_contract(
        ic=0.05,
        specific_variance=np.array([0.04, 0.09]),
        z=np.array([1.0, -2.0]),
        kappa=0.1,
    )

    assert alpha_vec[0] == pytest.approx(0.05 * 0.2 * 1.0 * 0.1)
    assert alpha_vec[1] == pytest.approx(0.05 * 0.3 * -2.0 * 0.1)
    # the negative control: the spelling this replaced, which the same inputs
    # would have produced, is a different number
    old = 0.05 * np.array([0.04, 0.09]) * np.array([1.0, -2.0]) * 0.1
    assert not np.allclose(alpha_vec, old)
    # and it is not a rescaling of it: the two disagree about which name is
    # the better bet, because the ratio alpha_1 / alpha_2 moves
    assert (alpha_vec[0] / abs(alpha_vec[1])) != pytest.approx(old[0] / abs(old[1]))


def test_a_name_with_no_variance_takes_the_cross_sections_median() -> None:
    """A name the model has no diagonal for is priced as the median name.

    Dropping it silently would change the book rather than the estimate, so the
    median variance stands in, and it is the median variance whose square root is
    taken: the stand-in has to be in the same units as the number it replaces.
    """
    variance = np.array([0.01, np.nan, 0.04])
    alpha_vec = alpha.alpha_from_contract(0.05, variance, np.ones(3), 0.1)

    assert np.all(np.isfinite(alpha_vec))
    assert alpha_vec[1] == pytest.approx(0.05 * np.sqrt(0.025) * 0.1)
    # a negative variance is impossible, so it earns no alpha rather than an
    # alpha with the wrong sign or a not-a-number the sizing cannot use
    negative = alpha.alpha_from_contract(0.05, np.array([-0.04]), np.ones(1), 0.1)
    assert negative[0] == pytest.approx(0.0)


def test_the_three_sites_size_from_the_one_contract() -> None:
    """One helper, three call sites, and no second spelling left anywhere.

    The evening job, the E8 conversion and the construction table each built
    their own alpha, and each multiplied the specific variance where the
    volatility belongs. The contract lives in `efb.alpha` now, and the point of
    the test is that no site kept a private spelling of it.
    """
    root = Path(alpha.__file__).resolve().parents[1]
    for relative in (
        "efb/alpha.py",
        "live/evening_job.py",
        "live/construction_table.py",
    ):
        source = (root / relative).read_text()
        assert "alpha_from_contract(" in source, relative
        # the spelling that put the variance under sigma: gone from every site
        assert "specific * z * kappa" not in source, relative
        assert "diag_v2 * z * KAPPA" not in source, relative


def test_the_conversion_rebuild_touches_only_the_conversion() -> None:
    """The narrow rebuild is one artifact per signal, and nothing else.

    The IC, the shift audits, the neutralized IC, the quantile portfolios and
    the multiple-testing ledger are all written by `run`, and the reason this
    function exists is that none of them is owed a second measurement when the
    contract is corrected: re-running `run` would append thirty ledger rows
    that were never executed and move F7.3 with them.
    """
    source = inspect.getsource(alpha.rebuild_conversion)
    assert "alpha.parquet" in source
    for forbidden in (
        "ic.parquet",
        "audit.parquet",
        "neutral_ic.parquet",
        "quantiles.parquet",
        "regime_ic.parquet",
        "summary.parquet",
        "write_ledger",
    ):
        assert forbidden not in source, forbidden


@pytest.mark.slow
@pytest.mark.integration
def test_the_conversion_rebuild_reproduces_the_stored_artifact() -> None:
    """The rebuilt conversion is the one on disk, for the signal's own inputs.

    One signal is enough: every signal goes through the same
    `_converted_alpha`. The comparison is against the stored artifact rather
    than against a number written here, so a refresh that wrote some other
    spelling fails. `store=False` keeps the test from rewriting an artifact,
    and the hash either side of the call is what says it did not.
    """
    path = Path(alpha.DATA_ROOT) / "alpha" / "momentum_12_1" / "alpha.parquet"
    if not path.exists():
        pytest.skip("the E7 conversion has not been written yet")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    summary = alpha.rebuild_conversion(store=False, signals=("momentum_12_1",))
    assert list(summary["signal"]) == ["momentum_12_1"]
    row = summary.iloc[0]
    stored = pd.read_parquet(path)
    assert int(row["n_rows"]) == len(stored)
    assert float(row["mean_abs_alpha"]) == pytest.approx(
        float(stored["alpha"].abs().mean()), rel=1e-12
    )
    assert float(row["mean_abs_alpha_xs_v2"]) == pytest.approx(
        float(stored["alpha_xs_v2"].abs().mean()), rel=1e-12
    )
    assert float(row["previous_mean_abs_alpha"]) == pytest.approx(
        float(stored["alpha"].abs().mean()), rel=1e-12
    )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
