# Level B — pluggable entry architecture

Today the engine only enters on **FVG**. `_signal()` returns one hardcoded
FVG direction + its mid/top/bot; everything else (CVD/VWAP filters, stop, TP,
sizing) hangs off that. Price action is broader — a **liquidity sweep**, a
**CVD divergence**, an **order block**, a **structure break (BOS/CHoCH)**, an
**EMA/MACD/RSI cross** are all valid entries, and which one works depends on the
regime (trend / counter-trend / turning point). Level B makes entries pluggable.

## The abstraction

An **entry generator** is a function that, per bar, yields a signal:

```
EntrySignal = (dir, entry_ref, stop_up, stop_down, kind)
  dir        +1 long · -1 short · 0 none
  entry_ref  price to enter at (limit) — or NaN for "market at close"
  stop_up    a price level to anchor a SHORT stop above (e.g. swept high, OB top)
  stop_down  a price level to anchor a LONG stop below (e.g. swept low, OB bottom)
  kind       the generator name (for provenance)
```

The engine keeps its stop/TP/sizing/account machinery unchanged; it just asks
the **enabled generators** for a signal instead of hardcoding FVG. FVG becomes
generator #1 (`entry_ref=fvg_mid`, `stop_down=fvg_bot`, `stop_up=fvg_top`) — so
El Toro is byte-for-byte identical after the refactor. That equality is the
regression test for step 1.

Filters (CVD streak, VWAP veto, premium/discount, time windows) stay separate:
they **veto** a generator's signal, they don't create entries.

## Entry generators to wire (broad, from the research)

Each is a numpy pass in `indicators.compute()` producing a per-bar dir + refs.

| Generator | Fires on | Entry / stop refs | Regime it suits |
|---|---|---|---|
| `fvg` *(have)* | 3-bar imbalance | mid / gap edge | trend continuation |
| `cvd_divergence` | price HH+CVD LH (bear) / LL+HL (bull) | close / pivot | turning point |
| `liquidity_sweep` | sweep of EQH/EQL then reclaim | reclaim / swept extreme | turning point / counter-trend |
| `order_block` | mitigation of last opposite candle before impulse | OB edge / OB far edge | trend continuation |
| `structure_bos` | break of prior swing (BOS) | close / broken swing | trend |
| `structure_choch` | first counter-break (CHoCH/MSS) | close / swing | reversal |
| `ema_cross` | fast EMA crosses slow EMA | close / ATR or swing | trend |
| `macd_cross` | MACD line crosses signal | close / ATR | trend/momentum |
| `rsi_reversion` | RSI exits OB/OS | close / swing | counter-trend |
| `sweep_reversal` | wick sweep + close back | close / wick extreme | turning point |

`silver_bullet` = `fvg` gated to the ICT time windows (a filter on `fvg`, not a
new generator). `premium_discount_ote` = a **context filter** (only longs in
discount, shorts in premium).

## Strategy-family coverage (what the roster is FOR)

The generator roster is how the engine spans the classic strategy families. This
is a **single-instrument 1m-bar + CVD** engine, so directional families map onto
entry generators; a few families need machinery this engine does not have, and
we say so rather than fake them.

| Family | Engine mechanism | Status |
|---|---|---|
| Trend Following | `ema_cross`, MA-pullback | ✅ B1 / wireable |
| Momentum | displacement/impulse entry | wireable |
| Mean Reversion | VWAP-revert, BB-extreme (enters *against* the VWAP bias) | wireable (new generator) |
| Breakout | `structure_bos`, range-break, ORB, Donchian | ✅ **B2 (BOS landed)** |
| Breakdown | `structure_bos` short-side | ✅ same generator |
| Range Trading | range-fade | wireable |
| Reversal | `sweep_reversal`, `structure_choch` | wireable |
| Pullback / Retracement | VWAP/EMA pullback | wireable |
| Continuation | flag/consolidation break = `structure_bos` | ✅ covered by BOS |
| Liquidity / Stop Run | `liquidity_sweep` | wireable |
| Order-Flow | `cvd_divergence` ✅ wireable; absorption/imbalance = footprint-data-gated | partial |
| Volatility | squeeze / ATR-expansion gate | wireable (coarse) |
| Market Making / Scalping | needs L2 order-book + tick — different execution model | ❌ out of scope |
| Relative Value / Spread | needs **two instruments at once** — single-symbol engine | ❌ needs a multi-series engine |
| Statistical Arbitrage | pairs/z-score, multi-instrument | ❌ needs a multi-series engine |
| Event / News Driven | present only as a **filter** (avoid roll/OpEx/FOMC); as a *trigger* needs an economic-calendar feed | filter-only |

