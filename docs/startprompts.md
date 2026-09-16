# Startprompts per chat — ronde 16-09

_Eigenaar: Scrum Master. Ververst elke toezichtronde. Watermerk: `9a411b0`, 16-09._

Plak het blok van de betreffende chat als **eerste bericht**. Elk blok begint met een pull,
zodat niemand op een oude stand claimt.

⚠️ **Verlopen blok?** Is de datum hierboven ouder dan het watermerk onderaan `docs/SPRINT.md`,
vraag dan eerst een verse ronde.

---

## 🟦 Middleware App

```
git pull origin claude/middleware-setup-guide-afhvtk

Lees docs/SPRINT.md, docs/execution-flow.md (nieuw, D-70) en de rondes van 16-09 in
docs/inbox.md. Er ligt één ding dat de rest blokkeert en één nieuw item dat klein en
waardevol is.

1. 🔴 D-53 — DE QTY-FIX. Dit staat sinds 25-08 open en blokkeert de uitrol.
   De gate raakt alleen `quantity_multiplier` (int > 0), maar Pine stuurt daarnaast zijn
   eigen `"quantity"` — bij MATADOR 6 contracten — en die blijft ongemoeid. Een
   integer-multiplier kan dat alleen gelijkhouden of verhogen, dus naar 1 contract schalen
   lukt niet.
   Overschrijf `obj["quantity"]` direct als string, laat de multiplier op 1, hernoem de env.
   EN: haal de regel commentaar op Program.cs:156 weg die zegt "Vers account = 1". Die is
   onwaar en is inmiddels doorgesijpeld naar execution-flow.md — CLO nam hem te goeder
   trouw over uit jullie code.

2. D-73 (nieuw) — PMT's antwoordbody opslaan in de routed-regel. `sent 200` is de status
   van ONZE POST, niet PMT's oordeel over de order; routed_journal.py r. 23-27 zegt dat
   zelf en noemt die rijen "accepted orders", niet "fills". Rejected() leest die body al,
   en dan gooien we hem weg. Web noemt dit waardevoller dan de exit-poort en ik ben het
   daarmee eens: dit maakt de poort die we WEL hebben eerlijk.

3. D-69 — render.yaml start nog `uvicorn app.main:app` en dat bestand is verwijderd. Een
   deploy vanaf die blueprint crasht. Advies: verwijderen.

4. D-07 — registry wint (besluit Ferry 24-08), dus 0,37 voor MNQ/MES/MYM. Verifiëren
   tegen Cash_History.

5. Uit de review van D-70: de qty-override herschrijft `body` vóórdat de blocked- en
   risk-gate mogen weigeren, dus bij een reject journaliseer je een body met een multiplier
   die nooit verstuurd is. Overweeg de override ná de gates, of log de onbewerkte body.

Claim één item in docs/SPRINT.md vóór je begint. Raakt het het live executiepad, meld het
in docs/inbox.md vóór je pusht.
```

---

## 🟩 Pine Dev

```
git pull origin claude/middleware-setup-guide-afhvtk

Lees docs/SPRINT.md en docs/execution-flow.md (nieuw, D-70 — jullie f_sendExec staat er
prominent in). D-71 (het validFrom/validUntil-venster) staat op review en ziet er goed uit;
het annuleren van een openstaande limietorder op de grens was eigen initiatief en was
terecht — zonder dat is de entry-stop geen harde stop.

Eén consequentie die je moet weten, en die je niet kon voorzien: dit is een
gedragswijziging op dertien scripts, dus onder D-18 staat de OOS-klok voor de HELE vloot
opnieuw op nul, per 07-09. Dat is geen reden om iets terug te draaien — wel om nergens te
schrijven dat deze vloot out-of-sample bewezen is.

Werk in deze volgorde:
1. D-64 — MEX_EL_DORADO.pine compileert niet: firmPreset draagt `apex_intraday_pa`, een
   sleutel die niet in de registry bestaat. De fout zit in gen_pine_firms.py
   STRATEGY_DEFAULT, dus repareren in het .pine-bestand wordt bij de volgende run
   overschreven.
2. D-66 — de pariteitsvraag, samen met Backtest Setup. 9 van de 9 scripts verwijzen naar
   ta.requestVolumeDelta met useCVDFilter aan, terwijl de canonieke regel de OHLCV-proxy
   voorschrijft. MATADOR's data_parity spreekt dat tegen, dus er ontbreekt iets in het
   beeld. DIT GAAT VOOR D-63.
3. D-63 — her-export LEON en REY op de bron-config, PAS NA D-66. Drie correcties in één
   ronde: LEON → apex_50k_eod_pa · REY → dag-winstblok Off 500/150/750 · beide →
   commissie 0,37.
4. D-44 — breakeven_offset in f_pmtJSON. Staat op review; wacht op Ferry's PMT-check
   (Auto BreakEven = YES, risk type ≠ Price).
5. D-57 pas ná D-54.

Claim één item vóór je begint. D-44 en D-63 raken echte orders.
```

