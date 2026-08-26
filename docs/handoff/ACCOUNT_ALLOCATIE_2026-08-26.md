# Accounttoewijzing — 16 Apex-accounts, stand 26-08-2026

Voorstel van Pine Dev op basis van de accountschermen van Ferry (26-08), de registry
`data/propfirms.json` en de bevroren parameters. **Nog niet uitgevoerd — ter beslissing.**

## Sizing-regel die ik hanteer

Houd minstens **8 opeenvolgende volle stops** tussen het account en zijn trailing floor.
Dat is een heuristiek, geen gemeten optimum. Onderbouwing: de vloot-sweep vond dat een
verliesreeks van ongeveer $2.700 een vers account breekt vóór de floor vergrendelt, en de
gemeten win rates liggen tussen 52% en 61% — acht op rij mis is dan ruwweg een 1-op-500
gebeurtenis per reeks. Ruimer mag; krapper is een bewuste gok.

Dollarstop per contract (tickwaarde uit de asset-spec in de scripts):

| Engine | Symbool | Stop (ticks) | $/contract | Zelfde stop op full-size |
|---|---|---|---|---|
| EL MATADOR | MES | 120 | **$150** | ES $1.500 |
| EL REY | MNQ | 200 | **$100** | NQ $1.000 |
| EL LEON | MYM | 480 | **$240** | YM $2.400 |
| TORO NQ SNIPER | MNQ | 100 | **$50** | NQ $500 |
| TORO NQ HF | MNQ | 90 | **$45** | NQ $450 |
| TORO ES FAST | MES | 90 | **$112,50** | ES $1.125 |
| TORO GC SNIPER | MGC | 90 | **$90** | GC $900 |

## De zes PA's

Het onderscheid dat telt is niet de balans maar of de **floor vergrendeld** is. Apex laat de
trailing threshold meelopen tot startsaldo + $100 en bevriest hem daar. Op een vergrendeld
account kan de floor nooit meer omhoog; op een niet-vergrendeld account achtervolgt hij elke
nieuwe high, en dan is een run-up gevolgd door een give-back dubbel duur.

| Account | Product | Equity | Floor | Ruimte | Vergrendeld | Engine | Symbool | Qty | $/stop | Stops |
|---|---|---|---|---|---|---|---|---|---|---|
| PA-13 | Legacy 50k | $55.729 | $50.100 | **$5.629** | ja | EL MATADOR MES PROD EOD | MES | **4** | $600 | 9,4 |
| PA-18 | Legacy 50k | $53.219 | $50.100 | **$3.119** | ja | EL MATADOR MES PROD EOD | MES | **2** | $300 | 10,4 |
| PA-22 | Legacy 50k | $50.152 | $48.055 | $2.096 | nee, +$2.045 | EL LEON MYM PROD EOD | MYM | **1** | $240 | 8,7 |
| PA-21 | Legacy 50k | $49.756 | $48.147 | $1.609 | nee, +$1.953 | EL REY MNQ PROD EOD | MNQ | **2** | $200 | 8,0 |
| PA-15 | 50k EOD Trail | $50.995 | $49.898 | $1.097 | nee, **+$202** | EL REY MNQ PROD EOD | MNQ | **1** | $100 | 11,0 |
| PA-17 | Legacy 50k | $49.596 | $48.553 | $1.043 | nee, +$1.547 | EL REY MNQ PROD EOD | MNQ | **1** | $100 | 10,4 |

Waarom zo:
- **MATADOR op de twee vergrendelde accounts.** Hij is de enige engine met een gesloten
  pariteitspoort en het enige bruikbare payout-cijfer. Zet je beste bewijs op de accounts
  waar de floor niet meer tegen je in kan bewegen.
- **De vier niet-vergrendelde accounts krijgen één opdracht: vergrendelen.** Niet maximaal
  verdienen — de floor stilzetten. Daarna mag de size omhoog. PA-15 staat **$202** van
  vergrendeling af; dat is de goedkoopste winst in de hele portefeuille.
- **PA-21 alternatief:** EL LEON op 1 MYM geeft 6,7 stops in plaats van 8,0. Meer spreiding
  over instrumenten, minder marge. Bewuste ruil.

