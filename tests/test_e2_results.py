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
        f23_garch_names_fitted=45,
        f23_paired_n=38,
        f23_paired_garch_win_share=0.47,
        f23_paired_ewma_win_share=0.29,
        f23_garch_beats_ewma_share=0.74,
        f24_bias_mean=1.05,
        f24_bias_by_year={"2025": 1.0, "2026": 1.1},
        f25_nw_gt_ols_share=0.9,
        f26_breaks=[],
        f26_break_rows=0,
        f26b_rows=373,
        f26b_matched=93,
        f26b_unverified=244,
        f26b_reused=4,
        f26b_reused_tickers=["CPWR", "EP", "MI", "POM"],
        f26b_kept_by_review=[],
        f26b_dropped=["CPWR", "EP", "MI", "POM"],
        f26b_truncated={},
        f26b_gaps=["CPWR"],
        f26b_leaks=[],
        f23b_win_shares={
            "1": {
                "garch": 0.4666666666666667,
                "ewma_094": 0.35403726708074534,
                "ewma_097": 0.5196687370600414,
            },
            "21": {
                "garch": 0.5555555555555556,
                "ewma_094": 0.19875776397515527,
                "ewma_097": 0.34368530020703936,
            },
        },
        f23b_garch_fitted=47,
        f23b_garch_failed=13,
        f23b_day_level={"pooled": 0.516, "by_year": {"2024": 0.513}},
        f26c={
            "review_rows": 36,
            "kept": ["ATI", "FOX", "FOXA", "PCG"],
            "stays_dropped": ["DD"],
            "n_current_dropped_by_c1": 4,
            "n_kept_current": 3,
            "n_current": 503,
            "n_covered": 502,
            "coverage": 502 / 503,
            "bar": 501 / 503,
            "missing": ["DD"],
        },
    )
    base.update(overrides)
    return base


def test_all_nine_criteria_present_with_valid_verdicts() -> None:
    criteria = evaluate.evaluate_e2_criteria(**_inputs())
    assert set(criteria) == {
        "F2.0a",
        "F2.0b",
        "F2.0c",
        "F2.1",
        "F2.2",
        "F2.3",
        "F2.3b",
        "F2.4",
        "F2.5",
        "F2.6",
        "F2.6b",
        "F2.6c",
    }
    for key, value in criteria.items():
        assert value["verdict"] in {"pass", "fail"}, key
        assert value["criterion"] and value["threshold"], key


def test_f23b_needs_both_methods_above_sixty_percent_at_both_horizons() -> None:
    # the fixture is the real result: GARCH reaches 55.6% at horizon 21 and
    # 46.7% at horizon 1, so the aligned evaluation still fails
    criteria = evaluate.evaluate_e2_criteria(**_inputs())
    assert criteria["F2.3b"]["verdict"] == "fail"
    stored = criteria["F2.3b"]["stored_numbers"]
    assert stored["win_shares"]["21"]["garch"] == pytest.approx(0.5556, abs=1e-3)
    assert stored["garch_fitted"] == 47
    assert stored["garch_failed"] == 13

    # a clean sweep at both horizons passes
    strong = evaluate.evaluate_e2_criteria(
        **_inputs(
            f23b_win_shares={
                "1": {"garch": 0.71, "ewma_094": 0.65},
                "21": {"garch": 0.75, "ewma_094": 0.68},
            }
        )
    )
    assert strong["F2.3b"]["verdict"] == "pass"

    # one method short at one horizon fails
    mixed = evaluate.evaluate_e2_criteria(
        **_inputs(
            f23b_win_shares={
                "1": {"garch": 0.71, "ewma_094": 0.65},
                "21": {"garch": 0.58, "ewma_094": 0.68},
            }
        )
    )
    assert mixed["F2.3b"]["verdict"] == "fail"

    # a single horizon is not enough to claim the aligned result
    one_horizon = evaluate.evaluate_e2_criteria(
        **_inputs(
            f23b_win_shares={"1": {"garch": 0.71, "ewma_094": 0.65}},
        )
    )
    assert one_horizon["F2.3b"]["verdict"] == "fail"


def test_f23b_note_states_the_garch_improvement() -> None:
    criteria = evaluate.evaluate_e2_criteria(**_inputs())
    note = criteria["F2.3b"]["note"]
    assert "55.6%" in note and "46.7%" in note
    assert "60%" in note


