# EFB project context

Both agents read this first, every turn. Reviewer owns this file; DeepSeek does
not edit it. Changes to it get a `handoff/LOG.md` entry saying why.

Companion files: `handoff/STANDARDS.md` (the standing rules), `handoff/TASK.md`
(the current unit of work), `handoff/LOG.md` (reviews, append-only),
`handoff/REPORT.md` (DeepSeek's report on the current task).

## Purpose

A learning instrument that builds every component of Paleologo's *Advanced
Portfolio Management* and *The Elements of Quantitative Investing* on free
equity data, and the template for porting the same machinery to corporate
credit. E13 is that port design, a document only.

It builds the machinery, not an edge. A profitable strategy is not required and
a negative result is a complete outcome. Each sprint bridges academic and
practitioner: three research questions, a PM question, pre-registered
falsification criteria with numeric thresholds written before the numbers exist,
and a research deliverable in `docs/research/` written for a senior quant or
risk manager. A concept implemented without the practitioner interpretation and
the written artifact is a textbook exercise.

Thirteen sprints in three tiers, with three research gates: RG-Data (end of E1),
RG-Signal (end of E7), RG-Operate (end of E10, before the book runs). A gate
that returns a negative answer has done its job.

## State

Ten sprints built. E11 is a dry-run loop. Its construction is chosen
(share-only, 20 shares, 2026-09-24). The store is on direct Postgres, and the
book, Guard 1 and the sanity gate are being redone (task
`e11-admit-and-live-gate`). E12's engine has not been started. HEAD 3e9dbe1. `e11-pre-deploy` is closed into `e11-deploy`, the critical path to a deployed dry run, under the owner's blocker rule (a finding blocks only if it changes what the cron does, risks data or evidence, or could leak a credential; everything else is on the post-deploy list in LOG.md). Items 1 to 4b, A, B-cron (design), c and e are accepted; last clean full suite 835 passed, 1 skipped. Track 1 (cron): the Render plan and snapshot fields, no write path into `data/raw/`, the stopped-run book from the store, R2 through boto3, the full suite. Track 2 (web): a minimal Vite/React page on a Cloudflare Worker behind Access. The owner's deploy list is in LOG.md. No SQL path, R2 put or Resend send has yet run against the real service. Five model versions
in `data/models/registry.json`. XS-v1 is champion, and its `live` block records
the construction: `share_only`, `share_floor` 20, `dollar_floor` 0,
`floor_iterated` true. TS-v1 is diagnostic only and
ineligible. Dashboard tabs D0 to D10 exist; D11 does not. `data/VERSION.json`
hashes 147 artifacts at `c3e0db6f`. `live/` holds the construction table and
its per-name weights.

Verdicts and headline numbers, all from `sprints/E*/RESULTS.json`:

- **E1** universe, returns, Hygiene Ledger, perf library. Gate RG-Data. F1.3
  passes; F1.1, F1.2, F1.4, F1.5 fail. Survivorship: 44.79% of deleted members
  have recoverable history against a 70% bar, and the naive backtest of current
  members earns **365.10 bp a year** over a point-in-time universe (F1.5).
  Coverage of all requested tickers 77.16% against a 95% bar (F1.1).
- **E2** time-series models, volatility, TS-v1. Seven pass, four fail. The
  volatility horse race failed and was accepted: GARCH beats trailing 252d on
  out-of-sample QLIKE for 58.16% of names and EWMA(0.94) for 35.40%, against a
  60% bar (F2.3), so production stayed with the decay 0.97 estimate. F2.6b found
  **36 reused ticker symbols** among 373 names on the removed list.
- **E3** cross-sectional model, Fama-MacBeth, FMPs, XS-v1. Gate G1. Eight pass,
  F3.6 fails. Mean daily cross-sectional R squared **0.32945** over 3,941 days
  (F3.1); FMP identity to 1.2e-13, identification to 7.0e-18. F3.6: the
  equal-weight book's bias is 0.9570, in band, and the momentum book's is
  **0.6664**, below the 0.8 floor, so XS-v1 cannot yet size that book.
- **E4** statistical models, covariance lab, PCA-v1 and PCA-v1c. Five pass, F4.1
  and F4.4 fail. PC1 correlates with the market factor at 0.7970 (PCA-v1) and
  0.9306 (PCA-v1c) against a 0.95 bar; the Marchenko-Pastur edge isolates **13**
  significant factors. F4.6 measured the survivor distortion: the size factor
  correlates only **0.5778** between the full and mapped universes.
- **E5** risk model evaluation, regimes, champion. Three pass, F5.1 and F5.2
  fail. **F5.1 failed, so the champion is provisional**: no version is inside
  0.9 to 1.1 across all portfolio families (XS-v1 1.0470, XS-v2 1.0385). XS-v1
  is champion under the pre-registered rule. Stress haircut **1.8471**, recovery
  13 trading days from 2020 Q1 (F5.4).
- **E6** hedging. All seven pass. The exact in-model FMP hedge drives the worst
  factor exposure to **5.83e-15** and the idio share to 1.0, at 461.9 names
  traded per rebalance (F6.1). The as-stored quarterly capped FMPs are not a
  hedge: worst residual exposure 0.7552, worse than unhedged.
- **E7** alpha lab, multiple-testing ledger. Gate RG-Signal. Four pass, F7.2 and
  F7.1b fail. **All six signals are NULL at RG-Signal.** F7.2: factor-neutral
  momentum IC is **-0.010684 with t -1.549** against a bar of 0.02 and t 2.
  Beware two different verdicts in this sprint: `RG_SIGNAL.json` (the seven
  question checklist, decided on factor-neutral out-of-sample t) says NULL for
  all six, while F7.3's `verdict_by_signal` (the deflated-Sharpe ledger label on
  the raw spread) reads PASS for momentum_12_1 and idio_momentum. The gate
  verdict is the binding one.
