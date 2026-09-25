# Sprint E11 pre-deploy, item 1: the universe is clamped to the close it prices

**What was wrong.** `live/evening_job.py::load_spy_universe` took the newest SPY
archive file on disk, whatever date it carried. `build_proposal` loaded the
universe **before** it worked out which close it was pricing, so a build for an
older close read a holdings snapshot filed after it. The stored 09-18 proposal
recorded it:

```text
2026-09-18 {'as_of': '2026-09-18', 'universe_source':
  'raw/spy_holdings/spy_holdings_2026-09-21.parquet', 'universe_as_of': '2026-09-21', ...}
```

Three sessions of look-ahead in the artifact's own fields.

**The fix, in the same shape `_input_as_of` already uses for everything else.**

- `load_spy_universe(data_root, as_of=None)` returns the newest archive dated
  **on or before** the close, and keeps the newest when no close is given, which
  is the live path's own answer. The archive's date is the one in its file name,
  which `spy.archive_snapshot` stamps from the `as_of` it fetched, so the name
  is the snapshot date by construction.
- `build_proposal` now computes `as_of_ts` first (`wide.index.max()` when no
  close is given, else the close asked for) and passes it to the loader. The
  comment says why: a holdings snapshot filed after the close must not inform
  the book priced on it.
- **Two refusals, both loud**, because a look-ahead universe is a wrong book and
  not a parse to patch. A close with no archive on or before it is refused:

  ```text
  ValueError: no SPY archive dated on or before 2026-09-03: the newest is
  spy_holdings_2026-09-21.parquet and it postdates the close being priced
  ```

  and an archive whose name carries no date is refused rather than skipped
  quietly (`SPY archive spy_holdings_backup.parquet does not carry a date`). The
  existing live-universe-seam check is untouched.

`live/construction_table.py` still calls the loader with no close, which is
correct for it: the table is a comparison of constructions on the latest data,
not a book priced for a session, and it should keep reading the newest archive.

## The shift audit, three tests in `tests/test_e11_evening.py`

1. `test_load_spy_universe_clamps_to_the_close`: with 09-18 and 09-21 archives on
   disk, a close of 2026-09-18 and a close of 2026-09-19 both return the 09-18
   file, and no close returns 09-21.
2. `test_a_universe_that_postdates_the_close_is_refused`: only the 09-21 archive
   exists and the close is 2026-09-18, so the loader raises
   `postdates the close being priced`.
3. `test_an_archive_name_without_a_date_is_refused`.

## The regenerated 09-18 proposal: the book did not change

```text
universe now: raw/spy_holdings/spy_holdings_2026-09-18.parquet 2026-09-18
before: 155 names n_eff 69.4578 max 0.062615 (MRNA) n_excluded None
after:  155 names n_eff 69.4578 max 0.062615 (MRNA) n_excluded 4 n_dropped 344
names in both: 155 | only before: [] | only after: []
largest weight change: 0.0 at ADM
total absolute weight change (turnover): 0.0
```

**Zero, and the artifact says so itself: the regenerated
`proposal_2026-09-18.parquet` is byte-identical and does not appear in this
commit's diff at all.** Only the manifest changed, ten lines of it, all of them
the universe fields. The reason is measurable rather than lucky: the two archives
carry the **same 503 tickers** (`identical ticker sets: True`, `only 09-18: []`,
`only 09-21: []`), so the universe the book was priced on is the same set either
way. What changed is the truthfulness of the artifact: it now names the archive
that existed at its close. The weights, breadth and largest position are
unchanged, which is why this item needed no re-derivation of Guard 1 and no
change to the confirmed book.

**One consequence worth carrying into item 4a.** The 2026-09-03 close is now
refused for a *second*, independent reason: there is no SPY archive dated on or
before it, so the build stops at the universe before it ever reaches the APH
price gap Part 5 found. Both refusals are correct, and the 09-03 close stays
un-repriced for the deploy's purposes.

## Verification

Per step, the selection is every test touching what changed: the loader, its
caller and the universe tests.

```text
$ .venv/bin/python -m pytest tests/test_e11_evening.py -q --tb=short
31 passed in 21.93s

$ make lint
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ... 170 files would be left unchanged.
```

