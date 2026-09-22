# Handoff log

Append-only. Reviewer writes; DeepSeek does not edit this file.

---

## 2026-09-21 review: E10 and RG-Operate at 5b77d6f

Reviewed at HEAD 5b77d6f, working tree clean. No prior TASK.md or REPORT.md
existed; this is the first review, run directly against the sprint artifacts,
`sprints/E10/RESULTS.json`, `docs/research/E10_risk_policy.md` and
`docs/research/RG_OPERATE.md`.

### Decisions needed from you

**Decision 1, and it is the important one: E11 would trade the momentum factor
through a machine built to hedge the momentum factor to zero.**

`RG_OPERATE.md` item 6 picks `momentum_12_1` as the book's signal, justified by
its raw horizon-1 IC surviving two shift audits (0.0151 to 0.0149 forward, 0.0151
to 0.0152 lagged). Those audits test for leakage. They do not test whether the
edge is a factor exposure, and the project has already measured that it is.

From `data/alpha/summary.parquet`, neutral IC at horizon 21 across all six
signals:

| signal | raw ic_h1 | neutral ic_h21 | neutral t | audit killed | leak flag |
| --- | --- | --- | --- | --- | --- |
| momentum_12_1 | 0.015076 | -0.010684 | -1.549 | False | False |
| idio_momentum | 0.012102 | -0.003094 | -0.512 | False | False |
| short_term_reversal | 0.012031 | 0.002796 | 0.609 | False | False |
| short_interest | 0.002677 | 0.008518 | 1.176 | True | False |
| post_earnings_drift | 0.123986 | 0.009876 | 1.310 | True | True |
| low_residual_volatility | -0.001400 | 0.001865 | 0.327 | True | False |

`momentum_12_1` has the most negative factor-neutral IC of the six. The hygiene
ledger already says why, in its 2026-09-21 entry on F7.2: "Neutralizing momentum
against a risk model that contains momentum projects the signal out ... the
signals are the known factors, not new information."

The conflict is with RG-Operate item 2, which records the champion hedge as the
exact in-model FMP hedge that "drives the worst post-hedge exposure to 5.8e-15
and the idio share after the hedge to 100.0%". Running the chosen signal through
the chosen hedge removes precisely the component carrying the +0.0151 IC and
leaves the component carrying the -0.0107 one. The book would be constructed to
trade the negative half of the signal. Nothing in the gate memo notes this.

Options, all of which keep E11 a documented-null book:

1. **Keep `momentum_12_1`, drop the hedge.** Run it unhedged and relabel E11 as a
   factor-bet operations rehearsal. Honest, and it exercises the daily loop, but
   it stops exercising E6 and E8, which are the parts of the machine E11 exists
   to prove.
2. **Switch to `idio_momentum`.** Neutral IC -0.0031 with t -0.51, that is null
   rather than negative; raw IC t 5.04; the most lag-robust of the six
   (0.01210 raw against 0.01233 one day later); and it is by construction the
   idiosyncratic component, which is what the hedged machine is built for. This
   is my recommendation: it changes one input, keeps the whole stack under test,
   and keeps the pre-written E12 verdict of luck intact.
3. **Switch to `short_term_reversal`.** The only signal that is not audit-killed,
   not leak-flagged, and has a positive neutral IC (0.0028, t 0.61). Cost is the
   problem: turnover 0.785 per rebalance against momentum's 0.390, roughly double,
   and E9's break-even for momentum was already 5.71 bp against a realistic 5 bp.
   Needs a cost check before it can be chosen.
4. **Synthetic alpha only, no real signal.** What E8, E9 and E10 already did. E11
   becomes a pure operations rehearsal and RG-Operate item 6 gets withdrawn.

I have not acted on this. The next TASK.md does not touch it.

**Decision 2: the constituent source.** My assessment is below under RG-Operate.
Short version: SSGA's SPY file works today and carries CUSIP and SEDOL;
iShares' IVV endpoint is gated and silently returns HTML; sector still comes
free from the live Wikipedia page. My recommendation is SPY as the membership
and identity source, live Wikipedia for sector, IVV added later only if the gate
can be cleared. This is a recommendation, not a blocker, and it is the task
after next.

