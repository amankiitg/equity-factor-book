# Sprint E11, Part 1R: the drop-then-admit rule, and the check that stops it

**The question this run ends on, at the top because the task stops.**

Part 1R's rule is implemented, installed and measured, and it passes every
check on every floor row **except one**: the min $5,000 comparison row keeps 35
names against the 51-name rank margin, so the fifth check fails there. On this
table a $5,000 minimum on a $1m book cannot reach 51 names (the rule's local
maximum is 35, the drop-only count 23, and the $5,000 leg is what makes the row
small), so that row can never satisfy the check, whatever the rule does.

So the question is: **does the 51-name rank margin gate the whole comparison
table, or only the book that trades?** If it gates the table, the min $5,000
row has to be dropped from the check, or from the table. If it gates only the
book, Part 1R is complete and Parts 2 to 5 follow, and the $5,000 row is
reported with its violation as a known property of the row. I did not decide
it: the check list says every floor row, and the same list says the margin is
"the rank margin the owner named when choosing", which is a property of the
chosen book. The two readings disagree, and the pre-registered stop fires under
the first, so this task stops and asks.

The installed book is share-only: **150 names, n_eff 70.592135, total error
0.6890189%, p90 1.8871021%, net 0, worst post-hedge exposure 1.263e-15, idio
share 1.0, zero names below floor.** It passes all five checks, it is 7 names
larger than the one-pass admission set the owner confirmed on (143), and the
re-decide trigger does not fire.

Nothing is deployed. `dry_run` is still `true`. No proposal was regenerated and
Guard 1 was not re-derived, because Part 5 waits on the answer above.

## The rule, as re-specified

`live/evening_job.py` gains `floor_order` (the `|w_i| / max(dollar_floor,
share_floor * price_i)` ordering on the full-book weights, stable), 
`admit_clearing_names` (one admission pass), `enforce_floor_by_drop_then_admit`
(the rule) and `floor_book_violations` (the five checks). `sized_kept_weights`
and `kept_shares` now hold the sizing and share math that `finalize_kept_set`
used to inline, so the search and the book read the same vector from the same
function; `kept_set_clears_floor` is the search's cheap check, measured at
0.0002s against `finalize_kept_set`'s 0.0067s on the full book, and agreeing
with it on 40 random kept sets.

The rule: drop from the full book with `enforce_floor_on_final_weights` to its
fixed point, admit names in the floor ordering while the enlarged set's final
weights still clear every kept name's floor, repeat the admission pass until a
pass admits nothing, then run the drop step once more as a check; if it drops
anything, repeat from the admission. The cycle cap is 10, and at the cap the
function returns `converged` false so the caller reports rather than picking a
cycle. Every floor row converged in **1 cycle**, after 3 or 4 admission passes.

## The book, every floor row

From `live/construction_table.parquet`. "book" is the installed kept set,
"drop" the drop-only count, "one-pass" the owner's confirmed basis (drop plus
one admission pass), "prefix" the superseded E11-F13 rule kept for the record.
All six rows converged in one cycle.

| construction | book | drop | one-pass | prefix | passes | admitted | checks | n_eff | total error | p90 | max weight | net | worst exposure | idio | below floor |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| min $1,500 | 234 | 194 | 222 | 131 | 3 | 40 | ok | 110.712067 | 2.7603160% | 8.0247230% | 4.0408% | 0 | 1.804e-15 | 1.0 | 0 |
| min $2,000 | 189 | 145 | 185 | 131 | 4 | 44 | ok | 95.554202 | 2.3792549% | 6.7577500% | 4.3692% | 0 | 1.166e-15 | 1.0 | 0 |
| min $3,000 | 94 | 72 | 88 | 3 | 3 | 22 | ok | 54.531726 | 1.2962986% | 4.7158405% | 6.1722% | 0 | 1.228e-15 | 1.0 | 0 |
| min $5,000 | 35 | 23 | 32 | 3 | 3 | 12 | **35 names, below the 51 name rank margin** | 19.886236 | 0.5846929% | 1.6406132% | 11.9495% | 0 | 4.014e-15 | 1.0 | 0 |
| two-part, $1,500 + 20sh | 129 | 87 | 124 | 66 | 4 | 42 | ok | 66.216759 | 0.7735140% | 2.1244166% | 5.4499% | 0 | 1.728e-15 | 1.0 | 0 |
| share-only, 20 shares | **150** | 119 | 143 | 16 | 4 | 31 | ok | 70.592135 | 0.6890189% | 1.8871021% | 5.3463% | 0 | 1.263e-15 | 1.0 | 0 |

