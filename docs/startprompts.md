# Startprompts per chat — ronde 18-09 · **alleen wat nú kan**

_Eigenaar: Scrum Master. Watermerk: `32afd0e`, 18-09._

**Opdracht Ferry 18-09: eerst verwerken wat kan, daarna pas de rest afwikkelen.** Elk blok
hieronder is daarom gesplitst in **DOE NU** en **NIET AAN BEGINNEN**. Dat tweede blok is geen
luiheid — het is voorkomen dat iemand werk aflevert tegen een aanname die nog kan omvallen.

**De sleutel van deze ronde is D-66.** Die zit bij Pine Dev én Backtest Setup en hij houdt
D-63 → D-54 → D-57 tegen, en daarmee de hele vlootrangorde. Alles wat daarop wacht staat
hieronder expliciet stil.

---

## 🟦 Middleware App — vijf items, alle vijf vrij

```
git pull origin claude/middleware-setup-guide-afhvtk

Lees docs/SPRINT.md, docs/execution-flow.md (D-70) en de rondes van 16-09 en 18-09 in
docs/inbox.md. Bij jullie ligt geen enkele blokkade — alle vijf kunnen nu.

DOE NU, in deze volgorde:

1. 🔴 D-53 — DE QTY-FIX. Staat sinds 25-08 open en houdt de uitrol tegen.
   De gate raakt alleen `quantity_multiplier` (int > 0), maar Pine stuurt daarnaast zijn
   eigen `"quantity"` — bij MATADOR 6 contracten — en die blijft ongemoeid. Een
   integer-multiplier kan dat alleen gelijkhouden of verhogen, dus naar 1 contract schalen
   lukt niet, en dat was het hele doel.
   Overschrijf `obj["quantity"]` direct als string, laat de multiplier op 1, hernoem de env.
   EN HAAL DE COMMENTAARREGEL Program.cs:156 WEG die zegt "Vers account = 1". Die is onwaar
   en is inmiddels doorgesijpeld naar execution-flow.md — CLO nam hem te goeder trouw over
   uit jullie code. Eén onjuiste regel commentaar heeft zich zo door twee documenten
   verspreid; dat is precies waarom hij mee moet in deze fix.

2. D-73 — sla PMT's antwoordbody op in de routed-regel. `sent 200` is de status van ONZE
   POST, niet PMT's oordeel over de order; routed_journal.py r. 23-27 zegt dat zelf en noemt
   die rijen "accepted orders", niet "fills". Rejected() leest die body al en dan gooien we
   hem weg. Dit gaat door ongeacht wat Ferry bij D-72 kiest.

3. D-74 (jullie helft) — publicatie-semantiek. Het ontwerp is af: tabel 2 van
   docs/execution-flow.md beschrijft het volledig. `account_type` per account; eval →
   pass/breached/lopend genormaliseerd naar 50k-equivalent, GEEN bedragen; funded → saldo
   alleen met `verified_amount` + `verified_at` binnen het venster.

4. D-69 — render.yaml start nog `uvicorn app.main:app` en dat bestand is verwijderd. Een
   deploy vanaf die blueprint crasht. Advies: verwijderen.

5. D-07 — de commissievraag is beantwoord: registry wint, dus 0,37 voor MNQ/MES/MYM. Het
   verifiëren tegen Cash_History kan los van D-63.

Uit de review van D-70, meenemen bij punt 1: de qty-override herschrijft `body` vóórdat de
blocked- en risk-gate mogen weigeren, dus bij een reject journaliseer je een body met een
multiplier die nooit verstuurd is. Override ná de gates, of log de onbewerkte body.

NIET AAN BEGINNEN: de exit-poort (gate #12). Die is niet bouwbaar zoals beschreven en de
routekeuze ligt bij Ferry (D-72).

Claim één item in docs/SPRINT.md vóór je begint. Raakt het het live pad, meld het vooraf.
```

---

## 🟩 Pine Dev — twee items, en één ervan is de sleutel van de ronde

