task_id: e10-fixes-and-constituent-source
status: done
base_commit: 5b77d6f2f8b983cb106304e239a4b2c9b709e49f

## Goal

Correct the nine defects the 2026-09-21 review found in E10's drawdown,
stop-loss and vol-targeting analysis, then stand up an ongoing constituent
source so the blocking RG-Operate item can clear. No verdict changes in either
part: F10.1 and F10.3 stay `fail`, and no F1.x to F9.x criterion moves.

## Before you start

Read `handoff/PROJECT_CONTEXT.md`, then `handoff/STANDARDS.md`, then the
2026-09-21 LOG entries. Four rules bind unusually hard here:

- A criterion keeps its ID and its verdict. A genuinely different measurement
  gets a **new ID** beside the old one (F10.1b, F10.2b, F10.3b), and the
  function the old criterion was scored on is left in place, not edited. A
  stored number that is simply wrong for the criterion as written is corrected
  under the same ID through the `revisions` block, with the old value beside the
  new one, which is how E1 restated 349.67 to 365.10.
- Print the error before editing anything.
- Do not run `make rebuild`. Use `make rebuild-e10`.
- **Part A is finished and committed before Part B starts.** If budget runs out
  inside Part B, commit what works, report Part A in full and Part B's progress,
  and name what is left. Do not leave Part A half done to reach Part B.

---

# Part A: the E10 corrections

## Steps

**A1. Reproduce and record.** Write `sprints/E10/PROBES.md` with a printed
reproduction of each defect, before changing any code: the F10.1 sign identity,
the i.i.d.-not-block bootstrap, the Gaussian control, the unreachable stop-loss
re-entry, the `seed_ew` sample size, and the F10.3 year mismatch. Commit alone.

**A2. F10.1 sign.** In `drawdown_analysis`, compare like with like: take the
magnitude of the simulated median before differencing it against the analytical
magnitude, or carry both as signed drawdowns. Do not wrap the difference in
`abs`. F10.1 keeps its ID, its verbatim `criterion` and its `fail` verdict;
`relative_gap_at_median` moves from 4.959825 to 2.959825 through `revisions`.

**A3. F10.1b, the horizon-matched benchmark.** Leave `magdon_ismail_median`
where it is, since F10.1 was scored on it. Add a function for the Magdon-Ismail
positive-drift expected maximum drawdown as a function of SR **and horizon**,
which is what `sprints/E10/PRD.md` specifies, with the horizon taken as
`n_obs * HORIZON / TRADING_DAYS` years from the same series the simulation uses.
Register F10.1b with its own criterion text naming the horizon requirement, and
store the horizon in years beside the value. Record in the hygiene ledger that
`ln(2) sigma^2 / (2 mu)` is the stationary drawdown median, not a
maximum-drawdown quantity, which is why F10.1's benchmark and its simulation
were never measuring the same thing.

**A4. The fat-tail claim and the bootstrap label.** Add the Gaussian control:
2000 i.i.d. Gaussian paths at the book's own mu and sigma with the same n, and
store its median maximum drawdown beside the bootstrap's. Either make the
bootstrap an actual block bootstrap, or correct every place that calls it
"block-bootstrapped" (the F10.1 note in `RESULTS.json`) to say i.i.d. Delete the
"fat tails and volatility clustering" sentence from the memo and the F10.1 note
and replace it with the mechanism the control supports. Your call which
bootstrap; record the choice and the reason.

**A5. F10.2b, a stop-loss that can re-enter.** Leave `_apply_stop_loss` in
place, since F10.2 was scored on it. Add a corrected implementation that keeps
tracking the unstopped equity curve while flat, so the re-entry test at -5% is
reachable, and score F10.2b on it. Store the stop's state path (entries, exits,
days flat) so the behaviour is inspectable rather than inferred.