Reading the row the owner chose: enforcement moved share-only from 119 names
(the drop-only book the reviewer asked the owner not to decide on) to 143 (the
one-pass admission set the owner confirmed on) to **150** (the rule's local
maximum). n_eff moves 58.822271 to 68.521819 to 70.592135, so the rule's extra
7 names add 2.07 of n_eff. Total error and p90 move with the added names:
0.6426% to 0.7767% to 0.6890% and 2.0385% to 1.8515% to 1.8871%.

**By construction, not a check** (Verification item 4): the book is at least as
large as the drop-only set and as the one-pass set, because the rule starts at
the drop-only set and only adds names. The stored columns show it: 234/194,
189/145, 94/72, 35/23, 129/87, 150/119.

**The five checks.** Four hold on every floor row: net dollar 0 of gross
against the 0.01 bound, worst post-hedge exposure from 1.166e-15 to 4.014e-15
against 1e-12, idio share exactly 1.0, and zero names below floor. The fifth,
at least 51 kept names, fails on the min $5,000 row alone, as above.

The live path (`build_proposal`) raises on any violation, so a book that would
trade cannot be built with a failing check. The table records the checks as a
string per row instead of raising, because raising would make the artifact
unbuildable and hide the measurement.

## The re-decide trigger, on these numbers

Pre-registered in E11-F12 and re-run here as Part 1R requires: compare the
enforced share-only book against the enforced min $2,000 book, both on this
rule's numbers, and stop if (a) share-only no longer has both the lower total
error and the lower p90, or (b) any enforced row is better or equal on both
n_eff and total error.

| reading | share-only: n_eff, error, p90 | min $2,000: n_eff, error, p90 | (a) fires | (b) fires |
| --- | --- | --- | --- | --- |
| Part 1R book | 70.592135, 0.6890189%, 1.8871021% | 95.554202, 2.3792549%, 6.7577500% | no | no |

Branch (a): share-only has both the lower error (0.689% against 2.379%) and the
lower p90 (1.887% against 6.758%). Branch (b): the rows with higher n_eff are
min $1,500 (110.712067, error 2.7603160%) and min $2,000 (95.554202, error
2.3792549%), and both carry higher error than share-only; min $3,000
(54.531726), min $5,000 (19.886236) and two-part (66.216759) all have lower
n_eff. Neither branch fires.

For the record, the gap the owner weighed has narrowed again: two-part now sits
at n_eff 66.216759 against share-only's 70.592135, where at the confirmation it
was 64.683243 against 68.521819, and its error is 0.7735140% against 0.6890189%.

## Ordering robustness, measured and not used to select

The same rule, the same floors, the names ordered by `|alpha_i|` descending
instead of `|w_i| / floor_i`. Nothing in the table's selection uses this.

| construction | floor-order names | alpha-order names | floor-order n_eff | alpha-order n_eff | n_eff gap |
| --- | --- | --- | --- | --- | --- |
| min $1,500 | 234 | 225 | 110.712067 | 107.396085 | -2.995% |
| min $2,000 | 189 | 168 | 95.554202 | 88.140760 | -7.758% |
| min $3,000 | 94 | 89 | 54.531726 | 51.537304 | -5.491% |
| min $5,000 | 35 | 35 | 19.886236 | 18.679509 | -6.068% |
| two-part, $1,500 + 20sh | 129 | 112 | 66.216759 | 57.902919 | -12.555% |
| share-only, 20 shares | 150 | 152 | 70.592135 | 66.600370 | **-5.655%** |

