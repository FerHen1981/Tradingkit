---
name: heatmap
description: Diagnostic time-of-day × day-of-week heatmap for a MEX strategy on a given asset (expectancy, PF, win%, net, count, hold time). Use when the user explicitly wants to SEE where in the week an edge sits — a heatmap, hourly or weekday breakdown. Invoke with /heatmap <preset> <data.csv> [symbol]. Do NOT use to decide what to run: "which config passes evals fastest" is /eval-throughput and "how much does a funded account pay out" is /payout-throughput.
---

# Strategy performance heatmap

> **Diagnostic, not a decision instrument.** This shows where an edge sits in the
> week. Neither goal asks that. An hour with a high profit factor and three trades
> a month is excellent here and useless for passing an eval quickly. Use
> `/eval-throughput` (Goal A) and `/payout-throughput` (Goal B) to choose what to
> run; use this to understand *why* one of them behaves the way it does.
>
> Fine-grained day×hour cherry-picking has already been disproven out-of-sample
> (`CLAUDE.md`). Treat every bright cell as a hypothesis, not a filter.

Produces an interactive ET-hour × weekday heatmap for one **strategy preset** on
one **asset dataset**, coloured by a switchable metric (expectancy / PF / win% /
net / trade count / avg hold), with per-cell hover across all axes.

## Inputs (from the slash-command args)

`/heatmap <preset> <data.csv> [symbol] [--native]`

- **preset** — one of `EL_TORO EL_TORO_TUNED EL_MATADOR EL_DORADO EL_DORADO_TUNED EL_PATRON`.
- **data.csv** — 1-minute bars: `DateTime,Open,High,Low,Close,CVD_close,Volume,BuyVolume,SellVolume,Delta` (Delta optional for non-futures).
- **symbol** — contract spec for P&L scaling: `NQ ES YM RTY GC CL BTC 6E 6B 6J 6A 6S 6C` (default NQ).
- **--native** — use the account phase overlay instead of research mode (default: research, i.e. all signals, cleanest per-bucket stats).

If the user names a strategy + asset but omits a path, ask for the CSV path (or use one already discussed in the conversation).

## Steps

1. Run the generator from the repo root (it reuses the `backtest/` package):
   ```bash
   python3 .claude/skills/heatmap/generate.py \
     --preset <PRESET> --data <DATA.csv> --symbol <SYMBOL> \
     --out /tmp/heatmap_<PRESET>_<SYMBOL>.html
   ```
   Add `--native` if requested. The script prints the best/worst hours and
   weekday summary to stdout — relay those.
2. Publish the produced HTML with the **Artifact** tool (favicon 🔥, a title like
   `<PRESET> · <SYMBOL> heatmap`). Each strategy+asset gets its own artifact.
3. Summarise the read: strongest / weakest hours, weekday tilt, and the
   in-sample overfitting caveat (hour filters must be walk-forward validated).

## Notes

- One heatmap = one preset + one asset. For several, run the generator once per
  combination and publish each separately.
- The heatmap uses ENTRY-bar attribution (ET hour + weekday) over the full file.
- Requires `pandas`/`numpy` (the backtester's deps).