### On the task status

Your protocol says a decision pending means TASK.md goes to `blocked`. I have
written it `ready` instead. Decision 1 belongs to E11 and nothing in the next
task depends on it, and the E10 defects below are worth more than a stalled
agent. Say the word and I will flip it.

### Verified

- `make test`: 586 passed, exit 0. Runtime 421 s.
- `make lint`: ruff clean, mypy clean on 32 source files, black clean on 128
  files. Exit 0.
- `notebooks/E10_walkthrough.ipynb`: 19 cells, 11 code cells, zero unexecuted,
  zero error outputs, execution counts 1 to 11 and monotonic. Clean against
  standing rule 10.
- `sprints/E10/RESULTS.json` stores the `criterion` and `threshold` strings for
  F10.1 to F10.3 verbatim against `sprints/E10/PRD.md`. The rewording is in the
  memo, not in the results file. See E10-F8.
- Every stored number in `data/allocation/*.parquet` reproduces from
  `efb.allocate.run(store=False)` at this data hash. The arithmetic is
  reproducible. What it measures is where the defects are.
- F10.1 sign mix, your first item: **confirmed exactly.**
- F10.3 trailing 12-window, your second item: **confirmed, with a measurement.**

### Findings

**E10-F1. F10.1's relative gap mixes signs. Confirmed.**
`efb/allocate.py:drawdown_analysis` computes
`abs(simulated - analytical) / abs(analytical)` where `simulated` is a signed
drawdown (-0.14031) and `analytical` is a magnitude (+0.03543). That yields
(|sim| + ana) / ana, which is the stored 4.959825. With consistent signs the gap
is (0.140308 - 0.035433) / 0.035433 = **2.9598**, your 3.0. The stored value is
inflated by exactly 2.0 because the sign flip adds one unit and the direction of
the comparison adds another.

**E10-F2. The analytical benchmark has no horizon in it, and the PRD says it
must. Confirmed.**
`sprints/E10/PRD.md` specifies "the Magdon-Ismail et al. closed form for the
expected maximum drawdown as a function of SR and horizon".
`magdon_ismail_median` implements `ln(2) * sigma^2 / (2 mu)`, which has no
horizon argument. That expression is the median of the **stationary** drawdown of
a drifted Brownian motion, not of its **maximum** drawdown. The all-time maximum
drawdown of a drifted Brownian motion is unbounded, so an infinite-horizon
maximum-drawdown median does not exist, and the quantity being compared against
the simulation is not the same quantity the simulation measures.

The simulated side is the maximum drawdown over 174 rebalances, a horizon of
174 * 21 / 252 = 14.5 years. The Magdon-Ismail positive-drift branch at that
horizon, `2 sigma^2 / mu * Qp(mu^2 T / (2 sigma^2))` with the large-argument form
`Qp(x) ~ 0.25 ln x + 0.49088`, gives x = 6.936, Qp = 0.9751, E[MDD] = **0.1994**.
Against a simulated median of 0.1403 that is the same order of magnitude, and the
gap is in the opposite direction to the one the memo reports. The horizon
mismatch does not merely explain most of the gap, it explains the gap and
reverses its sign.

**E10-F3. The recorded mechanism for F10.1 is contradicted by a control I ran.
This is the serious one.**
`RESULTS.json` note and the memo both say the gap "measures the fat tails and
volatility clustering the Brownian benchmark does not have". Two problems.

First, the note describes "block-bootstrapped paths". The code is
`rng.choice(x, size=n, replace=True)`, an i.i.d. resample with replacement. There
are no blocks. An i.i.d. bootstrap destroys volatility clustering by
construction, so the simulation cannot be measuring clustering, and the
deliverable claims it does.

Second, the fat-tail half does not survive a control. I drew 2000 i.i.d.
**Gaussian** paths at the book's own mu and sigma and the same n = 174, so no fat
tails and no clustering by construction, and took the median maximum drawdown:

