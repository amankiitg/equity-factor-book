# Incident 2026-10-15: a warrant applied as a spin-off child (SKYD -> SKYD.WS)

The 2026-10-15 evening email carried the line

```
Spin-offs: spinoff: SKYD -> SKYD.WS 1:1 applied.
```

`SKYD.WS` is the SPY holdings file's own **warrant** line for the same issuer
(`SKYD/WS`, weight 0.0, sector `-`, the same 6,658,074 shares as the common). The
vendor filed that distribution as a spin-off child, and the rule bought a close for
a symbol that is not a share: it replaced SKYD's 2026-10-14 return, a real
**-23.84%** print, with **+3.13%**. SKYD carries no sector row, no descriptor row
and no specific variance in the model inputs, so it is in the proposal's *excluded*
list and no book changed at any point. What was damaged is a return cell in the run
tree, one stored corporate-action row, and every later rebuild.

Fixed in `live/corporate_actions.py` with tests, on `fix-skyd-spinoff` (`68f1fe7`), merged to `main` in `7f9983a` (the merge of `68f1fe7`).

## 1. Which rule fired for SKYD -> SKYD.WS, and on what inputs

The detector is `live/corporate_actions.vendor_spinoffs`, called from the append
path, `scripts/run_live_daily.py`:

```python
outcome = corporate_actions.apply_to_artifact(run_tree, since=before_last)
```

Its records come from the **vendor**, not from the SPY file:
`live/alpaca.spin_offs(symbols, session)` (`live/alpaca.py:1479`) makes one
corporate-actions request over a ±1 day window and keeps only records whose
`ex_date` is the session, mapping each to
`{"parent": source_symbol, "child": new_symbol, "source_rate", "new_rate"}`.

The stored row is what proves which path fired: SSGA spells the warrant `SKYD/WS`
(slash), the record's child is `SKYD.WS` (dot), and the dot is the vendor's
spelling. Re-read read-only on 2026-10-16:

```
alpaca.spin_offs(["SKYD"], 2026-10-14)
[{'parent': 'SKYD', 'child': 'SKYD.WS', 'ex_date': 2026-10-14,
  'source_rate': 1.0, 'new_rate': 1.0}]
```

`source_rate` and `new_rate` are both 1.0, so `child_per_parent = 1.0` and the label
is `spinoff: SKYD -> SKYD.WS 1:1 applied` — the email's line, from
`describe_spinoffs`. There was no check on what kind of instrument the child is.

**Why it fired on the 10-15 run for a 10-14 ex-date.** The 10-15 run was a catch-up
run: `efb.run_status` for 2026-10-15 (`job live_daily`) has `catch_up = true` and
`catch_up_sessions = ['2026-10-14', '2026-10-15']`, and the append path applies the
rule to every appended session. So the correction landed on the 10-14 session
during the 10-15 run.

## 2. What "applied 1:1" changed

| artifact | SKYD | SKYD.WS |
|---|---|---|
| run tree `processed/returns.parquet`, cell `(2026-10-14, SKYD)`, columns `r` and `g` | **-0.2384034958** (9.27000045776367 -> 7.05999994277954) **-> +0.0312836538** | no row, before or after |
| run tree `raw/prices.parquet` | untouched | no row was created for it |
| `efb.e11_prices` | untouched: 8 rows, 10-06 .. 10-15, `split_factor` 0.0 | no row, ever |
| `efb.e11_corporate_actions` | one row inserted for the parent (see §3) | no row |
| `efb.run_status`, 2026-10-15 | `splits []`, `flags []`, `status ok` — the spin-off appears in no field | - |
| published `latest.json` | no spin-off field; `run_status.splits []`, `flags []` | - |
| evening email | the `Spin-offs:` line above, the only place it was announced | - |
| `efb.proposals`, `efb.reconciliation`, `efb.orders`, `efb.fills`, `efb.positions` | not touched by the rule | - |

The value it wrote is `(parent_close + 1.0 x child_close) / parent_previous_close - 1`
(`spinoff_return`), with the parent closes read from the run tree and the child close
from the vendor's own bars read:

