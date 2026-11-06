# Startprompts per chat — ronde 05-10

_Eigenaar: Scrum Master. Watermerk: `HEAD`, 05-10._

## Stand

**Fase 0 en 1 zijn af. Fase 2 is de kritieke lijn en is sinds deze ronde gedeblokkeerd.**
D-120 is beslist: de settings-tab komt **in de bestaande cockpit, direct vóór de Live-tab**.
Daarmee verhuizen D-83 en D-84 van Web naar Middleware App, is er géén nieuwe app-shell
nodig, en erft het scherm de bestaande auth.

⚠️ **En er loopt een incident op het live pad.** Zie D-116, D-122 en D-123 hieronder. Lees die
drie vóór je iets aan de middleware doet.

## De les van deze week, en hij geldt voor iedereen

🔴 **Vier keer in drie dagen heb ik een verklaring uit de code afgeleid in plaats van gemeten,
en drie daarvan waren fout.** De rate-limit als oorzaak (weerlegd door de tier-tabel), een
Pine-runtime-error (weerlegd: de charts waren niet gewijzigd), de webhook-routing (weerlegd:
er is geen enkele `NOTIFY_WEBHOOK*` gezet), en D-53 gesloten op de aanname dat
`MEX_ACCOUNT_QTY` leeg was (er staan **39 accounts** in).

**Werkregel vanaf nu: een uitspraak over het live pad vraagt een meting, geen leesbeurt.** De
code zegt wat er *kan* gebeuren; alleen het journaal zegt wat er *is* gebeurd. Schrijf in je
oplevering erbij *hoe* je het gemeten hebt — en als je het niet kon meten, schrijf dát.

📌 Mijn eigen env-meting van 02-10 was óók te smal: de grep miste `MEX_HALTED_ACCOUNTS` en
`MEX_ACCOUNT_ENTRY_CAPS`, en die zijn nu juist de hoofdverdachten in D-123. Een filter is een
aanname.

---

## 🟦 Middleware App — drie dingen, en D-123 gaat voor

### 1. D-123 — waarom kreeg account …018 geen entries? 🔴 LIVE

Gemeten op Ferry's PMT-export: op 05-10 vuurden **8 signalen** naar 7–8 kern-accounts en
**…018 ontbreekt bij alle acht**, terwijl het om 06:21 wél een `close` qty 4 kreeg. Op 02-10
deed het nog gewoon mee (22 alerts, qty 2).

**Entries weg, exits door** — dat is precies de vorm van allebei jullie poorten: `if (isEntry
&& …)` op r. 312 (D-40) en r. 330 (D-02).

➡️ **Doe de meting, niet de redenering.** `routed_*.jsonl` van 05-10, `kind: "pmt"`, account
op …018. Het `result`-veld onderscheidt alle vier de kandidaten:

| wat je ziet | wat het is |
|---|---|
| `GEWEIGERD lokaal — risk-gate: <reden>` | `MEX_HALTED_ACCOUNTS` of `MEX_ACCOUNT_ENTRY_CAPS` |
| `GEWEIGERD lokaal — day-cap/DLL blokkade actief` | de reactieve D-40-gate |
| een normale PMT-reply | de middleware stuurde wél; PMT plaatste niet |
| **geen enkele rij** | de middleware zag het alert nooit — dan zit het ervóór |

📌 Dump ook de **volledige** env-namen van het draaiende proces (niet gefilterd), want
`MEX_HALTED_ACCOUNTS` is de sterkste kandidaat: die is persistent en overleeft een herstart,
en dat is het enige wat een onderbreking van drie dagen moeiteloos verklaart.

🔴 **Verifieer apart** of die `close` voor 4 contracten op een vlak account een **omgekeerde
positie** heeft geopend — de payload draagt `reverse_order_close: True`.

### 2. D-116 — de fall-through, en nu met cijfers

