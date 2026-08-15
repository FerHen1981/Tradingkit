# Backtest Lab — plan (bck.mex-traders.com)

A dedicated backtesting environment, hosted separately from the live CIO cockpit,
that runs every strategy idea through **three lenses** and shows the outcomes in a
cockpit that mirrors the live dashboard's look & feel — but with backtest variables.
No Notion; everything is file-based on the server.

> Live cockpit (`app.mex-traders.com`) answers *"are the live accounts healthy and
> when is a payout ready?"*. The Lab (`bck.mex-traders.com`) answers *"does this idea
> survive the long term, pass the eval reliably, and pay out once funded?"* — **before**
> a script ever joins the fleet.

---

## 1. The three engines (lenses), and how they relate

All three run the **same** engine (`backtest/engine.py`) on the **same** strategy spec.
They differ only in the *account overlay* and the *reporting lens*:

| # | Lens | What it answers | Overlay | Primary output |
|---|------|-----------------|---------|----------------|
| 1 | **Classic (long-term)** | Is there a real edge, after costs, across regimes? | none (research_mode: no account halts) | Per-regime-year PF / MaxDD / expectancy / WFE, Monte-Carlo |
| 2 | **Eval** | How *reliably* does it fund an account? | eval rules (target + trailing/EOD DD) | PASS / BREACH / TIMEOUT distribution over many fresh starts (`funnel.py` + startdag-sweep) |
| 3 | **Funded** | Once funded, what does it actually *pay out* over time? | funded rules (DLL, consistency, min-days, safety-net, split) | Payout cadence & cumulative withdrawable, breach survival, $/month |

Mapping to what already exists:
- **Lens 1** = `Engine(research_mode=True)` + `metrics.kpis` + a per-regime-year wrapper (new, thin).
- **Lens 2** = `funnel.run_funnel` (already produces PASS/BREACH/TIMEOUT) + `sweep.py` (startdag-sweep). **Mostly done.**
- **Lens 3** = the gap. The rules live as data in `firms.py` (`Program`) and the payout math
  lives in `middleware/app/payout_rules.py`; what's missing is an **engine-side funded
  overlay** that walks time, applies DLL + consistency + min-days + safety-net, and emits a
  payout timeline. Also needs the **static-DD (FTMO)** overlay for forex/CFD firms
  (`firms.py` flags `drawdown_type = "static"` but the engine only models trailing today).

---

## 2. The core question: which indicators may be used, and with which values?

This is the governance layer. Proposal: **a Parameter Registry + declarative strategy specs.**

### 2a. Parameter Registry (`backtest/registry.yaml`) — single source of truth
Today the "allowed variables" are implicit in the `Config` dataclass fields, and concrete
values live in hard-coded presets (`EL_TORO`, …). We lift that into one explicit registry that,
per parameter, declares:

```yaml
groups:
  fvg:                       # a price-action "indicator block"
    price_action: true       # PA-only policy can forbid non-PA blocks
    params:
      use_gap_filter:   { type: bool,  default: true }
      gap_min_ticks:    { type: float, default: 9.0,  min: 3,  max: 20, step: 0.5 }
      gap_max_ticks:    { type: float, default: 12.0, min: 6,  max: 30, step: 0.5 }
  swing_stop:
    price_action: true
    params:
      pivot_k:          { type: int,   default: 3, min: 1, max: 8 }
      max_stop_ticks:   { type: float, default: 72, min: 20, max: 160, step: 2 }
  cvd:
    price_action: true       # order-flow = still PA-adjacent; tag as you prefer
    params:
      use_cvd_filter:   { type: bool, default: true }
      cvd_trend_count:  { type: int,  default: 4, min: 1, max: 10 }
  # …vwap_veto, breakeven, trail, tp, sizing, day_exit, mae_guard…
```

The registry mirrors the existing `Config` fields 1:1 but adds **metadata**: type, default,
**allowed range/step or enum**, and a `price_action` tag per group. This is exactly the knob
that answers *"which variables, with which values."*

### 2b. Strategy spec = a validated point in that space (`specs/<name>.yaml`)
A strategy is a declarative file: which indicator groups are ON + their chosen values.
It is **validated against the registry** before any run — out-of-range or unknown params are
rejected. Presets become specs; `Config` is built from the validated spec.

```yaml
name: El_Toro_v7_PAonly
base_asset: NQ
policy: { price_action_only: true, max_active_groups: 6 }   # overfit guardrails
groups: { fvg: {gap_min_ticks: 9, gap_max_ticks: 12}, swing_stop: {pivot_k: 3}, cvd: {cvd_trend_count: 4} }
```

