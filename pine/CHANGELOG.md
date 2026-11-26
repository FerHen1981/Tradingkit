## MEX_EL_TESORO v7.10.0 — engine profile (bevroren onderzoeksparameters)

## 2026-08-25 — D-42: de v1_0_0-vloot vervangt `pine/**`

De acht v6.9.5-scripts zijn naar `pine/history/` gegaan; `MEX_EL_TESORO.pine` is
gearchiveerd als `MEX_EL_TESORO.v7.10.0.bak` (de back-up die bij de keuze bedongen is —
onder het versienummer dat er werkelijk in stond, niet de v7.9.5 uit de besluittekst).
De dertien actieve scripts staan op **v2.3.0**.

**D-45 en D-46 blijven ingetrokken** als resultaat — dat was de voorwaarde bij deze keuze.
Het *mechanisme* van D-45 (daily risk-gate, DLL + trail op gerealiseerde sessie-P&L) zit
sinds 25-08 wél in alle dertien scripts, default UIT, op los verzoek van Ferry via
`INPUT_SPEC_v2.md`. Dat is een nieuwe uitrol, geen herleving van de meting: de cijfers van
D-45/D-46 blijven vervallen.

**De verhuizing is af (25-08, akkoord Ferry).** De negen bestanden staan nu in `pine/`,
naast de vier EL TORO's — dertien scripts in één map, geen `v1_0_0/`-submap meer. Het was een
zuivere hernoeming: 0 regels toegevoegd, 0 verwijderd.

De pariteitspoort van Backtest Setup hing aan een hard-gecodeerd `PINE_DIR = pine/v1_0_0` met
een `skipif` op een lege glob. Die is eerst meebewogen — `PINE_DIR` zoekt nu beide locaties,
de EL TORO-scripts worden gefilterd omdat ze geen mirror in `fleet.py` hebben, en er staat een
test bij die niet geskipt kan worden. Vóór de verhuizing 50 passed, ná de verhuizing 50 passed.


Nieuwe groep **`0B · ENGINE PROFILE`**. Een dropdown zet de bevroren signaal- en
exitparameters van een gevalideerde engine, in plaats van dat elke engine een eigen
bestand met bijna dezelfde code krijgt. Eerste profiel: **`TES-MGC-C`** (EL TESORO,
MGC Conservative EOD) — 7 MGC, FVG 11–16, CVD-streak 6, fixed stop 140t, 2,25R,
BE en trail uit. Bron: `frozen-engines.md`.

Waarom zo, en niet als nieuwe defaults:

- **Default is `Manual`**, dus een bestaande chart doet exact wat hij gisteren deed.
  De D-45/D-46-defaults van dit bestand blijven ongemoeid.
- Het profiel raakt **alleen signaal en exit**. De daily risk-gate (groep 1F) en de
  accountregels uit `data/propfirms.json` staan er los van en blijven gelden — dat is
  precies wat optie 3 van inbox 10 vraagt: accountmechaniek op een bevroren engine
  leggen zonder de signaalarchitectuur aan te raken.
- **Max Stop Distance volgt de Fixed Stop.** In `Fixed (legacy)`-modus is
  `sigStopDist` per definitie gelijk aan de fixed stop; staat het filter lager, dan
  wordt élk signaal weggefilterd en handelt het script niet meer. Met een profiel van
  140t en het oude filter van 130t was dat gebeurd. Het profiel zet ze daarom gelijk,
  wat geen nieuwe vrije parameter introduceert.
- **Instrumentbescherming** zoals bij de MEX-preset: `engInstrOK` voedt `canTrade`,
  dus een MGC-profiel op een andere root handelt niet in plaats van stilletjes tien
  keer zoveel dollarrisico te nemen.
- De **CFG-regel en het dashboard tonen nu de effectieve waarden**, niet de rauwe
  inputs, plus `eng=<profiel>`. Anders logt het journaal een configuratie die niet
  gedraaid heeft.

