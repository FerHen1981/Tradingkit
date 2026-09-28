# Startprompts per chat — ronde 28-09

_Eigenaar: Scrum Master. Watermerk: `abe75a6`, 28-09._

🔴 **Lees eerst `docs/PLAN-2026-09-27-herijking.md`.** Het bord is op 27-09 volledig herzien:
12 items geparkeerd, 7 opgegaan in een fase, 4 afgesloten, 27 nieuwe. Staat jouw item er niet
meer, kijk dan in `docs/ARCHIVE.md` voor de reden vóór je het opnieuw oppakt.

**Nieuw sinds gisteren, en het raakt bijna iedereen:** Ferry leverde echte Tradovate-fills
(13 exports, ~3.200 fills, PA013 t/m PA029) en zijn handmatige fleet-startschema. Daarmee is
**T3 bewezen haalbaar** — eigen FIFO-koppeling op de ruwe fills reproduceert de Apex-balans
tot op de cent, voor alle tien de accounts. Er is geen Tradovate-API nodig. Details in
`docs/DECISIONS.md` 28-09 en `docs/fleet-report-spec.md`.

⚠️ **Twee correcties op mijn eigen werk, omdat ze een les bevatten die jullie kunnen gebruiken:**
- Ik rekende eerst met **één puntwaarde voor alle producten**. De volledige exports bevatten
  naast MGC ook NQ, MNQ en MYM, en met $10 voor alles kwam PA022 op −$4.436 uit waar het
  +$2.671 moest zijn. **Koppel per product, en haal de puntwaarde uit de registry.**
- Ik zei *"alle accounts handelen uitsluitend MGC"*. Dat gold alleen voor het
  september-venster; over de volle historie is het overwegend maar niet uitsluitend MGC.

---

## 🟦 Middleware App (chat: **App Setup**) — nu drie dingen, en de eerste is nieuw

```
git pull origin claude/middleware-setup-guide-afhvtk

Lees docs/PLAN-2026-09-27-herijking.md en het nieuwe docs/SPRINT.md. Fase 1 (D-79/D-80/D-81)
is voor jullie maar wacht op D-77 en D-78; die schrijf ik nu.

DOE NU, in deze volgorde:

1. 🔴 D-105 — ER ZIJN TWEE WIDGET-SCRIPTS EN WE WETEN NIET WELKE DRAAIT.
   Ferry leverde MEX_Today.js als "volgens mij de laatste versie" — vier standen
   today/yesterday/week/total, met een eigen Eval/Funded-splitrij. Het repo-bestand
   middleware/scriptable/mex-fleet-widget.js kent week/funded/eval/all: andere standen,
   andere rijen, zelfde endpoint. Een kopie van Ferry's versie staat in
   docs/widget-MEX_Today-2026-09-28.js.txt — pak die op, hij ligt in jullie map thuis.
   ⚠️ Gevolg dat je meteen moet meenemen: de D-76-fix van 18-09 ging naar het repo-bestand
   en heeft Ferry's telefoon waarschijnlijk nooit bereikt. Dit is het dubbele-implementatie-
   patroon: wie als eerste merget maakt het werk van de ander tot dode code.
   Stappen: (1) stel vast welk script hij werkelijk draait en maak dát de bron in
   middleware/scriptable/; (2) archiveer de ander met een notitie, gooi niets weg;
   (3) pas dan de wijziging die Ferry vraagt: funded -> saldo-ontwikkeling in dollars,
   eval -> accountontwikkeling ZONDER bedragen (D-74), en de splitsing ook in week en total
   waar hij nu ontbreekt. De eval-splitrij toont vandaag moneyK(t.ev) — een bedrag — en dat
   is precies wat Ferry op 05-09 aanwees.

2. 🔴 D-73 — DE METING WAAR HEEL T2 OP RUST, en die is nu urgenter geworden.
   Nu T3 bewezen is, is T2 de enige laag waarvan we niets weten. Leg 20 echte
   PMT-antwoordbodies vast en beoordeel wat erin staat: een fill-prijs, of alleen een
   bevestiging? Ontwerp niets op T2 tot die meting er ligt.

3. D-69 — de Render-blueprint deployt middleware/app/main.py, dat bestaat niet meer.

VOORUITBLIK OP D-92 (fase 4), zodat je niet twee keer bouwt. Het formaat staat vast en is
uitgeschreven op het bord. Drie dingen die de koppelstap MOET doen en die je anders mist:
- Koppel PER PRODUCT met de puntwaarde uit de registry. Eén bestand bevat meerdere
  contracten en een gedeelde FIFO-wachtrij koppelt MGC tegen NQ.
- Een PAYOUT verlaagt de balans maar staat NIET in de fills. Payout-registratie is een
  aparte invoer; zonder die krijg je de balans nooit sluitend.
- In de volledige exports is buy != sell (1251/1254, 970/974, 472/474): er staan posities
  open aan de rand van het venster. RAPPORTEER dat, poets het niet weg.
```