def test_f26b_passes_only_when_the_build_applied_the_exclusions() -> None:
    good = evaluate.evaluate_e2_criteria(**_inputs())
    assert good["F2.6b"]["verdict"] == "pass"
    assert good["F2.6b"]["stored_numbers"]["reused_tickers"] == [
        "CPWR",
        "EP",
        "MI",
        "POM",
    ]

    # a name the table flagged is still in the estimated panel
    leaked = evaluate.evaluate_e2_criteria(**_inputs(f26b_leaks=["MI"]))
    assert leaked["F2.6b"]["verdict"] == "fail"

    # the table was never produced
    missing = evaluate.evaluate_e2_criteria(**_inputs(f26b_rows=0, f26b_leaks=[]))
    assert missing["F2.6b"]["verdict"] == "fail"

    # the table exists but the build excluded nothing
    idle = evaluate.evaluate_e2_criteria(**_inputs(f26b_dropped=[]))
    assert idle["F2.6b"]["verdict"] == "fail"


def test_f26b_does_not_reword_f26() -> None:
    criteria = evaluate.evaluate_e2_criteria(**_inputs())
    assert criteria["F2.6"]["criterion"].startswith(
        "Successor to F2.3, added on 2026-09-10"
    )
    assert criteria["F2.6b"]["criterion"].startswith("Close-out C1")
    # F2.6 keeps its recorded fail even when its own list is empty here
    assert criteria["F2.6"]["verdict"] == "pass"
    assert "F2.6" in criteria and "F2.6b" in criteria


def test_f26_fails_when_a_symbol_was_reused() -> None:
    criteria = evaluate.evaluate_e2_criteria(
        **_inputs(f26_breaks=["CPWR", "MI"], f26_break_rows=7)
    )
    assert criteria["F2.6"]["verdict"] == "fail"
    assert criteria["F2.6"]["stored_numbers"]["break_tickers"] == ["CPWR", "MI"]
    assert "not pre-registered" in criteria["F2.6"]["criterion"]


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
            f23b_win_shares={
                "1": {"garch": 0.7, "ewma_094": 0.65},
                "21": {"garch": 0.72, "ewma_094": 0.66},
            },
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


def test_f23_reports_the_paired_sample_not_just_the_win_shares() -> None:
    # GARCH fits only part of the universe, so a bare win share beside the
    # EWMA one reads as "GARCH is worse" when the opposite holds on the names
    # where both are available.
    criteria = evaluate.evaluate_e2_criteria(**_inputs())
    stored = criteria["F2.3"]["stored_numbers"]
    assert stored["garch_names_fitted"] == 45
    assert stored["paired_n"] == 38
    assert stored["garch_beats_ewma_094_share"] == pytest.approx(0.74)
    note = criteria["F2.3"]["note"]
    assert "45" in note and "38" in note
    assert f"{0.74:.1%}" in note


def test_write_results_records_the_sprint(tmp_path: Path) -> None:
    criteria = evaluate.evaluate_e2_criteria(**_inputs())
    path = tmp_path / "RESULTS.json"
    evaluate.write_results(criteria, path, sprint="E2")
    payload = json.loads(path.read_text())
    assert payload["sprint"] == "E2"
    assert set(payload["criteria"]) == set(criteria)


def test_f26c_needs_the_bar_and_a_stored_review() -> None:
    good = evaluate.evaluate_e2_criteria(**_inputs())
    assert good["F2.6c"]["verdict"] == "pass"
    assert good["F2.6c"]["stored_numbers"]["n_covered"] == 502
    assert good["F2.6c"]["stored_numbers"]["kept"] == ["ATI", "FOX", "FOXA", "PCG"]

    # one name below the brief's 501 of 503 bar
    short = evaluate.evaluate_e2_criteria(
        **_inputs(f26c={**_inputs()["f26c"], "n_covered": 500, "coverage": 500 / 503})
    )
    assert short["F2.6c"]["verdict"] == "fail"

    # nothing reviewed means nothing was restored, whatever the coverage says
    unreviewed = evaluate.evaluate_e2_criteria(
        **_inputs(f26c={**_inputs()["f26c"], "review_rows": 0, "kept": []})
    )
    assert unreviewed["F2.6c"]["verdict"] == "fail"


def test_f26c_does_not_reword_f26b() -> None:
    criteria = evaluate.evaluate_e2_criteria(**_inputs())
    assert criteria["F2.6b"]["criterion"].startswith("Close-out C1")
    assert criteria["F2.6c"]["criterion"].startswith("Close-out C6")


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
        "F2.3b",
        "F2.4",
        "F2.5",
        "F2.6",
        "F2.6b",
        "F2.6c",
    }
