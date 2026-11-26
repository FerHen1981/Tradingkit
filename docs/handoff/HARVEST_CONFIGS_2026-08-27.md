# Harvest-configuraties — instellingenblad

Pine Dev · 27-08-2026 · **voorstel, niet bevroren, niet gevalideerd**

Vier configuraties van de hoog-volume ("harvest") vorm, met de dagbracket erop. Bedoeld om
snel naar opneembaar saldo te komen in stappen van $1.500–$3.000, niet om meerjarig te
overleven.

> ⛔ **Zet dit niet op je bevroren charts.** Elk van deze configuraties wijkt op vier of meer
> bevroren parameters af. Gebruik een **aparte chart-instantie** per configuratie; de negen
> bevroren engines blijven ongemoeid. Zolang dit niet door trap 1–9 is, hoort het op een
> **evaluatie-account** ($167) en niet op funded kapitaal.

## Welk script op welke markt

Het maakt voor de logica niet uit welk merkscript je pakt — de motor is identiek en de
asset-spec wordt op de chart opgelost. Wat wél uitmaakt is de **commissie in `strategy()`**,
want die is een constante per script:

| Markt | Gebruik dit script | Commissie in dat script |
|---|---|---|
| **MGC** | `MEX_EL_TESORO_MGC_CON_EOD` | 0,52 ✅ |
| **MES** | `MEX_EL_MATADOR_MES_PROD_EOD` | 0,37 ✅ |
| **MNQ** | `MEX_EL_REY_MNQ_PROD_EOD` | 0,37 ✅ |
| **MYM** | `MEX_EL_LEON_MYM_PROD_EOD` | 0,37 ✅ |

## De vier configuraties

| Groep · input | **MGC** | **MES** | **MNQ** | **MYM** |
|---|---|---|---|---|
| *Bewijs* | 599 trades gemeten | 2.640 trades (FLEET 10-08) | **ongetest** | **ongetest** |
| **9 · SIGNAAL** | | | | |
| Min FVG Size (units) | 8 | 9 | 9 | 9 |
| Max FVG Size (units) | 23 | 15 | 15 | 15 |
| Confirmation window (bars) | 4 | 2 | 2 | 2 |
| Use Delta Filter | **uit** | **uit** | **uit** | **uit** |
| VWAP side veto | **aan** | **uit** | **uit** | **uit** |
| Market regime | All sessions | All sessions | All sessions | All sessions |
| **7 · ENTRY / STOP / TP** | | | | |
| Entry Mode | Limit @ 50% FVG | idem | idem | idem |
| Limit Order Expiry (bars) | 12 | 12 | 12 | 12 |
| Stop Mode | Fixed (legacy) | idem | idem | idem |
| Max Stop Distance (units) | **100** | **100** | **100** | **100** |
| Fixed Stop (units, legacy) | **100** | **100** | **100** | **100** |
| Take-Profit Mode | R-multiple | R-multiple | R-multiple | R-multiple |
| R-Multiple | **1,0** | **2,5** | **2,5** | **2,5** |
| Enable Break-even | **aan** | **aan** | **aan** | **aan** |
| BE Trigger MFE (units) | 50 | 40 | 40 | 40 |
| BE Offset (units) | 30 | 20 | 20 | 20 |
| Enable Trailing | **aan** | **aan** | **aan** | **aan** |
| Trail Activation MFE | 61 | 60 | 60 | 60 |
| Trail Buffer | 24 | 25 | 25 | 25 |
| **6 · SIZING** | | | | |
| Fixed Qty *(zie noot)* | **3** | **2** | **6** | **6** |
| — dollarstop per contract | $100 | $125 | $50 | $50 |
| — volle stop op die grootte | $300 | $250 | $300 | $300 |

**Waarom die aantallen:** de bindende beperking is de **dagverlieslimiet van $1.000**, niet de
drawdown. Kies de grootte zó dat er ongeveer **drie volle stops in de DLL passen** — dan kan een
slechte dag je niet in één klap uit het account werken. Op MGC bindt de DLL tot 3 contracten
nooit; vanaf 4 kapt hij 11% van de dagen af.