**Bevestigd en gekwantificeerd:** 688 pogingen op 02-10, **103 weggegooid = 15,0%**; over
alleen tier B **20,0%**. Ferry draait nu `MEX_RENDER_ENABLED=false` als noodmaatregel, dus de
kaarten staan uit.

Drie dingen in één fix:
1. Bij demping **doorvallen** naar `PostJsonAsync` in plaats van `return` (r. 438–451).
2. De `catch` in `RenderAndPostAsync` heeft **geen** tekst-fallback terwijl beide andere takken
   die wél hebben — zelfde klasse, andere tak.
3. De rate-limit staat op `tier != 'C'`, dus **tier C gaat ongelimiteerd door** terwijl tier B
   sneuvelt. De rem hoort vóór die afslag.

🔗 Dit is niet alleen ruis: D-123 laat zien dat de blokkademelding *"⛔ Order NIET geplaatst"*
vermoedelijk tussen die 103 zat. **Een weggegooide waarschuwing is duurder dan een
weggegooide kaart.**

### 3. D-121 + D-111B — de payload-helften

De widget-helften heb ik gebouwd (in jullie map, gemeld in `inbox.md`, review welkom). Wat bij
jullie ligt:

- `stack()` moet per stage ook `todayTrades/Winrate/Pf` en `weekTrades/Winrate/Pf` leveren.
  Dan kunnen de twee `· all`-achtervoegsels uit de widget.
- `passed_at` / `breached_at` in de payload. De afleidingsregel en de tien datums staan in
  `DECISIONS.md`. Dan kunnen de venster-standen een échte venstertelling tonen.

### 4. Fase 2 — D-83/D-84 zijn nu van jullie

D-120: de tab komt in `middleware/app/viewer.py`, tussen `Playbook` en `Live` (r. 702–716).
Auth: **alleen `_authed()`** — de cookie-sessie. **Niet `_api_authorized()`**: die laat ook de read-only widget-token door, en dit scherm schrijft secrets (D-135).

🔴 **Eén ontwerpeis vooraf:** de cockpit draait op `app.mex-traders.com`, de config-API op de
.NET-receiver achter `mw.mex-traders.com`. **Proxy server-side** naar `localhost:5000` en voeg
de Bearer daar toe — dan blijft CORS dicht en komt de token **nooit in de browser**. Niet
`MEX_CONFIG_API_CORS_ORIGIN` openzetten; dit scherm stuurt orders.

📌 **Volgorde: D-119 (de leeshelft) eerst.** Een scherm dat naar het live pad schrijft terwijl
ons model van dat pad fout is, is gevaarlijker dan PowerShell — en deze week bleek dat model
drie keer fout. D-119 is bovendien klein: `routed_*.jsonl` draagt `kind`, `account`,
`transport` en `result` al.

---

## 🟨 Pine Dev — D-110 heropend, en het is niet jullie fout

🔴 **Ik neem mijn intrekking van 29-09 terug.** Ik schreef toen dat het `runningPnL`-bezwaar
verviel omdat Pine en de broker dezelfde chart-qty zouden gebruiken. **Dat rustte op de
aanname dat `MEX_ACCOUNT_QTY` leeg was — er staan 39 accounts in** (D-122).

Gevolg: Pine berekent `runningPnL` én `ownerDll = 4 × SL × contractSize` op de **chart-qty**,
terwijl de middleware voor accounts in die map een **andere** qty naar PMT stuurt. De eigen
dagrem is dan gekalibreerd op een grootte die niet gehandeld wordt.

✅ **Maar de PMT-export verzacht het:** de qty is dáár niet uniform 1 — …013/…018/…022/…026/…034
staan op 2, …274/…278 op 5, …277 op **35**. Die accounts zitten dus níét in de map en bij hen
klopt Pine's rekensom wél.

➡️ **Deze ronde: niets aan de dertien scripts wijzigen.** Eerst moet vaststaan welke accounts
daadwerkelijk overschreven worden; dat is D-122 en het ligt bij Ferry en Middleware App. Wat
jullie wél kunnen: **D-86** zodra fase 2 staat, en **spoor C**.

