# Prompt voor Pine Dev — El Toro v7 · defaults, time-gate presets, cleanup

Kopieer dit blok integraal naar de Pine Dev-chat. **Prio: P1.**

---

## Wat er nodig is

De huidige El Toro (**`pine/MEX_EL_TORO.pine`**, v6.9.1, 1.725 regels) is functioneel maar
draagt veel legacy-inputs mee die inert zijn, en de defaults staan niet op de config
waarmee we net de beste 12-maands eval-resultaten hebben gedraaid. Ik wil een **v7.0**
die drie dingen tegelijk doet:

1. **Bewezen backtest-config als default** — de winnende run van 20-08-2026 op NQ1! (12 mnd
   backtest, netto +$109.726, 52% eval-pass rate, 37% one-shot passes) moet 1-op-1 als
   default in het script komen.
2. **Hardcoded tijdslot-presets** — uit de per-(dow, hour) analyse hebben we een lijst
   van 11 GO-slots (pass rate ≥ 65%, samplemaat ≥ 20 evals) en een lijst SKIP-slots
   (pass rate ≤ 35%). Deze presets moeten selectable in het script zitten, niet meer
   manueel per uur aan/uit gezet worden.
3. **Cleanup** — alle inputs, code-paths en visuals die "dood" zijn moeten eruit. De
   script-file moet substantieel korter, sneller compileren, en de input-panel voor de
   trader moet alleen nog de essentie tonen.

## Doel van El Toro (unchanged)

Uitsluitend evals passeren op Apex 50K. Geen funded-gebruik. One-shot-or-fail is
het gebruikspatroon: eerste trade wint groot → PASS in <1 uur, anders trailing DD →
FAIL en nieuwe eval starten.

## Bewezen backtest-config = nieuwe defaults

Deze waarden komen 1-op-1 uit de winnende Properties-export
(`_L_TORO_CME_MINI_NQ1_20260820_d35bd.xlsx`). Zet elke input hieronder als **default**;
de trader mag ze nog wél zien en tweaken, maar hoeft niks meer aan te passen om
de bewezen config te draaien.

### Trade — position sizing
| Input | Default |
|---|---|
| Sizing Mode | Fixed contracts |
| Fixed Qty | **5** |
| Max Qty Cap | 100 |

### Trade — Entry & stop
| Input | Default |
|---|---|
| Entry Mode | Limit @ 50% FVG |
| Limit Order Expiry (bars) | 12 |
| Stop Mode | Fixed (legacy) |
| Fixed Stop (units, legacy mode) | **75** |
| Max Stop Distance (units) | **80** |
| Pivot Strength | 3 |
| Stop Buffer beyond swing (units) | 2 |
| Distance Unit | Ticks |
| ATR Length | 14 |

### Trade — Take-profit & exits
| Input | Default |
|---|---|
| Take-Profit Mode | **Fixed (units)** |
| Take Profit (units, Fixed mode) | **122** |
| R-Multiple (R-multiple mode) | 2,5 (input blijft, niet actief bij Fixed) |
| Enable Break-even | **Off** |
| BE Trigger MFE (units) | 20 (inert bij Off) |
| BE Offset (units) | 8 (inert bij Off) |
| Enable Trailing | **Off** |
| Trail Activation MFE (units) | 70 (inert bij Off) |
| Trail Buffer (units) | 60 (inert bij Off) |
| Recovery trail on trade #2 after loss (Eval) | **On** |
| Recovery trail activation (units) | 40 |
| Recovery trail buffer (units) | 16 |

### Account — Phase, drawdown & guard
| Input | Default |
|---|---|
| Firm program | **apex_50k_eod_eval** |
| Drawdown Model | Intraday |
| Trailing Drawdown ($) | 2.500 |
| Eval Profit Goal ($) | 3.000 |
| Close all when eval passes intra-trade | **On** |
| Lock cost buffer (ticks) | 4 |

### FVG signal
| Input | Default |
|---|---|
| Use FVG Size Range Filter | **On** |
| Min FVG Size (units) | **3** |
| Max FVG Size (units) | **9** |
| Confirmation window (bars) | **1** |
| FVG fill check (gap invalid once mid touched) | On |
| Max FVG Boxes (visual) | 40 |

### Bias / VWAP / CVD
| Input | Default |
|---|---|
| VWAP side veto | **On** |
| Use Delta Filter | **Off** (per project-rule blijft de input aanwezig maar off als default op NQ eval-config) |
| Streak | On, Count = 1 |

### Time gate — **NIEUW GEDRAG**

Vervang de huidige "24 hour toggles + 5 day toggles" door één **PRESET SELECTOR**
input met de volgende opties:

```
Preset = "GO slots only" (default)     ← 11 hardcoded (dow, hour) slots
Preset = "GO + neutral (55%+)"         ← ~30 slots, ruimere config voor volume
Preset = "All hours (baseline)"        ← alles behalve SKIP-slots (58 slots)
Preset = "Manual (legacy)"             ← toont de oude 24×5 toggles
```

De **hardcoded slot-lijsten** (weekday in ET-tijd, `America/New_York`) zijn:

**GO slots — top 11 (pass rate ≥ 65%, sample ≥ 20 evals):**
```
Mon  09, 22
Tue  06
Wed  01, 14, 22
Thu  20, 22
Fri  00, 03, 09
```

**GO + neutral (55%+) — voegt toe aan bovenstaande:**
```
Mon  11, 18, 23
Tue  00, 02, 08, 09, 10, 13, 19, 23
Wed  00, 07, 08, 15, 20
Thu  00, 08, 11, 20, 23
Fri  05, 06, 08, 12, 15, 16
```

**SKIP slots — altijd geblokkeerd, ook in "All hours" preset (pass rate ≤ 35%):**
```
Mon  15, 20
Tue  04, 18
Wed  03, 04, 16, 18, 19, 21
Thu  21, 23
Fri  07, 13
```

**Force Flat Window** (17:00-18:00 ET) blijft als aparte hard block. Vrijdag na 17:00
tot Ma-open blijft ook block.

Deze presets moeten als **constants aan de top van het script** staan, niet in de
input-panel. Een gebruiker kiest alleen de preset-naam via een dropdown.

### Routing (unchanged defaults)
| Input | Default |
|---|---|
| → PMT Tradovate | On |
| → Discord | On |
| → Journal (CSV) | On |
| → PMT Rithmic | Off |
| → PineConnector | Off |
| Bot Name | MΞX ΞL TORO |
| Send CONFIG message on first live bar | On |
| Append full parameter config (`|CFG|`) | On |
| Alert: signal blocked by non-strategy rule | On |

## Cleanup — dit mag ERUIT

De huidige file heeft veel legacy die inert is. Verwijder codeblokken + inputs die
onder deze noemers vallen:

1. **`GROUP_DAY = "L4x · retired"`** — deze hele group is dead code. Weg.
2. **`usePaFilters`, `useRelVolFilter`, `useBbwpFilter`** — hard-disabled booleans
   die nergens aan zijn gekoppeld. Weg met alle bijbehorende gate-branches.
3. **Alle 24 hour-toggles + 5 day-toggles als losse inputs.** Vervang door de
   preset-selector (zie boven). Behoud alleen "Manual (legacy)"-branch voor wie
   dat wil.
4. **`Notify: regime-shift`** — staat op Off, wordt niet gebruikt. Weg.
5. **`Eval tracking on (NOT together with group 4b)`** — staat op Off, "group 4b"
   bestaat niet meer. Weg.
6. **`No entries before start date` + `Start date/time` + `Use end date` + `End date/time`**
   — research-only inputs. Als je ze wil behouden voor de `L4x · retired` gebruikers,
   verplaats ze naar een aparte "Research (dev only)" collapse-groep die default
   gecollapsed is.
7. **`Live sync: current account PnL vs start` + `Live sync: current HWM vs start`**
   — deprecated, wordt niet meer gebruikt met de nieuwe fan-out logica.
8. **`MEX preset (Fleet Matrix v1.1)`** — momenteel op "Manual"; als deze preset-flow
   niet meer gebruikt wordt kan de hele MEX-preset-dropdown eruit.
9. **`Use firm preset`** — als de "apex_50k_eod_eval" preset default is en niks anders
   ondersteund wordt op eval-configs, kan deze toggle weg (of blijft on-only).
10. **Visuals-inputs die geen echt visueel voordeel geven** — check zelf welke:
    `Gate bg transp.`, `Gate background`, `Trade zones (SL/TP fill)`,
    `Trade info next to zone`, `Mark Tested FVGs`, `Trade info next to zone`.
    Wat een backtester nooit nodig heeft: uit, of achter een "Show research overlays"
    single toggle stoppen.
11. **Dashboard layout `Compact (mobile)`** is de enige die gebruikt wordt — verwijder
    de andere layout-opties tenzij daar een reden voor is.

## Efficiëntie-asks — technisch

1. **Verkort de file substantieel.** Doel: van 1.725 regels naar < 900 regels
   (of leg uit waarom niet). Waarschijnlijk zit veel volume in dood-legacy plus
   uitgeschreven visual-branches die na cleanup kort worden.
2. **Verwijder `var` boxes en labels die alleen voor "Research" visuals dienen.**
   Pine-max is 500 boxes/labels; op eval-only gebruik heeft de trader die visuals
   niet nodig — dashboard + entry/exit-markers zijn genoeg.
3. **`max_bars_back=500` blijft** — daar is een reden voor (session boundary).
   Maar check of we het niet nog lager kunnen zetten voor sneller herladen.
