# EFB standing rules

The rules that hold across every sprint. Sources: `docs/engineering_standards.md`
(Roadmap Appendix B), `docs/hygiene_ledger.md`, `docs/open_items.md`, and the
sprint PRDs under `sprints/E*/PRD.md`.

This file is written by the reviewer. DeepSeek does not edit it. Any change to
it requires a `handoff/LOG.md` entry saying why it changed.

## 1. Criteria are copied verbatim and never reworded

A pre-registered falsification criterion is a numeric threshold stated in
advance, stored in the sprint's plan, and evaluated afterwards without being
reworded. E10 PRD, inherited constraint 1: "F10.1 to F10.3 are copied verbatim
from docs/roadmap_v2.md; a stored criterion is never reworded."

This binds the deliverables too, not only `RESULTS.json`. A memo, walkthrough or
dashboard panel that states a criterion states the stored `criterion` and
`threshold` strings, read from `RESULTS.json`, not a paraphrase. Appending a
disjunct ("or the gap is X") to a threshold converts a falsifiable criterion
into an unfalsifiable one and is a rewording. Substituting the measured value
for the threshold is a rewording, and makes the criterion pass by construction.

## 2. New findings take new IDs

A criterion keeps its ID and its verdict. A better measurement of the same
question is a new ID beside the old one, never an edit of the old one. The
project's convention for this is the letter suffix: F4.1, F7.1b, F7.1c, F8.1b.

## 2b. An acceptance band is not a criterion

A criterion states the question that was asked before the numbers existed. A
numeric band drawn around a value that has already been measured is not a
criterion, whatever it is stored as: it passes by construction and it hides the
result the pre-registered threshold would have given.

Acceptance items in `handoff/TASK.md` are the reviewer's guards on the
implementation. They are never lifted into criterion text. When a task registers
a new criterion, the criterion restates the original question against the
corrected object, and keeps the original threshold unless the owner changes it.
Recorded 2026-09-22 after F10.1b was registered against the reviewer's own
0.15 to 0.25 sanity band and scored `pass`, where the pre-registered 10% bar
would have scored it `fail` at 26 to 30%.

## 3. A threshold that is wrong for the built object fails, with the mechanism

Hygiene ledger, 2026-09-21 on F7.2: "the threshold was written for a different
neutralization ... a criterion written against one object scored another, and
the fail is the record of that mismatch, never a workaround." The verdict stays
`fail`. What gets written is the mechanism, and the mechanism has to be the one
that is actually true: a recorded mechanism that a measurement contradicts is
itself a defect, even when the verdict it sits under is right.

From the roadmap's gate rule: "A gate that returns a negative answer has done
its job: the number goes into RESULTS.json and the research deliverable, and the
next sprint adapts." A negative verdict is a complete deliverable.

## 4. No figure is typed by hand in a walkthrough or a deliverable

E10 PRD, inherited constraint 2: "No number in any walkthrough or deliverable is
typed by hand." Every figure is interpolated from an artifact or from
`RESULTS.json`. Each walkthrough ends with a cell that collects every stored
value into a forbidden set and asserts none appears as a literal anywhere in the
notebook's code.

## 5. Every deliverable ships a traceability test

The test asserts that every headline number in the deliverable matches a stored
value. It matches on the signed value, not on the absolute value: a test that
compares magnitudes cannot catch a sign error, and a sign error is one of the
defects this project keeps hitting.

## 6. Medians and win counts for skewed distributions

A per-name average over an unbounded loss function is dominated by a few names.
E2 reports the QLIKE horse race as a win share across names and across
name-days; E4 reports the covariance race as a median and a win count over 175
windows. Report the median and the win count, and say which population is being
counted.

## 7. Commit after every task

One task, one commit. A task is sized so it can be committed alone.

## 8. Print an error before editing anything

Reproduce the failure and print it first. A fix committed without the printed
error it fixes has no evidence behind it.

## 9. Never start a full rebuild to add one artifact

Hygiene ledger, 2026-09-20: E5 Task 0a "destroyed the evidence it was meant to
reproduce". An artifact that a stored criterion was scored on is evidence and
needs a derivation before it is rebuilt.

