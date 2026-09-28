# Startprompts per chat — ronde 28-09b · **fase 0 is af**

_Eigenaar: Scrum Master. Watermerk: `abe75a6`+, 28-09._

🔴 **Lees eerst `docs/PLAN-2026-09-27-herijking.md`.** Het bord is op 27-09 volledig herzien:
12 items geparkeerd, 7 opgegaan in een fase, 4 afgesloten, 29 nieuwe. Staat jouw item er niet
meer, kijk dan in `docs/ARCHIVE.md` vóór je het opnieuw oppakt.

## Wat er sinds gisteren is veranderd

- ✅ **Fase 0 is opgeleverd.** `docs/schema-event.md` (D-77) en `docs/schema-config.md` (D-78)
  staan op review. **Fase 1 start zodra die review rond is** — daarna is de volgorde dwingend.
- ✅ **Ferry heeft route B gekozen** (D-77 §3): **Pine blijft de Discord-tekst schrijven**, de
  middleware bepaalt alleen de bestemming. De ~20 kaartsjablonen blijven dus waar ze zijn.
- ✅ **T3 is bewezen.** Eigen FIFO-koppeling op Ferry's echte fills reproduceert de
  Apex-balans tot op de cent, voor alle tien de accounts. Geen Tradovate-API nodig.
- ✅ **D-44 dicht** (Ferry: *"die werkt al"*). **D-104** heeft een scope gekregen die veel
  kleiner is dan gedacht.

## Drie vondsten die iedereen moet kennen

**1. De canonieke route bestaat al, half.** Pine heeft een **zesde** routetoggle naast de vijf
die we kenden — `routeMiddleware` (r. 972) met `mwSecret` en `mwStrategy` — en `f_sendExec`
stuurt daar al een bericht heen met `secret · strategy · event · action · symbol · price ·
order_type · dollar_sl · dollar_tp · qty`. Hij doet niets omdat hij gericht was op
`accounts.yaml` (de Python-route, verwijderd in D-05) en omdat de .NET-receiver hem niet
herkent: hij valt door naar de Fase C-tak, die `node["account"]` leest terwijl dat veld er
niet in zit. **Fase 3 wordt hiermee kleiner.**

**2. De middleware raadt firma en fase uit de accountnáám.** `NotifyRoute` doet
`StartsWith("PA") → FUNDED` en `Contains("APEX") → APEX`. Dat werkt vandaag bij toeval omdat
élk account `PAAPEX…` heet, en het breekt zodra Blue Guardian, Top One of TradeDay erbij
komen. Het kan nu al Legacy 50K, Legacy 250K en Intraday 50K niet uit elkaar houden —
terwijl die **andere regels** hebben (consistency 30% tegen 50%, geverifieerd).

**3. Er draaiden twee widget-scripts.** De D-76-fix van 18-09 landde in het bestand dat Ferry
niet draait. De bevinding eronder klopte; alleen het bestand was fout.

⚠️ **En twee correcties op mijn eigen werk, omdat er een les in zit die jullie kunnen gebruiken:**
- Ik rekende eerst met **één puntwaarde voor alle producten**. De volledige fills-exports
  bevatten naast MGC ook NQ, MNQ en MYM, en met $10 voor alles kwam PA022 op −$4.436 uit waar
  het +$2.671 moest zijn. **Koppel per product, en haal de puntwaarde uit de registry.**
- Ik zei *"alle accounts handelen uitsluitend MGC"*. Dat gold alleen voor het
  september-venster.

---

## 🟦 Middleware App (chat: **App Setup**) — de widget is vrijgegeven