- **E8** sizing, Procedure 6.3, constraints. Gate G3. Six pass, F8.1 and F8.4
  fail. F8.1b passes at **6.42e-17**: with alpha GLS-neutralized in the D^-1
  metric, unconstrained mean-variance, the proportional rule and Procedure 6.3
  are the same vector. The constrained optimizer's worst violation is 3.95e-09
  with **zero solver fallbacks** (F8.3).
- **E9** transaction costs, capacity. Two pass, F9.1 and F9.2 fail, **F9.3 is
  not evaluable**. F9.1 fails on a mechanism worth knowing: net mean return does
  decline monotonically in AUM, but net Sharpe does not, because the impact
  cost's cross-rebalance variance inflates the denominator. F9.2: turnover cut
  37.55% against a 50% bar, at an ex-ante IR loss of 6.49%.
- **E10** Kelly, vol targeting, stop-loss, drawdowns by regime. Gate RG-Operate.
  Six criteria after the corrections: F10.2, F10.2b and F10.3b pass, F10.1 and
  F10.3 fail, F10.1b passes on a criterion fitted to the answer and is with the
  owner. **RG-Operate is not cleared**: the constituent source is stood up but
  not applied. Closed 2026-09-22 after two review rounds and 27 findings.
  The SSGA SPY daily holdings file is the ongoing source: 503 equity rows with
  CUSIP and SEDOL, archived dated and protected in the evidence snapshot.
  iShares IVV is recorded as a failing source, gated behind a disclaimer.

## Standing findings

Later work must respect these. They are measured, not assumed.

1. **The historical cross-section is survivor-only.** The sector file maps only
   the 502 current members, so the historical cross-section contains only
   companies in the index today. Survivorship bias is about **366 bp a year**.
   Size and liquidity are distorted by it: the size factor correlates **0.578**
   between the full and mapped universes (F4.6). Owned by E4, not fixable on the
   current data.
2. **A ticker symbol is not an identity.** 36 reused symbols are excluded; 33
   left the estimation panel and 3 were restored with truncated history. Prices
   attach to symbols, not issuers, and the fix needs a security-identity source.
3. **The champion XS-v1 is provisional.** F5.1 failed: no model is calibrated
   across all portfolio families. Stress haircut **1.8471**. XS-v2, the residual
   covariance version, lost narrowly despite four E4 measurements supporting
   residual structure. Declaring or changing the champion is a reserved decision.
