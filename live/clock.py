"""Sprint E11: the thirty-trading-day clock.

The clock is pre-registered: day 1 and the end date are written before
any window outcome is seen, which is what makes F11.1 falsifiable. Once
started it is never restarted with a different day.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLOCK_PATH = ROOT / "live" / "clock.json"
TRADING_DAYS = 30


def _end_date(day_1: str, trading_days: int) -> str:
    """The last business day of the window, day 1 included."""
    days = pd.bdate_range(day_1, periods=trading_days)
    return str(pd.Timestamp(days[-1]).date())


def start_clock(
    day_1: str,
    trading_days: int = TRADING_DAYS,
    path: Path = CLOCK_PATH,
) -> dict:
    """Write day 1 and the end date; a restart with a different day fails."""
    payload = {
        "day_1": day_1,
        "end_date": _end_date(day_1, trading_days),
        "trading_days": trading_days,
        "started": True,
    }
    if path.exists():
        existing = json.loads(path.read_text())
        if existing.get("day_1") != day_1:
            raise ValueError(
                f"the clock is already started on {existing.get('day_1')!r}, "
                f"not {day_1!r}; it is never restarted"
            )
        return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def load_clock(path: Path = CLOCK_PATH) -> dict:
    """The recorded clock, or a clear error before it has started."""
    if not path.exists():
        raise FileNotFoundError(f"no clock at {path}")
    return json.loads(path.read_text())


if __name__ == "__main__":
    today = date.today().isoformat()
    payload = start_clock(today)
    print(json.dumps(payload, indent=2, sort_keys=True))
