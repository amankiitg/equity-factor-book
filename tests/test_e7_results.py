"""Sprint E7 Task 4 and 7: the stored results file and the RG-Signal gate.

The criteria are re-evaluated from the artifacts on disk, so any drift
between the artifacts and the stored numbers fails here before it can reach
the walkthrough or the signal reports.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb import alpha as alpha_mod
from efb import evaluate

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "sprints" / "E7" / "RESULTS.json"
GATE = ROOT / "sprints" / "E7" / "RG_SIGNAL.json"
LEDGER = ROOT / "docs" / "multiple_testing_ledger.md"
ALPHA = ROOT / "data" / "alpha"

CRITERIA = ["F7.1", "F7.1b", "F7.1c", "F7.2", "F7.3", "F7.4"]

# The criteria whose numbers are read from the signal, the model and the
# ledger. F7.4 is the one that reads the converted alpha, and it is the only
# one: the separation is what the correction to the alpha contract relies on.
CRITERIA_THAT_NEVER_READ_THE_CONVERSION = ["F7.1", "F7.1b", "F7.1c", "F7.2", "F7.3"]


def _results() -> dict:
    if not RESULTS.exists():
        pytest.skip("E7 results not written yet")
    return json.loads(RESULTS.read_text())


@pytest.mark.integration
def test_every_criterion_is_present_with_a_verdict() -> None:
    payload = _results()
    assert set(CRITERIA) <= set(payload["criteria"])
    for name in CRITERIA:
        assert payload["criteria"][name]["verdict"] in ("pass", "fail")
        assert payload["criteria"][name]["stored_numbers"]


@pytest.mark.integration
def test_the_stored_hash_reproduces_from_the_artifacts() -> None:
    payload = _results()
    assert evaluate.e7_data_hash() == payload["data_hash"]


@pytest.mark.integration
def test_the_stored_criteria_equal_the_recomputed_ones() -> None:
    payload = _results()
    fresh = evaluate.evaluate_e7_criteria(**evaluate.compute_e7_from_artifacts())
    for name in CRITERIA:
        assert (
            fresh[name]["stored_numbers"] == payload["criteria"][name]["stored_numbers"]
        ), name
        assert fresh[name]["verdict"] == payload["criteria"][name]["verdict"], name


@pytest.mark.integration
def test_the_criterion_text_is_never_reworded() -> None:
    payload = _results()
    for name in CRITERIA:
        assert payload["criteria"][name]["criterion"] == evaluate.E7_CRITERIA_TEXT[name]


@pytest.mark.integration
def test_the_ledger_row_count_matches_the_runs() -> None:
    payload = _results()
    n_runs = payload["criteria"]["F7.3"]["stored_numbers"]["ledger_rows"]
    lines = [
        line
        for line in LEDGER.read_text().splitlines()
        if line.startswith("| ") and not line.startswith("| run_id")
        # the markdown separator row is not a run: `verdict_by_signal` carried it
        # as one until the parser learned to skip it (H3)
        and not all(set(cell) <= set("-: ") for cell in line.strip("|").split("|"))
    ]
    assert len(lines) == n_runs


@pytest.mark.integration
def test_the_rg_signal_gate_labels_every_signal() -> None:
    if not GATE.exists():
        pytest.skip("the RG-Signal gate has not run yet")
    gate = json.loads(GATE.read_text())
    for name, block in gate.items():
        assert block["verdict"] in ("PASS", "NULL"), name
        assert block["deciding_number"] is not None, name
        assert len(block["answers"]) == 7, name


@pytest.mark.integration
def test_f71b_records_the_empirical_shift_audit() -> None:
    payload = _results()
    f71b = payload["criteria"]["F7.1b"]["stored_numbers"]
    assert payload["criteria"]["F7.1b"]["verdict"] == "fail"
    assert f71b["post_earnings_drift"]["survives"] is True
    assert f71b["post_earnings_drift"]["ic_after_mean"] > (
        f71b["post_earnings_drift"]["ic_before_mean"]
    )
    assert f71b["short_term_reversal"]["flipped"] is True
    assert f71b["low_residual_volatility"]["killed"] is True


def _stored_conversion(name: str) -> pd.DataFrame | None:
    path = ALPHA / name / "alpha.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


@pytest.mark.integration
def test_the_stored_conversion_is_the_contract() -> None:
    """F7.4's numbers come from `alpha_from_contract`, to the digit.

    The stored contract carries its own inputs: the IC, the specific variance
    each model publishes and the z-score. Rebuilding the alpha from them must
    reproduce the stored column exactly, which is the test that fails when a
    site multiplies the variance where the contract multiplies its square
    root. Before the correction this artifact held the variance spelling and
    the stored F7.4 numbers were that spelling's, so the relation below is
    also the record that the refresh reached the artifact rather than only
    the results file.
    """
    names = [str(name) for name in pd.read_parquet(ALPHA / "summary.parquet")["signal"]]
    checked = 0
    for name in names:
        frame = _stored_conversion(name)
        if frame is None:
            continue
        checked += 1
        ic = float(frame["ic"].iloc[0])
        kappa = float(frame["kappa"].iloc[0])
        for column, variance_column in (
            ("alpha", "sigma_idio_xs_v1"),
            ("alpha_xs_v2", "sigma_idio_xs_v2"),
        ):
            expected = alpha_mod.alpha_from_contract(
                ic,
                frame[variance_column].to_numpy(dtype=float),
                frame["z"].to_numpy(dtype=float),
                kappa,
            )
            assert np.allclose(
                frame[column].to_numpy(dtype=float), expected, rtol=1e-12, atol=0.0
            ), f"{name}.{column}"
            # the negative control: the spelling this replaced, which the same
            # inputs would have produced, is a different number for every name
            # whose volatility is not one
            old = (
                ic
                * frame[variance_column].to_numpy(dtype=float)
                * frame["z"].to_numpy(dtype=float)
                * kappa
            )
            assert not np.allclose(frame[column].to_numpy(dtype=float), old), name
    assert checked == len(names)


@pytest.mark.integration
def test_the_conversion_never_reaches_the_other_criteria() -> None:
    """Only F7.4 reads the converted alpha.

    The negative control is multiplying every stored alpha by seven. If the
    IC, the shift audits, the deflated-Sharpe ledger or the neutralized IC
    read the conversion, their stored numbers or their verdicts move; they do
    not, and F7.4 does, which is what let the contract be corrected without
    the RG-Signal answers or the IC results being re-measured.
    """
    inputs = evaluate.compute_e7_from_artifacts()
    assert inputs["alphas"]
    base = evaluate.evaluate_e7_criteria(**inputs)
    scaled = {
        name: frame.assign(
            alpha=frame["alpha"] * 7.0, alpha_xs_v2=frame["alpha_xs_v2"] * 7.0
        )
        for name, frame in inputs["alphas"].items()
    }
    moved = evaluate.evaluate_e7_criteria(**{**inputs, "alphas": scaled})
    for name in CRITERIA_THAT_NEVER_READ_THE_CONVERSION:
        assert moved[name]["stored_numbers"] == base[name]["stored_numbers"], name
        assert moved[name]["verdict"] == base[name]["verdict"], name
    assert moved["F7.4"]["stored_numbers"] != base["F7.4"]["stored_numbers"]


@pytest.mark.integration
def test_the_gate_reads_no_conversion() -> None:
    """The RG-Signal answers are read from the IC and the ledger, not the alpha.

    Every answer in the gate quotes a stored number from the summary, the
    neutral IC or the multiple-testing ledger. The conversion is not one of
    its inputs, so the gate file is the same file after the alpha contract was
    corrected, and the last line here is what keeps it that way.
    """
    source = inspect.getsource(evaluate.write_rg_signal_gate)
    for forbidden in ("alpha_from_contract", "alpha.parquet", "alpha_xs_v2"):
        assert forbidden not in source, forbidden


@pytest.mark.integration
def test_a_revision_records_both_hashes_and_both_values() -> None:
    """A moved number is stored beside the number it replaced.

    The revisions block is the record of a correction: one history entry per
    data hash, each carrying the hash it moved from, and, per criterion, the
    old measurement beside the new one. A correction that rewrote the file
    with only the new numbers would leave no evidence that anything moved.
    The entries written before the writer recorded the hash it moved from
    carry a null there, which is what marks them as older rather than as a
    correction with no origin.
    """
    payload = _results()
    revisions = payload["revisions"]
    assert revisions["data_hash"] == payload["data_hash"]
    history = revisions.get("history") or []
    assert history
    assert history[-1]["data_hash"] == payload["data_hash"]
    for older, newer in zip(history, history[1:], strict=False):
        previous = newer["previous_data_hash"]
        if previous is not None:
            assert previous == older["data_hash"]
    # the correction this branch carries: the alpha contract moved F7.4, and
    # the entry says which hash it moved from
    last = history[-1]
    assert len(history) > 1
    assert last["previous_data_hash"] == history[-2]["data_hash"]
    assert last["previous_data_hash"] != last["data_hash"]
    assert last["data_hash"] == revisions["data_hash"]
    moved = [name for name, block in last["changed"].items() if block["changed"]]
    assert moved, "the entry this branch wrote has to record what moved"
    for name in moved:
        block = last["changed"][name]
        assert block["old"] is not None, name
        assert (
            block["old"]["stored_numbers"] != block["new"]["stored_numbers"]
            or block["old"]["verdict"] != block["new"]["verdict"]
            or block["old"]["criterion"] != block["new"]["criterion"]
        ), f"{name} is marked changed with nothing changed"
    # and the file's own summary of that entry agrees with it
    assert revisions["previous_data_hash"] == last["previous_data_hash"]
    assert revisions["changed_tickers_or_criteria"] == sorted(moved)
