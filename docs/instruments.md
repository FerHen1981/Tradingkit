# Running on other instruments (ES, GC, BTC, CL, YM, RTY, FX futures, spot FX)

The engine is instrument-agnostic. To backtest/optimise another symbol you
provide its data; the contract spec comes from the registry in `config.py`
(`CONTRACTS`), and you pick it with `--symbol`.

```bash
python -m backtest.run --data ES_1m.csv --preset EL_DORADO_TUNED --symbol ES
python -m backtest.run --data GC_1m.csv --preset EL_TORO_TUNED --symbol GC --unit-mode ATR
```

## Data format (per instrument)

Same layout as the NQ file:

```
DateTime, Open, High, Low, Close, CVD_close, Volume, BuyVolume, SellVolume, Delta
```

- `DateTime` with an explicit timezone offset (e.g. `-04:00`). Other formats are
  parsed best-effort; a tz-aware ET timestamp is ideal.
- `Delta` = per-bar buy−sell volume delta. **Required** for the delta filter. If
  an instrument has no reliable delta feed (common for spot FX), say so — we run
  it with `use_cvd_filter=False` instead of feeding garbage.
- 1-minute bars, chronological, de-duplicated.

## Contract specs already in the registry

| sym | tick | $/point | $/tick | notes |
|---|---|---|---|---|
| NQ | 0.25 | 20 | 5 | validated |
| ES | 0.25 | 50 | 12.50 | |
| YM | 1.0 | 5 | 5 | |
| RTY | 0.10 | 50 | 5 | |
| GC | 0.10 | 100 | 10 | gold |
| CL | 0.01 | 1000 | 10 | crude |
| BTC | 5.0 | 5 | 25 | **verify** (CME BTC=5, or MBT micro?) |
| 6E/6B/6J/6A/6S/6C | — | — | — | FX futures, **verify multipliers** |

Send corrected specs if your broker/data differ and I'll update the registry.

## The one thing that does NOT port automatically: tick-unit inputs

Every distance input (gap 9-12, stop ≤72, TP 122, BE/trail) is in **ticks**. A
"9-tick gap" is 2.25 pts on NQ but 0.9 pts on GC and 4.5 pips on 6E — completely
different filters. So you cannot reuse NQ's numbers on GC and expect sense.

Two ways to handle it, both supported:

1. **Re-tune per instrument** (most faithful): run the same sweeps/funnel with
   `--symbol X` and let the optimiser find that instrument's tick numbers. This
   is what "find the best settings for ES/GC/…" means and what I'll do per
   instrument once data lands.
2. **ATR unit mode** (`--unit-mode ATR`): the tick inputs become ATR multiples,
   so one config self-scales to each instrument's volatility. Good for a single
   portable config; note the default numbers (9, 12, …) are tick-counts, so in
   ATR mode you'd re-express them as small multiples (~0.5–2.0) first.

## Spot forex for FTMO — separate account model needed  ⚠️

GBPUSD, EURGBP, CADJPY, EURUSD, USDJPY on **FTMO** differ from Apex futures in
two fundamental ways, so they need a dedicated adapter (not just a contract row):

1. **Sizing is lots/pips, not contracts × point value.** 1.00 lot = 100k units;
   pip value ≈ $10 for USD-quote pairs, variable for cross/JPY pairs. The engine
   models this fine via `pointvalue`, but position sizing should switch to
   risk-% of balance (FTMO accounts are $ balances, not fixed-contract).
2. **FTMO rules ≠ Apex rules.** No intraday trailing drawdown or 6-step payout
   ladder. Instead: profit target (e.g. 10%), max daily loss (5%), max overall
   loss (10%), optional min trading days. The whole account overlay
   (`_account`) needs an `FTMO` phase implementing those, plus a "challenge
   funnel" (analogous to the eval funnel) measuring pass/fail of the challenge.

This is a clean, well-scoped addition — I'll build an `FTMOAccount` overlay and a
lot/pip sizing mode when we get to the spot-FX leg. Futures FX (6E, 6B, …) run on
the existing Apex model with just the right contract specs.

## Plan when data arrives

Per instrument: (1) load + data-quality check, (2) pick contract spec, (3) run
El Toro (funnel pass-rate) and El Dorado (banked/breach) with re-tuned distance
inputs, (4) walk-forward validate, (5) report best settings + caveats. For FTMO
spot-FX, first build the FTMO overlay, then the same loop against challenge
pass-rate.
