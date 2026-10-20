"""Shared helpers for the owner-fix restore scripts.

`scripts/restore_attribution.py` and `scripts/restore_reconciliation.py` both read a
JSON backup taken before a write and put the stored rows back. The comparison they
print is the point of the exercise: it has to show the columns the write was meant to
move, and prove that nothing else moved. That comparison lives here.
"""

from __future__ import annotations

import json
import pathlib
from decimal import Decimal
from typing import Any

import pandas as pd

from live import store

# Timestamps and jsonb come back from the store as objects and from the backup as
# strings, so they are compared through their parsed form.
STAMPS = ("trade_date", "written_at")

# Postgres `numeric` arrives as Decimal and json-decoded numbers as int or float.
NUMERIC = (int, float, Decimal)


def load_backup(path: pathlib.Path) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """The backup rows, both as stored in the JSON and re-encoded for `store.upsert`."""
    payload = json.loads(path.read_text())
    prepared: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for raw in payload["rows"]:
        clean: dict[str, Any] = {}
        for key, value in raw.items():
            if value is None:
                clean[key] = None
            elif isinstance(value, (dict, list)):
                clean[key] = store.json_text(value, sort_keys=True)
            elif key in STAMPS:
                clean[key] = pd.Timestamp(value).to_pydatetime()
            else:
                clean[key] = value
        prepared.append((raw, clean))
    return prepared


def missing(value: Any) -> bool:
    """`None` and NaN are the same absence here: the backup encodes one as the other."""
    return value is None or (isinstance(value, float) and pd.isna(value))


def _same_float(left: Any, right: Any) -> bool:
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return False


def diff_row(before: dict[str, Any], now: dict[str, Any]) -> list[str]:
    """The columns that differ between a backup row and the row stored now."""
    changed: list[str] = []
    for key, left in before.items():
        right = now.get(key)
        if missing(left) and missing(right):
            continue
        if key in STAMPS:
            if pd.Timestamp(left) != pd.Timestamp(right):
                changed.append(key)
        elif isinstance(left, (dict, list)) or isinstance(right, (dict, list)):
            if json.dumps(left, sort_keys=True) != json.dumps(right, sort_keys=True):
                changed.append(key)
        elif isinstance(left, NUMERIC) and isinstance(right, NUMERIC):
            if not _same_float(left, right):
                changed.append(key)
        elif str(left) != str(right):
            changed.append(key)
    return changed


def pct(value: Any) -> str:
    if missing(value):
        return "-"
    return f"{float(value) * 100:.2f}%"


def money(value: Any) -> str:
    if missing(value):
        return "-"
    return f"{float(value):,.2f}"
