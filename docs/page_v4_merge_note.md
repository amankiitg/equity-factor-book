# The trial merge of page-v4 with nov11, 2026-10-15

Nothing was pushed from this trial. A scratch worktree at `/tmp/efb5-trial` was
checked out detached at `page-v4` (`3ec9837`), `git merge --no-commit origin/nov11`
was run, the conflicts below were read, and then `git merge --abort` and
`git worktree remove` left the branch and the repository exactly as they were.

## What the merge looks like

Four conflicted files, every one of them under `web/src`. Nothing outside it
conflicted, and the merge auto-resolved `web/src/App.test.tsx`,
`web/src/sections.test.tsx`, `web/src/types.ts`'s top level and the Python the
nov11 branch carries (`efb/prices.py` merged cleanly).

| File | Conflicts | Why |
|---|---|---|
| `web/src/exceptions.ts` | 6 | Both branches deleted the two classes from `UNCHECKED` and both added `PREVIOUS_REVERSALS` in the same place, in different words: nov11 keeps the key names in the copy, page-v4 shortened it to one plain sentence. The floor's class and the corporate-action class are worded differently for the same reason. |
| `web/src/MetricsRow.tsx` | 6 | Both branches added `droppedNoRisk` and the `sent_notional` turnover basis at the same lines; page-v4 also replaced nov11's three-line construction prose with a three-line list, and the `turnover-note` paragraph differs. |
| `web/src/exceptions.test.ts` | 2 | Both added cases for `previous_reversals_pending` and `under_minimum_tickers`; the fixtures and the `doc()` helper are the same shape, the copy differs. |
| `web/src/types.ts` | 1 | One doc comment on `dropped_no_risk`: nov11 says "published on 2026-11", page-v4 says "absent on every document written before the evening published them". |

Every conflict is wording, duplication or ordering of the same behaviour. None of
them is a disagreement about what the page should do, because page-v4 was built by
porting nov11's handling of `bridge.under_minimum_tickers`,
`bridge.previous_reversals_pending`, `reconciliation.sent_notional` /
`unsent_notional` and `breadth.dropped_no_risk`, with tests for each.

## The resolution rule for November

1. **`web/src/**`: take page-v4, then run nov11's page tests.** page-v4 is a
   superset of nov11's page behaviour — it reads the same four keys and draws the
   same findings — and it is the branch with the plain-words rule and the phone
   measurements behind it. After taking page-v4, run
   `cd web && npx vitest run` on the merged tree: nov11's own cases for the four
   keys are the check that the port is complete, and any case that fails there is a
   behaviour nov11 has and page-v4 does not.
2. **Nothing else.** No other path conflicted, and the Python side of nov11
   (`efb/prices.py` and its tests) merged cleanly, so the run's own code is not part
   of this resolution.

## The one thing the November merge must not forget

**`origin/nov11` does not contain main's 2026-10-14 incident fix (`63c8f94`, the
warrant the vendor cannot price: `efb/prices.py` and `live/extend.py`, with
`docs/incident_2026-10-14.md` and its tests).** `git merge-base --is-ancestor
63c8f94 origin/nov11` says no; `origin/main` has it. Whichever direction the
November merge runs, it must bring that fix in and keep it: the fix is what stops
an unpriceable warrant from taking the evening run down, which is the failure the
2026-10-14 document in `web/fixtures/snapshot_2026-10-14_error.json` is a record
of.

## State of the two branches at the trial

- `page-v4` = `3ec9837` (merged to `main` as `2947eaa` and deployed;
  `origin/main` = `2947eaa`).
- `origin/nov11` = `6903912`.
- Trial merge conflicts: the four files above. Nothing pushed, nothing aborted
  halfway: the abort ran, and `git worktree list` shows no scratch worktree left.
