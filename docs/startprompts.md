# Startprompts per chat — ronde 25-08

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

Werk in deze volgorde:
1. D-59 — `Mex.Journal.Receiver` ontbreekt in `MexJournal.sln`. Eén commando. Doe dit eerst,
   anders bouwt je eigen build groen zonder het live pad aan te raken.
2. D-40 + D-53 SAMEN — beide zetten een controle per account vóór `ForwardJsonAsync` in
   `/signal/{token}`, op hetzelfde `multiple_accounts[0].account_id`. Apart bouwen betekent
   twee keer dezelfde plek in het live executiepad openleggen.
3. D-49 — alles naar `mw.mex-traders.com`. De `Caddyfile` die nu in git staat bevestigt die host.
4. D-05 en D-02 — Python fan-out afvoeren.

Claim één item in docs/SPRINT.md (status `wip` + owner + losse commit) vóór je begint.
Raakt je wijziging het live executiepad, meld het in docs/inbox.md vóór je pusht.
```

---

## 🟩 Pine Dev

```
git pull origin claude/middleware-setup-guide-afhvtk

Lees docs/SPRINT.md en docs/inbox.md vanaf de rondes van 25-08. D-61 is afgerond en door de
Scrum Master geverifieerd. Er liggen er nu zes, en de volgorde is niet willekeurig:

1. D-65 EERST — de firm-preset-generator kent de v1_0_0-vloot niet; `STRATEGY_DEFAULT` in
   `tools/gen_pine_firms.py` bevat alleen de oude v6.9.5-namen. Dit kan de wortel onder D-63
   zijn: een handmatig onderhouden firm-preset verklaart LEON's verkeerde programma net zo
   goed als TradingView dat oude inputs bewaart. Weet dit vóór D-63, anders is die her-export
   dweilen met de kraan open.
2. D-64 — `MEX_EL_DORADO.pine` compileert niet: `firmPreset` draagt `apex_intraday_pa`, een
   sleutel die niet in de registry bestaat. De fout zit in de generator, dus repareren in het
   .pine-bestand wordt bij de volgende run overschreven.
3. D-63 — her-export LEON en REY op de bron-config. Zet in dezelfde ronde de commissie van
   0,51 naar 0,37 (registry wint, besluit Ferry 24-08), anders exporteer je twee keer.
4. D-44 — `breakeven_offset` in `f_pmtJSON`. Byte-identiek blok in alle negen scripts, dus
   één sed. Wacht op Ferry's bevestiging dat het PMT risk type niet op `Price` staat.
5. D-41, D-42, D-51, D-57 — in die volgorde, D-57 pas ná D-54.

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
1. D-55 — de vloot-sweep heeft geen spoor in `validation/`. Gezien D-54 worden die cijfers
   waarschijnlijk herzien; dan wil je kunnen terugkijken wat er gemeten was.
2. MATADOR hertoetsen zodra Pine Dev de commissie op 0,37 heeft: zijn `data_parity` is
   behaald terwijl de export op 0,51 stond. $30,59/account-dag is nu het enige cijfer waar
   iets op rust.
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
