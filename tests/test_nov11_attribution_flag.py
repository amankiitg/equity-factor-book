"""The attribution step's outcome reaches the row and the message (item 28)."""

from __future__ import annotations

from live import notify


def message(flags: list[dict[str, object]]) -> str:
    return notify.compose(
        status="ok",
        target_close="2026-10-09",
        dry_run=True,
        orders=12,
        store="x",
        flags=flags,
    )


def test_a_successful_step_says_how_many_sessions_it_stored() -> None:
    text = message(
        [{"kind": "attribution", "outcome": "stored", "n_stored": 10, "n_done": 4}]
    )
    assert "Attribution: 10 session(s) stored, 4 already attributed." in text
    # And it is not read as a large move.
    assert "Large moves" not in text


def test_a_failed_step_says_so_and_names_the_exception() -> None:
    text = message(
        [
            {
                "kind": "attribution",
                "outcome": "failed",
                "error": "FileNotFoundError: beta_history.parquet",
            }
        ]
    )
    assert "Attribution: the step failed" in text
    assert "FileNotFoundError: beta_history.parquet" in text
    assert "not being written" in text


def test_large_moves_still_read_as_large_moves() -> None:
    text = message(
        [
            {"ticker": "XYZ", "return": 0.42, "flag": "40% move"},
            {"kind": "attribution", "outcome": "stored", "n_stored": 1, "n_done": 0},
        ]
    )
    assert "Large moves: XYZ +42.0% (40% move)." in text
    assert "Attribution: 1 session(s) stored, 0 already attributed." in text


def test_the_subject_does_not_count_a_step_flag_as_a_large_move() -> None:
    # The inbox line's last field is the unexplained *moves*; a step's outcome is
    # not one, and counting it would put a flag on the subject of every evening the
    # attribution ran.
    subject = notify.subject_text(
        status="ok",
        target_close="2026-10-09",
        dry_run=False,
        orders=171,
        flags=[{"kind": "attribution", "outcome": "stored", "n_stored": 10}],
    )
    assert "flag" not in subject
    moved = notify.subject_text(
        status="ok",
        target_close="2026-10-09",
        dry_run=False,
        orders=171,
        flags=[{"ticker": "XYZ", "return": 0.42, "flag": "40% move"}],
    )
    assert "flag 1" in moved