**A6. The seed-book sample.** Add `n_obs`, `n_dates_available`, `first_date`,
`last_date` and `stop_fired` to every row of `data/allocation/stoploss.parquet`,
and carry `n_obs` into the memo's stop-loss table. A Sharpe quoted on 207 of
4193 days states that beside itself. Do not change the E5 missing-data
semantics; they are correct. Record in the hygiene ledger that those semantics
delete 95% of a 500-name equal-weight book's days, so any statistic computed on
`seed_ew` under them is a ten-month statistic.

**A7. F10.3 year alignment.** Compute both dispersions on the intersection of
the two year sets and store `n_years` per side rather than one count for both.
F10.3 keeps its ID, its verbatim `criterion` including "more than 40%", and its
`fail` verdict; `dispersion_reduction` moves from 0.122049 to the aligned value
through `revisions`.

**A8. F10.3b, the daily estimator.** Build the design book's daily return series
from the held weights and `data/models/XS-v1/specific_returns.parquet`, and run
the vol target off a daily-return volatility estimate. Sweep the windows in
Table 5 below. Register F10.3b with its own criterion text naming the estimator.
Then correct F10.3's recorded mechanism: the estimator is not the cause, so the
note must say what is, namely that this book's year-to-year realized-volatility
dispersion is not forecastable at this horizon and the 40% bar was written for a
higher-frequency object than a monthly book.

**A9. The two guards.** In `tests/test_e10_memo.py`, match signed values, not
absolute ones, and add a regression case proving a wrong-signed memo number is
rejected. In `sprints/E10/write_memo.py`, stop typing criterion text by hand:
interpolate `criterion` and `threshold` from `RESULTS.json` for every F10.x, and
add a test asserting each stored `criterion` string appears verbatim in the memo.

**A10. Close Part A.** `make rebuild-e10`, re-execute and re-render the
walkthrough with a section per new criterion, refresh `data/VERSION.json`,
append the ledger entries, run `make test` and `make lint`, commit.

## Acceptance, Part A

1. `make test` passes with at least 586 tests; `make lint` clean. The suite
   never shrinks.
2. F10.1 `relative_gap_at_median` = 2.959825, verdict still `fail`, `criterion`
   byte-identical to the PRD, old value 4.959825 present in `revisions`.
3. F10.1b stores a horizon of 14.5 years (n_obs 174 at 21 sessions over 252), an
   expected maximum drawdown between 0.15 and 0.25, and a recomputed relative
   gap below 1.0. If your Qp implementation lands outside that band, stop and
   report rather than adjusting the band.
4. The Gaussian control's median maximum drawdown is stored, is near -0.1540,
   and is **deeper** than the bootstrap's -0.140308. No file says
   "block-bootstrapped" unless the code performs a block bootstrap.
5. `_apply_stop_loss` is unchanged. The new implementation, on
   `[-0.2, 0.5, 0.5, 0.5, 0.5, 0.5]` with threshold -0.10 and re-entry -0.05,
   re-enters: the output is not all zeros after index 0. A test asserts this.
6. `stoploss.parquet` reports `seed_ew` n_obs 207 against n_dates_available
   4193, and `seed_mom_ls` 4091 against 4092, and the memo's table shows n.
7. F10.3 `dispersion_reduction` = 0.150769 to four places (aligned, 14 years
   both sides), verdict still `fail`, `criterion` still contains "more than
   40%", old value 0.122049 present in `revisions`.
8. F10.3b's daily 21-day window reduction = 0.2042 to three places, and the
   maximum across every window swept is below 0.40, so F10.3's verdict stands.
   If any window clears 0.40, stop and report; that would change a verdict.
9. `tests/test_e10_memo.py` fails when a memo number's sign is flipped, proven
   by a test that does exactly that.
10. Each stored `criterion` string for F10.1, F10.1b, F10.2, F10.2b, F10.3 and
    F10.3b appears verbatim in `docs/research/E10_risk_policy.md`, asserted by a
    test. The memo contains no criterion text absent from `RESULTS.json`.
11. The walkthrough is fully executed, in order, no error outputs, no null
    execution counts, and no stored value appears as a literal in its code.
