"""Sprint E9 Task 1 to 5: the cost model and the capacity curve."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb import costs

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def test_the_impact_term_grows_with_the_square_root_of_trade_size() -> None:
    small = costs._trade_cost(
        np.array([0.01]),
        np.array([0.001]),
        np.array([0.02]),
        np.array([1e7]),
        aum=1e8,
        k=0.5,
    )
    large = costs._trade_cost(
        np.array([0.04]),
        np.array([0.001]),
        np.array([0.02]),
        np.array([1e7]),
        aum=1e8,
        k=0.5,
    )
    # quadrupling the trade size less than quadruples the cost per dollar
    assert 4 * small < large < 16 * small


def test_doubling_aum_raises_cost_per_dollar_by_about_41_percent() -> None:
    trade = np.array([0.01])
    one = costs._trade_cost(
        trade, np.array([0.0]), np.array([0.02]), np.array([1e7]), 1e8, 0.5
    )
    two = costs._trade_cost(
        trade, np.array([0.0]), np.array([0.02]), np.array([1e7]), 2e8, 0.5
    )
    # only the impact term changes: sqrt(2) about 1.414, plus the linear
    # part; assert the impact-only ratio is close to sqrt(2)
    impact_one = one
    impact_two = two
    assert np.isclose(impact_two / impact_one, np.sqrt(2.0), rtol=0.05)


@pytest.mark.integration
def test_the_chosen_spread_schedule_is_monotone_in_size() -> None:
    curves = costs.cost_curves(DATA, store=False)
    assert not curves.empty
    correlation = float(curves["spread_size_rank_correlation"].iloc[0])
    assert np.isfinite(correlation)
    # smaller names wider: the chosen schedule falls as the size rank rises
    assert correlation < 0.0


@pytest.mark.integration
@pytest.mark.slow
def test_the_probe_records_why_the_free_estimators_were_set_aside() -> None:
    probe = costs.spread_probe(DATA, store=False)
    assert not probe.empty
    # the overnight-adjusted Corwin-Schultz floors every name at zero
    assert (probe["cs_adjusted_half_spread"] == 0.0).all()
    # the Abdi-Ranaldo estimate has essentially no size gradient
    ar_corr = float(
        probe["abdi_ranaldo_half_spread"].corr(probe["size_decile"], method="spearman")
    )
    assert abs(ar_corr) < 0.1
    # the chosen schedule is 10 bp for the smallest and 1 bp for the largest
    assert np.isclose(
        probe.loc[probe["size_decile"] == 0, "schedule_half_spread"].iloc[0], 1e-3
    )
    assert np.isclose(
        probe.loc[probe["size_decile"] == 9, "schedule_half_spread"].iloc[0], 1e-4
    )


@pytest.mark.integration
def test_the_capacity_artifacts_are_written() -> None:
    capacity_path = DATA / "costs" / "capacity.parquet"
    if not capacity_path.exists():
        pytest.skip("the E9 run has not completed")
    capacity = pd.read_parquet(capacity_path)
    assert {"rho", "k", "aum", "gross_sharpe", "net_sharpe"} <= set(capacity.columns)
    halving = pd.read_parquet(DATA / "costs" / "capacity_halving.parquet")
    assert {"rho", "k", "halving_aum"} <= set(halving.columns)
    sensitivity = pd.read_parquet(
        DATA / "costs" / "capacity_spread_sensitivity.parquet"
    )
    assert {"rho", "spread_multiplier", "halving_aum"} <= set(sensitivity.columns)


@pytest.mark.integration
def test_the_e11_constraints_charge_borrow_at_e11s_rate() -> None:
    """The four constraints are measured on the E9 book and stored in E9.

    Borrow is charged on the short leg at the constant the live path reads, the
    $250 floor is applied at the tested AUM, a reversal costs two events, and
    borrow availability is recorded as having no history.
    """
    path = DATA / "costs" / "e11_constraints.parquet"
    if not path.exists():
        pytest.skip("the E9 run has not completed")
    row = pd.read_parquet(path).iloc[0]
    # The row records the rate the study was measured at, which is not the same
    # question as the rate the live path charges today: on 2026-10-23 the owner moved
    # `BORROW_RATE` from the E6 provisional 2% to 0.35% (docs/borrow_rate.md), and the
    # stored row is a measurement made before that. Asserting the artifact against the
    # live constant would make an owner's rate change a study defect. So the row is
    # checked for having recorded *a* rate, and the live path is checked separately,
    # below, for charging the one it declares.
    assert row["borrow_rate"] > 0.0
    assert costs.BORROW_RATE > 0.0
    assert row["min_notional"] == costs.ALPACA_MIN_NOTIONAL
    assert row["tested_aum"] == 1_000_000.0
    # borrow is charged on the short leg: a real, small share of the cost
    assert row["short_gross"] > 0.0
    assert 0.0 < row["borrow_cost_share"] < 0.05
    # the $250 floor skips legs but barely moves the book at any AUM
    assert 0.0 < row["min_notional_skipped_legs_share"] < 0.2
    assert 0.99 < row["min_notional_ir_ratio"] <= 1.0
    # a reversal is two cost events, and a third of the legs are reversals
    assert 0.2 < row["reversal_legs_share"] < 0.5
    assert 0.0 < row["reversal_ir_upper_bound_ratio"] < 1.0
    # borrow availability has no history: recorded, with size as a labelled proxy
    assert row["borrow_availability_history"] == 0.0
    assert row["borrow_availability_proxy"] == 1.0


def test_the_live_cost_estimate_charges_the_rate_the_module_declares(
    tmp_path: Path,
) -> None:
    """What the evening charges is `BORROW_RATE`, whatever the E9 study recorded.

    One book, one close, and the borrow term read back out of the estimate: half a
    nav of short gross over a 21-session horizon costs `BORROW_RATE x 0.5 x 21/252`.
    """
    from live import evening_job
    from tests.test_e11_live_costs import _prices, _write_root

    prices = _prices({"AAA": [1_000_000.0] * 63, "BBB": [1_000_000.0] * 63})
    root = _write_root(tmp_path, prices)
    cost, _thin = evening_job._cost_decomposition(
        np.array([0.5, -0.5]),
        ["AAA", "BBB"],
        np.array([4e-4, 4e-4]),
        1_000_000.0,
        root,
        None,
    )
    expected_bps = costs.BORROW_RATE * 0.5 * (evening_job.HORIZON / 252.0) * 1e4
    assert cost["borrow_bps"] == pytest.approx(expected_bps, rel=1e-9)


@pytest.mark.integration
def test_e9_stores_the_e11_constraints_beside_its_own_numbers() -> None:
    import json

    payload = json.loads((ROOT / "sprints" / "E9" / "RESULTS.json").read_text())
    numbers = payload["criteria"]["F9.1"]["stored_numbers"]
    stored = numbers.get("e11_constraints")
    assert stored, "E9 stores no E11 constraint measurement"
    assert {"borrow_rate", "min_notional", "borrow_availability_history"} <= set(stored)
    # the scored numbers are still there beside it
    assert "n_monotonicity_violations_net_sharpe" in numbers
    assert "halving_aum_by_rho_k" in numbers
