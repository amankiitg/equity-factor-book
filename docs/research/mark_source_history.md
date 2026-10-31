# The mark source over the live history, and why a past audit is not possible (P4c)

`docs/research/mark_source.md` answers the question for the five closes it could reach
(2026-10-26 .. 2026-10-30) by valuing every held position twice - at the broker's
`market_value` and at its session close - and finding the guard decision unchanged
(6.4105% against 6.4218% on 2026-10-30, both above the 5% rule; the four closes before
it stay far below either way).

This note records what the full live history can and cannot add, and what to store so
the next audit is possible.

## What the history holds

24 stored proposals, 2026-09-25 to 2026-10-30 (`efb.proposals`). One of them carries a
drift-guard block:

| close | guard threshold | reading | fired |
| --- | --- | --- | --- |
| 2026-10-30 | 5.00% | 6.4105% | yes, 109 legs, $68,858 |

Every other close has no `drift_guard` key at all: `EFB_DRIFT_GUARD` was set on Render
during the weekend of 2026-10-24, and the 2026-10-30 close was the first to read it. So
there is exactly **one** guard decision in the live history to audit, and it has been
audited.

The same table, read for the variance cap rather than the guard, says something else the
owner should see - the cap was exceeded for three weeks before the 2026-10-23 rebalance:

| closes | `max_variance_share` |
| --- | --- |
| 2026-10-01 .. 2026-10-22 (14 closes) | 11.2% .. **14.2%** |
| 2026-10-23 .. 2026-10-30 (6 closes) | 7.7% .. 8.7% |

The 10% rule was stated and not met for fourteen consecutive closes, and the manifest
said `variance_share_cap_binds: true` each time. `sizing.enforce_final_cap` (2026-10-31,
P1b/P1c) is what makes that impossible now: it caps and re-projects until the vector
that trades meets the rule, and the 2026-10-30 reconstruction reads 9.9678% with
`cap_binds` false.

## What the history cannot answer

**A per-name mark audit cannot be run after the fact.** The store keeps, per close and
per name, the loop's own `weight`, `signed_notional` and `previous_weight` - all of them
derived from the broker's `market_value` - and it does **not** keep the broker's
`market_value` or the held quantity. Re-marking a past close at the vendor close needs
`quantity x close`, and the quantity is only in the account, at the moment of the read.

That is why the audit stopped at five closes: those were computed while the account was
reachable, and the earlier ones cannot be reconstructed from the store at all. Any
claim about the mark source over 2026-09-30 .. 2026-10-23 would be an assumption dressed
as a measurement.

## What to store so the next audit is possible

1. **The mark, per held name, in the manifest.** `market_value` as read (and the
   quantity beside it) is two numbers per position and makes every future audit a join
   instead of a re-read of a live account that has moved on.
2. **The mark source and its summary.** The parked `held-marks-close` branch already
   returns one - mode, how many names were re-marked, and the largest move in dollars -
   from the account read; the evening should write it into the manifest whether or not
   the switch is ever turned on.
3. **The largest mark gap** between the two sources on the closes where both are
   computable, so the owner can see the distribution instead of the INTC anecdote.

## Recommendation, unchanged

Do not switch to vendor close x quantity. At 22:55 UTC the vendor's daily bar for the
current session has not printed (on 2026-10-30 every close for the session was `NaN`
four hours later), so the switch is a one-session lag on the number the guard reads, and
on the one earnings case in the history the extended-hours print the broker reported was
closer to the next session's reality than the official close. Record both readings; keep
valuing at the broker's mark.
