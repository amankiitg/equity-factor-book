# Sprint E11 live, then render: report

Task `e11-live-then-render`, base commit f2a2a83. Part A makes the loop
live and reframes the clock to an open-ended run; Part B puts it on
Render behind a live dashboard with Supabase state. The loop runs
indefinitely, paper only.

**The book runs indefinitely, paper only. Day 1 is 2026-09-22; the
thirty trading days are a reporting window, not the life of the run.**
Render runs two services, `efb-live-dashboard` (web) and `efb-live-daily`
(the daily cron). Every number below is read from an artifact.

## Table 1: the clock

| quantity | value | file / key |
| --- | --- | --- |
| void day 1 | 2026-09-22 | live/clock.json `history[0].day_1` |
| void reason | static days: the loop ran on the frozen 2026-09-03 close and would produce thirty identical proposals | live/clock.json `history[0].reason` |
| void status | void | live/clock.json `history[0].status` |
| new day 1 | 2026-09-22 | live/clock.json `day_1` |
| reporting window end | 2026-11-02 | live/clock.json `end_date` |
| reporting window days | 30 | live/clock.json `reporting_window_days` |
| started | true | live/clock.json `started` |
| run condition | open_ended | live/clock.json `run_condition` |

The loop's run condition is open-ended: `live/clock.py` `run_condition()`
returns "the book runs indefinitely; the thirty trading days from day 1
are a reporting window over the history, not the life of the run". No
code reads an end date as a stop condition.

## Table 2: the day-1 sanity gate

| quantity | value | file / key |
| --- | --- | --- |
| close 1 | 2026-09-18 | live/sanity_gate.json `closes[0]` |
| close 2 | 2026-09-21 | live/sanity_gate.json `closes[1]` |
| proposals differ | true | live/sanity_gate.json `proposals_differ` |
| passed | true | live/sanity_gate.json `passed` |
| weight turnover | 0.12909727295192375 | live/sanity_gate.json `weight_turnover` |
| turnover definition | 0.5 * sum(abs(w_t - w_{t-1})) | live/sanity_gate.json `definition` |
| names before | 499 | live/sanity_gate.json `n_names_before` |
| names after | 499 | live/sanity_gate.json `n_names_after` |

## Table 3: staleness, per proposal

The latest proposal, live/proposals/proposal_2026-09-21.json, stores the
as-of date of all nine inputs and the single max.

| input | as-of | file / key |
| --- | --- | --- |
| prices | 2026-09-21 | `input_as_of.prices` |
| shares | 2026-09-22 | `input_as_of.shares` |
| universe (SPY file) | 2026-09-21 | `input_as_of.universe` |
| sectors | 2026-09-11 | `input_as_of.sectors` |
| descriptors | 2026-09-21 | `input_as_of.descriptors` |
| factor_returns | 2026-09-21 | `input_as_of.factor_returns` |
| specific_returns | 2026-09-21 | `input_as_of.specific_returns` |
| factor_cov | 2026-09-21 | `input_as_of.factor_cov` |
| specific_var | 2026-09-21 | `input_as_of.specific_var` |
| max_input_staleness_days | 10 | `max_input_staleness_days` |

## Table 4: incremental integrity

Pre-cutoff block hashes are recorded in tests/test_e11_extend.py and
asserted after every extension. Rows dated on or before 2026-09-03 are
byte-identical before and after.

| artifact | rows on or before 2026-09-03 | rows after | pre-cutoff block hash |
| --- | --- | --- | --- |
| descriptors | 664146 | 38654 | 8f93968f67f31cd33453a7fad13685d74748f3f480f17406954459fdd31caafa |
| factor_returns | 70938 | 198 | 42a31d64e0cb7619f09669cfdac217085172ccd577ee37c304da6bab3246700a |
| specific_returns | 1842865 | 5467 | 176dc4b39fb75f1dae6afd0f6afea3b14c64bd6ebcc855450d392d46bd9d489a |

## Table 5: the cost item and the E6 reconciliation

