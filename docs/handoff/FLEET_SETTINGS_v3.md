# Vloot-instellingen zoals ze horen te zijn — v3.2.0 uitrol

Stand 26-08-2026 · Pine Dev · **ter goedkeuring vóór uitrol**

Bron van waarheid voor de engine-getallen:
`.claude/skills/strategy-validation-pipeline/references/frozen-engines.md`.
Alle 13 scripts zijn hiertegen gecontroleerd — **alle bevroren parameters kloppen**.

---

## A. Gedeelde basis — identiek in alle 13 scripts

| Instelling | Waarde |
|---|---|
| Reference timezone | `America/New_York` |
| Trading day boundary | Exchange session (ETH) |
| Handelsdagen | Zo–Vr aan, Za uit (uitz. zie C) |
| Uren-blokken 00/06/12/18 | alle vier aan |
| Time-gate vensters | Globex reopen · London · US morning **aan**; Asia · Init balance · NY AM · Lunch · NY PM · Power hour **uit** |
| Force flat 16:55–18:00 | aan |
| Sizing mode | Fixed contracts · max qty 100 |
| Entry mode | Limit @ 50% FVG |
| Stop mode | Fixed (legacy) |
| Break-even | **uit** |
| Trailing | **uit** |
| FVG fill check | aan |
| CVD streak-filter | aan |
| FVG size range filter | aan |
| Longs / Shorts | beide aan |
| Daily risk-gate | uit |
| BBWP / EMA / MFI / Volume profile / Discount-Premium filter | **alle vijf uit** |
| Dashboard | aan · Bottom Right · Wide (4 columns) · Auto theme · tiny |
| Signals / TP-SL levels / Order levels / Unfilled orders | alle vier aan |
| Trade Gate background | aan · TimeGate background uit |
| Alert: signal blocked | aan |
| Routing (PMT / Rithmic / PineConnector / Discord / Journal) | **alle vijf uit** — per account aanzetten |
| Lock cost buffer | 4 ticks |
| Backtest start | 01 jan 2025 00:00 −0400 · start balance 0 · geen entries daarvoor |

---

## B. De negen funded scripts (`accountPhase = Funded`, `useFirmPreset = ON`)

Met de preset aan schrijft de registry `ddModel`, `trailing DD`, `DLL` en `consistency`
over de handmatige velden heen. Vaste PA-waarden: **DLL $1.000 · payout buffer $500 ·
payout nr. 1 · consistency 50% · min. payout $500 · min. kwalificerende dag $250 ·
MAE-guard uit · lock-on-cap aan**.

| Script | Firm program | Qty | FVG | CVD | SL | TP | Expiry | Regime | Day-exit |
|---|---|---|---|---|---|---|---|---|---|
| **EL REY** MNQ PROD EOD | `apex_50k_eod_pa` | 6 | 2–8 | 8 | 200 | 1,25R | 6 | All sessions | Off |
| **EL REY** MNQ PROD INTRA | `apex_50k_intraday_pa` | 6 | 2–8 | 8 | 200 | 1,25R | 6 | All sessions | Off |
| **EL MATADOR** MES PROD EOD | `apex_50k_eod_pa` | 6 | 10–22 | 6 | 120 | 1,75R | 6 | All sessions | Off |
| **EL TESORO** MGC CON EOD | `apex_50k_eod_pa` | 7 | 11–16 | 6 | 140 | 2,25R | 12 | **Liquidity Core** | **Trail + cap** |
| **EL PATRON** MGC AGG EOD | `apex_50k_eod_pa` | 8 | 11–16 | 5 | **120** | 2,25R | 12 | **Liquidity Core** | **Trail + cap** |
| **EL LEON** MYM PROD EOD | `apex_50k_eod_pa` | 3 | 12–20 | 6 | 480 | 1,25R | 24 | All sessions | Off |
| **EL LEON** MYM CON EOD Q2 | `apex_50k_eod_pa` | **2** | 12–20 | 6 | 480 | 1,25R | 24 | All sessions | Off |
| **EL LEON** MYM CON INTRA Q2 | `apex_50k_intraday_pa` | **2** | 12–20 | 6 | 480 | 1,25R | 24 | All sessions | Off |
| **EL BANDIDO** MYM HF EOD | `apex_50k_eod_pa` | 5 | 4–8 | 3 | 160 | 1,5R | 18 | All sessions | **Day-cap (hard $1.000)** |

