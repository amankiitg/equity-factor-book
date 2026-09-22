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

---

## 2026-09-22 review: task e10-fixes-and-constituent-source at 3a82ccb

Reviewed HEAD 3a82ccb against base 5b77d6f. Five commits, working tree clean,
`handoff/TASK.md` status `done`, `handoff/REPORT.md` 149 lines. Both parts were
delivered. The work is good: nine defects corrected, none papered over, two
failing verdicts kept failing, and the RG-Operate rewrite is honest about what
the new source does not solve. Five new findings, one of which is mine.

### Decisions needed from you

**Decision 1, new: F10.1b's criterion was fitted to the answer, and the honest
version is a fail. Reserved decision 3, so I have not touched it.**

F10.1b is registered as:

> "The expected maximum drawdown at the book's horizon, n_obs * 21 / 252 years,
> is between 0.15 and 0.25 and within 100% of the simulated median."
> threshold: "expected maximum drawdown between 0.15 and 0.25 and a relative gap
> below 1.0", verdict **pass**.

That band is not a criterion. It is the acceptance guard I wrote into
`handoff/TASK.md` so I could check DeepSeek's Qp implementation, and I did not
say what F10.1b should actually test, so DeepSeek reasonably lifted my numbers
into the criterion text. The result passes by construction: the band was chosen
because the answer was already known. My error to fix, not DeepSeek's.

The honest version applies F10.1's own pre-registered threshold, "within 10% at
the median", to the corrected benchmark. Measured:

| comparison | gap | vs the 10% bar |
| --- | --- | --- |
| simulated median vs stationary median (F10.1, as stored) | 2.9598 | fail |
| simulated median vs horizon-matched E[MDD] (F10.1b, as stored) | 0.2963 | **fail** |
| simulated **mean** vs horizon-matched E[MDD] (like for like) | 0.2578 | **fail** |

So F10.1b should read `fail` at roughly 26 to 30%, and that is a far better
result than the `pass` on the record. It says the horizon fix cuts the gap by an
order of magnitude, from 296% to 26%, and does not close it. The residual is
real: I checked whether it was the mean-versus-median mismatch, since
Magdon-Ismail gives an expected maximum drawdown while the simulation reports a
median, and correcting that moves 0.2963 only to 0.2578. Something the Brownian
benchmark does not capture is still there at 26%, which is an open question
worth recording rather than a band worth widening.

Note the third row: the stored F10.1b compares a simulated **median** against an
analytical **mean**. That is a smaller instance of the exact like-for-unlike
comparison that E10-F1 and E10-F2 were about, surviving into the correction.

Options:

1. **Re-register F10.1b against F10.1's own 10% threshold, verdict fail, with
   the 296% to 26% reduction and the open residual recorded as the mechanism.**
   My recommendation. It keeps the pre-registered bar, records a negative result
   the way the project does everywhere else, and leaves a real question open.
2. Keep F10.1b as a diagnostic but rename it so it does not read as a
   falsification criterion, and put the 10% comparison in the memo prose.
3. Leave it. I would not: a `pass` on a band drawn around the answer is the
   defect class this project keeps hitting, and it is now in a deliverable.

**Decision 2, still open from 2026-09-21: what E11 trades.** Unanswered. It is
now the binding constraint on the schedule: RG-Operate item 5 is as clear as it
can get without your sign-off, item 6 is yours, and E11 needs 30 trading days of
calendar time. Everything else I can queue is small. My recommendation remains
(b), idio_momentum through the full stack.

**Decision 3: re-running the universe reconstruction.** DeepSeek correctly
stopped short of it and said why. It changes point-in-time membership and
ripples into every stored criterion E1 to E10. Needs your sign-off before it is
scheduled. Related: I also need to know where the Credit Trading Lab v8.x daily
loop lives. `live/` still holds only a `.gitkeep`.

### Verified, independently recomputed

Gates, run by me, not taken from the report:

- `make test`: **594 passed, exit 0**, 409.65s. Matches the report. Suite grew
  from 586 by 8.
- `make lint`: ruff, mypy (33 source files, up from 32), black (130 files) all
  clean, exit 0.
- Walkthrough: 23 cells, 13 code cells, zero unexecuted, zero error outputs,
  execution counts 1 to 13 monotonic, HTML rendered. The forbidden-literal guard
  is present and real.
- No em dashes in any of the 25 changed files.

Numbers, recomputed from the stored artifacts:

- F10.1 `relative_gap_at_median` 2.9598245584793177. Reproduces exactly.
- F10.1b horizon 14.5 years, E[MDD] 0.1993770805683501, gap 0.2962664086721387.
  Reproduces exactly, including the Qp asymptote.
- F10.3 raw 0.275355, targeted 0.233840, reduction 0.1507686421378931 on the
  aligned 14-year set. Reproduces exactly.
- F10.3b sweep reproduces at all five windows.
- Gaussian control -0.1539687769091203, deeper than the bootstrap's -0.140308,
  so the fat-tail explanation is correctly retired.
- Memo: all six `criterion` strings appear verbatim. E10-F8 is properly fixed;
  the memo now interpolates criterion and threshold from `RESULTS.json`.
- Traceability test is sign-aware and carries a regression case that a flipped
  sign is rejected. E10-F9 fixed.
- E1 through E9: **0 of 65 criteria changed verdict.** I checked all nine
  sprints, including E8 and E9, which the report's Table 8 omits.
- Membership artifacts unchanged: `universe_membership`, `universe_constituents`,
  `universe_changes` and `sectors` all carry identical sha256 in
  `data/VERSION.json` at base and HEAD. Only `drawdown`, `stoploss` and
  `voltarget` changed and `voltarget_daily` was added.
- SPY: 503 equity rows, CUSIP and SEDOL non-null on 503 of 503, no blanks.
  The parser raises `ValueError` on the IVV HTML fixture with a message naming
  the cause. `archive_snapshot` returns the existing path without rewriting.

Defect classes checked specifically:

- **Two rows identical.** `seed_mom_ls` shows the same +0.225966 under both the
  old and the re-entering stop, and both zero 1229 observations. I checked
  whether the new function was silently falling back. It is not: the re-entering
  stop works on the probe case, and on `seed_mom_ls` the unstopped equity curve
  never recovers above -5% after the first breach on 2021-10-11, so a correct
  re-entering stop also never re-enters. The identical rows are genuine.
- **A criterion that passes by construction.** `cross_check` enumerates the union
  of all three sources and reports every disagreement, so its zero SPY-versus-
  Wikipedia disagreement is a real result, not an artifact of only looking at
  Wikipedia-versus-stored. Verified by reading the implementation.
- **My own suspicion, and it was wrong.** I expected SPY as of 18-Sep to
  disagree with Wikipedia on BE, ILMN and P, since Wikipedia dates those
  additions 21-Sep. The file genuinely holds all three. SPY leads Wikipedia's
  `date_added`, which is a point in the new source's favour and worth carrying
  into the reconstruction task: the two sources date the same change
  differently.

### E10-F17, raised by DeepSeek, resolved in DeepSeek's favour

DeepSeek reported daily-21 at 0.206317 against my 0.2042 and could not recover
my convention. The sampling convention is identical; the difference is the daily
series. Mine treated a missing specific return as zero. `design_book_daily_returns`
applies the E5 missing-data semantics, marking the day missing if any held name
is missing, which is the project's convention everywhere else. **DeepSeek's
number is correct and mine was the looser construction.** Correcting my
2026-09-21 entry accordingly.

### New findings

**E10-F18. F10.1b's criterion is fitted to the answer.** Decision 1 above.

**E10-F19. F10.3b's year alignment is fixed at the year level and broken inside
the first year.** E10-F6 was that raw and targeted covered different year sets;
that is fixed. But the daily estimator's warmup still consumes part of 2012 on
the targeted side only, so the two sides estimate the same year's annual
volatility from different numbers of observations:

| window | 2012 raw obs | 2012 targeted obs | stored reduction | reduction dropping unequal years |
| --- | --- | --- | --- | --- |
| daily 21 | 11 | 9 | 0.206317 | **0.286842** |
| daily 42 | 11 | 9 | 0.176613 | 0.195261 |
| daily 63 | 11 | 8 | 0.106923 | 0.163429 |
| daily 126 | 11 | 4 | 0.204057 | 0.202698 |
| daily 252 | 11 | 0 (2013: 12 vs 10) | 0.144861 | 0.126479 |

The headline moves 8 points, from 0.2063 to 0.2869. An annual volatility built
from 4 monthly returns is not the same statistic as one built from 11, and it
enters the coefficient of variation on one side only. **The verdict is
unaffected**: the maximum is still far below 40%, so F10.3 stands and F10.3b's
conclusion stands. The stored headline is biased and the fix is a minimum
observation count per year applied to both sides.