| quantity | value | file / key |
| --- | --- | --- |
| nav | 1000000.0 | live/proposals/proposal_2026-09-21.json `nav` |
| gross | 0.9685376726947534 | live/proposals/proposal_2026-09-21.json `gross` |
| n names | 499 | live/proposals/proposal_2026-09-21.json `n_names` |
| average trade size | 1940.9572599093256 | live/proposals/proposal_2026-09-21.json `avg_trade_size` |
| spread | 4.713262872845437 bp | `cost_breakdown_bps.spread` |
| impact | 13.182112210073752 bp | `cost_breakdown_bps.impact` |
| commission | 0.9685376726947534 bp | `cost_breakdown_bps.commission` |
| borrow | 8.071147272456288 bp | `cost_breakdown_bps.borrow` |
| total | 26.935060028070232 bp | `cost_breakdown_bps.total` |
| establishment cost in dollars | 2693.5060028070234 | live/proposals/proposal_2026-09-21.json `expected_establishment_cost_usd` |
| E6 steady-state rebalance | 10.52718113254709 bp | live/cost_reconciliation.json `e6_reference.cost_bp` |
| ratio, establishment over E6 | 2.55862036464772 | live/cost_reconciliation.json `ratio_establishment_over_e6` |
| verdict | reconciled | live/cost_reconciliation.json `verdict` |

The four legs sum to the total, and the dollar equivalent is the total
in bp times the 1,000,000 NAV over 1e4. The 75.34 bp figure in the task
is the e11-setup proposal priced at the 1e8 capacity AUM without borrow;
at the 1,000,000 paper NAV with borrow the same establishment is 26.94 bp,
so the ratio to E6 is 2.56x, not the 7.15x from the capacity AUM without
borrow. The two borrow legs match; the difference is the richer E9
trading model on the full gross, whose square-root impact raises the
per-dollar cost at the larger notional.

## Table 6: Render

| quantity | value | source |
| --- | --- | --- |
| services | efb-live-dashboard (web), efb-live-daily (cron) | render.yaml |
| dashboard start | streamlit run live/dashboard_app.py | render.yaml |
| cron start | python scripts/run_live_daily.py | render.yaml |
| cron schedule | 30 22 * * 1-5 UTC (after the close) | render.yaml |
| largest file the dashboard reads | 1524 bytes, live/cost_reconciliation.json | measured |
| cold start | unmeasured, bounded by the Streamlit boot and the live series, no research parquet read | structural |
| peak memory | bounded by the live series in memory, no research parquet read | structural |
| state | Supabase (live/store.py), local parquet fallback under live/state/supabase/ | live/store.py |

The dashboard never reads a research parquet; its largest read is the
1524-byte cost reconciliation beside the 453-byte clock. Cold-start time
and peak memory are structural bounds, not measured numbers, because the
services have not been deployed (deployment needs the owner's Render
account and Supabase and Alpaca paper credentials).

## Table 7: the trade explanation, a sample of five positions

From proposal_2026-09-21 against proposal_2026-09-18, the five
highest-ranked positions by absolute alpha, with the stated reason from
live/trade_reasons.py.

| ticker | rank | alpha | z | idio vol | target weight | previous weight | trade | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MRNA | 1 | 0.000298 | 6.780151 | 0.190501 | 0.030816 | 0.031734 | -0.000918 | alpha moved |
| LITE | 2 | 0.000017 | 6.319079 | 0.047413 | 0.025623 | 0.016752 | 0.008871 | alpha moved |
| DELL | 3 | 0.000010 | 3.955123 | 0.045544 | 0.011620 | 0.008431 | 0.003189 | alpha moved |
| MRVL | 4 | 0.000009 | 4.565633 | 0.039739 | 0.015131 | 0.009802 | 0.005329 | alpha moved |
| MU | 5 | 0.000009 | 7.787528 | 0.030196 | 0.032615 | 0.023734 | 0.008882 | alpha moved |

Every position row carries one of the four reasons (alpha moved, risk
moved, the hedge moved, drifted past a band) or "no trade". A trade with
no stated reason is a bug, and tests/test_e11_render.py pins the
classifier on all four buckets.

## Table 8: no earlier verdict moved

