---
name: eval-throughput
description: Answer "how fast and how cheaply does this config get an account funded" for a MEX strategy on a given asset — pass rate, sessions to pass, attempts and cost per funded account. Use when the user asks about passing evals, time-to-funded, which config to run on an eval, or how many evals to buy. Invoke with /eval-throughput <preset> <data.parquet> [symbol]. Not for funded accounts — use /payout-throughput for those.
---

# Goal A — pass evals fast

## The question this answers

Not "is this strategy profitable". An eval is a cheap lottery ticket: you buy
attempts, and what matters is **how many attempts and how many weeks until an
account is funded, and what that costs**.

That reorders things. A config with a *lower* pass rate that resolves in a third
of the time can be the better buy, because you get more attempts per month for
the same money. Profit factor does not appear in this report on purpose — an eval
does not pay you, it promotes you.

## What it reports

| Number | The decision it drives |
|---|---|
| pass rate (of all starts / of resolved) | how often an attempt works at all |
| sessions to pass — median, p25, p75 | how long your money is tied up; the p75 is the one that hurts |
| sessions to breach | fast failure is *good* here — it frees the slot |
| attempts per funded account | 1 / pass rate |
| weeks to funded | attempts × average time per attempt, timeouts priced at the full horizon |
| cost per funded account | attempts × eval fee |

A timeout is not free and is not counted as neutral: it consumed the entire
window before you could start over, so it is priced at the full horizon.

## Before running — the CVD gate

The dataset must be registered in `data/manifest.json` and its window must be
CVD-valid. If it is not, **stop and say so**; do not run with `use_cvd_filter=False`
to make it work — that backtests a different strategy than the one live
(`indicators.py:162-173`). Propose a solution and wait for approval.

Run `tools/validate_dataset.py` on any file that has not been through it.

## Steps

1. Confirm the dataset is CVD-valid and note which window is being used.
2. Run the walk-forward funnel against the eval goal:
   ```bash
   python3 -m backtest.run --data <DATA> --preset <PRESET> --symbol <SYM> \
     --goal eval --eval-fee <FEE> --funnel-step 5 --funnel-horizon 20
   ```
   `--firm <key>` overlays a specific program's rules (see `backtest/firms.py`);
   without it the preset's own account settings apply.
3. Relay the numbers with the decision attached — not a table dump. Lead with
   attempts and weeks to funded, because that is what gets bought.
4. State the window used and, if selection is happening, that the reserved
   out-of-sample block was not touched.

## Reading it honestly

- **Selection happens inside the in-sample window only.** The last three years are
  reserved (`docs/state.md`). If a number came from that block, it is a result, not
  a choice.
- **Count the configurations tried.** A good pass rate found on the twentieth
  attempt means something different from one found on the two-thousandth. Say how
  many were tried.
- **Prefer a plateau to a peak.** If the neighbouring parameter values collapse,
  the setting is memorising the sample. Report whether neighbours hold up.
- **Horizon is a real parameter.** A 20-session horizon and a 60-session horizon
  answer different questions; state which was used.

## Not for

Funded accounts. A funded account never "passes" — it earns until it breaches.
Use `/payout-throughput`.

## Not yet built

The published dashboard. Today this reports to the terminal; the Goal A dashboard
URL is pending real data so it can be verified against real output rather than
synthetic.