## 10. Never leave a half-executed notebook

A walkthrough is committed fully executed, in order, with no error outputs and
no null execution counts, or it is not committed.

## 11. Evidence snapshots only for artifacts `make rebuild` cannot regenerate

Hygiene ledger, 2026-09-20 (E5 R1): the snapshot under `evidence/` covers
artifacts that are not rebuildable from a derivation. Files that are build
products of a `make rebuild-e*` target are listed as skipped rather than
committed. `make verify-evidence` checks each snapshot against both
`evidence/MANIFEST.json` and the hash in `data/VERSION.json`.

## 12. No em dashes in any file

Engineering standards: "No em dashes in any artifact: documents, notebooks,
prompts, docstrings, dashboard text." Applies to files under `handoff/` too.

## 13. No look-ahead, and every sprint runs a shift audit

Anything used as a forecast at t is computed from data through t-1. Fields
flagged not point-in-time must never feed a forecast unmodified.

## 14. A failing source is recorded, never silently dropped

Hygiene ledger, 2026-09-04 on the FRED DTB3 timeout: "a failing source is
recorded in the ledger and the design adapts; it is never silently dropped."
A fetch that returns HTTP 200 with the wrong payload is a failing source. Any
fetcher validates the shape of what came back and raises on a mismatch; status
code alone is not a check.

## 15. Ledgers are append-only

The Hygiene Ledger and the multiple-testing ledger are append-only and
timestamped. Entries are never edited or removed; corrections are new entries,
and a correction carries the old value beside the new one.

## 16. The synthetic label travels with every number

E10 PRD, inherited constraint 3: "The synthetic input is a controlled
experiment, never a backtest; the label travels with every number." The same
rule applies to any sample restriction: a statistic computed on a subset states
the subset size beside it.

## 17. Sprint exit checklist

Every `TASKS.md` item closed with a passing test; every F criterion evaluated
with a stored number in `RESULTS.json`; registry entry for any new model
version; walkthrough rendered to HTML and linked; research deliverable written
with its "What would falsify this?" section; ledger entries for every policy
decision; the sprint's PM question answered in one paragraph at the top of the
deliverable.

## 18. Gates

RG-Data (end of E1), RG-Signal (end of E7), RG-Operate (end of E10, before the
book runs in E11). A gate item answered negative sends that item back before the
next sprint runs. Every gate item is answered with a stored number, never with
reasoning standing in for a measurement.

## 19. The implementer verifies; the reviewer reads

Effective 2026-09-22. DeepSeek runs all gates, all recomputation and all
checking. The reviewer reads reports, keeps context current, helps the owner
decide, and writes the next task. The reviewer does not run the gates, does not
read source or notebooks, and does not recompute numbers, except on the owner's
explicit request for a deep review, and then once for that round.

The consequence for DeepSeek: a claim with no pasted evidence behind it is not a
claim anyone will check. Verification is now yours to do and yours to show.

## 20. REPORT.md ends with a Verification section

Every report ends with a section headed `## Verification` containing all of:

- **The exact commands run and the last lines of their output, pasted**, for
  `make test`, `make lint` and `make verify-evidence`. Paste the real output,
  including the test count and the exit status. A summary of output is not
  output.
- **Every headline number with the file and key it was read from**, so each one
  can be checked with a single read.
- **`git diff --stat` from `base_commit`**, pasted.
- **An explicit yes or no, each with one line of evidence**, for:
  1. Any two rows or two estimators identical.
  2. Any exception caught and skipped, or any fallback taken, with counts.
  3. Any criterion reworded or replaced by a different test.
  4. Any criterion that passes by construction.
  5. Any number that moved by a factor of 10 or more from its previous stored
     value.
  6. Any stored number typed into a notebook.
  7. Any earlier verdict changed.
- **Anything decided that the reviewer might disagree with.**

A "no" with no evidence line is incomplete. Where the honest answer is yes, say
yes and explain: a yes that is explained is fine, a yes that is hidden is the
defect. If the section is missing or an item is unanswered, the task comes back
unreviewed.
