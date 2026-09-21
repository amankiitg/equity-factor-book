"""The Methodology tab must serve documents the browser can actually open.

Links go through Streamlit's static route, so two things have to hold: the
documents are copied into the static folder, and static serving is enabled.
Both are checked here because the failure mode is silent: a bare relative
link returns 200 with the app shell, so a link check alone would pass while
the reader sees the dashboard reload.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from dashboard import publish
from dashboard.tabs import methodology

ROOT = Path(__file__).resolve().parents[1]


def test_publish_copies_every_existing_linked_document(tmp_path: Path) -> None:
    published = publish.publish(static_dir=tmp_path)
    expected = [rel for _label, rel in methodology.LINKS if (ROOT / rel).exists()]
    assert published == expected
    assert published, "nothing was published, the link table is probably empty"
    for rel in published:
        assert (tmp_path / rel).exists()
        assert (tmp_path / rel).stat().st_size > 0


def test_publish_skips_documents_that_do_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the rendered notebooks are gitignored, so a fresh clone has none yet
    monkeypatch.setattr(
        methodology, "LINKS", [*methodology.LINKS, ("Nope", "sprints/E10/PRD.md")]
    )
    published = publish.publish(static_dir=tmp_path)
    assert "sprints/E10/PRD.md" not in published
    assert not (tmp_path / "sprints" / "E10" / "PRD.md").exists()


def test_static_serving_is_enabled() -> None:
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())
    assert config["server"]["enableStaticServing"] is True


def test_link_prefix_is_the_static_route() -> None:
    assert publish.LINK_PREFIX == "app/static/docs"
    assert publish.STATIC_DIR == ROOT / "dashboard" / "static" / "docs"
