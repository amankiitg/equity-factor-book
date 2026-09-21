"""Sprint E10 Task 8: write the risk policy memo from the artifacts.

Every number is read from the artifacts or the stored results, never typed
by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RESULTS = ROOT / "sprints" / "E10" / "RESULTS.json"


def main() -> None:
    results = json.loads(RESULTS.read_text())
    config = json.loads((DATA / "allocation" / "config.json").read_text())
    kelly = pd.read_parquet(DATA / "allocation" / "kelly.parquet").iloc[0]
    drawdown = pd.read_parquet(DATA / "allocation" / "drawdown.parquet").iloc[0]
    voltarget = pd.read_parquet(DATA / "allocation" / "voltarget.parquet").iloc[0]
    stoploss = pd.read_parquet(DATA / "allocation" / "stoploss.parquet")
    regime = pd.read_parquet(DATA / "allocation" / "regime.parquet")
    verdicts = results["criteria"]

    stoploss_lines = "\n".join(
        f"| {row['book']} | {row['base_sharpe']:.3f} | "
        f"{row['real_book_sharpe_diff']:.3f} |"
        for row in stoploss.to_dict(orient="records")
    )
    regime_lines = "\n".join(
        f"| {row['vix_tercile']} | {row['mean_vix']:.2f} | "
        f"{row['max_drawdown']:.3f} | {row['n_underwater']} |"
        for row in regime.to_dict(orient="records")
    )

    text = f"""# E10 Risk Allocation and Drawdown Policy

The input is the synthetic book's net returns on corrected costs, at the
(rho, phi) configuration whose net annualized Sharpe is closest to 1.0,
scaled to the 10% volatility target, with the two seed books run
alongside. The synthetic label travels with every number.

The design book is rho {config['rho']}, phi {config['phi']}, seed
{int(config['seed'])}, with a net annualized Sharpe of
{config['net_sharpe_seed']:.3f} (the seed-averaged capacity table reads
{config['net_sharpe']:.3f}, and the book is one realization, not the
average of five).

## The Kelly analysis

The design book's annualized moments, the full and half Kelly leverage,
the growth at each, and the cost of over-betting when the Sharpe is
overstated by one standard error:

| quantity | value |
| --- | --- |
| mean (annualized) | {kelly['mean_ann']:.4f} |
| vol (annualized) | {kelly['vol_ann']:.4f} |
| Sharpe | {kelly['sharpe']:.3f} |
| SE of Sharpe | {kelly['sharpe_se']:.3f} |
| full Kelly leverage | {kelly['kelly_full']:.3f} |
| half Kelly leverage | {kelly['kelly_half']:.3f} |
| growth at full Kelly | {kelly['growth_full']:.4f} |
| growth at half Kelly | {kelly['growth_half']:.4f} |
| growth loss, SR overstated by one SE | {kelly['growth_loss_overbet']:.4f} |

The chosen fraction is half Kelly. Full Kelly is the wrong answer for an
estimated Sharpe: running full Kelly at a Sharpe overstated by one
standard error loses {kelly['growth_loss_overbet']:.4f} of annual growth,
while half Kelly gives up only a quarter of the growth rate for far less
variance.

## The drawdown distribution

The simulated median maximum drawdown against the analytical median:

| quantity | value |
| --- | --- |
| simulated median drawdown | {drawdown['simulated_median_drawdown']:.4f} |
| analytical median drawdown | {drawdown['analytical_median_drawdown']:.4f} |
| relative gap at the median | {drawdown['relative_gap_at_median']:.4f} |
| bootstrap samples | {int(drawdown['n_bootstrap'])} |

The analytical benchmark is the Magdon-Ismail infinite-horizon Brownian
median, ln(2) sigma squared over 2 mu. The gap measures the fat tails and
volatility clustering the Brownian benchmark does not have.

## The stop-loss verdict

The drawdown stop is flat while the running drawdown is below -10% and
re-enters at -5%. On i.i.d. bootstrapped returns it cannot improve Sharpe,
and on the real books the result is reported either way:

| book | base Sharpe | real-book Sharpe change |
| --- | --- | --- |
{stoploss_lines}

## The volatility-targeting rule

The book will run scale_t = 10% / trailing realized vol, clipped to 3
times. The dispersion of realized annual vol across years:

| quantity | value |
| --- | --- |
| raw dispersion | {voltarget['raw_dispersion']:.4f} |
| targeted dispersion | {voltarget['targeted_dispersion']:.4f} |
| dispersion reduction | {voltarget['dispersion_reduction']:.4f} |

## Drawdowns by VIX regime

| VIX tercile | mean VIX | max drawdown | periods underwater |
| --- | --- | --- | --- |
{regime_lines}

The risk budget is written per regime, not as one number.

## Stored criteria

- F10.1 (verdict {verdicts['F10.1']['verdict']}): the simulated median
  drawdown is within 10% of the analytical median, or the gap is the
  fat-tail and clustering the Brownian benchmark does not have.
- F10.2 (verdict {verdicts['F10.2']['verdict']}): the stop-loss does not
  improve Sharpe on the i.i.d. control, and the real book is reported
  either way.
- F10.3 (verdict {verdicts['F10.3']['verdict']}): vol targeting reduces
  the dispersion of realized annual vol across years by
  {voltarget['dispersion_reduction']:.4f}.

## What would falsify this?

- The stop-loss improves Sharpe in the i.i.d. control: a bug, since it
  cannot.
- Vol targeting shows no effect on realized vol dispersion: the vol
  forecast is not doing its job, back to E2 and E5.
- Drawdowns strongly regime-dependent: the risk budget is written per
  regime, not as one number.
"""
    out = ROOT / "docs" / "research" / "E10_risk_policy.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
