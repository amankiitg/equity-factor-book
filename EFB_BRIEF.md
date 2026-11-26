# EFB brief

## Who merges and who deploys

Set by Aman on 2026-11-26. Replaces the earlier page-only rule.

The agent merges and deploys every PR itself, without asking Aman, once the
automatic guardrails below hold. This covers page PRs, `live/monthly_view.py`,
republishing the snapshot, and trading-path code.

Guardrails (all automatic, no human step):

1. The gate passes: zero new failing test ids against main (`npx vitest run`,
   `npm run build`, and the python suite with its known failures named).
2. Never merge, deploy or republish between 14:30-16:00 UTC or 21:30-23:15 UTC.
3. Page and data changes: back up the published objects before writing, republish
   if the change needs it, check the live page at 1920 and 390, and run the
   anonymous `/api/snapshot` scan.
4. Trading-path changes (evening job, orders, sizing, hedge, guard): an identity
   proof that tonight's book is unchanged, unless the PR is meant to change it, in
   which case the proof shows exactly the intended difference.
5. A PR that changes `live/supabase_schema.sql` merges only after its migration
   is applied.
6. After each ship, one message to Aman: what changed, the Worker version, and
   the rollback command (the version live just before the deploy).

PR K is no longer on hold: finish it and ship it under this rule.
