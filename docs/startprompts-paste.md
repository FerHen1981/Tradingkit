# Paste-klare startprompts — ronde 08-10 (avond) · Pine Dev-blok (v3.13.8) en Middleware-blok (D-163) vervangen 04-11 · D-165 toegevoegd 05-11

_Eigenaar: Scrum Master. Eén blok per chat, letterlijk plakken. Eén release van maximaal
een dag per chat, met een acceptatietest (besluit Ferry 08-10: kleine releases boven
fase-brokken). **Rollen zonder eigen map staan ook in de ronde**, ook als het antwoord
"niets deze ronde" is._

> **Wat er sinds de vorige ronde is gebeurd en iedereen moet weten:**
> 1. 🔴 **Er is nu echte MGC-data** (3 jaar, 1.053.095 1-minuutbalken). Het GC-twin-voorbehoud
>    dat op elk goudoordeel stond, geldt voor metingen op deze set **niet meer**.
> 2. 🔴 **De config die live op EL TESORO draait is over drie jaar netto −$27.377** bij PF 0,96
>    en 49 breaches. De +$13.885 van anderhalve maand was een goede plek in een verliezende
>    verdeling. **De bevroren config is op diezelfde drie jaar nóg slechter** (−$28.413).
> 3. 🔴 **De tijdvensters doen het meeste werk.** US 07:00–12:00 en Globex 18:00–19:00 staan aan
>    en verliezen; Asia 19:00–02:00 staat uit en verdient. `Asia + London` geeft **+$16.752 bij
>    14 breaches** tegen −$27.377 bij 49. Nog geen edge (PF 1,04, 2024 is een verliesjaar),
>    maar het is de grootste enkele knop die we gemeten hebben.
> 4. 🔴 **De datasetpoort (`tools/validate_dataset.py`) is kapot op drie punten** en meldde
>    verzonnen structuurcijfers. Elke dataset die er ooit door ging, is zo gekeurd.
> 5. ⚠️ **Twee secrets lekken via TradingView-exports** — zie het blok van Pine Dev.
> Volledige cijfers en onderbouwing: D-149 t/m D-154 in `docs/SPRINT.md`.

---

## 🟨 Pine Dev

```
git pull origin claude/middleware-setup-guide-afhvtk
Lees in docs/inbox.md item 52 (SM, 04-11) en D-161 in docs/SPRINT.md.

RELEASE v3.13.8 — één ding, gemeten, geen nieuwe diagnose:
Ferry heeft de v3.2.0-bron (26-08) aangeleverd waarop de tekeningen WEL aan de prijs
blijven zitten. Dat is de referentie die vier rondes ontbrak. In git is de tekenlogica
byte-identiek van v3.2.0 t/m v3.12.0. De diff van alle box.*/label.*/scale-regels tussen
v3.2.0 en jouw v3.13.7, minus zelfcontrole en waarschuwingslabels, is precies dit:
  (1) scale=scale.right in strategy() — v3.13.2, het enige rendering-verschil;
  (2) geometrie: exit-label op _x1 i.p.v. _xm · tekstblok verankerd op de entry-bar
      (label_left) i.p.v. bar_index + 2 met set_xy per bar · vak uit zoneStopPx met
      bevroren top/bottom i.p.v. uit curStop en de live stop volgend · bij de exit
      hertekenen uit closedtrades.* + label.set_xy(_cb0) i.p.v. alleen box.set_right.
Verder niets. Let op: jouw v3.13.6-oorzaak (dubbele uitvoering per bar) staat OOK in
v3.2.0 — newLong is daar hetzelfde [1]-patroon — en v3.2.0 werkt. Die latch is juist,
maar kan niet de hele verklaring zijn.

DOEN: op v3.13.7 de geometrie exact terug naar v3.2.0 (de vijf regels hierboven) en
scale=scale.right eruit. BLIJVEN: drawMadeNo/drawShutSeen, drawTradeNo/zoneTradeNo,
loslaten bij exit, DRAW≠TRADE, en de meetlaag in de tabel. Dan is het script op
tekenniveau gelijk aan de versie die werkt, plus een tabel die zegt of het klopt.
Acceptatie: diff van de tekenregels v3.2.0 ↔ v3.13.8 = alleen zelfcontrole, meetlaag,
vensterkleur en waarschuwingslabels (de SM draait die diff na) · poorten groen ·
DEPLOYED.md op v3.13.8 · geen OOS-reset. Losse commit, DEPLOYED.md per tabel apart.

NOG OPEN BIJ FERRY: na het plakken de regel DRAW uit de tabel voorlezen, en één
schermafdruk mét scripttitel. OK n/n + beeld nog fout = chart (schaal van het symbool,
tweede instantie v3.10, opgeslagen input), niet code.
```

---

## 🟧 Analyses & Data

