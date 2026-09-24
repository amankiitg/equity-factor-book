task_id: e11-store-path-and-ledger-fix
status: ready
base_commit: 190496d

## The owner can pick now. Three things run alongside the choice.

The E11-F9 cycle was good work. The two-part row is at its fixed point, the
beta is split in raw-beta units, D10 derives its label from the artifact and
names the stale book honestly, the status report is corrected, and the
Verification section is complete. **The choice no longer waits on you.** None
of the three items below changes the ranking of the candidate books, so they
run in parallel with the owner's decision. **Do not choose. Do not re-derive
Guard 1. Do not change the live path's construction until the owner picks.**

### E11-F8, the ledger follow-up overclaims: append a correction

The 2026-09-23 follow-up entry in `docs/hygiene_ledger.md` has three problems.
The ledger is append-only, so fix them with a new dated entry that carries the
old values beside the new ones. Never edit the existing entry.

1. **Arithmetic.** The entry says shrinkage accounts for
   `0.1050 - 0.0555 = 0.0495 (47 percent)`. The quantity in the stored columns
   is the residual exposure at each stage, which is the part of the raw beta
   that stage fails to carry. The shrinkage step's increment is therefore
   **0.0555, 53 percent**, which is what REPORT.md's own table says. The three
   increments sum to the total only this way:
   `0.0555 + 0.0526 - 0.0031 = 0.1050`. The ledger's `0.0495 + 0.0526` is
   0.1021 and does not.
2. **"Standardization contributes zero to three decimals" is not what the
   columns show.** `residual_exposure_winsor` is 0.1081 and
   `residual_exposure_standardized` is 0.1050 at min $1,500: -0.0031 there,
   -0.0034 at $2,000, -0.0047 at $3,000 and -0.0031 on the full book, but
   exactly zero on min $5,000 and both top-N rows. The pattern across rows is
   part of what to explain. A regression residual is invariant to an
   affine change of the regressor on the same sample with the same weights. A
   nonzero increment therefore means the standardized stage is not an affine
   map of the clipped stage on that sample: a different cross-section, a
   different weighting, or orthogonalization folded in. Find which, and say so.
   It is small, but it is the prediction E11-F8 told you to check, and it came
   back nonzero.
3. **"Refuted" is not established.** The Vasicek-stage increment regresses
   TS-v1's raw beta, frozen at 2026-09-03, on XS-v1's shrunk beta at
   2026-09-21. It therefore mixes three things: the shrinkage, the gap between
   the TS-v1 and XS-v1 estimators, and twelve sessions of window drift.
   REPORT.md says this; the ledger entry drops it and asserts a mechanism
   ("name-specific through the standard error") that nothing measured. Under
   the identity hypothesis, the whole 0.0555 could be estimator gap. The
   correction entry records the candidate as **undetermined**, with 0.0555 as
   an **upper bound** on what shrinkage contributes. The clip's 0.0526 is a
   clean measurement, because both of its stages are XS-v1 at the same date.

Then split the 0.0555. Recompute XS-v1's pre-shrinkage beta at 2026-09-21
under the frozen XS-v1 specification, **as a diagnostic only**: no artifact is
restated, nothing is stored as a model input, and the specification does not
change. Insert it as a stage between raw and Vasicek. The raw-to-XS-v1-raw
increment is the estimator and date gap, and the XS-v1-raw-to-Vasicek
increment is the shrinkage. Append a second ledger entry with the verdict:
E11-F8 joins the class if the shrinkage increment is near zero, and is
refuted otherwise. Either way, record the measured shrinkage share.

### E11-F11: the live store is wired to the path the LOG ruled out

LOG.md at line 1064, and the TASK.md B1 amendment, settled the connection as
**direct Postgres under `EFB_SUPABASE_DB_URL` with `EFB_DB_SCHEMA=efb`, not
PostgREST**. `render.yaml` and `.env.example` carry `EFB_SUPABASE_URL` and
`EFB_SUPABASE_SECRET_KEY`, which are the PostgREST path. Neither file has
`EFB_SUPABASE_DB_URL`. The owner's deploy steps in REPORT.md use the PostgREST
variables on both services.

This matters for two reasons. PostgREST serves only schemas added to "Exposed
schemas" in the project's API settings. On the project shared with
credit-trading-lab, that is a dashboard change that widens the credit lab's
public API surface, which is a listed stop condition. And the secret key is
the service-role key: it bypasses row-level security on the **whole shared
project**, including credit-trading-lab's data, and it would sit on a public
web service.

1. State, with the code line as evidence, which connection `live/store.py` and
   `live/dashboard_app.py` actually use, and which schema the one-time setup
   creates.
2. If it is PostgREST, move both to `EFB_SUPABASE_DB_URL` and
   `EFB_DB_SCHEMA=efb`, as decided. If that cannot work without a dashboard
   change or a shared-role grant, **stop and report**; the owner moves to Neon
   or Render Postgres.
3. The dashboard only reads. Propose the least-privilege credential for it and
   let the owner decide. Do not create roles or grants on the shared project
   yourself.
4. Say what uses `EFB_SUPABASE_ACCESS_TOKEN`. A management token is
   account-wide, so confirm it never goes to either Render service.
5. `EFB_DRY_RUN` is how the owner will flip the clock on Render. **Unset,
   empty or unparseable must resolve to dry run**, and so must any spelling
   other than an explicit false. Add a test over those cases and paste it.
   Starting the clock by accident through a missing variable is the failure
   this guards.

Update the owner's deploy steps in REPORT.md to match.

### E11-F12: the floor is checked on weights that are not traded

REPORT.md: "every kept name holds at least 20 shares in the renormalized
full-book weights ... but the re-sizing on the kept subset moves about one name
in ten below 20 shares." So the fixed point is computed on weights from before
the subset is re-sized and re-hedged, and the book that trades is a different
vector. The same is presumably true of the dollar rows.

For this task, **measure only**. On every row, report the count of kept names
that end below their floor in the **final** weights (after re-sizing,
re-hedging, renormalizing and quantizing), with the worst shortfall. Do not
change the table.

After the owner picks, the live path implements the chosen construction with
the floor enforced on the final weights, iterated to a fixed point: drop,
re-size, re-hedge, check. Guard 1 is then derived from those weights. That is
the next task, not this one.

### Also

- The report's table dropped total error, net, long/short counts, raw beta,
  post-hedge exposure and idio share for the two new rows. The parquet has
  them. The report is where the owner reads the decision, so it carries every
  decision column, as E11-F7 already required.
- The previous full-run count recorded in LOG.md is 692, not 682. 695 still
  clears it.
- "Neither is close" is the owner's judgment to make. Report the ratio, and
  leave the word "close" to the owner.

### Stop only if

The standing stop conditions below apply, plus: E11-F11 item 2 needs a
dashboard change or a grant on the shared project.

---

## One row to its fixed point, the beta split in the right units, then the owner picks

The restored table is right and reads cleanly. **Do not rebuild it.** Re-run one
row, redo one decomposition in consistent units, add four facts to the D10
report, and correct the status report's last section. Do not choose. Do not
re-derive Guard 1.

**The owner holds the choice for this cycle**, agreed 2026-09-23. Comparing
the two-part row now would compare a one-pass book against fixed-point books.

### First, before anything else: D10 derives its label from the artifact

