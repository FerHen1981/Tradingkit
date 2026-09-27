# Startprompts per chat — ronde 27-09 · **na de herijking**

_Eigenaar: Scrum Master. Watermerk: `1144057`, 27-09._

🔴 **Het bord is volledig herzien.** Lees `docs/PLAN-2026-09-27-herijking.md` vóór je iets
claimt. Van de 33 openstaande items zijn er 12 geparkeerd, 7 opgegaan in een fase en 4
afgesloten; er staan 27 nieuwe items op. **Wat je gisteren op je lijstje had, staat er
mogelijk niet meer** — kijk in `docs/ARCHIVE.md` voor de reden voordat je het opnieuw
oppakt.

**Fasen zijn dwingend.** Claim geen item uit fase 3 zolang fase 1 en 2 niet af zijn. De
parallelsporen B en C lopen ernaast en mogen altijd.

**Waar we nu staan:** fase 0 is van de Scrum Master en loopt (D-77 en D-78, de twee
schema's). Zolang die niet vastliggen kan fase 1 niet beginnen — dat is bewust: als het
event-schema tijdens fase 2 alsnog gaat schuiven, moet fase 1 opnieuw.

---

## 🟦 Middleware App (chat: **App Setup**) — twee dingen die nu al kunnen

```
git pull origin claude/middleware-setup-guide-afhvtk

Lees eerst docs/PLAN-2026-09-27-herijking.md, daarna het nieuwe docs/SPRINT.md.
Fase 1 (D-79/D-80/D-81) is voor jullie, maar die start pas als D-77 en D-78 vastliggen.
Twee dingen kunnen wél nu, en het eerste is belangrijker dan het lijkt.

DOE NU:

1. 🔴 D-73 — DE METING WAAR HEEL T2 OP RUST. Dit item is bij de herijking gepromoveerd
   van opruimwerk tot fundament. Leg 20 echte PMT-antwoordbodies vast en beoordeel wat
   erin staat: bevat de body een fill-prijs, of alleen een bevestiging dat de order is
   aangenomen? Niemand heeft dat ooit gemeten. Het antwoord bepaalt of de bevestigingslaag
   (T2) een prijs kan dragen of alleen een status — en dus hoe dicht de webapp bij "live"
   kan komen zonder Tradovate-API. Ontwerp niets op T2 tot deze meting er ligt.

2. D-74 — jullie helft, maar NU SMALLER. Het volledige labelsysteem verhuist naar D-93 in
   fase 4. Wat overblijft is het stuk dat vandaag fout gaat: de eval-stand van
   mex-fleet-widget.js rendert realized en buffer IN DOLLARS, en dat is precies wat Ferry
   op 05-09 aanwees. Haal de bedragen daar weg en zet er de genormaliseerde tellers neer.
   Meer niet — de verified/unverified-labels komen later en met een API-veld dat er nog
   niet is.

REVIEW (kort, als je toekomt): D-69 — de Render-blueprint deployt middleware/app/main.py,
dat bestaat niet meer. Repareren of weghalen, maar niet laten staan alsof het werkt.

NIET AAN BEGINNEN: alles met een fasenummer 1 t/m 7 behalve D-73. De volgorde is er om te
voorkomen dat we twee keer bouwen.
```

---

## 🟩 Backtest Setup — spoor B, en dit is de grootste meting van het plan

```
git pull origin claude/middleware-setup-guide-afhvtk

Lees docs/PLAN-2026-09-27-herijking.md, spoor B. Ferry heeft besloten (antwoord 14) dat de
backtester het .pine-bestand ZELF moet lezen en dat resultaat door de hele molen moet.
Dit spoor loopt parallel aan alles en blokkeert niets.

⛔ HARDE REGEL: dit spoor komt niet in middleware/** of web/**.

DOE NU:

1. D-100 — INVENTARISEER welk deel van Pine onze scripts werkelijk gebruiken. De 13
   scripts van de v1_0_0-lijn komen uit één familie, dus de kans is groot dat de gebruikte
   taalconstructies een beperkte, opsombare verzameling zijn. Lever een lijst: welke
   functies, welke ingebouwde variabelen, welke taalconstructies, en hoe vaak elk voorkomt.
   Dat bepaalt of D-101 een project van weken of van maanden is — dus meet het vóórdat er
   iets ontworpen wordt.

   ➡️ D-66 (de CVD-pariteitsvraag) IS HIERIN OPGEGAAN EN VERVALT. Is er straks één
   implementatie, dan valt er geen pariteit meer te bewaken. Daarmee vervalt ook de keten
   D-63 → D-54 → D-57 die erachter stond. Begin er niet meer aan.

2. D-68 — blijft staan en is nu extra relevant: fleet.py:84 codeert acct_trail_dd=2000 en
   acct_dll=1000 hard, en higher.py:237 valt STIL terug op 2500. Lees uit
   data/propfirms.json en laat het HARD falen als een regel ontbreekt. Fase 5 bouwt
   dezelfde regel aan de webapp-kant; als jullie het hier goed zetten is dat daar een
   kopieerslag in plaats van een ontwerpronde.

NIET AAN BEGINNEN: D-54, D-15, D-16, D-25, D-38, D-39, D-50, D-27 — geparkeerd tot het
platform staat. Zie docs/ARCHIVE.md.
```

---

## 🟨 Pine Dev — spoor C nu, fase 3 later

```
git pull origin claude/middleware-setup-guide-afhvtk

Lees docs/PLAN-2026-09-27-herijking.md. Fase 3 is jullie grote werk — de kanaalrouting uit
alle 13 scripts halen — maar die start pas als fase 1 en 2 staan. Twee dingen nu.

DOE NU:

1. D-103 — spoor C, "alleen versies" (Ferry, antwoord 12). Leg vast welke versie van elk
   script op TradingView draait, met datum en een korte reden. Handmatig plakken blijft
   zoals het is (antwoord 13). Dit is een conventie plus een bestand, geen bouwwerk —
   houd het klein.

2. D-77 — lever input op het canonieke event-schema. Ik schrijf het, jullie toetsen één
   ding: is elk veld uit een Pine-script te produceren? Velden: strategie-id, account-
   sleutel, richting, type (entry/exit/halt/derisk/info), prijs, stop, target, tijdstempel,
   gebeurtenis-id. Kan er iets niet, dan wil ik dat nu weten en niet in fase 3.

VOORUITBLIK OP FASE 3, zodat je weet wat eraan komt: D-86 haalt 9 instellingen uit elk van
13 scripts (routePMT, routeRithmic, routePineConnector, routeDiscord, routeJournal,
pmtToken, pcLicense, pcSymbol, accountID). 🔴 Daarbij geldt: GEEN enkele wijziging aan
entry-, exit- of risicologica. Ferry heeft besloten dat de OOS-klok hiervoor niet op nul
gaat, maar die beslissing staat of valt met een diff die aantoont dat alleen de plumbing
wijzigde. Kunnen we dat niet aantonen, dan gaat de klok alsnog op nul voor de hele vloot.

NIET AAN BEGINNEN: D-64 en D-63 zijn geparkeerd. D-44 staat op review en de fix zelf ligt
bij Ferry in het PMT-dashboard.
```

---

## 🟪 Web — deze ronde bewust niets

Jullie werk zit in **fase 2** (D-83 en D-84, de settings-tab in twee niveaus) en dat kan
pas als de config-store van fase 1 er is. Vooruitbouwen zou betekenen: bouwen tegen een
schema dat nog vaststaat te worden.

Wat je wél kunt doen als je wilt vooruitkijken: lees `docs/PLAN-2026-09-27-herijking.md`
§2.1 en §4-fase-2. Eén punt is belangrijk om nu al te laten bezinken — **met de settings-tab
wordt de webapp onderdeel van het live executiepad**. Vandaag toont een fout daar een
verkeerd getal; straks stuurt hij een order naar het verkeerde account. Dat verandert wat
"af" betekent voor dat scherm.

---

## 🧑‍✈️ Ferry

**1. D-53 nog steeds uitrollen.** Bij de herijking is besloten dat contracten in Pine
blijven (antwoord 9), waardoor de qty-override een **vangnet** is en geen besturingsknop.
Dat maakt hem niet minder nuttig — een vangnet dat niet geïnstalleerd is, vangt niets.

```bash
cd /root/mex-middleware-b
dotnet build src/Mex.Journal.Receiver -c Release
# zet in de EnvironmentFile: MEX_ACCOUNT_QTY=<account>=1,...
systemctl restart mex-receiver
```

**2. Het eerste dat ik van je nodig heb voor fase 4:** één wekelijkse Tradovate fills-CSV,
zodat we het formaat kunnen lezen vóórdat we de import ontwerpen. Eén bestand is genoeg.

**3. Blijft staan, wanneer het uitkomt:** D-44 (PMT-dashboard: Auto BreakEven = YES,
risicotype ≠ `Price`) · D-11 (secrets roteren — verandert in fase 2 van karakter) ·
D-31 (snapshot-timer + het verlopen GitHub-token) · D-58 (default branch).