4. **All six signals are NULL at RG-Signal.** Their raw ICs are the known
   factors. Post-earnings drift's horizon-1 IC was announcement leakage, caught
   by F7.1c: its IC falls from 0.1240 to 0.0073 under the extra-day lag.
5. **Synthetic alpha uses future returns by construction.** It is a controlled
   experiment, never a backtest, and it can never trade live. The synthetic
   label travels with every number computed from it.
6. **Equity costs are an assumption, not a measurement.** A size-decile schedule
   of 1 to 10 bp half-spread, with a half and double sensitivity, because free
   daily OHLC cannot measure spreads for S&P 500 names. This is why F9.3 is
   recorded not evaluable rather than failed.
7. **Breadth.** IR is IC times sqrt(N) when forecast errors are independent, and
   IC times sqrt(N_eff) when they co-move the way residual returns do. Measured:
   **N_eff about 140 against N about 460** (F8.7: 139.89 and 461.89).
8. **Several criteria failed by construction** because the threshold was written
   before the object existed: F4.1, F7.2, F8.4, and F9.3 is not evaluable. They
   are recorded with their mechanisms and are never reworded. Neutralizing
   momentum against a risk model that contains momentum projects the signal out;
   that is F7.2's mechanism and it matters for the E11 decision.

## Decisions the owner has made

Settled 2026-09-22. These are no longer open; build on them.

- **E11 trades `idio_momentum` through the full stack**, Procedure 6.3 sizing
  plus the FMP hedge, documented as a null book. **Paper only.**
- **The book runs indefinitely.** The thirty trading days are E11's first
  reporting window, not the life of the run: F11.x are evaluated on days 1 to
  30 and the loop keeps going, so E12 gets a growing panel. Nothing in the loop
  may assume an end date.
- **Hosting, revised 2026-09-25.** Render runs **only the cron jobs**; there is
  no EFB web service on Render. The live book monitor (D10) is a **React app on
  Cloudflare**, built and deployed the way nutri-track is (Vite, React,
  `wrangler deploy`), but **not** with nutri-track's browser-to-Supabase data
  access. **The browser never queries Postgres.** The evening cron writes one
  JSON snapshot to a private R2 bucket, using a token scoped to that bucket,
  and the app reads it server-side through an R2 binding on the same
  hostname. **Cloudflare Access** protects every hostname. The snapshot
  carries its run status and `expected_next_by`, and the page fails loudly when
  the snapshot is late. Live state (proposals, orders, fills, reconciliation,
  NAV, P&L) stays in Supabase schema `efb`. D0 to D9 stay local Streamlit. The
  reason is the owner's: the credit lab's Render Python dashboard keeps
  hitting memory errors at $7 a month, while nutri-track on Cloudflare works
  well. **Later, not now:** the credit-trading-lab dashboard is a candidate
  for the same migration once EFB's is proven.
- **Alpaca is paper only, on an account provably disjoint from
  credit-trading-lab's**, because E12 attributes from holdings and commingled
  fills would make neither book's numbers its own. "Live" in this project means
  live data and a continuously running loop, never real money.
- **NAV is $1,000,000 paper, final.** Alpaca's paper funding field is capped at
  "$1 - $1,000,000", confirmed in the dashboard, so a $10m account is closed by a
  platform limit; documentation suggesting an arbitrary reset balance is stale.
  **Do not re-raise a higher NAV, and do not propose switching brokers**: that
  would rewrite the execution layer to solve a sizing problem a parameter solves.
  Read from the account each run; a failed read fails the run with no orders.
- **$1m over 499 names cannot be traded as constructed.** $1,941 a name is about
  ten shares of a $200 stock, so whole-share rounding moved gross by 5.4%, and a
  $5,000 minimum position left only 27 names at gross 0.27. The book therefore
  carries either a minimum position size or a top-N-by-alpha construction, chosen
  by the owner from a measured table. Two facts that constrain any choice: the
  book must be **renormalized to gross 1.0 after dropping names**, or it is
  under-invested and misses the vol target; and **N must clear XS-v1's roughly 18
  factors by a healthy multiple**, or the exact FMP hedge is rank-deficient and
  the idio book stops being idio.
