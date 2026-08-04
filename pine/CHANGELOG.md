# MEX Pine scripts — optimisation changelog

## v6.9.1 — "→ Middleware" route (fan-out seam)

All 8 scripts gain a `→ Middleware (fan-out)` alert route in group *9 · EXECUTION*.
When enabled, `f_sendExec` emits a lean JSON signal
(`{secret, strategy, event, action, symbol, price, order_type, dollar_sl, dollar_tp, qty}`)
instead of baking each account into the alert. The middleware (see `middleware/`) maps
`strategy` → subscribed accounts and rebuilds each account's PMT/PineConnector payload —
so 11+ accounts run from two alerts (GC, ES) plus a config file. New inputs: `mwSecret`,
`mwStrategy` (default per script: ES/GC/NQ). The emitted shape is verified against the
middleware `Signal` model. Set the webhook URL on the TradingView alert itself.

## v6.9.0 — Roll / OpEx / News factory (event-regime filters)

Applied to the **whole fleet** (all 8 scripts). Validated ES/GC edges:
**MEX_EL_LEON** (ES · Eval), **MEX_EL_REY** (ES · Funded),
**MEX_EL_MINERO** (GC · Eval), **MEX_EL_TESORO** (GC · Funded); plus the NQ fleet
**MEX_EL_TORO / MEX_EL_MATADOR / MEX_EL_DORADO / MEX_EL_PATRON** (Auto → `NQ · any`).

**Why.** 3-year OOS analysis showed the mean-reversion engine's losses concentrate
in the **quarterly roll / triple-witching window** — especially on quiet, no-news
days (ES no-news near-roll PF 0.86, −$144k; YM roll-window PF 0.77–0.95) — while
**macro news sits on the profit side** (NFP a tailwind for the index strats, FOMC a
profit day for ES/GC). Unlike fine-grained day×hour cells (which are OOS noise),
these are coarse, mechanism-backed regimes that persist every year.

**What.** A new input group *8b · SIGNAL — Roll / OpEx / News factory* with a
`Preset (strategy · type · phase)` dropdown. `Auto` resolves to the validated
default for that script; you can borrow another strategy/account-type's config, or
pick `Off / Custom` and drive seven individual toggles:
avoid quarterly roll window (± N days), news-override, avoid triple-witching week,
avoid the week after monthly OpEx, block FOMC, block NFP. Calendar math is native
(3rd-Friday resolver for quarterly + monthly expiries, 1st-Friday NFP); FOMC dates
are a hardcoded 2022-2026 table (2026 projected — update yearly). The gate folds
into `canTrade` via `evtGateOK`; master switch `useEvtFilter` disables the whole
block. Preset defaults: ES → avoid roll (news-override) + week-after-OpEx;
GC → no filter (robust across regimes); YM → avoid roll + witching; NQ → block FOMC.

---

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

## v6.8.11 / v6.8.16 — inputs restructured + firm-preset dropdown

- **Inputs menu reorganised** by concern via the GROUP_* labels: `0-1 ACCOUNT`
  (firm & routing / phase & drawdown / funded payouts / eval tracking),
  `2-4 TRADE` (sizing / entry & stop / TP & exits), `5-8 SIGNAL` (FVG / delta /
  VWAP / time gate), `9 EXECUTION`, `10-11 RESEARCH/MONITOR`. Research/Eval/Funded
  account settings now cluster together. (Grouping via labels; physical input
  order unchanged — a deeper reorder is higher-risk and deferred.)
- **Firm-preset dropdown** (`Use firm preset` + `Firm program`) in the ACCOUNT
  group: auto-fills drawdown model, trailing DD, eval goal, daily-loss and
  consistency from the prop-firm registry (inlined `f_firmRules`, generated from
  data/propfirms.json). **Futures/trailing firms only** (Apex, Topstep, MFFU,
  TPT, DayTraders S2F, Tradeify); forex/static firms run in the backtester until
  the static-DD Pine engine is added. Off by default -> zero behaviour change.
  No engine edits: the preset just overrides the existing account variables.

## v6.8.12 / v6.8.17 — alert destinations + borrowed-symbol delta (ALL FOUR)

**Pilot (El Toro v6.8.12) compiled and ran on a live EURUSD chart**, so the two
changes below were propagated verbatim to all four scripts:
Toro/Matador → **v6.8.12**, Dorado/Patron → **v6.8.17**. (Propagation done by an
asserted 8-replacement script so every file is byte-identical in these regions.)

- **Alert destinations added: `PMT Rithmic` and `PineConnector`.**
  - *PMT Rithmic* reuses the existing PickMyTrade JSON payload (`f_pmtJSON`), same
    as Tradovate — the Tradovate/Rithmic split is on the PMT side, not the payload.
    `useRithmic` (previously a dead `= false` stub) now routes it.
  - *PineConnector* emits the MT4/5 comma command
    `{license},{buy|sell|exit},{symbol}[,sl=,tp=,risk=]` — the FTMO/forex bridge.
    New inputs: `PineConnector license ID`, `PineConnector symbol (empty=chart)`,
    `PineConnector risk / lots`. SL/TP absolute prices are reconstructed from the
    call-site price distances. Closes send `exit` (flatten symbol).
  - `plainAlertsOK` / `execInstance` / `alertMsgAuto` updated to include both.
