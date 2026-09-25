# Sprint E11 pre-deploy, item 3: the book's breadth, and the full book's, with no unqualified `n_eff`

**What was wrong.** The proposal manifest carried one `n_eff`, and it was the
**full 499-name book's** number before the floor: 157.33 at the 2026-09-21 close,
beside a book whose own breadth is 70.59. `scripts/run_live_daily.py::store_proposal`
copied it into `efb.proposals`, and both pages rendered it as "effective breadth
(n_eff)". On the page the owner watches for two evenings, that number meant more
than it said.

**The stored names are now qualified, and nothing writes the unqualified one.**

| name | what it is |
| --- | --- |
| `n_eff_kept` | the book that trades: after the floor, after the renormalization to gross 1.0 |
| `n_eff_full_book` | the full universe book before the floor, reported beside it |

- `live/evening_job.py`: the manifest's unqualified `n_eff` key is gone, and
  `_decomposition`'s internal key is renamed `effective_breadth` so the
  ambiguity cannot come back through a helper. The governing-breadth ratio reads
  the renamed key.
- `scripts/run_live_daily.py::store_proposal` writes both qualified names, and
  `efb.proposals` gains those two columns in place of `n_eff`.
  `live/reconcile.py`'s row column becomes `n_eff_kept`, because that record is
  the book's own.
- `live/sanity.py` stores `n_eff_kept_before/after` and
  `n_eff_full_book_before/after`.
- A grep for the unqualified name across `live/`, `scripts/`, `dashboard/`,
  `efb/` and `tests/` leaves only `live/breadth.py`'s deliberate legacy reader
  (and E8's own sizing-study field, which is a different object in the research
  stack and is untouched).

## The labels, in one place

`live/breadth.py` owns the two labels and the reader both pages use:

```text
BOOK_LABEL      = "the book's effective breadth"
FULL_BOOK_LABEL = "the full 499-name book's, before the floor"
```

- The Render page builds them with `live/dashboard_app.py::_breadth_columns`.
- The research page uses them in D10's book panel, and its construction summary
  metric is relabelled from "n_eff kept" to the book's label.
- `live/construction_table.py` reads the renamed decomposition key, so the E11-F12
  table still builds; its own stored column names (`n_eff_kept`, `n_eff_full`) are
  left alone, because both are already qualified by which book they describe and
  renaming a stored column would mean rebuilding the comparison artifact and
  moving numbers the reviewer has been reading since Part 1R.

**The legacy mapping**, for artifacts stored before this item:
`breadth.full_book_breadth` reads an old `n_eff` as the full book's, and
`breadth.book_breadth` returns `None` for such an artifact rather than showing the
full book's as the book's. `breadth.LEGACY_NOTE` is available for a page to say
so in words, and `breadth.legacy_artifact(record)` is true exactly when the
artifact has the old name and not the new one.

## The regenerated proposals

```text
2026-09-18: book breadth (n_eff_kept) 69.4578 | full book (n_eff_full_book) 146.3238
            recomputed from the stored weights 69.4578
            keys present: ['n_eff_full_book', 'n_eff_kept', 'n_effective']
            unqualified n_eff present: False
2026-09-21: book breadth (n_eff_kept) 70.5921 | full book (n_eff_full_book) 157.3291
            recomputed from the stored weights 70.5921
            unqualified n_eff present: False
```

Both book figures equal the breadth recomputed from the stored weights, which is
the whole point: the number a page shows under "the book's effective breadth" is
the traded book's. The 09-21 book value is the owner-confirmed 70.59.

The two `proposal_*.parquet` files are **unchanged** (they carry weights, not
breadths) and do not appear in this commit; only the manifests moved.

## Tests

Five new in `tests/test_e11_breadth.py`:

1. the two names return the two books, and neither label contains `n_eff`;
2. a legacy artifact maps to the full book only, `book_breadth` is `None` for it,
   the note is `LEGACY_NOTE`, and an empty record invents nothing;
