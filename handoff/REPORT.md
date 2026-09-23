# Sprint E11 live fixes: report

Task `e11-live-fixes`, base commit bbe3180. The five fixes, the
minimum-position registry parameter and the breadth measurement are
landed and pushed. The owner's $10m Alpaca reset is still pending, so
the sanity gate has not yet re-run at $10m and the clock has not
restarted; that is stated in the body, not hidden. Every number below is
read from an artifact.

## The five fixes

- **Fix 4, the impact sigma: refuted, no change, no cascade.** The impact
  leg's sigma is daily. `live/evening_job.py _cost_decomposition` takes
  `sqrt(specific_var)`, and `specific_var` is the EWMA of squared daily
  specific returns, so it is a daily standard deviation. Worked example:
  MU daily specific_return std 0.02217 and sqrt(specific_var) 0.03020,
  both daily; MRNA 0.05984 and 0.19050. The book's total impact is 13.18
  bp under the daily sigma; annualizing would give 209.3 bp. No E9 or E10
  number moves. Recorded in docs/hygiene_ledger.md, 2026-09-22.
- **Fix 1: the quantization breach is finding E11-F1.** Continuing from
  E10-F27. Whole-share rounding of the smallest-weight tail breaches both
  clauses of the establishment bar: gross weight error 0.0539 (5.39% of
  NAV, 5.56% of gross), and 23 of 256 long names plus 13 of 243 short
  names round to zero shares. Mechanism and numbers in
  docs/hygiene_ledger.md, 2026-09-22.
- **Fix 2: Guard 1 re-derived, not rescaled.** The position cap moves from
  0.40 to 0.10 of NAV. See Table 9.
- **Fix 3: a failed NAV read fails the run.** `live/alpaca.py get_nav` no
  longer falls back to 1,000,000. A failed or invalid read raises, and
  `live/morning_job.py run_morning` reads the live NAV before building any
  order, so no order is submitted.
- **Fix 5: shares dated at or before the close.** `_input_as_of` clamps
  `shares` to the latest count on or before the close: 2026-09-22 becomes
  2026-09-17 for the 2026-09-21 close (see Table 3).

## The minimum position and the breadth consequence

`data/models/registry.json` XS-v1 `live.min_position_dollars` = 5000,
applied against the actual NAV: a name whose `|weight| * nav` is below
the threshold is dropped, not held at a badly rounded weight. The
parameter is NAV-relative in application, so it works at either NAV.
`docs/open_items.md` closes the item and names the residue: folding the
rule back into E8's construction stack rather than leaving it only in the
live path.

| quantity | $1m NAV | $10m NAV |
| --- | --- | --- |
| names kept | 27 | 399 |
| names dropped | 472 | 100 |
| kept gross | 0.2734 | 0.9418 |
| kept idio share | 0.8631 | 0.9999 |
| kept max factor exposure | 0.1458 | 0.0049 |
| naive breadth sqrt(460 / N_kept) | 4.1276 | 1.0737 |
| governing breadth sqrt(n_eff_full / n_eff_kept) | 3.0211 | 1.0276 |

The $1m book keeps 27 names, not the 150 to 200 the $5,000 ceiling
arithmetic suggested, because the top names carry only 27% of gross: the
long tail of small names is what carries the book's gross and its hedge.
That is the measured reason the $10m reset matters.

## Table 1: the clock

| quantity | value | file / key |
| --- | --- | --- |
| day 1 | 2026-09-22 | live/clock.json `day_1` |
| reporting window end | 2026-11-02 | live/clock.json `end_date` |
| reporting window days | 30 | live/clock.json `reporting_window_days` |
| run condition | open_ended | live/clock.json `run_condition` |
| started | true | live/clock.json `started` |
| void day 1 | 2026-09-22 | live/clock.json `history[0].day_1` |
| void reason | static days: the loop ran on the frozen 2026-09-03 close and would produce thirty identical proposals | live/clock.json `history[0].reason` |

The second void entry (the $10m economics change) is added only when the
sanity gate re-runs on two real closes at $10m, which is still pending the
owner's reset.

## Table 2: the sanity gate, as stored

Stored before the minimum-position drop; re-runs at $10m when the owner
resets the account.

| quantity | value | file / key |
| --- | --- | --- |
| close 1 | 2026-09-18 | live/sanity_gate.json `closes[0]` |
| close 2 | 2026-09-21 | live/sanity_gate.json `closes[1]` |
| proposals differ | true | live/sanity_gate.json `proposals_differ` |
| weight turnover | 0.12909727295192375 | live/sanity_gate.json `weight_turnover` |
| names before | 499 | live/sanity_gate.json `n_names_before` |
| names after | 499 | live/sanity_gate.json `n_names_after` |
| passed | true | live/sanity_gate.json `passed` |