**Owner instruction, 2026-09-23. The owner will not look at D10 until this
lands.** The registry's `min_position_dollars` is 5000, and the stored
2026-09-21 proposal is "the min $5,000 book". If that proposal predates E11-F4
and E11-F6, it is the 27-name book at gross 0.2734, idio share 0.8631 and max
exposure 0.1458, the one known to be degenerate. The selector's "min $5,000" is
a different book: 99 names at gross 1.0. Showing the first under the second's
label is worse than no page, because the owner would be reading the wrong book
without knowing it.

So the label is **derived from the artifact, never asserted beside it**:

1. Every proposal stores the construction it was built under: the construction
   type, every parameter (dollar floor, share floor, N), whether the floor was
   iterated to a fixed point, kept and dropped counts, kept gross before and
   after renormalization, and the code commit. If an existing proposal lacks
   any of these fields, the page says so on screen ("construction parameters not
   recorded in this artifact") and does not fill them from the registry or the
   table.
2. For every proposal and every selector row, the page displays those
   parameters, the kept count and the gross, read from that artifact. The label
   text is generated from the stored fields. No label is typed into the page.
3. A test builds two artifacts with the same nominal floor, one pre-iteration
   and one post-iteration, and asserts that the page renders two different
   labels with the right kept counts and gross.
4. Report what the header shows for the stored 2026-09-21 proposal after the
   change, quoting the rendered label, kept count and gross.

Whether to regenerate that proposal with the current code is your call. The
labeling rule comes first either way, so the old book can never appear under
a label that isn't its own.

### E11-F9: the two-part row is not at its fixed point

The row reads `252 -> 100` kept and `11.93% -> 1.80%` p90. The iteration only
admits names, so on every other row post is at least pre. Here the two columns
mean "before the share floor, after it", and the share leg has no fixed point
shown. The status report describes only the four dollar floors as iterated. This
is E11-F6 again, on the one row the owner's decision rule reads, and it biases
that row's n_eff **down**, the number the rule turns on.

Apply the combined floor to a fixed point: name i is kept when
`|w_i| * NAV * scale >= max(1500, 20 * price_i)`. That is a single ordering, by
`|w_i| / max(1500, 20 * price_i)`, so the prefix method from the dollar rows
carries over unchanged. Report one-pass and fixed-point values for every column,
and relabel so pre and post mean the same thing on every row.

State this bound in the report: at the fixed point every kept name holds at
least 20 shares, so if per-name error is relative to the name's target, as the
1.80% suggests, no name rounds by more than 0.5 / 20 = 2.5%. The iteration can
move p90 toward 2.5% and not past it. That is why the row is worth finishing:
breadth comes back without giving up the property that made it stand out.

Optional, flagged for the owner's veto: one row with the 20-share floor alone
and no dollar floor, at its fixed point, same columns. It tests whether the
$1,500 leg does any work once the share leg bounds the error.

### E11-F8 stays open: the split is drawn in the wrong units

The measurements are the right ones. The split drawn from them is not.

1. **Exposure to a stage is not a contribution.** A shrinkage with a common
   weight `k` is affine, `v = k * b + c`, and with net dollar zero it multiplies
   the exposure by `k`: the book's exposure to `v` is `k * 0.105` whatever `k`
   is, and nothing has been explained. The pre-win to raw ratio is 0.41 to 0.45
   on six of seven rows (0.36 on top-N 150). A near-common slope would produce
   exactly that, so the 0.059 now credited to Vasicek shrinkage may be only a
   change of units.
   Put every stage in raw-beta units. For each stage X (Vasicek, clipped,
   standardized, the finished descriptor), regress raw beta on X across the
   cross-section and with the weights XS-v1's fit uses. Then report the book's
   exposure to the regression residual. That residual exposure is the part of
   the 0.105 the stage fails to span. It runs from 0 at raw to the full residual
   at the descriptor, and each stage's increment is its contribution.
2. **Two steps should contribute zero, and saying otherwise needs a
   measurement.** Standardization is affine, so by the algebra already in
   E11-F8 it contributes exactly nothing. The report nonetheless lists it among
   the steps that "take the rest to zero". Orthogonalization against
   descriptors that are themselves hedged factors also contributes nothing,
   because the hedge zeroes those too. What remains are the non-affine steps:
   name-specific shrinkage weights, the 3 MAD clip and the fills. The algebra
   predicts that every stage after the clip carries zero exposure, apart from
   zero-filled names, so the whole residual arises at or before the clip.
   Check that prediction. If standardization or orthogonalization measures
   nonzero, that is its own finding.
3. **The zero fill is a second fill, uncounted.** The report fills names absent
   from the descriptor cross-section with 0 in z. The hedge cannot see those
   names' betas, so they land entirely in the residual. Per row, report how
   many there are and the residual raw beta excluding them, exactly as for the
   median fill.
4. **Say which raw beta.** Is the "raw beta" column XS-v1's own pre-shrinkage
   estimate, with the same window and market proxy, or TS-v1's? If TS-v1's,
   start the chain from XS-v1's pre-shrinkage beta and report the gap between
   TS-v1 and XS-v1 as its own line. That estimator mismatch was half of
   E11-F8's original hypothesis.
5. **Add the full 499-name book as a reference row.** If it also carries about
   0.1 raw beta, the residual is the signal's tilt and no construction choice
   changes it. If it is near zero, dropping names creates it.
6. **Rewrite the mechanism sentence to match whatever this shows.** Drop
   "exactly as the owner read it" unless the numbers put the residual where the
   owner put it. The conclusion is not in question: the hedge neutralizes a
   transformed descriptor, and the residual is what that descriptor does not
   span. What is open is which step fails to span it. STANDARDS rule 3.
7. **Append the follow-up to the hygiene ledger.** The 2026-09-23 entry
   records E11-F8 as a candidate fourth instance of "a number that is an
   identity", beside F4.1, F7.2 and F8.4. Append a new dated entry either way.
   If the residual exposure at the Vasicek stage is near zero, E11-F8 joins the
   class; say so with the number. If not, record the measured share that
   shrinkage explains, and state that the candidate is refuted. Never edit the
   2026-09-23 entry.

### D10: say what the owner will actually see

1. **The label.** Covered by the first section above.
2. **Name the seven panels and the stored field each drew from**, as 17d
   requires. The absence of the string "No data yet" does not show that a
   panel drew from the proposal. A dry run has no fills, so there is no P&L,
   realized vol, Sharpe or drawdown yet. Say what the tracking panel shows.
3. **What would a Render deploy show today?** D10 reads the local proposal
   directory. Is that directory in the repository Render builds from? If it is
   gitignored, the deployed page stays empty until the Supabase read is wired,
   "deployment-ready" is not yet true, and the report says so. Then list the
   owner's steps exactly: which services, which environment variables each one
   needs (a read-only dashboard should need no Alpaca keys), and any one-time
   schema setup.
4. **Confirm the local command.** The reviewer gave the owner `make dashboard`,
   which runs `streamlit run dashboard/app.py --server.headless true` at
   http://localhost:8501. If the owner needs anything else to reach D10 (a
   tab name, an environment variable, a data file), say so in the report.

### E11-F10: the status report's last section contradicts settled decisions

The "What comes next" section of `docs/research/STATUS_REPORT.md` has four
problems:

- "sign off on the universe reconstruction" contradicts the owner's 2026-09-22
  decision: the reconstruction is **not** scheduled and the universe stays
  split. Remove it.
- "E11's remaining work is the owner's" is wrong. Guard 1 against the chosen
  construction, the sanity gate on two real closes and the Supabase wiring are
  the implementer's, and they come before the flip. List remaining plan item 4
  in its order.
- "The dashboard is deployment-ready" claims more than has been verified. Say
  what was verified: the page renders locally, reads local state, and is not
  deployed.
- "the realized-beta column was decomposed before the owner read it" holds only
  once E11-F8 closes. Recheck it then.

The traceability test cannot catch any of these, because none of them is a
number. Read the prose against PROJECT_CONTEXT.md's "Decisions the owner has
made".

### Verification, four corrections

- **Item 1 is answered "no" with an evidence line the table contradicts.** Idio
  share is 1.0 and net dollar is zero on all seven rows, and top-N 150 and 200
  both read 0.135 raw beta. The honest answer is yes, with the reason: the
  first two hold by construction of the exact hedge and the net column. Rule 20
  exists to catch a "no" that the table contradicts.
- **Item 2 cites "effective equals kept everywhere, stated above"**, but it is
  not stated above. Add the effective-count column or paste the check.
- **Paste `git diff --stat` raw**, including the summary line. This one was
  reformatted. The contents match, but a reformatted paste is a summary.
- **Headline numbers need the column and row key**, not only the file. Also
  name the one skipped test and why it skips, which has been outstanding since
  e11-live-fixes. Cite rule 21 for the count: 692 against the previous full run
  of 682.

### Then the owner picks

Present the table with the two-part row at its fixed point and the beta
decomposition in raw-beta units. The owner's rule, stated before the numbers:
if the two-part floor's n_eff is close to min $1,500's, it wins outright. **Do
not choose. Do not re-derive Guard 1 until the construction is picked.**
`dry_run` stays `true`.

---

The sections below come from earlier cycles. Their standing rules still bind:
credentials, stop conditions, acceptance items and `dry_run`. Their superseded
specifics do not, such as the $10m NAV path and the 670 floor. Where anything
below conflicts with `handoff/PROJECT_CONTEXT.md`, PROJECT_CONTEXT.md wins.


## Ahead of the construction choice: deploy the dashboard now

**Owner instruction, 2026-09-23.** The owner wants to look at an actual book
before picking a construction, not after: its names, weights, exposures, hedge
and per-trade reasons. So the Render app and D10 move **ahead of the choice**,
and the table work continues in parallel. The choice waits on both.

Show the existing dry-run proposal for the **2026-09-21 close**. `dry_run` stays
`true`; nothing here starts the clock.

**Label what is on screen.** The stored proposal reflects whichever floor was
last applied, so the page must state, prominently, **which construction it is
rendering** and with what parameters. A page that shows a book without naming it
invites the owner to judge a construction they did not intend to look at, and one
of the candidates we already know is degenerate.

**Recommended, and the thing that would actually serve the stated goal: put a
construction selector on the page.** The table already computes seven books. If
D10 can render any row, the owner can page through min $1,500, min $2,000, the
two-part floor and the rest, seeing names, weights, exposures, hedge and trade
reasons for each. That turns the dashboard into the decision surface instead of a
static view of one arbitrary book. Build it if it is cheap; say so if it is not.

**What needs the owner.** Previous reports state the deploy needs the owner's
Render, Supabase and Alpaca credentials. Get the app deployment-ready and verify
it renders locally against the stored proposal with every panel populated, then
say exactly what remains for the owner to do and what you could not verify
without it. Do not treat a locally rendering page as a deployed one.


## Two findings, then the owner picks. Plus the status report.

The cycle was good: net is structurally zero, the iteration behaved as predicted,
the $5,000 reversal is correctly diagnosed, and the two-part floor cut p90 6.6x.
**Do not rebuild the table again.** Restore two things and decompose one number.

### E11-F7: the rerun dropped the columns the decision rests on

The previous table carried **n_eff, breadth naive, breadth governing, total
error, post-hedge max factor exposure and idio share**. The rerun dropped all
six. Those are what the choice turns on: min $1,500 keeps 252 names and the
two-part floor keeps 100, and **that trade cannot be read without n_eff and the
governing breadth ratio**. Post-hedge exposure and idio share are how the
rank-deficiency failure is detected at all; the report asserts no row degenerates
but shows no exposures.

Restore all six columns on all seven rows, beside the new ones. One table, every
column, so the owner reads the decision off one row.

### E11-F8: the realized-beta explanation does not follow

The report says the book "carries about a tenth of a unit of raw CAPM beta,
because the raw betas are not all 1.0". That does not follow. Write
`beta_i = m + s * z_i`. Then net beta is
`m * sum(w_i) + s * sum(w_i * z_i)`, which is `m * net_dollar + s * (z-beta
exposure)`. Net dollar is zero on every row and the FMP hedge zeroes the z-scored
beta exposure, so **both terms vanish and the level `m` is irrelevant**. A
residual of 0.105 to 0.147 therefore needs a different explanation.

**The owner's reading, and it is a modelling point, not a bug.** XS-v1's beta
descriptor is winsorized at 3 MAD, orthogonalized and z-scored, so the FMP hedge
neutralizes **a standardized rank, not the CAPM beta**. Whatever the
winsorization clipped, and whatever dispersion the standardization compressed,
survives the hedge. State it that way in the report: the residual is what the
descriptor does not span, which is a property of the design, not a defect in the
hedge.

Two candidates, both testable:

1. **The median fill.** Missing names are filled at the cross-sectional median
   0.691. Report **how many names per row were filled** and the residual beta
   with those names excluded. If the fill is doing most of the work, the column
   is measuring the fill, not the book.
2. **Model mismatch, the likely answer.** Test it directly: **recompute net beta
   using the pre-winsorization, pre-standardization beta values** and report how
   much of the 0.105 to 0.147 that accounts for. Also report the correlation
   between the raw beta and the finished descriptor, and the residual beta
   computed against XS-v1's own beta descriptor, so the gap between the two is
   measured rather than asserted.

Decompose it before the owner uses the column. The owner asked for realized beta
precisely because it is the measure the risk model cannot see, so it has to mean
what it claims.

### Also: `docs/research/STATUS_REPORT.md` is four sprints stale

It still covers E1 to E3 as "what this report covers" while the repository is at
E11 with a live paper loop. Bring it current, in the same voice and structure:
what the project is, the plan, what has actually been built through E11, the
findings, blockers and limitations, what the process taught, and what comes next.

**Every number read from an artifact**, with a traceability test in the shape of
`tests/test_e10_memo.py`, matching on the signed value. Two specifics to correct
while you are in there: the E1 survivorship figure is **365.10 bp**, not the 349
the older documents carry, and the three gates now have answers (RG-Data and G1
and G3 passed, RG-Signal returned all six NULL, RG-Operate not cleared).


## Run this cycle, then the owner picks

Owner approved 2026-09-23: the share-count diagnostic and the two-part floor row
are in, and the iteration direction is to be measured both ways. Run it.

The table is built and is good work. The min-position rows dominate top-N on both
n_eff and total error at matched name counts, so top-N is out. **Do not rebuild
the table from scratch**; add two columns and rerun it.

