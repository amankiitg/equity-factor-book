"""The page's sector map is generated, and here is what generated means.

The page groups a book by GICS sector from a JSON file bundled into its build,
because the snapshot carries no sector per name. That file is the one piece of the
page that could have been typed by hand, and a typed sector map is the worst kind
of wrong: it looks right for months.

So the map is regenerated here from `data/processed/sectors.parquet` and the dated
`data/raw/spy_holdings/` archive, and compared with the committed bytes. The other
tests pin the two properties the page leans on: every code is a sector the model
estimates, and every ticker the map does not carry is one the stored files do not
know, rather than one the generator dropped.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from efb.models.fundamental import SECTOR_CODES
from scripts import make_sector_map as generated

ROOT = Path(__file__).resolve().parents[1]
OK_FIXTURE = ROOT / "web" / "fixtures" / "snapshot_ok.json"


def committed() -> dict[str, object]:
    return json.loads(generated.TARGET.read_text())


@pytest.mark.integration
def test_the_committed_map_is_exactly_what_the_generator_produces() -> None:
    sectors = pd.read_parquet(generated.SECTORS_PATH)
    holdings = pd.read_parquet(generated.latest_holdings())
    assert committed() == generated.bundle(generated.build_map(sectors, holdings))


@pytest.mark.integration
def test_the_bundle_carries_the_map_and_not_the_diagnosis() -> None:
    # The page imports this file into its build, so what is in it is what the
    # browser downloads. The unmapped list is a few hundred names describing
    # names that are absent, and the page reads their absence rather than a list.
    assert set(committed()) == {"source", "sectors", "tickers"}


@pytest.mark.integration
def test_every_code_is_a_sector_the_model_estimates() -> None:
    document = committed()
    assert document["sectors"] == {
        str(code): name for name, code in SECTOR_CODES.items()
    }
    assert set(document["tickers"].values()) <= set(SECTOR_CODES.values())
    assert set(document["tickers"]).isdisjoint({"", "UNMAPPED"})


@pytest.mark.integration
def test_the_map_names_the_files_it_came_from_and_their_own_dates() -> None:
    document = committed()
    source = document["source"]
    assert source["sectors"] == "data/processed/sectors.parquet"
    assert source["holdings"].startswith("data/raw/spy_holdings/spy_holdings_")
    sectors = pd.read_parquet(generated.SECTORS_PATH)
    holdings = pd.read_parquet(generated.latest_holdings())
    assert source["sectors_as_of"] == str(sectors["as_of"].iloc[0])[:10]
    assert source["holdings_as_of"] == str(holdings["as_of"].iloc[0])[:10]


@pytest.mark.integration
def test_an_unmapped_ticker_is_one_the_stored_files_do_not_know() -> None:
    # The page renders a name with no sector as Unmapped. That reading is only
    # honest if the map's gaps are the sources' gaps: every ticker it carries is
    # one the sector file names with a code the model estimates, and every ticker
    # it leaves out is one the sources cannot code.
    sectors = pd.read_parquet(generated.SECTORS_PATH)
    holdings = pd.read_parquet(generated.latest_holdings())
    document = generated.build_map(sectors, holdings)
    modelable = {
        str(row["ticker"]).strip().upper(): row["gics_sector"].strip()
        for _, row in sectors.iterrows()
        if row["gics_sector"].strip() in SECTOR_CODES
    }
    assert set(document["tickers"]) == set(modelable)
    universe = {str(ticker).strip().upper() for ticker in holdings["ticker"].dropna()}
    assert set(document["unmapped_universe"]) >= universe - set(modelable)
    assert set(document["unmapped_universe"]).isdisjoint(modelable)


@pytest.mark.integration
def test_every_name_in_the_live_book_maps_unless_the_sources_lack_it() -> None:
    # The book is the index's own current members, so nearly all of it maps. The
    # equality is the check; the count below only says how much of the page's
    # sector section is filled in, and is deliberately not a threshold that fails
    # when a vendor changes a table.
    document = committed()
    book = json.loads(OK_FIXTURE.read_text())["book"]["names"]
    tickers = [str(name["ticker"]).strip().upper() for name in book]
    sectors = pd.read_parquet(generated.SECTORS_PATH)
    named = {
        str(row["ticker"]).strip().upper()
        for _, row in sectors.iterrows()
        if row["gics_sector"].strip() in SECTOR_CODES
    }
    assert [ticker for ticker in tickers if ticker in document["tickers"]] == [
        ticker for ticker in tickers if ticker in named
    ]