```
git pull origin claude/middleware-setup-guide-afhvtk

DOE NU — D-105, DE WIDGET. Ferry heeft dit 28-09 vrijgegeven.

BRON VASTGESTELD: MEX_Today.js wordt het script. Een kopie staat in
docs/widget-MEX_Today-2026-09-28.js.txt; die hoort thuis in jullie map.
middleware/scriptable/mex-fleet-widget.js gaat naar het archief met een notitie.

⚠️ Waarom: er draaiden twee widget-scripts met verschillende standen
(today/yesterday/week/total tegenover week/funded/eval/all) op hetzelfde endpoint.
De D-76-fix van 18-09 landde in het bestand dat Ferry NIET draait. De bevinding eronder
klopte wel en is in MEX_Today.js al correct toegepast: net leest top-level `today`
(vloot-breed), de splitrij leest stacks.funded.today en stacks.eval.today.

VIER STAPPEN, in deze volgorde:

1. MEX_Today.js opnemen in middleware/scriptable/ als de bron. De ander archiveren met
   een notitie waarom — niet weggooien.

2. 🔴 DE EVAL-SPLITRIJ TOONT EEN BEDRAG. split.a = moneyK(t.ev), dus dollars voor de
   eval-stack. Dat is precies wat Ferry op 05-09 aanwees en het loopt vandaag nog door.
   Eval krijgt ACCOUNTONTWIKKELING: passed/breached genormaliseerd naar 50k-equivalent.
   Web leverde for_public_evals() al en ik heb die functioneel nagemeten (1x50k + 1x100k
   passed = 3,0; 300k breached = 6,0; geneste lekken worden gevangen). Die telling
   ontbreekt alleen nog in /api/widget: stack() in viewer.py:281 geeft wel `accounts`
   en `breached`, niet de genormaliseerde tellers. Dat API-veld hoort bij deze ronde —
   jullie bezitten beide kanten, doe het in één keer.

3. 🔴 "yesterday" IS NIET "laatste handelsdag". Op maandag is gisteren zondag en toont de
   widget "No data / Yesterday missing". Ferry vroeg om vandaag · laatste handelsdag ·
   week · overall. Er is een venster nodig dat de laatste dag MET activiteit pakt.

4. De Eval/Funded-splitrij bestaat alleen in today en yesterday; hij hoort ook in week
   en total.

NIET MEENEMEN: de herkomstlabels (T1/T2/T3, verified/unverified). Die komen in D-93 en
vragen een API-veld dat pas na de meting van D-73 bestaat.

DAARNA: D-73 — leg 20 echte PMT-antwoordbodies vast en beoordeel wat erin staat. Nu T3
bewezen is, is T2 de enige laag waarvan we niets weten. Ontwerp niets op T2 tot die
meting er ligt.

OOK VAN JULLIE GEVRAAGD (review, kost een half uur):
- docs/schema-event.md (D-77): is elke huidige uitgaande payload hieruit te bouwen?
  Toets op een echt bericht per route, niet op papier.
- docs/schema-config.md (D-78): heeft elke huidige env-instelling hierin een plek?
  Meld wat ontbreekt. Let op §5 (geheimen worden verwijzingen, geen waarden) en op §6
  (caps zijn bewust een tweede plek naast Tradovate en moeten als zodanig gelabeld).

VOORUITBLIK D-92, zodat je niet twee keer bouwt — drie dingen die de koppelstap MOET doen:
- Koppel PER PRODUCT met de puntwaarde uit de registry. Eén bestand bevat meerdere
  contracten en een gedeelde FIFO-wachtrij koppelt MGC tegen NQ.
- Een PAYOUT verlaagt de balans maar staat NIET in de fills. Dat is een aparte invoer.
  Stand 28-09: één payout in de hele vloot (PA013 #1, $1.500, 10-09).
- In de volledige exports is buy != sell: er staan posities open aan de rand van het
  venster. RAPPORTEER dat, poets het niet weg.
```

---

## 🟩 Backtest Setup — D-104 is klein en concreet geworden

```
git pull origin claude/middleware-setup-guide-afhvtk

DOE NU:

1. 🔴 D-104 — data/propfirms.json uitbreiden. Ferry heeft de scope 28-09 vastgelegd:
   "waar mogelijk altijd 50k accounts; voor Apex Legacy 50k en 250k, plus 2 x 50k Intraday."
   Dus per firma ALLEEN het 50K-programma (eval -> funded), en voor Apex drie: Legacy 50K,
   Legacy 250K, Intraday 50K. Apex staat al grotendeels in de registry. Het echte werk is
   zeven 50K-programma's, waarvan drie bij firma's die er nog helemaal niet in staan:
   Blue Guardian, Top One, TradeDay. Die drie eerst.
   Per programma nodig voor D-96: trailing drawdown · lock-drempel en -offset · DLL en de
   SL-multiple · consistency-PERCENTAGE · cyclus in handelsdagen · kwalificatiedagen en de
   minimumdag · payout-ladder · platform(en).
   🔴 Het consistency-percentage VERSCHILT per programma — Apex legacy 30%, Intraday 4.0 50%.
   Beide zijn 28-09 geverifieerd tegen Ferry's fleet-doc en klopten exact op drie accounts.
   Eén verkeerd percentage geeft een plausibele en onjuiste payout-datum.
   ⚠️ Dit blokkeert nu twee dingen: D-78 kan pas volledig geldig zijn als elk `program`
   naar een bestaande registry-sleutel resolvet, en D-96 faalt per ontwerp hard op een
   ontbrekende regel. Gedeelde bron: volg data/propfirms.schema.json, draai daarna
   python tools/gen_pine_firms.py, en meld het in docs/inbox.md.

2. D-100 — spoor B, de inventarisatie: welk deel van Pine gebruiken de 13 scripts echt?
   Lever een lijst met functies, ingebouwde variabelen en constructies, met frequentie.
   Dat bepaalt of D-101 weken of maanden is. D-66 is hierin opgegaan en vervalt; daarmee
   vervalt ook de keten D-63 -> D-54 -> D-57.

3. D-68 — fleet.py:84 codeert acct_trail_dd=2000 en acct_dll=1000 hard; higher.py:237 valt
   STIL terug op 2500. Lees uit de registry en faal HARD bij een ontbrekende regel. Doe dit
   in dezelfde ronde als D-104 — zelfde bron, en fase 5 bouwt straks dezelfde regel aan de
   webapp-kant.
```