📌 Jullie D-110-oplevering zelf blijft overeind en is goed werk — `firmDllActive` dat letterlijk
de twee voorwaarden draagt en de samenvoeging ná `acctDLL := pfDLL` was precies de goede
redenering. Daar verandert niets aan.

---

## 🟩 Backtest Setup — D-113 erbij, en spoor B loopt door

### D-113 (nieuw) — de engine remt op iets wat het script niet meer heeft

Pine remt sinds D-110 op `min(4 × SL × qty, firm_dll)`; `backtest/engine.py` modelleert nog
alleen `cfg.acct_dll`. **Dat is een pariteitsverschil op dagniveau.**

De vorm is bekend en dat maakt het klein: Pine Dev noteerde dat `acct_dll = 4 × SL × qty` de
eigen rem **exact** reproduceert. Wat mist is de `min` met de firmawaarde, plus dat de rem op
`lossBasisEff` meet in plaats van op de ruwe running-P&L.

📌 De ⅓-ruimteterm hoort er **niet** in — die vraagt de balans uit T3 en zit ook niet in Pine.

### D-101 / D-102 — spoor B

Increment 3b (statements) en 4 (evaluator) staan nog open. D-102 kan pas starten als de
evaluator een draaibare backtest uit een `.pine` produceert.

---

## 🟪 Web — jullie zijn deze ronde vrij, en dat is een besluit

D-83 en D-84 **gaan naar Middleware App** (D-120): de settings-tab komt in de bestaande
cockpit, er komt geen nieuwe app-shell in `web/**`. Dat scheelt jullie het meeste werk uit mijn
statusopname van 30-09.

Wat blijft: `resultaten.astro` en `public-stats.json` volgen zodra het eval-format er is
(D-74), en **D-34** (publieke claims) staat nog op review.

⚠️ Herinnering die nog steeds geldt: **er is geen geldige vlootrangorde** en de OOS-klok staat
op nul. Geen enkele publieke claim mag suggereren dat deze vloot out-of-sample bewezen is.

---

## 🟧 Analyses & Data — de fleet-vraag van deze week

Jullie staan vast in de ronde (besluit Ferry 28-09) en gebruiken het voorvoegsel `A-`.

**D-112 staat nog open:** klopt `docs/fleet-report-spec.md` met hoe jullie het fleet-startschema
opstellen? Dat document is sinds 28-09 de acceptatietest voor D-96 en D-97, dus een afwijking
daar wordt straks een afgekeurde fase.

**Nieuw deze ronde, en het raakt jullie cijfers direct:** uit de PMT-export blijkt dat de
gehandelde contractgrootte per account varieert (2, 5, en één op **35**) en dat er sinds 18-09
een middleware-override van 39 accounts op qty 1 draait. 🔴 **Elke doorlooptijd- of
payout-per-dag-berekening die een vaste qty aanneemt, klopt daarmee niet.** Geef aan welke van
jullie cijfers dat raakt en wat jullie nodig hebben om het te corrigeren.

---

# ADDENDUM ronde 06-10 — nieuwe items, en twee die vóór alles gaan

_Toegevoegd door de Scrum Master. Watermerk: `HEAD`, 06-10._

## Wat er sinds 05-10 bij kwam

| item | bij wie | wat |
|---|---|---|
| **D-127** 🔴 | Ferry | 018 staat in `Developer`-modus: **alle** accountbeschermingen uit op een live funded account |
| **D-128** 🔴 | Ferry → SM | de live bronboom loopt achter op de repo; D-82 bestond niet op de VPS |
| **D-126** 🔴 | Pine Dev | `f_firmLadder` wordt gegenereerd en nooit aangeroepen, 13/13 |
| **D-125** 🔴 | Pine Dev | deadlock: `pmtBlock` eist geen `consistencyOK`, account kan er niet uit |
| **D-124** | Pine Dev | `useWaitForCap` is een harde constante, geen input |
| **D-123** ✅ | — | opgelost: 018 stond stil door `pmtBlock`, niet door een poort |
| **D-82** ✅ | — | config-API draait (401), **fase 2 is bouwbaar** |

