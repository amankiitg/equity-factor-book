# EFB brief

## Who merges and who deploys

Set by Aman on 2026-11-26.

- **Page only PRs** (every changed file under `web/`, no Python, no evening job, no
  stored data) may be merged and deployed by the agent without asking, once all three
  hold:
  1. the gate passes (`npx vitest run` and `npm run build`, plus the python suite
     reported with its known workspace failures named), and
  2. the agent's own screenshot check at 1920 and 390 is clean, and
  3. the clock is outside 14:30-16:00 UTC and 21:30-23:15 UTC.
- **Anything else waits for Aman**: trading code, the evening job, stored data, and
  anything outside `web/`. Those are never merged or deployed by the agent.
- PR K stays on hold until Aman says otherwise.
