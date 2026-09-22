"""Sprint E10 Task 8: the risk policy memo is traceable to artifacts.

The memo numbers must match the stored artifacts with the sign intact,
and every criterion's text must appear verbatim from RESULTS.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MEMO = ROOT / "docs" / "research" / "E10_risk_policy.md"
RESULTS = ROOT / "sprints" / "E10" / "RESULTS.json"

_FLOAT = r"-?\d+\.\d+(?:e-?\d+)?"


@pytest.fixture(scope="module")
def stored_numbers() -> list[float]:
    results = json.loads(RESULTS.read_text())
    config = json.loads((DATA / "allocation" / "config.json").read_text())
    texts = [json.dumps(results), json.dumps(config)]
    for stem in (
        "kelly",
        "drawdown",
        "voltarget",
        "voltarget_daily",
        "stoploss",
        "regime",
    ):
        frame = pd.read_parquet(DATA / "allocation" / f"{stem}.parquet")
        texts.append(frame.select_dtypes(include="number").to_string())
    return [float(match) for text in texts for match in re.findall(_FLOAT, text)]


def _untraceable(memo_text: str, stored: list[float]) -> list[str]:
    """The memo numbers that do not match a stored number, sign included."""
    text = " ".join(memo_text.split())
    offenders: list[str] = []
    for match in re.findall(_FLOAT, text):
        value = float(match)
        digits = len(match.split(".")[1])
        tolerance = 0.5 * 10 ** (-digits)
        if not any(abs(value - v) <= tolerance for v in stored):
            offenders.append(match)
    return offenders


@pytest.mark.integration
def test_the_memo_exists_and_is_traceable(stored_numbers: list[float]) -> None:
    assert MEMO.exists()
    offenders = _untraceable(MEMO.read_text(), stored_numbers)
    assert offenders == [], f"numbers not traceable: {offenders}"


@pytest.mark.integration
def test_a_flipped_sign_is_rejected() -> None:
    # signed matching: the sign is part of the value, so a memo that
    # prints +0.1994 where -0.1994 is stored must fail
    stored = [-0.1994]
    assert _untraceable("| gap | 0.1994 |", stored) == ["0.1994"]
    assert _untraceable("| gap | -0.1994 |", stored) == []


@pytest.mark.integration
def test_each_stored_criterion_appears_verbatim() -> None:
    results = json.loads(RESULTS.read_text())
    memo_text = " ".join(MEMO.read_text().split())
    missing: list[str] = []
    for key in ("F10.1", "F10.1b", "F10.2", "F10.2b", "F10.3", "F10.3b"):
        criterion = " ".join(results["criteria"][key]["criterion"].split())
        if criterion not in memo_text:
            missing.append(key)
    assert missing == [], f"criteria not verbatim in the memo: {missing}"


@pytest.mark.integration
def test_the_memo_states_the_kelly_verdict() -> None:
    text = " ".join(MEMO.read_text().split())
    assert "What would falsify this?" in text
    assert "half Kelly" in text
    assert "synthetic" in text