### E11-F5: there is no net-exposure column, and the sides are lopsided

Long/short counts: 90/118 at min $1,500, 63/92 at $2,000, **24/58 at $3,000**,
11/16 at $5,000, 55/95 at top-N 150, 72/128 at top-N 200. Dropping names
asymmetrically and then renormalizing **gross** to 1.0 does not preserve **net**
zero, and net dollar is a first-order risk for a book whose whole claim is market
neutrality. The post-hedge factor exposures being 1e-15 does not settle it: the
FMP hedge zeroes modeled factor exposure, not net dollar.

**Report net three ways on every row**, post-renormalization and
post-quantization:

1. **net dollar as a share of gross**
2. **long count against short count**
3. **the realized beta of the kept book against the market factor**

The third is the one that says whether the lopsidedness costs anything: a dollar
imbalance in low-beta names is a different object from the same imbalance in
high-beta names. Report all three; do not collapse them.

If a row's net is material, say what would restore it: a net constraint in the
re-sizing, or a different floor. **If the 24/58 and 55/95 style counts survive
the re-run, those rows are disqualified regardless of breadth.** The residual is
real dollar directionality the risk model cannot see, which is exactly what the
FMP hedge does not address.

### E11-F6: the floor is applied before renormalization, so it bites harder than stated

At min $1,500 the kept gross is 0.7515, so renormalizing scales by 1.33x and the
true post-renormalization minimum is about **$1,996**, not $1,500. Every row is
therefore conservative on breadth: names were dropped that would have cleared the
floor once the survivors were scaled up.

Apply the floor **iteratively to a fixed point**, and report the kept count both
**pre-iteration and post-iteration** so the breadth bought back is visible rather
than absorbed.

**The direction matters, and it is the opposite of the intuition.** The iteration
works by **admitting names back**: a name worth $1,200 pre-renormalization is
worth about $1,596 after a 1.33x scale-up and now clears a $1,500 floor. Admitting
it raises the pre-renormalization gross, which **lowers** the scale factor, which
makes every existing survivor **smaller**, not larger. So:

- breadth **rises**, which is the point
- the smallest positions get **smaller**, and new names enter sitting exactly at
  the floor
- so the per-name error tail, p90, will most likely **widen, not narrow**

The owner's expectation was that the iteration would lift the smallest survivors
and narrow the gap. It lifts the floor's reach, not the survivors. **Report p90
before and after the iteration on every row** so the direction is measured rather
than assumed. If p90 does widen, the choice is a genuine trade and the table
should say so plainly.


### A diagnostic that may dissolve the trade, flagged for the owner's veto

The dollar floor is probably the wrong instrument for the error tail. Whole-share
error depends on the **number of shares**, not the dollars: a $2,000 position in a
$20 stock is 100 shares and rounds to 0.5%, while the same $2,000 in an $800 stock
is 2.5 shares and rounds to 20%. A dollar floor treats those identically, which is
why min $1,500 can hold every name above $1,996 post-renormalization and still
carry a 9.08% p90.

So add, per row: the **median and 10th-percentile share count**, and a one-line
statement of what actually drives the p90 tail, small positions or high-priced
names. If it is price, the dollar floor is buying error control at a breadth cost
it does not need to pay.

And add **one extra row**, flagged so the owner can veto it: **min $1,500 dollars
AND a minimum share count of about 20**. If that row keeps most of min $1,500's
breadth while cutting p90 toward the $2,000 row's 5.59%, the owner's trade between
10.5% more IR and a fatter tail dissolves, and the answer is a two-part floor
rather than a bigger dollar floor. Same columns as every other row.

### Two small reporting items

- The "gross after renormalization" column is missing because it is 1.0 on every
  row. Say that rather than omitting it silently.
- The report cites the "670 floor", which rule 21 replaced with the relative
  rule: the full-run count must be at least the previous full-run count recorded
  in LOG.md, which was 680. 682 satisfies it and the removed test is named, so
  the rule is met; cite the rule that is in force.

### Then the owner picks

Rerun the table with the net columns, the iteration and the share diagnostic, and
present it. **The owner will not choose until the post-iteration table exists**,
because the p90 gap of 9.08% against 5.59% is large enough that the book held
differs noticeably from the book the risk model priced, which resurfaces as bias
in E12's attribution. My earlier provisional lean to min $1,500 stands only if the
net column clears it and the tail is addressable; the share-count row may replace
the question entirely.

**Do not choose. Do not re-derive Guard 1 until the construction is picked.**


## READ THIS FIRST: what is already done, and what this task is

The five fixes landed at ea821bc and are **not** to be redone: Fix 4 refuted,
Fix 1 filed as E11-F1, Fix 2 cap 0.40 to 0.10, Fix 3 NAV fallback removed, Fix 5
shares clamped to the close. Good work; leave them.

The previous run used an **older version of this file**. Three things changed
after it started and are now the task:

1. **NAV is $1,000,000, final.** Alpaca's paper funding field is capped at
   "$1 - $1,000,000", confirmed in the dashboard. Stop treating the $10m reset as
   pending: it is closed. Delete the $10m column from the reporting and do not
   size anything against it.
2. **The construction table is the decision** and was not built. It is the
   substance of this task. Specification below, unchanged.
3. **Slow-test markers** (Addition 5) were not done. Still wanted.

### Three findings from the review, to fix inside this task

**E11-F2. The kept book's average target dollar size is divided by the wrong
name count.** The report gives $547.81, which is `0.2734 x 1e6 / 499`. The kept
book has 27 names, so the figure is `/ 27` = about $10,126, an 18.5x
understatement. The gross-error metric beside it used the right positions, so
this is the reporting row, not the calculation. Fix it and check every other
per-name average for the same denominator slip.

**E11-F3. `sprints/E5/RESULTS.json` changed and the report does not say why.**
The diff shows 6 lines changed while Table 8 reports E5 at 0 verdicts changed.

**This is a stop, not a finding to carry forward.** Per STANDARDS rule 22, added
2026-09-22: an unexplained change to any stored-criteria file halts the task. If
it is a `data_hash` bump carried by the registry edit, record it through the
`revisions` block with both hashes and continue. **If anything else moved, stop
and report before doing anything else.**

**E11-F4. The book is never renormalized after dropping.** Kept gross is 0.2734,
so the book is 27% invested: it cannot meet the vol target, and the kept-book
quantization error of 0.57% is measured on positions smaller than would actually
trade. Renormalize to gross 1.0 after dropping, then quantize, as the table
specification requires.

**Watch this when you renormalize:** Guard 1 is now 0.10 of NAV and the largest
kept weight is 0.0326 at gross 0.2734. Renormalizing 27 names to gross 1.0
scales weights by about 3.66x, putting the largest near 0.119, which **breaches
the 0.10 cap on a legitimate book**. Re-derive Guard 1 against post-renormalization
weights, not pre. The guard must clear the largest legitimate target of whichever
construction the table selects.

### Also outstanding

- The 1 skipped test in the full run is not named. Name it and say why it skips.
- The construction table's rows must each report post-hedge exposure and idio
  share, which the 27-name result shows is the binding constraint: idio share
  0.8631 and max exposure 0.1458 at 27 names, against 1.0 and 5.8e-15 at 499.
  The rank prediction held; carry it into every row.

## NAV is $1,000,000, final. The construction table is the decision.