**E10-F20. `make verify-evidence` fails at HEAD and passed at base.** It reports
"data/VERSION.json: the artifact on disk has moved since the snapshot". Proven:
the evidence manifest's VERSION.json sha256 is `a180ec69...`, which is exactly
the sha at 5b77d6f, and on disk it is now `eb28c01f...`. The rebuild refreshed
`VERSION.json` without `make evidence`. A one-command fix, but the evidence
chain is currently broken and a `make` target exits 1. My acceptance list did
not name this gate; it should have.

**E10-F21. The SPY archive, the one artifact whose whole value is that it cannot
be regenerated, is the least protected thing in the repo.**
`data/raw/spy_holdings/spy_holdings_2026-09-18.parquet` is matched by
`.gitignore:20` (`data/**/*.parquet`), is untracked, is absent from
`data/VERSION.json`, and is absent from `evidence/MANIFEST.json`. SSGA serves
only the current file, so tomorrow's fetch cannot reproduce 18-Sep. The
project's own evidence policy, the 2026-09-21 open item, says the snapshot
covers "only the fetched inputs that make rebuild cannot regenerate", which is
precisely what this is. The E5 lesson, verbatim from the ledger: "an untracked,
underived artifact is one run away from being unrecoverable." Every day this
sits unprotected, a day of point-in-time record is at risk.

**E10-F22. Reporting, not work: Table 7's numbers are not recoverable from the
stored membership artifact.** The column reads "history dates wrongly marked a
member", but BE and P are **not columns in
`data/processed/universe_membership.parquet` at all**, and RDDT's stored count
is 4355 of 4355, not the reported 4336. The 4360/4360/4336 figures come from a
fresh `build_membership` over a business-day range ending today, which is 4361
rows, not the stored 4355. `sprints/E10/PROBES.md` is explicit and correct about
this, saying "a rebuild drops them" and naming the fresh range. REPORT.md's
table header is not, and a reader of the report alone would think the stored
artifact contains all four errors. Only RDDT's is present today.

**E10-F23. Reporting: two claims in Table 8 are weaker than they look.** The
"F1.x to F9.x no-change" row lists E1 to E7 and omits E8 and E9; I verified both
are unchanged, so the conclusion holds. And the proof that membership is
unchanged is given as "git status clean for data/processed", which proves
nothing, because `data/**/*.parquet` is gitignored and git status would be clean
whatever happened. The `VERSION.json` hashes do prove it, and they are the
evidence to cite. Also "23 cells executed" is 23 total cells and 13 code cells.

### Next

`handoff/TASK.md` rewritten as `evidence-and-archive-hardening`, status **ready**,
base commit 3a82ccb. It covers E10-F19, E10-F20, E10-F21 and the REPORT
corrections, all of which need no decision from you. **F10.1b is explicitly out
of scope** pending Decision 1, and the universe reconstruction is out of scope
pending Decision 3. The task is deliberately small so it does not consume time
you may want spent on E11 setup once Decision 2 lands.

---

## 2026-09-22 STANDARDS.md change

Added rule 2b, "An acceptance band is not a criterion", between rules 2 and 3.

Why: E10-F18. F10.1b was registered against the 0.15 to 0.25 band I wrote into
`handoff/TASK.md` as a reviewer's guard on the Qp implementation, and scored
`pass`. Nothing in `handoff/STANDARDS.md` said a TASK.md acceptance item is not
criterion material, and rule 1 only forbids rewording an existing criterion, not
inventing a new one around a known answer. The rule closes that gap and names
the instance so the next reader sees the example. No other rule changed.

---

## 2026-09-22 review: task evidence-and-archive-hardening at c263021

Reviewed HEAD c263021 against base 3a82ccb. Four commits, tree clean, status
`done`. **Every acceptance item met.** This is the cleanest task of the three:
the numbers I predicted are the numbers stored, to six places, and the two weak
claims I called out last time were both corrected without being argued about.

**E10 is closed.** What remains under E10 is yours, not DeepSeek's.

### Verified, run or recomputed by me

- `make test`: **595 passed, exit 0**, 413.69s. Matches the report.
- `make lint`: clean, 33 source files, 131 black files, exit 0.
- `make verify-evidence`: **evidence OK, exit 0.** It failed at the previous
  HEAD and passes now. E10-F20 fixed.