On the share-only row the two orders differ by 5.655% in n_eff, under the 10%
the reviewer set for flagging it at the top, so it is not flagged there and is
reported here. Note the direction: the alpha order keeps *two more* names (152
against 150) and still scores 5.655% lower n_eff, so the count and the breadth
do not move together. On the two-part row the order matters enough to cross the
10% line (-12.555%), which is a fact about that comparison row, not about the
book.

## Determinism, and the rule's run time

Determinism is tested on a synthetic book where the answer is arithmetic:
`test_drop_then_admit_is_deterministic` runs the rule twice on the same inputs
and asserts the same kept set and the same search report. The stored artifact is
deterministic too: two consecutive `build_table(store=True)` runs produce
byte-identical parquet, md5 `21cf6707ac5d8375ea6f72c674e2a6d2` both times. The
search's run time is deliberately not a column, because a clock reading would
make the artifact differ on every build.

On the live path the rule takes **0.08895804092753679 seconds** for the
share-only book (1 cycle, 4 admission passes), stored as
`floor_search_seconds` in the proposal manifest, and the whole
`build_proposal` runs in 4.45s locally, so the evening job's cost is unchanged
in any way that matters.

## The pseudoinverse fallback: naming it, and correcting the record

The Part 1 report's Verification item 2 said three fallbacks fire inside the
enforced-book loops, and asked for the rows and passes. Measured by wrapping
`np.linalg.solve` and recording the set size at each raise, with the call index
inside a row's loop being its pass index (one finalize, one hedge call):

| row | pass | names in the kept set at the raise | kept after the loop |
| --- | --- | --- | --- |
| min $1,500 | none | | 194 |
| min $2,000 | none | | 145 |
| min $3,000 | 3 | 72 | 72 |
| min $5,000 | 2 | 27 | 23 |
| min $5,000 | 3 | 23 | 23 |
| two-part, $1,500 + 20sh | none | | 87 |
| share-only, 20 shares | none | | 119 |

So the three are `min_position_3000` pass 3 at 72 names, and
`min_position_5000` pass 2 at 27 names and pass 3 at 23 names. The share-only
row, the book, takes none. Those two rows are the small ones, where a sector
or style column of the 17-wide design has no name in the subset and `X'X` is
singular rather than merely ill-conditioned; the pinv fallback still recovers
the hedge, and both rows reach 1e-15 exposure at the end.

**The earlier report's Verification item 2 answered "no fallback", and that was
wrong.** It was wrong because it counted only the fallbacks in one full
`build_table` run and attributed all 148 of them to the prefix scan's
degenerate small sets, on the strength of a 36-solve build that had already
shown 4 raises. Those 4 are these 3 plus one elsewhere. The books were never
affected, and the correction is the table above.

## What the check stop does and does not block

- The rule, its checks, the robustness measurement, the determinism test, the
  timing and the fallback attribution are done and committed.
- The table and the live path are installed on the rule's book.
- **Not done, and blocked on the question at the top:** Part 5's regeneration of
  the stored proposals and the re-derivation of Guard 1. They are Part 5 work
  and the check that fired is about the book the proposals would be priced on.
- Parts 2 to 4 (the inputs into Postgres, the staleness stop, the notification,
  the corrected deploy steps) do not depend on the book at all. The previous
  revision of this task said to carry on with them while a book question is
  open. I have not started them in this commit, because the stop list says to
  stop; say the word and they follow immediately.

## Verification

### Commands run and their last lines

Per-step selection while the code changed (rule 21), pasted with the command:

```text
$ .venv/bin/python -m pytest tests/test_construction_table.py tests/test_e11_evening.py -q
................................                                         [100%]
32 passed in 119.87s (0:01:59)
```

`make lint`, exit 0:

```text
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
pyproject.toml: note: unused section(s): module = ['alpaca', 'alpaca.trading.*']
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ✨ 🍰 ✨
115 files would be left unchanged.
```

`make test`, the full suite, exit 0:

