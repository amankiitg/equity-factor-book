"""Sprint E4 Task 0: the probes that decide the sprint's shape.

Three probes, each with its own test: the eigenvalue feasibility arithmetic,
the sector-source probe including its EDGAR parser, and the momentum factor's
volatility by exposure tercile. The network probes are tested through a
monkeypatched fetch, so the suite stays offline.
"""

from __future__ import annotations

import numpy as np
import pytest

from efb import probes

TEN = ("CPWR", "EP", "MI", "POM", "ABK", "ABS", "ACAS", "ACE", "AGN", "AKS")

ATOM_FIXTURE = """<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <company-info>
    <assigned-sic>7372</assigned-sic>
    <assigned-sic-desc>SERVICES-PREPACKAGED SOFTWARE</assigned-sic-desc>
  </company-info>
  <entry><content>
    <company-info><cik>0000859014</cik></company-info>
    <filing-href>https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany
      &amp;CIK=0000859014&amp;type=10-K</filing-href>
  </content></entry>
</feed>
"""

SUBMISSIONS_FIXTURE = {
    "sic": "7372",
    "filings": {
        "recent": {
            "form": ["10-K", "8-K", "10-K"],
            "filingDate": ["2014-07-29", "2013-01-15", "2006-06-13"],
        }
    },
}


@pytest.fixture(scope="module")
def feasibility() -> object:
    return probes.eigenvalue_feasibility()


@pytest.fixture(scope="module")
def terciles() -> object:
    return probes.momentum_factor_vol_by_tercile()


@pytest.mark.slow
def test_feasibility_states_n_and_t_for_both_universes(feasibility) -> None:
    frame = feasibility
    assert set(frame["universe"]) == {"model_universe", "panel"}
    assert frame["year"].nunique() == 16, "the probe must cover MODEL_START to 2026"
    model = frame.loc[frame["universe"] == "model_universe"]
    assert model["names_complete_all_year"].min() == 428
    assert model["names_complete_all_year"].max() == 499
    first = model.loc[model["year"] == 2011, "names_complete_all_year"].iloc[0]
    assert first == 428, "the 2011 cross-section is the narrowest by construction"


def test_mp_edge_follows_the_formula_for_the_stored_n_over_t() -> None:
    # the model universe holds a median of 473 names against a 504-day window
    ratio = 473 / 504.0
    edge = (1.0 + np.sqrt(ratio)) ** 2
    assert edge == pytest.approx(3.876, abs=5e-4)
    assert 0.9 < ratio < 1.0, "N is close to T, which is the reason for the lab"


def test_sector_source_probe_reports_the_dated_changes_table(offline_probe) -> None:
    subject = offline_probe
    assert list(subject["ticker"]) == list(TEN)
    assert subject["removed_security"].str.len().gt(0).all()
    assert subject["removal_date"].str.len().gt(0).all()


@pytest.fixture(scope="module")
def offline_probe() -> object:
    return probes.sector_source_probe(offline=True)


def test_edgar_parser_reads_the_sic_the_cik_and_the_filing_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_fetch(url: str, timeout: float = 12.0):
        calls.append(url)
        if "browse-edgar" in url:
            return 200, ATOM_FIXTURE
        return 200, __import__("json").dumps(SUBMISSIONS_FIXTURE)

    monkeypatch.setattr(probes, "_fetch", fake_fetch)
    parsed = probes._sec_company("Compuware")
    assert parsed["status"] == "ok"
    assert parsed["sic"] == "7372"
    assert parsed["sic_desc"] == "SERVICES-PREPACKAGED SOFTWARE"
    assert parsed["cik"] == "0000859014"
    assert parsed["first_10k"] == "2006-06-13"
    assert parsed["last_10k"] == "2014-07-29"
    assert len(calls) == 2, "the submissions file is asked for once"


def test_edgar_parser_reports_a_failed_lookup_rather_than_a_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(probes, "_fetch", lambda url, timeout=12.0: ("HTTPError", ""))
    parsed = probes._sec_company("Nonexistent Issuer")
    assert parsed["status"] == "HTTPError"
    assert "sic" not in parsed


def test_momentum_terciles_reproduce_the_stored_exposure_means(terciles) -> None:
    table = terciles
    assert list(table["bucket"]) == ["low", "mid", "high"]
    assert table["n_months"].tolist() == [47, 47, 47]
    assert table["exposure_mean"].tolist() == pytest.approx(
        table["stored_exposure_mean"].tolist(), abs=1e-9
    )
    assert table["exposure_mean"].tolist() == pytest.approx(
        [0.561474, 0.731709, 0.871312], abs=1e-6
    )


def test_the_momentum_factor_is_not_quieter_in_the_high_exposure_months(
    terciles,
) -> None:
    """Task 3 explanation (ii) predicts the opposite of what the probe finds."""
    forward = terciles["factor_vol_forward_21d"]
    assert (
        forward.iloc[2] > forward.iloc[1] > forward.iloc[0]
    ), "the factor's own realized volatility rises with the book's exposure"
    assert forward.iloc[2] - forward.iloc[0] == pytest.approx(0.008963, abs=1e-5)
    realized = terciles["stored_realized_vol"]
    assert (
        realized.iloc[2] < realized.iloc[0]
    ), "the book's realized volatility falls as its measured exposure rises"
    predicted = terciles["stored_predicted_vol"]
    assert predicted.max() - predicted.min() == pytest.approx(0.003656, abs=1e-5)