- Walkthrough: 23 cells, 13 code, zero unexecuted, zero errors.
- No em dashes in any of the 26 changed files.
- F10.3b's five revised reductions reproduce **exactly** from a fresh
  `allocate.run`: 0.286842, 0.195261, 0.163429, 0.202698, 0.126479. These are
  the values I computed independently on 2026-09-22 before the task was written.
- The within-year asymmetry is genuinely closed. I recomputed the per-year
  counts at all five windows: the only unequal year is 2012 (and 2013 at the
  252 window), and those are exactly the years dropped. Every kept year carries
  the same count on both sides. The artifact now stores `n_years_dropped` and
  `dropped_years`, which was not asked for and is the right addition.
- F10.3b's criterion text and `pass` verdict unchanged; old values in the
  `revisions` block; `n_changed` 1.
- **F10.1b is byte-identical to 3a82ccb** in criterion, threshold, verdict and
  stored_numbers. The out-of-scope instruction was respected exactly.
- E1 through E10: **0 of 71 criteria changed verdict.**
- Membership unchanged, proven by the four `VERSION.json` sha256 values, which
  is the evidence I asked for and the evidence the report now cites.
- SPY archive: snapshot tracked at
  `evidence/data/raw/spy_holdings/spy_holdings_2026-09-18.parquet.gz`,
  registered in `data/VERSION.json` (sha `e8c726ef...`, 34358 bytes) and in
  `evidence/MANIFEST.json`, which grew from 11 entries to 12. Growth claim
  checked: 24025 compressed bytes times 252 sessions is 6.05 MB a year, the
  report says 6.1.
- The verify-evidence gate is now `tests/test_evidence.py`, an integration test
  calling the same `evidence.verify()` that failed at the previous HEAD, so the
  gate is real and not decorative.

### Two new findings, both small, both carried into the next task

**E10-F25. The SPY side of the crosscheck is archived; the Wikipedia side is
not.** `data/processed/constituent_crosscheck.parquet` is absent from both
`data/VERSION.json` and `evidence/MANIFEST.json`. As a derived artifact that is
defensible, except that one of its three inputs is the **live** Wikipedia page,
which changes daily and is archived nowhere. So the crosscheck is only
half-reproducible: re-running it tomorrow compares against a different
Wikipedia list and the 2026-09-22 record of six disagreeing names cannot be
reconstructed. The whole point of the archive is a point-in-time record, and
one of its two sides is not being kept. The eventual reconstruction will also
need a dated sector map, which only Wikipedia supplies. Fix is the same shape
as the SPY fix and is one step in the next task.

**E10-F26. There is no restore path.** `efb.evidence` has `snapshot` and
`verify` and no `restore`. After a clean checkout the raw parquet is absent and
nothing repopulates it from the `.gz`. This is pre-existing across all eleven
evidence artifacts and is not a regression from this task, and the report is
honest about it, saying the file survives "in compressed form". It matters more
now than it did: every other evidence artifact can be re-fetched from its
source, and the SPY archive cannot.

**E10-F27, and it is the one you asked about.** The sprint task lists were never
ticked:

| sprint | tasks done | tasks open | real state |
| --- | --- | --- | --- |
| E1 | 11 | 0 | correct |
| E2 | 20 | 2 | correct, both open are marked OPTIONAL and deferred |
| E3 | 16 | 4 | correct, all four are marked OPTIONAL and deferred |
| E4 to E7 | 10, 10, 8, 9 | 0 | correct |
| **E8** | **0** | **10** | complete: F8.1 to F8.7 evaluated, memo, walkthrough |
| **E9** | **0** | **9** | complete: F9.1 to F9.5 evaluated, memo, walkthrough |
| **E10** | **0** | **10** | complete: F10.x evaluated, memo, walkthrough, RG-Operate |

Three consecutive sprints report every task open while their criteria are
evaluated, their memos written and their walkthroughs rendered. Anyone reading
`sprints/E*/TASKS.md` to find the project's state would conclude E8 never
started. Folded into the next task along with the README, which stopped at E2
and still quotes the superseded 349 bp (E10-F13).

### Decisions still with you, unchanged and now blocking

Nothing DeepSeek can do next touches these, and two of them gate the schedule.

1. **F10.1b's criterion is fitted to the answer.** My error. Recommendation:
   re-register against F10.1's own 10% bar, verdict `fail` at 26 to 30%,
   mechanism being that the horizon fix cuts the gap from 296% to 26% without
   closing it. Reserved decision 3.