## 🟨 Pine Dev — één ronde, drie items, één poort

**D-124, D-125 en D-126 raken alle drie dezelfde payout-poort. Doe ze samen, in één commit-reeks, met één OOS-reset.** Losse rondes betekent drie keer de klok op nul.

Volgorde die ik zou aanhouden:
1. **D-126 eerst** — `f_ladderCap` → `f_firmLadder(firmPreset, effPayoutNr)`. Dat is een bugfix met de waarden al in de registry, en hij maakt de rest meetbaar: zolang de ladder fout is, weet je niet wanneer de poort hóórt te sluiten.
2. **D-125** — `pmtBlock` moet ook `consistencyOK` eisen, of hangen op `payoutReady`.
3. **D-124** — `useWaitForCap` naar een input, **default `true`**.

🔑 **En bouw de poort die dit had voorkomen:** breid `gen_pine_firms.py` uit zodat **elke gegenereerde `f_firm*` minstens één call-site moet hebben**, anders faalt de generatie hard. `f_firmLadder` stond er maanden ongebruikt in en niets merkte het op. Zelfde vorm als `owner_dll_check.py`.

⛔ Nog steeds **niets aan de qty** tot D-122/D-128 helder zijn.

## 🟦 Middleware App — fase 2 is open, en D-116 is nu urgent

**De config-API draait en staat dicht (401).** Begin met **D-119** (leeshelft), dan **D-83/D-84**.

🔴 **En neem D-116 serieuzer dan vorige ronde:** D-123 liet zien dat de blokkademelding *"⛔ Order NIET geplaatst"* vermoedelijk tussen de 103 weggegooide berichten zat. Een weggegooide waarschuwing is duurder dan een weggegooide kaart. Ferry draait nu `MEX_RENDER_ENABLED=false` als noodmaatregel — die kan pas terug als de fall-through er is.

📌 **D-128 raakt jullie direct:** wat jullie in de repo opleveren, bereikt de VPS niet automatisch. Zodra de meting binnen is komt er een uitrolstap; neem in jullie oplevering voorlopig expliciet op *"dit staat in de repo en is niet uitgerold"*.

## 🟩 Backtest Setup — D-113 en spoor B

Ongewijzigd: D-113 (engine remt op `acct_dll`, Pine op de `min`), plus increment 3b en 4.

📌 **Nieuw signaal uit D-126 dat jullie aangaat:** de payout-ladder in de registry is per programma verschillend (250K legacy → `[3000,3000,3000]`). Als `fleet.py` of de funded-sim een vaste ladder aanneemt, klopt dat voor niet-Apex-50K niet. Meld of dat zo is.

## 🟪 Web — vrij, en dat blijft zo

D-83/D-84 zijn naar Middleware App (D-120). Resteert: `resultaten.astro` + `public-stats.json` zodra het eval-format er is, en **D-34** op review.

## 🟧 Analyses & Data — D-112, plus de qty-vraag

D-112 (review `fleet-report-spec.md`) staat nog open. En de vraag van 05-10 blijft: **welke van jullie cijfers nemen een vaste contractgrootte aan?** De PMT-export laat 1, 2, 5 en 35 zien.

## 🟥 MCP trader-dev — vanaf nu in de ronde

Deze rol staat in `docs/CHAT_INSTRUCTIE.md` maar had **nul items op het bord en nul regels in de inbox**. Dat is dezelfde fout als bij Analyses & Data: wie geen map bezit, valt uit de eigenaarstabel en dus uit de ronde.

➡️ **Vanaf nu vast in de ronde, voorvoegsel `M-` voor een eigen besluitregister.** En de werkafspraak: **open vragen horen in `docs/inbox.md`**, niet alleen in de chat — daar bereiken ze niemand. Zet je openstaande vragen daar neer, dan pak ik ze in de volgende ronde op.
