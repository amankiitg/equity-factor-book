# Sprint E11 live data and clock restart: report

Task `e11-live-data-and-clock-restart`, base commit 14d25bf. The loop is
now live: every model input extends one session per trading day, and the
thirty-day clock restarts from a clean day 1 after the static run was
voided.

**The clock restarted. Day 1 is 2026-09-22; the end date is 2026-11-02.**
The static start (which ran on the frozen 2026-09-03 close) is kept in
history as void, not deleted. Eleven sessions, 2026-09-04 through
2026-09-21, are appended, and rows dated on or before 2026-09-03 are
byte-identical. Every number below is read from an artifact.

## Table 1: the clock, voided and restarted

| quantity | value | file / key |
| --- | --- | --- |
| void day 1 | 2026-09-22 | live/clock.json `history[0].day_1` |
| void reason | static days: the loop ran on the frozen 2026-09-03 close and would produce thirty identical proposals | live/clock.json `history[0].reason` |
| void status | void | live/clock.json `history[0].status` |
| voided at | 2026-09-22T18:42:18.105380+00:00 | live/clock.json `history[0].voided_at` |
| new day 1 | 2026-09-22 | live/clock.json `day_1` |
| end date | 2026-11-02 | live/clock.json `end_date` |
| trading days | 30 | live/clock.json `trading_days` |
| started | true | live/clock.json `started` |

The void entry records a restart rather than a silent edit. The history
is append-only, and the reason states exactly which input was not
advancing.

## Table 2: the day-1 sanity gate

The gate ran the loop on two consecutive real closes. The proposals
differ, so the clock started.

| quantity | value | file / key |
| --- | --- | --- |
| close 1 | 2026-09-18 | live/sanity_gate.json `closes[0]` |
| close 2 | 2026-09-21 | live/sanity_gate.json `closes[1]` |
| proposals differ | true | live/sanity_gate.json `proposals_differ` |
| passed | true | live/sanity_gate.json `passed` |
| weight turnover | 0.12957758249149315 | live/sanity_gate.json `weight_turnover` |
| turnover definition | 0.5 * sum(abs(w_t - w_{t-1})) | live/sanity_gate.json `definition` |
| names before | 500 | live/sanity_gate.json `n_names_before` |
| names after | 500 | live/sanity_gate.json `n_names_after` |

Turnover 0.1296 is above zero, so the proposals on two different closes
are not identical and the data is live.

## Table 3: staleness is read off the proposal, never inferred

Every proposal stores the as-of date of every model input beside a single
max staleness.

| input | as-of | file / key |
| --- | --- | --- |
| prices | 2026-09-21 | live/proposals/proposal_2026-09-21.json `input_as_of.prices` |
| shares | 2026-09-22 | live/proposals/proposal_2026-09-21.json `input_as_of.shares` |
| universe (SPY file) | 2026-09-21 | live/proposals/proposal_2026-09-21.json `input_as_of.universe` |
| sectors | 2026-09-11 | live/proposals/proposal_2026-09-21.json `input_as_of.sectors` |
| descriptors | 2026-09-21 | live/proposals/proposal_2026-09-21.json `input_as_of.descriptors` |
| factor_returns | 2026-09-21 | live/proposals/proposal_2026-09-21.json `input_as_of.factor_returns` |
| specific_returns | 2026-09-21 | live/proposals/proposal_2026-09-21.json `input_as_of.specific_returns` |
| factor_cov | 2026-09-21 | live/proposals/proposal_2026-09-21.json `input_as_of.factor_cov` |
| specific_var | 2026-09-21 | live/proposals/proposal_2026-09-21.json `input_as_of.specific_var` |
| max_input_staleness_days | 10 | live/proposals/proposal_2026-09-21.json `max_input_staleness_days` |

Nine inputs, one field each, plus the single max. The sectors file is the
one stale input at 10 days, because it is the live Wikipedia snapshot
dated 2026-09-11 while the proposal is built on the 2026-09-21 close.

## Table 4: incremental integrity

The extension appends, never refits. Pre-cutoff block hashes are recorded
in tests/test_e11_extend.py and asserted after every extension.