- **The construction is share-only, a minimum of 20 whole shares per name**,
  with no dollar floor, iterated to a fixed point on the final traded
  weights. **Confirmed by the owner, 2026-09-24, on like-for-like numbers**:
  143 names, n_eff 68.52, total error 0.78% and p90 1.85%, the admission
  control with the floor enforced on the traded weights. That is about 20% of
  IR below min $1,500, with 3.6x lower total error, and it dominates two-part
  outright. **The installed book under the final rule (Part 1R, dd41d9b):
  150 names, n_eff 70.59, total error 0.689%, p90 1.887%, max weight 5.35%**,
  a local maximum under single-name moves. The re-decide trigger did not fire.
  The 51-name rank margin gates this book, not the comparison rows. **The 188-name book first chosen was
  never reachable**: 24 of its names hold under 20 shares once sized. The
  figures below are that first basis, kept for the record. Chosen 2026-09-24 from the fixed-point table: 188 names, n_eff
  85.69 against 157.33 for the full book, governing breadth 1.355, total
  error 1.25% of NAV, p90 per-name rounding 3.44%. These are table values
  from before the floor was enforced on final weights (E11-F12), and the
  enforced values supersede them. The owner's reasoning: the roughly 14% IR
  cost against min $1,500 is notional in a documented null book, while the
  error reduction is real. The gap between the priced book and the held book
  becomes attribution bias at E12, so trading imaginary IR for measurement
  fidelity is the right trade in a project whose purpose is measurement.
  Share-only rather than two-part, because the $1,500 leg cost 2.6 n_eff for
  0.19 points of error, and one floor is simpler to state than two. 188 names
  against about 18 factors leaves comfortable rank margin, which is what
  failed the small-N rows. **Changing it is reserved.**
- **The live store is direct Postgres, schema `efb`, and nothing else.**
  Settled again 2026-09-24 with E11-F11: never PostgREST, the service-role
  key never on a web service, and **no change to the Exposed schemas setting
  on the shared project**. Needing that change is a stop condition and stays
  one. The owner moves to Neon or Render Postgres rather than widen the
  shared project.
- **The model inputs live in Postgres, schema `efb`, not on disk.** Decided
  2026-09-24 on E11-F15. Each run reads the last stored date, appends the new
  session and writes it back, so a wiped Render container costs nothing.
  Rebuilding from raw on every run repeats work, and a persistent disk costs
  money and pins the region. The intended design is the git snapshot as the
  seed plus a Postgres appendix, which keeps pre-2026-09-04 rows byte-identical
  in git and fits the free-tier database cap shared with credit-trading-lab.
- **Staleness fails the run.** Owner, 2026-09-24, non-negotiable. If any input
  is older than it is allowed to be, the job stops before proposing, logs why,
  and places no orders. Staleness is counted in NYSE trading sessions against
  the most recent completed session. The dashboard reads the latest run
  status, and shows a stale, failed or missing run as a failure, never as the
  last good book. A book pricing Monday's close on Thursday must not trade.
- **The sanity gate runs on two closes the loop fetched on their own
  evenings**, through the **Render cron in dry run**, confirmed 2026-09-24.
  Catch-up and replays do not count. The owner watches the production path
  run itself for two evenings, and the flip then changes one variable.
- **Every run notifies the owner by email through Resend** (revised
  2026-09-25 from Slack), copying credit-trading-lab's pattern with EFB's own
  sending-only key, `EFB_RESEND_API_KEY`. The status sits in the subject, for
  example `EFB ok 2026-09-25 | 150 proposed, none sent | stale 0`. The email
  goes out on clean runs too, secrets are scrubbed, and a failed or
  unconfigured send fails the run. The heartbeat for a job that never starts
  is the owner's to add.
- **Staleness, confirmed:** trading sessions, zero behind the latest close.
  Shares and sectors are judged on fetch age, because the risk with slow
  inputs is the fetch quietly stopping.
- **The append handles corporate actions without restating rows.** Owner,
  2026-09-25. yfinance back-adjusts history on a split while the pipeline is
  append-only, and E1's 50% outlier flag misses a 2:1 split. So splits are
  detected at append time and the new day's return is computed with the split
  factor. Price-level readers apply the cumulative factor at read time, and no
  stored row is touched.
