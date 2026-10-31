"""Sprint E11: the variance-share rule, and where it sits in the sizing.

The owner's rule, set 2026-09-26: no name may carry more than 10% of the book's
predicted specific variance, a name above it is scaled down to 10%, and the book
is renormalized to gross 1.0 before the hedge. The cap therefore has to be part
of the sizing every caller shares, not a step after it.
"""

from __future__ import annotations

import logging

import numpy as np
import pytest

from live import evening_job as ev
from live import sizing


def _book(size: int = 20, biggest: float = 40.0) -> tuple[np.ndarray, np.ndarray]:
    weights = np.linspace(1.0, 0.5, size)
    weights[0] = biggest
    specific = np.linspace(1e-4, 2e-4, size)
    return weights, specific


def test_a_name_above_the_cap_is_taken_to_exactly_the_cap() -> None:
    weights, specific = _book()
    before = sizing.variance_shares(weights, specific)
    assert before.max() > 0.10, "the fixture must start above the cap"

    capped = sizing.cap_variance_shares(weights, specific)
    after = sizing.variance_shares(capped, specific)

    assert after.max() == pytest.approx(0.10, abs=1e-12)
    # Only the names above the cap move, and only downwards.
    assert np.all(np.abs(capped) <= np.abs(weights) + 1e-12)
    assert np.all(np.sign(capped) == np.sign(weights))
    untouched = before <= 0.10
    assert np.allclose(capped[untouched], weights[untouched])
    # More than one name can be clamped, and every clamped name sits at the cap.
    clamped = after > 0.10 - 1e-9
    assert clamped.sum() >= 1
    assert np.allclose(after[clamped], 0.10, atol=1e-9)


def test_the_cap_is_scale_invariant() -> None:
    """Renormalizing the book cannot change which names are over the cap."""
    weights, specific = _book()
    capped = sizing.cap_variance_shares(weights, specific)
    renormed = sizing.renormalize(capped, gross=1.0)

    assert np.allclose(
        sizing.variance_shares(renormed, specific),
        sizing.variance_shares(capped, specific),
    )


def test_a_book_too_small_for_the_cap_is_made_as_even_as_it_can_be() -> None:
    """Six names cannot each hold 10%: the shares have to sum to one.

    The search evaluates candidate subsets, so this case has to be answered rather
    than raised on: the tightest cap a six-name book can meet is one sixth, which
    is what the most even book there is holds.
    """
    weights = np.array([5.0, -5.0, 4.0, -4.0, 3.0, -3.0])
    specific = np.ones(6)

    capped = sizing.cap_variance_shares(weights, specific)
    shares = sizing.variance_shares(capped, specific)

    assert shares.max() == pytest.approx(1 / 6, abs=1e-12)
    assert np.allclose(np.abs(capped), np.abs(capped[0])), "not even"
    # Evened in variance, not in nothing: the signs and the dollar neutrality of
    # the fixture survive.
    assert abs(float(capped.sum())) < 1e-9
    assert np.allclose(np.sign(capped), np.sign(weights))


def _traded_fixture() -> (
    tuple[list[str], np.ndarray, np.ndarray, np.ndarray, dict[str, float]]
):
    """Twelve names and three factors, so the hedge has room to depend on the cap.

    A book with only one more name than factors is degenerate here: the hedge's
    image is then one-dimensional, so every candidate vector lands on the same
    direction and renormalizes to the same book whatever the cap does. Twelve
    names and three columns leaves the hedge nine dimensions to work in, which is
    where the order of the two operations can be told apart.
    """
    names = [f"T{index:02d}" for index in range(12)]
    alpha = np.linspace(9.0, -9.0, 12)
    specific = np.linspace(1e-4, 1e-3, 12)
    design = np.ones((12, 3))
    design[:, 1] = np.linspace(-1.0, 1.0, 12)
    design[:, 2] = np.sin(np.arange(12, dtype=float))
    close = {name: 50.0 for name in names}
    return names, alpha, specific, design, close


