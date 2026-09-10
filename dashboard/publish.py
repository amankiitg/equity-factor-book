"""Publish the sprint documents the Methodology tab links to.

Streamlit only serves files over HTTP from its static folder, so a plain
relative link such as `sprints/E2/PRD.md` falls through to the app shell and
clicking it shows the dashboard again. This copies every linked document into
`dashboard/static/docs/` and the tab links to `/app/static/docs/` instead.
Static serving is switched on in `.streamlit/config.toml`.

Run with `make publish`, which `make dashboard` depends on.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "dashboard" / "static" / "docs"

# Streamlit serves `static/` next to the main script under this route.
LINK_PREFIX = "app/static/docs"


def publish(static_dir: Path = STATIC_DIR) -> list[str]:
    """Copy every existing linked document under `static_dir`; return its path."""
    from dashboard.tabs.methodology import LINKS

    published: list[str] = []
    for _label, rel in LINKS:
        source = ROOT / rel
        if not source.exists():
            continue
        destination = static_dir / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        published.append(rel)
    return published


def main() -> None:
    published = publish()
    print(f"published {len(published)} documents to {STATIC_DIR.relative_to(ROOT)}")
    for rel in published:
        print(f"  /{LINK_PREFIX}/{rel}")


if __name__ == "__main__":
    main()