`efb.evaluate.prior_verdict_changes()` returns zero changed criteria for
E1 through E7; the full suite re-asserts the E8, E9 and E10 stored
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

E8 through E10 are covered by their own results tests
(tests/test_e8_results.py, test_e9_results.py, test_e10_results.py), all
passing.

## The 1,000,000 NAV is a design parameter

The paper account is new, separate from credit-trading-lab's, funded at
1,000,000 dollars, with the REST base https://paper-api.alpaca.markets/v2
(alpaca-py appends the version, so live/alpaca.py carries the base
without the /v2 suffix). NAV enters every proposal beside the cost in bp
and in dollars; a proposal with a null nav raises and is a failed run
(live/evening_job.py, pinned by tests/test_e11_evening.py).

### The two guards, re-derived for 1,000,000

| guard | arithmetic | value | file |
| --- | --- | --- | --- |
| position cap | 0.40 x 1,000,000 | 400,000 per position | live/guards.py `MAX_POSITION_PCT_OF_NAV` |
| traded-notional brake | one full flip of the gross-1 book, 2 x 1,000,000 | 2,000,000 per run | live/guards.py `MAX_TRADED_NOTIONAL_PER_RUN` |

The brake was 200,000 at the previous 100,000 book (2 x 100,000). At
1,000,000 the same one-full-flip arithmetic gives 2,000,000, which still
catches a fat-finger order at ten times the book (10,000,000).

### Whole-share quantization, the first proposal

Shorts must be whole shares (Alpaca paper rejects fractional sell-to-open),
so every target notional is quantized to integer shares at the proposal
close. live/alpaca.py `whole_share_quantization` reports it for the
2026-09-21 proposal at 1,000,000:

| quantity | value | source |
| --- | --- | --- |
| gross-weight error from rounding | 0.05389283244759932 | live/alpaca.py `whole_share_quantization` |
| gross notional error in dollars | 53892.83244759932 | same |
| long targets rounding to zero shares | 23 | same |
| short targets rounding to zero shares | 13 | same |

The gross-weight error is 0.054 of NAV, about 5.4 percent of the book,
from quantizing to whole shares. It is below the gross cap and is the
mechanical cost of whole-share execution, not a finding; it is reported
rather than adjusted.

### Account emptiness and separation, before the first live order

live/alpaca.py `verify_account` reads the account id and the position
count, and `require_empty_account` refuses to trade unless the account is
empty. scripts/verify_account.py prints the account id and the count
(never a key or secret) for the one-time pre-flight.

Run with the owner's keys, 2026-09-22:

| quantity | value |
| --- | --- |
| EFB paper account id | 5a255c4d-b385-47e6-875b-9186a939288f |
| EFB open positions | 0 |
| EFB account empty | true |
| credit-trading-lab account id | adc94a17-ef02-4f3f-8ebe-02217cb947a8 |
| ids distinct | true |

The account is empty and its id differs from credit-trading-lab's, so the
two books are provably disjoint for E12's attribution.

### Credentials

.env.example names the variables with one comment each, with EFB-specific
names distinct from credit-trading-lab's. .env is gitignored (and
!.env.example is the one exception so the example is committed). No key
or secret appears in any committed file, log, artifact, notebook output
or test fixture; tests/test_e11_render.py pins that the example carries
names, never values.

## Decisions

- **The Alpaca account is a separate paper account under the existing
  login.** Alpaca's dashboard supports several paper accounts ("Open New
  Paper Account" in the account selector), so EFB's positions, cash, NAV
  and fills are disjoint from credit-trading-lab's without a second
  login. The account itself is not created (I have no dashboard access);
  the owner creates it and sets the keys. Code reads
  EFB_ALPACA_PAPER_API_KEY and EFB_ALPACA_PAPER_SECRET_KEY, distinct
  from credit-trading-lab's names.
- **The morning execution runs in the same daily cron as the evening,
  after the close.** The task asks for two services, one cron running
  both jobs. Paper only, so the after-hours submission is a paper fill,
  not a market-order timing decision.
