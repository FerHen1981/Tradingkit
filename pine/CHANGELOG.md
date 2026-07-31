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


## v6.8.9 / v6.8.14 — FX / tick-volume delta note

No engine change. The delta filter already **auto-falls-back to tick-volume**
on spot-FX charts (which have no real volume), so the scripts run on FX as-is.
Clarified the *Use Delta Filter* tooltip to say this and to recommend, per the
CVD contribution test (`docs/forex_delta.md`), turning the **Streak off** (or the
filter off) on FX. The "borrow a CME FX-future's real delta" idea was dropped:
it needs a nested `request.security(sym, ta.requestVolumeDelta(...))` which
Pine generally rejects and would break the whole script.

Target-driven position sizing (size from the eval goal / DD room instead of a
fixed contract count) was prototyped in the Python backtester, not Pine — see the
session notes: it is the right architecture but does not manufacture edge, so it
is held until a positive-edge config is locked in.

## v6.8.10 / v6.8.15 — auto-guard the delta filter on non-futures assets

The CVD/delta filter needs volume. Added an auto-guard so the scripts behave on
Forex / CFD / Spot / Crypto / Commodities without manual toggling:
- `cvdEff = useCVDFilter and not na(volume)` — on symbols with **no real volume**
  (many CFDs/spot) the filter auto-disables (and `ta.requestVolumeDelta` is not
  called, avoiding a no-data runtime error).
- `streakEff = useCvdStreak and (syminfo.type=="futures" or "crypto")` — on
  **forex/CFD** (tick-volume proxy) the 4-bar streak auto-relaxes to
  direction-only; futures/crypto keep the full filter.
Purely a robustness guard; on futures nothing changes. Bundles with v6.8.9.

## How to use
Copy the file's contents into the Pine editor and save. Verify it compiles
(this environment cannot compile Pine). Then run your entire-history backtest —
the memory error should be gone. Paste any compile error back for an immediate fix.
