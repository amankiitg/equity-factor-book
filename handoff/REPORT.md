# Sprint E11, Part 5: the proposals regenerated on the confirmed book, and Guard 1 re-derived

**What this part does.** The owner's confirmed book is the 150-name drop-then-admit
share-only book. This part regenerates the stored dry-run proposals on it,
re-derives Guard 1 from the regenerated final weights, and states the headroom
against the book's own close-to-close movement.

**It also found a defect and fixed it.** The 2026-09-03 close cannot be re-priced:
the price panel has no close for APH that day, and the size path would have turned
that into a share count nobody asked for. The run now refuses and names the name.
The details are below; the two closes that do re-price cover Guard 1, and the one
that does not is reported rather than patched silently.

## The regenerated proposals

Built with `live.evening_job.build_proposal(as_of=<close>, store=True)`, the same
call a live run makes, then read back from the stored artifacts. That argument
writes the dated artifacts under `live/proposals/`, which is what "the stored
proposals" means here; the `efb.proposals` and `efb.positions` rows are written by
`scripts/run_live_daily.py::store_proposal` on a real run, and the local fallback
is gitignored, so no database row is part of this commit:

| close | names kept | dropped | n_eff on the final weights | largest final weight | rounding error | code |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-18 | 155 | 344 | 69.4578 | MRNA 6.2615% ($62,615) | 0.7117% | `ae1c686` |
| 2026-09-21 | 150 | 349 | 70.5921 | MU 5.3463% ($53,463) | 0.6890% | `ae1c686` |

