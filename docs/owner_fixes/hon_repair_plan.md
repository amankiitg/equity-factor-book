# The HON 2026-06-29 spin-off repair: the plan, and why it was not applied

Written 2026-10-28. Status: **not applied.** Two independent reasons, both measured
today, are in section 1 and section 4.

The first changes what the repair is for. The bad value is not in the live path. The
seed every live run starts from carries HON's 2026-06-29 specific return as
`-0.062064005330318736`, and the store's variance series shows no trace of the print.
The `+45.51%` return and the fitted row it produced live in the **research** artifact
set that `efb/build.py` builds, and the live book has never seen them.

The second is the stop rule: the repair as specified, a masked refit plus the variance
recomputed from that day forward, needs a writer that does not exist.

## 1. Every place the value lives, measured today

Read-only. The seed was downloaded from the seed bucket with the seed module's own
read-only client; the store was read through `live.store`; the research tree is the
artifact set at `/tmp/efb-gate` (a build from 2026-10-21 to 2026-10-02).

| location | HON 2026-06-29 | verdict |
|---|---|---|
| R2 seed, `models/XS-v1/specific_returns.parquet` | specific return **-0.062064005330318736** | clean |
| R2 seed, `models/XS-v1/specific_var.parquet` | 0.000279 on 2026-09-10, 0.000273 on 2026-09-21 | clean |
| store, `efb.e11_specific_var` | 0.000268 on 2026-09-25 falling to 0.000226 on 2026-10-27 | clean |
| research, `processed/returns.parquet` | `r` = **+0.45512682485681055**, `corrected=True` | **bad** |
| research, `models/XS-v1/specific_returns.parquet` | specific return **+0.4419966659996697** | **bad** |
| research, `models/XS-v1/specific_var.parquet` | 0.003349 (06-30), 0.002506 (07-31), 0.001900 (08-31), 0.001402 (09-30), 0.001358 (10-02) | **bad** |
| research, `models/XS-v1/factor_cov.parquet` | dateless snapshot taken over factor returns that include the 06-29 fit | **bad until recomputed** |
| research, `descriptors`, `factor_returns`, `xs_r2` | the 2026-06-29 session | **bad** |
| research, `alpha/`, `eval/`, `portfolios/`, `cov/`, `attribution/` | every table derived from the panel | **derived** |

The live seed's 16,172,652 bytes and the research tree's 16,094,906 are different
files, which is why the two disagree: the live path recomputes `r` for every session
from `raw/prices.parquet` in `live/extend.py::extend_returns` and re-applies only the
spin-off rows recorded in `efb.e11_corporate_actions`, and HON has no recorded row. So
the live panel carries the as-traded -6.46% and the fitted variance that follows from
it. The research build applies the recorded row, whose `new_rate` of 0.5 is wrong by a
factor of ten, and fits that.

The panel median specific variance on 2026-06-30 is 0.000310 and HON's is 0.003349,
ten times the cross-section, against a name that traded -6.5%.

## 2. Which script writes each, and the order

| step | what | writer | scope |
|---|---|---|---|
| 1 | the source of the wrong number: a recorded action whose ratio contradicts the vendor's own split factor | `live/corporate_actions.py::apply_recorded` (guard built on branch `hon-spinoff-return`) | one row |
| 2 | the 2026-06-29 cross-section refitted with HON masked | `scripts/repair_session.py --ticker HON --session 2026-06-29` | 1 session x 4 artifacts |
| 3 | specific variance from 2026-06-30 to the frontier | **none exists** | 5 dates in a research tree, 15 or more in a live-extended one |
| 4 | factor covariance | `scripts/repair_session.py` rewrites it whole, as does `efb/build.py` | the snapshot |
| 5 | re-derive the research outputs | `make rebuild` | the whole artifact set |

`repair_session.py` is the CTVA instrument and it does steps 2 and 4 correctly: it
masks the name out of the session panel, refits, replaces that session's rows in
`descriptors`, `factor_returns`, `specific_returns` and `xs_r2`, writes an explicit
null for the masked name, recomputes `factor_cov` whole, and recomputes
`specific_var` **for that session only**, deliberately keeping every earlier session's
rows because an EWMA's past does not move when a later observation does.

That last clause is exactly the problem here and it was not a problem for CTVA. CTVA's
print was 2026-10-01, at the frontier: only 2026-10-01 and 2026-10-02 existed after it
and both were refit. HON's print is 2026-06-29, roughly 85 sessions before the
frontier, so it sits inside the EWMA window of every date from 2026-06-30 onward:
`specific_var` for 06-30, 07-31, 08-31, 09-30 and every daily row after 2026-09-03.

