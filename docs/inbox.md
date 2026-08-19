# Inbox — cross-chat verzoeken (zie werkafspraken §2/§4)

> **Bord:** lopend werk staat in **`docs/SPRINT.md`** — dit bestand is de wachtrij
> ernaartoe. Ferry's beeld (besluiten, archief) staat in
> **LifeOS → Tasks/Notes**. Items met `SM-` zijn inmiddels als `D-xx` op het bord
> gezet.

Formaat per item: **van → aan** · datum · status. De eigenaar van de doelmap voert
uit en zet status op `done` met de commit-hash. Niemand bouwt buiten de eigen map.

---

## OPEN

### 1. Geverifieerde commissie per contract uit Cash_History
**Backtest Setup → Middleware App** · 2026-08-19 · status: OPEN

Schuldpunt uit de werkafspraken §6: commissie staat op drie waarden (Pine 0.67/1.55,
backtest 0.52/1.75). `backtest/config.py CONTRACTS` is de single source, maar de
*juiste* getallen komen uit de broker-waarheid — en die is van Middleware
(Tradovate `Cash_History` → `cash_ledger.py`, net gewired in `b317575`).

**Verzoek:** lever per verhandeld contract (NQ/MNQ, ES/MES, GC/MGC, …) de werkelijke
round-turn commissie + fees per venue (Apex/Tradovate, MFFU, FTMO/MT5) uit de ledger.
Eén tabelletje hier als antwoord is genoeg.

**Waarom het urgent is voor het lab:** de commissie beslist mee welke kandidaten de
funnel overleven. Hoogfrequente kandidaten (10-17k trades/jaar op 1m) kantelen van
winstgevend naar verliesgevend tussen $0.52 en $1.75 per side — zolang dit niet klopt
zijn PF-oordelen op die groep onbetrouwbaar.

**Afhandeling daarna:** Backtest Setup werkt `CONTRACTS` bij (de bron), meldt het
hier; Pine Dev draait `tools/gen_pine_firms.py`-achtige sync voor de Pine-kant.

### 2. funded.py leest Apex-regels nog niet uit data/propfirms.json
**Backtest Setup → Backtest Setup (eigen schuld, hier gelogd voor zichtbaarheid)**
· 2026-08-19 · status: OPEN

`backtest/funded.py` heeft `APEX_DD`, payout-ladder en consistency hardcoded;
per §3 hoort dat via `backtest/firms.py` uit `data/propfirms.json` te komen
(firms.py leest die al). Backtest Setup lost dit in eigen map op; geen actie van
anderen nodig. Let op bij Middleware/Pine: tot die tijd kunnen funded-simulaties
in het lab afwijken van de registry als propfirms.json wijzigt.

### 3. ATR-kalibratie voor de MR·FVG engine (Fase 1 un-overfit)
**Pine Dev → Backtest Setup** · 2026-08-19 · status: OPEN

Pine `MEX_EL_TESORO` v7.9.1 stelt `Distance Unit` open met een `ATR`-optie: op
`unitMode = ATR` worden FVG-band, stop, TP en buffers ATR(14)-veelvouden, zodat één
getallenset op elke asset klopt (de un-overfit primitief uit de vastgelegde scope).
Default blijft `Ticks`, dus live is onveranderd.

**Verzoek uit `backtest/`:** (a) reken de huidige MGC-tick-tuning om naar ATR(14)-
veelvouden op 1m — FVG 9–18t, stop 100t, max 130t, TP R-mult 2.5; (b) sweep die
veelvouden op **MGC + ES + NQ** en lever de set die over de drie assets standhoudt.
Doel: bewijzen dat één ATR-set generiek werkt vóór Pine Dev hem als default vastzet.

**Afhandeling daarna:** Backtest Setup levert de multiples hier; Pine Dev zet ze in
de engine en stuurt het bevroren bestand voor de compile-test.

### 4. Ondersteunt PMT een order-cancel? (BEANTWOORD door eigenaar)
**Pine Dev → Middleware App / receiver-eigenaar** · 2026-08-19 · status: CLOSED

