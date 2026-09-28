"""Sprint E11: pre-register F11.1 to F11.3 and the clock into RESULTS.json.

The criteria are copied verbatim from docs/roadmap_v2.md, never retyped:
this script reads them out of the roadmap by their IDs. The clock and the
day-1 proposal numbers are read from their artifacts. The window has not
closed, so every verdict is `pending`; the stored numbers arrive when the
thirty days complete.

Registration is refused unless the day-1 date the clock starts on is the date the
records agree on: the first live run (a run that was not a dry run and that sent
at least one order) and the first stored proposal. `live/clock.py` owns that check
and this script only calls it, so the rule lives in one place. The day-1 proposal
is then read *for that date* out of the store rather than the newest file on disk:
the newest file is whatever ran last, which before the flip is a rehearsal.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from live import clock as clock_module

ROOT = Path(__file__).resolve().parents[2]
ROADMAP = ROOT / "docs" / "roadmap_v2.md"
RESULTS = ROOT / "sprints" / "E11" / "RESULTS.json"
CLOCK = ROOT / "live" / "clock.json"

CRITERIA_IDS = ("F11.1", "F11.2", "F11.3")

# The manifest fields the day-1 proposal records. The same names the pre-flip
# registration stored, so the file's shape does not change when the day arrives.
PROPOSAL_FIELDS = (
    "signal",
    "as_of",
    "universe_source",
    "n_names",
    "n_excluded",
    "idio_share_after_fmp",
    "gross",
    "net",
    "achieved_annual_vol",
    "target_annual_vol",
)


def _criteria_verbatim() -> dict[str, str]:
    """Read F11.x out of the roadmap, one line below each ID."""
    lines = ROADMAP.read_text().splitlines()
    found: dict[str, str] = {}
    for index, line in enumerate(lines):
        if line.strip() in CRITERIA_IDS and index + 1 < len(lines):
            found[line.strip()] = lines[index + 1].strip()
    if set(found) != set(CRITERIA_IDS):
        missing = set(CRITERIA_IDS) - set(found)
        raise RuntimeError(f"could not read {missing} from the roadmap")
    return found


def _day_1_proposal(day_1: str) -> dict[str, Any]:
    """The stored proposal priced from the day-1 close, or a refusal.

    The store is the source rather than the newest proposal file: a file on disk
    is whatever ran last, and before the flip that is a rehearsal from a frozen
    close. The stored row carries the manifest the run priced from, which is what
    the day-1 numbers have to come from.
    """
    from live import store

    frame = store.select("proposals")
    if frame.empty or "trade_date" not in frame.columns:
        raise clock_module.RegistrationRefused(
            f"no proposal is stored, so the proposal priced from {day_1} cannot be "
            "recorded"
        )
    dates = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime(
        "%Y-%m-%d"
    )
    rows = frame.loc[dates == day_1]
    if rows.empty:
        raise clock_module.RegistrationRefused(
            f"the store holds no proposal priced from {day_1}"
        )
    manifest = json.loads(rows["manifest"].iloc[0])
    return {field: manifest[field] for field in PROPOSAL_FIELDS}


def register(records: dict[str, list[str]] | None = None) -> dict:
    """Start the clock on the first live session and register its criteria.

    Every read that can refuse happens before the first write, so a refusal leaves
    the repository exactly as it found it: no clock started on a day the records do
    not support, and no results file naming one. The day-1 proposal is read for the
    date the records agree on rather than the newest file on disk.
    """
    resolved = clock_module.records_from_store() if records is None else records
    day_1 = clock_module.first_day(resolved)
    proposal = _day_1_proposal(day_1)
    started = clock_module.start_clock(day_1, path=CLOCK, records=resolved)
    criteria = _criteria_verbatim()
    payload = {
        "sprint": "E11",
        "registered_at": datetime.now(UTC).isoformat(),
        "status": "pending",
        "clock": started,
        "criteria": {
            name: {
                "criterion": text,
                "verdict": "pending",
                "stored_numbers": [],
            }
            for name, text in criteria.items()
        },
        "day_1_proposal": proposal,
    }
    RESULTS.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


if __name__ == "__main__":
    print(json.dumps(register(), indent=2, sort_keys=True))