## Table 3: staleness, the 2026-09-21 proposal

| input | as-of | file / key |
| --- | --- | --- |
| prices | 2026-09-21 | `input_as_of.prices` |
| shares | 2026-09-17 | `input_as_of.shares` |
| universe (SPY file) | 2026-09-21 | `input_as_of.universe` |
| sectors | 2026-09-11 | `input_as_of.sectors` |
| descriptors | 2026-09-21 | `input_as_of.descriptors` |
| factor_returns | 2026-09-21 | `input_as_of.factor_returns` |
| specific_returns | 2026-09-21 | `input_as_of.specific_returns` |
| factor_cov | 2026-09-21 | `input_as_of.factor_cov` |
| specific_var | 2026-09-21 | `input_as_of.specific_var` |
| max_input_staleness_days | 10 | `max_input_staleness_days` |

Shares moved from 2026-09-22 to 2026-09-17 by Fix 5: the 09-22 count was
filed after the close it prices, and the latest count on or before the
close is 09-17.

## Table 4: incremental integrity

Pre-cutoff block hashes are asserted by tests/test_e11_extend.py after
every extension. Rows dated on or before 2026-09-03 are byte-identical.

| artifact | rows on or before 2026-09-03 | rows after | pre-cutoff block hash |
| --- | --- | --- | --- |
| descriptors | 664146 | 38654 | 8f93968f67f31cd33453a7fad13685d74748f3f480f17406954459fdd31caafa |
| factor_returns | 70938 | 198 | 42a31d64e0cb7619f09669cfdac217085172ccd577ee37c304da6bab3246700a |
| specific_returns | 1842865 | 5467 | 176dc4b39fb75f1dae6afd0f6afea3b14c64bd6ebcc855450d392d46bd9d489a |

The daily dry run extended no new rows: no 2026-09-22 close exists yet, so
prices still end 2026-09-21 and the VERSION.json data_hash is unchanged.

## Table 5: the cost

The stored E6 reconciliation is on the full 499-name book. The rebuilt
proposal applies the minimum-position drop, so the executed book at $1m
is 27 names and its cost is stored beside the reconciliation.

| quantity | value | file / key |
| --- | --- | --- |
| nav | 1000000.0 | live/cost_reconciliation.json `establishment.nav` |
| gross (full book) | 0.9685376726947534 | live/cost_reconciliation.json `establishment.gross` |
| n names (full book) | 499 | live/cost_reconciliation.json `establishment.n_names` |
| average trade size (full book) | 1940.9572599093256 | live/cost_reconciliation.json `establishment.avg_trade_size` |
| spread | 4.713262872845437 bp | live/cost_reconciliation.json `establishment.spread_bp` |
| impact | 13.182112210073752 bp | live/cost_reconciliation.json `establishment.impact_bp` |
| commission | 0.9685376726947534 bp | live/cost_reconciliation.json `establishment.commission_bp` |
| borrow | 8.071147272456288 bp | live/cost_reconciliation.json `establishment.borrow_bp` |
| total | 26.935060028070232 bp | live/cost_reconciliation.json `establishment.total_bp` |
| E6 steady-state rebalance | 10.52718113254709 bp | live/cost_reconciliation.json `e6_reference.cost_bp` |
| ratio, establishment over E6 | 2.55862036464772 | live/cost_reconciliation.json `ratio_establishment_over_e6` |
| verdict | reconciled | live/cost_reconciliation.json `verdict` |
| kept-book names at $1m | 27 | live/proposals/proposal_2026-09-21.json `n_kept` |
| kept-book gross | 0.2733587879946513 | live/proposals/proposal_2026-09-21.json `kept_gross` |
| kept-book total cost | 3.9645212321419105 bp | live/proposals/proposal_2026-09-21.json `expected_establishment_cost_bps` |

The sigma investigation (Fix 4) confirmed the impact leg is daily, so the
13.18 bp impact and the 2.56x ratio stand as written; the reconciliation
is not reopened.

## Table 6: Render and the database

| quantity | value | source |
| --- | --- | --- |
| services | efb-live-dashboard (web), efb-live-daily (cron) | render.yaml |
| dashboard start | streamlit run live/dashboard_app.py | render.yaml |
| cron start | python scripts/run_live_daily.py | render.yaml |
| cron schedule | 30 22 * * 1-5 UTC | render.yaml |
| dry run toggle | EFB_DRY_RUN, default true | render.yaml, scripts/run_live_daily.py |
| largest file the dashboard reads | 1524 bytes, live/cost_reconciliation.json | measured |
| state | Supabase, local parquet fallback under live/state/supabase/ | live/store.py |

Deployment is not performed; it needs the owner's Render, Supabase and
Alpaca paper credentials. The store is not configured for Supabase here
(supabase is not installed), so the daily run wrote to the local parquet
fallback, which is gitignored.

