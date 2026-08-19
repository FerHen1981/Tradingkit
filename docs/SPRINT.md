# SPRINT.md — het bord

> **De enige lijst met lopend werk.** Elke code-sessie leest dit eerst, claimt één item,
> en commit de claim vóór het werk begint. Vervangt `docs/scrum.md` (twee varianten) en
> de losse itemlijst in `docs/inbox.md`.
>
> Status: `todo` (vrij) · `wip` (in behandeling) · `review` (klaar, wacht op controle) ·
> `done` (goedgekeurd) · `blocked` (wacht op een ander item of op Ferry).
> Owner leeg = vrij te pakken.

**Stand:** 2026-08-19 · geverifieerd tegen `claude/middleware-setup-guide-afhvtk` @ `41ccf5e`

---

## Het claim-protocol

1. **Lees dit bestand** vóór je iets anders doet. Werk nooit aan een item dat al `wip`
   staat met een andere owner.
2. **Claim één item:** zet status op `wip`, vul je chatnaam in als owner, en **commit die
   ene regel meteen** — `git commit -m "claim: D-xx — <chatnaam>"` — vóór je aan de inhoud
   begint. Die commit is je slot.
3. **Een merge-conflict op dit bestand is het signaal**, geen fout: een andere sessie pakte
   hetzelfde item. Kies een ander item, forceer niet.
4. **Eén item tegelijk.** Rond af voor je een nieuw item claimt.
5. **Afronden:** wijziging gecommit → status op `review` → regel in `docs/DECISIONS.md`.
   Zet zelf niets op `done`; dat doet de Scrum Master bij de controle.
6. **Nieuwe ID's geeft de Scrum Master uit.** Heb je een nieuw item, zet het in
   `docs/inbox.md`; je krijgt er een D-nummer voor terug. Twee partijen die tegelijk
   het volgende vrije nummer pakken botsen namelijk *niet* in git — dat gebeurde op
   19-08 met D-34 — en dan staan er twee items met hetzelfde ID. `done`-items blijven
   staan als historie.

Raakt je werk iets buiten je eigen map of het live executiepad? Dan geldt daarnaast de
beslissingsboom uit de werkafspraken (`.claude/skills/mex-scrum-master/SKILL.md`).

---

## 🔴 Blokkeert geld of veiligheid

| ID | Status | Owner | Item |
|---|---|---|---|
| **D-35** | todo | Ferry + Middleware App | **De IPv4-fix is gecommit maar NIET gebouwd en NIET uitgerold** (`97c50cd`; Legacy heeft geen .NET SDK). De draaiende binary heeft nog het oude gedrag, met `dryRun:false` en `armed:true`: uitgaand verkeer kan via IPv6 → **PMT weigert orders**, en een weigering wordt weggeschreven als `sent 200` → **onzichtbaar in het journaal**. Blokkerend daarnaast: **`167.233.215.60` staat niet in de PMT IP-pool** — zolang dat niet geregeld is wordt er niets geplaatst, hoe de code er ook uitziet. Klaar pas na `dotnet build src/Mex.Journal.Receiver -c Release` + herstart, met `curl -s ifconfig.me` als controle. _(gemeld door Legacy 19-08)_ |
| **D-01** | review | Middleware App | **`mex-viewer` serveert de hele vloot zonder authenticatie.** `viewer.py:161` faalt open: staat `VIEWER_PASSWORD` niet in de omgeving, dan zijn `/api/state`, `/api/command` en `/api/widget` publiek — accountnummers, saldi, buffers, open posities. **OPGELOST** `8a14537`: `_authed()` faalt nu closed; open draaien vereist een expliciete `VIEWER_ALLOW_OPEN=1` en het dashboard meldt dan *fleet data is PUBLIC*. Vier tests in `middleware/tests/test_viewer_auth.py`. **Resteert voor Ferry:** `VIEWER_PASSWORD` + `VIEWER_API_TOKEN` zetten en herstarten — zonder wachtwoord weigert hij nu álles. _(was S-08 / SM-01)_ |
| **D-02** | blocked | Ferry | **De risk-gate heeft geen live executiepunt.** `risk.py` hangt uitsluitend aan `main.py` en `router.py`; die draaien niet. Day caps, DLL en halt worden berekend maar handhaven niets. Blocked by D-05. _(was S-01 / SM-02)_ |
| **D-03** | todo | Middleware App | **De reconciliatielaag heeft nooit gedraaid.** De Notion-database *MEX Reconciliation (live)* heeft een compleet schema en **0 rijen** (geverifieerd 19-08). Dat verklaart het gat dat Analyses vond: `realized_net` $21.597,35 vs `window_net` $31.424,81 — **$9.827,46** verschil dat precies deze laag had moeten vangen. _(was S-10 + S-11)_ |
| **D-04** | blocked | Ferry | **Notice-cards: bevestig de .NET-receiver als eigenaar.** Feitelijk beslecht — runtime toont `renderEnabled:true` met `/root/mex-renderer/render-signal.js`; `notices.py` is nooit uitgerold. Alleen de formele bevestiging ontbreekt, en zonder die bevestiging kan niemand mergen. **Eerstehands bewijs (Legacy, uitrol 11-08):** audit-log `card queued (tier B)` 01:28:52Z → `card sent 200` 01:28:57Z, kaart verscheen in Discord; een volledige tradecyclus liep erdoorheen (FILL 6ct @ 4474,8 → RISK OFF → TRAIL → EXIT +$153,96). De Python-tak bleek dood toen patches daar geen effect op de executie hadden. |
| **D-05** | blocked | Ferry | **Python fan-out: afvoeren of alsnog activeren?** `main.py`/`router.py`/`brokers/` zien er compleet uit en doen niets. Wortel onder D-02 en D-04. |

