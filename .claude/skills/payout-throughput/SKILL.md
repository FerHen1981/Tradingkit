---
name: payout-throughput
description: Answer "how much does this funded account actually pay out before it dies" for a MEX strategy on a given asset — payouts per account-year, odds of the full 6/6 ladder, breaches and survival. Use when the user asks about funded accounts, milking, payout cadence, the 6-step ladder, or how long an account survives. Invoke with /payout-throughput <preset> <data.parquet> [symbol]. Not for evals — use /eval-throughput for those.
---

# Goal B — milk funded accounts to 6/6 payouts

## The question this answers

A funded account never "passes". It earns until the trailing drawdown ends it. So
the question is **cadence and survival**: how many payouts per account-year, and
how likely is the full six-step ladder before a breach resets everything.

This is the opposite optimisation from Goal A. There, a fast breach is fine
because it frees the slot. Here, a breach destroys the ladder — `pa_payouts_this_cycle`
resets to zero (`engine.py:531`), so five payouts followed by a breach leaves you
starting from step one. Survival outranks return.

## What it reports

| Number | The decision it drives |
|---|---|
| payouts per window — median, p25, p75 | the realistic cadence, not the best case |
| payouts per account-year | comparable across horizons |
| P(any payout) | does this account ever pay at all |
| P(full 6/6 ladder) | the actual goal |
| banked per account-year, and in DD-units | comparable across firms and account sizes |
| breaches per account-year | how often the ladder resets |
| survival rate | share of windows that finished untouched |

**DD-units** = dollars divided by that account's trailing-drawdown allowance. It is
the only unit that makes GC on a 50k Apex comparable to 6E on a 100k FTMO, because
both goals are defined against the drawdown, not the balance.

## Prop-firm rules that decide the outcome

These are modelled and they dominate the result — read the report knowing them:

- **Trailing drawdown** locks once the account is far enough ahead; before that it
  follows the high-water mark and a good day can raise your own floor.
- **Qualifying days** (≥5) and the **consistency rule** gate every payout. A single
  huge day can make you ineligible while profitable — check `consistency_pct`.
- **Wait-for-cap** (`use_wait_for_cap`) changes the cadence completely: taking the
  full ladder cap each time is slower but larger. Say which mode produced the number.
- **Breach resets the cycle**, not just the balance.

## ⚠ One account is not the fleet

This report models **one account at a time**. Reading it as a fleet number is how
four accounts liquidate on the same afternoon.

`middleware/app/risk.py` gates per account (`_halted` is a per-account, per-day
set); nothing sees the portfolio. And NQ and ES correlate around 0.9 — running one
strategy across both is leverage wearing the costume of diversification.

So when the question is about several accounts, say plainly that this number does
not answer it, and that the fleet model (N accounts, correlated returns, P(≥k
simultaneous breaches)) is what does. Do not multiply a single-account result by
the number of accounts.

## Before running — the CVD gate

The dataset must be registered in `data/manifest.json` and CVD-valid. If it is not,
**stop and say so**; never fall back to `use_cvd_filter=False` — that backtests a
different strategy than the one live. Propose a solution and wait for approval.

## Steps

1. Confirm the dataset is CVD-valid and note the window.
2. Run the walk-forward funnel against the payout ladder. Use a long horizon —
   a ladder needs room:
   ```bash
   python3 -m backtest.run --data <DATA> --preset <PRESET> --symbol <SYM> \
     --goal payout --funnel-step 10 --funnel-horizon 126
   ```
   126 sessions ≈ half a year; the report scales rates to a full account-year.
3. Lead with payouts per account-year and P(6/6). Banked dollars come after —
   dollars without the ladder context describe a lucky window.
4. State the horizon, the wait-for-cap mode, and the window used.

## Reading it honestly

- **Median over mean.** One window that reached 9 payouts drags a mean; the p25 is
  what most accounts will actually see.
- **Selection stays inside the in-sample window.** The reserved out-of-sample block
  is not a tuning surface (`docs/state.md`).
- **Live overrules.** Where real fills exist, they weigh 2×, and if slippage
  deviates structurally the backtest is miscalibrated rather than merely noisy —
  re-run it with measured values instead of averaging.

## Not yet built

The published dashboard, and the fleet model. Today this reports to the terminal
for a single account; the Goal B dashboard URL and the correlated multi-account
simulation are the next builds.