The ❌ rows are an honest boundary, not a TODO: 12–15 would each require a
genuinely different engine (order-book, or two synchronized price series). They
stay out until/unless we build that, so the mill never pretends to test them.

## Regime context (which entry when)

A lightweight **regime tag** per bar drives which generators are allowed:
- `trend` (ADX≥threshold and MA-slope sign) → continuation generators
- `range` (ADX<threshold) → reversion/sweep generators
- `turning` (divergence or sweep present) → turning-point generators

The spec picks entries + optionally a regime gate; the engine only enters when
the bar's regime matches the generator's declared `suits`.

## Engine changes (surgical)

1. `indicators.compute()` gains a block per enabled generator → arrays
   (`<gen>_dir`, `<gen>_entry`, `<gen>_stopup`, `<gen>_stopdn`) + regime arrays.
2. `_signal(i)` → `_entry(i)`: iterate the spec's enabled generators in priority
   order; first non-zero dir that passes the filters + regime gate wins; return
   its refs. FVG-only spec reproduces today's `_signal` exactly.
3. `_try_place()` already takes (mid, top, bot) — rename to (entry_ref, stop_up,
   stop_down); when `entry_ref` is NaN, enter market at close (add a market path
   to `_broker`). Stops fall back to swing/ATR when a generator gives no level.
4. Registry: mark each generator `engine: entry` with its params; `spec_to_config`
   maps them; `WIRED_GROUPS`/generator sampler include them as they land.

## Build order (incremental, each VPS-validated)

- **B0 — refactor, zero behavior change.** Extract `_entry()` with only FVG.
  Guard: El Toro classic on NQ 5m must match the pre-refactor KPIs to the dollar.
- **B1 — first cross entry (`ema_cross`) end-to-end.** ✅ DONE. El Toro identical
  (404 / PF 1.22 / $11,437.7); EMA_Cross_20_50 = a genuinely different strategy
  (9,680 trades, PF 1.19). Proves the pluggable-generator + market-entry path.
- **B2/B3 — full wireable family LANDED (batch).** The whole directional roster
  is now wired, each guarded by a `use_*` flag (default off → El Toro identical),
  each lookahead-safe, for one combined VPS test pass. Generator → group → spec:

  | Generator | Group | Spec | Family |
  |---|---|---|---|
  | `structure_bos` | market_structure (mode:bos) | bos.yaml | breakout/continuation |
  | `structure_choch` | market_structure (mode:choch) | choch.yaml | reversal |
  | `liquidity_sweep` | liquidity_eqhl | liquidity_sweep.yaml | liquidity/stop-run |
  | `cvd_divergence` | divergence (osc_source:cvd) | cvd_divergence.yaml | order-flow |
  | `order_block` | order_block | order_block.yaml | continuation |
  | `momentum_impulse` | momentum | momentum.yaml | momentum |
  | `macd_cross` | macd | macd_cross.yaml | momentum (classic) |
  | `rsi_reversion` | rsi | rsi_reversion.yaml | mean reversion (classic) |
  | `donchian_break` | donchian | donchian.yaml | breakout (classic) |
  | `ma_pullback` | moving_average | ma_pullback.yaml | trend/pullback (classic) |
  | `bb_revert` | bollinger_bands | bb_revert.yaml | mean reversion/range (classic) |

  Design note: the CVD-streak + VWAP-veto filters are TREND filters, so the
  reversal/reversion specs (choch, liquidity_sweep, cvd_divergence, rsi_reversion,
  bb_revert) deliberately omit them — applying a with-trend filter to a
  counter-trend entry would suppress nearly all of its trades.
- **Still TODO (honest):** liquidity EQH/EQL tolerance (sweep uses the confirmed
  swing for now), RSI/MACD divergence (only the CVD axis is wired), OB breaker
  variant, BB EMA-basis, structure wick-ref.
- **B3 — classic entries:** `macd_cross`, `rsi_reversion`.
- **B4 — regime context** gate (trend/range/turning) + premium/discount filter.
- **B5 — grow the generator's search space** to all wired entries; re-run the
  honest mill → far more genuinely-distinct candidates.

Only after an entry is truly wired does it enter `WIRED_GROUPS`, so the honest
generator's space grows exactly in step with what the engine can really do.

## Testing constraint

The engine needs numpy/pandas (bt-venv on the VPS); it can't run in the build
sandbox. So every engine step is compile-checked here and **validated on the
VPS** — B0's dollar-for-dollar El Toro match is the anchor that proves the
refactor is safe before any new entry is added.
