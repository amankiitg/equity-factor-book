task_id: evidence-and-archive-hardening
status: done
base_commit: 3a82ccb0304611fbea508960e243ae1e7b9b04a3

## Goal

Protect the SPY archive, which is the one artifact in this repository that
cannot be regenerated, repair the evidence chain the last rebuild broke, and
close the within-year sample asymmetry left in F10.3b. Small and self-contained:
no verdict moves, no criterion text changes, no universe reconstruction.

## Before you start

Read `handoff/PROJECT_CONTEXT.md`, then `handoff/STANDARDS.md`, then the
2026-09-22 LOG entry. The work on the last task was good; these are the four
things that survived it.

**Out of scope, both blocked on the owner.** Do not touch either:

- **F10.1b.** Its criterion is fitted to the answer and its verdict is under
  review with the owner. Leave the criterion text, the threshold and the verdict
  exactly as they are.
- **The universe reconstruction.** Building the new membership from the SPY
  archive changes stored criteria and is reserved.

## Steps

**S1. Print the errors.** Append to `sprints/E10/PROBES.md`, before any fix:
`make verify-evidence` failing with its message; the SPY archive's absence from
`.git`, from `data/VERSION.json` and from `evidence/MANIFEST.json`; and the
F10.3b per-year observation counts showing 2012 measured from 11 raw against 9,
9, 8, 4 and 0 targeted observations at the five daily windows. Commit alone.

**S2. Protect the SPY archive.** It is a fetched input that `make rebuild`
cannot regenerate, because SSGA serves only the current file, so under the
2026-09-21 evidence policy it belongs in the evidence snapshot. Bring it in:
register each dated file in `data/VERSION.json`, extend `efb.evidence` to cover
`data/raw/spy_holdings/`, and refresh the snapshot. Check the size cost before
committing and report it; one file is about 40 KB, so a year of daily files is
small, but say what the growth rate is. If `.gitignore` needs a negation for
this directory, add it and record why in the ledger.

**S3. Repair the evidence chain.** Run `make evidence` so the snapshot matches
the current `data/VERSION.json`, then `make verify-evidence` until it exits 0.
Do not edit `evidence/MANIFEST.json` by hand.

**S4. Make the gate non-optional.** Add `make verify-evidence` to the test
suite as an integration test, or to a documented close-out step, so a rebuild
that forgets `make evidence` fails loudly instead of leaving a broken target.
Your call which; record it and the reason.

**S5. F10.3b's within-year asymmetry.** Require a minimum observation count per
year, applied to **both** sides, and drop any year where the two sides differ in
count. F10.3b keeps its ID, its criterion text and its `pass` verdict; the five
window reductions move through the `revisions` block with the old values beside
the new ones. Record in the ledger that E10-F6's year-level fix left a
within-year version of the same defect, and that an annual volatility built from
4 monthly returns is not the same statistic as one built from 11.

**S6. Correct the report's three weak claims.** In `handoff/REPORT.md`, which is
yours to rewrite for this task: cite `data/VERSION.json` hashes rather than
`git status` as the proof that membership is unchanged, since
`data/**/*.parquet` is gitignored and git status proves nothing there; extend
the F1.x to F9.x no-change row to E8 and E9; and label Table 7's counts as
measured on a fresh `build_membership`, noting that BE and P are absent from the
stored membership and only RDDT's error is present in it today.

**S7. Close.** `make rebuild-e10`, re-execute and re-render the walkthrough if
S5 changed a stored number, refresh `data/VERSION.json`, run `make evidence`
again if needed, then `make test`, `make lint` and `make verify-evidence`.
Write `handoff/REPORT.md` and set this file's status line to `done`.

## Acceptance

1. `make test` passes with at least 594 tests; `make lint` clean;
   **`make verify-evidence` exits 0**. All three run at the end, in that order.
2. `evidence/MANIFEST.json` contains an entry for
   `data/raw/spy_holdings/spy_holdings_2026-09-18.parquet`, and
   `data/VERSION.json` carries its sha256.
3. A fresh clone or a `git clean -xdf` would still contain the 18-Sep archive
   file. Demonstrate it, by whatever check you choose, and print the result.
4. `make verify-evidence` fails when `data/VERSION.json` is modified without
   refreshing the snapshot, proven by a test or a printed demonstration.
5. F10.3b's five stored reductions change, the old values appear in `revisions`,
   the criterion text and `pass` verdict are unchanged, and daily 21 lands near
   0.2868 with every window still below 0.40. If any window clears 0.40, stop
   and report; that would change F10.3's verdict.
6. Both sides of every F10.3b year carry the same observation count. Print the
   per-year table for all five windows.
7. F10.1b's criterion, threshold, stored numbers and verdict are byte-identical
   to their values at 3a82ccb. Print the comparison.
8. `data/processed` membership artifacts unchanged, proven by `VERSION.json`
   sha256 comparison, not by `git status`.
9. No F1.x to F10.x verdict changes except none. Assert across all ten sprints
   and print the count per sprint, E1 through E10.
10. No em dashes in any file touched.

## Stop only if

- Any criterion changes verdict.
- An F10.3b window clears 40%.
- Bringing the SPY archive into evidence would push the committed snapshot over
  the 100 MB line the 2026-09-21 open item records. Report the size instead.
- A fix would require re-running the universe reconstruction, or touching
  F10.1b. Neither is in scope.

Everything else you decide and record: the minimum observation count in S5, how
the archive is tracked in S2, and where the verify-evidence gate goes in S4.

## Report back

`handoff/REPORT.md`, every number read from an artifact.

**Table 1, gates.** `make test` count and exit code, `make lint` exit code,
`make verify-evidence` exit code, walkthrough total cells, code cells, error
outputs and null execution counts, each stated separately.

**Table 2, the archive.** File, bytes, sha256, present in `VERSION.json`,
present in `evidence/MANIFEST.json`, survives a clean checkout, and the
projected growth in MB per year of daily files.

**Table 3, F10.3b revisions.** Per window: old reduction, new reduction, years
dropped, n_years both sides.

**Table 4, per-year observation counts.** Per window and year: raw obs,
targeted obs, kept or dropped.

**Table 5, no-change.** Per sprint E1 to E10: criteria count, verdicts changed,
and for E10 the per-criterion before and after. Include the F10.1b
byte-identical check.

**Table 6, membership unchanged.** The four `VERSION.json` entries
(`universe_membership`, `universe_constituents`, `universe_changes`, `sectors`)
with sha256 at 3a82ccb and at HEAD.

Plus a paragraph naming every decision you made and why, and any finding this
task did not anticipate, with a new ID continuing from E10-F23.
