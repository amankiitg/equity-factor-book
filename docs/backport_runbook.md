# Backport runbook — branch `backport`

Research-only branch. It changes the research panel, the criteria and the tests;
it changes one thing on the live path (`efb/race.py`) and must not merge until
**2026-11-11**, when it lands together with a regenerated live seed. Until then
`make test` is the gate, and the two merge-time checks below are the ones no
default run can perform.

## 1. What this branch changes that the live cron executes

`scripts/run_cron.py` routes to `scripts/reconcile_fills.py` (`:113`, `:122`) and
`scripts.run_live_daily` (`:124`). Everything the live chain reaches from there,
that this branch touches:

| file | what changed | reached from | effect on a live run |
|---|---|---|---|
| `efb/race.py::next_descriptor_design` | builds the next-session design on `panel["returns_clean"]` instead of `panel["returns"]` (`efb/race.py:279`) | `efb/eval_risk.py:411` ← `live/evening_job.py:1205` | **the only real live behavioural change.** On a live tree the two frames are equal, so it is inert until the seed is regenerated; on the regenerated seed it changes the cross-section the hedge is solved against |
| `efb/hygiene.py::clean_returns` | `corrected` exception: a cell the corporate-action rule repaired is no longer masked by its own flag | `efb/eval_risk.py:156` (`load_clean_wide`) ← `live/evening_job.py:1191`; also `efb/race.py:60,338`, `efb/models/statistical.py:106` | inert while the live frame has no `corrected` column, which it does not until the seed is regenerated |
| `efb/probes.py::load_panel` | returns a new key, `returns_clean` | `live/extend.py:378` (still reads `inputs["returns"]` — see §3) | additive; no reader changes until the merge commit |
| `efb/build.py::build_e3_artifacts` | builds E3 from `inputs["returns_clean"]`, applies the recorded spin-offs | not on the cron path | changes the **seed**, i.e. the 2026-11-11 regeneration |
| `efb/evaluate.py`, `efb/models/fundamental.py` | criteria, docstring | not imported by `live/` | none |
| `efb/corporate_actions.py`, `scripts/collect_corporate_actions.py` | new | not imported by `live/` | none |

The XS-v1 fit itself (`efb/models/statistical.py`, `efb/cov.py`) is unchanged:
the fit consumes whatever panel it is handed, so the panel its caller passes is
the whole of the question.

## 2. Tests that need more than the repository tree

Both are **deselected, never skipped**: a default run reports them as
`N deselected`, and skipping them quietly is how the September hedge-vintage
pairs stopped existing without any test noticing.

| file | marker | what it needs | default run |
|---|---|---|---|
| `tests/test_hedge_vintage.py` | `requires_live_tree` | a run root the live loop has extended one session at a time, so that a descriptor row exists for the session after a month end | deselected |
| `tests/test_live_panel_parity.py::test_the_live_fit_and_the_next_design_read_one_panel` | `merge_guard` | the merge commit, not a tree (§3) | deselected |

    make test                                   # green today, 2 groups deselected
    make test-all                               # everything else, slow included
    EFB_RUN_ROOT=<run root> make test-live-tree # the vintage tests
    .venv/bin/python -m pytest tests/test_live_panel_parity.py -m merge_guard

`EFB_RUN_ROOT` is the same variable `live/runroot.py` materialises a run into
(`RUN_ROOT_ENV`, `live/runroot.py:31`). A tree rebuilt by `make rebuild-e3` is
**not** live-shaped: the build publishes descriptors at month ends plus the final
session, so it has no row for the session after a month end and cannot exercise
the vintage property at all.

## 3. Merge checklist — 2026-11-11

1. **Read one panel.** At merge, `live/extend.py` must read `returns_clean` as
   well, in the same commit, so the live model fit and `next_descriptor_design`
   use the same panel. The change is `live/extend.py:379`,
   `returns_frame = inputs["returns"]` → `inputs["returns_clean"]`.
   Run the guard before and after; it fails on the branch as pushed:
   `.venv/bin/python -m pytest tests/test_live_panel_parity.py -m merge_guard`