3. the stored proposals carry both names, no unqualified one, and
   `n_eff_kept` equals the breadth recomputed from the stored weights, at both
   closes;
4. the Render page's two columns are the two labels, and its book figure equals
   the traded book's recomputed breadth while its full-book figure is more than
   one name away from it;
5. the research page's D10 book panel shows the same twice over.

**Four existing test files were edited deliberately**, all of them fixtures whose
stub manifests carried the old key: `tests/test_e11_evening.py` (the internal
decomposition key and the two manifest keys),
`tests/test_e11_sanity.py`, `tests/test_e11_reconcile.py` and
`tests/test_dashboard_d10.py`. No assertion was weakened; each was retargeted at
the renamed field, and the d10 stub gained the full-book number so both labels can
be checked.

## Verification

Per step, the selection is every test touching what changed: the breadth names,
both pages, the runner, the sanity gate and the construction table.

```text
$ .venv/bin/python -m pytest tests/test_e11_breadth.py tests/test_e11_evening.py \
    tests/test_e11_sanity.py tests/test_e11_reconcile.py tests/test_dashboard_d10.py \
    tests/test_e11_render.py tests/test_e11_notify.py tests/test_e11_staleness.py \
    tests/test_run_live_daily.py -q --tb=short
103 passed, 1 skipped in 25.11s

$ .venv/bin/python -m pytest tests/test_construction_table.py tests/test_e11_breadth.py -q
12 passed in 103.98s (0:01:43)
```

The full suite is required here because two stored artifacts were regenerated
(standard 21, point 3).

```text
$ make test > /tmp/full5.log 2>&1; echo "EXIT=$?"
$ tail -c 300 /tmp/full5.log

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
786 passed, 1 skipped, 3 warnings in 599.86s (0:09:59)
EXIT=0
```

The previous full run, at Part 5's commit, was 774 passed, 1 skipped (775
collected). This one collects 787: item 1's 3 universe tests, item 2's 4 catch-up
tests and this item's 5 breadth tests, with nothing lost.

`make lint`, exit 0:

```text
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ... 172 files would be left unchanged.
```

`make verify-evidence`, exit 0:

```text
evidence OK
```

### Headline numbers, file and key

| number | file and key |
| --- | --- |
| the two stored names | `live/proposals/proposal_2026-09-21.json`, `n_eff_kept` and `n_eff_full_book` |
| 70.5921 and 157.3291 at 09-21, 69.4578 and 146.3238 at 09-18 | the same files, read directly |
| the book's number equals the recomputed breadth | the pasted block above, from `proposal_*.parquet` |
| no unqualified `n_eff` is written | `live/evening_job.py` (manifest), `scripts/run_live_daily.py:133` (row), `live/reconcile.py:82` |
| the legacy mapping | `live/breadth.py::full_book_breadth`, `book_breadth`, `legacy_artifact` |
| the two labels | `live/breadth.py::BOOK_LABEL`, `FULL_BOOK_LABEL`; used by `live/dashboard_app.py::_breadth_columns` and `dashboard/tabs/d10_book.py` |
| two columns in place of one | `live/supabase_schema.sql`, `efb.proposals`; `efb.reconciliation` carries `n_eff_kept` |
| 5 tests | `tests/test_e11_breadth.py` |

### git diff --stat from `base_commit` (4048b97)

This item's own files, from item 2's commit `6c1bbc2`, with
`git add -N live/breadth.py tests/test_e11_breadth.py` first so the new files
appear:

```text
$ git diff --stat 6c1bbc2 -- handoff/REPORT.md live/breadth.py live/evening_job.py \
    live/reconcile.py live/sanity.py live/construction_table.py \
    live/dashboard_app.py dashboard/tabs/d10_book.py live/supabase_schema.sql \
    scripts/run_live_daily.py live/proposals tests/test_e11_breadth.py \
    tests/test_e11_evening.py tests/test_e11_sanity.py tests/test_e11_reconcile.py \
    tests/test_dashboard_d10.py
 dashboard/tabs/d10_book.py              |  11 +-
 handoff/REPORT.md                       | 308 ++++++++++++++++++------------
 live/breadth.py                         |  65 ++++++++
 live/construction_table.py              |   4 +-
 live/dashboard_app.py                   |  18 ++-
 live/evening_job.py                     |  10 +-
 live/proposals/proposal_2026-09-18.json |   7 +-
 live/proposals/proposal_2026-09-21.json |   7 +-
 live/reconcile.py                       |   4 +-
 live/sanity.py                          |   6 +-
 live/supabase_schema.sql                |   5 +-
 scripts/run_live_daily.py               |   3 +-
 tests/test_dashboard_d10.py             |   3 +-
 tests/test_e11_breadth.py               |  92 +++++++++++
 tests/test_e11_evening.py               |   5 +-
 tests/test_e11_reconcile.py             |   2 +-
 tests/test_e11_sanity.py                |   2 +-
 17 files changed, 411 insertions(+), 141 deletions(-)
```

The two proposal parquets are absent from that list: the books did not move, only
their manifests' field names. From the task's `base_commit` (4048b97), which
carries items 1 and 2 as well:

```text
$ git diff --stat 4048b97
 ...
 24 files changed, 1316 insertions(+), 298 deletions(-)
```

### Yes or no, each with evidence

1. **Any two rows or two estimators identical.** No. The two books differ in both
   numbers at both closes (70.5921 against 157.3291, 69.4578 against 146.3238),
   and test 4 asserts the page's two figures are more than one name apart.
2. **Any exception caught and skipped, or fallback taken, with counts.** Yes, one,
   and it is the item's own subject: the legacy read. `full_book_breadth` falls
   back to the old `n_eff` for an artifact that predates the split, and it can
   only ever produce the full book's number; `book_breadth` refuses the fallback
   and returns `None`. Test 2 asserts both, and the note is exposed rather than
   swallowed.
3. **Any criterion reworded or replaced by a different test.** No `RESULTS.json`
   criterion, threshold or stored string was touched. Four existing test files'
   fixture dictionaries were renamed as listed above, and the d10 stub gained a
   field; no stored score moved. The construction table's own column names are
   deliberately unchanged, and the artifact is byte-identical in this commit.
4. **Any criterion that passes by construction.** One, declared: the regenerated
   manifests' `n_eff_kept` comes from the same `kept_decomposition` whose weights
   are written to the parquet, so the test comparing the manifest's number with
   the recomputed breadth proves the two agree, not that the breadth formula is
   the right one. The formula is E8's, unchanged by this item, and its own
   criterion stands.
5. **Any number that moved by a factor of 10 or more from its previous stored
   value.** No. `n_eff_kept` equals the number the manifest already carried under
   `n_eff_kept`, and `n_eff_full_book` equals the old `n_eff`: 157.33 and 70.59
   are the same numbers, now named for what they are. The 09-18 numbers moved
   only by the universe fields item 1 changed, and those weights did not move.
6. **Any stored number typed into a notebook.** No notebook was opened, edited or
   executed.
7. **Any earlier verdict changed.** No. Part 5's books, Guard 1's derivation and
   the owner's confirmed numbers all stand; this item renames fields so the page
   cannot mislead about the book the owner confirmed.

### Anything decided that the reviewer might disagree with

**The construction table's columns keep their names.** `n_eff_kept` and
`n_eff_full` inside `live/construction_table.parquet` are both qualified by which
book they describe, so the reviewer's complaint (an unqualified `n_eff` read as
the book's) does not apply to them, and renaming a stored column would rebuild the
comparison artifact and touch numbers the reviewer has read since Part 1R. If the
reviewer wants `n_eff_full_book` there too, it is a table rebuild plus two test
edits.

**The research dashboard now imports `live.breadth`.** The alternative was a
second copy of the labels in `dashboard/tabs/d10_book.py`, which is how
`_construction_label` ended up duplicated. One shared, tested reader is the
reason the two pages cannot disagree, and `live/breadth.py` imports nothing but
`__future__` and typing.