Settled 2026-09-22. **Alpaca's paper funding field is capped at "$1 - $1,000,000",
confirmed in the dashboard**, so option (a) is closed by a platform limit and the
documentation suggesting an arbitrary reset balance is stale. **We stay on
Alpaca**: switching brokers to buy breadth would mean rewriting the execution
layer to solve a sizing problem a parameter solves.

The dry run at $1m with a $5,000 floor kept **27 names of 499, gross 0.27**, and
breadth from about 460 to 27. That is not the book E8 constructed and E12 would
attribute almost nothing. So the threshold is no longer a contingency: **build the
table, the owner picks from it.**

### The table, at $1m on one close

Rows: minimum position size of **$1,500, $2,000, $3,000, $5,000**, plus two rows
for a different construction, **top N by alpha at N = 150 and N = 200**.

Columns, per row:

- kept names, dropped names
- **kept gross before renormalization and after**
- per-name quantization error **distribution: median and 90th percentile**, not
  only the total
- total gross error as a share of NAV
- **post-hedge max absolute factor exposure and idio share**
- **maximum post-renormalization weight**, as a share of gross
- both breadth numbers: naive `sqrt(460 / N_kept)` and the measured
  `sqrt(n_eff_full / n_eff_kept)` with n_eff computed the way E8 computes it

The maximum post-renormalization weight is what Guard 1 needs anyway, and it puts
**concentration beside breadth and error** so all three trade-offs are visible in
one row. A row can look good on breadth and error and still be a book nobody
would run.

### Four specification points, without which the rows are not comparable

**1. Renormalize to gross 1.0 after dropping, then quantize.** Gross 0.27 is the
tell that the previous run dropped names and left the book 27% invested. An
under-invested book cannot meet the vol target and its quantization error is
measured on positions smaller than the ones that would actually trade. So each
row drops, **renormalizes to gross 1.0**, then quantizes, and quantization is
reported **after** renormalization. Report kept gross both ways so the effect of
the renormalization is visible.

**2. Re-run the hedge on each subset.** The exact FMP hedge was computed on 499
names. Dropping names breaks it, so each row recomputes the hedge on its own
subset and reports post-hedge exposure and idio share. Without this the rows are
books with different factor neutrality being compared on error and breadth.

**3. Expect the $5,000 row to fail on rank, not on breadth.** XS-v1 estimates
about 18 factors, 7 styles plus 11 sectors plus the market. A 27-name book
hedging 18 factor exposures has 9 free dimensions left, so the FMP hedge is
close to rank-deficient and the "idio book" stops being idio. **A practical floor
on N is a healthy multiple of the factor count, not the quantization arithmetic.**
If a row cannot hedge, say so and report the exposure it actually achieves rather
than dropping the row.

**4. Define top N by alpha for a long/short book.** "Top N by alpha rank" is
ambiguous when the book is two-sided. Use **N names by absolute alpha, with the
sign of alpha setting the side**, so net stays near zero, then size the subset
with Procedure 6.3 and hedge it. State the long and short counts per row.

### How the two approaches are compared

**Dominates** means: strictly better or equal on **both** the measured n_eff and
total gross error, at comparable kept gross after renormalization. If top-N
dominates, it is the better answer and the minimum-position rule becomes a
**floor on top of it** rather than the whole mechanism. If neither dominates, say
so and present the trade rather than picking.

The owner picks from the table. Do not choose.

### Preconditions for the clock, unchanged

Threshold or construction chosen by the owner, gate reruns on two real closes
with `dry_run` still true, the Render dashboard live and showing a real dry-run
proposal, then the owner flips `dry_run` once and that act starts day 1.

### Addition 1: the quantization finding is not re-drawn

The breach gets its ID and **stays a finding at $10m too**, with the new numbers
stored beside the $1m ones, whatever they show. **The bar is not re-drawn to fit
the new NAV**: 0.5% of gross, or 5% of names on either leg, as written before any
number existed.

Reviewer's note on where to look: the error is driven by the **smallest**
targets, not the average, because a $19,400 average is 97 shares of a $200 stock
while a 0.02%-weight name is still only about $2,000. So report the **distribution**
of per-name rounding error, not just the total and the worst case, and report the
zero-share count against the smallest-weight decile. A total that lands under the
bar while the small tail is badly quantized is still worth stating.

### Addition 2: WITHDRAWN

The sigma hypothesis was tested and refuted, see Fix 4 below. **No sigma fix, no
E9 revisions, no E10 revisions, no memo or walkthrough re-execution, and the E6
cost reconciliation stays as stored at 2.56x.** The cascade warning that stood
here is withdrawn with it: nothing in `efb/costs.py` is being changed, so nothing
propagates to E9 or E10.

### Addition 3: a failed NAV read is a failed run

No fallback. A guard that silently restores design thresholds after a failed
account read **reports healthy while being blind, which is worse than no guard**.
A failed NAV read fails the run with a logged reason and **no orders**. Fix 3
below is amended accordingly: the `nav_source: fallback` option is withdrawn.


### Addition 4: the minimum-position item is promoted to now, and closed

This decision promotes the minimum-position open item from inherited to done.
**Close it with this decision** rather than appending it as a later item: state
in `docs/open_items.md` that E8's construction stack lacked a minimum-position
concept, that E11 now carries one as a registry parameter, and that a later
sprint revisiting construction should fold it back into E8 itself rather than
leaving it only in the live path. That last part is the residue, and it is small.

### The breadth consequence, and the formula to use

Effective breadth falls from roughly 460 names to whatever the threshold leaves.
The owner's bound is `sqrt(460 / N_kept)`, which at 200 names is 1.52, an IR
about 34% lower. **Record that as the naive N-based bound, and then measure the
one that governs.**

The fundamental law uses **N_eff**, not N, once forecast errors co-move, and E8
measured `n_eff` at about **140 against n_names about 460** (F8.5, F8.7). N_eff
is limited by residual co-movement, not by name count, so dropping the
smallest-weight tail may barely move it and the true haircut may be far smaller
than 1.52. Compute `n_eff` for the kept book the way E8 computes it and report
**both**: the naive `sqrt(460 / N_kept)` and the governing
`sqrt(n_eff_full / n_eff_kept)`. If the two disagree materially, that is the
answer to the question the open item was going to ask, and it belongs in the
report.

This is a documented null book, so no expected return is lost either way. What
must not happen is an E11 number meeting an E8 transfer coefficient without
stating that the executed book's breadth is reduced and by how much.

### Addition 5: mark the slow tests and split the paths

Per STANDARDS rule 21, added 2026-09-22 because 640 tests on every step is the
bottleneck. Mark anything over about two seconds with a pytest marker for the
slow path, so the fast subset is the default and the full run is deliberate.

Report the split: tests on each path, and how long each path takes.

Two things to get right. **The suite still never shrinks**, so a full run must
still execute everything; report the full-suite count and it must not fall below
670. And **verify the shared-module set by import graph** rather than trusting
the list in rule 21: `build`, `evaluate`, `costs`, `risk`, `size` and `models/`
are named there, but `registry`, `evidence`, `perf`, `universe` and `cov` also
look widely imported. Record the measured set; it is the trigger for a required
full run.

For this task specifically, a full suite is required anyway before `done`, and
again before anything touches the clock.

### Sequencing, revised: the flip starts the clock