```
7.05999994277954 / 9.27000045776367 - 1  = -0.23840349577687925   the print
(7.05999994277954 + 1.0 x 2.5) / 9.27000045776367 - 1 = +0.03128365379669362
alpaca.closes_on(["SKYD.WS"], 2026-10-14) -> 2.5
alpaca.closes_on(["SKYD/WS"], 2026-10-14) -> APIError "invalid symbol: SKYD/WS"
```

**No flag was raised**, because the cell was corrected rather than nulled and the
adjusted value is inside the 40% band: `spinoff_flags` fires only on a nulled cell or
`|adjusted| > 40%`. So the run's own output said nothing about it, and the two flags
lists in the stored run status and the document are empty.

**The corrected value is not stored anywhere.** There is no returns appendix table, so
the number the run wrote can only be re-derived from the closes and the record. What
*is* stored is the record, and the two readers disagree about it: the append path
corrected the cell (+3.13%, using the vendor close), while the rebuild path
(`live/extend.py:recorded_spinoffs` -> `apply_recorded`) finds no `SKYD.WS` row in the
price panel and therefore **nulls** the cell. A rebuilt tree on `origin/main` has
`SKYD` 2026-10-14 = NaN; the run tree had +3.13%.

## 3. What persists

```sql
select trade_date, ticker, effective_date, factor, source, cross_check_ratio,
       explained_by, new_ticker, source_rate, new_rate
  from efb.e11_corporate_actions
 order by trade_date;
```

| trade_date | ticker | effective_date | factor | source | cross_check_ratio | explained_by | new_ticker | source_rate | new_rate |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-01 | CTVA | 2026-10-01 | 1.0 | manual.record | NULL | spinoff | VYLR | 1.0 | 1.0 |
| 2026-10-15 | SKYD | 2026-10-14 | 1.0 | alpaca.corporate_actions | NULL | spinoff | **SKYD.WS** | 1.0 | 1.0 |

Exactly two rows exist in the whole table, and the SKYD one is the incident. No row
has `ticker = 'SKYD.WS'` or `'SKYD/WS'`.

## 4. Will it fire again, and would a second application stack?

**The append path will not fire again.** `alpaca.spin_offs` returns only records
whose `ex_date` equals the session it is asked about, and it drops the rest
(`if ex_date != day: continue`). Tomorrow's appended session is 2026-10-16 and this
record's ex-date is 2026-10-14, so the vendor filter cannot hand it back. Re-read
today the record is still served — but only for the 2026-10-14 window.

**The rebuild path fires every evening, and that is the idempotency check that does
not exist.** `live/extend.py:222 recorded_spinoffs()` reads *every* stored row with
`explained_by = 'spinoff'` and `extend_returns` calls
`corporate_actions.apply_recorded(...)` on **every run**, so the SKYD row is
re-applied to the recomputed panel tonight and every night after. There is no
"already applied" marker anywhere; the only thing that stops it is the reader.

**A second application does not stack.** `_apply_spinoff` computes the value from the
raw closes and the record's ratio and reads the frame's current value only to report
the raw print in the log. Re-applying writes the same number (or the same NaN), so
the record is idempotent in effect and wrong in value — which is why the reader, not
the count, is what had to change.

## 5. Did it touch the 2026-10-15 book?

**No.** The published 2026-10-15 document (`generated_at 2026-10-15T22:50:28Z`,
`target_close 2026-10-15`, `catch_up true`, `status ok`, `detail ""`) carries 169 kept
names and no SKYD. `efb.positions` has no SKYD row on any date. `efb.broker_positions`
and `efb.orders`/`efb.fills` carry SKYD exactly once, on 2026-10-08, and that is the
**sale** of a legacy holding (intended notional -3055.30, 326.07 shares) — nothing to
do with this incident.

SKYD's place in the model inputs is the *excluded* list, not a dropped list:

