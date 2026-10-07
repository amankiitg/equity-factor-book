# The known test failures, and what a report has to do with them

Measured on `main` at `0e69f69` on 2026-10-06, with the suite the merge gate
runs (every marker except `slow`, `requires_live_tree` and `merge_guard`):

```
.venv/bin/python -m pytest tests/ -q -m "not slow and not requires_live_tree and not merge_guard"
```

**55 failed, 1272 passed, 1 skipped, 35 deselected.** Every failing id is below,
grouped by cause, each group with the one line that explains it and the November
11 step that clears it (the step numbers are section 3 of
`docs/backport_runbook.md`, which points here rather than keeping its own copy).

Every report of a full-suite run compares that run against this file and splits
its failures three ways: **known** (an id listed here), **new** (an id that is
not), and **newly passing** (an id listed here that came back green). A new
failure is investigated on its own and is never folded into this list to make a
merge look clean. **Zero new is the bar.** The 2026-11-11 refresh is what turns
this list into nothing: its exit condition is 0 failures, with anything still red
fixed or written down here with its reason, never skipped and never `xfail`.

## 1. Live-page fixtures and figures: the September vintage (10)

**Cause.** The committed web fixtures are the 2026-09-21 vintage and the writers have moved since, so the regenerated documents carry a newer `book_as_of`, `breadth`, `hedge`, `exposures_*` and `expected_cost_*`; the notify test types the four sessions of an appendix the tree has long outgrown, and the fixture tests pin `CLOSE` (`2026-09-21`).

**Cleared by.** Step 5 (`scripts/make_web_fixtures.py` on the refreshed seed, committed with what it produces), re-pinning `CLOSE`/`NEXT_CLOSE`/`CATCH_UP_CLOSE`/`STOPPED_CLOSE`/`REMOVED_CLOSE` and the session window from the refreshed artifacts rather than typing them. Step 9 is the check.

- `tests/test_e11_web_fixtures.py::test_every_fixture_is_what_the_writer_produces_now[snapshot_catch_up.json]`
- `tests/test_e11_web_fixtures.py::test_every_fixture_is_what_the_writer_produces_now[snapshot_error.json]`
- `tests/test_e11_web_fixtures.py::test_every_fixture_is_what_the_writer_produces_now[snapshot_establishment.json]`
- `tests/test_e11_web_fixtures.py::test_every_fixture_is_what_the_writer_produces_now[snapshot_expired.json]`
- `tests/test_e11_web_fixtures.py::test_every_fixture_is_what_the_writer_produces_now[snapshot_market_closed.json]`
- `tests/test_e11_web_fixtures.py::test_every_fixture_is_what_the_writer_produces_now[snapshot_ok.json]`
- `tests/test_e11_web_fixtures.py::test_every_fixture_is_what_the_writer_produces_now[snapshot_stale_stopped.json]`
- `tests/test_e11_web_fixtures.py::test_the_ok_snapshot_carries_the_book_and_both_exposure_vectors`
- `tests/test_e11_web_fixtures.py::test_the_stopped_snapshot_shows_the_last_book_under_its_own_close`
- `tests/test_e11_notify.py::test_the_appended_sessions_are_measured_from_the_calendar`

## 2. Sprint registries: the stored hashes and criteria no longer reproduce (17)

**Cause.** Each `sprints/E<N>/RESULTS.json` recorded its data hash and its criterion numbers on an artifact vintage that has since been rebuilt, so `evaluate.e<N>_data_hash()` and `compute_e<N>_from_artifacts()` no longer equal what is stored (`F7.1`, `F8.1`, `F9.1` are the first mismatches), and the notebooks' hash cells assert the same stored hashes.

**Cleared by.** The refresh (steps 3 and 4), then re-record each `sprints/E<N>/RESULTS.json` and the notebooks' hash cells from the refreshed artifacts. Step 6 is the check that cannot pass until it is done.