### 2c. Why this ties into the validation pipeline
The registry operationalizes the `strategy-validation-pipeline` skill's rules:
- **"Parameter count justified"** → `policy.max_active_groups` is enforced, not hoped for.
- **"±20% perturbation stays profitable"** → sweeps may only move params **within registry ranges/steps**.
- **"Price-action focused"** → `price_action_only: true` forbids any group tagged `price_action: false`.
- **Pre-registration** → the spec file IS the pre-registered plan; it's hashed into the run id.

**Optimization** (`optimize`/`sweep`) therefore can only explore the registry-bounded grid — you
can't accidentally overfit on a knob that isn't declared, and every value it tries is a legal value.

---

## 3. Data room (big files on the server, no Notion)

```
/data/lab/
  datasets/
    NQ_1m_2019-2025/           # one dir per dataset
      data.csv|.parquet        # big file (tickdata / 1m OHLCV + Delta + CVD, BuyVol/SellVol)
      manifest.json            # symbol, timeframe, date range, source, columns present, rows, sha256
    EURUSD_1m_2018-2025/
    BTCUSD_1m_2020-2025/
  results/
    <run_id>/                  # run_id = hash(spec + dataset + lens + engine_git_sha)
      run.json                 # the full resolved config + provenance
      kpis.json  trades.csv  equity.csv  funnel.csv  payouts.csv
  index.json                   # registry of all runs (the cockpit reads this)
```

- **Ingestion**: `data.py` already accepts `DateTime, OHLC, Volume, Delta` (+ optional
  `CVD_close, BuyVolume, SellVolume`). You just drop a big file + a manifest; a small
  `catalog` step validates columns and computes the manifest.
- **Formats**: CSV works today; add optional **Parquet** for the big multi-year/tick files
  (smaller, faster). Resampling (`data.resample`) already exists for tf changes.
- **No secrets, git-ignored**: `/data/lab/` lives on the VPS only; big files never go in git
  (like `*.db`, `.env` today). Repo carries code + registry + specs; server carries the data.

---

## 4. The cockpit (`bck.mex-traders.com`) — duplicate look & feel

A **separate service on its own port + subdomain** (your DNS: `bck.mex-traders.com`), so a
heavy backtest run can never touch the live viewer. It reuses the live cockpit's theme,
`heatColor`, stat tiles, heatmap/calendar/equity renderers — same visual language, backtest data.

Tabs (mirroring live, re-cut for backtests):
- **Overview** — pick a run (or compare 2); headline KPIs per lens.
- **Long-term** — per-regime-year PF/MaxDD/expectancy, walk-forward efficiency, Monte-Carlo cone.
- **Eval** — PASS/BREACH/TIMEOUT distribution, startdag-sweep, median gross, time-to-pass.
- **Funded** — payout timeline, cumulative withdrawable, $/month, breach survival.
- **Heatmap / Calendar** — reuse existing renderers (day×hour expectancy).
- **Portfolio** — correlation of a candidate vs the existing fleet (<0.7 gate).
- **Data room** — dataset catalog (what's available, ranges, columns).
- **Runs** — the run registry: filter/compare/promote; each row links to its artifacts.
- **Footer** — system status (like live): datasets loaded, last run, engine git-sha.

`/api/*` endpoints read `/data/lab/index.json` + per-run artifacts (stdlib-only, same as viewer).

---

## 5. What we reuse vs build

**Reuse as-is:** `engine.py`, `indicators.py`, `funnel.py`, `sweep.py`, `firms.py`,
`metrics.py`, `heatmap.py`, `data.py`; the live viewer's HTML/CSS/JS theme + components.

**Build (thin, in order):**
1. `registry.yaml` + `spec.py` (load/validate spec → `Config`); lift presets into specs.
2. Data-room catalog step + `manifest.json`/`index.json` writers; Parquet loader option.
3. Run orchestrator: run a spec × dataset × lens → write artifacts + register in `index.json`.
4. Per-regime-year wrapper for Lens 1 (thin over `metrics.kpis`).
5. **Funded overlay** (engine-side payout simulation) + **static-DD (FTMO)** overlay — the real new engine work.
6. `bck_viewer` cockpit (duplicate of `viewer.py`) + its `/api/*`.
7. systemd unit `mex-bck.service` + nginx vhost for `bck.mex-traders.com`.

---

## 6. Open decisions (need your steer)
- **CVD/order-flow classification**: tag the `cvd` group as price-action or as a separate
  "order-flow" class? (Affects what `price_action_only` allows.)
- **Data granularity**: true tick data, or 1-minute bars with CVD/volume? (Tick = much bigger
  files + a tick→bar build step; 1m is what `data.py` ingests today.)
- **Spec format**: YAML (readable, needs a tiny parser) vs JSON (stdlib, less friendly).
- **Promotion path**: when a spec passes all three lenses in the Lab, how does it hand off to
  Pine + the live fleet? (Manual export first; automated later.)
