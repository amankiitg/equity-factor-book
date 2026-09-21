"""Sprint E8 Task 8: the construction memo is traceable to stored artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MEMO = ROOT / "docs" / "research" / "E8_construction_memo.md"
RESULTS = ROOT / "sprints" / "E8" / "RESULTS.json"


@pytest.fixture(scope="module")
def stored_numbers() -> list[float]:
    results = json.loads(RESULTS.read_text())
    summary = pd.read_parquet(DATA / "portfolios" / "e8_summary.parquet")
    resampling = pd.read_parquet(DATA / "portfolios" / "e8_f84_resampling.parquet")
    neff = pd.read_parquet(DATA / "portfolios" / "e8_neff.parquet")
    realized_ic = pd.read_parquet(DATA / "portfolios" / "e8_realized_ic.parquet")
    texts = [
        json.dumps(results),
        summary.select_dtypes(include="number").to_string(),
        resampling.select_dtypes(include="number").to_string(),
        neff.select_dtypes(include="number").to_string(),
        realized_ic.select_dtypes(include="number").to_string(),
    ]
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
def test_the_memo_names_the_synthetic_label() -> None:
    text = " ".join(MEMO.read_text().split())
    assert "controlled experiment" in text
    assert "What would falsify this?" in text
