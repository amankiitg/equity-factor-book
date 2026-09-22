# Sprint E11 setup: report

Task `e11-setup`, base commit c263021. The daily paper-trading loop is
stood up and the thirty-trading-day clock has started.

**The clock started. Day 1 is 2026-09-22; the thirty-day end date is
2026-11-02.** The loop runs end to end on one paper day, in dry run, and
F11.1 to F11.3 are pre-registered with verdicts pending. Every number
below is read from an artifact.

## Table 1: the clock

| quantity | value | file / key |
| --- | --- | --- |
| day 1 | 2026-09-22 | live/clock.json `day_1` |
| end date | 2026-11-02 | live/clock.json `end_date` |
| trading days | 30 | live/clock.json `trading_days` |
| started | true | live/clock.json `started` |
| calendar | business days, day 1 included | live/clock.py `_end_date` |

The end date is 30 business days from day 1, computed by
`pd.bdate_range(day_1, periods=30)`, which is a business-day calendar, not
the exchange holiday calendar. The clock is never restarted with a
different day.

## Table 2: F10.1b re-registered to fail

The criterion was re-registered against F10.1's verbatim threshold, per
the owner's approval. Verdict: fail. The old values stay in the revisions
block.

| quantity | value | file / key |
| --- | --- | --- |
| verdict | fail | sprints/E10/RESULTS.json `criteria.F10.1b.verdict` |
| threshold | simulated median drawdown within 10% of the analytical value | sprints/E10/RESULTS.json `criteria.F10.1b.threshold` |
| median relative gap | 0.296266 | sprints/E10/RESULTS.json `criteria.F10.1b.stored_numbers.expected_mdd_relative_gap` |
| mean relative gap | 0.257764 | sprints/E10/RESULTS.json `criteria.F10.1b.stored_numbers.expected_mdd_mean_relative_gap` |
| simulated median drawdown | -0.140308 | sprints/E10/RESULTS.json `criteria.F10.1b.stored_numbers.simulated_median_drawdown` |
| old verdict | pass | sprints/E10/RESULTS.json `revisions.changed.F10.1b.old.verdict` |
| new verdict | fail | sprints/E10/RESULTS.json `revisions.changed.F10.1b.new.verdict` |

The horizon fix cut the gap from 296% to about 26%, and the remaining
mean-versus-median part is recorded in the criterion note. No other E10
criterion moved.

## Table 3: the day-1 proposal

The evening job builds the null book from `idio_momentum` through the full
stack. Nothing executes.

| quantity | value | file / key |
| --- | --- | --- |
| signal | idio_momentum | live/proposals/proposal_2026-09-03.json `signal` |
| proposal as-of close | 2026-09-03 | live/proposals/proposal_2026-09-03.json `as_of` |
| universe source | raw/spy_holdings/spy_holdings_2026-09-18.parquet | live/proposals/proposal_2026-09-03.json `universe_source` |
| n names | 499 | live/proposals/proposal_2026-09-03.json `n_names` |
| n excluded from the frozen model | 4 (BE, DD, ILMN, P) | live/proposals/proposal_2026-09-03.json `n_excluded` |
| idio share after FMP | 1.0 | live/proposals/proposal_2026-09-03.json `idio_share_after_fmp` |
| max factor exposure after FMP | 2.5e-15 | live/proposals/proposal_2026-09-03.json `max_abs_exposure_after_fmp` |
| gross | 1.0 | live/proposals/proposal_2026-09-03.json `gross` |
| net | -1.47e-15 | live/proposals/proposal_2026-09-03.json `net` |
| target annual vol | 0.10 | live/proposals/proposal_2026-09-03.json `target_annual_vol` |
| achieved annual vol | 0.0423 | live/proposals/proposal_2026-09-03.json `achieved_annual_vol` |
| gross cap bound | true | live/proposals/proposal_2026-09-03.json `gross_cap_bound` |
| expected establishment cost | 75.34 bps | live/proposals/proposal_2026-09-03.json `expected_establishment_cost_bps` |

The universe is the SPY archive and is asserted, not assumed: the loader
rejects any archive dated before the 2026-09-18 seam. The null book is
factor-neutral to machine precision after the exact FMP hedge, and its
null-ness is the point: factor-neutral IC -0.0031 (t -0.51) at horizon 21,
read from data/alpha/summary.parquet.

## Table 4: the two fail-safe guards

Ported from v8.x and restated for the E11 book. Each has a test that
trips it.

| guard | condition that trips it | action | constant | file |
| --- | --- | --- | --- | --- |
| 1 position-size cap | abs(target notional) > 40% of NAV | REJECTED_CAP, never submitted | MAX_POSITION_PCT_OF_NAV = 0.40 | live/guards.py |
| 2 traded-notional brake | run traded notional would exceed the absolute brake | REJECTED_TRADED_NOTIONAL, never submitted | MAX_TRADED_NOTIONAL_PER_RUN = 200000 | live/guards.py |

Guard 1 is NAV-relative, Guard 2 is absolute. The brake was restated from
v8.x's 16000 to 200000, one full flip of the 100k gross book, so a
fat-finger ten times the book is still caught while the book establishes
in one run. Each guard has a firing test in tests/test_e11_guards.py.

## Table 5: what is reused from v8.x and what is rebuilt

| piece | decision | why |
| --- | --- | --- |
| loop shape (evening propose, morning execute, reconcile) | reused | proven operational shape |
| Option A governance | reused, ported | propose, rules decide, nothing discretionary; dated decisions |
| two fail-safe guards | reused, restated | different units on purpose; constants resized for E11 |
| idio_momentum alpha, Procedure 6.3, FMP hedge, E8 constraints, E9 costs, E10 vol | rebuilt from the EFB stack | the stack E11 exists to run |
| dashboard D10 | rebuilt, not copied | the strategy-review view, answer first |
| state store | rebuilt on EFB artifacts, no Supabase | the owner's artifacts are the state |