**`dry_run` stays `true` for the whole of this task. DeepSeek never flips it.**
Day 1 is no longer set by a gate pass; it is set by the owner flipping `dry_run`
to `false` once, deliberately. That act starts the clock.

The order, and **Part B now comes before the clock, not alongside it**:

1. Fixes 1, 2, 3 and 5 land. Fix 4 is withdrawn. The share-count look-ahead is
   fixed here, not deferred.
2. **NAV settled.** The owner is attempting an Alpaca reset to $10,000,000,
   which the documentation says sets an arbitrary balance. If it succeeds,
   option (a) stands and the minimum-position threshold is sized against $10m
   instead of $1m. **Build the threshold to work at either NAV**: it is a
   registry parameter read at run time, never a constant tied to one balance,
   and the report states which NAV it was exercised at and what it gives at the
   other.
3. **The sanity gate reruns on two real closes, with `dry_run` still `true`.**
4. **Render deployed, and the D10 dashboard confirmed** reading from Supabase.
   This is now a **prerequisite for the clock**, not something built while the
   clock runs.
5. The owner flips `dry_run` to `false`. That is day 1. `live/clock.json`
   records the second void of the 2026-09-22 start, with its reason, and takes
   its new day 1 from the flip.

**What the dashboard must show before the owner will flip.** The dry-run
proposals it has already produced, rendered. A page that has never displayed a
real proposal is not confirmed working. So D10 must render a full day's actual
dry-run output, every panel populated from a stored proposal rather than from a
placeholder or an empty frame, and the report must show what it rendered: the
proposal date, which panels drew, and any panel that had no data and why.

## Goal

Get the loop onto live data and restart the clock (Part A), then put it on
Render behind a light, explainable live dashboard the owner can read from
anywhere, with state that survives a restart (Part B). The loop runs
indefinitely from now on; the thirty days become a reporting window, not the
life of the book.

## Standing decisions. Build on these, do not revisit.

- **`idio_momentum` through the full stack**, Procedure 6.3 plus the exact FMP
  hedge, documented null book.
- **PAPER ONLY.** "Live" throughout this task means live data and a
  continuously running loop, never real money. Real money remains a reserved
  decision the owner has not made. Alpaca **paper** keys only, never committed.
- **Alpaca: read the credit-trading-lab setup and decide there**, see B0.
- **NAV is $10,000,000 if Alpaca allows it, otherwise $1,000,000 with a minimum
  position size.** Read from the account, never hardcoded; a failed read fails
  the run. See below.
- **The universe stays split.** History frozen on the pinned table; live
  universe from the SPY archive. No universe reconstruction.
- **The clock restarts on live data and static days do not count.** The
  2026-09-22 start is void.

## New, from the owner 2026-09-22

**The book runs indefinitely.** E11's thirty trading days become the first
reporting window over a loop that does not stop. F11.1 to F11.3 are evaluated
on days 1 to 30 and the loop keeps running past them, so E12 has a growing
panel rather than a closed one. Nothing in the loop may assume an end date;
the window is a query over the history, not the life of the run.


## NAV is $1,000,000, and it is a design parameter

The owner's paper account is funded at **$1,000,000 USD**. This is not an
incidental fact; it sizes the book, both guards and the share quantization.

**NAV is read, not hardcoded.** The proposal stores the account equity Alpaca
reports at proposal time, with its source and timestamp, and $1,000,000 is the
initial design value. A hardcoded million drifts away from the truth the moment
P&L accrues, and the guards below are expressed as a fraction of NAV, so a
stale NAV silently moves the thresholds. Until the live account is reachable,
store the design value and label it as such.

**A proposal with a null NAV is a failed run, not a warning.** It must raise.
Every proposal stores `nav`, the expected cost in bp, and its dollar
equivalent, so the cost and both guards can be checked from the artifact alone.

### The two guards are re-derived at $1m, not carried over

Show the arithmetic that sizes each one, not just the number. State each in
**both** dollar and percentage form.

**Guard 2 is broken as it stands, and would block day 1.** The brake is
$200,000, sized as one full flip of a $100,000 gross book. At NAV $1m with
gross 1.0 the book is $1,000,000 gross, so a from-flat establishment trades
about $1,000,000 and **the existing brake trips on the first real run and the
book never establishes**. Scaled by the same rule it becomes $2,000,000. Note
that establishment and steady state are different sizes: establishment trades
full gross, a steady-state rebalance trades only the delta, roughly 39% turnover
on this signal, about $390,000. Decide whether one threshold clears
establishment while still catching a fat finger, or whether the brake needs an
establishment value and a steady-state value, and say which and why.

**Guard 1 probably cannot fire.** The cap is 40% of NAV, which at $1m is
$400,000 per position. Gross 1.0 across roughly 500 names puts the average
position near $2,000, so the cap sits about 200x the average and no legitimate
or plausible fat-finger order reaches it. A guard that cannot fire is not a
guard. Re-derive it from the realized distribution of target weights in the
first real proposal: it must sit clear of the largest legitimate target with
headroom, and low enough that an order ten times too large trips it. Report the
weight distribution you sized it from.

### Whole-share quantization

At $1m across roughly 500 names the average target is about $2,000, so rounding
to whole shares should be a small effect. Verify it rather than assume it. The
first real proposal reports:

- the gross-weight error introduced by rounding, in total and the per-name
  worst case
- the count of names whose target rounds to **zero shares**, long leg and
  short leg separately, and the effective name count that survives
- the same for the short leg, where a fractional share cannot be shorted either

Pre-registered bar, set before the numbers exist: if rounding moves gross by
more than 0.5%, or more than 5% of names round to zero on either leg, that is a
**finding with an ID**, and the book may need fewer names carried at larger
size. Do not adjust the bar after seeing the number.

## Credentials are the owner's to place

The owner creates the local `.env` and sets the Render environment variables.
DeepSeek does not.

DeepSeek writes `.env.example` listing every variable name with a one-line
comment saying what it is and where it comes from, confirms `.env` is
gitignored, and **never prints, echoes, logs or commits a key**. That includes
debug output, exception messages, the proposal and reconciliation artifacts,
the dashboard, and anything Render captures as a log line. Check it and say how
you checked.


---

# Part A: live data, the sanity gate, the clock

Unchanged from the previous task. A Render dashboard showing a static book is
worth nothing, so this ships first and alone if budget runs short.

## The problem in one line

Live prices are necessary but not sufficient. `descriptors`, `factor_returns`,
`specific_returns`, `factor_cov` and `specific_var` are all frozen at
2026-09-03 too, so a live-price book priced by a three-week-old Sigma is stale
in a second way, and nothing in the artifact says so.

## Cadence, and why

**Daily. Every model input extends one session per trading day, incrementally.**

Not a slower cadence, because any lag reintroduces exactly the staleness this
task exists to remove: a weekly Sigma is a five-day-old Sigma four days out of
five, and the proposal cannot tell you which. Daily is affordable because
XS-v1 is a cross-sectional fit, so one new session is one new WLS fit of 17
estimated columns, not a refit of 3,941 days, and `factor_cov` and
`specific_var` are rolling window estimates that update by appending a session.

**Incremental append only, never a refit.** Rows dated on or before 2026-09-03
come back byte-identical after every extension. Restating history would move
stored criteria, which is reserved. XS-v1 estimates its own factor returns from
the cross-section and does not read the Kenneth French series, so the daily
extension needs only prices, share counts and sectors, and is not blocked by
the French library ending 2026-07-31.