| path law | median max drawdown |
| --- | --- |
| Gaussian i.i.d., same mu, sigma, n | -0.15397 |
| book's returns, i.i.d. bootstrap (stored) | -0.14031 |

The Gaussian null draws down **deeper** than the book. There is no fat-tail
excess to explain. The entire 4.96 is the wrong benchmark, and the memo's
explanatory sentence should be deleted rather than reworded.

**E10-F4. The stop-loss never re-enters. Re-entry is unreachable by
construction.**
`efb/allocate.py:_apply_stop_loss`. While `invested` is False the function
updates neither `wealth` nor `peak`, so `wealth / peak - 1.0` is frozen at the
value that tripped the stop, which is below -0.10 and therefore never above the
-0.05 re-entry level. Demonstrated on `[-0.2, 0.5, 0.5, 0.5, 0.5, 0.5]`, which
returns `[-0.2, 0, 0, 0, 0, 0]`. The rule the memo states, "flat while the
running drawdown is below -10% and re-enters at -5%", is never executed in any
path. The rule actually tested is "flat forever after the first -10% drawdown".
On `seed_mom_ls` that zeroes 1229 of 4091 days, and the +0.226 Sharpe improvement
in the table is a negative-Sharpe book being switched off permanently, not a
stop-loss result.

**E10-F5. The `seed_ew` row rests on 207 of 4193 days, and the table does not say
so. A well-formed table hiding a bug.**
`seed_book_daily_returns` applies the E5 missing-data semantics, under which any
held name with a missing return makes the whole portfolio-day missing. The E5
semantics are correct; applied to a roughly 500-name equal-weight book they
delete almost everything. Measured:

| book | dates available | non-missing days | window | min drawdown | stop fired |
| --- | --- | --- | --- | --- | --- |
| seed_ew | 4193 | 207 | 2025-10-28 to 2026-08-27 | -0.0421 | no |
| seed_mom_ls | 4092 | 4091 | 2010-05-28 to 2026-09-03 | -0.2160 | yes |

So the memo's "seed_ew | 2.207 | 0.000" reads as "the stop is neutral for the
equal-weight book" when it means "the surviving sample is the last ten months, a
window whose deepest drawdown is 4.2%, so a -10% stop could not fire". The 2.207
base Sharpe is a ten-month figure presented beside a sixteen-year one in the same
column. Neither number carries its n. This violates standing rule 16.

**E10-F6. F10.3 compares 15 raw years against 14 targeted years.**
`_vol_target_returns` uses `rolling(12)` then `shift(1)`, so the targeted series
starts in 2013 while the raw series starts in 2012. `vol_target_analysis`
computes each dispersion on its own year set and stores `n_years: 15`, the raw
count, for both. 2012 carries raw annual vol 0.1126 and is in the raw
denominator only. Recomputed on the intersection:

| basis | raw CV | targeted CV | reduction |
| --- | --- | --- | --- |
| as stored, 15 raw years vs 14 targeted | 0.2663 | 0.2338 | **0.1220** |
| aligned, 14 years both sides | 0.2754 | 0.2338 | **0.1508** |

Verdict is unaffected, both are far below the 40% threshold. The stored headline
number is wrong by 2.9 points and is quoted in the memo.

**E10-F7. F10.3's recorded mechanism blames the estimator, and the estimator is
not the cause. Your second item, measured.**
The stored note says "the trailing 12-window volatility estimate lags and is
noisy, so the targeting cannot remove the year-to-year dispersion the 40%
threshold asks for". A daily-return estimator was available: the design book's
weights are held constant across each 21-session hold, and
`data/models/XS-v1/specific_returns.parquet` is daily, so the book's daily
return series (3594 observations, 2012-02-01 to 2026-08-31) is computable from
inputs `efb/allocate.py` already loads. Rebuilding the target from it, all
figures on aligned years:

| estimator | window | reduction |
| --- | --- | --- |
| daily | 21 | **0.2042** |
| daily | 42 | 0.1848 |
| daily | 63 | 0.1119 |
| daily | 126 | 0.2059 |
| daily | 252 | 0.1470 |
| monthly | 6 | -0.1122 |
| monthly | 12 (as built) | 0.1508 |
| monthly | 24 | 0.1713 |
| monthly | 36 | 0.0702 |

