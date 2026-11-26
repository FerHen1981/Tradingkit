# Prompt voor Pine Dev — El Tesoro v7.9.2 met daily risk-gate

Kopieer dit blok integraal naar de Pine Dev-chat.

---

## Wat er nodig is

Ik heb een nieuwe versie van **El Tesoro v7.9.2** nodig die de bestaande CVD-signaal-
engine intact laat maar er een **daily risk-gate** overheen legt. De risk-gate
staat volledig los van entry/exit-signalen en werkt per handelsdag per Apex-account.
Getallen komen uit een 1-jaar backtest op MGC1! (data-bestand hieronder). Zie
`docs/risk_caps.md` in de repo voor de volledige achtergrond.

## Achtergrond in één alinea

Op de 3.651 trades van El Tesoro over MGC1! van 2025-08-19 tot 2026-08-19
verdampt >90% van de sessies onder de huidige regels (baseline -$89.556 op q6).
Uit backtesting blijkt dat drie ingrepen dat volledig omkeren: (a) alleen entries
in het 18-23 ET venster, (b) een harde intra-trade Daily Loss Limit die vuurt
binnen één trade, en (c) een trail op cum P&L per sessie die alleen op trade-close
kijkt (dus niet op intra-trade tick-noise). De combinatie op q3 met T=$10 / B=$100
/ DLL=$150 overleeft Apex 50K en produceert alle 6 payouts in het jaar. Op q6
met T=$50 / B=$25 / DLL=$500 werkt de regel voor Legacy/100K+ maar blowt Apex 50K
in week 4.

## Deliverable

Een nieuwe file `pine/el_tesoro_v7_9_2.pine` die:

1. De bestaande CVD-signaal-logica van v7.9.x behoudt (entry/exit/short/long,
   FVG-gap detection, CVD-filter). Geen wijzigingen aan de signaal-engine zelf.
2. Bovenop dat een **Daily Risk-Gate** module toevoegt met de mechanismen
   hieronder.
3. Alle nieuwe parameters exposed als Pine `input.*` zodat ik ze in de UI kan
   bijstellen zonder de code aan te raken.
4. Een backtest-overlay die per sessie visueel toont of DLL / trail / natural
   close is opgetreden, én een propfirm-account-overlay die live meerekent of
   Apex 50K in de gekozen variant overleeft.
5. Blijft signaal-genererend naar TradingView-alerts. Wanneer de risk-gate halt,
   moet het alert-payload een `halt=true` veld bevatten zodat `mex-receiver`
   weet dat het geen order moet fan-outten.

## Rule-mechaniek (exact zoals gebouwd, moet 1-op-1 in Pine)

### Sessie-definitie

- Sessie start bij **CME-roll: 18:00 ET** (`America/New_York`).
- `cum_session_pnl` reset naar $0 op 18:00 ET.
- `session_peak` reset naar $0 op 18:00 ET.
- `trail_active` reset naar `false` op 18:00 ET.
- `halt_active` reset naar `false` op 18:00 ET.

### Daily Loss Limit (DLL) — intra-trade hard

- Op elke tick tijdens een open positie: bereken
  `intratrade_pnl = cum_session_pnl_realized + open_position_pnl_current`
- Als `intratrade_pnl ≤ -DLL` → **sluit positie NU** (market-close), `halt_active = true`.
- Geboekt bedrag: exact `-DLL` (niet de werkelijke close-fill; script moet close
  tikken zodra de drempel bereikt wordt).
- Na halt: geen nieuwe entries deze sessie.

### Trail — alleen op trade-close cum

- Na elke gesloten trade, update `cum_session_pnl` met de realized P&L.
- Als `!trail_active` en `cum_session_pnl >= trigger_T`:
  - `trail_active = true`
  - `session_peak = cum_session_pnl`
  - `exit_lvl = session_peak - buffer_B`
- Als `trail_active`:
  - Als `cum_session_pnl > session_peak`: `session_peak = cum_session_pnl`,
    `exit_lvl = session_peak - buffer_B`
  - Als `cum_session_pnl <= exit_lvl`: sluit open positie, `halt_active = true`

### Venster-filter

- Nieuwe entries alleen toegestaan als huidige tijd in [session_window_start,
  session_window_end] (default 18:00-23:59 ET).
- Buiten venster: bestaande positie loopt door (exits mogen nog vuren), maar
  geen nieuwe entries.

## Parameters exposed als Pine inputs

Groepeer in `input.*` calls onder groepen. Alle default-waarden staan hieronder;
gebruiker kan ze in UI aanpassen.