The full suite is not required at this step: no `efb/` module changed, and
although the 09-18 proposal artifact was rebuilt, its weights are byte-identical
apart from the universe fields, so no stored number moved. The `make test` run
for this task lands with item 4b (the store), which changes `live/store.py` for
every consumer; the report says so there.

### Headline numbers, file and key

| number | file and key |
| --- | --- |
| the universe is the newest archive on or before the close | `live/evening_job.py::load_spy_universe`, `as_of` argument |
| the close is computed before the universe is loaded | `live/evening_job.py::build_proposal`, `as_of_ts` above the loader call |
| the 09-18 proposal now names the 09-18 archive | `live/proposals/proposal_2026-09-18.json`, `universe_source` / `universe_as_of` |
| 155 names, n_eff 69.4578, max MRNA 0.062615, turnover 0.0 | the before/after block above, read from `proposal_2026-09-18.parquet` |
| the two archives hold the same 503 tickers | `data/raw/spy_holdings/spy_holdings_2026-09-18.parquet` and `..._2026-09-21.parquet`, measured |
| 3 new tests | `tests/test_e11_evening.py`, the three `load_spy_universe` tests |

### git diff --stat from `base_commit` (4048b97)

This item's own files, from the in-progress commit `8196e43`:

```text
$ git diff --stat 8196e43 -- handoff/REPORT.md live/evening_job.py \
    live/proposals/proposal_2026-09-18.json \
    live/proposals/proposal_2026-09-18.parquet tests/test_e11_evening.py
 handoff/REPORT.md                       | 375 ++++++++++----------------------
 live/evening_job.py                     |  53 ++++-
 live/proposals/proposal_2026-09-18.json |  10 +-
 tests/test_e11_evening.py               |  36 ++++
 4 files changed, 208 insertions(+), 266 deletions(-)
```

The parquet is named in the command and absent from the output: the book did not
move. From the task's `base_commit` (4048b97), which carries only TASK.md's status
change before this:

```text
$ git diff --stat 4048b97
 ...
 7 files changed, 888 insertions(+), 286 deletions(-)
```

### Yes or no, each with evidence

1. **Any two rows or two estimators identical.** No. The 09-18 and 09-21 books
   still differ (155 names against 150, n_eff 69.46 against 70.59, largest MRNA
   against MU). Within the 09-18 close, the before and after books are
   identical, which is the finding above rather than a defect.
2. **Any exception caught and skipped, or fallback taken, with counts.** No new
   catch. The item removes a silent fallback rather than adding one: the universe
   was quietly served a later file, and now a missing archive on or before the
   close raises. No exception is swallowed.
3. **Any criterion reworded or replaced by a different test.** No stored
   criterion was touched and no existing test was edited: the three tests are
   added to `tests/test_e11_evening.py` and the three earlier loader tests still
   pass unchanged.
4. **Any criterion that passes by construction.** One, declared: the clamp is
   tested on synthetic archives under `tmp_path`, so it proves the selection
   logic, not that the real `data/raw/spy_holdings/` directory holds the right
   files. The real directory's effect is shown separately, by the regenerated
   artifact's `universe_source` and by the 09-03 refusal, and both are pasted
   above.
5. **Any number that moved by a factor of 10 or more from its previous stored
   value.** No. The regenerated proposal's universe fields changed and nothing
   numeric did: n_kept 155, n_eff 69.4578, max weight 0.062615, turnover 0.0.
6. **Any stored number typed into a notebook.** No notebook was opened, edited
   or executed.
7. **Any earlier verdict changed.** No. Part 5's book, Guard 1 and the 09-03
   refusal all stand; this item adds a second refusal reason to the same close
   and leaves the two re-priceable closes' books untouched.

### Anything decided that the reviewer might disagree with

**The construction table keeps reading the newest archive.** It is a comparison
artifact over the latest data rather than a proposal for a session, so clamping
it would change what it measures without protecting anything. If the reviewer
wants the table clamped too, it is the same one-argument change at
`live/construction_table.py:67`, and it would re-run the whole table.