- `tests/test_e10_results.py::test_the_stored_criteria_equal_the_recomputed_ones`
- `tests/test_e10_results.py::test_the_stored_hash_reproduces_from_the_artifacts`
- `tests/test_e10_walkthrough_notebook.py::test_the_hash_cell_asserts_the_sprint_hash_against_the_artifacts`
- `tests/test_e4_walkthrough_notebook.py::test_cell_1_asserts_the_sprint_hash_against_the_registry`
- `tests/test_e5_walkthrough_notebook.py::test_the_hash_cell_asserts_the_sprint_hash_against_the_artifacts`
- `tests/test_e6_results.py::test_the_stored_criteria_equal_the_recomputed_ones`
- `tests/test_e6_results.py::test_the_stored_hash_reproduces_from_the_artifacts`
- `tests/test_e6_walkthrough_notebook.py::test_the_hash_cell_asserts_the_sprint_hash_against_the_artifacts`
- `tests/test_e7_results.py::test_the_stored_criteria_equal_the_recomputed_ones`
- `tests/test_e7_results.py::test_the_stored_hash_reproduces_from_the_artifacts`
- `tests/test_e7_walkthrough_notebook.py::test_the_hash_cell_asserts_the_sprint_hash_against_the_artifacts`
- `tests/test_e8_results.py::test_the_stored_criteria_equal_the_recomputed_ones`
- `tests/test_e8_results.py::test_the_stored_hash_reproduces_from_the_artifacts`
- `tests/test_e8_walkthrough_notebook.py::test_the_hash_cell_asserts_the_sprint_hash_against_the_artifacts`
- `tests/test_e9_results.py::test_the_stored_criteria_equal_the_recomputed_ones`
- `tests/test_e9_results.py::test_the_stored_hash_reproduces_from_the_artifacts`
- `tests/test_e9_walkthrough_notebook.py::test_the_hash_cell_asserts_the_sprint_hash_against_the_artifacts`

## 3. Sprint memos and the README: the numbers they quote have moved (9)

**Cause.** A memo's numbers are the stored artifacts' numbers, stated in prose and checked for traceability; the artifacts moved, so numbers like `1.1304`, `-0.0045`, `1.8401` and the `xs_v1` family means are no longer in any artifact the test can find, and `README.md` quotes the same drift.

**Cleared by.** The refresh, then re-state each memo's and the README's numbers from the refreshed artifacts (`sprints/E<N>/memo.md` is hand-written, so this is an edit, not a regeneration). Step 6 is the check.

- `tests/test_e10_memo.py::test_the_memo_exists_and_is_traceable`
- `tests/test_e5_memo.py::test_every_headline_number_is_in_the_memo_and_traceable`
- `tests/test_e5_memo.py::test_the_champion_scores_are_the_stored_family_means`
- `tests/test_e5_memo.py::test_the_heatmap_cells_are_the_stored_family_bias`
- `tests/test_e6_memo.py::test_every_headline_number_is_in_the_study_and_traceable`
- `tests/test_e7_memo.py::test_every_number_in_the_reports_is_traceable`
- `tests/test_e9_memo.py::test_the_memo_exists_and_is_traceable`
- `tests/test_readme_traceability.py::test_live_book_numbers_match_the_alpha_summary`
- `tests/test_readme_traceability.py::test_stress_haircut_matches_the_artifact`

## 4. Research artifacts against their own recomputation (7)

**Cause.** The stored study artifacts were recorded on an older vintage and the recomputation from `data/` has moved past them: `data/raw/*.parquet` has moved since the evidence snapshot, `21.8828` where `22.3031` is stored, `0.8263` where `0.57778` is, 309 names where 323 was measured, and the E1 reference `n_obs` differs.

**Cleared by.** The refresh, then `make evidence` to re-snapshot the artifacts and the sprint's own evaluate step to re-record the stored numbers. Step 6 is the check. `make verify-evidence` is the same check by hand.

- `tests/test_cov.py::test_the_stored_horse_race_puts_the_sample_covariance_last`
- `tests/test_e3_probes.py::test_e1_reference_values_recompute_from_the_artifacts`
- `tests/test_evidence.py::test_the_evidence_chain_verifies`
- `tests/test_statistical.py::test_residual_pca_reports_a_factor_above_its_own_edge`
- `tests/test_survivor_measurement.py::test_style_correlations_are_stored_and_size_is_the_low_one`
- `tests/test_survivor_measurement.py::test_the_excluded_names_were_riskier_and_earned_less`
- `tests/test_survivor_measurement.py::test_the_size_premium_deepens_between_universes`

## 5. Repository documents against the repository (4)