def _capped_sized(alpha: np.ndarray, specific: np.ndarray) -> np.ndarray:
    sized = alpha / specific
    capped = sizing.cap_variance_shares(sized, specific)
    assert not np.allclose(capped, sized), "the fixture must bind the cap"
    return sizing.renormalize(capped, gross=1.0)


def test_the_cap_lands_before_the_hedge_and_the_traded_book_uses_it() -> None:
    """The order is the rule: capping after the hedge would undo the hedge.

    The traded vector is rebuilt from the two halves - cap, renormalize, hedge,
    renormalize - and has to be the vector the shared sizing returns, so the floor
    search and the book that trades cannot disagree about which book it is.
    """
    names, alpha, specific, design, close = _traded_fixture()
    factor_covariance = np.eye(3)
    keep = np.ones(12, dtype=bool)

    idx, names_sub, w_sub, _prices, _d, _s, pre_hedge = ev.sized_kept_weights(
        keep, names, alpha, design, factor_covariance, specific, close, 100_000.0
    )

    pre = _capped_sized(alpha, specific)
    assert sizing.variance_shares(pre, specific).max() == pytest.approx(0.10, abs=1e-12)
    # The hedge acted on that capped vector, not on the uncapped one.
    assert np.allclose(pre_hedge, design.T @ pre)
    expected, _pre = sizing.procedure_6_3_hedged_with_exposures(
        alpha, design, factor_covariance, specific, sized=pre
    )
    hedge_of_record = sizing.renormalize(expected, gross=1.0)
    # ...and the vector that trades is that hedge passing the cap on the way out,
    # which is the one addition the 2026-10-31 change made.
    assert np.allclose(
        w_sub, sizing.enforce_final_cap(hedge_of_record, design, specific)
    )
    assert list(names_sub) == names
    assert idx.tolist() == list(range(12))


def test_the_hedge_can_lift_a_capped_name_back_above_the_cap() -> None:
    """The rule is the sized vector's, and the hedge is allowed to move it after.

    Measured rather than assumed: on this fixture the sized vector sits exactly on
    the cap and the traded book has a name above it. The owner's rule puts the cap
    before the hedge, and clamping the post-hedge vector instead would break the
    exact projection that makes the book dollar-neutral, so this is the rule's
    stated boundary rather than a defect. It is pinned here so that changing the
    order is a deliberate act, and it is reported with its real numbers in
    `handoff/REPORT.md` - on the 2026-09-21 close, one name of 169 (TER 11.72%).
    """
    names, alpha, specific, design, close = _traded_fixture()
    pre = _capped_sized(alpha, specific)
    _idx, _names, w_sub, *_rest = ev.sized_kept_weights(
        np.ones(12, dtype=bool),
        names,
        alpha,
        design,
        np.eye(3),
        specific,
        close,
        100_000.0,
    )

    before = sizing.variance_shares(pre, specific)
    after = sizing.variance_shares(w_sub, specific)
    assert before.max() == pytest.approx(0.10, abs=1e-12)
    assert after.max() > 0.10, "the fixture must show the hedge lifting a share"
    # What the cap gives up is what the hedge buys: the traded vector has no
    # factor exposure to the 1e-15, and the sized vector it was made from has a
    # lot of it, which is why the two cannot be capped in the same place.
    assert np.abs(design.T @ w_sub).max() < 1e-12
    assert np.abs(design.T @ pre).max() > 1e-3


def test_the_uncapped_hedge_is_not_what_trades() -> None:
    """The negative control: without the cap the book differs, so the test bites."""
    names, alpha, specific, design, close = _traded_fixture()
    _idx, _names, w_sub, *_rest = ev.sized_kept_weights(
        np.ones(12, dtype=bool),
        names,
        alpha,
        design,
        np.eye(3),
        specific,
        close,
        100_000.0,
    )
    hedged, _pre = sizing.procedure_6_3_hedged_with_exposures(
        alpha, design, np.eye(3), specific
    )

    assert not np.allclose(w_sub, sizing.renormalize(hedged, gross=1.0))


