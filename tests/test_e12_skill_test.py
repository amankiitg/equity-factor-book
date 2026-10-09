"""Sprint E12 item 7: the skill test, and the bar it refuses to clear.

The sprint's third criterion is a rule about what may be claimed, so the tests
here are about the rule as much as the arithmetic: a t below the bar claims
nothing, a t above it says so, the days-to-detect table is the closed form rather
than a guess, and the Sharpe's standard error comes from the E1 library rather than
from a second implementation of the same estimator.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb import attribution, perf

ROOT = Path(__file__).resolve().parents[1]
SEED_ATTRIBUTION = ROOT / "data" / "attribution" / "daily.parquet"


def _frame(idio: list[float], total: list[float] | None = None) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=len(idio), freq="B"),
            "pnl_idio": idio,
            "pnl_total": total if total is not None else idio,
        }
    )


def test_the_mean_its_error_and_the_t_are_the_arithmetic() -> None:
    """Seven numbers by hand: mean, sd, se = sd/sqrt(n), t = mean/se, IR."""
    idio = [0.01, -0.005, 0.02, 0.0, 0.015, -0.01, 0.005]
    result = attribution.skill_test(_frame(idio))
    values = np.asarray(idio, dtype=float)
    mean = float(values.mean())
    sd = float(values.std(ddof=1))
    se = sd / math.sqrt(len(values))

    assert result["n_days"] == 7
    assert result["idio_mean"] == pytest.approx(mean)
    assert result["idio_sd"] == pytest.approx(sd)
    assert result["idio_se"] == pytest.approx(se)
    assert result["t_stat"] == pytest.approx(mean / se)
    assert result["ir_annual"] == pytest.approx(mean / sd * math.sqrt(252))
    # The information ratio's own standard error, at this sample size.
    assert result["ir_se"] == pytest.approx(
        math.sqrt((1.0 + result["ir_annual"] ** 2 / 2.0) / len(values))
    )


def test_the_sharpe_and_its_errors_are_the_e1_librarys_own() -> None:
    """Not a re-implementation: the same function the E1 report used."""
    idio = [0.01, -0.005, 0.02, 0.0, 0.015, -0.01, 0.005, 0.002]
    frame = _frame(idio)
    result = attribution.skill_test(frame)
    total = frame["pnl_total"]

    assert result["sharpe_annual"] == pytest.approx(perf.annualized_sharpe(total))
    # The library returns the **daily** error, so the annualized one carries the
    # same sqrt(252) the Sharpe itself carries.
    assert result["sharpe_se_iid"] == pytest.approx(
        perf.sharpe_se_iid(total) * math.sqrt(252)
    )
    assert result["sharpe_se_lo2002"] == pytest.approx(
        perf.sharpe_se_lo2002(total) * math.sqrt(252)
    )


def test_the_days_to_detect_is_the_closed_form() -> None:
    """`n = (t / IR_daily)^2`, so an IR of 1.0 needs four years at t of 2."""
    result = attribution.skill_test(_frame([0.01, -0.005, 0.02, 0.0, 0.015]))
    days = result["days_to_detect"]
    for ir, expected in ((0.25, 16128), (0.5, 4032), (1.0, 1008), (2.0, 252)):
        assert days[ir] == expected, ir
    # And a stated power is not the same thing: the table is a two-sided t of two,
    # which is the bar F12.3 sets, not an 80% power calculation.
    assert result["target_t"] == attribution.DETECTION_T == 2.0
    # A single day of testing cannot show an annualized IR of 0.25: the table is
    # the reason the thirty-day window is a machinery check, not a performance one.
    assert days[0.25] > 40 * 30


def test_a_small_t_claims_nothing_and_says_luck() -> None:
    result = attribution.skill_test(_frame([0.001, -0.001] * 30))
    assert result["skill_claimed"] is False
    assert "no skill is claimed" in result["verdict"]
    assert "luck" in result["verdict"]


def test_a_t_above_the_bar_is_reported_as_clearing_it() -> None:
    """A large, steady edge: the rule has to be able to say yes, not only no."""
    result = attribution.skill_test(_frame([0.004, 0.005, 0.006, 0.003] * 40))
    assert result["t_stat"] > attribution.DETECTION_T
    assert result["skill_claimed"] is True
    assert "exceeds" in result["verdict"]


def test_too_few_days_reports_rather_than_raising() -> None:
    for frame in (pd.DataFrame(), _frame([0.001])):
        result = attribution.skill_test(frame)
        assert result["n_days"] == len(frame)
        assert result["t_stat"] is None
        assert result["skill_claimed"] is False
        # The days-to-detect table is a property of the bar and the imagined edge,
        # so it is reported even with nothing to test: a one-day window still has to
        # say how long an edge of a given size would need.
        assert result["days_to_detect"][1.0] == 1008
        assert result["days_to_detect"][0.25] == 16128


def test_a_book_with_no_dispersion_is_not_tested() -> None:
    result = attribution.skill_test(_frame([0.0] * 10))
    assert result["idio_sd"] == 0.0
    assert result["t_stat"] is None
    assert result["skill_claimed"] is False


@pytest.mark.integration
def test_the_seed_book_clears_the_bar_and_the_number_is_still_not_a_discovery() -> None:
    """The sprint's own artifact, and the reading its numbers actually support.

    The seed book's fourteen years are distinguishable from zero: the t-statistic
    is over three. That is not the live book, which trades a different signal and is
    documented as a null book, and it is not a discovery either: E10's design search
    picked the (rho, phi) whose net annualized Sharpe is closest to 1.0 on this
    sample, so a Sharpe near 0.85 measured on the same sample is the selection
    working rather than an edge found. What the criterion requires is that the number
    travels with its standard error and that the bar is applied mechanically, which
    is what this pins.
    """
    if not SEED_ATTRIBUTION.exists():
        pytest.skip("the seed attribution artifact is not built")
    frame = pd.read_parquet(SEED_ATTRIBUTION)
    result = attribution.skill_test(frame)

    assert result["n_days"] == len(frame) > 3000
    assert result["idio_mean"] is not None
    assert result["idio_se"] is not None
    # The Sharpe is reported with both standard errors, and the autocorrelation
    # correction moves it, which is why the library's Lo 2002 form is the one quoted.
    assert result["sharpe_annual"] == pytest.approx(0.849, abs=0.01)
    assert result["sharpe_se_lo2002"] == pytest.approx(0.258, abs=0.01)
    assert result["sharpe_se_iid"] != result["sharpe_se_lo2002"]
    # The rule, applied rather than interpreted: t above two is a cleared bar.
    assert result["t_stat"] > attribution.DETECTION_T
    assert result["skill_claimed"] is True
    assert "exceeds" in result["verdict"]
    # And the bar itself is written down, so the verdict cannot read as an opinion.
    assert result["target_t"] == 2.0
    assert result["days_to_detect"][1.0] == 1008
    assert result["days_to_detect"][0.5] == 4032
