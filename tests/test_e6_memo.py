"""Sprint E6 Task 5: the hedge study's numbers are traceable to artifacts.

The rule for this project is that no number is typed by hand. The study is
prose, so it cannot be executed, but every headline number in it has to be
findable in a stored artifact or recomputed from one, and this test is what
makes that a property of the repository rather than a promise.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
MEMO = ROOT / "docs" / "research" / "E6_hedge_study.md"
RESULTS = ROOT / "sprints" / "E6" / "RESULTS.json"
REGISTRY = ROOT / "data" / "models" / "registry.json"
HEDGE = ROOT / "data" / "hedge"

# Every number the study leans on, at the rounding the study prints it at.
HEADLINE_NUMBERS = [
    "5.8e-15",  # worst absolute exposure after the exact FMP hedge
    "100.0%",  # idio share of variance after the exact FMP hedge
    "461.9",  # mean FMP name count
    "97.85%",  # long-only factor variance removed by the ETF hedge
    "0.9785",  # the same share, F6.4 form
    "13.0",  # mean instruments used
    "0.0017",  # long-only ETF hedge mean monthly cost
    "42.81%",  # momentum book factor variance removed by the ETF hedge
    "0.3816",  # residual size exposure, F6.5
    "0.3222",  # residual liquidity exposure, F6.5
    "0.1155",  # residual reversal exposure, F6.5
    "0.0503",  # residual momentum exposure, F6.5
    "0.0130",  # residual market beta exposure, F6.5
    "0.0168",  # residual sector_15 exposure, F6.5
    "0.1337",  # residual sector_45 exposure, F6.5
    "-0.0272",  # hedged momentum book realized beta, F6.3
    "-0.0495",  # unhedged momentum book realized beta
    "-0.0025",  # momentum book FMP hedge realized beta
    "0.0075",  # momentum book beta hedge realized beta
    "0.0065",  # decay curve at 5 days
    "0.0139",  # decay curve at 63 days
    "0.3326",  # long-only book unhedged realized beta
    "-0.2837",  # long-only book ETF hedge realized beta
    "0.0125",  # long-only book FMP hedge realized beta
    "-0.0552",  # long-only book beta hedge realized beta
    "0.7552",  # worst capped-stored FMP residual exposure
    "0.7169",  # the unhedged reversal exposure on that date
    "0.7640",  # long-only FMP hedge mean turnover
    "0.7925",  # momentum FMP hedge mean turnover
    "0.820",  # long-only ETF hedge mean turnover
    "0.0011",  # momentum FMP hedge mean monthly cost
    "0.0064",  # derived: 63-day minus 21-day decay beta
]


@pytest.fixture(scope="module")
def memo() -> str:
    """The study with newlines collapsed, so a phrase that wraps matches."""
    return " ".join(MEMO.read_text().split())


@pytest.fixture(scope="module")
def stored_numbers() -> list[float]:
    """Every number in the stored files and frames the study can cite."""
    texts = [RESULTS.read_text(), REGISTRY.read_text()]
    for name in (
        "hedge_metrics.parquet",
        "e6_efficacy.parquet",
        "e6_exposures.parquet",
        "e6_decay.parquet",
        "hedge_positions.parquet",
    ):
        frame = pd.read_parquet(HEDGE / name)
        texts.append(frame.select_dtypes(include="number").to_string())
    return [
        float(match)
        for text in texts
        for match in re.findall(r"-?\d+\.\d+(?:e-?\d+)?", text)
    ]


def test_the_study_exists_and_carries_the_required_sections(memo: str) -> None:
    for heading in (
        "## The answer, in one paragraph",
        "## Before and after: the FMP hedge",
        "## Before and after: the ETF minimum-variance hedge",
        "## Realized efficacy, 2018 to 2026",
        "## Efficacy against rebalancing frequency",
        "## Champion against alternative",
        "## Recommended hedge policy",
        "## What would falsify this?",
        "## The criteria, as stored",
    ):
        assert heading in memo, heading


def test_the_criteria_are_quoted_verbatim(memo: str) -> None:
    criteria = json.loads(RESULTS.read_text())["criteria"]
    for key in ("F6.1", "F6.2", "F6.3", "F6.4", "F6.5"):
        text = " ".join(criteria[key]["criterion"].split())
        assert text in memo, key


@pytest.mark.integration
def test_every_headline_number_is_in_the_study_and_traceable(
    memo: str, stored_numbers: list[float]
) -> None:
    missing_from_memo = [n for n in HEADLINE_NUMBERS if n not in memo]
    assert missing_from_memo == [], f"study does not quote {missing_from_memo}"
    derived = {"0.0064"}  # 63-day minus 21-day decay beta, recomputed in prose
    untraceable: list[str] = []
    for number in HEADLINE_NUMBERS:
        if number in derived:
            continue
        if number.endswith("%"):
            printed = abs(float(number[:-1])) / 100.0
            digits = len(number[:-1].split(".")[1])
        else:
            printed = abs(float(number))
            digits = len(number.split(".")[1].split("e")[0])
        tolerance = 0.5 * 10 ** (-digits)
        if not any(abs(abs(value) - printed) <= tolerance for value in stored_numbers):
            untraceable.append(number)
    assert untraceable == [], f"not traceable to an artifact: {untraceable}"


def test_the_derived_decay_number_matches_the_stored_curve() -> None:
    decay = pd.read_parquet(HEDGE / "e6_decay.parquet")
    momentum = decay.loc[decay["book"] == "seed_mom_ls"].set_index(
        "rebalance_frequency"
    )
    difference = float(
        momentum.loc[63.0, "realized_beta_to_mkt_rf"]
        - momentum.loc[21.0, "realized_beta_to_mkt_rf"]
    )
    assert difference == pytest.approx(0.0064, abs=0.00005)
