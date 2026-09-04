"""Tests for Task 9: F1 criteria evaluation and RESULTS.json."""

import json
from pathlib import Path

import pandas as pd
import pytest

from efb import evaluate


def _series(values: list[float], start: str = "2020-01-02") -> pd.Series:
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)))


def test_criteria_have_all_five_keys() -> None:
    criteria = evaluate.evaluate_criteria(
        yf_coverage=0.9,
        current_coverage=1.0,
        ten_year_coverage=0.95,
        interior_nans=0,
        f13_corr=0.96,
        f14_max_bp=0.5,
        f14_mean_bp=0.01,
        survivorship_fraction=0.8,
        bias_bp_per_year=12.0,
    )
    assert set(criteria) == {"F1.1", "F1.2", "F1.3", "F1.4", "F1.5"}


def test_verdicts_follow_thresholds() -> None:
    criteria = evaluate.evaluate_criteria(
        yf_coverage=0.9,
        current_coverage=1.0,
        ten_year_coverage=0.95,
        interior_nans=3,
        f13_corr=0.92,
        f14_max_bp=2.5,
        f14_mean_bp=0.01,
        survivorship_fraction=0.8,
        bias_bp_per_year=12.0,
    )
    assert criteria["F1.1"]["verdict"] == "fail"
    assert criteria["F1.2"]["verdict"] == "fail"
    assert criteria["F1.3"]["verdict"] == "fail"
    assert criteria["F1.4"]["verdict"] == "fail"
    assert criteria["F1.5"]["verdict"] == "pass"


def test_criterion_text_verbatim() -> None:
    criteria = evaluate.evaluate_criteria(
        yf_coverage=1.0,
        current_coverage=1.0,
        ten_year_coverage=1.0,
        interior_nans=0,
        f13_corr=0.99,
        f14_max_bp=0.1,
        f14_mean_bp=0.01,
        survivorship_fraction=0.9,
        bias_bp_per_year=1.0,
    )
    assert criteria["F1.3"]["criterion"].startswith(
        "Equal-weight universe daily return vs the Kenneth French market return"
    )


def test_survivorship_bias_bp_per_year() -> None:
    naive = _series([0.001] * 5)
    pit = _series([0.0005] * 5)
    bias = evaluate.annualized_gap_bp(naive, pit)
    assert bias == pytest.approx(0.0005 * 252 * 10_000.0)


def test_write_results_json_valid(tmp_path: Path) -> None:
    criteria = evaluate.evaluate_criteria(
        yf_coverage=0.9,
        current_coverage=1.0,
        ten_year_coverage=0.95,
        interior_nans=0,
        f13_corr=0.96,
        f14_max_bp=0.5,
        f14_mean_bp=0.01,
        survivorship_fraction=0.8,
        bias_bp_per_year=12.0,
    )
    out = tmp_path / "RESULTS.json"
    evaluate.write_results(criteria, out)
    data = json.loads(out.read_text())
    assert set(data["criteria"]) == {"F1.1", "F1.2", "F1.3", "F1.4", "F1.5"}
    assert data["criteria"]["F1.3"]["stored_number"] == pytest.approx(0.96)


def test_ten_year_history_fraction() -> None:
    first_possible = pd.Series(
        [
            pd.Timestamp("2010-01-04"),
            pd.Timestamp("2020-01-02"),
            pd.Timestamp("2016-06-01"),
        ],
        index=["A", "B", "C"],
    )
    first_available = pd.Series(
        [
            pd.Timestamp("2010-01-04"),
            pd.Timestamp("2020-01-02"),
            pd.Timestamp("2016-10-01"),
        ],
        index=["A", "B", "C"],
    )
    frac = evaluate.ten_year_history_fraction(
        first_possible, first_available, cutoff="2016-09-02"
    )
    # B joined after the cutoff and is not eligible; of A and C only A has 10 years
    assert frac == pytest.approx(0.5)