⚠️ **Er is geen echte spreiding en dat kan ik nu niet oplossen.** MES, MNQ en MYM zijn alle
drie Amerikaanse index-exposure. De enige niet-index-engines zijn EL TESORO en EL PATRON op
MGC, en die staan allebei onder het GC-twin-voorbehoud — TESORO is nooit getoetst, PATRON is
in de sweep afgevallen. **Ik zet geen funded kapitaal op een engine waarvan het bewijs op een
surrogaat-markt staat.** Zes accounts, één risicorichting: weet dat dat zo is.

## De tien evaluaties

🔴 **Draai de TORO-scripts op de MICRO, niet op full-size.** De commissies in die vier scripts
(1,55 voor ES/NQ, 1,75 voor GC) zeggen dat ze op volle contracten geconfigureerd zijn, en dan
is één stop op de bevroren grootte al fataal: TORO ES FAST op 6 ES is **$6.750 per stop** op
een account met $2.000 ruimte. Op MNQ/MES/MGC zijn de signalen **identiek** — NQ en MNQ delen
mintick 0,25, ES en MES ook, GC en MGC delen 0,1 — alleen de dollars verschillen een factor
tien. Zie de openstaande punten hieronder voor wat dat met de commissie doet.

| Account | Product | Ruimte | Script | Symbool | Qty | $/stop | Stops |
|---|---|---|---|---|---|---|---|
| 218 | Intraday Trail (4.0) | $2.000 | TORO NQ SNIPER INTRA | MNQ | 5 | $250 | 8,0 |
| 219 | Intraday Trail (4.0) | $2.000 | TORO NQ HF INTRA | MNQ | 5 | $225 | 8,9 |
| 220 | Intraday Trail (4.0) | $2.000 | TORO ES FAST INTRA | MES | 2 | $225 | 8,9 |
| 221 | Intraday Trail (4.0) | $2.000 | TORO NQ SNIPER INTRA | MNQ | 3 | $150 | 13,3 |
| 222 | Intraday Trail (4.0) | $2.000 | TORO NQ HF INTRA | MNQ | 3 | $135 | 14,8 |
| 217 | Legacy 50k | $2.500 | TORO GC SNIPER EOD | MGC | 3 | $270 | 9,3 |
| 223 | Legacy 50k | $2.500 | TORO GC SNIPER EOD | MGC | 2 | $180 | 13,9 |
| 224 | Legacy 50k | $2.500 | TORO ES FAST INTRA | MES | 2 | $225 | 11,1 |
| 225 | Legacy 50k | $2.500 | TORO NQ SNIPER INTRA | MNQ | 6 | $300 | 8,3 |
| 197 | Legacy 25k Rithmic | $1.500 | TORO NQ HF INTRA | MNQ | 4 | $180 | 8,3 |

De duplicaten draaien met opzet dezelfde engine op **twee groottes** (5 vs 3, 6 vs 3, 3 vs 2).
Contractgrootte is exposure en geen signaalparameter, dus dit valt niet onder de
bevriezingsregel — en zo levert een dubbel account informatie op in plaats van een kopie.

**Twee accounts op MGC is geen toeval.** Het enige echte gat in het bewijs van dit project is
MGC-data: TESORO en PATRON zijn op de GC-twin gemeten en dáárom staat elk oordeel over ze
onder voorbehoud, ook het negatieve. Twee evals die MGC vooruit draaien vullen dat gat met
echte data, op accounts die $167 kosten in plaats van op funded kapitaal.

### Wat de evals eigenlijk waard zijn

Nul scripts in deze vloot zijn out-of-sample bewezen; de OOS-klok loopt pas vooruit vanaf het
bevriezen van een config. **Tien evals die vanaf vandaag een bevroren config vooruit draaien
zijn precies het meetinstrument dat ontbreekt.** Dat is op dit moment plausibel meer waard dan
de eval-payouts zelf. Voorwaarde: zet **Journal én Discord aan op alle tien**, anders is de
forward-data weg zodra de eval afloopt.

## Instellingen — wat er per chart moet