2. **Re-declare the champion after any E3 rebuild.** `efb.build.rebuild_e3`
   registers XS-v1 with `champion=False`, and only the E5 step
   (`efb.eval_risk.apply_champion`, `efb/build.py:1981`) sets the flag, so
   `make rebuild-e3` on the real tree leaves the registry with no champion.
   Measured on 2026-10-03: rebuilding E3 on `data/` cleared it, three tests
   failed (`test_champion`, `test_build_e3::test_registry_entry_is_eligible_but_not_champion`,
   `test_dashboard_d3`), and
   `python -c "from efb import eval_risk; eval_risk.apply_champion()"` restored
   XS-v1 as the winner (mean |bias-1| 0.060664 against XS-v2 at 0.067194, the
   same winner as before the rebuild). Run that after the seed regeneration.
3. **Regenerate the live seed** from this branch's research artifacts, so the
   published descriptors and the repaired returns come from the same panel.
4. **Run the hedge-vintage tests on the regenerated seed**, materialised as a run
   root: `EFB_RUN_ROOT=<run root> make test-live-tree`, or directly
   `EFB_RUN_ROOT=<run root> python -m pytest tests/test_hedge_vintage.py`. Two of
   the eight assert that the row built at the close *is* the published row; on the
   regenerated seed they pass, and on a tree whose published rows were built from
   the raw panel they fail by construction.
5. **Regenerate the web fixtures** after the seed lands
   (`scripts/make_web_fixtures.py`) and re-run `make test-all` once, on the
   merged commit, with the seed in place.
6. **Re-score E6 with the month-end finding folded in** (item 3 of the back-port):
   see the entry in `docs/hygiene_ledger.md` dated 2026-10-03.
7. **Regenerate with the end date stated.** Every rebuild is pinned (§4). At the
   merge, state the session the seed means to reach —
   `make rebuild END=<last session before the merge>` — rather than taking the
   default, which deliberately reproduces the stored panel.

## 4. The panel pin — every rebuild takes an end date

`make rebuild-e1` … `make rebuild-e10` all take `END=YYYY-MM-DD`, and the entry
point behind them takes `--end`. Left unset the pin is the **stored panel's own last
session** (`efb.build.pinned_panel_end`, read from the date index of
`data/processed/returns.parquet`), not the clock, so a rebuild that re-reads sources
cannot extend the panel by accident. A first build, with no panel on disk, still
falls back to today, because there is nothing to freeze yet.

**`END=2026-10-02` is the date every rebuild in this pass used**: the stored panel's
last session (4,213 sessions from 2010-01-04, `data/processed/returns.parquet`),
which is the panel every re-scored record here was measured on. State that date when
re-running any of these rebuilds.

Two rules come with it:

- a leg that **reads** the panel (E2 … E10) refuses a pin earlier than the panel's
owned end, because it cannot un-read rows it has already been handed;
- `rebuild-e1` is the exception: it *makes* the panel, so an earlier pin re-cuts it,
  and an `END` past the stored end is how a run says it means to extend the panel.

The price and factor artifacts are clipped at the pin
(`efb.prices.build_prices_artifact`, `efb.factors.build_factors_artifact`) and the
membership grid is built to it (`efb.universe.build_membership`). Those are the two
ways the panel used to grow on an ordinary `make rebuild`: a price cache refreshed by
a live run, and a membership grid that ran to today. `tests/test_panel_freeze.py`
holds both directions, together with the control that the newer source rows really
are in the fixture.

## 4. What could not be verified on this branch

- The parity guard fails on the branch as pushed and passes only after item 1 of
  §3. Its red is the branch's statement that the two readers disagree; it is not
  evidence that the merge has happened.
- The hedge-vintage tests were last run green on `/tmp/efb-repair/data`, a live
  tree as of 2026-10-02 (209 descriptor dates). Six of eight pass there; the two
  that compare the built row against the published row fail, for the reason in
  §2 — the published rows in that tree were built from the raw panel.
- Nothing in §1 was executed against a live tree by this branch; the effects in
  the last column are read off the call sites.