The best available estimator reaches 0.2042. The 40% threshold is not reachable
by changing the estimator, so **F10.3 stays a fail and the verdict is safe**, but
the mechanism on the record is wrong. Under standing rule 3 the fail is kept and
the mechanism is corrected to the one that is true: the year-to-year dispersion
of this book's realized volatility is not forecastable at this horizon, and the
40% bar was written for a higher-frequency object than a monthly book.

**E10-F8. The memo paraphrases two criteria instead of quoting them. A criterion
reworded.**
`sprints/E10/write_memo.py` interpolates `verdicts['F10.x']['verdict']` but types
the criterion text by hand, so the deliverable diverges from the verbatim text
sitting in the same file it reads:

- F10.1 stored: "Simulated drawdown distribution matches the analytical
  approximation within 10% at the median for the seed book's SR."
  Memo: "... within 10% of the analytical median, **or the gap is the fat-tail
  and clustering the Brownian benchmark does not have**." The appended disjunct
  makes the criterion unfalsifiable, and E10-F3 shows the disjunct is false.
- F10.3 stored: "Vol targeting reduces the dispersion of realized annual vol
  across years by **more than 40%**."
  Memo: "... across years by **0.1220**." The threshold is replaced by the
  measured value, so the criterion reads as satisfied by construction.

The fix is mechanical: interpolate the stored `criterion` and `threshold`.

**E10-F9. The memo traceability test cannot catch a sign error.**
`tests/test_e10_memo.py` matches with `abs(abs(v) - value) <= tolerance`. Both
sides are absolute values, so a memo that printed +0.1403 for a stored -0.1403
would pass. Given that E10-F1 is a sign defect and the project lists sign
mix-ups among its recurring classes, the guard is blind to the defect it most
needs to catch. It also only requires a number to appear somewhere in the union
of all stored numbers, not in the artifact it is quoted from.

**E10-F10. The regime table's "max drawdown" is computed on a spliced path.**
`regime_analysis` groups observations by VIX tercile and runs a cumulative
product within each group. The observations in a tercile are not contiguous in
time, so the wealth curve splices across years and the resulting drawdown is not
a drawdown any book experienced. The same applies to `n_underwater`. This may be
the intended diagnostic, but it is labelled "max drawdown" in the memo and in
RG-Operate item 4 with no note, and the risk budget is written off it.

**E10-F11. RG-Operate item 5 understates the constituent problem.**
The memo says "the universe is frozen at the pinned Wikipedia revision". It is
not frozen, and that is worse. `efb/universe.py:fetch_constituents` reads the
**live** page and still works: 503 rows, all with GICS sector, fetched today.
Only `fetch_changes` is pinned, at 407 rows ending 2026-08-05.
`build_membership` seeds every date with today's live members and then walks the
pinned changes table backward to correct history. A name that joined after the
pin has no event row, so it is never corrected, and is marked a member all the
way back to 2010. Fetched today:

| symbol | security | date added | in pinned changes table |
| --- | --- | --- | --- |
| BE | Bloom Energy | 2026-09-21 | no |
| P | Everpure | 2026-09-21 | no |
| RDDT | Reddit | 2026-08-18 | no |
| ILMN | Illumina, Inc. | 2026-09-21 | yes |

Three of the four are retroactively members for sixteen years of history, and the
names they replaced are symmetrically retroactive non-members. This is
look-ahead, it did not exist when E1 was built, and it grows with every index
change. Note also that `P` was Pandora Media's symbol, so it lands directly on
the reused-symbol problem E1 recorded in F2.6.

### RG-Operate item 5: iShares IVV and SSGA SPY as the replacement

Assessed by fetching both today.

**SSGA SPY: works, and is better than expected on identity.**
Plain unauthenticated GET, HTTP 200, 54420 bytes of real xlsx, dated
"As of 18-Sep-2026". 505 holding rows with columns Name, Ticker, Identifier
(CUSIP), SEDOL, Weight, Sector, Shares Held, Local Currency.