```
// === Risk-gate: master switch ===
input.bool(true,  "Enable daily risk-gate",           group="Risk-Gate")
input.string("Intraday", "Apex account type", options=["Legacy_EOD","Intraday","EOD"], group="Risk-Gate")

// === Risk-gate: parameters (in $, per account, niet per contract) ===
input.float(10.0,  "Trigger T ($)",     minval=0.0,  step=1.0,  group="Risk-Gate Params")
input.float(100.0, "Buffer B ($)",      minval=0.0,  step=1.0,  group="Risk-Gate Params")
input.float(150.0, "DLL ($)",           minval=0.0,  step=10.0, group="Risk-Gate Params")

// === Venster ===
input.int(18, "Session start hour (ET)", minval=0, maxval=23, group="Window")
input.int(23, "Session end hour (ET)",   minval=0, maxval=23, group="Window")

// === Contract sizing ===
input.int(3, "Contracts per trade (q)", minval=1, maxval=10, group="Position")

// === Propfirm engine (backtest overlay) ===
input.bool(true,   "Test against Apex 50K engine",         group="Propfirm Test")
input.float(50000, "Account start balance ($)",            group="Propfirm Test")
input.float(2500,  "Trailing DD ($)",                       group="Propfirm Test")
input.float(50100, "Trailing lock at balance ($)",         group="Propfirm Test")
input.float(52600, "Safety net ($, min balance for payout)", group="Propfirm Test")
```

## Interne fields die het script moet bijhouden (per bar / per tick)

```
var float cum_session_pnl     = 0.0
var float session_peak        = 0.0
var float exit_lvl            = na
var bool  trail_active        = false
var bool  halt_active         = false
var float account_balance     = start_balance
var float trailing_stop       = start_balance - trailing_dd
var int   trading_days_count  = 0
var float total_profit        = 0.0
var float best_day_profit     = 0.0
var int   payout_step         = 0    // 0..6, 6 = wait-for-cap
var float total_payouts       = 0.0
```

Reset bij CME-roll (18:00 ET):
- `cum_session_pnl = 0.0`
- `session_peak = 0.0`
- `exit_lvl = na`
- `trail_active = false`
- `halt_active = false`
- Aan het EIND van elke sessie:
  - Update account_balance (bij Intraday-mode is dit intra-tick geëvalueerd)
  - Update trailing_stop volgens Apex-mode
  - Als balance ≤ trailing_stop → account BLOWN → strategie stopt

## Apex-account-modes (verschil in DLL-enforcement)

De user selecteert één van drie via de `Apex account type` input:

### `Legacy_EOD`
- Trailing DD update alleen op EOD balance (= cum_session_pnl EOD).
- Intraday drawdown telt niet mee voor trailing.
- Balance-check gebeurt op sessie-eind, niet tussentijds.
- Onze DLL van $150 blijft intra-trade hard (dat is onze eigen regel), maar
  Apex zelf halt niet op intra-day dips.

### `Intraday`
- Trailing DD update real-time op laagste intra-sessie punt.
- Als op enig moment tijdens de sessie `account_balance + intraday_lowest ≤ trailing_stop`
  → account BLOWN.
- Onze DLL van $150 firet dan als eerste (voordat trailing wordt geraakt) — dat
  is precies waarom Config A werkt op Intraday.

### `EOD` (nieuwe accounts, geen locked trailing)
- Trailing DD update op EOD balance, geen $50.100 lock.
- Verder gelijk aan Legacy_EOD.

## Payout-ladder implementatie

Elke sessie na de close, check of alle drie voorwaarden waar zijn:

1. `trading_days_count ≥ 8` (dag telt als P&L ≥ $50 die dag)
2. `account_balance > safety_net`
3. `best_day_profit ≤ 0.30 * total_profit`

Als ja én `payout_step < 6`:
- `payout = min(account_balance - safety_net, payout_max[payout_step])`
- `payout_max = [2000, 2000, 2000, 2500, 2500, inf]`
- `total_payouts += payout`
- `account_balance -= payout`
- `payout_step += 1`
- Reset payout-counters: trading_days_count=0, total_profit=0, best_day_profit=0

## Backtest-overlay (Pine plot output)

- Marker onder de bar op elke halt-sessie:
  - Rood cirkel = DLL-halt
  - Oranje driehoek = trail-halt
  - Groene ster = natural close (payout-eligible dag)
- Label bij elke payout met bedrag en step-nummer.
- Table in top-right hoek met live-stats:
  - Account balance
  - Trailing stop
  - Payout step
  - Total payouts
  - # halts vandaag / cumulatief
  - Status: OK / HALTED / BLOWN
- Statistiek in strategy.performance-output aan het eind van backtest:
  - Aantal sessies overleefd
  - # SL-halts, # trail-halts, # natural closes
  - Total profit, total payouts
  - Overleeft account? Ja/Nee
  - Bij Nee: datum van blowout

## Alert-payload (voor `mex-receiver` fan-out)

Bestaande alerts moeten worden uitgebreid met risk-gate-status fields. JSON-payload
in `alert_message`:

```json
{
  "strategy": "El_Tesoro_v7.9.2",
  "asset": "{{ticker}}",
  "action": "{{strategy.order.action}}",
  "contracts": {{position_size}},
  "price": {{close}},
  "halt_active": {{halt_active}},
  "halt_reason": "{{halt_reason}}",  // "DLL" / "trail" / ""
  "session_cum_pnl": {{cum_session_pnl}},
  "trail_active": {{trail_active}},
  "account_type": "{{account_type}}"
}
```

