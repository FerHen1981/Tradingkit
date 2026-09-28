# Startprompts per chat — ronde 29-09

_Eigenaar: Scrum Master. Watermerk: `50cd6c6`, 29-09._

**Stand:** fase 0 is op één review na af, fase 1 loopt al (D-79 op review, D-80 in de bouw),
en de registry is gedeblokkeerd. Ferry heeft LifeOS laten opschonen: van de oude taken staan
er nog vijf op hem, de rest is dicht of geparkeerd.

## Wat er sinds gisteren is veranderd

- ✅ **D-78 is `done`** — Middleware App auditeerde 19 `MEX_*`-vars plus 25 Python-envs,
  akkoord zonder blokkers, drie toevoegingen overgenomen.
- 🔴 **D-77 heeft de review van Pine Dev gehad en dat leverde drie blokkades op.** Alle acht
  punten zijn afgehandeld en het schema staat op **v2**. **Er ontbreekt nog één review: die
  van Middleware App.** Dat is het laatste wat fase 0 dichtzet.
- ✅ **Route B gekozen** (Ferry): Pine blijft de Discord-tekst schrijven, de middleware
  bepaalt alleen de bestemming. De ~20 kaartsjablonen blijven waar ze zijn.
- ✅ **D-73 afgerond en het weerlegde de aanname onder T2.** 4539 PMT-rijen gemeten: de body
  draagt **nooit** een fill-prijs of order-id. T2 wordt een **statuslaag**, geen prijslaag —
  en daarmee blijft **T1→T3 de enige slippage-meting**, wekelijks.