---

## 🟩 Backtest Setup — D-104 is nu klein en concreet

```
git pull origin claude/middleware-setup-guide-afhvtk

DOE NU:

1. 🔴 D-104 — data/propfirms.json uitbreiden. Ferry heeft de scope 28-09 vastgelegd en die
   is veel kleiner dan "acht firma's compleet": "waar mogelijk altijd 50k accounts; voor
   Apex Legacy 50k en 250k, plus 2 x 50k Intraday."
   Dus: per firma ALLEEN het 50K-programma (eval -> funded), en voor Apex drie —
   Legacy 50K, Legacy 250K, Intraday 50K. Apex staat al grotendeels in de registry.
   Het echte werk is zeven 50K-programma's, waarvan drie bij firma's die er nog helemaal
   niet in staan: Blue Guardian, Top One, TradeDay. Die drie eerst.
   Per programma minimaal nodig voor D-96: trailing drawdown · lock-drempel en -offset ·
   DLL en de SL-multiple · consistency-PERCENTAGE · cyclus in handelsdagen ·
   kwalificatiedagen en de minimumdag · payout-ladder · platform(en).
   🔴 Het consistency-percentage VERSCHILT per programma — Apex legacy rekent 30%, Intraday
   4.0 rekent 50%. Beide zijn op 28-09 geverifieerd tegen Ferry's fleet-doc en klopten
   exact. Eén verkeerd percentage geeft een plausibele en onjuiste payout-datum.
   Gedeelde bron: volg data/propfirms.schema.json, draai daarna
   python tools/gen_pine_firms.py, en meld het in docs/inbox.md.

2. D-100 — spoor B, de inventarisatie: welk deel van Pine gebruiken de 13 scripts echt?
   Lever een lijst met functies, ingebouwde variabelen en constructies, met frequentie.
   Dat bepaalt of D-101 weken of maanden is. D-66 is hierin opgegaan en vervalt.

3. D-68 — fleet.py:84 codeert acct_trail_dd=2000 en acct_dll=1000 hard; higher.py:237 valt
   STIL terug op 2500. Lees uit de registry en faal HARD bij een ontbrekende regel.
   Doe dit in dezelfde ronde als D-104 — het is dezelfde bron.
```

---

## 🟨 Pine Dev — klein deze ronde

```
git pull origin claude/middleware-setup-guide-afhvtk

DOE NU:

1. D-103 — spoor C, "alleen versies". Leg vast welke versie van elk script op TradingView
   draait, met datum en een korte reden. Handmatig plakken blijft zoals het is. Conventie
   plus een bestand, geen bouwwerk.

2. D-77 — input op het canonieke event-schema. Ik schrijf het; jullie toetsen één ding:
   is elk veld uit een Pine-script te produceren? Velden: strategie-id, account-sleutel,
   richting, type (entry/exit/halt/derisk/info), prijs, stop, target, tijdstempel,
   gebeurtenis-id. Kan er iets niet, dan wil ik dat nu weten en niet in fase 3.

AFGEROND: D-44 is dicht — Ferry 28-09: "die werkt al." De BE-offset bereikt de broker.

VOORUITBLIK FASE 3: D-86 haalt 9 instellingen uit elk van 13 scripts. GEEN wijziging aan
entry-, exit- of risicologica; de OOS-klok blijft alleen op nul staan als we met een diff
kunnen aantonen dat uitsluitend de plumbing wijzigde.
```

---

## 🟪 Web — nog steeds bewust niets

Fase 2 (D-83, D-84) kan pas als de config-store van fase 1 er is, en die wacht op mijn twee
schema's. Vooruitbouwen is bouwen tegen een schema dat nog vastgesteld wordt.
