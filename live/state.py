"""Sprint E11: append-only state on EFB artifacts.

No Supabase: the loop's truth lives in parquet and json files under
`live/state/`. Writers are append-only and idempotent on the (trade_date,
key) pair, so a re-run updates one row instead of duplicating it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "live" / "state"

DECISION_COLUMNS = ["trade_date", "decision", "reason", "created_at"]
POSITION_COLUMNS = ["trade_date", "ticker", "signed_notional", "weight", "side"]


def _load_frame(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    return pd.read_parquet(path)


def write_decision(
    trade_date: str,
    decision: str,
    reason: str = "",
    state_dir: Path = STATE_DIR,
) -> None:
    """Upsert one dated decision; re-submitting the same day overwrites it."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "decisions.parquet"
    frame = _load_frame(path, DECISION_COLUMNS)
    frame = frame.loc[frame["trade_date"] != trade_date]
    row = pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "decision": decision,
                "reason": reason,
                "created_at": pd.Timestamp.now("UTC").isoformat(),
            }
        ]
    )
    pd.concat([frame, row], ignore_index=True).to_parquet(path, index=False)


def fetch_decision(trade_date: str, state_dir: Path = STATE_DIR) -> str | None:
    """The stored decision for a trade date, or None when there is none."""
    frame = _load_frame(state_dir / "decisions.parquet", DECISION_COLUMNS)
    rows = frame.loc[frame["trade_date"] == trade_date, "decision"]
    return str(rows.iloc[0]) if len(rows) else None


def _read_settings(state_dir: Path) -> dict[str, object]:
    path = state_dir / "settings.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _write_settings(settings: dict[str, object], state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "settings.json").write_text(json.dumps(settings, indent=2))


def get_auto_approve(state_dir: Path = STATE_DIR) -> bool:
    """Whether execution runs unless the dated decision is reject."""
    return bool(_read_settings(state_dir).get("auto_approve", False))


def set_auto_approve(value: bool, state_dir: Path = STATE_DIR) -> None:
    settings = _read_settings(state_dir)
    settings["auto_approve"] = bool(value)
    _write_settings(settings, state_dir)


def write_positions(
    trade_date: str,
    rows: list[dict[str, object]],
    state_dir: Path = STATE_DIR,
) -> None:
    """Upsert one day's positions; a re-run replaces that day's rows."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "positions.parquet"
    frame = _load_frame(path, POSITION_COLUMNS)
    frame = frame.loc[frame["trade_date"] != trade_date]
    day = pd.DataFrame(rows)
    pd.concat([frame, day], ignore_index=True).to_parquet(path, index=False)


def fetch_positions(trade_date: str, state_dir: Path = STATE_DIR) -> pd.DataFrame:
    """The stored positions for a trade date, empty when there are none."""
    frame = _load_frame(state_dir / "positions.parquet", POSITION_COLUMNS)
    return frame.loc[frame["trade_date"] == trade_date].reset_index(drop=True)