**The 2026-09-21 row is the owner's confirmed book, to the last digit.** The
construction table's share-only row reads `n_kept=150 n_eff=70.592135
err=0.006890189 maxw=0.053463`, and the owner confirmed 150 names, n_eff 70.59,
total error 0.689%, max weight 5.35%. The regenerated artifact now carries the
same numbers, so the book that trades is the book that was confirmed. Both
proposals are `construction: share_only`, share floor 20, no dollar floor,
`floor_iterated: true`, `floor_rule: drop_then_admit`.

**One naming hazard worth the reviewer's decision.** The proposal manifest's
`n_eff` field is not the final book's. At the 2026-09-21 close it stores 157.33,
because it is `full_decomposition["n_eff"]` (`live/evening_job.py:141` computes
it, `:965` assigns it): the effective breadth of the full 499-name book before the
floor is enforced and before the renormalization to gross 1.0. The final book's
number is in the same manifest, correctly labelled, as **`n_eff_kept` = 70.5921**
(`:992`, beside `n_eff_full` at `:991` and a ratio at `:1007`). Both numbers are
right about different objects, and the one that lacks a qualifier is the wrong
one for a book: `scripts/run_live_daily.py::store_proposal` stores the unqualified
`n_eff` into the `proposals` table, so the dashboard shows 157.33 beside a book
whose breadth is 70.59. I did not change it: renaming a stored field or pointing
the table at `n_eff_kept` changes what a stored artifact means and what the page
reports, which is the reviewer's call, not a Part 5 side effect. Flagging it with
both numbers and the lines.

## The 2026-09-03 close cannot be re-priced, and the reason was a live defect

Regenerating that close first failed with `ValueError: cannot convert float NaN to
integer` inside `live/alpaca.py:144`. The cause is in the data and in how the
pricing path treated it:

- **APH has no close price** on 2026-08-28, 09-01, 09-02 and 09-03 (NaN close,
  NaN adj_close), and its close **halves** from 158.78 on 2026-08-27 to 82.78 on
  2026-09-04, which is a 2:1 split. Four of APH's 4,204 rows are NaN. APH is in
  the SPY archive and in the cleaned panel, so it is a legitimate universe name.
- At that close the kept set contains APH. `_close_prices` returns it with a NaN.
  `sized_kept_weights` built `prices = [close.get(name, 0.0)]`, and `kept_shares`
  computes `floor(|w| * nav / max(price, 1e-12))`. With a NaN price that division
  is undefined and `.astype(int)` produces an integer nobody asked for; with a
  missing price the 0.0 default becomes a 1e-12 denominator and produces an
  astronomically large share count. Neither raises.

**The fix, one guard where the price vector is built:**

```text
$ .venv/bin/python -c "from live import evening_job; evening_job.build_proposal(as_of=pd.Timestamp('2026-09-03'), store=False)"
ValueError: no usable close price for APH at the proposal close: a kept name with
no price cannot be quantized to whole shares, so the run stops instead of pricing
it
```

`live/evening_job.py::usable_prices` refuses a NaN, a non-positive or an absent
price and names up to five offending tickers. It sits in `sized_kept_weights`,
which is the single source of the price vector for both the floor search and the
final book, so one guard covers every path. Three tests pin it: a NaN price, a
missing key and a zero price all stop the run and name the names, and the happy
path is unchanged.

**What that means for a live run.** A close with such a name now stops the run
loudly: no proposal row, no order, `run_status` at `error`, and Part 3b's
notification carries the line above, so the owner reads the ticker. Both closes
that re-price today are unaffected, so the live path as it stands prices the book
it should. The 2026-09-03 close is seed data (it is not after `SEED_CUTOFF`), so
the appendix will never repair it and the stored `proposal_2026-09-03` artifact
still carries the superseded construction's book. Nothing was deleted or
rewritten there.

## Guard 1, re-derived over the closes the loop can re-price

`MAX_POSITION_PCT_OF_NAV` stays **0.10**, and the derivation behind it moved to
the confirmed book:

| quantity | value |
| --- | --- |
| largest final weight, 2026-09-18 | MRNA 0.062615 = 6.2615% of NAV = $62,615 |
| largest final weight, 2026-09-21 | MU 0.053463 = 5.3463% of NAV = $53,463 |
| the largest legitimate target | 6.2615% of NAV |
| cap 0.10 clears it with | **1.5971x** headroom (0.0626 -> 0.10) |
| a 10x order on the largest name | 0.6261 of NAV, which trips the cap |
| close-to-close movement of the largest weight | 0.915 pp, $9,152 |
| clearance above the largest weight | 3.74 pp, so the cap is not inside the movement |

The movement, in per-name detail, because the largest name changed between the two
closes: **MRNA** 6.2615% to 4.5447% (-1.717 pp, -$17,168), **MU** 4.8854% to
5.3463% (+0.461 pp, +$4,609). The cap clears the largest weight by 3.74 pp while
the largest weight itself moved 0.92 pp between closes, so 0.10 is not sitting
inside the book's own daily variation. That is the answer to the reviewer's
question, and it is 1.60x rather than the previous 1.54x because the confirmed
book is broader than the 119-name book the old derivation used.

Both the comment in `live/guards.py` and
`tests/test_e11_guards.py::test_a_ten_times_order_on_the_largest_target_trips_the_cap`
now carry this arithmetic, with the source file and the 09-03 exclusion named.

## What could not be verified

- **The 2026-09-03 close.** It is one of the three closes the loop has run, and it
  cannot be re-priced, so Guard 1's "every close" is two closes plus the reason the
  third is missing. I did not substitute a neighbouring close or drop APH from the
  universe to make the number look complete: dropping a name is a book-level rule
  the owner would have to choose, and it would change every historical book.
- **The failure is not repaired at the source.** The 211 names with a NaN close in
  the panel (ABK, ABMD, ABS, ACAS, ACE and the rest, mostly delisted) are still
  there, and the pipeline's flagging keeps the names in the cleaned panel while
  dropping their NaN rows. Any future close where a *kept* name has no price stops
  the run; that is now loud, but the data gap is not fixed, and fixing it belongs
  to the research stack, not to a live part.
- **The dashboard's `n_eff`.** Reported above with both numbers (`157.33` against
  `n_eff_kept` 70.5921); not changed.

## Tests

Three new tests in `tests/test_e11_evening.py` for the price guard (NaN, missing,
zero, plus the passing control), and **two existing tests updated deliberately**:

- `tests/test_e11_guards.py`'s cap test: the largest legitimate target moves from
  0.065 to 0.062615 with the source named, and it now asserts the 1.5971x headroom
  and that the cap clears the observed movement.
- `tests/test_e11_render.py`'s regenerated-proposal test: it asserted the old
  book's `n_kept == 119` and `n_dropped == 380`, and now asserts the confirmed
  book's `150` and `349` plus `floor_rule == "drop_then_admit"`. The assertion's
  form is unchanged; the artifact it reads was regenerated, which is this part's
  mandate.

The `tests/test_e11_staleness.py` and `tests/test_e11_notify.py` suites are
untouched and green.

## Verification

Per step, the selection is every test touching what changed: the regenerated
artifacts, the guard, the D10 header and the Render page.

```text
$ .venv/bin/python -m pytest tests/test_e11_guards.py tests/test_e11_evening.py \
    tests/test_dashboard_d10.py tests/test_e11_render.py tests/test_dashboard_app.py \
    -q --tb=short