12. No F1.x to F9.x verdict changes. Assert against the stored
    `reference_values` blocks and print the comparison.

---

# Part B: the ongoing constituent source

## Scope limit, read this first

Part B **builds and validates the new source and measures the defect. It does
not re-run the universe reconstruction into the main artifacts.** Re-running it
changes point-in-time membership, which changes the seed books, which ripples
into every stored criterion from E1 to E10. That is a plan-changing event and it
gets its own task with the owner's sign-off. Build the source, prove it, archive
it, quantify what the current one gets wrong, and stop.

## Steps

**B1. Print the defect.** `efb/universe.py:build_membership` seeds every date
with today's **live** members and corrects history backward from the **pinned**
changes table, so a name added after the pin has no event row and is marked a
member back to 2010. Measured on 2026-09-21: BE, P and RDDT are live members
added after the pin with no event row; ILMN is the only one covered. Reproduce
this into `sprints/E10/PROBES.md`, including the count of affected dates per
name and the symmetric case, names removed after the pin. Note that `P` was
Pandora Media's symbol, so it lands on the reused-symbol finding in
`docs/open_items.md`. Commit alone.

**B2. The SPY fetcher.** Add a fetcher for the SSGA SPY daily holdings file. It
fetched clean on 2026-09-21 with a plain unauthenticated GET: 54420 bytes of
xlsx, "As of 18-Sep-2026", 505 holding rows, columns Name, Ticker, Identifier
(CUSIP), SEDOL, Weight, Sector, Shares Held, Local Currency. Requirements:

- **Validate the payload, not the status code.** Per standing rule 14, assert
  the parsed shape (header row present, row count in a sane band, as-of date
  parseable) and raise on a mismatch. A 200 with the wrong body is a failing
  source.
- **Filter non-equity rows explicitly and count them**, never silently. Known
  cases: `US DOLLAR` (ticker "-", CUSIP 999USDZ92), the cash line; and
  `TPG INC` with ticker `2602335D` and CUSIP `436CVR021`, a contingent-value
  line. Log every dropped row with its reason.
- **`openpyxl` is not in the venv.** Add it as a dependency or read the xlsx
  through the zip and XML directly. Your call; record it and the reason.
- Carry CUSIP and SEDOL through to the artifact. They are the point: E1's
  standing finding is that a ticker is not an identity, and
  `docs/open_items.md` names a security-identity source as the fix.

**B3. Record IVV as a failing source.** The documented iShares CSV endpoint
returns **HTTP 200 with about 2.25 MB of HTML**, the product page behind an
investor-type disclaimer and bot protection; a cookie jar seeded from the
product page does not clear it. Do not build on it and do not retry it into a
workaround. Write a hygiene ledger entry recording it as a failing source with
the mechanism, the way the 2026-09-04 FRED DTB3 entry does.

**B4. The dated archive.** Write each fetch to a dated, append-only archive so a
genuinely point-in-time membership and identity record starts accumulating from
today. One file per as-of date, never overwritten. This is the asset: neither
fund publishes an archive of past files, so the record only exists if it is kept
from now on.

**B5. Sector stays where it is.** The SPY file's Sector column is `-` for all
505 rows, so it cannot supply the sector map. The live Wikipedia constituents
table still works and returned 503 rows with full GICS sector on 2026-09-21.
Leave sector on that source and say so in the memo.

**B6. Cross-check and quantify.** Compare the SPY membership on its as-of date
against the live Wikipedia constituents list and against the current stored
membership. Store the three-way disagreement: names in one and not the others,
with the reason where it is knowable. This is the daily data-quality probe the
new source buys, and it is the evidence that RG-Operate item 5 can clear.

**B7. Update the gate and close.** Rewrite `docs/research/RG_OPERATE.md` item 5
with the stored numbers: what the source provides (ongoing dated membership plus
CUSIP and SEDOL), what it does **not** provide (no history; neither fund
archives past files, so the pre-2026 universe still comes from the pinned table
and the survivor-only cross-section is untouched), and what remains before the
item is positive. Correct the item's current wording: the universe is not
"frozen", it is retroactively wrong and degrading, which is worse. Append the
open-items entry, run `make test` and `make lint`, commit.

