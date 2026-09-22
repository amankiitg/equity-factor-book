task_id: e11-live-data-and-clock-restart
status: in_progress
base_commit: 14d25bf

## Goal

Make the E11 loop actually live, then restart the thirty-day clock from a
clean day 1. The previous setup ran end to end but on the frozen 2026-09-03
close, so it would have produced thirty identical proposals. The static days
are discarded and do not count.

## The owner's decision, settled 2026-09-22

**Option (a): stop the clock, wire live data, restart at day 1. Do not count
the static days.** The clock does not restart until the sanity gate in S5
passes. Everything else from `e11-setup` stands: `idio_momentum` through the
full stack, Procedure 6.3 plus the exact FMP hedge, documented null book,
**paper only**, universe from the SPY archive, history frozen.

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
`specific_var` are rolling window estimates that update by appending a
session rather than by rebuilding history.

**Incremental append only, never a refit.** Rows dated on or before 2026-09-03
must come back byte-identical after every extension. Restating history would
move stored criteria, which is reserved. XS-v1 estimates its own factor
returns from the cross-section and does not read the Kenneth French series, so
the daily extension needs only prices, share counts and sectors, and is not
blocked by the French library ending 2026-07-31.

## Steps

**S1. Stop the clock and discard the static days.** Record in `live/clock.json`
that the 2026-09-22 start is void, with the reason, so the record shows a
restart rather than a silent edit. Nothing about the static run is deleted.

**S2. Extend the price and universe layer daily.** Fetch the session's prices
and share counts from the same vendor E1 uses, append, and take the universe
from the newest SPY archive file. Fetch and archive a fresh SPY holdings file
and a fresh Wikipedia constituents snapshot each session, both dated, both
into `data/VERSION.json` and the evidence snapshot. The 2026-08-05 to
2026-09-18 seam stays documented and unbridged.

**S3. Extend the model artifacts daily.** Append one session to `descriptors`,
`factor_returns` and `specific_returns` by fitting that day's cross-section
under the frozen XS-v1 specification, then roll `factor_cov` and
`specific_var` forward by one session. The specification does not change: this
extends the champion, it does not re-estimate or re-declare it.

**S4. Make staleness visible in the artifact.** Every proposal stores the
as-of date of **every** model input it used, one field each, at minimum:
prices, shares, universe (SPY file), sectors, descriptors, factor_returns,
specific_returns, factor_cov, specific_var. Add a single `max_input_staleness_days`
beside them. Staleness is read off the artifact, never inferred.

**S5. The day-1 sanity gate. The clock does not start until this passes.**
Run the loop on **two consecutive real closes** and confirm the proposals
differ. Print and store the weight turnover between them, defined as
`0.5 * sum(abs(w_t - w_{t-1}))` with the definition stated. Identical
proposals on two different closes means the data is not actually live and the
gate fails. Report the number either way; do not tune anything to pass it.

**S6. The cost item.** Store `nav` beside `expected_establishment_cost_bps` in
every proposal, and show the arithmetic that reaches 75.34 bp, decomposed into
spread, impact, commission and borrow, each in bp, with the notional and the
average per-name trade size stated. Then reconcile against E6's stored 10.53 bp
per rebalance for the hedged momentum book, which is a **steady-state
rebalance** trading only the delta, against an **establishment** trading the
full gross from flat plus the hedge book. The ratio to explain is about 7.15x.
**If the two cannot be reconciled, that is a finding: record it with an ID and
its mechanism, do not adjust either number to close the gap.**

**S7. Restart the clock.** Only after S5 passes. Record the new day 1, the end
date and the void first start. Then `make test`, `make lint`,
`make verify-evidence`.

## Acceptance

1. `make test` passes with at least 640 tests, `make lint` clean,
   `make verify-evidence` exits 0.
2. Rows dated on or before 2026-09-03 in `descriptors`, `factor_returns`,
   `specific_returns` are byte-identical before and after an extension.
   Assert it with a test; print the hashes.
3. Every proposal carries an as-of date for all nine inputs in S4 plus
   `max_input_staleness_days`.
4. The sanity gate ran on two consecutive real closes, the proposals differ,
   and the weight turnover between them is stored with its definition. If the
   gate failed, the clock did not start and the report says what is not live.
5. `nav` is stored beside the cost in every proposal, and the four-way bp
   decomposition sums to the stored total.
6. The E6 reconciliation is either closed with arithmetic or recorded as a
   finding with an ID.
7. `live/clock.json` shows the void 2026-09-22 start with its reason, and the
   new day 1 and end date if the gate passed.
8. No F1.x to F10.x verdict changes, F10.1b included. Print the count per
   sprint.
9. No credential, key or token in any committed file. State how you checked.
10. No em dashes in any file touched.

## Stop only if

- The sanity gate fails. Then stop, do not start the clock, and report exactly
  which input is not advancing.
- Extending a model artifact would restate any row dated on or before
  2026-09-03.
- The vendor cannot supply a session's prices or share counts. Record the
  failing source per the ledger rule; do not fill it.
- A step would need the universe reconstruction, real money, or a change to
  the XS-v1 specification.

Everything else you decide and record: the extension's storage layout, the
retry policy on a failed fetch, and the D10 panels that surface staleness.

## Report back

`handoff/REPORT.md`, every number read from an artifact.

**Table 1, the clock.** Void start and reason, new day 1, end date, whether
the gate passed.

**Table 2, the sanity gate.** The two closes, weight turnover between them,
n names each, and whether the proposals differ.

**Table 3, staleness.** Per proposal, the as-of date of all nine inputs and
`max_input_staleness_days`.

**Table 4, incremental integrity.** Per extended artifact: rows before, rows
after, hash of the pre-2026-09-04 block before and after.

**Table 5, the cost.** nav, gross, n names, average per-name trade size, the
four bp components, the total, and the E6 reconciliation with its arithmetic
or its finding ID.

**Table 6, no-change.** Per sprint E1 to E10: criteria, verdicts changed.

**Include the Verification section per STANDARDS.** Rules 19 and 20.