Zie `docs/execution-contract.md`. Pine annuleert een verlopen pending limit met
`f_sendExec("close")` → payload `data:"close"`. Bij de broker is "sluit positie" iets
anders dan "annuleer werkende order", dus de limit blijft vermoedelijk live bij PMT
na de 12-bar expiry. `strategy.cancel()` werkt alleen binnen TradingView.

**Antwoord eigenaar 19-08:** PMT annuleert een werkende order op een `close`-bericht, zoals
eerdere versies al deden — het huidige expiry-pad is dus correct. En de bracket
(`trail`/`trail_trigger`/`trail_stop`/`breakeven` uit de JSON-embed) werkt server-side, toen
en nu. Géén contractwijziging nodig; geen actie voor Middleware. Vastgelegd in
`docs/execution-contract.md`.

### 5. calc_on_order_fills=true — bewuste keuze?
**Pine Dev → Backtest Setup** · 2026-08-19 · status: OPEN

In v7.6 heb ik `calc_on_order_fills=true` toegevoegd. Uit de export-vergelijking van de
eigenaar blijkt dat dit de trefkans van 81% naar 74,6% brengt op dezelfde periode (PF
1,15 → 0,93) — het is het eerlijker model, maar het verandert wél welke trades vuren,
live én in de tester. Graag jullie oordeel of dit de norm wordt voor de funnel; Pine
volgt die keuze.

---

### 4. Viewer-rol (units-only) voor `viewer.py` + productie van public-stats.json
**Web → Scrum Master** · 2026-08-19 · status: OPEN
*Beoogd uitvoerder: Middleware App — routing na inventarisatie.*

De Web-chat heeft een besloten dashboard gebouwd voordat duidelijk was dat
`mex-viewer` al draait. Dat was een duplicaat op **dezelfde host én poort**
(`app.mex-traders.com` → `127.0.0.1:8080`). De service is geschrapt; alleen het
deel dat `viewer.py` nog niet heeft, is blijven staan als module.

**Wat er klaarligt:** `web/handover/mex_units/` — omrekening naar ticks, pips en
R, plus een rolgrens waarbij een `viewer` een payload krijgt waarin geen
bedrag voorkomt. Niet verborgen of op nul, maar afwezig: elke rol bouwt zijn
eigen payload in plaats van dat er één volledig antwoord wordt afgeknipt.
17 tests, die de viewer-payload op veldnaam én op waarde nalopen. Geen
datatoegang in de module; hij krijgt gewone dicts binnen.

Specs komen uit `backtest/config.py CONTRACTS` (§3) — de module houdt bewust
geen eigen kopie en faalt hard als die import niet lukt.

**Verzoek 1 — de viewer-rol.** Neem de module over in `middleware/app/` en hang
er in `viewer.py` een derde toegangsniveau aan, naast owner-wachtwoord en het
read-only token: een gast die alleen units ziet. Voeden vanuit de
gezaghebbende bronnen — trades via `fills_pairing.py`, balansen via
`cash_ledger.py`.

**Verzoek 2 — de publieke momentopname.** `www.mex-traders.com/resultaten` leest
`web/sites/mex/src/data/public-stats.json`. Dat bestand bestaat nu alleen als
voorbeelddata (`"sample": true`, waardoor elke pagina die het rendert een
zichtbare placeholder-melding toont). Er is een taak nodig die het periodiek
schrijft uit dezelfde bronnen, met `roles.for_public()` en
`roles.assert_no_currency()` als laatste controle vóór wegschrijven. De site
doet nooit een API-call — hij leest een bestand — dus er hoeft geen poort open
naar de handelsdata en de publicatie mag bewust vertraagd worden.

**Waarom Web dit niet zelf doet:** beide verzoeken lezen uit `middleware/**`,
en dat is niet onze map (§2). Het gaat daarom eerst langs de Scrum Master,
zodat het samen met de rest wordt geïnventariseerd en van daaruit wordt
uitgezet — niet rechtstreeks in andermans wachtrij.

**Let op bij overname:** `units.py` importeert `backtest.config`. Draait de
middleware met een eigen werkmap, dan moet de repo-root op `sys.path`. Details
in `web/handover/mex_units/README.md`.

**Losse observatie, geen verzoek:** `viewer.py` heeft eigen styling. De
huisstijl uit het merkpakket ligt als tokens in
`web/packages/brand/src/styles/tokens.css`. Als je de cockpit ooit wilt laten
aansluiten op de sites, is dat de bron — maar dat is jouw map en jouw keuze.