- **Retention: Postgres holds the longest model lookback, and older days are
  archived to git** in separate dated files, never into the seed artifacts
  E1 to E10 were scored on. The archive is a local, deliberate command with
  its own delete-only role, never run on Render. It lands within a month of
  the deploy.
- **The public-schema function limit is accepted** (2026-09-25). New roles can
  execute functions in the shared project's `public` schema through
  PostgreSQL's default PUBLIC grant. Revoking it would change the shared
  project. The deploy notes state it.
- **Whatever is chosen, the executed book's breadth is reduced and every E11
  number meeting an E8 transfer coefficient must say so.** The naive bound is
  `sqrt(460 / N_kept)`; the governing one is `sqrt(n_eff_full / n_eff_kept)`,
  since E8 measured n_eff near 140 against n_names near 460 and N_eff is limited
  by residual co-movement rather than name count. **Do not quote the naive bound
  at E12 without the measured one beside it.** This is a documented null book, so
  no expected return is lost either way.
- **The 30-day clock restarts on live data, and static days do not count.**
  The 2026-09-22 start is void: the loop ran on the frozen 2026-09-03 close and
  would have produced thirty identical proposals. Prices, descriptors, factor
  returns, specific returns and both covariance artifacts all extend **daily by
  incremental append**, never a refit, with pre-2026-09-04 rows byte-identical.
  Every proposal stores the as-of date of all nine model inputs. The clock is
  held until a sanity gate runs two consecutive real closes and shows the
  proposals differ, with the weight turnover printed.
- **F10.1b is re-registered** against F10.1's original 10% bar, verdict `fail`,
  through a `revisions` block, with the mean-versus-median note.
- **The universe stays split.** Historical artifacts stay frozen on the pinned
  Wikipedia changes table; the SPY archive supplies the live universe from
  2026-09-18 forward. The full reconstruction is **not** scheduled: it would
  move every artifact and hash E1 to E10 and put F1.1, F1.5, F3.1, F3.6, F5.1
  and F5.2 at risk, including the champion, and it recovers no history. The
  seam between the two sources is documented and never silently bridged.
- **The v8.x daily loop is at `/Users/amankesarwani/PycharmProjects/credit-trading-lab`**:
  `execution/`, `dashboard/`, `scripts/`, `render.yaml`, `.streamlit/`,
  `sprints/v8.1` and `v8.6`. **Guidance, not a template.** Reuse its loop
  shape, its Option A governance and its fail-safes; do not inherit its
  dashboard design. Its own README carries a lesson E12 must inherit:
  fixed-entry P&L accounting is mandatory, because rolling residuals marked to
  market with drifting parameters produced up to $13M of phantom P&L there.

## How the two agents split

Since 2026-09-22: **DeepSeek executes and verifies everything.** The reviewer
reads reports, keeps this file current, helps the owner decide, and writes the
next task. Every REPORT.md ends with a `## Verification` section per STANDARDS
rules 19 and 20; a report without it comes back unreviewed.

## Carried items

- **E8's construction stack has no minimum-position concept.** Recorded and then
  **closed the same day, 2026-09-22**, by the NAV decision: E11 carries a
  minimum position size as a registry parameter. The residue is small and still
  open: folding the rule back into E8's construction stack rather than leaving
  it only in the live path, owned by whatever sprint next revisits construction.
- **E11's raw beta is now a required line in E12's scope**, promoted from a
  note by the owner on 2026-09-23. See remaining plan item 5.

## Reserved decisions

Only the project owner makes these. Set `handoff/TASK.md` to `blocked` with the
question and write it at the top of the LOG entry. Do not decide these and do
not work around them.

1. **Any change to what E11 trades, or any move from paper to real money.**
2. **Anything that declares or changes the champion.**
3. **Any change to a stored criterion outside a `revisions` block.**
4. **Deleting or rewriting evidence, artifacts or git history.**
5. **Anything touching real money or real broker credentials. Paper only.**

## Remaining plan

Sequenced 2026-09-23. Each numbered item is roughly one TASK.md or less.

