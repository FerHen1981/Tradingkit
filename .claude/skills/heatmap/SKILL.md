---
name: heatmap
description: Generate a time-of-day × day-of-week performance heatmap for a MEX strategy on a given asset. Use when the user wants a heatmap / hourly / weekday breakdown of a strategy's edge (expectancy, PF, win%, net, count, hold time) for a specific preset (EL_TORO, EL_MATADOR, EL_DORADO, EL_PATRON, *_TUNED) and dataset. Invoke with /heatmap <preset> <data.csv> [symbol]. Runs the backtester and publishes an interactive heatmap artifact — one per strategy+asset.
---

# Strategy performance heatmap

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
