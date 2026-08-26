# Startprompts per chat — ronde 26-08

_Eigenaar: Scrum Master. Ververst elke toezichtronde; de datum bovenaan is de houdbaarheid._

Plak het blok van de betreffende chat als **eerste bericht**. Elk blok begint met een pull,
zodat de chat op de actuele stand staat vóór hij iets claimt. Werk dat op een oude stand
begint is precies hoe de analyses-chat dagen op een ingetrokken aanname doorwerkte.

⚠️ **Verlopen blok?** Is de datum hierboven ouder dan de laatste toezichtronde onderaan
`docs/SPRINT.md`, plak dan niet blind — vraag de Scrum Master om een verse ronde.

---

## 🟦 Middleware App

```
git pull origin claude/middleware-setup-guide-afhvtk

Lees docs/SPRINT.md en docs/inbox.md vanaf de rondes van 25-08. Er is sinds gisteren veel
veranderd bij jullie:

- D-06 is opgeleverd: de .NET-solution staat compleet in git en is bouwbaar.
- D-35 is live: de receiver draait sinds 25-08 01:23 UTC op actuele code. IPv4-forcering en
  de body-check zijn nu echt in het draaiende proces.
- Vier items stonden onterecht op `blocked` en zijn losgezet: D-40, D-53, D-05, D-07.

D-40, D-02, D-05, D-49 en D-59 zijn geREVIEWD en akkoord — goed werk, vooral de
`Rejected()`-analyse en het feit dat jullie erbij schreven dat de auto-DLL-halt ook in `risk.py`
dormant was. Zo hoort een port verantwoord te worden.

Werk in deze volgorde:
1. 🔴 D-53 — DE QTY-FIX, EN HIJ BLOKKEERT DE UITROL. De implementatie raakt alleen
   `quantity_multiplier` (int > 0), maar Pine stuurt daarnaast zijn eigen `"quantity"` — bij
   MATADOR 6 contracten — en die blijft ongemoeid. Een integer-multiplier kan dat alleen
   gelijkhouden of verhogen, dus naar 1 contract schalen lukt niet. Ook de bordregel "ontbrekend
   account = vers account is per default veilig" klopt daardoor niet: dan handelt het account op
   Pine's volle grootte, precies wat de sweep als niet-funderbaar aanwijst.
   Voorstel: overschrijf `obj["quantity"]` direct als string, laat de multiplier op 1, en hernoem
   de env — "multipliers" dekt de lading niet meer.
2. D-69 — `render.yaml` start nog `uvicorn app.main:app` en dat bestand hebben jullie verwijderd.
   Een deploy vanaf die blueprint crasht. Advies: verwijderen, de architectuur die hij deployde is
   met D-04 afgevoerd. Jullie map, jullie besluit.
3. D-07 — de commissievraag is beantwoord: registry wint (besluit Ferry 24-08), dus 0,37 voor
   MNQ/MES/MYM. Wat resteert is verifiëren tegen `Cash_History`.
4. D-17 — viewer-rol, wacht op mijn review zodra jullie melden dat hij af is.

Claim één item in docs/SPRINT.md (status `wip` + owner + losse commit) vóór je begint.
Raakt je wijziging het live executiepad, meld het in docs/inbox.md vóór je pusht.
```

---

## 🟩 Pine Dev

```
git pull origin claude/middleware-setup-guide-afhvtk

Lees docs/SPRINT.md en docs/inbox.md vanaf de rondes van 25-08. D-61 is afgerond en door de
Scrum Master geverifieerd. Er liggen er nu zes, en de volgorde is niet willekeurig:

1. D-64 — `MEX_EL_DORADO.pine` compileert niet: `firmPreset` draagt `apex_intraday_pa`, een
   sleutel die niet in de registry bestaat. De fout zit in de generator, dus repareren in het
   .pine-bestand wordt bij de volgende run overschreven.
2. 🔴 D-66 — jullie delta-signalering geldt voor de HELE vloot, niet voor twee scripts: 9 van de
   9 verwijzen naar `ta.requestVolumeDelta` en in 9 van de 9 staat `useCVDFilter` op true. Dat
   botst met D-09. Maar MATADOR haalde `data_parity`, wat daar tegenin gaat — er is iets dat ik
   niet zie. Beantwoord samen met Backtest Setup welke het is: motoren lopen dicht genoeg gelijk,
   filter bindt zelden, of gat in de pariteitstoets. DIT GAAT VOOR D-63.
3. D-63 — her-export LEON en REY op de bron-config, PAS NA D-66. Zet in dezelfde ronde de
   commissie van 0,51 naar 0,37 (registry wint, besluit Ferry 24-08), anders exporteer je twee
   keer, en dan tegen een meetlat die zelf niet klopt.
4. D-44 — `breakeven_offset` in `f_pmtJSON`. Byte-identiek blok in alle negen scripts, dus
   één sed. Wacht op Ferry's bevestiging dat het PMT risk type niet op `Price` staat.
5. D-57 pas ná D-54. D-41, D-42, D-61 en D-65 zijn dicht en gereviewd — die kun je afvinken.

Claim één item in docs/SPRINT.md vóór je begint. D-44 en D-63 raken echte orders: melden
in docs/inbox.md vóór je pusht.
```