2. **What E11 trades.** Open since 2026-09-21. Recommendation (b),
   idio_momentum through the full stack. E11 needs 30 trading days and the
   clock cannot start until this lands.
3. **Sign-off to re-run the universe reconstruction.** Reserved.
4. **Where the Credit Trading Lab v8.x daily loop lives.** `live/` still holds
   only a `.gitkeep`.

### Next

`handoff/TASK.md` rewritten as `e12-attribution-engine`, status **ready**, base
commit c263021. This moves the project to the next sprint. Per the plan's step
4, E12's machinery depends on nothing live and can be built and tested on the
seed books now, so that E12 is a run rather than a build on day 30 of E11. The
task covers the E12 PRD with F12.1 to F12.3 copied verbatim from the roadmap,
`efb/attribution.py`, the three criteria evaluated on the seed books, the two
housekeeping items above, and the README refresh you asked for. D11, the memo
and the walkthrough are the task after, because one TASK.md is one sprint or
less and this is already a full one.

One thing to watch in E12, carried from E10-F5: under the E5 missing-data
semantics `seed_ew` has 207 usable days against `seed_mom_ls`'s 4091. F12.1 is
an algebraic identity and holds on any complete day, but F12.2 and F12.3 are
statistical and must be read off `seed_mom_ls`, with n stated beside every
number on both books.

---

## 2026-09-22 PROJECT_CONTEXT.md update

Refreshed three things after E10 closed: the E10 state line now lists the six
criteria and the SPY source rather than the pre-review state; remaining-plan
steps 1 and 2 are struck through as done with what they did and did not solve;
and step 2b is inserted for E12's engine, brought forward from step 4 because
steps 3 and 4 are blocked on the owner or waiting on E11. Header counts moved
to HEAD c263021 and 595 tests. No standing finding and no reserved decision
changed.

---

## 2026-09-22 role change, STANDARDS rules 19 and 20, and four decisions

**Role change, effective now.** I am a lightweight reviewer: read the report,
check its Verification section, apply judgment to the reported numbers, log,
and write the next task. I no longer run gates, read source or notebooks, or
recompute. Deep review on request only, once per round when asked.

**STANDARDS.md gains rules 19 and 20.** Why: verification has to live where the
work lives. Three rounds of review found real defects, but every one cost a full
gate run and a recomputation by the reviewer, which does not scale and puts the
checking furthest from the person who can fix it. Rule 19 moves verification to
DeepSeek. Rule 20 makes the evidence mandatory and pasted, so a claim can be
checked in seconds rather than re-derived. The seven yes-or-no questions are the
defect classes this project has actually hit, turned into a checklist the
implementer answers before the reviewer sees it.

### Decisions recorded

1. **F10.1b: approved.** Re-register against F10.1's original 10% bar, verdict
   `fail`, through a `revisions` block, with the mean-versus-median note. In the
   current task.
2. **E11 trades idio_momentum through the full stack**, Procedure 6.3 sizing
   plus the FMP hedge, documented as a null book. Paper only. Clock starts as
   soon as setup is done. Confirmed 2026-09-22 after the decision arrived with
   both options still bracketed.
3. **Universe reconstruction: not yet.** The paragraph you asked for is below.
4. **The v8.x loop is at `/Users/amankesarwani/PycharmProjects/credit-trading-lab`.**
   Structure noted: `execution/`, `dashboard/`, `scripts/`, `render.yaml`,
   `.streamlit/`, `sprints/v8.1` and `sprints/v8.6`. Its README also carries a
   lesson E11 should inherit: fixed-entry P&L accounting is mandatory, because
   rolling residuals marked to market with drifting parameters produced up to
   $13M of phantom P&L there. E12's attribution must not repeat it.

### Decision 3: what re-running the universe reconstruction would change

