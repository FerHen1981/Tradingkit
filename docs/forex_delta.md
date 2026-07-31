# Volume delta outside futures (spot FX / FTMO) — and how crucial CVD really is

## First: is the CVD pillar even pulling its weight? (NQ test)

Before replacing CVD for FX, we measured its contribution on NQ by removing it:

| El Dorado (PA) | trades | PF | banked | breaches |
|---|---:|---:|---:|---:|
| CVD filter ON (default) | 1,130 | 0.89 | $9,000 | 28 |
| CVD filter OFF | 4,082 | 0.91 | $20,000 | 74 |
| CVD streak OFF (direction only) | 3,413 | **0.94** | $23,000 | 52 |

| El Matador eval pass-rate | pass |
|---|---:|
| CVD ON (default) | 35.8% |
| CVD OFF | **44.4%** |

**The CVD *streak* (4 consecutive same-direction delta bars) does not clearly add
edge on NQ** — dropping it keeps/improves PF and raises pass-rate. It mostly cuts
frequency. (Independent reimplementation, in-sample — walk-forward validate before
removing it live.) Implication: **losing the delta pillar on spot FX is far less
costly than assumed.**

## The problem in FX

Spot FX is decentralised — there is no true, centralised volume or buy/sell delta.
So `ta.requestVolumeDelta` on a spot pair is built from **tick volume** (count of
price updates), a proxy, not real order flow.

## Three options (best → simplest)

1. **Borrow the CME FX future's real delta** (majors). The future has real
   exchange volume + delta and the spot pair tracks it tick-for-tick. Map:
   EURUSD→`6E`, GBPUSD→`6B`, USDJPY→`6J`, AUDUSD→`6A`, USDCAD→`6C`, USDCHF→`6S`.
   In Pine, pull the future's delta onto the spot chart:
   ```pine
   deltaSym = input.symbol("CME_MINI:6E1!", "Delta source symbol (futures)")
   [dO,dH,dL,dC] = request.security(deltaSym, timeframe.period,
        ta.requestVolumeDelta(cvdLowerTf, "1D"), lookahead=barmerge.lookahead_off)
   perBarDelta := dC - dO
   ```
   Best fidelity. Crosses (EURGBP, CADJPY) have no single future → option 2 or 3.

2. **Tick-volume delta** (universal fallback). What `ta.requestVolumeDelta` already
   gives on FX. Correlates ~0.8–0.9 with real volume. Weaker but always available.

3. **Drop the streak (or CVD entirely).** Given the NQ result above, a
   direction-only delta or no delta filter is competitive — and it removes the FX
   data problem entirely, leaning on the other pillars (FVG + VWAP + time-gate),
   which are all price-based and fully valid in FX.

## Proposed new-version feature: a "Delta source" selector

Add one input group to the scripts:

```pine
deltaSrc = input.string("Chart CVD", "Delta source",
     options=["Chart CVD","External futures","Tick-volume proxy","Direction-only","Off"],
     group="L8 · Filters: Volume Delta")
deltaSym = input.symbol("CME_MINI:6E1!", "  ↳ external futures symbol", group="L8 · Filters: Volume Delta")
```
- **Chart CVD** — current behaviour (futures).
- **External futures** — pull real delta from `deltaSym` (spot-FX majors).
- **Tick-volume proxy** — chart `requestVolumeDelta` (FX fallback).
- **Direction-only** — delta sign, no 4-bar streak (the NQ-competitive lighter filter).
- **Off** — disable the delta pillar (rely on FVG + VWAP + time).

This makes one script run on futures *and* spot FX, and lets you A/B the CVD
weight. Ships as v6.8.9 / v6.8.14 once the v6.8.8 memory/recovery batch is
confirmed to compile (not stacking untested Pine changes).

## To validate empirically

Send **6E (or another FX future) data** — it has real Delta — and I'll test in the
Python backtester whether "future-delta on the pair" and "direction-only / off"
hold up out-of-sample, before you commit the Pine change.
