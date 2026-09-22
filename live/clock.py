"""Sprint E11: the thirty-trading-day clock.

The clock is pre-registered: day 1 and the end date are written before
any window outcome is seen. A start can be voided (discarded, never
counted) and the clock restarted from a new day 1, but every start,
voided or live, stays on the record.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLOCK_PATH = ROOT / "live" / "clock.json"
TRADING_DAYS = 30


def _end_date(day_1: str, trading_days: int) -> str:
    """The last business day of the window, day 1 included."""
    days = pd.bdate_range(day_1, periods=trading_days)
    return str(pd.Timestamp(days[-1]).date())


def _now() -> str:
    return datetime.now(UTC).isoformat()


def load_clock(path: Path = CLOCK_PATH) -> dict:
    """The recorded clock, or a clear error before it has started."""
    if not path.exists():
        raise FileNotFoundError(f"no clock at {path}")
    return json.loads(path.read_text())


def void_start(
    day_1: str,
    reason: str,
    path: Path = CLOCK_PATH,
) -> dict:
    """Void a start: the window is discarded and never counts.

    The voided start and its reason stay on the record, so the file shows
    a restart rather than a silent edit. The clock is left not started.
    """
    existing = load_clock(path) if path.exists() else {}
    history = list(existing.get("history", []))
    if existing.get("started"):
        history.append(
            {
                "day_1": existing.get("day_1"),
                "end_date": existing.get("end_date"),
                "status": "void",
                "reason": reason,
                "voided_at": _now(),
            }
        )
    elif not any(
        entry.get("day_1") == day_1 and entry.get("status") == "void"
        for entry in history
    ):
        history.append(
            {
                "day_1": day_1,
                "end_date": _end_date(
                    day_1, existing.get("trading_days", TRADING_DAYS)
                ),
                "status": "void",
                "reason": reason,
                "voided_at": _now(),
            }
        )
    payload = {
        "started": False,
        "day_1": None,
        "end_date": None,
        "trading_days": existing.get("trading_days", TRADING_DAYS),
        "history": history,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def start_clock(
    day_1: str,
    trading_days: int = TRADING_DAYS,
    path: Path = CLOCK_PATH,
) -> dict:
    """Start the clock on a new day 1, the earlier starts kept in history."""
    existing = load_clock(path) if path.exists() else {}
    payload = {
        "started": True,
        "day_1": day_1,
        "end_date": _end_date(day_1, trading_days),
        "trading_days": trading_days,
        "history": existing.get("history", []),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


if __name__ == "__main__":
    payload = load_clock()
    print(json.dumps(payload, indent=2, sort_keys=True))