| quantity | value | file / key |
| --- | --- | --- |
| frozen as-of | 2026-09-03 | live/extend.py `FROZEN_AS_OF` |
| sessions appended | 11 | live/extend.py `extend_model` result `extended` |
| first appended session | 2026-09-04 | live/extend.py `extend_model` result `new_dates[0]` |
| last appended session | 2026-09-21 | live/extend.py `extend_model` result `last_date` |
| descriptors block hash | 8f93968f67f31cd33453a7fad13685d74748f3f480f17406954459fdd31caafa | tests/test_e11_extend.py `BASELINE.descriptors` |
| factor_returns block hash | 42a31d64e0cb7619f09669cfdac217085172ccd577ee37c304da6bab3246700a | tests/test_e11_extend.py `BASELINE.factor_returns` |
| specific_returns block hash | 176dc4b39fb75f1dae6afd0f6afea3b14c64bd6ebcc855450d392d46bd9d489a | tests/test_e11_extend.py `BASELINE.specific_returns` |

The pre-2026-09-04 rows of descriptors, factor_returns and
specific_returns are byte-identical before and after the extension. The
extension also applies the E1 identity exclusions, so a reused symbol
does not reappear with another company's history; DD, the one dropped
ticker the sector file maps, stays out of returns and specific_returns,
asserted by tests/test_e11_extend.py.

## Table 5: the cost item and the E6 reconciliation

| quantity | value | file / key |
| --- | --- | --- |
| nav | 100000.0 | live/proposals/proposal_2026-09-21.json `nav` |
| establishment cost | 17.931038305607757 bp | live/proposals/proposal_2026-09-21.json `expected_establishment_cost_bps` |
| spread | 4.723374260207236 bp | live/proposals/proposal_2026-09-21.json `cost_breakdown_bps.spread` |
| impact | 4.142885161830039 bp | live/proposals/proposal_2026-09-21.json `cost_breakdown_bps.impact` |
| commission | 0.9712263089539801 bp | live/proposals/proposal_2026-09-21.json `cost_breakdown_bps.commission` |
| borrow | 8.093552574616503 bp | live/proposals/proposal_2026-09-21.json `cost_breakdown_bps.borrow` |
| total (the four legs) | 17.931038305607757 bp | live/proposals/proposal_2026-09-21.json `cost_breakdown_bps.total` |
| notional | 97122.63089539802 | live/proposals/proposal_2026-09-21.json `notional` |
| average trade size | 194.24526179079604 | live/proposals/proposal_2026-09-21.json `avg_trade_size` |
| E6 steady-state rebalance | 10.52718113254709 bp | live/cost_reconciliation.json `e6_reference.cost_bp` |
| ratio, establishment over E6 | 1.7033086141331812 | live/cost_reconciliation.json `ratio_establishment_over_e6` |
| verdict | reconciled | live/cost_reconciliation.json `verdict` |

The four-way decomposition sums to the stored total: spread 4.72 plus
impact 4.14 plus commission 0.97 plus borrow 8.09 equals 17.93 bp. The
trading leg (spread plus impact plus commission) is 9.84 bp against E6's
3.96 bp turnover component; the borrow leg is 8.09 bp against E6's 6.56
bp. The 75.34 bp figure in the task is the e11-setup proposal priced at
the 1e8 capacity AUM without borrow, stored as
live/proposals/proposal_2026-09-03.json `expected_establishment_cost_bps`
(75.34348012608805). Priced at the paper NAV of 100k with borrow, the
same establishment is 17.93 bp, so the ratio to E6 is 1.70x, not the
7.15x that came from the capacity AUM without borrow. The two borrow
legs match; the difference is the richer E9 trading model applied to the
full gross.

## Table 6: no earlier verdict moved

`efb.evaluate.prior_verdict_changes()` returns zero changed criteria for
every sprint. The full suite re-asserts the E8, E9 and E10 stored
criteria equal the recomputed ones.

| sprint | n_criteria | n_changed |
| --- | --- | --- |
| E1 | 5 | 0 |
| E2 | 13 | 0 |
| E3 | 9 | 0 |
| E4 | 7 | 0 |
| E5 | 5 | 0 |
| E6 | 7 | 0 |
| E7 | 6 | 0 |

Before the fix, E2 F2.0c moved from pass to fail because the extension
added a new above-50bp audit day in the appended sessions. The F2.0c
audit is now frozen at 2026-09-03, and the same freeze holds for the two
E4 probes that read the extended panels, so appended sessions cannot move
stored numbers.

## Decisions

- **The extension applies identity exclusions before writing returns.**
  Recomputing returns from prices without the E1 identity drops restored
  DD, a reused symbol, with another company's history. The extension now
  reads ticker_identity.parquet and ticker_identity_readded.parquet and
  applies the same drops and truncations as rebuild_e1.