## Steps

**A1. Stop the clock and discard the static days.** Record in `live/clock.json`
that the 2026-09-22 start is void, with the reason. Nothing is deleted.

**A2. Extend the price and universe layer daily.** Session prices and share
counts from the vendor E1 uses; universe from the newest SPY archive file.
Fetch and archive a fresh SPY holdings file and a fresh Wikipedia constituents
snapshot each session, both dated, both into `data/VERSION.json` and the
evidence snapshot. The 2026-08-05 to 2026-09-18 seam stays documented.

**A3. Extend the model artifacts daily.** Append one session to `descriptors`,
`factor_returns` and `specific_returns` by fitting that day's cross-section
under the frozen XS-v1 specification, then roll `factor_cov` and `specific_var`
forward one session. The specification does not change: this extends the
champion, it does not re-estimate or re-declare it.

**A4. Make staleness visible in the artifact.** Every proposal stores the as-of
date of every model input: prices, shares, universe, sectors, descriptors,
factor_returns, specific_returns, factor_cov, specific_var, plus a single
`max_input_staleness_days`. Staleness is read, never inferred.

**A5. The day-1 sanity gate. The clock does not start until this passes.** Run
the loop on **two consecutive real closes** and confirm the proposals differ.
Print and store the weight turnover, `0.5 * sum(abs(w_t - w_{t-1}))`, with the
definition stated. Identical proposals on two different closes means the data
is not live and the gate fails. Report the number either way; tune nothing.

**A6. The cost item.** Store `nav` beside `expected_establishment_cost_bps`,
and show the arithmetic reaching 75.34 bp decomposed into spread, impact,
commission and borrow, each in bp, with the notional and average per-name trade
size stated. Reconcile against E6's stored 10.53 bp per rebalance, which is a
**steady-state rebalance** trading only the delta against an **establishment**
trading full gross from flat plus the hedge book. The ratio to explain is about
7.15x. **If it will not reconcile, that is a finding with an ID and a
mechanism; do not adjust either number to close the gap.**

**A7. Reframe to a continuous loop.** Remove any assumption of an end date.
`live/clock.json` keeps day 1 and marks the thirty-day window as a reporting
slice with its end date, while the loop's own run condition is open-ended.

---

# Part B: Render, persistent state, and the live dashboard

## B0. Alpaca: read credit-trading-lab's setup first, then decide

**Read how credit-trading-lab connects to Alpaca before writing any of this.**
`/Users/amankesarwani/PycharmProjects/credit-trading-lab`: `execution/`,
`scripts/`, `render.yaml`, `.streamlit/`, and wherever the keys are loaded and
the client is built. Reuse that pattern rather than inventing one; it already
works in production on Render.

**Then resolve the account question and record the answer.** Does EFB reuse the
existing paper account or does it need its own? Find out from Alpaca's own
documentation or dashboard whether a second paper account can be created under
the existing login, or whether it needs a second login, and say which you used.

The reasoning that should decide it: two strategies sharing one paper account
share positions, cash, NAV and fill history. E12 attributes P&L **from
holdings**, so credit-trading-lab's fills would land inside EFB's attribution
and neither book's numbers would be its own. Reconciliation of forecast against
outcome would also be reconciling against someone else's trades. So the default
is a **separate paper account**, and reusing the existing one needs a reason
better than convenience. Whatever you choose, EFB's positions must be provably
disjoint from credit-trading-lab's; say how you check that.

Use environment variable names distinct from credit-trading-lab's so the two
cannot be crossed by a stale shell. Paper keys only. Nothing committed.

## B1. State that survives a restart: the shared Supabase project, schema `efb`

**AMENDED 2026-09-22, mid-flight. Read this before writing any storage code.**

The Supabase free tier allows two projects and both are in use, so E11 **shares
the existing project with credit-trading-lab and owns the schema `efb`**. Every
live table lives in `efb`. Never `public`, never the credit lab's schema.

**Connect over direct Postgres, not PostgREST.** Use the session-pooler
connection string under a distinct variable, `EFB_SUPABASE_DB_URL`, with
`EFB_DB_SCHEMA=efb` beside it, so a stale shell cannot cross the two projects.
The reason to prefer the direct connection: PostgREST only serves schemas that
have been added to "Exposed schemas" in the project's API settings, which is a
dashboard change on a project the credit lab also uses and it widens that
project's public API surface. A direct Postgres connection reaches any schema
with no dashboard change and no shared surface. The `EFB_SUPABASE_URL` and
`EFB_SUPABASE_SECRET_KEY` variables already in `.env.example` are the PostgREST
path; keep them only if something actually needs them, and say what.

Rules:

- `CREATE SCHEMA IF NOT EXISTS efb` on first run. Every DDL and DML statement
  is schema-qualified `efb.<table>`, or runs under `search_path=efb`. A test
  asserts that no statement in the codebase targets `public` or an unqualified
  table name.
- **The first run reports which schema it wrote to and the row count per
  table.** Not a log line that scrolls past: a stored artifact and a line in
  the report.
- Live series only: proposals, orders, fills, reconciliation, NAV and realized
  P&L, keyed by date. Research artifacts stay in git and the evidence snapshot.

**Say so if it is not clean.** On a shared free-tier project this separation is
a naming discipline, not a permission boundary: the same database role can see
both schemas, so the isolation is only as good as the schema-qualification
test. If targeting a non-default schema turns out to need dashboard changes,
shared-role grants, or anything that touches the credit lab's data, **stop and
report it**. The owner will move to Neon or Render Postgres instead. Do not
work around it.



Render's filesystem is ephemeral and a free web service spins down, so the
previous task's "state on local artifacts, no Supabase" decision does not
survive the move. A loop that must run indefinitely needs a store that outlives
the container. **Use Supabase**, which the owner already runs for
credit-trading-lab, for the live series only: proposals, orders, fills,
reconciliation, NAV and realized P&L, keyed by date. Research artifacts stay
where they are, in git and the evidence snapshot. Credentials come from the
environment and are never committed. If you judge a different store better,
say why before building it.

## B2. Deploy on Render

Follow the shape of `/Users/amankesarwani/PycharmProjects/credit-trading-lab`:
`render.yaml`, `.streamlit/`, the service layout and the cron wiring. Two
services: the **daily cron** running the evening and morning jobs, and the
**dashboard web service**. Health check, and a clear failure when a required
environment variable is missing.

## B3. The live dashboard, and what it is not

**It does not carry D0 to D9.** The full research dashboard stays local; the
Render app reads only the live series from Supabase plus a small current-book
snapshot. If a panel needs a large parquet, it does not belong here. State the
memory and cold-start cost in the report.

Build it for someone deciding whether the book is doing what it was built to
do. Lead with the answer. One idea per panel. Every number with its n and its
units. The null-book framing impossible to miss.

**What it shows:**

1. **Status.** Is the book live, when did it last run, how stale is every input
   (from A4), day count, and the thirty-day window's position inside it.
2. **Tracking metrics.** P&L cumulative and daily, realized vol against the 10%
   target, Sharpe with its standard error and its t, drawdown, turnover, cost
   paid against cost expected. No skill claimed unless t exceeds 2.