## 3. The missing writer, named

`fundamental.specific_variance` has three call sites and all three are read and
confirmed:

| file | line | what it passes | what it writes |
|---|---|---|---|
| `efb/build.py` | 1434 | no date filter, the whole history | a full rebuild of every artifact, far more than this repair may touch |
| `live/extend.py` | 468 | all dates, then keeps only `new_dates` | new sessions only, appended |
| `scripts/repair_session.py` | 416 | `dates=[session]` | one session |

The CLI takes one `--session`. Nothing recomputes a range of `specific_var` rows and
writes them back.

What the missing writer has to do is small and it should be added rather than worked
around: take a first date, compute `fundamental.specific_variance` over the repaired
`specific_returns` for every stored date on or after it, and replace those rows in
`specific_var.parquet` and in `efb.e11_specific_var`. The second half has the same
gap: `live/appendix.py::persist_new_sessions` writes sessions after the stored
frontier, so the stored rows for 2026-09-25 to 2026-10-27 have no range writer either.

Per the stop rule this is a writer that does not exist, so nothing was applied and no
artifact or store row was written today.

## 4. Expected running time

Measured, not estimated: one dry run of
`scripts/repair_session.py --ticker HON --session 2026-06-29 --tree <copy>` took
**517 s (8 m 37 s)** on this machine at a load average of 5. Two thirds of that is the
tree load, which hydrates the seed plus the appendix before fitting.

A repair with the missing writer added is one tree load plus one refit plus one
variance pass over five dates, so about **10 to 12 minutes**, not the 8.6 minutes x 5
a per-session loop would cost.

## 5. Predicted HON specific variance after the repair

Computed with the estimator's own settings (`D_HALF_LIFE` 42, `D_SHRINK_K` 60, 3,977
HON observations at 2026-06-30), on the research history with HON's 2026-06-29 cell
nulled:

| date | stored now | predicted after | ratio |
|---|---|---|---|
| 2026-06-30 | 0.003349 | **0.000264** | 12.7x lower |
| 2026-10-23 | 0.001358 in a research tree that ends 10-02; the live tree reads **0.000228** | about 0.00027 | 1.0x against the live tree |

The 2026-10-23 line is the important one for the book. The live tree already reads
0.000228 there, which is the level the prediction names, and that is the measurement
that says the repair would not move the 2026-10-23 book at all: the weight (0.05396),
the variance share (0.1448) and the raw signal (+1.450992, 99.59th percentile) are all
already computed from the as-traded return.

## 6. Backups and rollback, for the day the repair does run

Every file goes to `~/efb-backups/2026-10-28/` with a manifest naming its source, size
and sha256, and nothing is overwritten in place until the manifest row exists.

| to back up | how | rollback |
|---|---|---|
| the artifact tree's `models/XS-v1/*.parquet` and `processed/returns.parquet` | copy | copy back, then re-run the check below |
| `efb.e11_specific_var` rows for the dates touched | `copy ... to stdout with csv header` | `copy ... from stdin with csv header` inside one transaction |
| the R2 seed bundle | the seed manifest and the tree it was pushed from | `scripts/push_seed.py --dry-run` to confirm, then push the backed-up tree |
| the published snapshots | not touched by this repair, by the owner's rule | none needed |

The dry run of any rollback is the same check run forwards: re-read the artifact and
the table and compare against the backed-up copy row for row.

## 7. What I recommend instead of applying it today

1. **Merge `hon-spinoff-return`.** The guard nulls a recorded share distribution whose
   ratio contradicts the vendor's own split factor, which is the source of the
   `+45.51%`, and it is already gated. That is the mechanism fix; the data repair is a
   consequence.
2. **Add the range writer** to `scripts/repair_session.py` as `--variance-from
   <date>`, writing both the artifact and `efb.e11_specific_var`, with a dry run that
   prints the dates and the largest change per date. Then the research artifact set can
   be brought into line in one command and one backup.
3. **Change the recorded row.** `new_rate` 0.5 in `efb.e11_corporate_actions` is wrong;
   the correct ratio is 0.05 (one HONA per 20 HON) and the vendor's own factor, 0.9535,
   agrees with it. Until that row is corrected the guard will keep nulling the session,
   which is the safe answer but not a permanent one. That correction is a store write
   and needs the owner's decision.
4. **The live path needs nothing.** It is already correct, and the section 1 rows are
   the evidence.