Afwijkingen op de gedeelde basis, met opzet:
- **PATRON + TESORO**: `tradeSunday = uit`, regime **Liquidity Core**, `useVwapVeto = aan`,
  delta-engine op **TradingView volume delta** (D-09 niet-canoniek by design, staat zo in de linter).
- **BANDIDO**: harde dagcap $1.000 conform `frozen-engines.md`. Pine-pariteitspoort staat nog open —
  **niet live zetten**.
- **MATADOR** draagt als enige een eigen `enableDailyLossLimit` (uit).
- LEON Q2 = het recovery-profiel op 2 MYM; verandert exposure, niet de signalen.

---

## C. De vier EL TORO — **uitsluitend evaluatie-accounts**

`accountPhase = Eval` · `useFirmPreset = UIT` · `tradeSunday = uit` ·
`tpMode = Fixed (units)` · `confirmBarsIn = 2` · geen payout-/MAE-machinerie.

| Script | Qty | FVG | CVD | SL | TP (units) | Expiry | DD-model | VWAP veto |
|---|---|---|---|---|---|---|---|---|
| **EL TORO** GC SNIPER EOD | 5 | 10–14 | 6 | 90 | 64 | 12 | EOD | aan |
| **EL TORO** NQ SNIPER INTRA | 7 | 4–8 | 7 | 100 | 90 | 6 | Intraday | aan |
| **EL TORO** NQ HF INTRA | 7 | 4–12 | 3 | 90 | 90 | 9 | Intraday | aan |
| **EL TORO** ES FAST INTRA | 6 | 2–8 | **filter uit** | 90 | 44 | 18 | Intraday | uit |

---

## D. Wat de uitrol verandert (twaalf scripts naar v3.2.0)

EL REY MNQ PROD EOD staat al op **v3.2.0**; de andere twaalf op **v2.3.2**.
De uitrol brengt daar functionaliteit heen, **geen enkele engine-parameter verandert**:

1. **Time-gate vensters getekend met naam** — `showGateBoxes = aan`, `gateBoxKeep = 4`.
2. **Trade-annotaties los van de tekenvenster-limiet** — nieuw `tradeDrawLast = 0` (= alles),
   caps naar 480 boxes/labels, zodat oude trades zichtbaar blijven.
3. **ARMED-kaart** — nieuw `notifyArmed = aan`: alert zodra de time gate opent.
4. **Drie-laags tabel** (ACCOUNT · INDICATORS · TRADE) met vandaag-stats en open ORDER/POSITION-regel.
5. **Overlay-indicatoren met eigen schakelaar**, los van of het filter actief is:
   `showVwapLine = aan`, `showEmaLine = aan`, `showPocLine = uit`, `showDpBand = uit`.
6. **FVG-weergave**: `fvgSizeMode = All`. Dit is **alleen weergave** (raakt `fvgDrawOK`,
   niet de handelslogica) — het size-filter blijft op de bevroren range staan.
7. **Performance**: alle `request.*`-aanroepen op dode takken verwijderd, BBWP- en MFI-loop
   achter hun schakelaar. Doel is de time-outs die op REY al weg zijn.

---

## E. Drie punten die ik nog van je nodig heb

1. **EL TORO trailing DD = $2.500.** De vier TORO's staan met `useFirmPreset = UIT` op een
   handmatige $2.500, terwijl hun eigen programmasleutel (`apex_50k_*_eval`) in de registry
   **$2.000 / lock $2.100** is — de Apex 4.0-route die je zelf hebt vastgesteld.
   Op een 4.0-eval is $2.500 dus **te ruim**: het script denkt dat er nog speling is als de
   firma al gebreacht heeft. Voorstel: **naar $2.000**, of `useFirmPreset` aan zetten zodat de
   registry het invult. Alleen als de TORO's op *legacy* evals draaien klopt $2.500.
2. **`fvgSizeMode = All` fleet-breed** (punt D6). Puur weergave, maar het maakt de charts wel
   voller — akkoord?
3. **Bestandsnaam-hernoeming (`_v1_0_0` eraf) en de automatische versiebump** houd ik als
   aparte stap ná deze uitrol, zodat de zip één ding tegelijk verandert. Akkoord?
