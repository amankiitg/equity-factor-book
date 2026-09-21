"""Sprint E9 Task 7: the cost and capacity memo is traceable to artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MEMO = ROOT / "docs" / "research" / "E9_tcost_capacity.md"
RESULTS = ROOT / "sprints" / "E9" / "RESULTS.json"


@pytest.fixture(scope="module")
def stored_numbers() -> list[float]:
    results = json.loads(RESULTS.read_text())
    texts = [json.dumps(results)]
    for stem in ("cost_curves", "capacity", "capacity_halving", "turnover_tradeoff"):
        frame = pd.read_parquet(DATA / "costs" / f"{stem}.parquet")
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
    for match in re.findall(r"-?\d+\.\d+", text):
        value = abs(float(match))
        digits = len(match.split(".")[1])
        tolerance = 0.5 * 10 ** (-digits)
        if not any(abs(abs(v) - value) <= tolerance for v in stored_numbers):
            offenders.append(match)
    assert offenders == [], f"numbers not traceable: {offenders}"


@pytest.mark.integration
def test_the_memo_states_the_undefined_capacity() -> None:
    text = " ".join(MEMO.read_text().split())
    assert "synthetic" in text
    assert "What would falsify this?" in text