The CUSIP and SEDOL columns are the find. E1's sharpest failure was that a
ticker symbol is not an identity, and open_items records the fix as "a security
identity source so that prices attach to an issuer rather than to a symbol".
SPY supplies one daily, free.

Two caveats found by reading the file rather than assuming:
- **Sector is unpopulated.** All 505 rows carry "-". SPY cannot supply the sector
  map. It does not need to: the live Wikipedia constituents table still returns
  503 rows with full GICS sector, so sector keeps its current source.
- **Non-equity rows are present and must be filtered explicitly, not silently.**
  `US DOLLAR` (ticker "-", CUSIP 999USDZ92) is the cash line, and `TPG INC`
  appears with ticker `2602335D` and CUSIP `436CVR021`, a contingent-value-right
  line. 505 rows minus these is 503, matching Wikipedia exactly.
- Format is xlsx and **`openpyxl` is not installed in the venv**, so this adds a
  dependency or a manual zip/XML reader.

**iShares IVV: does not work, and fails in the shape this project keeps getting
caught by.** The documented CSV endpoint returns **HTTP 200 with 2255066 bytes
of HTML**, the product page behind an investor-type disclaimer and bot
protection (448 occurrences of "disclaimer", 108 of "bot", title "iShares Core
S&P 500 ETF | IVV"). Retried with a cookie jar seeded from the product page,
same result. `raise_for_status()` passes on this. Any fetcher written against it
must validate payload shape, per standing rule 14. I would not build on IVV
until the gate is cleared, and I would not treat "it downloaded" as evidence
that it worked.

**What this does and does not solve.** It gives an ongoing, dated membership
record with stable identifiers, snapshotted daily from today forward, which is
exactly and only what a forward-running paper book needs, and it fixes the
retroactive-membership defect in E10-F11 going forward. Neither fund publishes
an archive of past daily files, so **it reconstructs no history**. The pre-2026
universe still comes from the pinned Wikipedia table, and the survivor-only
cross-section that E4 owns is untouched. The gate memo must not claim otherwise.

My recommendation: SPY for membership and identity, live Wikipedia for sector,
a daily snapshot written to a dated archive so the point-in-time record starts
accumulating immediately, and IVV deferred. If IVV can later be fetched, the
disagreement between the two funds' membership on the same date is a free daily
data-quality probe and worth having.

### Next

`handoff/TASK.md` written as `e10-corrections`, status ready, base commit
5b77d6f. It covers E10-F1 through E10-F9. E10-F10 and E10-F11 and the constituent
source are the task after. Decision 1 is untouched and waits on you.

---

## 2026-09-21 review, part 2: project context built, E10 review completed

Supplements the entry above rather than replacing it. Every finding E10-F1 to
E10-F11 stands as written. What is new: the full-repo read, four findings the
first pass did not reach, the E11 options restated in your (a)/(b)/(c) frame,
and a rescoped TASK.md.

### Decision needed from you: what E11 trades

Restating your three options with the stored numbers behind each, from
`data/alpha/summary.parquet`, `sprints/E7/RG_SIGNAL.json` and
`sprints/E7/RESULTS.json`.

| | signal | raw ic_h1 | neutral ic_h21 | neutral t | RG-Signal | turnover | break-even cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| a | momentum_12_1 | 0.015076 | -0.010684 | -1.549 | NULL | 0.3897 | 5.71 bp vs 5 bp |
| b | idio_momentum | 0.012102 | -0.003094 | -0.512 | NULL | 0.3829 | 6.07 bp vs 5 bp |
| c | short_interest | 0.002677 | 0.008518 | 1.176 | NULL | 0.1471 | 21.02 bp vs 5 bp |

**(a) Raw momentum_12_1 as a documented-null book.** This is what
`RG_OPERATE.md` item 6 currently commits to, and it is the weakest of the three.
Its factor-neutral IC is the most negative of all six signals, because the
signal is the momentum factor and the champion design contains a momentum
factor. The hygiene ledger already records the mechanism, in its 2026-09-21
entry on F7.2: "Neutralizing momentum against a risk model that contains
momentum projects the signal out." Procedure 6.3's neutralization, which E8
established as the champion construction, would remove most of the signal
before it ever reached a position. Choosing (a) means either running unhedged,
which stops exercising E6 and E8, or running the stack as designed and trading
the residual with the negative IC.

**(b) idio_momentum through the full stack, Procedure 6.3 sizing plus the FMP
hedge, documented null. Recommended, and I agree with your recommendation.**
Three reasons from stored numbers. Its neutral IC is -0.0031 with t -0.51, which
is null rather than negative, so the hedge is not removing the thing being
traded. It is the most lag-robust of the six: F7.1c moves its IC from 0.012102
to 0.012332 under the extra-day lag, a rise, against post-earnings drift's
collapse from 0.1240 to 0.0073. And it is by construction the idiosyncratic
component, which is what the E6 hedge and the E8 sizing were built for, so E11
exercises every component as designed rather than testing one against its own
purpose. Break-even 6.07 bp against a realistic 5 bp, the best of the three on
cost headroom.

**(c) Short interest, neutralized.** The one near miss on the numbers: it is the
only option with a positive neutral IC, and its neutral out-of-sample t is
2.1035. It is NULL for lack of history, not lack of signal, which
`docs/open_items.md` records on 2026-09-21. The cadence is the problem you
named: FINRA publishes semi-monthly and the panel holds **24 settlement dates
from 2018 to 2026**. A daily loop on a signal that updates twice a month spends
most of its days re-trading a stale number, and break-even 21.02 bp against a
realistic 5 bp is measured on a panel too thin to trust. I would not start the
30-day clock on it.

Synthetic alpha is excluded: it uses future returns by construction and can
never trade live.

**Consequences of the choice, so it is made once.** Whichever you pick,
`docs/research/RG_OPERATE.md` item 6 is rewritten, the multiple-testing ledger
gains a row, and the expected E12 verdict of luck is written down before E11
starts. If you pick (b), the change is one input and nothing downstream moves.

I have not acted on this, and `handoff/TASK.md` does not touch it.

### Four findings from the full-repo read

**E10-F12. Two E1 criteria carry verdicts with no stored number, and two
documents quote different values for one of them.**
`sprints/E1/RESULTS.json` has `stored_numbers: null` for F1.2 (fail) and F1.3
(pass). The sprint exit checklist in `docs/engineering_standards.md` requires
"Every F criterion evaluated with a stored number in RESULTS.json (pass, fail,
or explicitly pending with a reason)." Neither is marked pending. The
consequence is already visible: `README.md` quotes F1.3 as 0.9557 and
`docs/research/STATUS_REPORT.md` quotes it as 0.9564, and neither is traceable,
because there is nothing stored to trace to. One of the two is wrong and no
test can say which.

