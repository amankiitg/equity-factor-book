"""Sprint E12 item 6: the attribution section of the page, and its contract.

The page reads one document, `docs/snapshot.schema.json` is that document's
contract, and `live.snapshot.build` is the only writer. So the things worth
pinning are that the block the builder emits is the block the schema declares,
that the cumulative sums are the stored rows' own sums rather than a second
reconstruction, and that a run which could not read the attribution store says so
on the page instead of showing an empty table.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from live import snapshot

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs" / "snapshot.schema.json"
# The sprint's own artifact: the seed book's stored attribution, which is what the
# page and the fixtures show until the live days exist.
SEED_ATTRIBUTION = ROOT / "data" / "attribution" / "daily.parquet"


@pytest.fixture(scope="module")
def seed_frame() -> pd.DataFrame:
    if not SEED_ATTRIBUTION.exists():
        pytest.skip("the seed attribution artifact is not built")
    return pd.read_parquet(SEED_ATTRIBUTION)


def test_the_seed_artifact_reports_its_own_sums(seed_frame: pd.DataFrame) -> None:
    """Cumulative is the stored rows' sum, not a recomputation of them."""
    block = snapshot.attribution_block(seed_frame)
    assert block["n_days"] == len(seed_frame)
    assert block["cumulative"]["pnl_total"] == pytest.approx(
        float(seed_frame["pnl_total"].sum())
    )
    assert block["cumulative"]["pnl_factor"] == pytest.approx(
        float(seed_frame["pnl_factor"].sum())
    )
    assert block["cumulative"]["pnl_idio"] == pytest.approx(
        float(seed_frame["pnl_idio"].sum())
    )
    assert block["cumulative"]["pnl_cost"] == pytest.approx(
        float(seed_frame["pnl_cost"].sum())
    )
    # The worst day of the identity, not the sum of the residuals: a decomposition
    # is checked per day, and a summed residual of zero would hide two bad days.
    assert block["cumulative"]["max_identity_residual"] == pytest.approx(
        float(seed_frame["identity_residual"].abs().max())
    )
    assert block["cumulative"]["n_computed_specific"] == int(
        seed_frame["n_computed_specific"].sum()
    )


def test_the_per_factor_totals_are_the_stored_maps(seed_frame: pd.DataFrame) -> None:
    block = snapshot.attribution_block(seed_frame)
    expected: dict[str, float] = {}
    for mapping in seed_frame["pnl_factor_json"]:
        for name, value in mapping.items():
            expected[name] = expected.get(name, 0.0) + float(value)
    assert set(block["by_factor"]) == set(expected)
    for name, value in expected.items():
        assert block["by_factor"][name] == pytest.approx(value)


def test_the_daily_series_is_the_window_newest_last_and_days_not_timestamps(
    seed_frame: pd.DataFrame,
) -> None:
    block = snapshot.attribution_block(seed_frame)
    assert len(block["daily"]) == snapshot.ATTRIBUTION_DAYS
    days = [day["trade_date"] for day in block["daily"]]
    assert days == sorted(days), "the series is not in date order"
    assert days[-1] == block["last_day"]
    for day in days:
        assert len(str(day)) == 10, f"a date carries a time: {day}"
    # Every day carries the lines the section shows, including the hedge's own
    # factor P&L and the raw-beta line.
    for key in ("pnl_timing", "book_beta", "pnl_beta", "market_return"):
        assert key in block["daily"][0], key


