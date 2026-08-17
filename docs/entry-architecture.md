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
- **B1 — first cross entry (`ema_cross`) end-to-end.** New indicator arrays,
  registry entry, spec/sampler wiring, market-entry path. Validate it makes
  sensible, different trades.
- **B2 — order-flow/PA entries:** `cvd_divergence`, `liquidity_sweep`,
  `order_block`, `structure_bos`/`choch`, `sweep_reversal`.
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