## 🟠 Bronnen die niet kloppen of onbereikbaar zijn

| ID | Status | Owner | Item |
|---|---|---|---|
| **D-06** | wip | Legacy (Middleware App) | **De live .NET-broncode staat niet volledig in git.** Alleen `middleware/dotnet-receiver/Program.cs` (641 r), en dat *vervangt* `src/Mex.Journal.Receiver/Program.cs` op de VPS; `using Mex.Journal.Recon;` bestaat hier niet. Bouwvalkuil: de receiver zit niet in `MexJournal.sln`, een kale `dotnet build -c Release` meldt succes zonder hem te bouwen. Bouwen met `dotnet build src/Mex.Journal.Receiver -c Release`. **Geclaimd door Legacy 19-08**; die chat mag niet naar deze branch pushen, dus de Scrum Master zet de regel. **Voorstel overgenomen: de hele solution onder versiebeheer**, niet 'de VPS is de bron' vastleggen — dat laatste laat live code zonder historie en zonder review, en de sln-valkuil laat een deploy stil mislukken met *Build succeeded*. _(was S-07 / SM-04)_ |
| **D-07** | todo | Middleware App | **Werkelijke commissie per contract uit `Cash_History`.** De bron `backtest/config.py CONTRACTS` kent zeven waarden; Pine twee; de FLEET-validatie mat micro 0.67. Lever per contract de round-turn commissie + fees per venue. _(was inbox 1 / S-06)_ |
| **D-08** | review | Pine Dev | **De commissie in Pine is een kopie van een contract-spec.** Ook als het getal klopt is een handmatig getal een tweede bron. `PropFirms.pine` wordt al gegenereerd; de contract-specs niet. Onafhankelijk van D-07 op te lossen. _(was SM-06)_ |
| **D-09** | todo | Backtest Setup | **CVD-tegenspraak.** `legacy_accounts_playbook.md` zegt dat de instellingen zijn gevalideerd met de delta-filter **uit**; de projectregel is dat CVD nooit uitgaat. `ES/GC/YM_norm.csv` dragen `Delta ≡ 0`. Draaien de live scripts CVD aan, dan beschrijft elk getal in het playbook een andere strategie. Eén live alert nakijken. _(was S-09 / SM-05)_ |
| **D-10** | blocked | Backtest Setup | **CVD-diepte van de NQ-dataset is onbekend.** Blokkeert optie A van D-18. Wacht op de pilot-export + validator-output — **blocked by D-36**. _(was S-13 / SM-09)_ |
| **D-11** | todo | Middleware App | **Secrets roteren** — Notion-token, Discord-webhook, Fase C endpoint-token. Alle drie in chats langsgekomen, sinds 9 aug ongeroteerd. Afvinken in `middleware/docs/SECRETS-REGISTER.md`. _(was SM-07)_ |
| **D-20** | todo | Scrum Master | **De Notion-ids in `CLAUDE.md` zijn deels dood.** *MEX Reconciliation* heeft 0 rijen (geverifieerd). Fleet Performance en Trade Journal nog te controleren. _(was S-11)_ |

