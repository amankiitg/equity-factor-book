# The borrow rate: 2% for no stated reason, and what the evidence says

`efb/costs.py` carries `BORROW_RATE = 0.02`, and the docstring says only "2% per year on
short notional, the E6 provisional". Nothing records where 2% came from. It is the one
cost parameter in the model that is neither measured here nor sourced from a paper, and
it matters: at 2% the monthly cadence designs net a few basis points a year or less at
the 169 bp gross anchor, and at 0.35% they net sixty.

This note collects what is publicly documented, recommends a rate and a range, and
states what the recommendation does *not* cover. **`BORROW_RATE` is not changed here** -
the owner decides.

## What the public evidence says

| # | claim | figure | source |
|---|---|---|---|
| 1 | Index-level borrow of the largest S&P 500 names is priced near 10 bp/yr | SPY trailing 1-year volume-weighted average fee **10 bp**, IVV **11 bp** (utilization 19% / 0%) | State Street Global Advisors, citing Markit IHS, data as of 2026-09-11 — <https://www.ssga.com/us/en/intermediary/insights/unlocking-the-securities-lending-potential-of-spy> |
| 2 | The industry's general-collateral anchor is 30 bp | "the **30bps** cost of a general collateral borrow"; **83-84%** of US short interest was GC in 2022-23; **4.6-5.5%** sat in names with fees **> 1.0%** | S3 Partners, 2024-01-24 — <https://www.s3partners.com/articles/us-stock-borrow-fees> |
| 3 | General collateral is cheap and specials are a small minority of names | **91%** of lent stocks cost **< 1%/yr**, value-weighted mean GC **17 bp**; **9%** of stocks had fees **> 1%**, mean **4.3%/yr**, extremes 35-50%; "S&P 500 constituents ... are almost always general collateral" | D'Avolio, *The Market for Borrowing Stock*, JFE 2002 — <https://static1.squarespace.com/static/5e6033a4ea02d801f37e15bb/t/5f5be636844f06065a200cdb/1599858231220/davolio_borrowing_stock_JF.pdf> |
| 4 | Borrow cost concentrates in the hard-to-borrow tail | names with **> 10%** fees were **< 2%** of dollars shorted but **> 40%** of total borrow cost | S3 Partners, 2024-01-24 |
| 5 | Alpaca charges nothing to borrow the easy names | "$0 locate and borrow fees" on **5,000+** easy-to-borrow securities; hard-to-borrow needs an approved locate, round lots of 100, and locate fees are separate and non-refundable | Alpaca Margin and Short Selling docs, updated 2026-09-17 — <https://docs.alpaca.markets/us/docs/margin-and-short-selling> |
| 6 | Alpaca's hard-to-borrow fee is a per-name annualized rate accrued daily | fee = Σ (HTB short market value × that stock's HTB rate) / **360**, charged daily and **3 days** over a Friday settlement; the rate is per account and **not published**; the `/v1/locates/quotes` `price` is a per-share locate fee, not the annualized rate | same doc |
| 7 | Alpaca pays no rebate on short proceeds | "Alpaca shall **not be obligated to pay interest on any free credit balance**" and receives "interest and/or **rebates** derived from customer ... free credit balances" | Alpaca Customer Agreement §41 (V26.2026.07) — <https://files.alpaca.markets/disclosures/library/AcctAppMarginAndCustAgmt.pdf> |
| 8 | The borrow fee is authorised but not scheduled | "Alpaca **may charge me a fee to borrow a Security** in connection with a short sale"; the Brokerage Fee Schedule carries **no** borrow/HTB/locate line item | Customer Agreement §11; <https://files.alpaca.markets/disclosures/library/BrokFeeSched.pdf> (template 2026-10-12) |
| 9 | Paper-versus-live accrual is undocumented | no public statement on whether paper accounts accrue borrow or locate fees | searched Alpaca docs and FAQ |

Two of those deserve a caveat. **#1 is a lender's publication citing a data provider**,
not a raw dataset: it is the most recent hard number found, and it is for the two
largest ETFs rather than the average S&P 500 name. **#5-#8** describe a broker that
charges nothing on general collateral at all, so the *effective* rate for this book
depends on whether any name it shorts is hard to borrow - something Alpaca does not
publish a list for, but exposes per asset as `borrow_status` (`easy_to_borrow` or
`hard_to_borrow`) on `GET /v2/assets` — <https://docs.alpaca.markets/us/reference/get-v2-assets-1>.

## Recommendation

**Use 0.35%/yr as the default, with a range of 0.10%-1.00%.**

The reasoning, in the order it matters:

1. **General collateral is 10-35 bp, not 200.** Three independent sources put the GC
   cost at 10 bp (index-level, 2026), 17 bp (value-weighted mean, 2002) and 30 bp (the
   industry benchmark, 2024). 2% is six to twenty times any of them.