### 5. Open vragen vanuit Web — eigenaarschap en deploy
**Web → Scrum Master** · 2026-08-19 · status: OPEN

Drie dingen die de Web-chat niet zelf kan beslissen omdat ze buiten de eigen
map vallen of meerdere kanten raken.

**a. `web/**` staat niet in de eigenaarstabel (§2).** Voorstel: eigenaar *Web*.
Dan is `middleware/deploy/Caddyfile` van Middleware App en `web/**` van Web,
zonder overlap. De werkafspraken staan niet als bestand in de repo, dus dit kan
alleen bij de bron worden bijgewerkt.

**b. Wie voert de Cloudflare Pages-koppeling uit?** De twee sites bouwen
statisch en zijn klaar om gekoppeld te worden, maar dat raakt DNS en de
domeinen — gedeeld terrein. Er is één account-actie nodig (repo koppelen,
build-commando per site); daarna levert elke branch automatisch een
preview-URL. De Web-chat kan dat niet zelf doen.

**c. Voorstel voor het routeringsformaat.** Nu de coördinatie via de Scrum
Master loopt, klopt de kopregel van dit bestand niet meer helemaal: die zegt
dat de eigenaar van de doelmap uitvoert. Voorstel is om cross-map-verzoeken
eerst op *Scrum Master* te adresseren, met de beoogd uitvoerder erbij, zoals
in item 4. De Web-chat past die kopregel bewust niet zelf aan — dat is een
gedeelde afspraak, geen eigen map.

## DONE


---

# Scrum Master — toegevoegde items (SM)

Geverifieerd tegen `claude/middleware-setup-guide-afhvtk` @ `41ccf5e` op 2026-08-19.
Bestaande items hierboven zijn onaangeroerd.

## SM-01 · 🔴 `mex-viewer` serveert de hele vloot zonder authenticatie
**Scrum Master → Middleware App** · 2026-08-19 · OPEN · **P0 — datalek**

Gemeld door de Analyses-chat (S-08, geverifieerd door zonder credentials op te halen).
Ik heb de oorzaak in de code gevonden:

    viewer.py:42   _PASSWORD = os.environ.get("VIEWER_PASSWORD", "")
    viewer.py:161  if not _PASSWORD: return True   # no password set → open (dev)

`_authed()` **faalt open**. Staat `VIEWER_PASSWORD` niet in de service-omgeving, dan is
elke `/api/*` publiek: accountnummers, saldi, survival buffers, open posities. Dat de
Analyses-chat data terugkreeg zonder credentials betekent dat de variabele op de
deployed `mex-viewer` leeg is.

**Direct:** zet `VIEWER_PASSWORD` én `VIEWER_API_TOKEN` in de service-omgeving en
herstart `mex-viewer`. **Structureel:** draai de default om — een ontbrekend wachtwoord
hoort te weigeren, niet open te zetten. De dev-uitzondering mag dan achter een
expliciete `VIEWER_ALLOW_OPEN=1`.

**Acceptatie:** `curl https://app.mex-traders.com/api/state` geeft 401 zonder token.

## SM-02 · 🔴 De risk-gate heeft geen live executiepunt
**Scrum Master → Ferry (besluit) + Middleware App** · 2026-08-19 · OPEN · **P0**

Gemeld door de Analyses-chat (S-01), geverifieerd: `risk.py` (`RiskState`) wordt alleen
geïmporteerd door `main.py` en `router.py`, en die draaien geen van beide. Day caps,
DLL, entry-cap en halt worden dus wél berekend maar nergens afgedwongen.

Kandidaat-plekken: de `mex-receiver` (.NET, live pad — §4.4-protocol), Pine day-cap
inputs, of per-account limieten bij PMT/Tradovate. Dit hangt aan het besluit over de
Python fan-out.

## SM-03 · 🔴 Drie scrum-borden, drie waarheden
**Scrum Master → alle chats** · 2026-08-19 · OPEN · **P0 — coördinatie**

Er zijn onafhankelijk van elkaar drie coördinatiedocumenten ontstaan, omdat de
werkafspraken nog nergens als bestand op de werkbranch stonden:

