"""Sprint E4 Task 6: every criterion evaluated with a stored number.

The verdicts are asserted here as they were measured, including the two
failures. F4.1 fails against a threshold written for an object the sprint did
not build; F4.4 fails because PCA loses to a daily-refitted XS-v1 by 7.2
points. Both stay on the record, and the test that would notice them changing
is the point of the file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from efb import evaluate

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "sprints" / "E4" / "RESULTS.json"


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(RESULTS.read_text())


@pytest.mark.integration
def test_the_seven_criteria_are_stored_with_the_verdicts_measured(
    payload: dict,
) -> None:
    verdicts = {key: block["verdict"] for key, block in payload["criteria"].items()}
    assert verdicts == {
        "F4.1": "fail",
        "F4.2": "pass",
        "F4.3": "pass",
        "F4.4": "fail",
        "F4.5": "pass",
        "F4.6": "pass",
        "F4.7": "pass",
    }


@pytest.mark.integration
def test_every_criterion_carries_a_stored_number_and_an_unreworded_threshold(
    payload: dict,
) -> None:
    for key, block in payload["criteria"].items():
        assert block["criterion"] == evaluate.E4_CRITERIA_TEXT[key], key
        assert block["threshold"] == evaluate.E4_THRESHOLDS[key], key
        assert block["stored_numbers"], key
        assert block["note"], key


@pytest.mark.integration
def test_the_two_failures_store_the_numbers_that_failed(payload: dict) -> None:
    f41 = payload["criteria"]["F4.1"]["stored_numbers"]
    assert f41["pc1_vs_market_pca_v1"] == pytest.approx(0.797019, abs=5e-6)
    assert f41["pc1_vs_market_pca_v1c"] == pytest.approx(0.930599, abs=5e-6)
    assert f41["pc1_vs_equal_weight_pca_v1"] > 0.95, (
        "the correlation PCA's PC1 is an equal-weight object, which is why the "
        "market threshold was the wrong threshold"
    )
    f44 = payload["criteria"]["F4.4"]["stored_numbers"]
    assert f44["pca_rolling_refit"] < f44["xs_v1_daily_refit"]
    assert f44["xs_v1_plus_top3_residual_pcs"] > f44["xs_v1_descriptors_frozen"]


@pytest.mark.integration
def test_f4_2_is_the_stop_condition_and_it_is_inside_the_band(payload: dict) -> None:
    numbers = payload["criteria"]["F4.2"]["stored_numbers"]
    assert 3 <= numbers["n_factors_mp"] <= 15
    assert numbers["n_factors_mp"] == 13
    assert numbers["panel_n_factors_above_edge"] == 14


@pytest.mark.integration
def test_f4_3_is_scored_on_medians_and_the_sample_never_wins(payload: dict) -> None:
    numbers = payload["criteria"]["F4.3"]["stored_numbers"]
    assert numbers["windows_won"]["sample"] == 0
    assert numbers["windows_won"]["ewma"] == 0
    assert numbers["worst_ratio"] < 0.9
    medians = numbers["median_realized_vol"]
    for name in (
        "clip",
        "constant_correlation",
        "ledoit_wolf",
        "ts_v1",
        "pca_v1",
        "pca_v1c",
    ):
        assert medians[name] < medians["sample"], name
    # EWMA is the one estimator worse than the sample covariance, which is why
    # F4.3 names shrinkage and factor estimators rather than every alternative
    assert medians["ewma"] > medians["sample"]
    # E5 rebuilt the race and could not reproduce the XS-v1 row: F5.0b.
    assert numbers["estimators_missing"] == ["xs_v1"]


@pytest.mark.integration
def test_f4_6_stores_the_survivor_numbers_as_measured(payload: dict) -> None:
    numbers = payload["criteria"]["F4.6"]["stored_numbers"]
    assert numbers["style_correlation_panel_vs_mapped"]["size"] < 0.9
    assert numbers["style_correlation_panel_vs_mapped"]["market"] > 0.99
    assert numbers["size_premium"]["mapped"] < numbers["size_premium"]["panel"] < 0
    assert (
        numbers["mean_r_squared"]["mapped_502"] > numbers["mean_r_squared"]["panel_825"]
    )
    assert numbers["excluded_names"]["annualized_vol"] > (
        numbers["excluded_names"]["included_annualized_vol"]
    )


@pytest.mark.integration
def test_f4_7_keeps_the_covariance_count_out_of_f4_2s_band(payload: dict) -> None:
    numbers = payload["criteria"]["F4.7"]["stored_numbers"]
    assert numbers["pca_v1c_n_factors_above_edge"] == 16
    assert numbers["scored_against_f4_2"] is False
    assert (
        numbers["pca_v1c_pc1_vs_equal_weight"] < numbers["pca_v1_pc1_vs_equal_weight"]
    )


def test_the_data_hash_covers_the_artifacts_read() -> None:
    digest = evaluate.e4_data_hash()
    assert len(digest) == 64
    again = evaluate.e4_data_hash()
    assert digest == again
    # every artifact the criteria read exists, so the hash is not hashing air
    for path in evaluate.e4_artifacts():
        assert path.exists(), path


@pytest.mark.integration
def test_no_earlier_verdict_moved() -> None:
    """The stop condition that outranks every number in the sprint."""
    check = evaluate.prior_verdict_changes()
    assert check, "the earlier sprints were not re-evaluated at all"
    for sprint, block in check.items():
        assert block.get("n_changed") == 0, (sprint, block)