```text
732 passed, 1 skipped, 3 warnings in 510.38s (0:08:30)
```

The count is 732 against the 727 recorded at `2a9e0b6`. The five added tests are
the fast-check agreement, the local-maximum property, determinism, the cycle
cap, and the check messages. The wall time (510.38s against 759.79s) is not
comparable to the previous run: that one was measured while other heavy scripts
of mine were running against the same machine, so the difference is mostly
contention, not the code. The one real speed change in the rule's favour is that
the floor search now checks a set with `kept_set_clears_floor` at 0.0002s
instead of building the full finalize at 0.0067s.
`make verify-evidence`, exit 0:

```text
.venv/bin/python -c "from efb import evidence; p = evidence.verify(); print('evidence OK' if not p else chr(10).join(p)); raise SystemExit(1 if p else 0)"
evidence OK
```

### Headline numbers, file and key

All from `live/construction_table.parquet`, one row per `construction`, in the
order min $1,500, min $2,000, min $3,000, min $5,000, top_n_150, top_n_200,
two_part, share_only, full_book:

| number | file and key |
| --- | --- |
| the book 234/189/94/35/129/150 | `n_kept` |
| drop-only 194/145/72/23/87/119 | `n_kept_drop_only` |
| one-pass admission 222/185/88/32/124/143 | `n_kept_one_pass_admission` |
| the superseded prefix 131/131/3/3/66/16 | `n_kept_prefix` |
| cycles 1 and passes 3/4/3/3/4/4 | `admit_cycles`, `admit_passes` |
| added names 40/44/22/12/42/31 | `admit_extra` |
| the checks | `floor_book_checks`, "ok" on five rows and the rank-margin message on min $5,000 |
| n_eff 110.712067/95.554202/54.531726/19.886236/66.216759/70.592135 | `n_eff_kept` |
| total error 0.027603160/0.023792549/0.012962986/0.005846929/0.007735140/0.006890189 | `total_gross_error_share_of_nav` |
| p90 0.080247230/0.067577500/0.047158405/0.016406132/0.021244166/0.018871021 | `quant_error_p90_pct_of_target` |
| max weight 0.040408/0.043692/0.061722/0.119495/0.054499/0.053463 | `max_weight_share_of_gross` |
| net 0 on all six | `net_dollar_share_of_gross` |
| worst post-hedge exposure 1.804e-15/1.166e-15/1.228e-15/4.014e-15/1.728e-15/1.263e-15 | `post_hedge_max_abs_exposure` |
| idio share 1.0 on all six, below floor 0 on all six | `post_hedge_idio_share`, `n_below_floor_final` |
| alpha-order names 225/168/89/35/112/152 | `n_kept_alpha_order` |
| alpha-order n_eff 107.396085/88.140760/51.537304/18.679509/57.902919/66.600370 | `n_eff_kept_alpha_order` |
| n_eff gaps -2.995/-7.758/-5.491/-6.068/-12.555/-5.655 percent | `n_eff_alpha_gap_pct` |
| the live path's rule time 0.08895804092753679s | `live/proposals` manifest key `floor_search_seconds`, from `build_proposal(store=False)` |

### git diff --stat from `base_commit` (2a9e0b6)

```text
 handoff/LOG.md                    | 104 ++++++
 handoff/PROJECT_CONTEXT.md        |  24 +-
 handoff/REPORT.md                 | 750 ++++++++++++++------------------------
 handoff/TASK.md                   |  81 ++++-
 live/construction_table.parquet   | Bin 43229 -> 49789 bytes
 live/construction_table.py        | 153 ++++++--
 live/construction_weights.parquet | Bin 33674 -> 36102 bytes
 live/evening_job.py               | 361 +++++++++++++++++--
 tests/test_construction_table.py  |  48 ++-
 tests/test_e11_evening.py         | 224 +++++++++++-
 10 files changed, 1200 insertions(+), 545 deletions(-)
```

