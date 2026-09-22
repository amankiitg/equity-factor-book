"""Sprint E10 Part B: the SSGA SPY holdings fetcher.

The fetcher validates the payload by shape, not by the HTTP status code, so
a 200 with an HTML body (as IVV returns) is a failing source. The tests use
stored fixtures and make no network calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from efb import spy

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"

SPY_FIXTURE = FIXTURES / "spy_holdings.xlsx"
IVV_FIXTURE = FIXTURES / "ivv_response.html"


@pytest.fixture(scope="module")
def spy_xlsx() -> bytes:
    if not SPY_FIXTURE.exists():
        pytest.skip("SPY holdings fixture not present", allow_module_level=True)
    return SPY_FIXTURE.read_bytes()


def test_the_spy_parser_returns_503_equity_rows(spy_xlsx: bytes) -> None:
    frame, as_of = spy.parse_spy_xlsx(spy_xlsx)
    equity, dropped = spy._drop_non_equity(frame)
    assert len(equity) == 503
    assert as_of.startswith("18-Sep-2026") or as_of.endswith("2026")
    dropped_ids = {(d["ticker"], d["identifier"], d["reason"]) for d in dropped}
    assert ("-", "999USDZ92", "cash line") in dropped_ids
    assert ("2602335D", "436CVR021", "contingent-value-right line") in dropped_ids


def test_every_equity_row_carries_cusip_and_sedol(spy_xlsx: bytes) -> None:
    frame, _ = spy.parse_spy_xlsx(spy_xlsx)
    equity, _ = spy._drop_non_equity(frame)
    assert equity["identifier"].notna().all()
    assert equity["sedol"].notna().all()
    assert not (equity["identifier"] == "-").any()
    assert not (equity["sedol"] == "-").any()


def test_the_fetcher_rejects_the_ivv_html_payload() -> None:
    # a 200 with an HTML body is a failing source; the parser must say what
    # was wrong rather than return a frame
    html = IVV_FIXTURE.read_bytes()
    assert html.startswith(b"<!DOCTYPE html>")
    with pytest.raises(ValueError, match="not an xlsx zip"):
        spy.parse_spy_xlsx(html)


def test_the_archive_is_append_only(tmp_path: Path) -> None:
    frame, _ = spy.parse_spy_xlsx(SPY_FIXTURE.read_bytes())
    equity, _ = spy._drop_non_equity(frame)
    first = spy.archive_snapshot(equity, "18-Sep-2026", data_root=tmp_path)
    second = spy.archive_snapshot(equity, "18-Sep-2026", data_root=tmp_path)
    assert first == second
    assert first.exists()
    files = list((tmp_path / "raw" / "spy_holdings").glob("*.parquet"))
    assert len(files) == 1


def test_the_cross_check_reports_disagreement() -> None:
    import pandas as pd

    equity = pd.DataFrame(
        {"ticker": ["AAA", "BBB"], "identifier": ["1", "2"], "sedol": ["3", "4"]}
    )
    constituents = pd.DataFrame({"symbol": ["BBB", "CCC"]})
    membership = pd.DataFrame(
        False, index=[pd.Timestamp("2026-01-01")], columns=["AAA", "DDD"]
    )
    membership.loc[pd.Timestamp("2026-01-01"), "AAA"] = True
    table = spy.cross_check(equity, constituents, membership, as_of="2026-09-18")
    names = set(table["ticker"])
    assert "AAA" in names  # SPY and stored, not Wikipedia
    assert "BBB" in names  # SPY and Wikipedia, not stored
    assert "CCC" in names  # Wikipedia only
    assert not table.empty