Onafhankelijke bevestiging: elk bevroren profiel heeft BE en trail uit — dezelfde
uitkomst als D-46 op de validatieset, langs een andere weg gevonden.

**Nog open:** `frozen-engines.md` noemt bij TESORO ook *Liquidity Core*. Die feature
zit niet in dit bestand en is niet uit een parametertabel af te leiden; die wacht op
het `v1_0_0`-bestand zelf.

# MEX Pine scripts — optimisation changelog

## v7.7.3-MGC-PA — the dashboard says which layer is steering

With a Fleet Matrix preset active, eight controls in the panel stop doing anything and nothing on
screen says so. That is what "the Fleet gets in the way" means: you change a number and the chart
ignores you.

What a preset takes over, in full:

| Setting | Replaced by |
|---|---|
| Fixed Qty | `polQty` |
| Max Stop Distance | `polMaxStopT` |
| Day-cap hard target | `polCapUSD` |
| Day-trail | **switched off entirely** |
| Account Phase | `polPhase` |
| Firm program | `polFirmKey` |
| Instrument | guarded against the preset's own contract |
| Trading at all | blocked while the preset is parked |

The Minimal dashboard gains a **Sturing** row on the bottom line, in gold when a preset governs and
in normal text on Manual:

```
Sturing    PA013 · MGC q3 · cap $750 · q3 · stop 130t · cap $750
Sturing    Manual · q8 · stop 100t · Day-trail (keep peak)
```

The preset tooltip now lists what it takes over instead of describing it as "pins some values".

Reading the chart of 18 August: it was running on **Manual** — 6 contracts entered where PA013 would
have given 3, and an exit labelled `Day-trail`, which a preset makes impossible. The 6 is `Fixed Qty`
8 trimmed to 6 by the MAE guard, which is exactly the $300 risk shown on the trade label.

## v7.7.2-MGC-PA — the instrument guard now matches the contract, not the family

Symptom: the script compiled, drew its signals and painted the gate background, and took **zero
trades**. The chart was `GC1!` — the full 100-ounce gold contract — while every preset is sized for
`MGC`, the 10-ounce micro.

The MAE guard was right to refuse. With a 100-tick stop:

| | GC1! ($100/point) | MGC1! ($10/point) |
|---|---|---|
| Risk per contract | **$1,000** | $100 |
| MAE allowance | $675 | $675 |
| `maeQtyMax` | **0** — blocked | 6 |
| Risk at q3 | $3,000 | $300 |

One full contract already breaches the Apex 30% negative-P&L rule, so not a single signal could pass.
The engine behaved correctly; nothing was broken.

**What was wrong is that it happened silently.** `polInstrOK` compared *families*: a `GC` preset
accepted both `GC` and `MGC`. But a preset pins a quantity, and quantity only means something
against one contract spec — the same q3 is $300 of risk on the micro and $3,000 on the full size.
The guard now matches the exact root, the presets carry `MGC` instead of `GC`, and the warning label
says which contract the preset expects and which one the chart is showing.

Running the same preset on the wrong contract is now refused loudly instead of dying quietly in the
MAE guard.

## v7.7.1-MGC-PA — compile fix: generated branch chain opened with `else if`

`f_firmLadder` came out as:

```
    float[] _l = array.from(...)
    else if _p == "apex_50k_eod_pa"
```

Only three of the twelve programs carry a payout ladder — the Apex PA variants — but the generator
chose `if` versus `else if` from the **loop index** instead of from how many branches it had
actually written. The first nine programs emitted nothing, so the first real branch inherited
`else if` and Pine rejected it with `Syntax error at input "new line"`.

Both `f_firmMinPayout` and `f_firmLadder` now count emitted branches. Verified across all eight
scripts: every generated chain opens with `if` and continues with `else if`, and that check is now
part of the static pass so this class of error cannot come back silently.

## v7.7-MGC-PA — TESORO: one account choice, and the last fixed values

**156 → 85 inputs** since the live v7.3.

### The MEX preset now names the firm program