## De dagbracket — dit is het nieuwe deel

Identiek voor alle vier de markten, want de DLL en de consistency-regel zijn **accountregels**,
geen marktregels.

| Input (groep 8 · DAY EXIT en 11 · RISK GATE) | Apex 4.0 | Legacy |
|---|---|---|
| Day-profit exit mode | **Day-cap (hard target)** | **Day-cap (hard target)** |
| Day-cap hard target ($) | **750** | **500** |
| Daily risk-gate | **aan** | **aan** |
| DLL $ | **900** | **900** |
| DLL basis | Realized + open (cuts the trade) | idem |
| Trail arms above $ | **99999** ← zet de intraday-trail uit | idem |
| give-back $ | irrelevant zolang de trail uit staat | idem |

- **$900 in plaats van $1.000:** je stopt zelf vóór Apex je stopt. Ik heb met $1.000 gemeten;
  $900 geeft marge voor slippage en is niet gemeten.
- **Legacy krapper dan 4.0:** niet vanwege risico maar vanwege de **30%-consistencyregel**. Zonder
  cap werden in de simulatie 187 uitbetalingsaanvragen geblokkeerd; met een cap van $500 nul.
- **De dag-trail staat expliciet uit.** Gemeten als neutraal tot negatief; de risk-gate heeft er
  standaard een op *arms above $10 / give-back $100* en die vuurt continu.

## Account-blok

| Input | Waarde |
|---|---|
| Account phase | Funded (op een eval: Eval) |
| Use firm preset | **aan** |
| Firm program | `apex_50k_eod_pa` (4.0) · `apex_50k_legacy_pa` (legacy) · `apex_50k_intraday_eval` / `apex_50k_legacy_eval` op een eval |
| MAE guard | **aan** |
| Close all when payout cap is reached | aan |
| Next payout number (1-6) | volg je echte stand |
| Routing | per account: PMT Tradovate · Discord · Journal |

## ❌ Twee dingen die géén instelling zijn

1. **Contracten per fase.** De meting zegt: 2 contracten vóór de vergrendeling, 3 erna
   (0 breaches tegen 10 bij vast 3). `useDeriskPA`, `deriskPaLvl` en `deriskPaQty` staan als
   **harde constanten** in het script en de logica schaalt bovendien de verkeerde kant op — naar
   beneden bij nadering van de safety net in plaats van omhoog na de vergrendeling. **Tot dit
   gebouwd is: draai de kolom hierboven als vaste grootte en accepteer de hogere breach-kans, of
   zet handmatig één contract lager tot je floor vaststaat.**
2. **Stoppen na N uitbetalingen.** Bestaat niet; de cyclus reset hardcoded op zes. Zolang dat zo
   is moet je de zesde uitbetaling zélf niet aanvragen — het script blijft hem melden.

## Bewijsstatus per configuratie — lees dit vóór je iets aanzet

| | Status |
|---|---|
| **MGC** | 599 trades over 64 sessies gemeten, volledige Apex-cyclus gesimuleerd. Sterkste bewijs, maar drie maanden, één instrument, in-sample, op zelfgekozen parameters. |
| **MES** | 2.640 trades in de FLEET-run van 10-08. PF 0,90 in-sample / 1,01 r12 / 1,04 oos. Accountdoel $500 per breach. **Zakte door de stress-test.** |
| **MNQ · MYM** | **Nooit in deze vorm getest.** De NQFAMILY-run testte MATADOR's configuratie op die markten, niet de harvest-vorm. Puur verkennend. |

⚠️ **Alle vier de FLEET-harvestruns zakten door de stress-test** (2 ticks slippage + dubbele
commissie) — en ze zijn allemaal gemeten **zonder** de dagbracket. Dat is precies de faalmodus:
het zijn breaches, en de dagstop was in mijn simulatie het verschil tussen 25 dode accounts en 0.
**De eerste zinnige test is de FLEET-configs opnieuw draaien mét de bracket**, niet deze
instellingen live zetten.