## 🔵 Werk dat vastzit op een merge

| ID | Status | Owner | Item |
|---|---|---|---|
| **D-12** | todo | Backtest Setup | **`validation/` bewijs staat alleen op de legacy-branch** — stage 1-2 preregistraties én 3-10 verdicts, het onderliggende bewijs voor *GC + ES funded edge, NQ/YM eval-only*. _(was SM-08)_ |
| **D-13** | blocked | Ferry | **Merge-plan voor de drie resterende branches** (website is al gemerged): legacy (.NET + validation), discord-notify (notices.py + tests), analyses (state.md, validate_dataset.py, goals.py, 3 engine-fixes). Blocked by D-04. _(was S-03)_ |
| **D-36** | todo | Ferry | **Lever de NQ pilot-export met CVD-diepte** — deblokkeert D-10 en daarmee optie A van D-18. Formaat volgens `docs/data_export.md` (Quantower-spec, analyses-branch). Backtest Setup draait daarna `tools/validate_dataset.py` met de CVD-gate en rapporteert op het bord. Let op: die validator staat óók nog op de analyses-branch, dus D-13 loopt hier doorheen. _(gevraagd door Backtest Setup 19-08)_ |
| **D-37** | todo | Legacy (of Ferry) | **Lever één recente live alert-payload** uit het executiepad — deblokkeert D-09. Backtest Setup vergelijkt hem tegen het playbook en de norm-datasets om te bepalen of de live scripts CVD aan of uit hebben. Read-only pad op de VPS mag ook. **Secrets eruit** vóór levering (webhook-URL's, tokens). _(gevraagd door Backtest Setup 19-08)_ |
| **D-19** | todo | Ferry | **`docs/**`, `tools/**` en `validation/**` hebben geen eigenaar** terwijl meerdere chats erin schrijven. _(was S-02)_ |

## 🟡 Lopend werk

| ID | Status | Owner | Item |
|---|---|---|---|
| **D-14** | wip | Backtest Setup | `backtest/funded.py:19` heeft `APEX_DD` hardcoded terwijl `firms.py` de registry al leest. _(was inbox 2)_ |
| **D-15** | todo | Backtest Setup | ATR-kalibratie MR·FVG: tick-tuning omrekenen naar ATR(14)-veelvouden en sweepen op MGC + ES + NQ. _(was inbox 3)_ |
| **D-16** | todo | Backtest Setup | `calc_on_order_fills=true` — wordt dit de norm voor de funnel? Trefkans 81% → 74,6%, PF 1,15 → 0,93. Eerlijker model, maar het verandert welke trades vuren. _(was inbox 5)_ |
| **D-17** | todo | Middleware App | Viewer-rol (units-only) overnemen uit `web/handover/mex_units/` + `public-stats.json` periodiek schrijven. _(was Web-inbox 4)_ |
| **D-18** | blocked | Ferry | **OOS-venster 2023-2026 is opgebrand** — herselecteren op pre-2023 of heretiketteren als validatie. Blokkeert elke publieke claim. Blocked by D-10 voor optie A. |
| **D-21** | todo | Ferry | Account 214 is geslaagd ($3.035/$3.000, `eligible:true`) maar staat nog als eval. _(was S-12)_ |
| **D-34** | review | Web | **Publieke claims in `web/**` afzwakken zolang D-18 open staat.** De sites beweren op zes plekken dat er een *gevalideerde edge* is; het OOS-venster daarachter is opgebrand. Betreft `public-stats.json`, `resultaten.astro`, de homepage, de pijlerpagina, `methodiek.mdx` en de prop-firm-gids. Begrippen die het *concept* validatie uitleggen blijven staan. Blocked-by-strekking van D-18, maar zelfstandig uit te voeren. |

## ⚪ Later

| ID | Status | Owner | Item |
|---|---|---|---|
| **D-22** | todo | Middleware App | Chart-snapshot staat 3× open voor één feature. De renderer heeft de haak (`chartUrl`); de Playwright-capture ontbreekt. Houd er één aan. _(was SM-10)_ |
| **D-23** | todo | Middleware App | Sharpe uit de compliance-monitor is nooit gebouwd — opnieuw scopen of laten vervallen. _(was SM-11)_ |
| **D-24** | done | Pine Dev | Herformuleerd. "v7.0-FM" bestond nooit; de fleet staat op v6.9.5 (7 scripts) en TESORO op v7.9.2. Compile-schuld is nu concreet: **TESORO v7.9.2 wacht op een paste-test in de Pine-editor** (richting-gate + D-08), de andere 7 zijn ongewijzigd sinds hun laatste groene compile op v6.9.5 behalve de gegenereerde regio + commissie uit D-08 — die 7 hebben één compile-ronde nodig zodra iemand ze aanraakt. _(was SM-13)_ |
| **D-25** | todo | Backtest Setup | Twee taken bouwen op weerlegde aannames: engine-spec (ingehaald door het lab) en woensdag-analyse (cherrypicking weerlegd). _(was SM-12)_ |
| **D-26** | todo | Scrum Master | `docs/chats.md` archiveren; eerst de CVD-regel en 'geen getal zonder dataset-id' redden. |
| **D-27** | todo | Backtest Setup | `docs/state.md` is nooit ingevuld — live settings `_TBD_`, `data/manifest.json` bestaat niet. |
| **D-28** | blocked | Middleware App | Notify-kanaal: zes uitbreidingen. Blocked by D-04 — de helft zit al in de receiver. |
| **D-29** | todo | Ferry | `web/**` formeel als *Web* in de eigenaarstabel. De merge is al gebeurd. |
| **D-30** | todo | Ferry | Vier vervallen Notion-items op workspace-niveau verwijderen (API kan niet naar de prullenbak). |
| **D-31** | todo | Ferry | Duurzame route naar runtime-waarheid: gecommitte snapshot of read-only ops-endpoint. Nu hangt het ervan af of een chat toevallig op de VPS kan. |
| **D-32** | done | Ferry | ~~Bevoegdheid Scrum Master~~ — **beantwoord 19-08: mag zelf corrigeren.** Grenzen vastgelegd in de werkafspraken §1c. |
| **D-33** | done | Ferry | ~~Toezichtritme~~ — **beantwoord 19-08: hybride, op mutaties.** Werkwijze en watermerk vastgelegd in §1d. |

---

## Watermerk — laatste toezichtronde

> De Scrum Master begint elke sessie met `git fetch origin --prune` en vergelijkt
> hiermee. Alles wat nieuwer is dan deze hashes is nog niet beoordeeld.
> **Werk dit blok bij aan het eind van elke ronde.**

| Branch | Beoordeeld t/m | Datum |
|---|---|---|
| `claude/middleware-setup-guide-afhvtk` | `d568233` | 2026-08-19 |
| `claude/legacy-accounts-scripts-analysis-ui0j6m` | `2f05103` | 2026-08-19 |
| `claude/discord-notify-hnydfa` | `5a5f49a` | 2026-08-19 |
| `claude/analyses-data-chat-org-3tii8j` | `f6e9af0` | 2026-08-19 |
| `claude/pine-dev-l410a6` | `dc567e8` | 2026-08-18 |
| `claude/mex-traders-website-ont1mk` | `9920af1` | opgenomen in de werkbranch |
| `claude/mcp-trader-dev-sse-ibl64y` | `34537f5` | dood — opgenomen in de werkbranch |
| `main` | `c767a0d` | 2026-07-29 |