| input | SKYD rows |
|---|---|
| `efb.e11_universe` | 10-05, 10-06, 10-07, 10-08, 10-09, 10-12, 10-14 (`SKYDANCE CORP`, weight 0.0058 on 10-14) |
| `efb.e11_sectors` | none |
| `efb.e11_descriptors` | none |
| `efb.e11_specific_returns` | none |
| `efb.e11_specific_var` | none |
| `efb.e11_prices` | 10-06 .. 10-15 |
| `efb.e11_shares` | 10-06 |
| `ebf.e11_corporate_actions` | the incident row, 10-15 |

So the proposal's `excluded` list — SPY members the frozen model has no column for —
is where it lands: my rebuilt proposals for 2026-10-13, -14 and -15 all report
`excluded = ['BE', 'DD', 'ILMN', 'P', 'SKYD', 'TWLO', 'VYLR']` and
`dropped_no_risk = [FDXF, HONA, Q]`, `dropped_no_price = []`. It was never in the
kept book, in an excluded-from-book sense at the floor, or in any dropped list.

## The fix

`is_derivative_line(ticker)` in `live/corporate_actions.py`: the last component after
splitting on `/`, `.` or `-` must not be a warrant, unit or right marker
(`WS WT W WTS U UN UNIT R RT RIGHT`). It is applied in **both** readers:

- `vendor_spinoffs` — the vendor's record, before it is applied, so tonight's rule
  cannot fire on a warrant;
- `spinoffs_from_rows` — the appendix's stored row, before a rebuild re-applies it.

Both log a warning naming the child, and the reader's warning says the row should be
deleted. **Nothing stored is edited or deleted by the code.**

What is deliberately *not* done: the "zero-weight SPY row with sector `-`" alternative
is not usable as a signal. In `ebf.e11_universe`, `sector` is `-` for **all 503 rows**
of every archived file (the SPY file's sector column is not the GICS mapping the model
uses), and the SPY spelling `SKYD/WS` never reaches `efb.e11_universe` at all — the
only signal present in both sources is the ticker marker. Separators are checked on the
last component only, so `BRK.B` and `BF.B` (share classes, both live in the universe),
`BRK/B`, `VYLR` (a real child) and `W` (Wayfair, no separator) are untouched.

## The proofs

**Tests** (`tests/test_week2_spinoff.py`, `tests/test_e11_extend.py`, 11 new):

- `test_a_warrant_unit_or_right_is_never_a_spin_off_child` — the real record, seven
  spellings; the share child in the same payload still reads (the control).
- `test_the_marker_is_only_ever_the_last_component` — `BRK.B`, `BRK/B`, `VYLR`, `W`,
  `''`, `None` are not derivative lines.
- `test_the_real_skyd_record_would_have_moved_the_cell_without_the_filter` — the
  control: read as a spin-off the record nulls the cell; the reader now returns nothing
  for it.
- `test_a_recorded_warrant_is_not_put_back_by_the_rebuild` — the real stored row, the
  real closes: the rebuild writes -23.84% and the warning names the row; the same tree
  and row with a *share* child moves the cell instead (the control).
- `test_the_stored_history_reads_the_same_except_for_skyd` — both real stored rows read
  together: CTVA survives, SKYD is dropped.

**The detector over the real stored history**, with and without the fix:

```
with the fix   : [('CTVA', 'VYLR', True)]
without the fix: [('CTVA', 'VYLR', True), ('SKYD', 'SKYD.WS', True)]
```

Identical except SKYD.

**The identity proof.** `build_proposal(store=False)` for 2026-10-13, -14 and -15 on a
copy of the committed tree in a temp directory, hydrated from the store's appendix
(read-only) and rebuilt by each branch's own code, so both branches saw exactly the
same inputs:

| close | code | n_kept | kept_gross | max abs weight | kept vol | excluded | dropped (price / risk) |
|---|---|---|---|---|---|---|---|
| 2026-10-13 | origin/main | 180 | 1.0 | 0.0 diff | 0.0419868204 | same | same / same |
| 2026-10-13 | fix-skyd-spinoff | 180 | 1.0 | 0.0 diff | 0.0419868204 | same | same / same |
| 2026-10-14 | origin/main | 185 | 1.0 | 0.0 diff | 0.0428081337 | same | same / same |
| 2026-10-14 | fix-skyd-spinoff | 185 | 1.0 | 0.0 diff | 0.0428081337 | same | same / same |
| 2026-10-15 | origin/main | 173 | 1.0 | 0.0 diff | 0.0401109724 | same | same / same |
| 2026-10-15 | fix-skyd-spinoff | 173 | 1.0 | 0.0 diff | 0.0401109724 | same | same / same |

Same kept names on all three dates, **max absolute weight difference exactly 0.0**,
same `kept_gross`, same `n_kept`, same `excluded`, `dropped_no_price` and
`dropped_no_risk` lists. The only difference anywhere in the returned frame is the
cell the record was about, and the name it belongs to never enters the book:

```
SKYD 2026-10-14 return  origin/main: None        (the record nulls it)
SKYD 2026-10-14 return  branch     : -0.23840350 (the print, restored)
SKYD in the kept book   : False on every close, both branches
```

**`make lint`** (ruff, mypy over `live scripts`, black) is green.

**The gate suite.** `.venv/bin/python -m pytest tests/ -q -m "not slow and not
requires_live_tree and not merge_guard"`, run on `origin/main` and on this branch in
the same environment each time (a git worktree holds no built artifacts — the seed
tree is not committed — so the artifact-reading families fail on both sides alike;
the third and fourth rows are the same comparison with the committed seed tree
copied in):

| environment | code | failed | errors | passed | skipped | deselected |
|---|---|---|---|---|---|---|
| worktree, no built tree | `origin/main` | 84 | 50 | 1247 | 60 | 36 |
| worktree, no built tree | `fix-skyd-spinoff` | 84 | 50 | **1258** | 60 | 36 |
| worktree + committed seed tree | `origin/main` | 60 | 0 | 1378 | 3 | 36 |
| worktree + committed seed tree | `fix-skyd-spinoff` | 60 | 0 | **1389** | 3 | 36 |

The failing id sets are **identical** in both environments: `diff` of the two sorted
`FAILED`/`ERROR` id lists is empty (134 ids without the tree, 60 with it), so **zero
new failures and zero newly passing**; the 11 extra passes are this branch's own new
tests. Against `docs/known_test_failures.md`, with the tree present 48 of the 60 ids
are in that ledger and the other 12 are: the six walkthrough-notebook HTML renders,
the dashboard d5 methodology links, one web-fixture set test, and four
`tests/test_week2_spinoff.py` tests that now stop on a live vendor answer for CTVA
(`the vendor back-adjusted the last stored session (ratio 0.150038) with no split
record behind it`). All twelve fail on `origin/main` in the same run with the same
message, so none of them is this branch's; none of the eleven new tests fails
anywhere. The ledger's 55-id baseline was measured on a machine holding the built
tree, which is why the same-environment comparison above, rather than the ledger's
count, is what the gate is read against here.

## The row the owner should delete

```sql
delete from efb.e11_corporate_actions
 where ticker = 'SKYD' and trade_date = '2026-10-15';
```

That is the only row. Deleting it is belt and braces: with the fix in place the reader
ignores it whether it is there or not, and every rebuild recomputes SKYD's 2026-10-14
return from the raw closes, so the print comes back either way.

## Is tomorrow's run safe?

Yes.

- The warrant record cannot reach the append path again (vendor filter on `ex_date`).
- If it somehow did, `vendor_spinoffs` refuses it, logs it, and never fetches a close
  for it.
- The stored row cannot re-apply the correction to the rebuilt panel:
  `spinoffs_from_rows` refuses it and logs the row to delete.
- SKYD's 2026-10-14 return in a rebuilt tree is the raw print, -23.84%, which is the
  number the session actually paid.
- No book was affected: SKYD is in the `excluded` list on every live close, and the
  identity proof shows the three closed books are byte-identical with and without the
  fix.

Nothing was written to R2, the database or the broker while this was investigated or
fixed; the store was read with SELECTs and the vendor with reads, and no Render run
was triggered.
