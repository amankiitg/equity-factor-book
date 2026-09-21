"""Sprint E10 Task 8: the risk policy memo is traceable to artifacts."""

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


@pytest.fixture(scope="module")
def stored_numbers() -> list[float]:
    results = json.loads(RESULTS.read_text())
    config = json.loads((DATA / "allocation" / "config.json").read_text())
    texts = [json.dumps(results), json.dumps(config)]
    for stem in ("kelly", "drawdown", "voltarget", "stoploss", "regime"):
        frame = pd.read_parquet(DATA / "allocation" / f"{stem}.parquet")
        texts.append(frame.select_dtypes(include="number").to_string())
    return [
        float(match)
        for text in texts
        for match in re.findall(r"-?\d+\.\d+(?:e-?\d+)?", text)
    ]


@pytest.mark.integration
def test_the_memo_exists_and_is_traceable(stored_numbers: list[float]) -> None:
    assert MEMO.exists()
    text = " ".join(MEMO.read_text().split())
    offenders: list[str] = []
    for match in re.findall(r"-?\d+\.\d+(?:e-?\d+)?", text):
        value = abs(float(match))
        digits = len(match.split(".")[1])
        tolerance = 0.5 * 10 ** (-digits)
        if not any(abs(abs(v) - value) <= tolerance for v in stored_numbers):
            offenders.append(match)
    assert offenders == [], f"numbers not traceable: {offenders}"


@pytest.mark.integration
def test_the_memo_states_the_kelly_verdict() -> None:
    text = " ".join(MEMO.read_text().split())
    assert "What would falsify this?" in text
    assert "half Kelly" in text
    assert "synthetic" in text