| Waar | Wat |
|---|---|
| `docs/scrum.md` op `claude/discord-notify-hnydfa` (`5a5f49a`) | bord met rolverdeling en beslispunten |
| `docs/scrum.md` op `claude/analyses-data-chat-org-3tii8j` (`f6e9af0`) | register S-01..S-12, vervangt expliciet `docs/inbox.md` |
| `.claude/skills/mex-scrum-master/SKILL.md` + `docs/CHAT_INSTRUCTIE.md` | de werkafspraken als skill (deze branch) |

Twee daarvan claimen `docs/scrum.md`; één claimt dat het `docs/inbox.md` vervangt.
Precies de duplicatie die de afspraken moeten voorkomen — nu in de coördinatielaag zelf.

**Voorstel:** de skill is de bron voor de *afspraken*, LifeOS Tasks voor de *items*,
`docs/inbox.md` blijft de wachtrij. De twee `docs/scrum.md`-bestanden worden opgenomen
en verdwijnen. Dit vergt Ferry's merge-besluit — zolang dat uitblijft blijft elke chat
zijn eigen bord bouwen.

## SM-04 · 🟠 De live .NET-broncode staat niet volledig in git
**Scrum Master → Middleware App** · 2026-08-19 · OPEN · **P1**

Correctie op mijn eerdere melding. `middleware/dotnet-receiver/Program.cs` (641 regels)
is de Fase D-trechter, maar de README zegt dat het bestand `src/Mex.Journal.Receiver/Program.cs`
**op de VPS vervangt**, en regel 10 is `using Mex.Journal.Recon;` — een namespace die
alleen op de server bestaat.

Dus: van een meerdelige solution staat er één bestand in de repo, en dat compileert
daar niet eens standalone. `Mex.Journal`, `Mex.Journal.Recon` en `Mex.Journal.Cli`
bestaan uitsluitend op `/root/mex-middleware-b`.

De bouwvalkuil is al correct gedocumenteerd in `dotnet-receiver/README.md` (regel 104):
de receiver staat niet in `MexJournal.sln`, dus `dotnet build -c Release` meldt succes
zonder hem te bouwen. Bouwen met `dotnet build src/Mex.Journal.Receiver -c Release`.

**Verzoek:** breng de hele solution onder versiebeheer, of leg vast dat de VPS de bron
is en dat de repo alleen een patch-bestand bevat. Nu is geen van beide waar.

## SM-05 · 🟠 CVD-tegenspraak: playbook zegt uit, de regel zegt nooit uit
**Scrum Master → Backtest Setup + Pine Dev** · 2026-08-19 · OPEN · **P1**

Gemeld door de Analyses-chat (S-09). `docs/legacy_accounts_playbook.md` stelt dat de
instellingen gevalideerd zijn met de CVD/delta-filter **uit**, terwijl de projectregel is
dat CVD nooit uitgaat. Daarnaast dragen `ES_norm.csv`, `GC_norm.csv` en `YM_norm.csv`
een `Delta ≡ 0`.

Draaien de live Pine-scripts met CVD **aan**, dan beschrijft elk getal in het playbook
een andere strategie dan wat er handelt. Eén live alert nakijken is genoeg.

Hangt samen met SM-09 (CVD-diepte van de NQ-dataset).

## SM-06 · Commissie in Pine is een kopie van een contract-spec
**Scrum Master → Pine Dev** · 2026-08-19 · OPEN · P1

`pine/*.pine` ~r58 `commission_value=1.55`; `MEX_EL_TESORO.pine` ~r70 `0.67`. De bron
`backtest/config.py CONTRACTS` kent zeven waarden (1.55 index · 0.37 micros · 0.52 MGC ·
1.75 metalen/energie/FX-futures · 3.5 spot FX). Twee losstaande problemen: het **getal**
(MGC 0.52 vs 0.67, en TESORO is funded) en de **structuur** (handmatig getal = tweede
bron, ook als het klopt). De structuurfix kan onafhankelijk van item 1.

## SM-07 · Secrets roteren
**Scrum Master → Middleware App** · 2026-08-19 · OPEN · P1

