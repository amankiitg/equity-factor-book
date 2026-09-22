"""Sprint E11: pre-register F11.1 to F11.3 and the clock into RESULTS.json.

The criteria are copied verbatim from docs/roadmap_v2.md, never retyped:
this script reads them out of the roadmap by their IDs. The clock and the
day-1 proposal numbers are read from their artifacts. The window has not
closed, so every verdict is `pending`; the stored numbers arrive when the
thirty days complete.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROADMAP = ROOT / "docs" / "roadmap_v2.md"
RESULTS = ROOT / "sprints" / "E11" / "RESULTS.json"
CLOCK = ROOT / "live" / "clock.json"
PROPOSALS = ROOT / "live" / "proposals"

CRITERIA_IDS = ("F11.1", "F11.2", "F11.3")


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


def _latest_proposal() -> dict:
    proposals = sorted(PROPOSALS.glob("proposal_*.json"))
    if not proposals:
        raise RuntimeError("no proposal manifest to register")
    return json.loads(proposals[-1].read_text())


def register() -> dict:
    criteria = _criteria_verbatim()
    clock = json.loads(CLOCK.read_text())
    proposal = _latest_proposal()
    payload = {
        "sprint": "E11",
        "registered_at": datetime.now(UTC).isoformat(),
        "status": "pending",
        "clock": clock,
        "criteria": {
            name: {
                "criterion": text,
                "verdict": "pending",
                "stored_numbers": [],
            }
            for name, text in criteria.items()
        },
        "day_1_proposal": {
            "signal": proposal["signal"],
            "as_of": proposal["as_of"],
            "universe_source": proposal["universe_source"],
            "n_names": proposal["n_names"],
            "n_excluded": proposal["n_excluded"],
            "idio_share_after_fmp": proposal["idio_share_after_fmp"],
            "gross": proposal["gross"],
            "net": proposal["net"],
            "achieved_annual_vol": proposal["achieved_annual_vol"],
            "target_annual_vol": proposal["target_annual_vol"],
        },
    }
    RESULTS.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


if __name__ == "__main__":
    print(json.dumps(register(), indent=2, sort_keys=True))