65 passed, 1 skipped in 27.75s
```

The full suite is required at this step because an artifact was rebuilt (standard
21, point 3), and because this is the state the task is set `done` on.

```text
$ make test > /tmp/full4.log 2>&1; echo "EXIT=$?"
$ tail -c 300 /tmp/full4.log

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
774 passed, 1 skipped, 3 warnings in 599.11s (0:09:59)
EXIT=0
$ .venv/bin/python -m pytest tests/ -q --collect-only | tail -1
775 tests collected in 2.31s
```

The previous full run, at Part 3's commit, was `751 passed, 1 skipped` (752
collected); this one collects 775, so the count grew by 23 and shrank by nothing.
The 23 are Part 3b's 11 notification tests plus its 1 credential-check test,
Part 4's 8 deploy tests, and this part's 3 price-guard tests.

`make lint`, exit 0:

```text
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ... 170 files would be left unchanged.
```

`make verify-evidence`, exit 0:

```text
evidence OK
```

### Headline numbers, file and key

| number | file and key |
| --- | --- |
| 150 names, n_eff 70.5921, max MU 5.3463%, error 0.6890% | `live/proposals/proposal_2026-09-21.parquet` and its manifest |
| 155 names, n_eff 69.4578, max MRNA 6.2615%, error 0.7117% | `live/proposals/proposal_2026-09-18.parquet` and its manifest |
| the same numbers on the floor row | `live/construction_table.parquet`, row `share_only_20shares` |
| Guard 1 at 0.10, 1.5971x headroom, 10x trips at 0.6261 | `live/guards.py::MAX_POSITION_PCT_OF_NAV` and its comment |
| the movement, 0.915 pp / $9,152 | the two stored books, tabulated above |
| APH: NaN on 2026-08-28, 09-01, 09-02, 09-03, halving on 09-04 | `data/raw/prices.parquet`, measured |
| the refusal message naming APH | `live/evening_job.py::usable_prices`, reproduced above |
| 211 NaN closes at the 09-03 close, 206 at 09-18 and 09-21 | `data/raw/prices.parquet`, measured |
| the manifest carries both: `n_eff` 157.33 (full) and `n_eff_kept` 70.5921 (final) | `live/proposals/proposal_2026-09-21.json`, values read directly; fields assigned at `live/evening_job.py:965` and `:992` |

### git diff --stat from `base_commit` (dd41d9b)

This part's own files, from Part 4's commit `ae1c686`:

```text
$ git diff --stat ae1c686 -- handoff/REPORT.md live/evening_job.py live/guards.py \
    live/proposals tests/test_e11_evening.py tests/test_e11_guards.py \
    tests/test_e11_render.py
 handoff/REPORT.md                          | 565 +++++++++++++----------------
 live/evening_job.py                        |  29 +-
 live/guards.py                             |  25 +-
 live/proposals/proposal_2026-09-18.json    |  83 +++--
 live/proposals/proposal_2026-09-18.parquet | Bin 7111 -> 8458 bytes
 live/proposals/proposal_2026-09-21.json    |  87 ++---
 live/proposals/proposal_2026-09-21.parquet | Bin 7195 -> 8283 bytes
 tests/test_e11_evening.py                  |  51 +++
 tests/test_e11_guards.py                   |  21 +-
 tests/test_e11_render.py                   |  10 +-
 10 files changed, 462 insertions(+), 409 deletions(-)