```
git pull origin claude/middleware-setup-guide-afhvtk
Lees D-152, D-153 en de pariteitsregel van 08-10 in docs/DECISIONS.md.
Jullie dagstop-notitie is omgezet in D-154 en staat bij Pine Dev op het bord.

DRIE DINGEN, en het eerste is nieuw voor jullie.

(1) A-93 zegt dat geen regime-filter vóór de entry winnaars van verliezers scheidt, en
noemt volume, ATR, VWAP-afstand, trend, weekdag en dagbereik. SESSIEVENSTERS staan niet in
die lijst, en daar zit wel iets. Gemeten op Ferry's echte 3-jaars MGC-set, zijn live
config, accountregels aan, enabled_hours echt beperkt (geen toerekening):
  All sessions (nu live)   5745 tr   -27.377   PF 0,96   49 breaches
  Liquidity Core (bevroren) 4060 tr  -28.413   PF 0,95   37 breaches
  Liquidity Core + Asia    4953 tr   -17.076   PF 0,97   40 breaches
  Asia + London            2989 tr   +16.752   PF 1,04   14 breaches
  Asia alleen              2183 tr   +13.072   PF 1,04   13 breaches
US 07-12 verliest in alle vier de jaren, Globex 18-19 in drie van vier.
Jullie conclusie "de verliezers zitten in het dagpad" is daarmee niet weerlegd maar wel
incompleet: een deel zit in twee vooraf gedefinieerde sessievensters die nu aan staan.
GEVRAAGD: de dagstops EN de vensterset samen meten. Niemand heeft die combinatie gedraaid,
en beide verlagen de breach-kans - dus of ze elkaar aanvullen of overlappen is onbekend.
Meetlat blijft de jullie: kans op de volgende trede binnen 40-60 dagen tegen breach-kans.

(2) D-153 - tools/validate_dataset.py heeft drie defecten, gevonden op Ferry's bestand:
hij parseert het canonieke formaat van de repo verkeerd (geen dayfirst, 36,7% van de
regels), hij ziet een constante UTC-offset over een DST-grens niet, en zijn aliastabel kan
een Volume-kolom pakken die overal 0 is. Hij meldde 1.473 dubbele tijdstempels waar er nul
zijn en 28 gaten >3 dagen waar het 6 zijn. Fix hoort in backtest/** - zie inbox 38.
Belangrijk voor jullie werk: elke dataset die ooit door die poort is gegaan, is zo gekeurd.

(3) Jullie melden de Pine-pariteit op MGC als GESLOTEN (3.566 vs 3.627 trades, 92%
gepaarde entries). Het bord draagt TESORO's poort nog als OPEN, en daarop heb ik D-152 als
"indicatief" gelabeld. Mijn onafhankelijke controle wijst dezelfde kant op (23
overlappende dagen: Python 281 tr/+$8.848/59,8% tegen Pine 293/+$8.299/59,4%, 248 van 293
entries op dezelfde minuut). Ik zet die poort NIET om op twee losse metingen die dezelfde
kant op wijzen - lever de audit-uitvoer van de pijplijn, dan verwerk ik het op het bord.

Push gerust op je eigen branch, maar meld elke oplevering in docs/inbox.md op de
werkbranch. Anders bestaat hij voor niemand.
```

---

## 🟩 Backtest Setup

```
git pull origin claude/middleware-setup-guide-afhvtk
Lees D-153 en inbox 38. Dat gaat vóór release 3b, want het raakt elke meting.

RELEASE — D-153: drie defecten in tools/validate_dataset.py, alle drie gemeten op Ferry's
3y MGC-bestand van 08-10.
  1. _to_datetime (r. 111) roept pd.to_datetime(..., format="mixed") ZONDER dayfirst=True,
     terwijl backtest/data.py:_parse_datetimes dat expliciet wél doet en in zijn docstring
     uitlegt waarom. Elke datum met dag <= 12 krijgt dag en maand omgewisseld: 386.750 van
     1.053.095 regels (36,7%). Gevolg: hij meldde bereik 2023-01-10 t/m 2026-12-08 (echt:
     2023-09-26 t/m 2026-09-25), 1.473 dubbele tijdstempels (echt: nul) en 28 gaten
     > 3 dagen met de grootste 28,7 dagen (echt: 6 gaten, grootste 3,1 dagen).
  2. Een constante UTC-offset over een DST-grens glipt erdoor. Dit bestand stempelt op een
     vaste -04:00 klok terwijl ET in de winter -05:00 is, dus ~5 van elke 12 maanden staat
     een uur te laat - en data.py neemt een offsetloze kolom als ET-wandklok over. Twee
     goedkope checks: een offsetkolom die constant is over een DST-grens = weigeren, en het
     lege uur van de CME-dagpauze mag niet per maand verschuiven (hier stond het 's zomers
     op 17 en 's winters op 18).
  3. De aliastabel mapt "volume" -> Volume; in dit bestand is die kolom overal 0 en zit het
     echte volume in "Volume(from bar)". Weiger een volledig nulle Volume - nulvolume breekt
     stil VWAP en VWMA.
Neem ook de normalisatie op in de tooling i.p.v. in een los script: lezen als Etc/GMT+4,
omzetten naar America/New_York, wegschrijven met %z per regel, Volume(from bar) -> Volume.
Acceptatie: na conversie is uur 17 ET in ALLE 37 maanden het enige lege uur (zo is het
geverifieerd), en de poort meldt 0 duplicaten en 6 gaten i.p.v. 1.473 en 28.

En één nuance in de poort zelf: hij weigert een deltaloos bestand omdat de engine de
deltafilter dan STIL in een doorlaat zou veranderen. Staat use_cvd_filter expliciet uit,
dan is die doorlaat een keuze en geen stille terugval. Maak dat onderscheid, anders
weigert hij bestanden die voor zulke configs bruikbaar zijn.

DAARNA release 3b (tailor-scoring als job) en dan D-130. Die staan ongewijzigd.
```