There were two layers describing the same account and they knew nothing about each other: the Fleet
Matrix preset in group 0 set quantity, max stop, day cap and phase, while a separate *Use firm
preset* checkbox in group 1 gated a dropdown that did nothing until you ticked it. That dropdown
read as missing, which is fair — an inert control is an absent control.

`f_pol()` now returns the firm program alongside the rest, so **PA013 also means
`apex_intraday_pa`**. The checkbox is gone; the dropdown applies only when the preset is set to
Manual. One choice covers the account.

What the firm program drives is deliberately narrow — **only rules that are the firm's own**:
consistency percentage, minimum payout and the payout ladder. Drawdown model, trailing drawdown and
daily loss stay manual, because this account genuinely deviates: it runs a **$473 daily loss limit**
against the program's $1,000. Auto-filling those would have quietly overwritten a live risk setting.

Picking `apex_legacy_pa` now actually changes something: consistency drops from 50% to 30%, which is
the Apex rule for accounts bought before March 2026.

### Ladder and minimum payout from the registry

`f_ladderCap` hardcoded `[1500, 1500, 2000, 2500, 2500, 3000]`. Both now come from
`data/propfirms.json` through the generator.

> A bug surfaced while wiring this and is worth recording: the generator picked the **first** row of
> a program's size table, and since Apex now carries seven sizes starting at 25K, every payout cap
> came out **halved** — 750 instead of 1500. It now matches the tier to the program's own account
> size. Caught by reading the generated output rather than trusting it.

### Remaining fixed values

Twenty inputs become constants at the value they already carried: the MAE percentages, payout
buffer, last-payout anchor, the distance unit and ATR length, fractional-qty, the delta timeframe
and borrow symbol, the seven custom event toggles, start balance, journal account name and bot name.
`evalTrailEod` now follows the drawdown model instead of being its own switch.

## v7.6-MGC-PA — TESORO: strategy properties pinned in code

Three backtest properties are now set in the `strategy()` call instead of being left to whatever the
chart happens to carry:

- **`use_bar_magnifier=true`** — it was never set, so it defaulted off. The version history is
  explicit that the magnifier is required for exits, and that running on realtime ticks without it
  produced a −$12,770 artefact. The exit engine now reads intrabar detail rather than inferring it
  from the one-minute close.
- **`calc_on_order_fills=true`** — made explicit. This reproduces the run that produced the clean
  v7.3 ↔ v7.5 comparison.
- **`calc_on_every_tick=false`** — unchanged, but worth naming: this is "on realtime" and it stays
  off.

Why it matters beyond tidiness: the day cap fires on `riskDayPeak`, which counts open profit. How
often the strategy recalculates therefore decides *when* the cap trips. In the two exports of 17
August that single difference moved one exit from 22:34 to 22:36, changed its result by $20 and let
one extra trade through. Pinning the properties in code makes a fresh chart load deterministic.

## v7.5-MGC-PA — TESORO: the live v7.3 with the repo's four cleanups on top

The live MGC script was developed outside the repository, so the repo's v6.9.x line for TESORO was
never what ran on the chart. v7.3 is now the base, and the four repo steps are re-applied to it.
**156 → 108 inputs, 1,829 → 1,694 lines.**

Everything v7.3 brought is untouched: the fourteen brand-palette tokens, the eighteen glyphs with
their `useEmoji` switch, the Fleet Matrix policy layer with its four account presets and the
instrument-family guard, all three dashboard layouts with Minimal as default, and the MGC tuning
(0.67 cash commission, slippage 1, `max_bars_back` 500, `import TradingView/ta/8`).

Re-applied on top:

1. **Retired features removed** — the same 36 flags and their inert paths, −131 lines. All 32
   anchors matched v7.3 unchanged, so this transferred one-to-one.
2. **Firm registry generated in** — the inline `f_firmRules` goes from 8 stale presets to 12 from
   `data/propfirms.json`, and the default moves from `apex_50k_eod_eval` to `apex_50k_eod_pa`,
   which is what this script actually is.