```

From the revision's `base_commit` (dd41d9b), which also carries Parts 2 to 4 and
the reviewer's `ef67024`:

```text
$ git diff --stat dd41d9b
 ...
 30 files changed, 3414 insertions(+), 479 deletions(-)
```

The two `.parquet` files are the regenerated books themselves, 8,458 and 8,283
bytes against 7,111 and 7,195. Nothing else in the repository changed: no research
artifact, no construction table, no notebook.

### Yes or no, each with evidence

1. **Any two rows or two estimators identical.** No. The two regenerated books
   differ (155 names against 150, n_eff 69.46 against 70.59, and the largest name
   changes from MRNA to MU), which is the sanity gate's requirement that two
   consecutive closes produce different proposals, now true of the confirmed book
   as well.
2. **Any exception caught and skipped, or fallback taken, with counts.** Yes, one
   new one, and it is the opposite of a skip: `usable_prices` raises instead of
   silently producing a share count. The exception is not caught anywhere in the
   live path, so it stops the run, writes the `error` row and is notified (Part
   3b). No other exception was added or suppressed.
3. **Any criterion reworded or replaced by a different test.** No `RESULTS.json`
   criterion, threshold or stored string was touched. **Two tests were edited
   deliberately**, both listed above: the guard's cap test (the re-derivation this
   part was asked for) and the Render page's regenerated-proposal counts (the
   artifact's own change from 119 to 150 names). Both keep their assertions' form
   and make them stricter, not weaker.
4. **Any criterion that passes by construction.** One, declared: the reconciliation
   between the regenerated proposal and the construction table's share-only row is
   strong evidence that the artifact that trades is the confirmed book, but both
   numbers come from the same `enforce_floor_by_drop_then_admit` code, so the test
   proves the artifact carries that code's output, not that the rule is right. The
   rule's own checks are Part 1R's five, which stand.
5. **Any number that moved by a factor of 10 or more from its previous stored
   value.** No. The stored proposal's `n_kept` moved 119 -> 150, n_eff on the final
   weights 58.82 -> 70.59, and the largest weight 0.0596 -> 0.0535; the guard's
   headroom moved 1.54x -> 1.60x. No factor of ten anywhere.
6. **Any stored number typed into a notebook.** No notebook was opened, edited or
   executed.
7. **Any earlier verdict changed.** No. The 150-name book was already the owner's
   confirmed choice; this part makes the stored artifacts match it. `dry_run` is
   still `true` and I have not flipped it. The E11-F12 floor verdicts are
   untouched.

### Anything decided that the reviewer might disagree with

**I refused the 2026-09-03 close rather than making it re-price.** The alternative
was to drop APH (or names like it) from the universe for that close, which would
have produced a book the owner never chose and would have changed the guard's
"every close" answer by changing the population. I chose the refusal, wrote the
name into the message, and left the stored 09-03 artifact as the superseded book
it already was.

**The price guard raises rather than substituting a price.** A stale or carried
price would let the run continue and price a share count on data the panel does
not have. The project's standing rule is that a failed run beats a wrong book, so
the guard refuses and names the ticker.

**I did not rename the manifest's `n_eff`.** The mismatch between it (157.33) and
the final book's (70.59) is real and now documented with lines. Renaming it would
change what a stored artifact means and would ripple into the dashboard, the
`proposals` table and the D10 header, so it is a decision rather than a fix.
