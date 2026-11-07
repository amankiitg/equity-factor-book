# Owner fix: attribution bias statistic must never fail the evening step

**Fix in code, not yet applied live.** The 2026-11-06 evening email read
"Attribution: the step failed and the page's attribution section is not being
written (ValueError: a bias statistic needs at least 30 observations)". The run had
been clean on 2026-11-05.

## What is wrong

`efb/eval_risk.py::bias_statistics` raises when it has fewer than 30 **finite**
observations. `efb/attribution.py::_with_risk_lines` guards that call with the
**raw** count of z-scores (`len(z) >= 30`), and a session with no stored forecast
enters `z` as a NaN. On 2026-11-06 the live book reached its 30th session while
three sessions carried no forecast, so the raw guard passed, `bias_statistics` was
handed 27 finite observations, and it raised. The exception propagated out of
`restate_risk_lines` and failed the whole attribution step.

The raise and the mismatched guard are old: `bias_statistics` has raised below 30
since `30b1a36` (2026-09-20) and the raw-count guard since `2166388`
(2026-09-26). No 2026-11-05 merge touched either; the trigger was the 30th session
being attributed on 2026-11-06.

## The fix

- `efb/attribution.py::_with_risk_lines` now counts **finite** z-scores, exactly as
  `bias_statistics` does, and below 30 writes the sentence
  `not enough data yet (N of 30)` instead of a number. The statistic can no longer
  raise the attribution step, and the rest of the row (realized volatility and its
  ratio) is still written.
- `live/attribution_job.py` no longer assumes a stored number is always a float:
  `_shown` renders the sentence, and `_same_number` treats a null and a NaN as the
  same absence so the restatement stays idempotent.
- `live/supabase_schema.sql` changes `bias_statistic` from `double precision` to
  `text`, with `docs/migrations/e12_attribution_bias_text.sql` to apply by hand and
  its check beside it.

## Tests

`tests/test_attribution_risk_lines.py` gains three cases: 28 observations report
"not enough data yet (28 of 30)", 30 report a number, and 30 raw sessions with three
missing forecasts report "not enough data yet (27 of 30)" without raising.

## Back-fill

The next evening already back-fills the missed day on its own: the attribution job's
work list is "the sessions with a book and no row", and
`restate_risk_lines` is a whole-series pass, so 2026-11-06's risk lines are
recomputed the next run. The contract is pinned by
`tests/test_e12_attribution_job.py::test_a_stored_book_with_no_row_yet_is_attributed_and_stored`.

## Live verification pending

This agent does not run anything against the real store or broker and never loads
keys. The owner's main agent runs, read-only, and reports:

```bash
# The attribution step's own restatement, dry run over the real store:
python scripts/repair_risk_lines.py
```

A pass looks like: exit 0 and **no** `ValueError: a bias statistic needs at least 30
observations`. The diff shows the recent sessions - 2026-11-06 among them - with a
numeric `realized_vol` and `vol_ratio`, and `bias_statistic` reading
`not enough data yet (N of 30)` (a number once the book has 30 finite sessions).