3. **Display layer collapsed** — fifteen inputs to two, with the fixed colours taken from the brand
   palette (`#5AA2FF`, `#E0796E`, `#F2EBDA`), not the old green/red. The tokens themselves are
   declared further down the file, so the literals are used here.
4. **Time gate to session strings** — 36 fields to two. The default is
   `0000-1700,1800-2400:23456`, because v7.3 has hour 17 switched off. That hour sits inside the
   16:55–18:00 flat window anyway, so it is belt and braces — but the comma range keeps the intent
   explicit rather than relying on the flat window staying where it is.

**Check in the editor:** whether `input.session` accepts the comma form in its widget. If it does
not, the fallback is `0000-2400:23456`, which behaves identically as long as the flat window covers
17:00–18:00.

The other seven scripts stay on v6.9.5 until their own live versions arrive. The fleet is split, on
purpose and visibly.

## v6.9.5 — Input rework, step 2: the time gate

Thirty-six fields become two session strings. **140 → 106** on the funded scripts, **128 → 94** on
the eval scripts.

Out: seven weekday toggles, **twenty-four hourly toggles**, the Force Flat Window switch and its
four hour/minute fields. In:

- **Trading window (days + hours)** — `0000-2400:23456`. Hours before the colon, days after, where
  1 is Sunday and 7 is Saturday. Comma-separated ranges work, so `0000-0600,1200-1800:23456` still
  expresses a split day; the hourly toggles were only ever used to carve one out.
- **Force-flat window** — `1655-1800:1234567`. Empty switches it off, which is what the old
  `useAutoFlat` toggle did.

The gate now reads `not na(time(timeframe.period, tradingSession, activeTz))` instead of a weekday
function plus a 24-slot array lookup. `f_isTradingDay()`, `hourEnabled`, `f_inRangeMOD` and
`f_toMOD` are gone with them; `tradeDOW` and `f_minuteOfDay()` stay for the Monday-open filter,
which is day-specific and does not belong in a session string.

**Defaults reproduce the fleet's live configuration exactly** — Mon-Fri, all twenty-four hours
enabled, flat from 16:55 to 18:00. Checked against the strategy-tester export of 17 August: every
weekday toggle and all four visible hour blocks were on, so nothing expressible is lost.

**The one thing that is lost:** a chart that had individual hours switched off will not carry that
over. Nothing in the fleet did.

## v6.9.4 — Input rework, step 1: the display layer

Fifteen inputs out of the settings panel, no drawing code touched. **154 → 140** on the funded
scripts, **142 → 128** on the eval scripts.

> Correction: this entry first said 134 → 120. The counter behind it matched one declaration per
> line, and the twenty-four hourly toggles sit several to a line, so it under-counted by twenty.

The eight separate visibility toggles (signals, SL/TP levels, pending limit, unfilled-limit boxes,
exit labels, trade info, trade zones, gate background) collapse into one **Chart visuals** switch,
and the FVG boxes plus their tested-recolor into **FVG boxes**. Both default on, as all ten did.

Gone as inputs, now fixed at the value they always carried: gate background transparency (90), the
FVG box limit (40), and the bull / bear / tested fill colors.

Also removed: `notifyRegime`, an input with nothing left to fire it since the regime engine went in
v6.9.2, and the `notifyDerisk` alias, which lost its only reader in the same release.

**How it is done matters for the risk.** The old names survive as plain assignments driven by the
two new switches, so every `plot`, `box`, `label` and `table` call below reads exactly what it read
before. One axis changed — the settings panel — and the rendering code is untouched. The
indentation histogram is byte-identical to v6.9.3.

**One consequence to know about:** if a chart had any of the removed toggles switched off, that
saved value is gone and the layer now follows the master switch. Removing an input always does
that; there were ten of them and they were all on.

Kept on purpose: `drawLast` (the memory guard), `showDashboard`, `dashPos`, `visTheme`, `txtSize`
and `dashLayout` — that last one because the fleet actually runs the Minimal layout, not only Wide.

