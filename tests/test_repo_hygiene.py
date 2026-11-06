"""The repository's own tree: no link where a directory belongs, in the index either."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts import check_symlinks

ROOT = Path(__file__).resolve().parents[1]


def test_the_worktree_and_the_index_are_free_of_the_symlink_accident() -> None:
    """Two accidents in three weeks, from both ends, and the same mess each time.

    A `.venv` link committed by a worktree replaced the real virtualenv with a link to
    itself on checkout; a `data` link committed in a worktree replaced the artifact tree
    with a pointer to one machine's gate copy. The guard is what stops the third.
    """
    assert check_symlinks.problems(ROOT) == []


def test_data_is_a_real_directory_here() -> None:
    assert (ROOT / "data").is_dir()
    assert not (ROOT / "data").is_symlink()


def test_the_guard_catches_a_link_in_the_worktree(tmp_path: Path) -> None:
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "data").symlink_to(tmp_path / "elsewhere")
    found = check_symlinks.problems(tmp_path)
    assert any("data: is a symlink" in line for line in found)


def test_the_guard_catches_a_link_the_index_holds(tmp_path: Path) -> None:
    """The index is what a checkout follows, so a link there is the accident even when
    the working tree looks right."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]

    subprocess.run([*git, "init", "-q"], cwd=repo, check=True, capture_output=True)
    (repo / "target").mkdir()
    (repo / ".venv").symlink_to(repo / "target")
    subprocess.run([*git, "add", "-A"], cwd=repo, check=True, capture_output=True)
    assert check_symlinks.tracked_as_symlink(".venv", repo)
    found = check_symlinks.problems(repo)
    assert any(".venv: git tracks a symlink" in line for line in found)


def test_gitignore_covers_both_forms_of_the_virtualenv() -> None:
    """A trailing slash matches a directory and not a link: how the link got in.

    Both forms are listed now: the bare name matches the link, and the slashed name and
    the wildcard keep the directory and anything like `.venv.old` out as well.
    """
    lines = {(ROOT / ".gitignore").read_text()}.pop().splitlines()
    stripped = {line.strip() for line in lines}
    assert ".venv" in stripped, "the bare pattern is the one that matches a link"
    assert ".venv*" in stripped, "and the wildcard covers a name the bare one misses"