---

## 🟨 Backtest Setup

```
git pull origin claude/middleware-setup-guide-afhvtk

Lees docs/SPRINT.md en de ronde van 16-09 in docs/inbox.md. Er zijn twee dingen uit Pine
Dev's v3.4.0 (D-71) die direct jullie kant raken en die nog niet gerouteerd waren:

- De default van het handelsvenster schoof van 01-01-2025 naar 01-01-2026. Bestaande
  backtestbeelden worden dus KORTER zodra een script vervangen wordt. Dat raakt het
  exportvenster waar trap 1 tegen meet — check dit vóór D-54 en D-63, anders meet je
  straks tegen een ander venster dan je denkt.
- TradingView's datumkiezer leest in de EXCHANGE-tijdzone, niet in ET, terwijl onze hele
  sessie-logica op 18:00 ET hangt. Dat is precies de klasse fout die eerder de
  'naïeve kolom met utc=True'-bug opleverde.

Werk in deze volgorde:
1. 🔴 D-66 — de pariteitsvraag, samen met Pine Dev. Blokkeert D-63 en D-54.
2. D-68 — de vloot-pijplijn leest de accountregels niet uit de registry maar codeert ze
   hard: fleet.py:84, firms.py:255, en de stille fallback `or 2500` in higher.py:237 die
   bij een lege waarde terugvalt op precies de onjuiste waarde. Die laatste faalt niet,
   hij liegt zachtjes.
3. D-54 — zodra de her-exports van D-63 binnen zijn: trap 1, dan trap 8.
4. D-15, D-16, D-38, D-39, D-25 — in die volgorde als er ruimte is.
5. D-50 en D-27 staan op blocked; zeg het als dat niet meer klopt.

Claim één item vóór je begint. validation/ is append-only.
```

---

## 🟪 Web

```
git pull origin claude/middleware-setup-guide-afhvtk

Eerst dit: jullie route-check (inbox 34) was uitstekend werk. Statisch bewijs langs twee
onafhankelijke kanten, een falsifieerbare voorspelling erbij ("0% voor TP/SL/TRAIL/BE-STOP,
>0% voor administratief — wijkt de meting af, dan wint de data"), en een read-only script.
Dat heeft een ontwerpbesluit omgegooid: gate #12 uit execution-flow.md is niet bouwbaar en
staat nu als D-72 bij Ferry. De losse bevinding over PMT's antwoordbody staat als D-73.

Werk:
1. D-34 — de publieke claims. Nog steeds gedeblokkeerd, en er is één ding veranderd sinds
   je laatste ronde: de OOS-klok staat sinds 07-09 op nul voor de HELE vloot (D-71). Dus:
   "gevalideerd op drie jaar (2023-2026)" mag, "3 jaar out-of-sample" niet, en een
   ranglijst mag niet — die is er niet. Alleen MATADOR heeft een gesloten pariteitspoort,
   en ook dat cijfer wacht op een hertoets.
2. Als je tijd hebt: het route_check.py-script uit inbox 34 kan niet door jullie gedraaid
   worden (/root/intent-store staat op mex-mw-01). Zeg het als je wilt dat ik het bij
   Ferry of Middleware App neerleg.

Meld het in docs/inbox.md als D-34 af is; de review loopt via de Scrum Master.
```