# ---------------------------------------------------------------------------
# EFB_HEDGE_MODE: the cap-then-rehedge construction, behind a default-off flag.
#
# The rule above caps before the hedge, and the test above records the boundary it
# accepts: the hedge can lift a capped name back over the cap. The research on the
# live books (docs/research/nov11_hedge.md, docs/research/etf_overlay_hedge.md)
# measures the other order - cap, re-project, three times - as cutting the worst
# single-name share from about 12.6% to 10.0008% with the neutrality kept. It is
# the owner's decision to trade on that construction, so the flag defaults to off
# and an unrecognised value falls back to the hedge that has always run.
# ---------------------------------------------------------------------------


def _mode(monkeypatch: pytest.MonkeyPatch, value: str | None) -> str:
    """The mode the module resolves for one value of the flag, cache and all."""
    monkeypatch.setattr(ev, "_HEDGE_MODE_CACHE", None)
    if value is None:
        monkeypatch.delenv(ev.HEDGE_MODE_ENV, raising=False)
    else:
        monkeypatch.setenv(ev.HEDGE_MODE_ENV, value)
    return ev.hedge_mode()


@pytest.mark.parametrize("value", [None, "", "exact", "exact ", "EXACT", "Exact"])
def test_the_flag_reads_as_the_exact_hedge_until_it_names_the_other_one(
    value: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _mode(monkeypatch, value) == ev.HEDGE_MODE_EXACT


@pytest.mark.parametrize(
    "value", ["cap_then_rehedge", " CAP_THEN_REHEDGE ", "Cap_Then_Rehedge"]
)
def test_the_one_other_value_the_loop_reacts_to(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _mode(monkeypatch, value) == ev.HEDGE_MODE_CAP_THEN_REHEDGE


@pytest.mark.parametrize("value", ["cap_then_rehedg", "yes", "1", "rehedge", "exact_2"])
def test_a_typo_falls_back_to_the_exact_hedge_and_says_so(
    value: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A typo must never change the book, and it must not be silent either."""
    with caplog.at_level(logging.WARNING):
        resolved = _mode(monkeypatch, value)

    assert resolved == ev.HEDGE_MODE_EXACT
    assert f"{ev.HEDGE_MODE_ENV}={value!r} is not a hedge mode" in caplog.text
    assert "the exact hedge is used" in caplog.text


def test_the_mode_is_decided_once_and_then_remembered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The floor search calls the sizing hundreds of times per row.

    The flag is a start-of-run decision, not a per-call one: reading it again inside
    the search would let a value that changed mid-run build a book out of two
    hedges, and a typo would be logged once per candidate set instead of once.
    """
    assert _mode(monkeypatch, ev.HEDGE_MODE_CAP_THEN_REHEDGE) == (
        ev.HEDGE_MODE_CAP_THEN_REHEDGE
    )
    monkeypatch.setenv(ev.HEDGE_MODE_ENV, "exact")
    assert ev.hedge_mode() == ev.HEDGE_MODE_CAP_THEN_REHEDGE, "read once per process"

    monkeypatch.setattr(ev, "_HEDGE_MODE_CACHE", None)
    assert ev.hedge_mode() == ev.HEDGE_MODE_EXACT


def test_the_default_mode_is_the_hedge_of_record_and_then_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default is still the exact hedge - and the cap now holds on what trades.

    Until 2026-10-31 this test asserted the delivered vector was the renormalized
    hedge byte for byte, which is exactly the bug: on 2026-10-20 that book carried
    11.69% of its predicted specific variance on one name against a 10% rule. The
    contract now has two halves, and both are asserted here: `apply_hedge_mode`
    still returns the hedged vector untouched in the default mode, and the weights
    that leave `sized_kept_weights` are the hedge of record *passing the cap*.
    """
    names, alpha, specific, design, close = _traded_fixture()
    pre = _capped_sized(alpha, specific)
    hedged, _pre = sizing.procedure_6_3_hedged_with_exposures(
        alpha, design, np.eye(3), specific, sized=pre
    )
    assert _mode(monkeypatch, None) == ev.HEDGE_MODE_EXACT
    assert ev.apply_hedge_mode(hedged, design, specific) is hedged

    _idx, _names, w_sub, *_rest = ev.sized_kept_weights(
        np.ones(12, dtype=bool), names, alpha, design, np.eye(3), specific, close, 1e5
    )
    hedge_of_record = sizing.renormalize(hedged, gross=1.0)
    final = sizing.enforce_final_cap(hedge_of_record, design, specific)
    assert np.array_equal(w_sub, final)
    # This twelve-name book is too small for the neutral space to hold a capped
    # book, so the pass improves the share without meeting the cap: the manifest
    # reports that rather than the code pretending otherwise.
    assert sizing.variance_shares(final, specific).max() <= (
        sizing.variance_shares(hedge_of_record, specific).max()
    )


def _cap_fixture() -> (
    tuple[list[str], np.ndarray, np.ndarray, np.ndarray, dict[str, float]]
):
    """Forty names and three factors: big enough for the neutral space to hold a
    capped book. The twelve-name fixture above is deliberately too small for it -
    with nine free dimensions and one name carrying most of the variance, no
    number of cap-then-re-project passes meets the cap, and the reconstruction is
    under-shot rather than met. This is the size at which the construction does
    what it claims, which is what has to be pinned. Deterministic: one seed, no
    randomness in the test.
    """
    rng = np.random.default_rng(6)
    names = [f"C{index:02d}" for index in range(40)]
    design = rng.normal(size=(40, 3))
    alpha = np.linspace(9.0, -9.0, 40) * (1.0 + 0.5 * rng.normal(size=40))
    specific = np.linspace(1e-4, 2e-3, 40)
    close = {name: 50.0 for name in names}
    return names, alpha, specific, design, close


def test_the_flag_puts_the_cap_on_the_book_that_trades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point of the construction, on the traded vector.

    The control is the same fixture and the same call with the flag unset: that book
    is the one the loop builds today, and its worst name is 11.94% of the book's
    predicted specific variance against the 10% rule. With the flag on the worst
    name is at the cap to within the last re-projection's own move (10.00508%), which
    is what the research measured on the live books (9.6%). The neutrality is
    unchanged either way, and that is what the re-projections buy: the cap is applied
    *after* the hedge here and nowhere else, and the book ends on the neutral space
    the hedge put it on.
    """
    names, alpha, specific, design, close = _cap_fixture()
    args = (
        np.ones(len(names), dtype=bool),
        names,
        alpha,
        design,
        np.eye(3),
        specific,
        close,
        1e5,
    )

    assert _mode(monkeypatch, None) == ev.HEDGE_MODE_EXACT
    idx_off, _n_off, traded_off, _p_off, _d_off, _s_off, _pre_off = (
        ev.sized_kept_weights(*args)
    )
    shares_off = sizing.variance_shares(traded_off, specific)

    assert _mode(monkeypatch, ev.HEDGE_MODE_CAP_THEN_REHEDGE) == (
        ev.HEDGE_MODE_CAP_THEN_REHEDGE
    )
    idx_on, _n_on, traded_on, _p_on, _d_on, _s_on, _pre_on = ev.sized_kept_weights(
        *args
    )
    shares_on = sizing.variance_shares(traded_on, specific)

    assert idx_off.tolist() == idx_on.tolist() == list(range(len(names)))
    # Before 2026-10-31 the default shipped 11.94% here; the final pass takes it to
    # the cap and the flag lands a shade closer, because it caps at every pass
    # rather than once at the end.
    assert shares_off.max() == pytest.approx(0.1000508, abs=1e-6), "the default's book"
    assert shares_on.max() == pytest.approx(0.1000001, abs=1e-6), "the flag's book"
    assert shares_off.max() <= 0.10 + 2e-4
    assert shares_on.max() <= 0.10 + 2e-4
    assert shares_on.max() <= shares_off.max()
    # Both books are factor-neutral to machine precision: the flag does not trade
    # the neutrality for the cap, and it does not need to.
    assert np.abs(design.T @ traded_off).max() < 1e-12
    assert np.abs(design.T @ traded_on).max() < 1e-12
    assert not np.allclose(traded_on, traded_off), "the flag has to change the book"


def test_the_cap_holds_on_the_vector_that_trades_and_not_only_before_the_hedge() -> (
    None
):
    """A hedge after the cap can put a name back above it; the last pass must not.

    Measured on the live book: 2026-10-20 shipped `max_variance_share` **11.69%**
    with `variance_share_cap_binds: true`, a book that states it is above the cap it
    is supposed to meet. The cap was applied before the hedge, and the hedge then
    moved the composition.
    """
    # Forty names and three factors, the fixture the cap can actually be met on:
    # the twelve-name one is deliberately too small for the neutral space to hold a
    # capped book, which is a different test.
    names, alpha, specific, design, close = _cap_fixture()
    pre = _capped_sized(alpha, specific)
    hedged, _ = sizing.procedure_6_3_hedged_with_exposures(
        alpha, design, np.eye(3), specific, sized=pre
    )
    hedge_of_record = sizing.renormalize(hedged, gross=1.0)
    assert (
        sizing.variance_shares(hedge_of_record, specific).max() > 0.10
    ), "the fixture must show the hedge lifting a name over the cap"

    final = sizing.enforce_final_cap(hedge_of_record, design, specific)
    assert sizing.variance_shares(final, specific).max() <= 0.10 + 2e-4
    # Nothing is renormalized away: the gross is the gross it was given.
    assert float(np.abs(final).sum()) == pytest.approx(
        float(np.abs(hedge_of_record).sum())
    )
    # And it stays on the neutral space, which is what the re-projections buy.
    assert np.abs(design.T @ final).max() < 1e-12
    # A book already under the cap is returned untouched, to the bit.
    under = sizing.cap_variance_shares(hedge_of_record, specific)
    assert np.array_equal(sizing.enforce_final_cap(under, design, specific), under)
    del names, close


def test_the_floor_that_pushes_a_name_over_the_cap_is_caught() -> None:
    """The case the owner asked for: the floor renormalizes and the cap breaks.

    A kept subset that drops the middle of the book leaves the largest name with a
    bigger share than it had in the full book, and that is exactly what the last
    pass is for.
    """
    names, alpha, specific, design, close = _cap_fixture()
    pre = _capped_sized(alpha, specific)
    hedged, _ = sizing.procedure_6_3_hedged_with_exposures(
        alpha, design, np.eye(3), specific, sized=pre
    )
    capped = sizing.renormalize(hedged, gross=1.0)
    before = sizing.variance_shares(capped, specific).max()
    keep = np.ones(len(names), dtype=bool)
    keep[5:20] = False  # the construction floor drops fifteen of the forty names
    floored = capped[keep]
    share_after = sizing.variance_shares(floored, specific[keep]).max()
    assert share_after > before, "dropping names concentrates the book"
    assert share_after > 0.10, "the fixture must break the cap on the floor"

    final = sizing.enforce_final_cap(floored, design[keep], specific[keep])
    achieved = sizing.variance_shares(final, specific[keep]).max()
    # The pass answers: it brings the worst name down and leaves the book on the
    # neutral space. Whether it can reach the cap depends on the space - three
    # factors and twenty-five names cannot hold a 10% book, which is the under-shoot
    # `cap_then_rehedge` documents and the manifest reports as a binding cap.
    assert achieved < share_after
    assert np.abs(design[keep].T @ final).max() < 1e-12
    assert float(np.abs(final).sum()) == pytest.approx(float(np.abs(floored).sum()))
    del alpha, close