- **The F2.0c audit and the two E4 probes are frozen at 2026-09-03.**
  They are stored measurements, not live measurements. The frozen as-of
  is a module constant, not a per-call parameter, so the freeze is
  explicit rather than accidental.
- **The live loop now refreshes its own version file.** The first
  extension rewrote VERSION.json and the evidence snapshot by hand. The
  loop now calls live/extend.py `refresh_version` to rehash the versioned
  set after an extension, so a subsequent extension is repeatable from
  code rather than from a one-off command.
- **The version-note test accepts the live loop's note.** The E3 test
  asserted the note starts with "Built by make rebuild (Sprint E". The
  live loop's VERSION.json note starts with "Extended daily by the E11
  live loop", so the test now accepts either prefix.

## Verification

### Commands and output

`make test`:

```
650 passed, 3 warnings in 445.67s (0:07:25)
```

`make lint` (plus `mypy live`, which the Makefile does not run):

```
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ✨ 🍰 ✨
151 files would be left unchanged.
=== mypy live ===
Success: no issues found in 9 source files
```

`make verify-evidence`:

```
.venv/bin/python -c "from efb import evidence; p = evidence.verify(); print('evidence OK' if not p else chr(10).join(p)); raise SystemExit(1 if p else 0)"
evidence OK
```

Exit status 0.

### Headline numbers, file and key

- day 1 2026-09-22, end date 2026-11-02, started true: live/clock.json `day_1`, `end_date`, `started`
- void start 2026-09-22 with reason and status void: live/clock.json `history[0]`
- sanity gate turnover 0.12957758249149315, passed true, proposals differ: live/sanity_gate.json `weight_turnover`, `passed`, `proposals_differ`
- max_input_staleness_days 10: live/proposals/proposal_2026-09-21.json `max_input_staleness_days`
- sessions appended 11, last date 2026-09-21: live/extend.py `extend_model` result
- pre-cutoff block hashes: tests/test_e11_extend.py `BASELINE`
- nav 100000.0, establishment cost 17.931038305607757 bp: live/proposals/proposal_2026-09-21.json `nav`, `expected_establishment_cost_bps`
- E6 cost 10.52718113254709 bp, ratio 1.7033086141331812, verdict reconciled: live/cost_reconciliation.json
- e11-setup cost at capacity AUM 75.34348012608805: live/proposals/proposal_2026-09-03.json `expected_establishment_cost_bps`
- verdict changes: efb.evaluate.prior_verdict_changes(), all n_changed 0

### git diff --stat from base_commit

```
37 files changed, 1270 insertions(+), 223 deletions(-)
```

### Yes or no, each with evidence

1. **Any two rows or two estimators identical?** No. The sanity gate ran
   two consecutive closes, and the proposals differ
   (live/sanity_gate.json `proposals_differ` true, turnover 0.1296).
   One estimator, XS-v1, is extended one session at a time, never
   re-estimated.
2. **Any exception caught and skipped, or any fallback taken?** No
   exception is caught and skipped. One fallback is taken and counted:
   the SPY universe minus the frozen model leaves 3 names out (BE, ILMN,
   P), stored as live/proposals/proposal_2026-09-21.json `n_excluded`.
   Share counts are fetched only for names not already cached, which is
   the design, not a fallback.
3. **Any criterion reworded or replaced by a different test?** No. No
   criterion text changed; the F2.0c audit and the E4 probes were frozen
   in code, not reworded.
4. **Any criterion that passes by construction?** No. The sanity gate is
   an acceptance guard, not a criterion. The idio share of 1.0 after the
   FMP hedge is by construction of the exact hedge, but it is a stored
   number, not a verdict.
5. **Any number that moved by a factor of 10 or more?** No. The buggy
   extension moved the F2.0c audit mean from 0.01782 to 0.01908 and the
   E4 momentum vol spread from 0.008963 to 0.008294, each about a 7
   percent relative change, and both were rolled back by the fixes.
6. **Any stored number typed into a notebook?** No. No notebook was
   touched in this task.
7. **Any earlier verdict changed?** No. prior_verdict_changes() returns
   n_changed 0 for E1 through E7, and the full suite re-asserts the E8,
   E9 and E10 stored criteria equal the recomputed ones.

### Anything decided that the reviewer might disagree with

The frozen as-of is a hard-coded module constant in efb/evaluate.py and
efb/probes.py rather than a registry-driven flag, so a future model
session boundary would need the constant moved by hand. The version-note
test now accepts two prefixes rather than one. The live loop writes its
own VERSION.json note, which is why the build-note assertion needed the
second prefix.