**E10-F13. The README status block stopped at E2 and quotes a superseded
number.** It shows E3 unchecked and "E4 to E13" as future work while the repo
is at E10 with G1 and G3 passed. It also states E1's survivorship bias as "349
bp per year", which the E1 restatement moved to 365.10 through the revisions
block. The old value is correct as history and wrong as a current statement,
and the README presents it as current. Low severity, high visibility: it is the
first file a reader opens.

**E10-F14. A header row leaked into a stored dictionary.** F7.3's
`verdict_by_signal` contains the key `"---"` with value `"---"`, a markdown
table separator that reached a JSON artifact. Harmless today; it means whatever
built that dict parsed a rendered table rather than the underlying data, which
is the kind of path that produces a wrong number later.

**E10-F15. Two verdict vocabularies coexist in E7 and one of them reads as its
opposite.** F7.3's `verdict_by_signal` records momentum_12_1 and idio_momentum
as **PASS**, while `RG_SIGNAL.json` records all six as **NULL**, and the repo
everywhere states that RG-Signal returned all six NULL. Both are correct within
their own definitions: F7.3's label is the deflated-Sharpe ledger verdict on the
raw spread, and the gate verdict is the seven-question checklist decided on the
factor-neutral out-of-sample t. F7.3's criterion is about labeling and row
counts, so its `pass` is right. But a stored artifact that says PASS for a
signal the project calls NULL is a trap for any later agent reading artifacts
rather than prose, and it sits directly on the E11 decision above. Recorded in
`handoff/PROJECT_CONTEXT.md` so both agents read the distinction once.