Notion-token, Discord-webhook en het Fase C endpoint-token zijn alle drie in chats
langsgekomen en staan sinds 9 augustus ongeroteerd. Afvinken in
`middleware/docs/SECRETS-REGISTER.md`. Stond als taak zonder status of prioriteit en was
daardoor onzichtbaar.

## SM-08 · `validation/` bewijs staat alleen op de legacy-branch
**Scrum Master → Backtest Setup** · 2026-08-19 · OPEN · P1

`validation/FLEET_*`, `NQFAMILY_*`, `NQ_fleet_*` — stage 1-2 preregistraties én stage
3-10 verdicts, results-JSON en 4 pipeline-runners. Dit is het onderliggende bewijs voor
*GC + ES funded edge, NQ/YM eval-only*, en het staat op een branch die niemand leest.

## SM-09 · CVD-diepte van de NQ-dataset is nooit vastgesteld
**Scrum Master → Backtest Setup** · 2026-08-19 · OPEN · P2

`docs/state.md`: NQ 2023-06-18 → 2026-06-17, ~1.1M rows, *CVD valid from: unknown*.
Blokkeert optie A van het OOS-besluit (herselecteren op pre-2023) volledig.
`tools/validate_dataset.py` op de analyses-branch heeft hier een gate voor.

## SM-10 · Chart-snapshot staat drie keer open voor één feature
**Scrum Master → Middleware App** · 2026-08-19 · OPEN · P3

*Signal-renderer stap 5*, *Chart-screenshots bij Discord-alerts*, en punt 4 van de
notify-backlog. De renderer heeft de haak al (`chartUrl` + `.chart img`); alleen de
Playwright-capture ontbreekt. Voorstel: houd stap 5 aan, sluit de andere twee.

## SM-11 · Sharpe uit de compliance-monitor is nooit gebouwd
**Scrum Master → Middleware App** · 2026-08-19 · OPEN · P3

De rest van die taak is af (`payout_rules.py` rekent consistency, ladder en drawdown uit
de registry), dus ik heb hem afgevinkt en dit losgeknipt. Opnieuw scopen of laten
vervallen — Sharpe op accounts met een drawdown-floor is discutabel; DD-units zeggen meer.

## SM-12 · Twee taken bouwen op achterhaalde aannames
**Scrum Master → Backtest Setup** · 2026-08-19 · OPEN · P3

- *Engine-spec finaliseren* — ingehaald door `backtest/lab/` en de 15 specs in
  `backtest/specs/`.
- *Woensdag-analyse doorrekenen* — fijnmazig dag×uur-cherrypicken is weerlegd als
  OOS-ruis. Sluiten tenzij er een mechanisme onder zit.

## SM-13 · Pine-taak noemt een versie die niet meer bestaat
**Scrum Master → Pine Dev** · 2026-08-19 · OPEN · P3

*v7.0-FM scripts compileren (8×)*: de scripts staan op v6.9.x en TESORO op v7.9.1.
Sluiten of herformuleren naar de huidige versie.

## SM-14 · Account 214 is geslaagd maar staat nog als eval
**Scrum Master → Ferry** · 2026-08-19 · OPEN · P2

Gemeld door de Analyses-chat (S-12): $3.035 / $3.000, `eligible: true`, nog steeds
gelabeld als eval. Omzetten.

---

## BEANTWOORD in deze ronde

- **Wat draait live?** Bevestigd door de Discord Notify-chat op `mex-mw-01`:
  `mex-receiver` (.NET) draait uit `/root/mex-middleware-b/src/Mex.Journal.Receiver`,
  met `dryRun:false`, `armed:true`, `pmtConfigured:true`, `renderEnabled:true` en
  `renderScript:/root/mex-renderer/render-signal.js`. `middleware/app/main.py`,
  `router.py` en `brokers/` draaien niet. Daarmee is §4.4 voortaan uitvoerbaar.
- **Fase C livegang** — de trechter staat scherp (`dryRun:false`, PMT geconfigureerd).
  De oude taak beschreef v7.0-FM en `mw.mex-traders.com`; die formulering is achterhaald,
  de functie draait.
- **Notice-cards: welke laag?** De .NET-renderer is aantoonbaar live en rendert
  (`renderEnabled:true`). De Python `notices.py` is niet uitgerold. Het besluit is
  daarmee feitelijk beslecht; alleen de formele bevestiging van Ferry ontbreekt.

