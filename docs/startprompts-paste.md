# Paste-klare startprompts — ronde 08-10 (avond)

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
Lees D-154, D-149 en D-150 in docs/SPRINT.md. Drie dingen, in deze volgorde.

RELEASE A (de release van vandaag) — D-154: vier nieuwe inputs in het day-exit-blok,
ALLE VIER DEFAULT UIT, zodat het gedrag ongewijzigd is zolang niemand ze aanzet:
  1. Max verliezen op rij per dag      (int, 0 = uit)
  2. Max winsten op rij per dag        (int, 0 = uit)
  3. Eerste verlies boven +X sluit de dag ($)   (float, 0 = uit)
  4. Giveback-2 ($) + vanaf (uur ET)   (default = de gewone giveback, uur 0)
"Dag dicht" = exact de bestaande Day-trail/Day-cap-halt, met HALT-kaart en reden
STREAK-LOSS / STREAK-WIN / LOSS-AFTER-PLUS / DAY-TRAIL-2, en het bestaande
dayHaltClose-gedrag voor een open positie. Eerste die raakt wint. Netto incl. commissie;
exact 0 telt als verlies. Volledige semantiek staat in D-154 — lees die, niet dit blok.

Waarom: de slechte dagen zijn EEN verliesreeks, niet veel kleine verliezen (reeks 5 =
-$475 per contract), en de day-trail werkt alleen op winst-teruggave. Stop na 5 verliezen
halveert de breach-kans bij gelijke hit-kans. Dit voegt GEEN edge toe en moet nergens zo
genoemd worden: streaks voorspellen de volgende trade niet. Het knipt variantie.

Acceptatie: een jaarexport met Max verliezen op rij = 5 tegen dezelfde export zonder, op
TP 85 / 250-100-500 / qty 1 / MGC. Verwacht identieke trades tot de eerste halt per dag,
~7,7 i.p.v. ~8,1 trades per dag, HALT-kaarten met reden STREAK-LOSS, netto per contract
hoger, slechtste dag niet slechter dan -$1.100. Analyses & Data draait dezelfde
vergelijking in de engine en legt ze naast elkaar.

DAARNA, en pas daarna:

(B) D-150 — een strategie-export schrijft ELKE input.string in platte tekst naar de
Properties-tab, dus het PMT-token en het middleware-secret staan leesbaar in elke export
die Ferry ooit heeft gedeeld. display=display.none helpt niet. Vraag: kunnen die twee uit
de chart-inputs? Het alert-BERICHT moet ze dragen, de chart-CONFIG niet per se - maar
f_pmtJSON() bouwt de payload nu uit precies die inputs. Kan het niet, zeg dat dan
expliciet, dan wordt "wis de Properties-tab voor je deelt" een vaste regel in CLAUDE.md.
Zet de waarden zelf nergens neer: niet in een commit, niet in een testfixture.

(C) D-149 — marketRegimeMode heeft in de bron default "Liquidity Core", maar Ferry's live
chart draagt een opgeslagen override naar "All sessions" die een verse chart niet meeneemt.
Dat kostte 254 van 389 entries zodra hij v3.10 opende. Zodra Ferry kiest welke de echte is:
default in de dertien scripts gelijkzetten EN in frozen-engines.md vastleggen.
Breder dan dit item: f_cfgStr() draagt mktRegime= al mee in het journaal. Kan de
ontvangstkant dat per alert vergelijken met de bevroren config, zodat een afwijkende chart
meteen opvalt? Graag een oordeel of dat in Pine kan of aan de ontvangstkant hoort.

Claim met status wip + owner in docs/SPRINT.md, losse commit per release.
De OOS-klok gaat op nul. Dat is bekend en hier de prijs waard.
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

RELEASE 3a staat ongewijzigd: het playbook toont de invoer van de fleet-berekening en de
hardgecodeerde doctrine gaat eruit. Spec in docs/inbox.md onder "het playbook krijgt de
logica van het fleet-doc". Acceptatie: de Playbook-tab toont per account ruimte /
gelockt-of-vers / beste dag sinds laatste payout / eerstvolgende cap / kwalificatiedagen /
consistency-ruimte, en er staat nergens meer een markt- of strategieregel die niet uit een
bestand komt.

DRIE BLOKKERS DAARVOOR, en ze zijn er alle drie nog:
 - _APEX_FALLBACK draagt nog APEX_LADDER_50K = [1500,1500,2000,2500,2500,3000] met
   "verified": True. Die ladder BESTAAT NIET (D-148): de cap is vast $2.000 en vervalt
   vanaf de zesde payout.
 - payout_cap_uncapped_from wordt in geen enkel bestand in middleware/app/ gelezen.
 - payout_terms_verified: false moet WEIGEREN, niet stilzwijgend iets anders invullen.
Deploy niet vóór die drie dicht zijn - anders rekent het playbook met een plafond dat
alleen in onze code bestaat, en 018 zit precies in die fase.

Eén nieuwe vraag uit D-149, los van 3a: f_cfgStr() draagt mktRegime= mee in elk
journaalbericht. Ferry's live chart bleek maanden een andere vensterinstelling te hebben
dan de bevroren config, en niets zag dat. Kan de ontvangstkant die string per alert
vergelijken met de bevroren config en afwijking melden? Geen bouwopdracht - een oordeel of
dit hier hoort of in Pine. Antwoord in docs/inbox.md.
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