## Table 7: the trade explanation, five positions

From the kept book, the five highest-ranked positions by absolute alpha,
with the stated reason from live/trade_reasons.py.

| ticker | rank | alpha | z | idio vol | target weight | previous weight | trade | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MRNA | 1 | 0.000298 | 6.780151 | 0.190501 | 0.030815 | 0.031733 | -0.000918 | alpha moved |
| LITE | 2 | 0.000017 | 6.319079 | 0.047413 | 0.025606 | 0.016743 | 0.008863 | alpha moved |
| DELL | 3 | 0.000010 | 3.955123 | 0.045544 | 0.011645 | 0.008457 | 0.003188 | alpha moved |
| MRVL | 4 | 0.000009 | 4.565633 | 0.039739 | 0.015135 | 0.009808 | 0.005328 | alpha moved |
| MU | 5 | 0.000009 | 7.787528 | 0.030196 | 0.032631 | 0.023736 | 0.008895 | alpha moved |

Every position row carries one of the four reasons (alpha moved, risk
moved, the hedge moved, drifted past a band) or "no trade";
tests/test_e11_render.py pins the classifier on all four buckets.

## Table 8: no earlier verdict moved

| sprint | n_criteria | n_changed |
| --- | --- | --- |
| E1 | 5 | 0 |
| E2 | 13 | 0 |
| E3 | 9 | 0 |
| E4 | 7 | 0 |
| E5 | 5 | 0 |
| E6 | 7 | 0 |
| E7 | 6 | 0 |

E8 (8 criteria), E9 (5 criteria) and E10 (6 criteria) are covered by
tests/test_e8_results.py, test_e9_results.py and test_e10_results.py,
which assert the stored criteria equal the recomputed ones; all pass in
the full run below.

## Table 9: the guards at $1m

| guard | old value | new value | arithmetic | fires against a legitimate order | fire test |
| --- | --- | --- | --- | --- | --- |
| position cap | 0.40 x NAV = $400,000 | 0.10 x NAV = $100,000 | largest target 0.0326 (MU); ten times that is 0.326, which cleared 0.40. 0.10 sits clear of 0.0326 with 3.1x headroom and trips 0.326 | no, only a 10x fat-finger trips it | tests/test_e11_guards.py test_a_ten_times_order_on_the_largest_target_trips_the_cap |
| traded-notional brake | 2,000,000 | 2,000,000 (unchanged) | one full flip of the gross-1 book, 2 x 1,000,000 | no | tests/test_e11_guards.py test_brake_accumulates_across_orders |

Guard 2 was already re-derived at $1m in the prior task and does not move.

## Table 10: quantization

The whole-share rounding report for the 2026-09-21 proposal at 1,000,000.
The full book breaches the bar and is finding E11-F1; the kept book
(after the minimum-position drop) is reported beside it.

| quantity | full book | kept book at $1m |
| --- | --- | --- |
| names | 499 | 27 |
| gross-weight error from rounding | 0.05389283244759932 | 0.0056529973414225195 |
| gross notional error, dollars | 53892.83 | 5653.00 |
| worst-case per-name error, pct of target | 100 (names rounding to zero) | 17.09 |
| long names rounding to zero shares | 23 | 0 |
| short names rounding to zero shares | 13 | 0 |
| effective name count (n_eff) | 157.33 | 17.24 |
| NAV used | 1000000.0 | 1000000.0 |
| average target dollar size | 1940.96 | 547.81 |
| bar breached | yes, both clauses, E11-F1 | no zero-rounds; gross error 0.57% of NAV |

The full-book numbers are the E11-F1 finding. The kept-book distribution
is stored in live/proposals/proposal_2026-09-21.json `quantization`.

## Verification

### Commands and output

`make test` (full suite, run after the registry and evidence changes):

```
680 passed, 1 skipped, 3 warnings in 453.78s (0:07:33)
```

`make lint`, plus `mypy live` which the Makefile does not run:

```
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
pyproject.toml: note: unused section(s): module = ['alpaca', 'alpaca.trading.*', 'supabase']
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ✨ 🍰 ✨
158 files would be left unchanged.
=== mypy live ===
Success: no issues found in 13 source files
```

`make verify-evidence`:

```
.venv/bin/python -c "from efb import evidence; p = evidence.verify(); print('evidence OK' if not p else chr(10).join(p)); raise SystemExit(1 if p else 0)"
evidence OK
```

Exit status 0.

### Headline numbers, file and key