- ✅ **D-104 is gedeblokkeerd**, Ferry beantwoordde alle drie de vragen.
- ✅ **`apex_250k_legacy_pa` bestaat** (door de Scrum Master aangemaakt op Ferry's verzoek).
- 🔴 **Twee nieuwe live-items:** **D-107** (dubbele sluiting + verkeerde exit-qty in Pine) en
  **D-108** (de dertien `.pine` lopen achter op de registry sinds D-68).

---

## 🟦 Middleware App (chat: **App Setup**) — eerst die ene review

```
git pull origin claude/middleware-setup-guide-afhvtk

Mooi doorgepakt op D-79 en D-80. Eén ding gaat daar nu vóór.

1. 🔴 D-77 REVIEW — dit is het laatste wat fase 0 dichtzet.
   Lees docs/schema-event.md (staat inmiddels op v2, met §3b waarin Pine Devs drie
   blokkades zijn afgehandeld). Toets één ding: is elke huidige uitgaande payload hieruit
   te bouwen? Toets op een ECHT bericht per route — PMT-JSON, Discord-embed,
   PineConnector-commando, journaalregel — niet op papier.
   Let specifiek op wat er sinds v1 veranderd is en wat dat voor D-87 betekent:
   - `kind` is gesplitst in `order` en `fill`. Een order draagt GEEN journal-object, een
     fill wel. Reden: f_sendExec vuurt bij het plaatsen, f_journal("FILL") pas nadat de
     fill gedetecteerd is — bij een limietorder tot expiryBars later.
   - `id` wordt strategy:ts:kind:seq. Het volgnummer is nodig omdat twee sluitingen op
     dezelfde bar kunnen vuren.
   - `action` krijgt "cancel" erbij.
   - Bij een sluitende fill is `qty` de WERKELIJKE positie, niet de signaal-qty.
   - `journal.acct_name` wordt MEEGESTUURD, niet in de middleware nagebouwd. f_autoAcctName()
     leidt hem af uit accountID + evalStartBal + validFrom; een kopie zou een tweede bron zijn.
   - Route B: voor Discord neem je text.title en text.body ONGEWIJZIGD over en beslis je
     alleen over webhook, tier en rendering.

2. Ga daarna door met fase 1: D-81 (auditspoor + migratie) sluit de fase af.

3. D-105 en D-53 staan op review bij mij; D-74 en D-69 lopen nog bij jullie.

VOORUITBLIK D-91, nu D-73 binnen is. T2 kan vier toestanden onderscheiden en geen prijs:
CONFIRMED (90,4%) · UNKNOWN (9,1%, lege body) · REJECTED · en verder niets. 🔴 En let op de
tweede bevinding, die de live code raakt: "GEWEIGERD 200" kwam 0 keer voor in 4539 rijen.
De body-gebaseerde Rejected()-check heeft nooit iets afgevangen omdat PMT error:true in de
praktijk niet stuurt — een echte weigering is HTTP 403. De poort hoort op de statuscode.

D-106 ligt deels bij jullie: log per POST welk endpoint gekozen werd (Rithmic of Tradovate).
Dat haalt de eerste onbekende weg bij het account dat 100% van het afwijkende verkeer draagt.
```

---

## 🟩 Backtest Setup — D-104 is vrij, en het is kleiner dan gedacht

```
git pull origin claude/middleware-setup-guide-afhvtk

D-104 staat weer op todo — je drie vragen zijn beantwoord, zie docs/inbox.md.

Goed dat je gestopt bent in plaats van te gokken op een verified:true-record dat live
accounts voedt. Dat is precies de juiste reflex.

A · Ferry gaf een REGEL in plaats van een lijst: "ik kies altijd de programma's die het
    dichtst bij de Apex-regels liggen." Leg die regel vast in de meta van elk nieuw record,
    met de motivering — dan is over drie maanden nog na te gaan waarom er Standard staat
    en geen Direct. Toegepast: Blue Guardian Standard · Top One Elite (met het bekende
    verschil dat Elite wél een DLL kent) · TradeDay EOD trailing. 🎯 Die regel beslist
    meteen jouw open vraag over TradeDay's DD-soort.
B · Top One consistency = 40%. Zet verified:true met "owner-confirmed" als bron, niet de
    website — die twee bronnen spraken elkaar tegen en daarom lag het bij Ferry.
C · apex_250k_legacy_pa heb ik zelf aangemaakt op Ferry's verzoek. Eenmalig; normaal is
    dat jullie pen. Kijk hem na.

🔴 EN CONTROLEER DIT, het raakt de vooruitblik van elk legacy-account:
apex_50k_legacy_pa draagt max_daily_loss $1.000, terwijl Ferry's fleet-doc §9 voor legacy
letterlijk "geen DLL" zegt. Dat is geen tegenspraak in het doc maar twee verschillende
dingen: de FIRMA legt geen DLL op (registry = null) en FERRY legt zichzelf er één op in
Tradovate (hoort in D-78 accounts[].caps). Staat Ferry's cap als firm-regel in de registry,
dan bewaakt D-96 straks een limiet die Apex niet kent. Meld wat je vindt, zet het niet
stil recht — het is een verified:true-record.

Draai na het vullen python tools/gen_pine_firms.py. ⚠️ Die diff is nu veel groter dan
één preset door D-68; dat is D-108 bij Pine Dev. Push de pine-kant NIET zelf.

Daarna: D-100 staat op review, dus door naar D-101 — de interpreter voor de
Pine-deelverzameling, die HARD weigert op alles wat hij niet kent.
```

---

## 🟨 Pine Dev — twee live-items, en het eerste is het zwaarst

```
git pull origin claude/middleware-setup-guide-afhvtk

Sterke review op D-77. De drie blokkades zijn alle drie afgehandeld en het schema staat op
v2 — lees §3b van docs/schema-event.md, daar staat per punt wat het geworden is en waarom.
Dank ook voor de correctie op mijn vondst: routeMiddleware is een constante, geen toggle.
Die staat rechtgezet.

Eén ding heb ik nog van je nodig op D-77: bevestig dat blokkade 1 vanzelf oplost.
Mijn redenering: in fase 3 smelten f_sendExec, f_sendDiscord en f_journal samen tot één
alert(), dus de `not execInstance`-guard wordt irrelevant in plaats van verwijderd en er
komt geen extra alert bij. Klopt dat tegen de code?

DOE NU:

1. 🔴 D-107 — JOUW TERZIJDE WAS GEEN TERZIJDE, het raakt echte orders.
   (a) Vier sluitingspaden — auto-flat (r. 2262), venster-grace (2282), dag-halt (2297),
       account-halt (2324) — roepen elk strategy.close_all() aan, alleen bewaakt door
       if posSize != 0 en zonder onderlinge uitsluiting. Twee kunnen op dezelfde bar vuren.
   (b) Vijf van de zes close-aanroepen sturen t_qty mee, de qty van de ENTRY, in plaats van
       math.abs(strategy.position_size). Alleen de cap-lock doet het laatste. Normaal valt
       dat samen; na een gederiskte of gecapte fill niet — dan sluit je te veel (doordraaien
       naar de andere kant) of te weinig (restpositie blijft staan).
   Dit is bestaand gedrag, niet door de herijking veroorzaakt. Het mag samen met D-86 in
   één ronde, dan test je het één keer.

2. D-108 — de dertien .pine lopen achter op de registry sinds D-68. Draai
   python tools/gen_pine_firms.py en LEES DE DIFF REGEL VOOR REGEL.
   Ik draaide hem gisteren en kreeg 14 bestanden / 370 regels. Dat leek eerst een fout maar
   is het niet: D-68 haalde twee verzonnen fallbacks uit firms.py — acct_dll viel terug op
   1_000.0 en consistency_pct op 50.0 voor elk programma zonder registry-waarde. De
   gecommitte .pine draagt die verzonnen waarden nog.
   ✅ Gemeten via to_overlay(): Ferry's eigen programma's veranderen NIET. apex_50k_legacy_pa
   houdt DLL 1000 / consistency 30, apex_50k_intraday_pa houdt 1000 / 50.
   ⚠️ Toch een gedragswijziging in dertien live scripts. Bevestig dat er niets verandert aan
   een programma dat Ferry werkelijk draait vóór je pusht. Ik heb de regeneratie bewust
   teruggedraaid en niet meegecommit — jullie map, live pad.
   📌 Neem meteen mee: de firmPreset-default staat op apex_50k_eod_pa terwijl Ferry LEGACY
   handelt. Dat zet de consistency in Pine op 50 waar hij 30 hoort te zijn.
```

---

## 🟪 Web — nog even niets, maar het komt dichtbij

Fase 1 is bijna rond (D-79 op review, D-80 in de bouw, D-81 resteert). Zodra **D-82** — de
config-API — er is, zijn D-83 en D-84 aan de beurt.

**Lees alvast `docs/schema-config.md` §2 en §3**: dat is letterlijk het scherm dat jullie
gaan bouwen, in twee niveaus. En §5, want dat bepaalt de vorm: **tokens worden verwijzingen,
geen waarden.** Het scherm toont `apex_pmt · ✓ gezet · gewijzigd 12-09` en een veld om te
vervangen — nooit de waarde zelf.

⚠️ Eén ding dat nu al telt: **met dit scherm wordt de webapp onderdeel van het live
executiepad.** Vandaag toont een fout daar een verkeerd getal; straks stuurt hij een order
naar het verkeerde account. Dat verandert wat "af" betekent voor dit scherm.