**Verplicht, anders rekent het script met de verkeerde accountregels:**

1. **`Firm program` op de vijf legacy PA's naar `apex_50k_legacy_pa`.** De scripts staan default
   op `apex_50k_eod_pa`, en dat programma draagt $2.000 trailing en 50% consistency. Zijn
   accounts zijn legacy: **$2.500 en 30% consistency**. PA-15 is de enige die op
   `apex_50k_eod_pa` hoort.
2. **`Use firm preset` AAN op de vier TORO's** (staat nu UIT). Dan vult de registry per eval de
   trailing DD én het drawdown-model: `apex_50k_intraday_eval` voor 218–222,
   `apex_50k_legacy_eval` voor 217/223/224/225, `apex_25k_legacy_eval` voor 197. Dat is beter
   dan het handmatige getal, want het onderscheidt legacy van 4.0 met één keuze.
3. **`PMT/Tradovate Account ID`** per chart invullen — de receiver leest het account uit de
   omschrijving.
4. **Account 197 draait op Rithmic, niet op Tradovate.** Route `→ PMT Rithmic` in plaats van
   `→ PMT Tradovate`. Ook: maximaal 4 contracten op een 25k.
5. **`Fixed Qty`** per account volgens de tabellen hierboven.

**Aanbevolen:**

6. **`Daily risk-gate` AAN op PA-15, met DLL ≈ $300.** Dat is het enige account met een actieve
   daily loss limit ($1.000) én een ruimte van $1.097 — één slechte dag is daar bijna het hele
   account. De risk-gate stopt de dag ruim vóór Apex dat doet. Op de andere vijf laten staan.

**Overwegen, niet aandringen:**

7. **`MAE guard`** staat overal uit. Op de vier niet-vergrendelde PA's is dat precies waar hij
   voor bedoeld is (hij schaalt risico terug als percentage van de profit balance in de
   PA-fase). Op 1 contract bindt hij niet, dus pas relevant als de size omhoog gaat.

## Drie dingen die eerst een antwoord nodig hebben

1. **🔴 Payout-signaal staat te vroeg op de legacy PA's.** Het script gebruikt
   `qualDays >= 5`, hardgecodeerd. De registry zegt dat `apex_50k_legacy_pa` **8 handelsdagen
   met fills én 5 kwalificerende dagen** vraagt, en het firm-preset zet die drempel niet mee —
   hij vult alleen ddModel, trailing DD, goal, DLL en consistency. Op vijf van je zes PA's
   meldt de tabel dus drie dagen te vroeg "payout ready". **Ik kan dat repareren** (drempel uit
   de registry halen, net als de rest), maar het raakt alle dertien scripts, dus ik doe het
   niet ongevraagd.
2. **🟠 Daily loss limit: registry en jouw scherm spreken elkaar tegen.** `propfirms.json` geeft
   `apex_50k_legacy_pa` een DLL van $1.000; jouw risicoscherm laat de kolom leeg bij alle PA's
   behálve PA-15. Als je legacy PA's echt geen DLL hebben, stopt het script de dag bij −$1.000
   terwijl Apex je door laat gaan — veilig, maar het kost handelsdagen, en handelsdagen zijn
   op een legacy PA een harde payout-eis. Klopt de registry of het scherm?
3. **🟠 TORO-commissie hoort niet bij de micro.** Als je ze op MNQ/MES/MGC draait — en dat is
   mijn advies — dan staat de commissie in het script met 1,55/1,75 drie tot vier keer te hoog
   (registry: 0,37 en 0,52). Dat raakt de live-uitvoering niet, alleen elk backtestcijfer dat
   je er daarna uit haalt. Rechtzetten betekent wel dat alle bestaande TORO-backtestcijfers
   veranderen, dus dat is jouw beslissing en niet de mijne.

Verder los: **EL TORO GC SNIPER heet EOD, maar je hebt geen EOD-trailing eval.** Alle tien je
evals trailen intraday. Met het juiste firm-preset rekent het script wél goed, maar hij draait
dan onder een ander drawdown-model dan waarvoor hij bedacht is. Kleine afwijking, wel bewust.
