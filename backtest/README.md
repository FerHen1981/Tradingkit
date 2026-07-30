# NQ futures backtester — MEX ΞL TORO / ΞL DORΛDO

A faithful, self-contained Python reimplementation of the two MEX Pine v6
strategies, built to backtest and optimise them on **NQ 1-minute** data with a
real **futures + Apex prop-firm** model (contract multiplier, tick value,
trailing drawdown, daily loss limit, consistency rule, 6-step payout ladder) —
things TradingView's tester and the trader.dev crypto engine can't express.

The two scripts share **one engine**; they differ only in default inputs and
account phase. So this package is one engine (`engine.py`) plus two presets
(`config.py`: `EL_TORO`, `EL_DORADO`).

## Layout

| file | role |
|---|---|
| `config.py` | contract specs (NQ: tick 0.25, $20/pt, $1.55/side) + the two presets |
| `data.py` | CSV loader, ET timezone, CME session roll at 18:00 ET |
| `indicators.py` | FVG, session VWAP, confirmed swing pivots, volume-delta streak |
| `engine.py` | bar-by-bar order/position state machine + Apex account overlay |
| `funnel.py` | walk-forward **eval funnel** (pass-rate distribution) |
| `metrics.py` | trade-list KPIs |
| `run.py` | CLI |

## Usage

```bash
# pure signal stats over the whole file (no account halts)
python -m backtest.run --data NQ_1m.csv --all --research

# native Apex phase (Eval overlay for Toro, PA payout-cycle for Dorado)
python -m backtest.run --data NQ_1m.csv --all

# El Toro eval funnel: how often does it fund an account?
python -m backtest.run --data NQ_1m.csv --preset EL_TORO --funnel

# dump the trade list
python -m backtest.run --data NQ_1m.csv --preset EL_DORADO --trades-out trades.csv
```

CSV columns expected: `DateTime, Open, High, Low, Close, CVD_close, Volume,
BuyVolume, SellVolume, Delta` (DateTime like `18-6-2023 18:00:00 -04:00`).

## What the engine reproduces

- **Signal**: 3-bar fair-value gap, size-filtered (ticks), with an optional
  confirmation-memory window (`confirm_bars`).
- **Filters**: session VWAP side-veto, per-bar volume-delta direction with a
  consecutive-streak requirement (uses the real `Delta` column, not the Pine
  `requestVolumeDelta` approximation).
- **Entry**: resting limit at the 50% FVG retrace, expires after `expiry_bars`.
- **Stop**: swing structure (confirmed pivot ∧ gap edge ∧ buffer), capped.
- **Take-profit**: R-multiple / fixed-ticks / swing.
- **Management**: break-even, trailing, Eval-only recovery-trail.
- **Time gate**: ET weekday/hour mask, Monday-open block, 16:55–18:00 flat.
- **Apex overlay**: intraday/EOD trailing drawdown, DLL, day-trail exit,
  consistency rule, qualifying days, 6-step payout ladder with wait-for-cap,
  PA breach→reset (backtest mode), MAE (30%) guard.

## Fill model & parity caveats  ⚠️ read this

This is an **independent** engine, **not** bit-exact to TradingView. Where the
broker emulation is ambiguous it chooses a **pessimistic** rule:

- Limit entries rest from the bar *after* placement; fill at the limit price
  (no entry slippage) when the bar trades through it.
- The stop/target bracket set at the close of bar *t* is evaluated on bar *t+1*.
- If a bar's range spans **both** stop and target, the **stop** is assumed hit
  first.
- Stop and market exits pay **1 tick** of adverse slippage; target exits pay
  none.
- Exits are not checked on the fill bar itself (no same-bar stop-out).

The stop-first rule in particular penalises a low-win-rate / wide-target
strategy like El Toro. Treat absolute P&L as a **conservative lower bound** and
compare configs **relative to each other**, which is what optimisation needs.

## Results — NQ 1m, 2023-06-18 → 2026-06-17 (this data sample)

Pure signal (`--research`, contracts-only P&L, pessimistic fills):

| preset | trades | win% | PF | expectancy | net (contracts) |
|---|---:|---:|---:|---:|---:|
| EL_TORO (5ct, fixed 122t TP) | 2,628 | 24.2 | 0.90 | −$78 | −$204k |
| EL_DORADO (2ct, R2.5, BE+trail) | 1,193 | 62.4 | 0.92 | −$12 | −$14k |

Apex overlay (native phase):

- **EL_TORO** eval funnel (151 fresh evals, every 5 sessions, 20-session
  horizon): **PASS 29.1%**, BREACH 70.9%, median 3 trades to resolve. A single
  trade that runs to large open profit and reverses blows the *intraday*
  trailing drawdown — El Toro is very sensitive to giving back unrealised P&L.
- **EL_DORADO** PA (continuous, resets on breach): banked **$3,000** across the
  window while suffering **17 breaches** and 0 full 6-payout cycles.

**Honest bottom line for this sample:** as-shipped, neither preset is net
positive on pure signal here, and the account overlays don't rescue them over
these 3 years. That is the starting point for optimisation (next step), not a
verdict on the idea — the fill model is conservative and the parameter defaults
are untuned for this window.
