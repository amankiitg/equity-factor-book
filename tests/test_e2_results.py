"""Tests for Task 8: E2 criteria evaluation."""

import json
from pathlib import Path

import pytest

from efb import evaluate


def _inputs(**overrides):
    base = dict(
        model_start=2010,
        coverage_years_stored=17,
        interior_nan_rows=302,
        nan_rows_dropped_not_imputed=True,
        audit_mean_bp=0.018,
        large_audit_days=2,
        large_audit_days_with_event=2,
        f21_corr=0.95,
        f22_mean_pairwise=0.03,
        f22_n_names=150,
        f23_garch_win_share=0.47,
        f23_ewma094_win_share=0.36,
        f24_bias_mean=1.05,
        f24_bias_by_year={"2025": 1.0, "2026": 1.1},
        f25_nw_gt_ols_share=0.9,
    )
    base.update(overrides)
    return base


def test_all_eight_criteria_present_with_valid_verdicts() -> None:
    criteria = evaluate.evaluate_e2_criteria(**_inputs())
    assert set(criteria) == {
        "F2.0a",
        "F2.0b",
        "F2.0c",
        "F2.1",
        "F2.2",
        "F2.3",
        "F2.4",
        "F2.5",
    }
    for key, value in criteria.items():
        assert value["verdict"] in {"pass", "fail"}, key
        assert value["criterion"] and value["threshold"], key


def test_thresholds_decide_the_verdicts() -> None:
    criteria = evaluate.evaluate_e2_criteria(
        **_inputs(
            f23_garch_win_share=0.47,
            f23_ewma094_win_share=0.36,
            f25_nw_gt_ols_share=0.55,
            f22_mean_pairwise=0.07,
            audit_mean_bp=0.018,
            large_audit_days=2,
            large_audit_days_with_event=1,
        )
    )
    assert criteria["F2.3"]["verdict"] == "fail"
    assert criteria["F2.5"]["verdict"] == "fail"
    assert criteria["F2.2"]["verdict"] == "fail"
    assert criteria["F2.0c"]["verdict"] == "fail"  # one large day lacks an event


def test_passing_configuration() -> None:
    criteria = evaluate.evaluate_e2_criteria(
        **_inputs(
            f23_garch_win_share=0.7,
            f23_ewma094_win_share=0.65,
            f25_nw_gt_ols_share=0.95,
        )
    )
    assert all(value["verdict"] == "pass" for value in criteria.values())


def test_criteria_are_verbatim() -> None:
    criteria = evaluate.evaluate_e2_criteria(**_inputs())
    assert criteria["F2.4"]["criterion"].startswith(
        "For the equal-weight seed portfolio, bias statistic"
    )
    assert criteria["F2.3"]["criterion"].startswith(
        "GARCH(1,1) and EWMA(0.94) each beat trailing 252d vol"
    )


def test_write_results_records_the_sprint(tmp_path: Path) -> None:
    criteria = evaluate.evaluate_e2_criteria(**_inputs())
    path = tmp_path / "RESULTS.json"
    evaluate.write_results(criteria, path, sprint="E2")
    payload = json.loads(path.read_text())
    assert payload["sprint"] == "E2"
    assert set(payload["criteria"]) == set(criteria)


def test_real_results_file_has_every_criterion_if_present() -> None:
    path = Path(__file__).resolve().parents[1] / "sprints" / "E2" / "RESULTS.json"
    if not path.exists():
        pytest.skip("E2 RESULTS.json not built yet")
    payload = json.loads(path.read_text())
    assert set(payload["criteria"]) == {
        "F2.0a",
        "F2.0b",
        "F2.0c",
        "F2.1",
        "F2.2",
        "F2.3",
        "F2.4",
        "F2.5",
    }