The morning job's live Alpaca path is stubbed: it reads paper keys from
the environment only and raises clearly when `alpaca-py` is missing. The
loop runs in dry run today.

## Table 6: no other verdict moved

Only two RESULTS.json files differ from base: `sprints/E10/RESULTS.json`
(F10.1b pass to fail, by the owner's approval) and the new
`sprints/E11/RESULTS.json` (three pending). Every F1.x to F9.x and every
other F10.x is byte-identical, because their RESULTS.json files did not
change:

```
git diff --name-only c263021..HEAD -- 'sprints/*/RESULTS.json'
sprints/E10/RESULTS.json
sprints/E11/RESULTS.json
```

## Decisions

- **The E8 constraint set is satisfied by the hedge plus two caps.** The
  exact FMP hedge drives every modeled factor exposure, styles and sectors
  included, to machine precision, so sector-neutrality and beta-neutrality
  are exact in model. The remaining constraints, gross at most 1 and net
  zero, hold to 1e-15. The position cap does not bind at this book's
  scale. The E10 vol target is applied and capped by gross 1: a null
  alpha cannot reach 10% annual vol inside gross 1, so the cap binds and
  the achieved 4.23% is stored beside the 10% target.
- **Day 1 is 2026-09-22, the day the loop first ran.** The proposal's
  as-of close is 2026-09-03, the last close in the frozen model data. The
  seam is stated, not bridged: going forward the loop needs live data, and
  until then it re-runs on the frozen close.
- **The loop runs dry.** Live Alpaca paper submission needs `alpaca-py`
  plus paper keys from the environment. Neither is available to me, so
  the dry-run path is complete and the live path fails loudly rather than
  silently.
- **F11.x are pre-registered, not evaluated.** The 30-day window has not
  closed, so every verdict is pending with empty stored numbers, and the
  criterion text is copied verbatim out of the roadmap by a script.

## Verification

### Commands and output

`make test` (full suite, output to a log):

```
640 passed, 3 warnings in 413.02s (0:06:53)
TEST_EXIT=0
```

`make lint`:

```
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ✨ 🍰 ✨
147 files would be left unchanged.
```

`make verify-evidence`:

```
.venv/bin/python -c "from efb import evidence; p = evidence.verify(); print('evidence OK' if not p else chr(10).join(p)); raise SystemExit(1 if p else 0)"
evidence OK
```

### Headline numbers, file and key

- day 1 2026-09-22, end date 2026-11-02: live/clock.json `day_1`, `end_date`
- F10.1b verdict fail, old verdict pass: sprints/E10/RESULTS.json `criteria.F10.1b.verdict`, `revisions.changed.F10.1b.old.verdict`
- F10.1b median gap 0.296266: sprints/E10/RESULTS.json `criteria.F10.1b.stored_numbers.expected_mdd_relative_gap`
- idio share after FMP 1.0: live/proposals/proposal_2026-09-03.json `idio_share_after_fmp`
- gross 1.0, achieved annual vol 0.0423: live/proposals/proposal_2026-09-03.json `gross`, `achieved_annual_vol`
- universe source raw/spy_holdings/spy_holdings_2026-09-18.parquet: live/proposals/proposal_2026-09-03.json `universe_source`
- factor-neutral IC -0.0031, t -0.51: data/alpha/summary.parquet row `idio_momentum` `neutral_ic_h21_mean`, `neutral_ic_h21_t`
- position cap 0.40, brake 200000: live/guards.py `MAX_POSITION_PCT_OF_NAV`, `MAX_TRADED_NOTIONAL_PER_RUN`

### git diff --stat from base_commit

```
57 files changed, 3051 insertions(+), 296 deletions(-)
```

### Yes or no, each with evidence

1. **Any two rows or two estimators identical?** No. The proposal has 499
   unique tickers; the book is one estimator, XS-v1.
2. **Any exception caught and skipped, or any fallback taken?** No
   exception is caught and skipped. One fallback is taken and counted: the
   SPY universe minus the frozen model leaves 4 names out (BE, DD, ILMN,
   P), stored as `n_excluded` in the proposal manifest.
3. **Any criterion reworded or replaced by a different test?** Yes. F10.1b
   was re-registered against F10.1's threshold, by the owner's approval.
   F11.1 to F11.3 are byte-identical to the roadmap, checked by
   tests/test_e11_results.py.
4. **Any criterion that passes by construction?** No. F11.x are pending;
   F10.1b fails. The idio share of 1.0 after the hedge is by construction
   of the exact FMP hedge, but it is a stored number, not a criterion
   verdict.
5. **Any number that moved by a factor of 10 or more?** Yes. F10.1b's gap
   moved from about 296% to 26%, roughly an 11x change, from the horizon
   fix. Old and new values are both in the revisions block.
6. **Any stored number typed into a notebook?** No. No notebook was
   touched in this task.
7. **Any earlier verdict changed?** Yes. F10.1b pass to fail, by the
   owner's approval. No other verdict moved.

### Anything decided that the reviewer might disagree with

The E8 constraint set is treated as satisfied by the exact FMP hedge plus
gross and net caps, rather than re-running the constrained optimizer over
the Procedure 6.3 book. The traded-notional brake is restated from 16k to
200k. Day 1 is 2026-09-22 while the proposal is built on the frozen close
2026-09-03. The loop runs dry because the live Alpaca path needs
`alpaca-py` and paper keys that are not available to me.

