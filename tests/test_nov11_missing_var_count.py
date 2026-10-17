"""The count of names the risk block cannot measure is reported, not discarded."""

from __future__ import annotations

from live import notify


def message(**overrides: object) -> str:
    kwargs: dict[str, object] = {
        "status": "ok",
        "target_close": "2026-10-07",
        "dry_run": True,
        "orders": 12,
        "store": "x",
    }
    kwargs.update(overrides)
    return notify.compose(**kwargs)  # type: ignore[arg-type]


def test_the_count_is_said_out_loud_beside_the_dropped_names():
    text = message(
        no_risk=[{"ticker": "Q", "reason": "no specific variance"}],
        missing_var=3,
    )
    assert "Dropped for no risk estimate: Q" in text
    assert "3 universe name(s) have no row in the risk artifact" in text


def test_no_line_when_the_diagonal_measures_every_name():
    assert "no row in the risk artifact" not in message(missing_var=0)
    assert "no row in the risk artifact" not in message()


def test_the_manifest_records_the_count_the_diagonal_reports():
    # The summary field is what the run row and the page can read afterwards.
    from pathlib import Path

    source = Path("live/evening_job.py").read_text()
    assert '"n_specific_var_missing"' in source
    assert "n_missing_var" in source
