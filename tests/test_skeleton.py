"""Sanity checks for the repo skeleton.

Every sprint must leave this suite green. The test suite never shrinks.
"""

from pathlib import Path

import efb

ROOT = Path(__file__).resolve().parents[1]


def test_package_imports_and_has_version() -> None:
    assert efb.__version__.count(".") == 2


def test_expected_directories_exist() -> None:
    for rel in [
        "data/raw",
        "data/processed",
        "data/models",
        "data/cov",
        "data/eval",
        "data/hedge",
        "data/alpha",
        "data/portfolios",
        "data/costs",
        "data/allocation",
        "data/attribution",
        "efb/models",
        "dashboard/tabs",
        "live",
        "notebooks",
        "sprints",
        "docs/research",
        "tests",
    ]:
        assert (ROOT / rel).is_dir(), f"missing directory: {rel}"


def test_standards_documents_exist() -> None:
    for rel in [
        "docs/engineering_standards.md",
        "docs/roadmap_v2.md",
        "docs/Equity_Factor_Book_Roadmap_v2.docx",
        "data/VERSION.json",
        "Makefile",
        "pyproject.toml",
        ".pre-commit-config.yaml",
        "README.md",
        ".gitignore",
    ]:
        assert (ROOT / rel).is_file(), f"missing file: {rel}"


def test_claude_command_files_exist() -> None:
    for rel in [
        ".claude/commands/quant-prd.md",
        ".claude/commands/quant-dev.md",
        ".claude/commands/quant-walkthrough.md",
    ]:
        assert (ROOT / rel).is_file(), f"missing file: {rel}"