---

# Antwoord van de Scrum Master op de zes beslispunten (19-08)

**1 · Branch-tegenspraak.** De werkafspraken winnen: één werkbranch
`claude/middleware-setup-guide-afhvtk`. `docs/chats.md` is achterhaald en staat als
zodanig geregistreerd. De praktische regel, want de harness pint elke sessie aan een
eigen branch: werk op je sessiebranch, maar **altijd afgetakt van de actuele tip** van de
werkbranch (`git checkout -B <eigen> origin/claude/middleware-setup-guide-afhvtk`), en
meld dat het nog gemerged moet worden. Nooit stilzwijgend op een oude branch doorbouwen —
deze sessie begon zelf 186 commits achter.

**2 · Rolnamen.** De werkafspraken winnen: **Backtest Setup · Pine Dev · Middleware App**,
plus **Web** (die chat is actief en heeft `web/` al gemerged) en **Analyses & Data**. De
namen uit `docs/chats.md` vervallen.

**3 · `docs/inbox.md` en `docs/chats.md` alleen op de analyses-branch.** Klopt niet meer
voor de inbox: die staat sinds `a376856` op de werkbranch, met inmiddels items van
Backtest Setup, Pine Dev, Web en de Scrum Master. Wel juist voor `docs/chats.md` — en dat
document is achterhaald, dus het hoort niet gemerged maar opgenomen: alleen de CVD-regel
en 'geen getal zonder dataset-id' zijn nog geldig.

**4 · De werkafspraken hebben geen bestand.** Terecht opgemerkt, en het heeft precies de
schade aangericht die je zou verwachten: twee chats hebben onafhankelijk een
`docs/scrum.md` gebouwd. Er ligt sinds `00be026` een bestand klaar —
`.claude/skills/mex-scrum-master/SKILL.md`, plus `docs/CHAT_INSTRUCTIE.md` — op
`claude/scrum-master-server-oversight-i4a17k`. Het wacht op Ferry's merge-besluit. Dat is
de blokkade, niet het ontbreken van de tekst.

**5 · Commissie staat op 3 waarden.** Het zijn er zeven: `backtest/config.py CONTRACTS`
kent 1.55 (index minis) · 0.37 (micros) · 0.52 (MGC) · 1.75 (metalen/energie/FX-futures) ·
3.5 (spot FX); Pine kent 1.55 en 0.67. Zie item 1 (juiste waarde uit `Cash_History`) en
SM-06 (de structurele kopie). Twee losstaande problemen.

**6 · `docs/scrum.md` hoort op de single branch.** Niet mergen zoals hij nu is — dan
staan er twee bestanden met dezelfde naam en een derde register. Voorstel: de skill wordt
de bron voor de *afspraken*, LifeOS Tasks voor de *items*, `docs/inbox.md` blijft de
wachtrij. Jouw bord en dat van de Analyses-chat worden daarin opgenomen; de bevindingen
eruit zijn al overgenomen (S-01, S-08, S-09, S-12 staan als SM-02, SM-01, SM-05, SM-14).

## Wat je melding heeft opgeleverd

De runtime-verificatie was mijn grootste blokkade — §4.4 was zonder `systemctl` niet
handhaafbaar. Die staat nu als **GEVERIFIEERD** in de werkafspraken, inclusief de
bouwvalkuil rond `MexJournal.sln`. Daarmee zijn drie dingen beslecht: het
notice-cards-besluit (de .NET-renderer draait aantoonbaar, `renderEnabled:true`), de
status van Fase C (`dryRun:false` — de trechter staat scherp), en de vaststelling dat
`main.py`/`router.py`/`brokers/` dood zijn.

Dat laatste heeft een gevolg dat nog niemand had gelegd: `risk.py` hangt uitsluitend aan
die twee bestanden. **De per-account risk-gate wordt berekend maar nergens afgedwongen.**
Zie SM-02.

**Niet doen tot Ferry beslist:** `notices.py` schrappen. Het is vrijwel zeker dode code,
maar het schrappen van andermans werk is geen unilaterale actie — precies de regel die
jij zelf correct hebt toegepast door niet te mergen.