---

## 🟦 Middleware App

```
git pull origin claude/middleware-setup-guide-afhvtk
Lees D-163 (herijkt 05-11) in docs/SPRINT.md.

D-163 is geleverd (0ae751d) en wacht op uitrol door Ferry; niets bouwen tot zijn
systemctl-bewijs er is. Twee dingen intussen, allebei klein:
1. Zoek uit welk proces het Trade Journal (collection 1ddb61ea-444d-8136-8cd1-000b89919d64,
   Sync Status = Auto, Source = Custom Executor) nu al dagelijks vult — mex-journal-sync.timer
   op de VPS, of iets op Ferry's pc — en meld dat in docs/inbox.md met systemctl cat als bewijs.
   Het veld Commissions staat daar overal op 0: als het journal_sync.py is, lever dan de kleine
   release die Commissions uit de Cash_History meeschrijft (zelfde bron als fleet_daily.py).
2. Na Ferry's uitrol: journalctl + Notion-rijen nalopen en melden; dan pas ik de PA-taken aan
   zodat ze Fleet Performance lezen en de eigen commissieberekening laten vallen.
Geen raakpunt met mex-receiver, orders of PMT. Geen saldi of accountnummers in de repo.

NIEUW 05-11 — D-165 (inbox 55, lees die eerst): het Trade Journal boekt PA/eval op het
account-voorvoegsel en '(Intraday)' staat hardcoded; Ferry heeft besloten dat de
Accounts-DB de waarheid is, maar die is leeg voor alle 32 live accountpagina's.
Volgorde: (1) accounts_fill.py --dry-run met een voorstel per lege accountpagina,
lijst gaat via de SM in het Approval-item; schrijven pas na Ferry's bevestiging;
(2) writer leest Account Type van de accountpagina en gokt niet meer (leeg + notitie
als het ontbreekt); (3) journal_retag.py, dry-run met telling per type vóór/ná.
Stap 1 nu; 2 en 3 bouwen mag, draaien niet vóór de lijst bevestigd is.
```

---

## 🟪 Web

```
git pull origin claude/middleware-setup-guide-afhvtk

Twee kleine, ongewijzigd: (1) D-129 regel 3 - de poort bijt alleen bij sample:true; er moet
een regel bij die bij sample:false bijt, met Ferry's besluit: een AANTAL mag evals meenemen,
een BEDRAG nooit. (2) D-132 - verwijder web/handover/mex_units/; canoniek is
middleware/app/mex_units/.

En één waarschuwing voordat er iets over goud op de site komt: de drie jaar echte MGC-data
van 08-10 zeggen dat de config die live draait netto NEGATIEF is (-$27.377, PF 0,96, 49
breaches). Publiceer niets over TESORO-resultaat, ook geen percentage, ook niet in een
voorbeeld of mockup. Er is ook nog steeds geen out-of-sample bewijs voor welke engine dan
ook - de klok staat sinds 07-09 op nul en gaat met D-154 opnieuw op nul.
```

---

## 🟥 MCP trader-dev

```
git pull origin claude/middleware-setup-guide-afhvtk
Je rol is bevestigd: drijvende meet-/reviewrol, register M-, geen eigen map.

Verifieer ná oplevering, in deze volgorde:
 1. D-154 bij Pine Dev - vier nieuwe day-exit-inputs. Controleer vooral dat alle vier
    DEFAULT UIT staan en dat het gedrag met de inputs uit bit-voor-bit ongewijzigd is.
    Dat is de hele veiligheidsaanname van die release.
 2. D-153 bij Backtest Setup - de dayfirst-fix. Controleer of de poort ná de fix 0
    duplicaten en 6 gaten meldt op Ferry's MGC-bestand i.p.v. 1.473 en 28.
 3. Release 3a bij Middleware - staat er nog een getal in het playbook dat niet uit een
    bestand komt, en zijn de drie fallback-blokkers echt dicht?

Eén eigen opdracht: ik heb in D-152 de Python-engine tegen Ferry's Pine-export gehouden op
23 overlappende dagen (281 tr/+$8.848 tegen 293/+$8.299). Analyses & Data meldt dezelfde
pariteit als gesloten, het bord draagt hem als open. Twee metingen die dezelfde kant op
wijzen zijn geen poort. Kijk mee of er een reden is om die poort NIET te sluiten.

Melden in docs/inbox.md. Niet muteren buiten je eigen scope.
```