**Cause.** `docs/credit_port_design.md`'s port map and its stored module count (113) predate everything added since, and the measured count is 103 of them missing; the committed `web` sector map predates the artifacts it is built from (it records `2026-09-11` where `data/processed/sectors.parquet` and the latest SPY holdings now say `2026-10-03`).

**Cleared by.** The refresh, then `scripts/make_sector_map.py` re-run and committed, and the port map extended with every module it names plus the stored count re-recorded. Step 6 is the check.

- `tests/test_e13_design_note.py::test_every_module_in_the_repository_appears_in_the_map`
- `tests/test_e13_design_note.py::test_the_stored_module_count_is_the_count_this_test_measures`
- `tests/test_web_sector_map.py::test_the_committed_map_is_exactly_what_the_generator_produces`
- `tests/test_web_sector_map.py::test_the_map_names_the_files_it_came_from_and_their_own_dates`

## 6. Momentum probes and the hedge vintage (7)

**Cause.** The probes' tercile counts (`[47, 47, 48]` against `[47, 47, 47]`), their exposure means and the E4 momentum bound are measured on the tree's current priced set, and the hedge-vintage rows are the ones section 6 of the runbook describes: the row dated the close leaves `0.000e+00` where the model's row leaves the exposure the hedge is meant to remove, and the holiday pair no longer exercises a moved priced set.

**Cleared by.** Step 4 (`EFB_RUN_ROOT=<run root> make test-live-tree` on the regenerated seed) with step 8's re-recorded frozen-block baseline; the probes follow from the refreshed artifacts. Step 6 is the check.

- `tests/test_e4_probes.py::test_momentum_terciles_reproduce_the_stored_exposure_means`
- `tests/test_e4_probes.py::test_the_momentum_factor_is_not_quieter_in_the_high_exposure_months`
- `tests/test_hedge_vintage.py::test_a_published_next_session_row_is_used_as_it_stands`
- `tests/test_hedge_vintage.py::test_the_hedge_is_handed_the_next_sessions_row`
- `tests/test_hedge_vintage.py::test_the_row_built_at_the_close_is_the_row_the_model_publishes`
- `tests/test_hedge_vintage.py::test_the_row_dated_the_close_fails_that_bound`
- `tests/test_hedge_vintage.py::test_the_session_before_a_holiday_is_bounded_and_not_exact`

## 7. The APH split (1)

**Cause.** The split reproduction reads the real `data/raw` rows and the price it recovers (`82.78`) is no longer within the bound the stored row expects (`82.07`), so the split the test reproduces is not the one the real rows now carry.

**Cleared by.** The refresh, then re-recording the split from the refreshed real rows. Step 6 is the check.

- `tests/test_e11_corporate_actions.py::test_the_aph_split_is_reproduced_from_the_real_rows`

## The eleventh id: red in the targeted run, green in the full suite (1)

The live-loop files run on their own (the command in step 9) report **11**
failures, and the full suite reports the ten above. The difference is
`tests/test_e11_snapshot.py::test_the_hedge_drives_the_exposures_to_zero`
(`n_eff_kept` 140.887 against the pinned 131.9175, line 648): it fails on its own
and in that targeted run and passes inside the full suite, so something earlier
in the suite leaves the state it reads. It is a known red either way: a report of
either run names it, and neither counts it as new.

## Red only under load or in some orders, and not in the baseline (2)

These are not in the 55 and are not new failures either. Both were seen while
this file was being written and pass in the baseline run:

- `tests/test_e4_probes.py::test_feasibility_states_n_and_t_for_both_universes` -
  fails as `427 == 428` when it runs in a subset and passes in the full suite, so
  it reads a session count that another test's state moves.
- `tests/test_repair_session.py::test_a_second_refit_changes_nothing` - the
  refits are heavy and the file's fixtures carry a 120s `pytest-timeout`; under a
  loaded machine the run times out (the file alone gives 6 passed and 2 timeout
  errors). It passed in both baseline runs.

A report that sees one of these says which of the three buckets it is in, and does
not call it new.

## The count moves when modules are added

`tests/test_e13_design_note.py` enumerates the repository, so the port-map group
above grows every time a module lands: this branch adds `live/preflight.py` to the
list of modules the note does not yet name, and the bridge branch adds
`live/bridge.py`. The stored count is re-recorded with the map at the refresh
(step 6's pass), not before it.