---

## 🟨 Backtest Setup

```
git pull origin claude/middleware-setup-guide-afhvtk

Lees docs/SPRINT.md en docs/inbox.md vanaf de rondes van 25-08. Twee dingen zijn veranderd
aan wat je dacht dat er lag:

- D-18 is beslist (optie B): de drie jaar 2023-2026 heten VALIDATIE, echte OOS loopt forward
  vanaf de config-freeze van 23-08-2026. Er is dus twee dagen OOS-historie. Ook jullie
  sweep-cijfers vallen volledig binnen het validatievenster.
- D-10 VERVALT daardoor — dat bestond alleen om optie A mogelijk te maken. Draai dat
  validator-commando niet.

Werk in deze volgorde:
D-55 en D-56 zijn binnen en gereviewd. Jullie MGC-analyse heeft mijn eigen voorbehoud
gecorrigeerd — de twin-bias is asymmetrisch en pleit vóór de afwijzingen. Dat argument is beter
dan het mijne en ik heb het overgenomen.

⛔ EN TREK DIT IN: ik vroeg jullie trap 7/8 te hertoetsen omdat propfirms.json $2.500 droeg in
plaats van $2.000. Nagemeten: de vloot-pijplijn leest dat bedrag helemaal niet — `fleet.py:84`
draagt `acct_trail_dd=2000.0` hardgecodeerd. De sweep is dus NIET geraakt. Draai die run niet.

1. 🔴 D-66 — de pariteitsvraag, samen met Pine Dev. Zie hun blok. Dit blokkeert D-63 en D-54.
2. D-68 — juist ómdat de sweep hier ongeschonden uitkwam: dat was omdat een hardgecodeerd getal
   toevallig klopte, niet omdat de registry gelezen werd. `fleet.py:84`, `firms.py:255`, en de
   stille fallback `or 2500` in `higher.py:237` die bij een lege waarde terugvalt op precies de
   onjuiste waarde. Maak daar een harde fout van.
3. MATADOR hertoetsen zodra Pine Dev de commissie op 0,37 heeft — dat blijft wél staan.
3. D-54 — zodra de her-exports van D-63 binnen zijn: trap 1 voor LEON en REY, dan trap 8.
4. D-56 — is echte MGC-data te krijgen? Zolang die ontbreekt staat elk MGC-oordeel onder
   voorbehoud, ook de afwijzing van PATRON.
5. D-43, D-50, D-27 — en meld welke nummers inbox 6 en 7 moeten krijgen.

Claim één item in docs/SPRINT.md vóór je begint. `validation/` is append-only.
```

---

## 🟪 Web

```
git pull origin claude/middleware-setup-guide-afhvtk

D-34 is gedeblokkeerd: D-18 is 25-08 beslist. Je stond geblokkeerd zonder dat het op het
bord stond — excuses daarvoor.

Wat je nu mag schrijven, en wat niet:
- WEL: "gevalideerd op drie jaar (2023-2026)".
- NIET: "3 jaar out-of-sample". Echte OOS loopt forward vanaf de config-freeze van
  23-08-2026 — dat zijn twee dagen. Claim geen OOS-bewijs.
- Er is ook GEEN geldige vlootrangorde. Alleen MATADOR heeft een gesloten pariteitspoort, en
  ook dat cijfer moet nog hertoetst worden op de juiste commissie. Zet geen ranglijst online.

Loop de zes plekken uit D-34 na en controleer dat de nieuwe tekst niet alsnog op de oude
GC+ES-aanname of op een rangorde leunt. Meld het in docs/inbox.md als je klaar bent; de
Scrum Master doet de review.
```

---

## ⚫ Legacy (Discord Notify)

```
git pull origin claude/middleware-setup-guide-afhvtk

D-28 kan verder. Je drie hooks zitten sinds 25-08 01:23 UTC in de draaiende binary — D-35 is
gebouwd en herstart. Ze doen nog niets zolang `MEX_CARD_MAX_PER_MINUTE` en de routing-env-vars
niet gezet zijn.

Zet ze ÉÉN VOOR ÉÉN aan, niet alle tegelijk: gaat er iets mis op het notify-kanaal, dan wil je
weten door welke. Bepaal eerst welke je wilt aanzetten en in welke volgorde, en meld dat in
docs/inbox.md vóór je een env-var zet — dit raakt het live pad.

Let op: D-41 (elf guard-kaarten dragen geen account) ligt bij Pine Dev, niet bij jou. Zolang
dat open staat is per-kanaal routing voor die kaarten sowieso niet volledig.
```