2. **But the tail is real, and the model has no tail.** The book shorts ~160-180 S&P 500
   names at a time and the model charges one rate to all of them. 9% of lent names cost
   more than 1%/yr and average 4.3%, and it is those names that carry 40% of a lender's
   borrow bill on 2% of the dollars. A single number is an average over a distribution
   with a fat tail, so it should sit above the GC point estimate rather than at it: 35 bp
   is roughly the GC benchmark plus a margin for the tail.
3. **At Alpaca the general-collateral case is free**, which makes 35 bp conservative
   rather than aggressive, and means the number is a stress input rather than a
   forecast. The thing to watch is a short that turns hard to borrow; the fee is then
   quoted per name and accrued daily, and a 20-50%/yr name would swamp every other cost
   in this model.

### The monthly book at the anchor, at each rate

The study's restatement is `net = 169 - cost - borrow x (rate / 2%)`, where `borrow` at
2% is 100.8 bp/yr for the G5 variant (a book that is ~50% short gross, so 2% x 50.4%).
`docs/research/daily_design_study.md` (on `main` since 2026-10-24) gives G5 a cost of 88.7
bp/yr; B0 (no guard) costs 62.4 bp and shares the same borrow term.

| borrow rate | G5 net at 169 bp gross | B0 net at 169 bp gross |
|---|---|---|
| 0.10% (index-level GC) | **+75.3** | +101.6 |
| **0.35% (recommended)** | **+62.7** | +89.0 |
| 0.50% | +55.1 | +81.4 |
| 1.00% | +29.9 | +56.2 |
| 2.00% (today's constant) | -20.5 | +5.8 |

The monthly book with the 5% guard breaks even at a borrow rate of about
**1.6%/yr** (169 - 88.7 = 80.3 bp of headroom against 50.4 bp of short gross per 1% of
rate). Every GC rate in the evidence leaves it comfortably positive. The 2% constant is
therefore doing the work of a pessimistic stress case, not of a central estimate - which
is a defensible thing to keep, provided it is labelled as one.

## What this note does not settle

- **The rate a paper account is charged.** If the paper account accrues nothing, the
  live comparison of expected against realized cost will look better than the live
  account will, and the difference is this term.
- **Per-name borrow status in the run.** The loop could read `borrow_status` per asset
  and charge 0 on `easy_to_borrow` and a flagged estimate on `hard_to_borrow`; that is a
  change to the cost model, and it waits for the owner.
- **Locate fees**, which are per-share and one-off, and are not in the model at all.

## The account's shorts, read from the broker (2026-10-24 01:12 UTC)

The one question above that a read can answer is whether any name the book is
short is hard to borrow. Read-only, from `GET /v2/positions` then `GET
/v2/assets/<symbol>` for every short, on the paper account:

| | |
|---|---|
| positions | 174 (91 short, 83 long) |
| equity | $982,176.93 |
| long notional | $486,672.56 |
| short notional | −$486,945.06 |
| gross | $973,617.61 |
| short as a share of gross | **50.0%** |
| shorts that are `easy_to_borrow: true`, `shortable: true`, `status: active`, `borrow_status: easy_to_borrow` | **91 of 91** |
| **hard-to-borrow names currently short** | **none** |

The largest shorts, for the record:

| symbol | shares | short notional | borrow status |
| --- | --- | --- | --- |
| AES | −968 | −$14,520.00 | easy_to_borrow |
| LHX | −44 | −$11,146.19 | easy_to_borrow |
| VICI | −454 | −$10,814.28 | easy_to_borrow |
| NVDA | −51 | −$10,766.81 | easy_to_borrow |
| TSN | −60 | −$3,402.00 | easy_to_borrow |

So tonight the borrow tail is **$0 of notional**, and Alpaca's published rate for
easy-to-borrow names is "$0 locate and borrow fees" (claim 5 above). The `0.35%`
constant is therefore a stress input against a realized cost of nothing, which is
the right shape for it: the number that matters is not tonight's bill but the
first night a short turns hard to borrow, when the fee is quoted per name,
accrued daily on `/360`, and can be 20-50%/yr.

At 0.35% on a 50.4%-short book that is about **17.6 bp a year of NAV**, or $1,730
on the equity above - small next to the 169 bp gross anchor, and inside the
model's own range.

What this read **cannot** show, and why:

- **A borrow-fee accrual on the account.** Paper trading does not simulate borrow
  fees at all - the paper-versus-live table in
  <https://docs.alpaca.markets/us/docs/paper-trading> marks "Borrow Fees" as
  "Coming Soon". A zero accrual here is the simulator's, not the broker's.
- **Locate fees.** The locate endpoints are documented as "not available in paper
  trading", so there is nothing to read.
- **A per-name HTB rate.** Alpaca does not publish the rates; `borrow_status` is
  the only per-asset signal, and it is what the table above reads.
