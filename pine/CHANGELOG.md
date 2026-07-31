# MEX Pine scripts — optimisation changelog

The four scripts are one engine; they differ only in phase + drawdown model:

| script | version | phase | drawdown model |
|---|---|---|---|
| MEX_EL_TORO | v6.8.7 → **v6.8.8** | Eval | Intraday |
| MEX_EL_MATADOR | v6.8.7 → **v6.8.8** | Eval | EOD |
| MEX_EL_DORADO | v6.8.12 → **v6.8.13** | Funded/PA | Intraday |
| MEX_EL_PATRON | v6.8.12 → **v6.8.13** | Funded/PA | EOD |

## v6.8.8 / v6.8.13 — changes

### 1. FIX: "Memory limit exceeded" on entire-history backtests
The strategy created FVG boxes, trade-zone boxes, exit labels and info labels on
qualifying bars across the **whole** history. Over 1M+ bars that exhausts
TradingView's drawing/memory budget.

**Fix:** a new input **`Visuals: draw only on last N bars (0 = all)`** (default
**2000**, group *B2 · BACKTEST — Visuals & Labels*) and a guard
`inDrawWin = drawLast <= 0 or (last_bar_index - bar_index) <= drawLast`. Every
drawing-object *creation* is now gated by `inDrawWin`:
- FVG boxes + tested-box recolouring
- unfilled-limit markers
- exit labels (SL/TP/PnL)
- trade zones + trade-info label

This is **purely cosmetic — strategy results, orders and P&L are identical**.
Visuals simply render on the most recent N bars. Set the input to `0` to draw on
all bars (may hit the memory limit again on long histories).

> If "Memory limit exceeded" still appears with a small `drawLast`, the remaining
> suspect is `ta.requestVolumeDelta` buffering the 1-minute lower timeframe over
> the whole history — tell me and I'll address that path separately.

### 2. FIX (A1): recovery-trail was effectively dead
`useRecovTrail` gates on `attemptTradeNo == 1 and attemptFirstLoss`, but those
counters were only reset inside the `evalTrack` block (off by default). With the
account phase layer in use, they never reset — so the recovery-trail fired only
on the **2nd trade of the entire run**, then never again.

**Fix:** re-arm the counters each trading day:
```pine
if isNewTradingDay
    attemptTradeNo := 0
    attemptFirstLoss := false
```
The recovery-trail now works as intended (per session). Backtest evidence: with
the recovery-trail active it adds ~+4pp to El Toro's eval pass-rate.

## Not yet changed (next step)
- **Inputs-menu reorganisation** (Research / Eval / Funded grouped). Deferred on
  purpose: the account-section inputs differ between the Eval scripts (Toro/
  Matador have `Eval Profit Goal` as an input) and the Funded scripts (Dorado/
  Patron have the payout/DLL/consistency/MAE inputs), so it is a per-file change.
  Will be done once these memory/recovery fixes are confirmed to compile.

## How to use
Copy the file's contents into the Pine editor and save. Verify it compiles
(this environment cannot compile Pine). Then run your entire-history backtest —
the memory error should be gone. Paste any compile error back for an immediate fix.