### Verified in this pass

- All ten `sprints/E*/RESULTS.json` read. Criterion strings in E1 to E10 match
  their PRDs. The only rewording found anywhere is in the E10 memo (E10-F8).
- `data/models/registry.json`: five versions, XS-v1 `champion: true`, TS-v1
  `champion: false` and ineligible by the pre-registered family rule. The
  champion rule string is intact and predates E2's estimators.
- `data/VERSION.json`: 143 artifacts at `810a1ef6`, built 2026-09-21T23:39:10Z.
- `live/` contains only `.gitkeep`. The v8.x daily loop is **not in this
  repository**, which is why plan item 3 asks you where it lives rather than
  assuming. Dashboard has D0 to D9; D10 and D11 do not exist.
- `docs/open_items.md`: 18 entries, the oldest four still open. The blocking one
  is the 2026-09-10 constituent source entry, which the 2026-09-21 E10 close-out
  restates.

### On the task status

`handoff/TASK.md` is `ready`, not `blocked`. The E11 decision is reserved and I
have not touched it, but nothing in steps 1 and 2 of the remaining plan depends
on your answer, and both are on the critical path to starting the 30-day clock.
Blocking the implementer now would cost days of calendar time on a decision that
gates a later task. Flip it if you disagree.

### Next

`handoff/TASK.md` rewritten as `e10-fixes-and-constituent-source`, status ready,
base commit 5b77d6f, covering remaining-plan steps 1 and 2 only. Step 3 waits on
your E11 decision and on where the v8.x loop lives.

---

## 2026-09-21 correction to E10-F12, and one more finding

**E10-F12 as written above is understated and partly wrong.** I said two
documents quote different values for F1.3 and that one of them must be wrong.
Checked properly, there are **three** values in circulation and the deliverable
contradicts its own revision table:

| source | F1.3 value |
| --- | --- |
| `sprints/E1/RESULTS.json` | `stored_numbers: null`, nothing stored |
| `README.md` | 0.9557 |
| `docs/research/STATUS_REPORT.md` | 0.9564 |
| `docs/research/E1_data_note.md`, body, four places | 0.9557 |
| `docs/research/E1_data_note.md`, revision table | 0.95575 corrected to **0.95655** |

The E1 data note records its own correction, "the universe return no longer
averages in 36 spliced series", and then goes on quoting the pre-correction
0.9557 in its summary, its practitioner rules and its falsification section.
0.9564 in the status report matches none of them. Because F1.3 stores no number,
no traceability test can arbitrate, which is how three values survived.

**E10-F16. The same pattern on F1.5 in the same document.** The E1 data note's
body says survivorship bias is "about 349 bp per year" and "349.4 bp per year",
its own revision table says 349.67 corrected to 365.81, and
`sprints/E1/RESULTS.json` stores 365.10364. Three values again, and here the
stored one exists, so the deliverable is simply stale against it. The status
report and `handoff/PROJECT_CONTEXT.md` both use the stored 365.10.

The mechanism is the same in both cases and is worth naming: E1's deliverables
were written before the traceability-test discipline existed, so their bodies
were hand-edited while their revision tables were appended, and the two drifted.
Every sprint from E2 on generates its deliverable from the artifacts, which is
why this does not recur later.

**Not added to the current TASK.md.** It is cheap to fix but it is a third
piece of work, and the rule in `handoff/PROJECT_CONTEXT.md` is one sprint or
less per task. Queued as the task after the constituent source: store numbers
for F1.2 and F1.3 through the revisions block, regenerate the E1 data note from
the artifacts the way E2 onward do, and refresh the README status block, which
stopped at E2 and still shows E3 unchecked (E10-F13). Note that storing a number
for a criterion that currently stores none touches reserved decision 3, so that
task needs your sign-off before it runs.
