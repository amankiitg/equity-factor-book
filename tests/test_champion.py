"""Sprint E5 Task 5: the champion rule and the registry update.

The rule text is byte-identical to its pre-registered value, exactly one
version is champion, and the champion is eligible.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from efb import registry

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "models" / "registry.json"


@pytest.mark.integration
def test_the_champion_rule_text_is_unchanged() -> None:
    payload = registry.load(REGISTRY)
    assert payload["champion_rule"] == registry.DEFAULT_CHAMPION_RULE
    assert payload["family_notes"] == registry.DEFAULT_FAMILY_NOTES


@pytest.mark.integration
def test_exactly_one_version_is_champion_and_it_is_eligible() -> None:
    payload = registry.load(REGISTRY)
    champions = [
        name for name, entry in payload["models"].items() if entry.get("champion")
    ]
    assert len(champions) == 1, champions
    champion = champions[0]
    assert payload["models"][champion]["eligible_for_champion"]
    # TS-v1 is diagnostic only and can never be champion
    assert champion != "TS-v1"


@pytest.mark.integration
def test_the_registry_still_validates_with_the_champion_declared() -> None:
    payload = registry.load(REGISTRY)
    assert registry.validate(payload) == []


def test_declare_champion_refuses_an_ineligible_version() -> None:
    import json
    import tempfile

    from efb.registry import declare_champion, model_entry, write_registry

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "registry.json"
        universe = Path(tmp) / "u"
        universe.write_text("x")
        write_registry(
            path,
            model_entry(
                version="A-v1",
                family="statistical",
                parameters={},
                universe_path=universe,
                data_paths=[universe],
                walkthrough="w",
                deliverable="d",
                results="r",
                champion=False,
                eligible_for_champion=False,
            ),
        )
        with pytest.raises(ValueError):
            declare_champion(path, "A-v1")
        payload = json.loads(path.read_text())
        assert not payload["models"]["A-v1"]["champion"]
