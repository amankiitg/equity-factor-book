# The held-marks switch, parked (P1a, 2026-10-31)

Branch `held-marks-close`. **Not merged.** The evening values the held book at the
broker's `market_value`; this branch adds `EFB_HELD_MARKS=close`, which values each
position at the newest vendor close the tree holds times the broker's quantity. Unset
is the broker's value, so the switch is inert until someone sets it.

## Why it is not merged

`docs/research/mark_source.md` has the evidence. Two facts decide it:

1. **The vendor's daily bar for the current session is not printed at 22:55 UTC.** On
   2026-10-30 every 2026-10-30 close in the panel was `NaN` at 00:40 UTC the next
   morning, so "close x quantity" on a live evening is yesterday's close: a
   one-session lag on the number the guard reads.
2. **The extended-hours print was the better number in the one case that mattered.**
   On 2026-10-29 INTC was marked $71.16 against an official close of $92.07 after
   earnings; the 2026-10-30 session then closed at $65.88. The mark the broker
   reported was closer to the next session's reality than the official close was.

## The replay: every live close, both mark sources

Worst factor exposure, 196-leg book of the 2026-10-30 manifest, computed twice: the
broker's marks, and every position valued at its session close (the last 5-minute bar
at or before 16:00 New York, validated against the 2026-10-29 daily close: median
1.8 bp, p95 8.5 bp, max 29 bp).

| Close | Broker marks | Session closes | Guard (5.00%) |
| --- | --- | --- | --- |
| 2026-10-26 | 2.28% | 2.29% | not fired either way |
| 2026-10-27 | 1.52% | 1.51% | not fired either way |
| 2026-10-28 | 3.07% | 3.27% | not fired either way |
| 2026-10-29 | 3.03% | 2.86% | not fired either way |
| 2026-10-30 | 6.41% | 6.42% | fires either way |

Recomputed exactly from the manifest's own `weight_before` values and the evening's
design: 6.4105% at broker marks against 6.4218% at session closes. **The mark source
never changed a guard decision in the live history.**

## What the branch does

- `live/held_marks.py`: the mode, a provider hook, and `at_close`, which re-marks a
  name at close x quantity and keeps the broker's number for a name it has no close
  for - a missing mark must not drop a position out of the book the guard measures.
- `live/positions.py::account_read` applies it and returns `mark_source` with the read,
  so the run can say which names were re-marked and the largest move in dollars.
- `scripts/run_live_daily.py` configures the provider once the run tree is known.
- `tests/test_held_marks.py`: the default is the broker, a bad mode is refused, a name
  is re-marked at close x quantity, a name with no close keeps the broker's number and
  is named, and a provider that fails leaves the book at the broker's marks.

## If the owner wants it

Set `EFB_HELD_MARKS=close` on Render. The evening then logs
`held marks: N name(s) at the vendor close, M at the broker's market value; largest
move TICKER ±X`, and the session lag shows up as `M` names on the previous close
whenever the current bar has not printed. It moves held weights, drift and the guard
reading; the target book is untouched, because sizing reads the account's equity and
the target, not the held marks.