def test_a_cost_row_populates_realized_against_expected() -> None:
    """The two cost numbers travel separately, so the page can show both."""
    frame = pd.DataFrame(
        {
            "trade_date": ["2026-09-21"],
            "pnl_total": [0.001],
            "pnl_factor": [0.0005],
            "pnl_idio": [0.0008],
            "pnl_cost": [-0.0003],
            "identity_residual": [0.0],
            "n_computed_specific": [0],
            "pnl_factor_json": [{"market": 0.0005}],
            "pnl_timing": [0.0001],
            "book_beta": [0.02],
            "market_return": [0.005],
            "pnl_beta": [0.0001],
            "realized_vol": [0.07],
            "forecast_vol": [0.10],
            "expected_cost_bps": [15.0],
            "realized_cost_bps": [11.0],
        }
    )
    block = snapshot.attribution_block(frame)
    assert block["cost"]["expected_bps"] == pytest.approx(15.0)
    assert block["cost"]["realized_bps"] == pytest.approx(11.0)
    assert block["cost"]["n_realized"] == 1


def test_an_unrealized_cost_is_counted_as_missing_rather_than_zero() -> None:
    """A cost nobody measured is not a cost of nothing."""
    frame = pd.DataFrame(
        {
            "trade_date": ["2026-09-21", "2026-09-22"],
            "pnl_total": [0.001, 0.002],
            "pnl_factor": [0.0, 0.0],
            "pnl_idio": [0.001, 0.002],
            "pnl_cost": [0.0, 0.0],
            "identity_residual": [0.0, 0.0],
            "n_computed_specific": [0, 0],
            "pnl_factor_json": [{"market": 0.0}, {"market": 0.0}],
            "expected_cost_bps": [15.0, 15.0],
            "realized_cost_bps": [11.0, None],
        }
    )
    block = snapshot.attribution_block(frame)
    assert block["cost"]["expected_bps"] == pytest.approx(15.0)
    assert block["cost"]["realized_bps"] == pytest.approx(11.0)
    assert block["cost"]["n_realized"] == 1, "the null was counted as measured"


def test_an_empty_store_says_so_rather_than_showing_nothing() -> None:
    block = snapshot.attribution_block(pd.DataFrame())
    assert block["n_days"] == 0
    assert block["daily"] == []
    assert block["note"], "an empty block must say why it is empty"
    assert block["cumulative"]["pnl_total"] is None


def test_the_builder_and_the_schema_declare_the_same_block(
    seed_frame: pd.DataFrame,
) -> None:
    """The drift check the page's contract rests on.

    `types.ts` and the fixtures are checked against the schema on the TypeScript
    side; this is the other half, that the writer's own keys are the schema's.
    """
    schema = json.loads(SCHEMA.read_text())
    declared = schema["properties"]["attribution"]
    assert "attribution" in schema["required"]
    block = snapshot.empty_attribution("nothing yet")
    assert set(block) == set(declared["required"])
    assert set(block) == set(declared["properties"])
    cumulative = declared["properties"]["cumulative"]
    assert set(block["cumulative"]) == set(cumulative["required"])
    assert set(block["cost"]) == set(declared["properties"]["cost"]["required"])
    # A real day's keys against the schema's, because the empty block carries no
    # day at all and the day is where the section's lines live.
    day_schema = declared["properties"]["daily"]["items"]
    assert set(day_schema["required"]) <= set(day_schema["properties"])
    real = snapshot.attribution_block(seed_frame)
    assert set(real["daily"][0]) == set(day_schema["properties"])
    assert set(day_schema["required"]) <= set(real["daily"][0])


def test_build_passes_the_block_through_and_says_when_it_was_not_read() -> None:
    """`build` is an assembler: it never recomputes the store's numbers."""
    carried = snapshot.empty_attribution("from the run")
    carried["n_days"] = 3
    payload = snapshot.build(run={"target_close": "2026-09-21", "attribution": carried})
    assert payload["attribution"]["n_days"] == 3
    assert payload["attribution"]["note"] == "from the run"
    # A run that did not read the store says so, rather than showing an empty
    # section that reads as a book that earned nothing.
    bare = snapshot.build(run={"target_close": "2026-09-21"})
    assert bare["attribution"]["n_days"] == 0
    assert bare["attribution"]["note"] == "the run did not read the attribution store"