This is the diff at the Part 1R commit, measured after it, so it counts this
section. Re-taking it would move the `handoff/REPORT.md` line and both totals by
the size of whatever paragraph replaced this one, which is why the number above
is the one measured and is not re-taken.

`handoff/LOG.md`, `handoff/PROJECT_CONTEXT.md` and the TASK.md part of that
number are the reviewer's and owner's commits `7978caa` and `e0429f2`, which
land between `2a9e0b6` and here; my TASK.md flip is two lines of it.
`live/construction_weights.parquet` changed because the installed book changed:
it now carries the 150-name share-only book where the committed one carried
119.

### Yes or no, each with evidence

1. **Any two rows or two estimators identical.** No. Every floor row differs in
   book count, n_eff, error, p90 and max weight; the closest pair is the
   min $1,500 and min $2,000 **prefix** columns, which are identical for the
   reason recorded in the Part 1 report (same ordering, same stopping `k` of
   131), and the prefix is a recorded superseded rule, not a row's book. The
   min $3,000 and min $5,000 rows also carry identical prefix columns (3 names,
   n_eff 2.240310, error 0.000925, p90 0.005012), again the recorded superseded
   rule; the two rows' books differ (94 against 35).
2. **Any exception caught and skipped, or fallback taken, with counts.** Yes,
   and named in the section above: the pseudoinverse fallback in
   `live/sizing.hedge_exact_robust` fires 3 times in the six drop-only loops,
   on `min_position_3000` pass 3 (72 names) and `min_position_5000` passes 2 and
   3 (27 and 23 names). No exception is swallowed: the fallback returns the
   best achievable hedge and the achieved exposure is reported. The earlier
   report's answer to this item was wrong and said so above.
3. **Any criterion reworded or replaced by a different test.** No. No
   `sprints/E*/RESULTS.json` criterion, threshold or criterion string was
   touched, and no criterion ID was added. The rule change came from the
   reviewer's own Part 1R, not from me.
4. **Any criterion that passes by construction.** Two things, both declared:
   (a) the prefix scan's own validity is by construction and is why the table
   does not store a below-floor column for it; (b) the book being at least as
   large as drop-only is by construction, because the rule starts there and only
   adds names. The reviewer's instruction says not to report (b) as a check and
   to report it here instead, which is what the section above does. The five
   checks are not by construction: the min $5,000 row fails one of them, which
   is the point of the check existing.
5. **Any number that moved by a factor of 10 or more from its previous stored
   value.** No. The book columns are new; the two superseded counts
   (`n_kept_drop_only`, `n_kept_prefix`) and the prefix metric columns are
   unchanged from the Part 1 table, and every other column that existed before
   this commit is unchanged, which the diff check in the Part 1 report
   established column by column.
6. **Any stored number typed into a notebook.** No. No notebook was opened,
   edited or executed.
7. **Any earlier verdict changed.** No. Every verdict in `sprints/E*/RESULTS.json`
   and the registry is untouched, and the construction table carries no verdict.

### Anything decided that the reviewer might disagree with

**I installed the rule's book while the fifth check fails on another row.** The
book is share-only, which passes all five checks, and the failing row is a
comparison row that cannot satisfy the margin. Installing the book is what
makes the artifact and the live path coherent and what the owner confirmed;
refusing to install it would have left the table claiming a book (the drop-only
one) that the reviewer has already ruled out. If the reviewer reads the check as
gating the whole table, the fix is to drop the min $5,000 row from the check
list or from the table, and I will do either.

**The rule's run time is stored on the live manifest and not in the table.** The
reviewer asked for the run time on the live path; storing it in the table would
have made the parquet differ on every build, which is a worse defect than the
extra field is a benefit.

**The fast floor check is a second implementation of the share rule.**
`kept_set_clears_floor` and `finalize_kept_set` both call `sized_kept_weights`
and `kept_shares`, so there is one implementation and two entry points, and a
test asserts they agree. If the reviewer would rather the search pay 0.0067s per
trial than have two entry points, the rule takes about 30 times longer per row
(0.09s becomes about 2.7s per row) and I will change it.