---

## 🟨 Pine Dev — review gevraagd, en één vondst die jullie aangaat

```
git pull origin claude/middleware-setup-guide-afhvtk

🔴 VONDST DIE IN JULLIE MAP LIGT: de canonieke route bestaat al, half.
MEX_EL_MATADOR_MES_PROD_EOD_v1_0_0.pine heeft een ZESDE routetoggle naast de vijf die we
kenden: routeMiddleware (r. 972), met mwSecret (r. 970) en mwStrategy (r. 971). f_sendExec
stuurt daar al een bericht heen (r. 1864) met secret/strategy/event/action/symbol/price/
order_type/dollar_sl/dollar_tp/qty. Dat is bijna het canonieke event uit D-77.
Hij doet vandaag niets omdat (a) de tooltip van mwStrategy verwijst naar accounts.yaml — de
dode Python-route, verwijderd in D-05 — en (b) de .NET-receiver het bericht niet herkent en
het laat doorvallen naar de Fase C-tak, die node["account"] leest terwijl dat veld er niet
in zit. Het belandt met een LEEG accountveld in intents_<datum>.jsonl.
Gevolg: fase 3 wordt kleiner. Pine krijgt geen nieuwe route, alleen een vollediger bericht
op een route die er al ligt.

DOE NU:

1. D-77 REVIEW — lees docs/schema-event.md en toets één ding: is elk verplicht veld uit een
   script te produceren? Velden: v · id (idempotentiesleutel) · ts · strategy · symbol ·
   kind · action · qty · price · order_type · dollar_sl · dollar_tp · text.title ·
   text.body · journal.* (de zestien kolommen van de huidige journaalregel).
   Kan er iets niet, dan wil ik dat NU weten en niet in fase 3.
   ✅ Ferry koos route B: jullie blijven de Discord-tekst schrijven. De ~20 kaartsjablonen
   blijven dus in Pine; het event draagt ze als text.title/text.body.

2. D-103 — spoor C, "alleen versies". Leg vast welke versie van elk script op TradingView
   draait, met datum en een korte reden. Handmatig plakken blijft zoals het is. Conventie
   plus een bestand, geen bouwwerk.

AFGEROND: D-44 is dicht — Ferry 28-09: "die werkt al."

VOORUITBLIK FASE 3: D-86 haalt 9 instellingen uit elk van 13 scripts (routePMT,
routeRithmic, routePineConnector, routeDiscord, routeJournal, pmtToken, pcLicense,
pcSymbol, accountID). GEEN wijziging aan entry-, exit- of risicologica. Ferry besloot dat
de OOS-klok daarvoor niet op nul gaat — maar dat besluit staat of valt met een diff die
aantoont dat uitsluitend de plumbing wijzigde. Lukt dat niet, dan gaat de klok alsnog op
nul voor de hele vloot.
```

---

## 🟪 Web — nog steeds bewust niets, en nu met een datum

Fase 2 (D-83, D-84) kan pas als de config-store van fase 1 er is. Fase 1 start zodra de
review van D-77 en D-78 rond is. **Wel alvast lezen:** `docs/schema-config.md` §2 en §3 —
dat is letterlijk wat jullie straks als scherm bouwen, in twee niveaus. En §5: **tokens
worden verwijzingen, geen waarden.** Het scherm toont `apex_pmt · ✓ gezet · gewijzigd 12-09`
en een veld om te vervangen, nooit de waarde zelf.

Eén ding om nu al te laten bezinken: **met dit scherm wordt de webapp onderdeel van het live
executiepad.** Vandaag toont een fout daar een verkeerd getal; straks stuurt hij een order
naar het verkeerde account. Dat verandert wat "af" betekent.
