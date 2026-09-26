"""Sprint E11 Part B: Render, Supabase, Alpaca and the live dashboard."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from live import alpaca, store, trade_reasons

ROOT = Path(__file__).resolve().parents[1]


def test_alpaca_dry_run_connect_returns_none() -> None:
    assert alpaca.connect(dry_run=True) is None


def test_alpaca_live_connect_names_the_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if importlib.util.find_spec("alpaca") is not None:
        pytest.skip("alpaca-py is installed")
    monkeypatch.setenv("EFB_ALPACA_PAPER_API_KEY", "k")
    monkeypatch.setenv("EFB_ALPACA_PAPER_SECRET_KEY", "s")
    with pytest.raises(RuntimeError, match="alpaca-py"):
        alpaca.connect(dry_run=False)


def test_store_unknown_table_raises() -> None:
    with pytest.raises(ValueError, match="unknown live-series table"):
        store.upsert("not_a_table", [{"a": 1}])


def test_store_local_fallback_is_disjoint_from_state_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EFB_SUPABASE_DB_URL", raising=False)
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path)
    store.upsert(
        "nav", [{"trade_date": "2026-09-22", "nav": 100000.0, "realized_pnl": 0.0}]
    )
    frame = store.select("nav")
    assert len(frame) == 1
    assert float(frame["nav"].iloc[0]) == 100000.0
    assert (tmp_path / "nav.parquet").exists()


def test_store_is_supabase_false_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EFB_SUPABASE_DB_URL", raising=False)
    assert store.is_supabase() is False


def test_trade_reasons_classify_each_bucket() -> None:
    today = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D"],
            "weight": [0.02, 0.02, 0.02, 0.01],
            "z": [1.5, 1.0, 1.0, 1.0],
        }
    )
    previous = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D"],
            "weight": [0.01, 0.01, 0.01, 0.01],
            "z": [1.0, 1.0, 1.0, 1.0],
        }
    )
    today_specific = pd.Series({"A": 0.3, "B": 0.5, "C": 0.3, "D": 0.3})
    previous_specific = pd.Series({"A": 0.3, "B": 0.3, "C": 0.3, "D": 0.3})
    reasons = trade_reasons.assign_trade_reasons(
        today, previous, today_specific, previous_specific
    ).set_index("ticker")["reason"]
    assert reasons["A"] == "alpha moved"
    assert reasons["B"] == "risk moved"
    assert reasons["C"] == "the hedge moved"
    assert reasons["D"] == "no trade"


def test_trade_reasons_new_name_is_alpha() -> None:
    today = pd.DataFrame({"ticker": ["X"], "weight": [0.03], "z": [0.9]})
    reasons = trade_reasons.assign_trade_reasons(
        today, None, pd.Series(dtype=float), None
    )
    assert reasons["reason"].iloc[0] == "alpha moved"


def test_render_dashboard_reads_no_research_parquet() -> None:
    """The Render app reads the live series and two tiny files, never a
    research parquet, so acceptance 7 holds by construction."""
    source = (ROOT / "live" / "dashboard_app.py").read_text()
    assert "read_parquet" not in source
    assert "data/" not in source


def test_render_dashboard_labels_the_construction_from_the_artifact() -> None:
    """The Render page's construction label is generated from the proposal's
    stored fields, never asserted beside the artifact."""
    from live import dashboard_app

    assert (
        dashboard_app._construction_label(
            {
                "construction": "share_only",
                "construction_floor_dollars": None,
                "construction_floor_shares": 20,
                "construction_top_n": None,
                "floor_iterated": True,
            }
        )
        == "min 20 shares (iterated to a fixed point)"
    )
    assert (
        dashboard_app._construction_label(
            {"construction": "min_position", "construction_floor_dollars": 5000.0}
        )
        == "min position $5,000 (one pass, not iterated)"
    )


def test_render_dashboard_reports_missing_construction_fields() -> None:
    from live import dashboard_app

    assert dashboard_app._construction_label({}) == (
        "construction parameters not recorded in this artifact"
    )


def test_the_regenerated_proposal_is_the_share_only_book() -> None:
    """Part 6 regenerated it under share-only; Part 5 regenerated it again on
    the 150-name drop-then-admit book. Both the D10 header and the Render page
    label it from its own fields."""
    import json

    from live import dashboard_app

    manifest = json.loads(
        (ROOT / "live" / "proposals" / "proposal_2026-09-21.json").read_text()
    )
    assert manifest["construction"] == "share_only"
    assert manifest["construction_floor_shares"] == 20
    assert manifest["construction_floor_dollars"] is None
    assert manifest["floor_iterated"] is True
    assert manifest["floor_rule"] == "drop_then_admit"
    assert manifest["n_kept"] == 150
    assert manifest["n_dropped"] == 349
    assert dashboard_app._construction_label(manifest) == (
        "min 20 shares (iterated to a fixed point)"
    )


def test_whole_share_quantization_counts_zero_rounds() -> None:
    rows = pd.DataFrame({"ticker": ["A", "B"], "weight": [0.000001, -0.000001]})
    prices = {"A": 100.0, "B": 100.0}
    nav = 1_000_000.0
    # each target notional is 1 dollar, one whole share costs 100, so both
    # round to zero shares, one long and one short
    result = alpaca.whole_share_quantization(rows, prices, nav)
    assert result["long_targets_rounding_to_zero"] == 1
    assert result["short_targets_rounding_to_zero"] == 1
    assert result["gross_weight_error"] > 0


def test_require_empty_account_rejects_existing_positions() -> None:
    class Account:
        id = "acct-efb"

    class Client:
        def get_account(self):
            return Account()

        def get_all_positions(self):
            return [object()]

    with pytest.raises(RuntimeError, match="refusing to trade"):
        alpaca.require_empty_account(Client())


def test_env_example_names_the_keys_without_values() -> None:
    text = (ROOT / ".env.example").read_text()
    lines = text.splitlines()
    # two keys carry safe non-secret defaults; every other key is empty
    defaults = {"EFB_DB_SCHEMA": "efb", "EFB_DRY_RUN": "true", "EFB_STORE": "local"}
    for name in (
        "EFB_ALPACA_PAPER_API_KEY",
        "EFB_ALPACA_PAPER_SECRET_KEY",
        "EFB_SUPABASE_DB_URL",
        "EFB_DB_SCHEMA",
        "EFB_SUPABASE_PROJECT_URL",
        "EFB_SUPABASE_ACCESS_TOKEN",
        "EFB_DRY_RUN",
        "EFB_STORE",
        "EFB_RESEND_API_KEY",
        "EFB_NOTIFY_EMAIL_FROM",
        "EFB_NOTIFY_EMAIL_TO",
    ):
        match = [line for line in lines if line.startswith(name)]
        assert match, f"{name} missing from .env.example"
        expected = f"{name}={defaults.get(name, '')}"
        assert (
            match[0] == expected
        ), "the example carries only safe defaults, never a secret"


def test_render_yaml_commits_key_names_not_values() -> None:
    render = (ROOT / "render.yaml").read_text()
    assert "EFB_ALPACA_PAPER_API_KEY" in render
    assert "EFB_ALPACA_PAPER_SECRET_KEY" in render
    # direct Postgres, never PostgREST
    assert "EFB_SUPABASE_DB_URL" in render
    assert "EFB_DB_SCHEMA" in render
    # the account-wide access token must never reach a Render service
    assert "EFB_SUPABASE_ACCESS_TOKEN" not in render
    assert "EFB_SUPABASE_SECRET_KEY" not in render
    assert "sync: false" in render
    assert "AKIA" not in render
    assert "-----BEGIN" not in render


def test_render_yaml_runs_one_service_and_it_holds_the_credentials() -> None:
    """One cron. No web service, so no read role and one fewer box to fall over."""
    render = (ROOT / "render.yaml").read_text()
    assert "- type: web" not in render
    assert "efb-live-dashboard" not in render
    assert render.count("- type: cron") == 1
    _, cron = render.split("- type: cron")
    for name in (
        "EFB_RESEND_API_KEY",
        "EFB_NOTIFY_EMAIL_FROM",
        "EFB_NOTIFY_EMAIL_TO",
        "EFB_SNAPSHOT",
        "EFB_R2_ACCOUNT_ID",
        "EFB_R2_BUCKET",
        "EFB_R2_ACCESS_KEY_ID",
        "EFB_R2_SECRET_ACCESS_KEY",
    ):
        assert name in cron, f"{name} missing from the cron service"
    # names only: no key material, no address, no endpoint prose
    assert "re_" not in render
    assert "@" not in render
    # and the channel the code no longer has is gone from the blueprint
    assert "SLACK" not in render
    assert "EFB_NOTIFY_SLACK_WEBHOOK_URL" not in render


def test_the_cron_is_created_on_the_four_gigabyte_plan() -> None:
    """Without `plan`, Render creates a cron on 0.5c-512mb and the peak kills it.

    The measured peak is 1.07 GiB, so the plan has to be at least 4 GB to keep the
    2x headroom rule. From Render's Blueprint reference, the `plan` field's Cron
    Job table: `2c-4g` is 2 CPU and 4 GB, and the same page says an omitted field
    gives a new cron job `0.5c-512mb`.
    """
    render = (ROOT / "render.yaml").read_text()
    _, cron = render.split("- type: cron")
    assert "plan: 2c-4g" in cron
    assert "plan: 0.5c-512mb" not in render
    assert "plan: 1c-2g" not in render
