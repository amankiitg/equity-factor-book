"""Refuse a commit where `data/` or `.venv` is a link, or tracked as one.

Two accidents in three weeks made the same mess from opposite ends. `.gitignore` said
`.venv/`, which matches a directory and not a link, so a worktree's link to the shared
virtualenv went into the index; a checkout of that branch then replaced the real
virtualenv with a link to itself. And a commit made in a worktree where `data/` had been
replaced by a link to the gate copy recorded that link in place of the artifact tree, so
every checkout pointed its data at one machine's scratch directory.

A guard, not a convention: `make symlink-guard` runs it, `make hooks` installs it as a
pre-commit hook, and `tests/test_repo_hygiene.py` runs it in the gate, so a commit that
would repeat either accident fails before it exists.

Exit code 1 with one line per problem, 0 when both paths are what they should be.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The two paths that must be a real directory and an untracked virtualenv.
DIRECTORY_PATHS = ("data",)
UNTRACKED_PATHS = (".venv",)
# Git's mode for a symlink, in `ls-files -s`.
SYMLINK_MODE = "120000"


def tracked_as_symlink(path: str, root: Path | None = None) -> bool:
    """Whether git's index holds `path` as a symlink, whatever the worktree shows."""
    base = Path(root) if root is not None else ROOT
    try:
        out = subprocess.run(
            ["git", "ls-files", "-s", "--", path],
            cwd=base,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return False
    return any(line.split(maxsplit=1)[0] == SYMLINK_MODE for line in out.splitlines())


def problems(root: Path | None = None) -> list[str]:
    """Every reason the tree would repeat the accident, as one line each."""
    base = Path(root) if root is not None else ROOT
    found: list[str] = []
    for name in DIRECTORY_PATHS:
        path = base / name
        if path.is_symlink():
            found.append(
                f"{name}: is a symlink (to {path.readlink()}); it must be a real "
                "directory, because every checkout resolves it"
            )
        if tracked_as_symlink(name, base):
            found.append(
                f"{name}: git tracks a symlink here, so a checkout replaces the tree "
                "with a link; restore the directory from the commit before it"
            )
    for name in UNTRACKED_PATHS:
        path = base / name
        if path.is_symlink():
            found.append(
                f"{name}: is a symlink (to {path.readlink()}); a worktree's link to "
                "the shared virtualenv must stay out of the worktree and the index"
            )
        if tracked_as_symlink(name, base):
            found.append(
                f"{name}: git tracks a symlink at this path; take it out of the index "
                "and let .gitignore cover both the directory and the link"
            )
    return found


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    base = Path(args[0]) if args else ROOT
    found = problems(base)
    for line in found:
        print(f"symlink guard: {line}", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
