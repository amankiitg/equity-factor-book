"""Sprint E11 Part B: the README is traceable to artifacts.

Every headline number in README.md matches a stored value, with the sign
intact, read from the artifact named beside it. The test rounds the
stored value to the same decimals the README prints and asserts the
printed string is present.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DATA = ROOT / "data"


def _printed(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


@pytest.mark.integration
def test_readme_exists_and_names_the_handoff_files() -> None:
    text = README.read_text()
    assert "handoff/" in text
    assert "render.yaml" in text
    assert "XS-v1" in text


@pytest.mark.integration
def test_e1_headline_numbers_match_results() -> None:
    results = json.loads((ROOT / "sprints" / "E1" / "RESULTS.json").read_text())
    text = README.read_text()
    f13 = float(results["criteria"]["F1.3"]["stored_number"])
    f15 = float(
        results["criteria"]["F1.5"]["stored_numbers"]["naive_minus_pit_bp_per_year"]
    )
    assert _printed(f13, 4) in text  # F1.3 correlation, 0.9564
    assert _printed(f15, 2) in text  # survivorship bias, 365.10 bp per year


@pytest.mark.integration
def test_live_book_numbers_match_the_alpha_summary() -> None:
    summary = pd.read_parquet(DATA / "alpha" / "summary.parquet")
    row = summary.loc[summary["signal"] == "idio_momentum"].iloc[0]
    text = README.read_text()
    assert _printed(float(row["neutral_ic_h21_mean"]), 4) in text
    assert _printed(float(row["neutral_ic_h21_t"]), 2) in text
    assert _printed(float(row["ic_h1_mean"]), 4) in text
    assert _printed(float(row["ic_h1_t"]), 2) in text


@pytest.mark.integration
def test_stress_haircut_matches_the_artifact() -> None:
    haircut = float(
        pd.read_parquet(DATA / "eval" / "e5_stress_haircut.parquet")[
            "stress_haircut"
        ].iloc[0]
    )
    assert _printed(haircut, 4) in README.read_text()


@pytest.mark.integration
def test_the_neutral_ic_is_printed_with_its_sign() -> None:
    text = README.read_text()
    assert "-0.0031" in text  # the neutral IC is negative, printed signed
    assert "0.0031" not in text.replace("-0.0031", "")
