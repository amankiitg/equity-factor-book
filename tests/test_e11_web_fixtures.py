"""The page's fixtures are the writer's own output, and they stay that way.

Two things are checked here and nowhere else. First, that every committed fixture
is byte-for-byte what `scripts/make_web_fixtures.py` produces now, which is what
stops a fixture from being hand-edited into agreement with a page that is wrong.
Second, that each state variant really carries the state it is named for, so a
test that renders `snapshot_error.json` is testing the error path.
"""

from __future__ import annotations

import json

import jsonschema
import pytest

from live import snapshot
from scripts import make_web_fixtures as fixtures

SCHEMA = json.loads((fixtures.ROOT / "docs" / "snapshot.schema.json").read_text())


def _close(value: object) -> str:
    """The date part of an ISO close, which is how the page compares two closes."""
    return str(value).split("T", 1)[0]


@pytest.fixture(scope="module")
def written() -> dict[str, dict[str, object]]:
    """Every fixture, built once for the whole module."""
    return fixtures.snapshots()


def test_the_schema_is_a_schema_the_page_can_validate_against() -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("name", fixtures.NAMES)
def test_every_fixture_is_what_the_writer_produces_now(
    name: str, written: dict[str, dict[str, object]]
) -> None:
    committed = json.loads((fixtures.FIXTURE_DIR / name).read_text())
    assert committed == json.loads(snapshot.payload_text(written[name])), (
        f"{name} is not what the writer produces: rebuild it with "
        "'python scripts/make_web_fixtures.py'"
    )


@pytest.mark.parametrize("name", fixtures.NAMES)
def test_every_fixture_validates_against_the_schema(
    name: str, written: dict[str, dict[str, object]]
) -> None:
    jsonschema.validate(written[name], SCHEMA)


def test_the_ok_snapshot_carries_the_book_and_both_exposure_vectors(
    written: dict[str, dict[str, object]],
) -> None:
    ok = written[fixtures.NAMES[0]]
    assert _close(ok["book_as_of"]) == fixtures.CLOSE
    assert _close(ok["target_close"]) == fixtures.CLOSE
    assert str(ok["book_as_of"]) == str(
        ok["target_close"]
    ), "the ok snapshot's book is the close it asked for, spelled the same way"
    book = ok["book"]
    assert isinstance(book, dict)
    names = book["names"]
    assert isinstance(names, list) and names
    weights = [abs(float(entry["weight"])) for entry in names]
    assert weights == sorted(weights, reverse=True), "the book is by absolute weight"
    before = ok["exposures_before_hedge"]
    after = ok["exposures_after_hedge"]
    assert isinstance(before, dict) and isinstance(after, dict)
    worst_before = max(abs(float(value)) for value in before.values())
    worst_after = max(abs(float(value)) for value in after.values())
    assert worst_before > 1e-3, f"the pre-hedge vector is only {worst_before:.3e}"
    assert worst_after < 1e-10, f"the hedge left {worst_after:.3e}"
    assert list(before) == list(after)


def test_the_stopped_snapshot_shows_the_last_book_under_its_own_close(
    written: dict[str, dict[str, object]],
) -> None:
    stopped = written[fixtures.NAMES[1]]
    status = stopped["run_status"]
    assert isinstance(status, dict)
    assert status["status"] == "stale_stopped"
    assert status["worst_sessions_behind"] == 3
    # The book is the last one that exists, dated by its own close, while the
    # target close is the one the run could not reach.
    assert _close(stopped["book_as_of"]) == fixtures.CLOSE
    assert _close(stopped["target_close"]) == fixtures.STOPPED_CLOSE
    assert str(stopped["book_as_of"]) != str(stopped["target_close"])


def test_the_error_snapshot_names_what_failed(
    written: dict[str, dict[str, object]],
) -> None:
    failed = written[fixtures.NAMES[2]]
    status = failed["run_status"]
    assert isinstance(status, dict)
    assert status["status"] == "error"
    assert status["failing_inputs"] == ["prices", "shares"]
    assert status["detail"]


def test_the_expired_snapshot_is_past_its_own_deadline(
    written: dict[str, dict[str, object]],
) -> None:
    late = written[fixtures.NAMES[3]]
    generated = str(late["generated_at"])
    deadline = str(late["expected_next_by"])
    assert deadline and generated > deadline
    status = late["run_status"]
    assert isinstance(status, dict)
    assert status["status"] == "ok", "expiry is the clock's, not the run's"


def test_the_catch_up_snapshot_names_the_evenings_it_caught(
    written: dict[str, dict[str, object]],
) -> None:
    caught = written[fixtures.NAMES[4]]
    status = caught["run_status"]
    assert isinstance(status, dict)
    assert status["catch_up"] is True
    assert status["catch_up_sessions"] == [fixtures.NEXT_CLOSE, "2026-09-23"]
    assert _close(caught["target_close"]) == fixtures.CATCH_UP_CLOSE


def test_the_fixture_set_is_exactly_the_states_the_page_tests(
    written: dict[str, dict[str, object]],
) -> None:
    assert set(written) == set(fixtures.NAMES)
    committed = sorted(path.name for path in fixtures.FIXTURE_DIR.glob("*.json"))
    assert committed == sorted(
        fixtures.NAMES
    ), "the fixtures directory holds exactly the set the writer produces"
