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


def test_every_evening_that_priced_a_book_publishes_its_names(
    written: dict[str, dict[str, object]],
) -> None:
    """The page's list against the run's own count, on every kind of evening.

    `book.names` is the only field the page draws that comes from a frame rather
    than from the manifest, so it is the only one that can go missing while every
    number around it stays right. On 2026-10-01 it did: the page read "The book: 0
    name(s)" over an empty table beside a gross of 100%, a correct hedge and 188
    orders, because `store_proposal` returned nothing while its docstring promised
    the rows. Every evening that priced a book carries the book its own manifest
    counted, so a writer that hands the page an empty list fails here instead of in
    a browser.

    The no-book evening is the one exception, and it is checked rather than
    skipped: its book is empty because the store held nothing for the close it
    asked for, which is the state that fixture exists to render. Asserting the
    emptiness here is what stops the exception from quietly widening to cover a
    fixture that should have rows.
    """
    without_book = "snapshot_no_book.json"
    empty = written[without_book]["book"]
    assert isinstance(empty, dict), without_book
    assert empty["names"] == [] and empty["n_names"] == 0, (
        f"{without_book} is the fixture for an evening whose store held no book, "
        "so an empty list and a zero count are its state; it has rows now, which "
        "means the exemption above it no longer applies"
    )
    for name in fixtures.NAMES:
        if name == without_book:
            continue
        payload = written[name]
        book = payload["book"]
        assert isinstance(book, dict), name
        names = book["names"]
        kept = book["n_kept"]
        assert isinstance(names, list) and names, f"{name} published no book at all"
        assert isinstance(kept, int | float), f"{name} states no kept count"
        assert len(names) == book["n_names"] == int(kept), (
            f"{name}: the page lists {len(names)} name(s) and n_names "
            f"{book['n_names']} against n_kept {kept}, so the list is not the "
            "book the run kept"
        )
        assert all(str(entry["ticker"]) for entry in names), name
        assert {entry["side"] for entry in names} <= {
            "long",
            "short",
        }, f"{name} has a row with no side"


def test_the_fixture_set_covers_every_evening_type(
    written: dict[str, dict[str, object]],
) -> None:
    """One fixture per kind of evening, rather than one edited into shapes.

    The four the page must render differently: an establishment evening, an
    ordinary rebalance, a stopped run and a closed day, plus the late and
    catch-up states the owner has to be able to tell apart.
    """
    statuses: dict[str, dict[str, object]] = {}
    for name in fixtures.NAMES:
        status = written[name]["run_status"]
        assert isinstance(status, dict), name
        statuses[name] = status
    assert [status["status"] for status in statuses.values()].count(
        "market_closed"
    ) == 1, "expected exactly one closed-day fixture"
    assert [
        name
        for name, status in statuses.items()
        if status["status"] in {"stale_stopped", "error"}
    ], "no fixture is a stopped run"
    opened = [name for name, status in statuses.items() if status["establishment"]]
    assert len(opened) == 1, "expected exactly one establishment fixture"
    assert statuses[opened[0]]["cost_label"] == "establishment"
    ordinary = [
        name
        for name, status in statuses.items()
        if status["status"] == "ok"
        and not status["establishment"]
        and not status["catch_up"]
    ]
    assert ordinary, "no fixture is an ordinary rebalance"
    assert all(statuses[name]["cost_label"] == "rebalance" for name in ordinary)


def test_the_establishment_snapshot_opens_the_book_from_flat(
    written: dict[str, dict[str, object]],
) -> None:
    """The first evening: every row is a position opened, not a move."""
    name = "snapshot_establishment.json"
    assert name in written
    status = written[name]["run_status"]
    assert isinstance(status, dict)
    assert status["establishment"] is True
    assert status["cost_label"] == "establishment"
    book = written[name]["book"]
    assert isinstance(book, dict)
    names = book["names"]
    assert isinstance(names, list) and names
    assert {entry["reason"] for entry in names} == {
        "new position"
    }, "an establishment evening has no earlier book, so nothing moved"