```
git pull origin claude/middleware-setup-guide-afhvtk

D-71 (het validFrom/validUntil-venster) staat op review en ziet er goed uit. Het annuleren
van een openstaande limietorder op de grens was eigen initiatief en was terecht — zonder dat
is de entry-stop geen harde stop.

Eén gevolg dat je niet kon voorzien: dit is een gedragswijziging op dertien scripts, dus
onder D-18 staat de OOS-klok voor de HELE vloot opnieuw op nul, per 07-09. Geen reden om
iets terug te draaien; wel om nergens te schrijven dat deze vloot out-of-sample bewezen is.

DOE NU:

1. 🔴 D-66 — DE PARITEITSVRAAG, samen met Backtest Setup. Dit is de sleutel: hij houdt
   D-63, D-54 en D-57 tegen.
   9 van de 9 scripts verwijzen naar ta.requestVolumeDelta met useCVDFilter aan, terwijl de
   canonieke regel (D-09) de deterministische OHLCV-proxy voorschrijft en de Python-kant zich
   daar wél aan houdt. Maar MATADOR haalde data_parity op trap 1, en dat spreekt een
   materieel verschil tegen. Er ontbreekt dus iets in het beeld.
   Drie kandidaten: de motoren lopen op MES dicht genoeg gelijk · de filter bindt zelden ·
   of er zit een gat in de pariteitstoets. Welke van de drie is het?

2. D-64 — MEX_EL_DORADO.pine compileert niet: firmPreset draagt `apex_intraday_pa`, een
   sleutel die niet in de registry bestaat. De fout zit in gen_pine_firms.py
   STRATEGY_DEFAULT, dus repareren in het .pine-bestand wordt bij de volgende generatorrun
   overschreven.

NIET AAN BEGINNEN:
- D-63 (her-export LEON en REY) — wacht op D-66. Exporteer je nu, dan meet je tegen een
  meetlat waarvan we niet weten of hij klopt, en dan doe je het straks opnieuw.
- D-44 (breakeven_offset) — wacht op Ferry's PMT-dashboardcheck (Auto BreakEven = YES,
  risk type ≠ Price). Zonder die check test je in het donker.
- D-57 (derisk in de bevroren configs) — wacht op D-54.

Claim één item vóór je begint.
```

---

## 🟨 Backtest Setup — D-66 eerst, daarna vrij werk zat

```
git pull origin claude/middleware-setup-guide-afhvtk

Twee dingen uit Pine Dev's v3.4.0 (D-71) die jullie kant raken en die je moet weten vóór je
iets meet:
- De default van het handelsvenster schoof van 01-01-2025 naar 01-01-2026. Bestaande
  backtestbeelden worden dus KORTER zodra een script vervangen wordt. Dat raakt het
  exportvenster waar trap 1 tegen meet.
- TradingView's datumkiezer leest in de EXCHANGE-tijdzone, niet in ET, terwijl onze hele
  sessie-logica op 18:00 ET hangt. Dat is dezelfde klasse fout als de 'naïeve kolom met
  utc=True'-bug.

DOE NU:

1. 🔴 D-66 — de pariteitsvraag, samen met Pine Dev. Zie hun blok voor de drie kandidaten.
   Dit blokkeert D-63, D-54 en D-57 — het is het item met de meeste hefboom op het bord.

2. D-68 — de vloot-pijplijn leest de accountregels niet uit de registry maar codeert ze hard:
   fleet.py:84, firms.py:255, en de stille fallback `or 2500` in higher.py:237 die bij een
   lege waarde terugvalt op precies de onjuiste waarde. Die laatste faalt niet, hij liegt
   zachtjes — maak er een harde fout van.
   Waarom nu: bij D-67 bleek dat propfirms.json maandenlang $2.500 droeg waar $2.000 hoorde.
   De sweep kwam er ongeschonden uit, maar puur omdat het hardgecodeerde getal toevallig het
   juiste was. Was het andersom gegaan, dan had de correctie de pijplijn nooit bereikt.

3. D-15, D-16, D-25, D-38, D-39 — vrij onderzoekswerk, in die volgorde als er ruimte is.

NIET AAN BEGINNEN:
- D-54 — wacht op de her-exports uit D-63, die wacht op D-66.
- D-27 — wacht op D-31 (de runtime-snapshot-timer, ligt bij Ferry). Let op: docs/runtime-
  snapshot.md bestaat niet, dus die timer draait niet of commit niet.
- D-50 staat op blocked; zeg het als dat niet meer klopt.

Claim één item vóór je begint. validation/ is append-only.
```

---

## 🟪 Web — D-34 afmaken, en de helft van D-74 kan al

```
git pull origin claude/middleware-setup-guide-afhvtk

Je route-check (inbox 34) heeft een ontwerpbesluit omgegooid: gate #12 uit execution-flow.md
is niet bouwbaar en ligt nu als D-72 bij Ferry, en je losse bevinding over PMT's antwoordbody
staat als D-73 bij Middleware App. Statisch bewijs langs twee kanten, een falsifieerbare
voorspelling erbij en een read-only script — zo hoort het.

DOE NU:

1. D-34 — de publieke claims afmaken. Er is één ding veranderd sinds je laatste ronde: de
   OOS-klok staat sinds 07-09 op nul voor de HELE vloot (D-71, het nieuwe handelsvenster).
   Dus: "gevalideerd op drie jaar (2023-2026)" mag · "3 jaar out-of-sample" mag NIET · een
   ranglijst mag NIET, want die is er niet. Alleen MATADOR heeft een gesloten pariteitspoort,
   en dat cijfer wacht zelf nog op een hertoets.

2. D-74 (jullie helft, deels) — je kunt `mex_units.roles.for_public_evals()` en de test die
   borgt dat geen eval-metric door `for_public()` glipt NU al schrijven, tegen de spec in
   tabel 2 van docs/execution-flow.md. Eval-bedragen horen sowieso van de site af.

NIET AAN BEGINNEN: het publiceren van het genormaliseerde eval-format zelf — dat wacht tot
Middleware App het format levert. Schrijf de gate en de test, niet de consument.

Meld het in docs/inbox.md als D-34 af is; de review loopt via de Scrum Master.
```