- impact sigma daily, MU 0.03020, MRNA 0.19050, total impact 13.18 bp: docs/hygiene_ledger.md (2026-09-22 entry)
- E11-F1 gross weight error 0.0539, 23 long and 13 short to zero: docs/hygiene_ledger.md, live/alpaca.py `whole_share_quantization`
- Guard 1 cap 0.10, Guard 2 brake 2,000,000: live/guards.py `MAX_POSITION_PCT_OF_NAV`, `MAX_TRADED_NOTIONAL_PER_RUN`
- shares as-of 2026-09-17, max_input_staleness_days 10: live/proposals/proposal_2026-09-21.json `input_as_of.shares`, `max_input_staleness_days`
- min_position_dollars 5000: data/models/registry.json `models.XS-v1.live.min_position_dollars`
- kept 27 of 499 at $1m, kept gross 0.2734, naive breadth 4.1276, governing 3.0211: live/proposals/proposal_2026-09-21.json `n_kept`, `kept_gross`, `breadth_naive_bound`, `breadth_governing`
- establishment cost 26.94 bp, E6 ratio 2.56x, verdict reconciled: live/cost_reconciliation.json
- day 1 2026-09-22, run_condition open_ended: live/clock.json
- sanity gate turnover 0.1291, passed true: live/sanity_gate.json

### git diff --stat from base_commit (bbe3180)

```
 data/VERSION.json                          |   6 +-
 data/models/registry.json                  |   6 +-
 docs/hygiene_ledger.md                     |  51 ++++++++++
 docs/open_items.md                         |  12 +++
 efb/evaluate.py                            |   4 +
 efb/registry.py                            |  13 +++
 evidence/MANIFEST.json                     |  20 ++--
 evidence/data/VERSION.json.gz              | Bin 7986 -> 7972 bytes
 evidence/data/models/registry.json.gz      | Bin 4207 -> 4389 bytes
 live/alpaca.py                             |  73 ++++++++++----
 live/evening_job.py                        | 150 +++++++++++++++++++++++------
 live/guards.py                             |  10 +-
 live/morning_job.py                        |   8 +-
 live/proposals/proposal_2026-09-21.json    |  73 ++++++++++++--
 live/proposals/proposal_2026-09-21.parquet | Bin 19968 -> 4114 bytes
 notebooks/E5_walkthrough.ipynb             |  94 +++++++++---------
 scripts/run_live_daily.py                  |   5 +-
 sprints/E5/RESULTS.json                    |   6 +-
 tests/test_e11_evening.py                  |  49 ++++++++++
 tests/test_e11_execution.py                |  46 +++++++++
 tests/test_e11_guards.py                   |  18 +++-
 tests/test_registry.py                     |  11 +++
 tests/test_run_live_daily.py               |  39 ++++++++
 23 files changed, 566 insertions(+), 128 deletions(-)
```

### Yes or no, each with evidence

1. **Any two rows or two estimators identical?** No. The sanity gate ran
   two consecutive closes and the proposals differ
   (live/sanity_gate.json `proposals_differ` true, turnover 0.1291).
2. **Any exception caught and skipped, or any fallback taken?** No
   exception is caught and skipped. One fallback exists and was taken in
   this task: the live-series store falls back to local parquet because
   Supabase is not configured here (live/store.py `get_client` returns
   None, is_supabase false). The NAV fallback that existed at base_commit
   was removed by Fix 3 and no longer exists.
3. **Any criterion reworded or replaced by a different test?** No. No
   criterion text changed.
4. **Any criterion that passes by construction?** No. No new criterion was
   registered.
5. **Any number that moved by a factor of 10 or more?** Yes. The executed
   name count moved from 499 to 27 kept names (about 18.5x down) under the
   minimum-position drop at $1m, by the owner's instruction and stored as
   n_kept/n_dropped in the proposal manifest. At $10m the same threshold
   keeps 399 names.
6. **Any stored number typed into a notebook?** No. The E5 walkthrough was
   re-executed because its printed data_hash moved with the registry; the
   hash is recomputed in the notebook's first cell, never typed.
7. **Any earlier verdict changed?** No. prior_verdict_changes() is 0 for
   E1 through E7, and the E8, E9 and E10 results tests pass.

### Anything decided that the reviewer might disagree with

The minimum-position drop is applied in the evening proposal at the design
NAV (live/evening_job.py `PAPER_NAV`, 1,000,000), not at the live NAV
read in the morning, because the proposal is built before the morning NAV
read exists. At $1m this keeps 27 names, which is far below the owner's
stated 150 to 200 expectation, and the kept book is not factor-neutral
(kept idio share 0.8631, max exposure 0.1458) because the dropped tail
carried part of the hedge. Both are reported, not hidden, and both are the
reason the $10m reset matters. The rebuilt proposal_2026-09-21.parquet
(27 rows) replaced the 499-row first proposal in the commit, which changes
a previously committed artifact; the 499-row full book remains in the E11
record and in the cost reconciliation.