Fan-out-logica in `mex-receiver` moet:
- Als `halt_active=true` in het alert: geen order verzenden naar accounts die
  al gehalt zijn deze sessie.
- Als `halt_active=false`: normale fan-out volgens `accounts.yaml`.
- Halt-status per account per sessie tracken (reset op 18:00 ET).

## Test-parameters uit de backtest

**Data-bestand voor validatie:**
`T_SORO_COMEX_MINI_MGC1_20260819_e5951.xlsx` (op mijn machine)
- 3.651 trades, 254 sessies, 53 weken
- MGC1! op Comex Mini Gold, 1 point = $10 per contract
- Native q6 (kan gescaald worden naar q1-q6 in backtest)

**Config A validatie (default settings, moet reproduceerbaar zijn):**
```
Enable daily risk-gate: true
Apex account type:       Intraday
Trigger T:               10
Buffer B:                100
DLL:                     150
Session start:           18
Session end:             23
Contracts per trade:     3
Test against Apex 50K:   true
```

Verwachte backtest-uitkomst (op MGC1! trade-set 2025-08-19 → 2026-08-19):
- **Overleeft Apex 50K**: JA
- **Eindbalance**: ~$56.894
- **Payouts**: 6/6 stappen, totaal ~$12.810
- **# SL-halts**: ~87 (33% van sessies)
- **# trail-halts**: ~73 (28%)
- **# natural closes**: ~91 (35%)
- **Diepste cum-punt**: ~-$1.183 in week 9

**Config B validatie (agressief, voor Legacy EOD only):**
```
Apex account type:       Legacy_EOD
Trigger T:               50
Buffer B:                25
DLL:                     500
Contracts per trade:     6
```

Verwachte backtest-uitkomst:
- **Overleeft Apex 50K Intraday**: **NEE, BLOWN op ~week 4**
- **Overleeft Apex 100K+ (trailing $3.000+)**: JA
- Op 50K Legacy: **BLOWN** (drawdown-diepte -$3.264 > trailing $2.500)

## Verifieerbare uitkomsten

Als jouw v7.9.2 backtest op mijn data ongeveer deze cijfers oplevert (marge <5%),
weten we dat de risk-gate correct geïmplementeerd is. Als er grote afwijking is,
zit er een implementatieverschil (waarschijnlijk in intra-trade DLL-timing of
sessie-reset moment).

## Prioriteit

**Hoog.** 6 live funded accounts wachten op deze gate. Op dit moment draaien ze
zonder risk-gate, wat betekent dat één slechte week het account kan blowen. De
huidige mediaan-verlies-per-week op q6 zonder gate is -$1.690 — dat verdampt de
buffer razendsnel.

## Vragen die je waarschijnlijk hebt

**"Wat als de tick niet exact op de DLL landt?"**
Sluit op de eerste tick waarbij `cum + open_pnl ≤ -DLL`. Pine's `strategy.close_all()`
in een intra-bar branch werkt. Als slip optreedt door bar-close aggregatie: dat
is aanvaardbaar (het is nog steeds beter dan geen intra-bar sluiten), maar
documenteer het als bekende slip.

**"Moet trail ook intra-bar vuren?"**
Nee, expliciet niet. Trail werkt UITSLUITEND op trade-close cum. Dat is het hele
punt van de ontkoppeling: intra-trade noise mag niet aan de trail zitten.

**"Moet ik de CVD-filter aan laten?"**
Ja, CVD-filter altijd aan. Zie project rule in `CLAUDE.md`. De backtest hierboven
draaide op CVD-loze export dus is een ondergrens; live met CVD zou beter moeten
zijn.

**"Wat als er meerdere strategie-instances op één account draaien?"**
Dat gebeurt niet in de huidige setup — 1 strategy per account op MGC. Maar goede
vraag voor later; DLL zou dan cross-strategy moeten aggregeren, en dat hoort in
`mex-receiver`, niet in Pine. Voor v7.9.2: 1-op-1 aanname.

**"Waarom de $10 trigger zo laag?"**
Bimodale pullback-analyse liet zien dat pullback na peak ofwel $0-$10 (59%) of
$500+ (35%) is. Kleine trigger ($10) vangt vrijwel elke echte trend zonder op
noise-pieken te firen. Buffer $100 laat post-peak dumps door de drempel gaan
zodat de winst locked wordt.

## Wat ik terug wil zien

1. `pine/el_tesoro_v7_9_2.pine` — nieuwe Pine-file
2. Screenshots of screencap van de backtest op MGC1! met beide configs
3. Confirmatie dat de exposed inputs allemaal werken via de TradingView UI
4. Confirmatie dat het alert-payload de halt-fields bevat
5. Bij afwijkingen >5% van bovenstaande verwachtingen: analyse waarom

---

*Einde prompt voor Pine Dev.*
