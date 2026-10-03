"""Sprint E4 Task 6: every criterion evaluated with a stored number.

The verdicts are asserted here as they were measured, including the two
failures. F4.1 fails against a threshold written for an object the sprint did
not build; F4.4 fails because PCA loses to a daily-refitted XS-v1 by 7.2
points. Both stay on the record, and the test that would notice them changing
is the point of the file.
"""

from __future__ import annotations

import json
import math
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
    """The verdicts are re-derived from the artifacts, not read back.

    Asserting the stored strings against hardcoded strings would pass with every
    stored number replaced by garbage - measured: it does - because a verdict is
    not a number. This recomputes the verdicts from the artifacts the numbers were
    measured on and requires the stored file to agree.
    """
    derived = evaluate.evaluate_e4_criteria(
        **evaluate.compute_e4_from_artifacts(data_root=ROOT / "data")
    )
    assert {key: block["verdict"] for key, block in payload["criteria"].items()} == {
        key: block["verdict"] for key, block in derived.items()
    }
    assert payload["criteria"]["F4.1"]["verdict"] == "fail"
    assert payload["criteria"]["F4.4"]["verdict"] == "fail"


@pytest.mark.integration
def test_a_missing_estimator_fails_f4_3(payload: dict) -> None:
    """A race that drops a requested row cannot pass on the shorter list."""
    numbers = payload["criteria"]["F4.3"]["stored_numbers"]
    if "estimators_required" not in numbers:
        pytest.skip(
            "this record predates the F4.3 revision; rebuild E4 to store the "
            "required list beside the missing one"
        )
    missing = numbers["estimators_missing"]
    required = numbers["estimators_required"]
    assert set(missing).issubset(set(required))
    assert payload["criteria"]["F4.3"]["verdict"] == (
        "fail" if missing else "pass"
    ), "the verdict has to follow the missing list"


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
def test_the_failing_criteria_store_the_numbers_that_failed(payload: dict) -> None:
    """A failing verdict stores the number it failed on, and the set is pinned.

    The set is asserted rather than the values: the panel these were measured on
    moves (the 2026-10-03 rebuild moved F4.1's correlations in the fourth
    decimal), so pinning a value here would fail on a correct rebuild, while a
    verdict that flips without a deliberate edit must fail. H2 made F4.3 the
    third failure on purpose.
    """
    failing = {
        key for key, block in payload["criteria"].items() if block["verdict"] == "fail"
    }
    assert failing == {"F4.1", "F4.4"}, failing

    f41 = payload["criteria"]["F4.1"]["stored_numbers"]
    assert (
        max(f41["pc1_vs_market_pca_v1"], f41["pc1_vs_market_pca_v1c"]) < 0.95
    ), "F4.1 fails on both PC1 objects, and both are stored"
    assert f41["pc1_vs_equal_weight_pca_v1"] > 0.95, (
        "the correlation PCA's PC1 is an equal-weight object, which is why the "
        "market threshold was the wrong threshold"
    )
    f44 = payload["criteria"]["F4.4"]["stored_numbers"]
    # the comparison the criterion names, both sides finite
    assert f44["pca_rolling_refit"] < f44["xs_v1_daily_refit"]
    assert f44["held_out_days"] > 0
    for name in ("pca_frozen_k_mp", "pca_frozen_k_17", "xs_v1_daily_refit"):
        assert math.isfinite(f44[name]), name
    # Three held-out variants read NaN after the panel was extended to 2026-10-02
    # (they need the frozen XS-v1 descriptors over the held-out window). That is a
    # defect of the E4 held-out harness, not of this branch, so it is pinned by
    # name here and recorded in docs/open_items.md: a NEW NaN, or the set clearing,
    # has to fail this test rather than pass unnoticed.
    known_nan = {
        "xs_v1_descriptors_frozen",
        "xs_v1_plus_top3_residual_pcs",
        "xs_v1_plus_top5_residual_pcs",
    }
    nan = {
        name
        for name, value in f44.items()
        if isinstance(value, float) and math.isnan(value)
    }
    assert nan == known_nan, f"the NaN set moved: {nan} (see docs/open_items.md)"


@pytest.mark.integration
def test_f4_3_scores_every_required_estimator(payload: dict) -> None:
    """F4.3's verdict comes from scoring the full list, not from a short one.

    The XS-v1 row exists now: `efb.race.xs_supplier` reads the model's own design,
    factor covariance and specific diagonal, and the E4 build owns the race
    artifact its criterion reads. A missing estimator still fails
    (`test_a_missing_estimator_fails_f4_3` covers that), so the error this test
    rules out is the opposite one - a pass produced by scoring fewer estimators.
    """
    block = payload["criteria"]["F4.3"]
    numbers = block["stored_numbers"]
    required = numbers["estimators_required"]
    assert numbers["estimators_missing"] == [], numbers["estimators_missing"]
    assert set(numbers["ratio_to_sample"]) == set(required)
    for name, ratio in numbers["ratio_to_sample"].items():
        assert math.isfinite(ratio), name
    assert numbers["worst_ratio"] == pytest.approx(
        max(numbers["ratio_to_sample"].values())
    )
    # the estimator that was absent is scored, and its ratio is stored
    assert math.isfinite(numbers["ratio_to_sample"]["xs_v1"])
    assert (
        numbers["median_realized_vol"]["xs_v1"]
        < numbers["median_realized_vol"]["sample"]
    )
    assert block["verdict"] == (
        "pass" if max(numbers["ratio_to_sample"].values()) <= 0.9 else "fail"
    )


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
    # E5 rebuilt the race and could not reproduce the XS-v1 row: F5.0b. The row is
    # owed back and a missing estimator fails the criterion; this asserts the
    # requirement rather than pinning the defect in place, which is what the
    # earlier version of this test did - it failed the moment the row came back.
    required = numbers.get("estimators_required")
    if required is None:
        pytest.skip("this record predates the F4.3 revision; rebuild E4")
    assert "xs_v1" in required
    assert set(numbers["estimators_missing"]).issubset(set(required))
    if numbers["estimators_missing"]:
        assert payload["criteria"]["F4.3"]["verdict"] == "fail"
    else:
        assert "xs_v1" in medians


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


# The stored verdicts are re-derived here, which is 86.8 s on the development
# machine with the plugin disabled (2026-09-26) and over the global 120 s inside a
# full suite, where the earlier tests have already spent the machine's memory. The
# bound is per test and stays well under a real hang.
@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.timeout(300)
def test_no_earlier_verdict_moved() -> None:
    """The stop condition that outranks every number in the sprint."""
    check = evaluate.prior_verdict_changes()
    assert check, "the earlier sprints were not re-evaluated at all"
    for sprint, block in check.items():
        assert block.get("n_changed") == 0, (sprint, block)
