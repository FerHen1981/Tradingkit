# Voorstel: opruimronde op de input-laag van de vloot

> Pine Dev · 25-08 · **voorstel, nog niet uitgevoerd.** Ferry vult aan en past aan.
> Harde randvoorwaarde van de opdracht: **de bestaande logica blijft onaangetast.**

## De regel die alles afdekt

**Elke input die verdwijnt, wordt vervangen door zijn huidige default als constante.**
De gecompileerde beslissingen zijn daarna identiek — er verdwijnt een *knop*, geen gedrag.
Wat nu op `false` staat en weggaat, staat daarna hard op `false`.

Drie controles voordat er iets gepusht wordt:

1. **Per verwijderde input** vastleggen: naam, huidige default, de constante die ervoor
   in de plaats komt. Die lijst gaat mee in de commit.
2. **`backtest/tests/test_fleet_parity_source.py`** (Backtest Setup, D-61) leest
   `pine/v1_0_0/*.pine` bij elke testrun en faalt bij afwijking. Verandert er per ongeluk
   een waarde, dan valt hun suite om.
3. **Ferry's eigen test:** zelfde chart, zelfde periode, export vóór en ná. Die moeten
   **trade voor trade** gelijk zijn. Wijkt er één trade af, dan gaat de wijziging terug.

## Waar we nu staan

**216–220 inputs per script**, waarvan er ongeveer **106 zichtbaar** in het paneel staan
(de rest is `display.none`). De grootste blokken:

| groep | inputs | wat |
|---|---|---|
| `0b · MEX — Stability presets` | **49** | 48 richtings-uurtoggles + een MGC-specifieke lock |
| `8 · SIGNAL — Time gate` | **37** | 24 uurtoggles + 7 weekdagen + venster |
| `1 · ACCOUNT — Phase` | 16 | |
| `10 · RESEARCH — Visuals` | 16 | |
| overige 18 groepen | ~100 | |

**79 van de ~218 inputs zijn losse uur- en dagvinkjes.** Dat is ruim een derde van het
paneel voor één mechanisme.

## Voorstel in vier lagen

### Laag 1 — knoppen die in élke stand niets doen (nul risico)

Zestien schakelaars staan als **harde constante** in de bron, geen input. Alles wat eraan
hangt is daarmee onbereikbaar, maar staat wél in het paneel:

`usePaFilters` · `useRelVolFilter` · `useBbwpFilter` · `useOrBreakout` · `useGoalTp` ·
`useDerisk` · `useDeriskPA` · `useRecovTrail` · `enableDailyTarget` ·
`enableDailyDrawdown` · `enableEquityLock` · `onlyFirstTrade` · `useSweepFilter` ·
`useBiasFilter` — allemaal `false`.

Weg met de schakelaar **en** met de inputs die alleen door hem gelezen worden
(`dailyProfitTarget`, `dailyDrawdownLimit`, `equityLockThreshold`, `equityLockPerc`,
`recovTrailStart`, `recovTrailBuf`, de sweep- en bias-parameters, de derisk-niveaus).

> ⚠️ **`enableDailyLossLimit` hoort hier NIET bij.** Die heb ik gisteren juist tot input
> gemaakt in MATADOR omdat de machinerie eronder werkt. Die blijft.

### Laag 2 — de uurroosters (de grote winst: −79 inputs)

24 uurtoggles + 48 richtings-uurtoggles + 7 weekdagen.

Fijnmazige (dag, uur)-selectie staat in dit project op drie plaatsen als **weerlegde
OOS-ruis** vastgelegd (`CLAUDE.md:43`, `pipeline-v7-authoritative.md:23` en `:182`). Ik heb
dat voor EL TORO nagerekend: bij 120 cellen à ~20 evals levert toeval ~21 cellen boven 65%,
en de analyse vond er 11 — de lijst was kleiner dan ruis.

**Vervangen hoeft niet, want het alternatief zit er al in en is live.**
`marketRegimeMode` (`All sessions` / `Liquidity Core` / `Custom` met London 02:00-05:00 en
US 07:00-12:00) voedt `timeGatePassRaw` op regel 718. Dat zijn economisch vooraf
gedefinieerde vensters, precies wat de pijplijn wél toestaat.

Voorstel: **`marketRegimeMode` blijft, de 79 losse vinkjes gaan weg**, en er komt één
grofmazig `Trading window (uur van – tot)` terug voor wie een blok wil dichtzetten.
De weekdagen kunnen desgewenst blijven als één multi-select in plaats van zeven vinkjes.

### Laag 3 — resten van de fork

`stabilityPreset` biedt *"Lock MGC Stability Core · 2 MGC / 3 MGC"* aan — óók in het MES-,
MNQ- en MYM-script. Zelfde soort artefact als de dubbele merkkop en de NQ-preset in het
GC-script: gekopieerd zonder de identiteit te herschrijven.

Per script alleen aanbieden wat op dat instrument bestaat, of helemaal weg als de lock
nergens meer gebruikt wordt.

### Laag 4 — verbergen in plaats van verwijderen

Wat research-only is maar wél werkt, hoort niet in het dagelijkse paneel: de visuals (16),
de research-datumgrenzen, de live-sync offsets. Eén groep `12 · RESEARCH (dev)`, standaard
ingeklapt.

## Wat het oplevert

| | nu | na |
|---|---|---|
| inputs totaal | ~218 | **~120** |
| zichtbaar in het paneel | ~106 | **~45** |
| knoppen die niets doen | 14+ | **0** |

## Wat ik expliciet NIET voorstel

- Geen enkele **parameterwaarde** wijzigen. De bevroren configuratie blijft exact.
- Niets aanraken aan het **executiepad**: `f_sendExec`, de PMT-payload, de alert-emitters.
- `marketRegimeMode`, de risk-gate-machinerie en de firm-preset-koppeling blijven zoals ze
  zijn — dat is levende logica, geen paneelruis.
- Geen samenvoeging van scripts. Negen bestanden blijven negen bestanden.

## Volgorde

1. Ferry vult aan en schrapt uit dit voorstel.
2. Ik lever de **exacte lijst** per script: input → vervangende constante.
3. Uitvoeren op **één script** (MATADOR ligt voor de hand — die staat al klaar), export
   vóór/ná vergelijken.
4. Pas na een schone vergelijking de andere acht, in één ronde.