1. ~~E10 review fixes.~~ Done 2026-09-22, two rounds, 27 findings.
2. ~~The ongoing constituent source.~~ Done 2026-09-22. SPY archived and
   protected; IVV a recorded failing source; sector on live Wikipedia.
3. ~~The construction choice.~~ **Done 2026-09-24: share-only, minimum 20
   shares.** See "Decisions the owner has made". The owner's earlier rule (if
   the two-part floor's n_eff is close to min $1,500's, it wins outright) was
   read against the fixed-point table, and the owner chose share-only over
   two-part.
4. **E11 to completion**, in this order and no other (task
   `e11-share-floor-to-gate`):
   a. The E11-F8 ledger correction, and the store moved to direct Postgres
      (E11-F11).
   b. The live path implements share-only 20 shares with the floor enforced
      on the final traded weights, iterated to a fixed point (E11-F12). The
      table is enforced the same way on every row. **Re-decide trigger,
      pre-registered:** if, against enforced min $2,000, share-only loses its
      lower total error or lower p90, or if any enforced row dominates it, the
      choice goes back to the owner.
   c. The registry records the construction; the E5 `data_hash` bump goes
      through `revisions`.
   d. Guard 1 re-derived against the chosen construction's final weights.
   e. The proposal is regenerated under the chosen construction, labeled from
      its own fields on D10 and on the Render page.
   f. The sanity gate on two real closes with `dry_run` still true.
   g. Deploy-ready over direct Postgres. The owner deploys, and a real dry-run
      proposal is shown on the Render page from `efb`. A page that has never
      displayed a real proposal is not confirmed working.
   h. The owner flips `dry_run` once. **That act starts day 1.**
   **Status at 938da6c:** a, c and the store move are done. The regenerated
   proposal, Guard 1's basis and the sanity gate are redone, because the
   enforcement loop only dropped names (E11-F13) and the gate replayed
   historical closes rather than showing live data (E11-F14). Before any
   deploy, the owner decides where the daily-extended inputs live on Render
   (E11-F15). **Status at 4048b97:** the appendix, the staleness stop, the
   notification and the deploy steps are built. **Do not deploy** until
   `e11-pre-deploy` items 1 to 4b land: the universe look-ahead, catch-up
   labelling, the dashboard's `n_eff`, the corporate-actions rule and the APH
   repair, and no silent store fallback. The shared project measured about
   2 MB on 2026-09-25, against the 400 MB stop. **After the first deploy, the
   round trip is verified against the real `efb` schema before any gate evening
   counts**, because every earlier round-trip test ran on the parquet fallback.
   **Resequenced 2026-09-25:** the cron deploys to Render in dry run once
   `e11-pre-deploy` items 1 to 4b, A (Resend) and B-cron (the snapshot writer,
   the memory measurement, no web service) land. Email is the owner's monitor
   for the two gate evenings. The React page on Cloudflare is built in
   parallel and does not block the gate. **The owner flips `dry_run` only after
   the Cloudflare page shows a real proposal from a real snapshot.** The
   earlier sequence follows, for the record:
   **Resequenced 2026-09-24 after the owner's decisions:**
   1. The prefix fixed point, then the owner re-confirms share-only.
   2. The model inputs move into Postgres.
   3. The staleness hard stop.
   4. Corrected deploy steps.
   5. Proposals and Guard 1 on the confirmed book.
   6. The owner deploys in dry run, and the gate runs on two closes the loop
      fetches on their own evenings.
   7. The owner flips `dry_run`.
   **F11.1 to F11.3 stay open until 30 live days accumulate.**