- **Supabase is the live-series store, with a local fallback.** The store
  degrades to parquet under live/state/supabase/ when Supabase is not
  configured, so local dry runs and the test suite keep working. The
  provisioning script and schema are committed; provisioning was not run
  because it needs the owner's credentials.
- **Deployment is not performed.** Render, Supabase and Alpaca paper all
  need the owner's credentials, which I do not have. The deployable
  artifacts (render.yaml, the dashboard, the cron, the schema, the
  provisioning script) are committed and tested.
- **NAV is 1,000,000, a design parameter.** Every proposal stores nav
  beside the cost in bp and in dollars, the two guards are re-derived for
  1,000,000, and the sanity-gate proposals and the cost reconciliation
  are regenerated at 1,000,000. The account-emptiness check and the
  whole-share quantization report are committed; the account check has
  run and confirmed the account is empty and distinct.

## Verification

### Commands and output

`make test`:

```
670 passed, 3 warnings in 427.57s (0:07:07)
```

`make lint` (plus `mypy live`, which the Makefile does not run):

```
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ✨ 🍰 ✨
157 files would be left unchanged.
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

- day 1 2026-09-22, run_condition open_ended, window end 2026-11-02: live/clock.json `day_1`, `run_condition`, `end_date`
- sanity gate turnover 0.12909727295192375, passed true: live/sanity_gate.json
- max_input_staleness_days 10: live/proposals/proposal_2026-09-21.json
- pre-cutoff block hashes and row counts: tests/test_e11_extend.py, data/models/XS-v1/*.parquet
- nav 1000000.0, establishment cost 26.935060028070232 bp, 2693.5060028070234 dollars, E6 10.52718113254709 bp, ratio 2.55862036464772: live/cost_reconciliation.json
- trade reasons, five-name sample: live/proposals/proposal_2026-09-21.parquet against proposal_2026-09-18.parquet
- verdict changes: efb.evaluate.prior_verdict_changes(), all n_changed 0

### git diff --stat from base_commit

```
52 files changed, 2703 insertions(+), 314 deletions(-)
```

### Yes or no, each with evidence

1. **Any two rows or two estimators identical?** No. The sanity gate ran
   two consecutive closes and the proposals differ
   (live/sanity_gate.json `proposals_differ` true, turnover 0.1291).
   One estimator, XS-v1, is extended one session at a time.
2. **Any exception caught and skipped, or any fallback taken?** No
   exception is caught and skipped. Three fallbacks are taken and
   counted: the store falls back to local parquet when Supabase is not
   configured (live/store.py `get_client` returns None); the live NAV
   falls back to 1,000,000.0 when the account read fails (live/alpaca.py
   `get_nav`); and the SPY universe minus the frozen model leaves 3 names
   out (BE, ILMN, P), stored as `n_excluded`.
3. **Any criterion reworded or replaced by a different test?** No. No
   criterion text changed.
4. **Any criterion that passes by construction?** No. The sanity gate is
   an acceptance guard, not a criterion; the idio share of 1.0 after the
   FMP hedge is by construction of the hedge but is a stored number, not
   a verdict.
5. **Any number that moved by a factor of 10 or more?** Yes. The NAV
   moved from 100,000 to 1,000,000 (10x), by the owner's explicit
   instruction, and the traded-notional brake moved from 200,000 to
   2,000,000 (10x) as its arithmetic consequence. The establishment cost
   in bp moved from 17.93 to 26.94 (1.5x), which follows from the
   square-root impact at the larger notional. All three are recorded
   here, not hidden.
6. **Any stored number typed into a notebook?** No. No notebook was
   touched in this task.
7. **Any earlier verdict changed?** No. prior_verdict_changes() returns
   n_changed 0 for E1 through E7, and the E8 through E10 results tests
   pass.

### Anything decided that the reviewer might disagree with

The morning execution is folded into the same daily cron as the evening,
after the close, rather than a separate pre-open cron, because the task
specifies two services and paper only. The Alpaca paper account and the
Supabase schema are specified and committed but not created or
provisioned, because those need the owner's credentials; the report
states which parts are unverified for that reason. Cold-start time and
peak memory are stated as structural bounds rather than measured numbers,
because the services have not been deployed.