3. **Factor breakdown, several dimensions.** Exposure and P&L by style factor,
   by sector, and by VIX regime, before and after the hedge, so the hedge's
   effect is visible rather than asserted.
4. **Hedge panel.** Which hedge is on, which factor each leg neutralizes, the
   exposure before and after, the names and notional it costs, and **why**.
5. **The trade explanation, per name.** For every position and every trade
   today: the name, its alpha score and rank, its idio vol, the target weight
   and where Procedure 6.3's sizing got it, the current weight, the trade, and
   **why this trade today**: alpha moved, risk moved, the hedge moved, or it
   drifted past a band. Say which. A trade with no stated reason is a bug.

## B4. README

Update `README.md` and push. It stops at E2, shows E3 unchecked, and quotes
E1's survivorship bias as the superseded 349 bp. Bring it current: E1 to E10
built, the gates passed and not passed, the registry with XS-v1 provisional
champion, the live book and its Render link, and where the handoff files live.
**Every number read from an artifact**, with a traceability test in the shape
of `tests/test_e10_memo.py`, matching on the signed value.

## Acceptance

1. `make test` at least 640 tests, `make lint` clean, `make verify-evidence`
   exits 0.
2. Rows dated on or before 2026-09-03 in `descriptors`, `factor_returns` and
   `specific_returns` are byte-identical before and after an extension.
   Asserted by a test, hashes printed.
3. Every proposal carries an as-of date for all nine inputs plus
   `max_input_staleness_days`.
4. The sanity gate ran on two consecutive real closes, the proposals differ,
   and the turnover is stored with its definition. If it failed, the clock did
   not start and the report says which input is not advancing.
5. `nav` stored beside the cost; the four bp components sum to the total; the
   E6 reconciliation is closed with arithmetic or recorded as a finding.
6. Nothing in the loop assumes an end date. Show the run condition.
7. The Render dashboard loads without reading any file over 5 MB. State the
   largest read and the cold-start time.
8. Every open position and every trade on the dashboard carries a stated
   reason from B3 item 5.
9. README contains no number absent from an artifact, proven by its
   traceability test, and is pushed.
10. No credential, key or token in any committed file, including
    `render.yaml`. State how you checked.
11. No F1.x to F10.x verdict changes. Print the count per sprint.
12. No em dashes in any file touched.
13. **Every proposal stores a non-null `nav`**, the expected cost in bp and its
    dollar equivalent. A null NAV raises and the run fails; prove it with a
    test that a null-NAV proposal is rejected, not warned about.
14. Both guards are re-derived at $1m, each stated in dollars and as a
    percentage, each with the arithmetic that sized it shown. Guard 2 clears a
    full from-flat establishment of about $1,000,000. Each guard still has a
    test that fires it.
15. The first real proposal reports the whole-share quantization effect: total
    and worst-case gross-weight error from rounding, and the count of names
    rounding to zero shares on the long leg and the short leg separately. If it
    breaches the pre-registered bar, it is recorded as a finding with an ID.
16. `.env.example` exists with every variable named and commented, `.env` is
    gitignored, and no key appears in any committed file, artifact, log line or
    dashboard panel. State how you checked each surface. Every value in
    `.env.example` stays empty or an obvious placeholder; a real key there is a
    committed leak.
17. WITHDRAWN with Fix 4. No E9 or E10 numbers move, so no memo or walkthrough
    is re-executed.
17b. `dry_run` is `true` in every committed configuration and in every run in
    this task. DeepSeek does not flip it and does not set a new day 1.
17c. The minimum-position threshold is a registry parameter that works at either
    NAV. The report states which NAV it ran at and what the threshold gives at
    the other.
17e. Slow tests are marked, the fast and full paths are both reported with test
    counts and runtimes, the full-suite count is at least the previous full-run
    count in LOG.md with any decrease explained, and the measured shared-module
    set is recorded.
17d. D10 renders a full day's stored dry-run proposal with every panel populated
    from it. The report names the proposal date, the panels that drew, and any
    panel with no data and why.
18. The Alpaca cap question is answered with its source: balance or initial
    funding, and whether a reset to a higher balance is possible.
18b. If $10m is unreachable: the minimum position size is stored as a **registry
    parameter**, and the threshold, kept name count, dropped count and the new
    quantization distribution are all stored and reported.
18c. Both breadth numbers are reported: the naive `sqrt(460 / N_kept)` and the
    governing `sqrt(n_eff_full / n_eff_kept)` with `n_eff_kept` computed the way
    E8 computes it.
18d. `docs/open_items.md` records the minimum-position item as **closed by this
    decision**, with the residue named: folding it back into E8's construction
    stack rather than leaving it only in the live path.
19. Every live table is in schema `efb`. No statement targets `public` or an
    unqualified name, asserted by a test. The first run stores and reports the
    schema written to and the row count per table.

## Stop only if

- The sanity gate fails. Stop, do not start the clock, report which input is
  not advancing.
- Extending an artifact would restate any row dated on or before 2026-09-03.
- Anything would need real money, the universe reconstruction, or a change to
  the XS-v1 specification.
- **Any stored-criteria file changed and you cannot account for the change.**
  Halt. A `data_hash` bump goes through a revisions block with both hashes;
  anything else is a stop before further work.
- **Any artifact, log line, error message or dashboard panel could contain a
  key.** Stop immediately, do not commit, and report the surface.
- A proposal cannot obtain a NAV. Do not substitute a guess; report it.
- Targeting schema `efb` needs a dashboard change, a shared-role grant, or
  anything touching credit-trading-lab's data. Stop and report; the owner will
  move to Neon or Render Postgres.
- Part B cannot be finished. Ship Part A, commit it, and say what is left.
  Do not leave Part A half done to reach Part B.

Everything else you decide and record: the Supabase schema, the Render plan and
service names, the retry policy on a failed fetch, and the dashboard layout.

## Report back

**Table 1, the clock.** Void start and reason, new day 1, window end date,
the loop's open-ended run condition.

**Table 2, the sanity gate.** The two closes, weight turnover, n names each,
whether the proposals differ.

**Table 3, staleness.** Per proposal, the as-of date of all nine inputs and
`max_input_staleness_days`.

**Table 4, incremental integrity.** Per extended artifact: rows before, rows
after, hash of the pre-2026-09-04 block before and after.

**Table 5, the cost.** nav, gross, n names, average per-name trade size, the
four bp components, the total, and the E6 reconciliation or its finding ID.

**Table 6, Render and the database.** Services, plans, largest file read,
cold-start seconds, peak memory. Then: the schema written to, the row count per
table after the first run, the connection method (direct Postgres or
PostgREST), and confirmation that no statement targets `public`.

**Table 7, the trade explanation.** A sample of five positions with alpha
score, rank, idio vol, target weight, current weight, trade, and stated reason.

**Table 8, no-change.** Per sprint E1 to E10: criteria, verdicts changed.

**Table 9, the guards at $1m.** Per guard: old value, new value in dollars and
as a percentage of NAV, the arithmetic that sized it, whether it can fire
against a legitimate order, and the test that fires it.

**Table 10, quantization.** Total and worst-case gross-weight error from
rounding, names rounding to zero on the long leg and the short leg, effective
name count, NAV used, average target dollar size, and whether the
pre-registered bar was breached.

**Include the Verification section per STANDARDS.** Rules 19 and 20.
