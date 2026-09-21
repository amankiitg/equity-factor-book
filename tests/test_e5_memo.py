"""Sprint E5 Task 7: the memo's numbers are traceable to stored artifacts.

The rule for this project is that no number is typed by hand. The memo is
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
MEMO = ROOT / "docs" / "research" / "E5_risk_model_diagnostic.md"
RESULTS = ROOT / "sprints" / "E5" / "RESULTS.json"
REGISTRY = ROOT / "data" / "models" / "registry.json"
EVAL = ROOT / "data" / "eval"

# Every number the memo leans on, at the rounding the memo prints it at.
HEADLINE_NUMBERS = [
    "0.0607",  # champion XS-v1, mean |bias-1|
    "0.0672",  # XS-v2
    "0.1388",  # PCA-v1
    "0.1392",  # PCA-v1c
    "1.1050",  # xs_v1 long only
    "1.0186",  # xs_v1 long short
    "0.9726",  # xs_v1 factor tilted
    "1.0917",  # xs_v1 sector concentrated
    "1.1048",  # xs_v2 long only
    "1.0256",  # xs_v2 long short
    "0.9426",  # xs_v2 factor tilted
    "1.0809",  # xs_v2 sector concentrated
    "1.1304",  # sample long only
    "1.0752",  # sample long short
    "1.1859",  # sample factor tilted
    "1.1258",  # sample sector concentrated
    "1.1286",  # pca_v1 long only
    "1.0729",  # pca_v1 long short
    "1.2238",  # pca_v1 factor tilted
    "1.1301",  # pca_v1 sector concentrated
    "1.1284",  # pca_v1c long only
    "1.0755",  # pca_v1c long short
    "1.2177",  # pca_v1c factor tilted
    "1.1352",  # pca_v1c sector concentrated
    "1.1312",  # ts_v1 long only
    "1.0663",  # ts_v1 long short
    "1.6456",  # ts_v1 factor tilted
    "1.2343",  # ts_v1 sector concentrated
    "0.0755",  # pca_v1c long/short distance, F5.2
    "0.0752",  # sample long/short distance, F5.2
    "2.8471",  # champion 2020 Q1 bias
    "2.8305",  # XS-v2 2020 Q1 bias
    "3.2050",  # sample 2020 Q1 bias
    "3.2236",  # pca_v1 2020 Q1 bias
    "3.2320",  # pca_v1c 2020 Q1 bias
    "3.4989",  # ts_v1 2020 Q1 bias
    "1.1393",  # champion 2022 bias
    "1.1292",  # XS-v2 2022 bias
    "1.3239",  # champion high-VIX bias
    "3.6738",  # champion worst family, 2020 Q1 long only
    "1.8471",  # recommended stress haircut
    "0.9691",  # XS-v2 / XS-v1, factor tilted
    "0.9998",  # XS-v2 / XS-v1, long only
    "1.0069",  # XS-v2 / XS-v1, long short
    "0.9901",  # XS-v2 / XS-v1, sector concentrated
    "1.0385",  # closest mean family bias, F5.1
    "0.9787",  # champion horizon scaled, long only
    "1.1594",  # champion horizon direct, long only
]


@pytest.fixture(scope="module")
def memo() -> str:
    """The memo with newlines collapsed, so a phrase that wraps still matches."""
    return " ".join(MEMO.read_text().split())


@pytest.fixture(scope="module")
def stored_numbers() -> list[float]:
    """Every number in the stored files and frames the memo can cite."""
    texts = [RESULTS.read_text(), REGISTRY.read_text()]
    for name in (
        "e5_family_bias.parquet",
        "e5_regimes.parquet",
        "e5_horizon.parquet",
        "e5_stress_haircut.parquet",
    ):
        frame = pd.read_parquet(EVAL / name)
        texts.append(frame.select_dtypes(include="number").to_string())
    return [
        float(match)
        for text in texts
        for match in re.findall(r"-?\d+\.\d+(?:e-?\d+)?", text)
    ]


def test_the_memo_exists_and_carries_the_required_sections(memo: str) -> None:
    for heading in (
        "## The answer, in one paragraph",
        "## The champion decision",
        "## The full heatmap",
        "## The criteria, as stored",
        "## The regime table",
        "## XS-v2 against XS-v1",
        "## The champion's known weaknesses",
        "## What would falsify this?",
    ):
        assert heading in memo, heading


def test_the_champion_rule_is_quoted_verbatim(memo: str) -> None:
    registry = json.loads(REGISTRY.read_text())
    rule = registry["champion_rule"]
    assert " ".join(rule.split()) in memo


@pytest.mark.integration
def test_every_headline_number_is_in_the_memo_and_traceable(
    memo: str, stored_numbers: list[float]
) -> None:
    missing_from_memo = [n for n in HEADLINE_NUMBERS if n not in memo]
    assert missing_from_memo == [], f"memo does not quote {missing_from_memo}"
    # the four champion scores are means of the stored family table rather
    # than stored numbers; the dedicated test below pins them to the table
    derived = {"0.0607", "0.0672", "0.1388", "0.1392"}
    untraceable: list[str] = []
    for number in HEADLINE_NUMBERS:
        if number in derived:
            continue
        printed = abs(float(number))
        digits = len(number.split(".")[1])
        tolerance = 0.5 * 10 ** (-digits)
        if not any(abs(abs(value) - printed) <= tolerance for value in stored_numbers):
            untraceable.append(number)
    assert untraceable == [], f"not traceable to an artifact: {untraceable}"


@pytest.mark.integration
def test_the_champion_scores_are_the_stored_family_means() -> None:
    """The four deciding numbers are means of the stored family table."""
    family = pd.read_parquet(EVAL / "e5_family_bias.parquet")
    scores = family.groupby("version")["abs_bias_minus_1"].mean().round(4)
    expected = {"xs_v1": 0.0607, "xs_v2": 0.0672, "pca_v1": 0.1388, "pca_v1c": 0.1392}
    for version, value in expected.items():
        assert float(scores[version]) == pytest.approx(value, abs=1e-4), version


@pytest.mark.integration
def test_the_heatmap_cells_are_the_stored_family_bias() -> None:
    family = pd.read_parquet(EVAL / "e5_family_bias.parquet")
    pivot = family.pivot(index="version", columns="family", values="bias").round(4)
    memo_text = " ".join(MEMO.read_text().split())
    for version in pivot.index:
        for column in pivot.columns:
            cell = f"{pivot.loc[version, column]:.4f}"
            assert cell in memo_text, (version, column, cell)


def test_the_failures_are_stated_with_their_mechanisms(memo: str) -> None:
    assert "F5.1" in memo and "fail" in memo
    assert "F5.2" in memo
    assert "0.0003" in memo, "the F5.2 mechanism is the three-ten-thousandths miss"
    assert "13 trading days" in memo