4. **`calc_on_every_tick=false`** blijft. Verifieer dat nergens tick-check
   nodig is behalve de intra-trade eval-check (die zit al in de propfirm-engine
   overlay).
5. **Compile-time bench** — de huidige v6.9.1 kost bij mij ~4-6 sec compile op
   een 15-min tester. Doel: **< 2 sec**.

## Efficiëntie-asks — gebruik (trader-UX)

1. **Input-panel moet in één schermweergave passen.** Op mijn resolutie
   (1440×900) betekent dat < 25 zichtbare inputs bij initieel openen. Rest achter
   collapsed groups.
2. **Groepen die default OPEN staan bij eerste laden**:
   `1 · ACCOUNT — Firm & routing` (klein, 4-5 inputs),
   `8 · SIGNAL — Time gate` (nu 1 dropdown!),
   `9 · EXECUTION — Alerts & routing` (routing on/off toggles).
3. **Groepen die default COLLAPSED staan**:
   Signal-tuning (FVG size, confirmation, etc.),
   Position sizing (defaults zijn goed),
   Trade — Entry/Stop/TP (defaults zijn goed),
   Research (dev only) groep.
4. **Alle bewezen defaults moeten in-tooltip vermeld staan** met de opmerking
   *"Deze default komt uit 12-maands backtest 20-08-2026, pass rate 52%. Niet
   aanraken tenzij je opnieuw wil optimaliseren."*
5. **Dashboard vereenvoudiging** — op de intraday eval-run zien we nu heel veel
   metrics. Wat echt belangrijk is:
   - Account phase + balance + trailing stop
   - Eval status (pending / passed / failed)
   - # trades vandaag / cumulatief in deze eval
   - Volgende toegestane GO-slot (aftellen in HH:MM)
   - `Halt reason` indien blocked

## Wat ik terug wil zien

1. **`pine/MEX_EL_TORO.pine` v7.0** — nieuwe file, current v6.9.1 blijft als backup
   (rename naar `.pine.bak` of tag in git).
2. Screenshots van de nieuwe input-panel (default openings-view) + van de dashboard
   overlay tijdens een backtest.
3. Bevestiging dat de default-run op NQ1! 1-min chart, 12 mnd terug,
   de cijfers uit de backtest reproduceert (marge <5%):
   - Netto P&L: ~+$109.726
   - 5.408 exit-trades
   - 39% win rate
   - 52% eval-pass rate (2.447 evals)
4. Regelaantal + compile-time voor en na.
5. Lijst van verwijderde inputs + code-blokken (voor changelog).

## Waarom P1

Op basis van deze v7.0 zetten we de eval-fleet van 20 PA-accounts op. De prompt
voor de nieuwe risk-gate (`docs/pine_dev_prompt_v7.9.2.md` — El Tesoro) staat
open op **q3/q4 met T=$10/B=$100/DLL=$150** voor de funded-side. Zonder deze v7.0
El Toro-cleanup moeten we handmatig 24×5 uur-toggles per eval-account instellen.
Met de preset-selector wordt dat één dropdown-keuze. Time-to-fleet zakt van weken
naar dagen.

## Vragen die je waarschijnlijk hebt

**"Zit deze data-set (die van 20-08-2026) in de repo?"**
Nee — het is een lokaal TradingView-export op mijn machine
(`_L_TORO_CME_MINI_NQ1_20260820_d35bd.xlsx`). Ik stuur hem apart aan, of je genereert
dezelfde run zelf via jouw v7.0 op MGC1! 1-min chart om te valideren.

**"Wat als een default default niet klopt met de backtest-properties?"**
De properties-export in de bijlage is de bron van waarheid. Bij twijfel: neem
letterlijk over.

**"Kan de time-gate preset ook via `input.string` met opties in plaats van
constants at top-of-file?"**
Ja, dat mag. Belangrijk is dat het slot-lijstje niet in de zichtbare input-panel
staat, alleen de dropdown-naam.

**"Moet de recovery trail (trade #2 na loss) actief blijven?"**
Ja, on. Die staat On in de winnende config en de analyse ondersteunt dat het
"tweede-shot" gedrag past bij het one-shot-or-fail patroon van El Toro.

**"Wat als een default op q6 komt te staan?"**
Nee. Position size default = 5 contracts (uit properties). Bij q6 zou trailing
sneller raken op eval; q5 is bewezen op deze config.

**"Wil je de Firm preset dropdown houden?"**
Alleen als er meer dan één firm-preset ondersteund gaat worden op eval-configs.
Voor nu is `apex_50k_eod_eval` de enige. Als je het weglaat: schrijf `apex_50k_eod_eval`
hard in als constant.

---

*Einde prompt voor Pine Dev.*