- **Borrow delta from another symbol** (`Borrow delta from symbol`, group 6):
  set e.g. `CME_MINI:6E1!` on a spot-EURUSD chart to drive the delta filter from
  the Euro FX future's REAL volume. Uses `request.security_lower_tf` up/down
  volume (delta = up − down) — an approximation of native CVD, not TradingView's
  exact `ta.requestVolumeDelta`. Empty = chart's own volume (unchanged). When a
  borrow symbol is set, the no-volume auto-guard and the streak both treat the
  chart as if it had real volume (the borrowed futures does).
  - *Correction to the v6.8.9 note:* borrowing another symbol's delta IS possible
    this way. Only the *nested* `request.security(sym, ta.requestVolumeDelta(...))`
    is rejected by Pine — the `request.security_lower_tf` up/down-volume path is not.

> FTMO **static-drawdown account engine** is still deferred (by decision: prove a
> positive-edge config first). PineConnector gives FTMO/EURUSD *execution* now;
> the FTMO *phase/DD rules* in-Pine come after the edge is locked.

## v6.8.13 / v6.8.18 — alert routing as independent toggles (ALL FOUR)

**Pilot (El Toro v6.8.13) compiled clean, so propagated to all four:** Toro/Matador → v6.8.13, Dorado/Patron → v6.8.18.

The single-select **"Alert destination" dropdown is replaced by independent
per-destination on/off toggles**, so all routing config lives in the inputs and
any combination can be enabled:
`→ PMT Tradovate` · `→ PMT Rithmic` · `→ PineConnector (MT4/5)` · `→ Discord` ·
`→ Journal (CSV)`, each with its own params (PMT token, PineConnector
license/symbol/risk, account-id from group 0). `usePMT/useRithmic/
usePineConnector/useDiscord/useJournal` now derive from the toggles; all
downstream emitters, `plainAlertsOK`, `execInstance` and `alertMsgAuto`
unchanged.

Interim by design (config stays in the script): **TradingView still delivers one
alert to one webhook URL and Pine cannot POST to a URL itself**, so for now enable
ONE route per alert and put that route's webhook on the alert. Enabling several
at once is the MIDDLEWARE step (planned): the alert URL points only at the
middleware, which reads the enabled routes and fans out — per-route webhooks then
live in the middleware, keyed by these toggles. No behaviour change when a single
route is on; off by default.

## How to use
Copy the file's contents into the Pine editor and save. Verify it compiles
(this environment cannot compile Pine). Then run your entire-history backtest —
the memory error should be gone. Paste any compile error back for an immediate fix.

## NEW ES scripts — El León (Eval) + El Rey (Funded)

First asset to clear the from-scratch edge bar. **ES has a real, out-of-sample
robust edge** (research PF 1.063; split-half H1 1.107 / H2 1.023 — positive in
both halves), unlike NQ. See LifeOS "📊 Asset-analyse — ES".

Two new scripts, forked from the EOD templates with the ES-validated preset
baked into the defaults:
- **MEX_EL_LEON** (ES · Eval · EOD) — from El Matador. contractSize 1.
- **MEX_EL_REY** (ES · Funded · EOD) — from El Patron. contractSize 1.

ES preset defaults (both): FVG band **9–15** · **Fixed stop 100 ticks** (25 pts) ·
**TP R1.5** · **Delta filter OFF** (edge validated without CVD; this dataset had
no delta) · EOD drawdown · all hours. Same engine as the four NQ scripts
(v6.8.13/18), only input DEFAULTS differ. Eval funnel (Apex 50k): EOD 26.8% /
Intraday 24.0% pass. PF ~1.06 is a thin-but-real edge — size accordingly.

## NEW GC scripts — El Minero (Eval) + El Tesoro (Funded)

**GC (gold) is the strongest edge so far** — pervasive across nearly all 18 swept
configs (research PF up to 1.132; winner FVG6-12 stop100 split-half H1 1.19 /
H2 1.05, positive both halves). See LifeOS "📊 Asset-analyse — GC".

- **MEX_EL_MINERO** (GC · Eval · EOD) — from El Matador. FVG 6-12 · fixed 100t ·
  R1.5 · CVD off · **2 contracts** (2ct lifts eval pass 20%→31.9%; edge supports it).
- **MEX_EL_TESORO** (GC · Funded · EOD) — from El Patron. FVG 6-12 · fixed 100t ·
  R2.5 · CVD off · 1 contract (scale to taste). PF 1.12.

GC tick 0.10, $100/pt ($10/tick); 100t stop = 10 pts = $1,000/contract. Same
engine as the rest; only input defaults differ.