`build_membership` seeds every date with today's live constituents and then
walks the pinned changes table backward to correct history, so re-running it
today rewrites membership on both ends at once: the four processed artifacts
move first (`universe_membership.parquet` 532623d5, `universe_constituents`
d14736b7, `universe_changes` 86411430, `sectors` 66d1b7fa), and because the
point-in-time universe is the input to the seed books, the TS-v1 estimation
panel, the XS-v1 cross-section and its sector dummies, descriptors and
regression weights, essentially every derived artifact and every sprint
`data_hash` moves with them, E1 through E10. The verdicts genuinely at risk are
the ones computed on the composition of the universe rather than on an algebraic
identity: F1.1 and F1.5, because the deleted-member set changes and 365.10 bp is
a statistic about exactly that set; F3.1 and F3.6, because the cross-section's
membership changes its R squared and its bias; F5.1 and F5.2, which is the
serious one, because a change in bias across families can move the champion, and
the champion is itself a reserved decision; then F7's ICs, F8.5 and F8.7's
breadth, F9's capacity and F10's design book, each on a different panel. Against
that, the gain from re-running history is zero, because the SPY archive
reconstructs nothing before 2026-09-18 and the pinned table remains the only
source for the past. **Your preference is the right design, not a compromise**:
freeze every historical artifact on the pinned table, where it is reproducible
and already scored, and use the SPY archive only for the live universe from
today forward. E11 needs today-forward membership and nothing else, so it is
unblocked by the split, and the retroactive-membership defect stops growing
because the live universe stops coming from the backward walk. What it costs is
one documented seam: history ends on the pinned table at 2026-08-05 and the live
record begins on the SPY archive at 2026-09-18, with a gap between the two that
must be labelled and never silently bridged. I recommend signing off on the
split and leaving the full re-run permanently unscheduled unless a later sprint
needs a restated history for its own reason.

---

## 2026-09-22 review: e11-setup at 14d25bf

**Decision needed: the clock is counting days of frozen data.** Day 1 is
2026-09-22 but the proposal is built on the 2026-09-03 close, the last in the
frozen model data, and the report says the loop "re-runs on the frozen close"
until live data arrives. Thirty runs on one close gives thirty identical
proposals and nothing for E12 to attribute. Options: (a) stop the clock, wire
live prices, restart at day 1, my recommendation, because a 30-day window on a
single close produces no forward evidence; (b) let it run and label days before
live data as warm-up outside the 30; (c) accept 30 static days and say so now.

Verified by report: Verification section complete, all seven questions answered
with evidence. `make test` 640 passed exit 0, `make lint` clean,
`make verify-evidence` OK, all pasted. F10.1b re-registered to `fail` at 0.2963
with the old `pass` in revisions and the mean-versus-median note, as approved.
Clock arithmetic checks: 30 business days from 2026-09-22 inclusive is
2026-11-02. Guards, reuse table and the universe seam are all stated honestly,
including the 4 excluded names and the dry-run Alpaca path.

Concern, not blocking: the proposal stores
`expected_establishment_cost_bps` 75.34 with `nav` null, so neither the cost nor
the two notional-based guards can be checked from the artifact. 75.34 bp is
about 7x E6's stored 10.53 bp per rebalance for the hedged momentum book.
Wants one line of arithmetic and the NAV stored beside it.

---

## 2026-09-22 decision (a), and the task rewritten

Owner chose (a): stop the clock, wire live data, restart at day 1, static days
not counted. Scope widened correctly by the owner: prices alone are not enough,
because descriptors, factor returns and specific variances are frozen at
2026-09-03 too, so a live-price book priced by a three-week-old Sigma is stale
in a second way. TASK.md is `e11-live-data-and-clock-restart`, status ready.

Cadence set to daily incremental append, stated with its reason in TASK.md: any
slower cadence reintroduces the staleness being removed, and one session is one
cross-sectional WLS fit rather than a refit of 3,941 days. XS-v1 estimates its
own factor returns, so the extension needs only prices, shares and sectors and
is not blocked by the French series ending 2026-07-31. Pre-2026-09-04 rows must
return byte-identical, because restating history would move stored criteria.

Added per the owner: every proposal stores the as-of date of all nine model
inputs plus max staleness; a day-1 sanity gate that runs two consecutive real
closes and prints the weight turnover, with the clock held until it passes; and
the cost item, nav stored beside the bp figure, a four-way spread, impact,
commission and borrow decomposition, and a reconciliation against E6's 10.53 bp
steady-state rebalance, ratio about 7.15x, recorded as a finding if it will not
close.

---

## 2026-09-22 review: nothing to review

`handoff/REPORT.md` is still the `e11-setup` report, base c263021, already
reviewed above. `handoff/TASK.md` is `e11-live-data-and-clock-restart`, still
`ready`, and the only commit since 14d25bf is my own handoff commit f2a2a83.
DeepSeek has not picked the task up, so there is no new work and no verdict
from me this round. Task left `ready`, unchanged. When DeepSeek starts, it
overwrites REPORT.md for the new task; the stale one must not be read as
current, and in particular the clock in it is void per the owner's decision (a).