5. **E12, built during the 30-day window, not after it.** See the correction
   below: the engine does **not** exist yet, so this is a build, not a
   finishing pass. `efb/attribution.py`, holdings-based and returns-based
   attribution, the seven-way decomposition, the skill test, D11, the memo and
   the walkthrough, all exercised against the **historical seed books**, with
   the live panel wired and empty.
   **Required in E12's spec, owner 2026-09-23: a raw-market-beta line.** E11's
   kept books carry 0.105 to 0.147 of raw CAPM beta that XS-v1 cannot see; the
   decomposition is open under E11-F8. XS-v1 books that market P&L as
   stock-specific return, which is precisely the error E12 exists to catch. So
   the attribution reports the book's daily raw CAPM beta and its market P&L
   as a separate line beside XS-v1's factor lines. The skill test is run on
   specific return both as XS-v1 reports it and net of that line, and both
   results are stored. The table's idio share of 1.0 is in-model and overstates
   the book's true idio share; E12 states the book's idio share net of raw
   beta too. Rough size, assuming 17% market vol: about 1.8% annualized against
   the 10% target, small in variance but directional. The E12 task and PRD
   carry this as a numbered deliverable, not a note.
   **E12's criteria cannot be evaluated until the live panel has 30 days.**
   F12.1's reconciliation identity can be exercised now on the seed books as a
   machinery check, but its stored verdict, and F12.2's and F12.3's, are on the
   live book and stay pending. On day 30 E12 is a run, not a build.
6. **E13, the credit port design note**, alongside item 5. A document, no code,
   no live data. **This is the piece with the most direct value to the owner at
   Bracebridge, so it is written while the context is fresh rather than
   reconstructed in January.** F13.1 is about the repository rather than the
   book, so unlike E12 this sprint can be **completed** inside the window.
7. **E12 on the live data** once 30 trading days exist: evaluate F12.1 to F12.3,
   close the sprint.

### Correction, 2026-09-23: E12's engine has not been built

An earlier `e12-attribution-engine` task was written and then superseded by the
E11 live work before DeepSeek started it. Verified at HEAD: no
`efb/attribution.py`, no D11 tab, no `sprints/E12/`, no E12 tests, and
`data/attribution/` empty. Item 5 is therefore a full sprint's build, not a
finishing pass, and should be scoped that way.

## Working lessons

- **One TASK.md is one sprint or less.** Implementer sessions run out of working
  budget, and chained sprints stop mid-task.
- **Every real defect so far was found by reading an output, not the code**: two
  rows identical, a magnitude off by 100x, a sign mix, a result too clean. The
  E10 review is the same story: the code reads fine and the numbers are
  reproducible; what is wrong is what they measure. Review outputs.
- **Never rebuild an artifact a stored criterion was scored on without
  preserving it first.** E5 lost the published XS-v1 covariance race row that
  way, and it is not reproducible from any derivation.
- **Never rerun a full sprint build to add one artifact.** Use the
  `make rebuild-e<n>` target.
- **A stop condition exists only for irreversible or plan-changing events.**
  Everything else the implementer decides and records in `handoff/REPORT.md`.
- **Mechanistic explanations with worked numbers**, inputs and outputs labeled.
  A claim about a mechanism is checked against a measurement before it is
  written down; a recorded mechanism that a control contradicts is itself a
  defect, even when the verdict above it is right.
- **No em dashes anywhere**, including files under `handoff/`.
- **A review ends with a commit of the handoff files** (STANDARDS rule 23).
  Several uncommitted cycles left a fresh session reading a stale task.
- **A fixed-point spec must name the family it searches, not only the loop.**
  Two reviewer specs failed on E11-F13. "Drop, check, repeat" never admits a
  name. "The largest valid prefix" of the full-book ordering is still a
  dropping rule, and re-sizing a subset reorders the weights, so a few
  high-priced names broke every prefix between 17 and 499. The rule that works
  is drop, then admit, to a local maximum under single-name moves. A
  pre-registered stop caught the second error at no cost, which is what stops
  are for.
- **A fixed-point spec must name admission as well as dropping.** E11-F6
  showed that iteration buys breadth by admitting names back. The E11-F12 spec
  said only "drop, re-size, check, repeat", and it got a drop-only loop that
  landed at roughly the one-pass count. Name the rule that selects the set
  (for example the largest valid prefix), not only the loop.
- **A gate on historical dates is a replay, not a live check.** A gate meant to
  show the data advances runs on the most recent closes at run time, through
  the entry point production uses.
- **Check whether a number is an identity before reading it as a result.**
  Three recorded instances (F4.1, F7.2, F8.4) and one candidate (E11-F8); see
  the hygiene ledger, 2026-09-23. Ask whether it would take the same value for
  any data, or scale with a constant fixed upstream.