## v6.9.3 — Firm registry reaches the scripts

`tools/gen_pine_firms.py` claimed to keep "the Python backtester and the Pine scripts" in sync, but
it only wrote `pine/lib/PropFirms.pine` — and the strategies never import that library, because a
Pine library must be published on TradingView first. Each script carried its own inline
`f_firmRules()` instead, frozen at **8 presets** while the registry had grown to **18**.

The generator now also rewrites two regions in every strategy file: the **Firm program** dropdown
and the inline `f_firmRules()` body. Running it is idempotent.

**What changes in the scripts.** The dropdown goes from 8 to **12 presets** — every futures program
with a trailing drawdown, which is what a futures strategy can actually be run against. New:
`apex_legacy_pa`, `apex_intraday_pa`, `mffu_starter_50k`, `mffu_builder_50k`. All eight existing
keys stay, so a saved chart setting keeps resolving.

**Corrections that finally reach Pine.** The registry values fixed earlier today were stranded in
the JSON: Apex's 75K drawdown (2,750, previously absent), the 75K target (4,500, was 4,250) and the
300K target (18,000, was 20,000).

**Per-script defaults.** All eight opened on `apex_50k_eod_eval`, including the four funded scripts
and the two intraday ones — switch the preset on and it rewrote a funded account's rules to an
eval account's. Each script now opens on the program matching its own phase and drawdown model:
TESORO/REY/PATRON → `apex_50k_eod_pa`, DORADO → `apex_intraday_pa`, MINERO/LEON/MATADOR →
`apex_50k_eod_eval`, TORO → `apex_50k_intraday_eval`.

Inert until `Use firm preset` is switched on — it defaults off, and no trading logic changed.
Statically verified per file: 12 branches in the generated function, the default present in its own
option list, brackets balanced, no tabs, no new indentation deviations.

## v6.9.2 — Retired-feature cleanup

Removes the v6.8 leftovers. The inputs were taken out back then, but the constants and the engine
paths behind them stayed in every script — 36 flags pinned to a constant and roughly 137 lines per
file that could never execute.

Gone from all 8 scripts: the **OR-breakout** session tracker, the **PA context filters**
(relative volume, BBWP, RTH-open block), the **regime indicator** (efficiency-ratio classifier plus
its Discord notifications), the **derisk ladder** (both the eval and the PA variant), the
**goal-TP** clamp in `f_tpFixDist`, the **PA-threshold** notification, the DD guards
(`guardEval`/`guardPA`), `gateOpenOnRiskOff`, `startNeedRegime`, `exitPreset` and the retired
`GROUP_DAY` constant. **1,096 lines removed across the fleet**, exactly 137 per file.

**No behaviour change.** Every removed path was gated on a constant that was already `false`, and
the two constants that were `true` (`gateOpenOnRiskOff`, `orOneSetup`) were folded into the
expressions that read them. Three things were deliberately preserved:

- `useRegime` and `regimeFav` stay, because `f_journal()` writes a regime column — removing them
  would change the CSV schema the journal pipeline and Notion consume.
- The `|CFG|` alert payload is byte-identical: `goalTp`, `derisk` and `deriskPA` now emit the fixed
  `0` / `off` / `off` that the dynamic expressions always produced.
- The dashboard still renders `Regime —` in the same cells; only the dead branches are gone.

`notifyRegime` and `notifyDerisk` remain as inputs with nothing left to trigger them. Removing an
input changes the settings panel and the saved chart settings, so that belongs with the v7 input
rework, not here.

**Verified statically, not compiled.** This environment cannot compile Pine. Checked per file: no
reference to any of the 69 removed names survives, the required symbols are all still present,
brackets balance, no tabs, no new indentation deviations against the previous version, and the
pairwise differences between the eight scripts are unchanged (TESORO 10, PATRON 26, DORADO 30,
LEON 108, MINERO 110, MATADOR 124, TORO 146 changed lines versus REY — identical to v6.9.1).
**Paste one script into the editor and confirm it compiles before this goes on a chart.**

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
