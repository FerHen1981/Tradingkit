# Paste-klare startprompts — ronde 08-10 (avond) · Pine Dev-blok vervangen 04-11 (v3.13.4 / D-162)

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
Lees in docs/inbox.md de items 49 en 50 (SM, 04-11) en D-161 + D-162 in docs/SPRINT.md.

EERST: v3.13.4 NAKIJKEN — ik heb in jouw map gepatcht, op directe opdracht van Ferry
("drawings staan nog steeds niet goed, fix het"). Commit 2cdf511, alle dertien. Twee
tekendefecten die DRAW≠TRADE niet kon zien omdat die alleen vakken toetst:
  (1) het exit-label (PnL/MFE/MAE) stond op _xm, het MIDDEN van de trade, i.p.v. op de
      exit-bar → nu strategy.closedtrades.exit_bar_index(_ti);
  (2) tradeInfo hing op bar_index + 2 en werd elke bar met set_xy verplaatst → schoof mee
      met de laatste candle op de entryprijs en sprong bij de exit terug. Nu verankerd op
      (entry-bar, entryprijs), label.style_label_right, achtergrond transparant;
  (3) bijvangst: box.new bij de aanmaak las curStop/curLimit i.p.v. jouw zoneStopPx/
      zoneLimitPx — in het D-162-geval de stop van de vorige trade.
Jouw map, jouw oordeel: wil je het anders, dan wordt dat v3.13.5 van jou. Ik kan niet
compileren en de chart niet zien; xloc/yloc als benoemde argumenten bij label.new is
nieuw gebruik in dit script.

RELEASE v3.13.5 — D-162, één dag, op zichzelf:
Sluit een trade en opent de volgende in dezelfde 1-minuutbar, dan vuurt
`if newLong or newShort` niet (newLong hangt op het teken van posSize, r. ±2941). Dan
ontbreken de FILL-kaart en de journaalregel, en houden curStop/curLimit/posHi/posLo de
waarden van de VORIGE trade. Nuance die je note niet noemt: de placement-exit (r. ±2891)
gaat goed naar PMT, maar het inLong-blok zet strategy.exit dezelfde bar OPNIEUW op de
stale curStop/curLimit (r. ±3127) zonder alert_message — TradingView en broker lopen
dan op een andere stop en TP, en de reconciliatie boekt dat als slippage.
Fix: het fill-blok op de tradeteller (drawTradeNo verandert), zoals je bij D-161 deed.
Acceptatie: evenveel FILL- als EXIT-regels in het journaal, geen fill zonder kaart;
poorten groen; DEPLOYED.md op v3.13.5. Geen OOS-reset als er geen config-wijziging in zit.

MEE IN DEZELFDE RELEASE (inbox 49, geen aparte bump):
  - TESORO contractSize default 7 → 1 (de bevroren volle grootte is niet
    fresh-account-funderbaar; de ladder zet qty per chart);
  - BANDIDO dayCapUSD 300 → 200 per contract (× qty 5 = $1.000, het bevroren getal).
    Wil je liever frozen-engines.md aanpassen, zeg het — dat bestand is van mij.

NOG OPEN BIJ FERRY (jouw twee feiten uit de v3.13.3-note blijven staan): de versie in de
scripttitel op de chart en of de oude v3.10-instantie er nog naast hangt; en of er een
rood DRAW≠TRADE-label staat en wat erachter staat. Claim D-162 met status wip + owner,
losse commit per deel.
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