## Acceptance, Part B

13. The defect in B1 is reproduced with printed rows naming BE, P and RDDT, and
    the count of history dates each is wrongly marked a member across.
14. The SPY fetcher returns a parsed frame with 503 equity rows after filtering,
    matching the live Wikipedia constituent count of 503, with the dropped rows
    listed by ticker, CUSIP and reason. CUSIP and SEDOL are non-null for every
    equity row.
15. The fetcher raises, with a message naming what was wrong, when handed the
    IVV HTML response. A test asserts this against a stored fixture of that
    response. Do not fetch IVV inside the test.
16. The archive holds at least one dated file and a second fetch on the same
    as-of date does not overwrite or duplicate it.
17. The three-way disagreement in B6 is stored, with counts, and the memo quotes
    them from the artifact.
18. `docs/research/RG_OPERATE.md` item 5 states both what is solved and what is
    not, and does not claim history is recovered.
19. No F1.x to F10.x criterion changes verdict, and `data/processed` membership
    artifacts are **unchanged**. Print the comparison proving it.
20. No em dashes in any file touched, in either part.

---

## Stop only if

- Any F1.x to F9.x criterion changes verdict.
- F10.3b clears 40% at any window, or F10.1b lands outside 0.15 to 0.25.
- A fix would require editing an artifact that a stored criterion was scored on
  and that `make rebuild-e10` cannot regenerate.
- The SPY file's structure has changed enough that 503 equity rows cannot be
  recovered, or the endpoint has gone the way IVV has.
- Part B appears to require re-running the universe reconstruction to satisfy an
  acceptance item. It does not; if you think it does, stop and say why.

Everything else you decide and record: the block-versus-i.i.d. bootstrap choice,
the Qp implementation, the daily-vol window carried into the memo as the
headline, the xlsx reader, and the archive's file layout.

## Report back

`handoff/REPORT.md`, every number read from an artifact.

**Table 1, verdicts.** One row per F10.1, F10.1b, F10.2, F10.2b, F10.3, F10.3b:
id, verbatim criterion, threshold, verdict, stored numbers.

**Table 2, revisions.** One row per corrected number: criterion, quantity, old,
new, reason. At minimum F10.1 `relative_gap_at_median` 4.959825 to 2.959825 and
F10.3 `dispersion_reduction` 0.122049 to 0.150769.

**Table 3, drawdown benchmarks.** Simulated median (bootstrap), Gaussian control
median, Magdon-Ismail stationary median (the old benchmark), Magdon-Ismail
expected maximum drawdown at horizon, horizon in years, n_obs, n_bootstrap, and
the relative gap under each benchmark.

**Table 4, the stop-loss.** Per book: book, n_obs, n_dates_available,
first_date, last_date, base Sharpe, Sharpe change under the old stop, Sharpe
change under the re-entering stop, entries, exits, days flat, stop_fired.

**Table 5, the vol-target sweep.** Per estimator and window: estimator (daily or
monthly), window, n_years both sides, raw CV, targeted CV, reduction. Include
monthly 12 aligned and daily 21, 42, 63, 126, 252.

**Table 6, the constituent source.** SPY as-of date, raw row count, equity row
count after filtering, dropped rows with reason, CUSIP and SEDOL non-null
counts, and the three-way disagreement against live Wikipedia and stored
membership.

**Table 7, the retroactive-membership defect.** Per affected name: symbol,
date added, present in pinned changes table, number of history dates wrongly
marked a member.

**Table 8, gates.** `make test` count and exit code, `make lint` exit code,
walkthrough executed-cell count and error count, the F1.x to F9.x no-change
comparison, and proof that `data/processed` membership artifacts are unchanged.

Plus a short paragraph naming every decision you made under "Stop only if" and
why, and any finding this task did not anticipate, with a new ID continuing from
E10-F15.
