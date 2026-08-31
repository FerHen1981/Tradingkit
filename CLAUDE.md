# Tradingkit — project memory

## Brand & philosophy
- **Pips and Palm Trees** — website **pipsandpalmtrees.com**.
- Core framing: *the whole game is about pips and ticks.* Execution quality (slippage in
  ticks on futures, pips on FX) is a first-class metric, not an afterthought — which is why
  the middleware has a full reconciliation layer measuring it per trade × venue.

## What this repo is
An automated prop-firm trading system with three parts:
- `backtest/` — Python bar-by-bar backtester + walk-forward eval funnel + prop-firm registry.
- `pine/` — Pine v6 strategies, Spanish "El ___" names. **De v6.9.5-familie is vervangen**
  door de `v1_0_0`-lijn uit `MEX_FLEET_PACKAGE_2026-08-23` (zie hieronder).
- `middleware/` — the control plane: one TradingView alert → fan-out across channels.

## De vloot (stand 2026-08-23 — vervangt de oude GC+ES-conclusie)

> ⚠️ **De regel "funded edge = alleen GC + ES, NQ/YM eval-only" is INGETROKKEN** (Ferry, 24-08).
> Die kwam uit de funnel van vóór de pariteitscorrecties. Onder de research-invalidatieregel
> van de pijplijn vervallen alle rankings die onder een materiële pariteitsfout tot stand
> kwamen — en dat gold voor die conclusie. Zie `docs/DECISIONS.md`.

Merknaam = vaste strategie-persoonlijkheid. Titel codeert MARKT + CON/AGG/PROD/HF + EOD/INTRA.
Shorttitle ≤ 10 tekens. **EL TORO is voorbehouden aan evaluatie-accounts.**

| Merk | Markt | Profiel | Shorttitle |
|---|---|---|---|
| EL TESORO | MGC | Conservative EOD | `TES-MGC-C` |
| EL PATRON | MGC | Aggressive EOD | `PAT-MGC-A` |
| EL REY | MNQ | Production EOD / Intraday | `REY-MNQ-P` / `REY-NQ-PI` |
| EL MATADOR | MES | Production CVD6 EOD | `MAT-MES-P` |
| EL LEON | MYM | Production / recovery | `LEO-MYM-P` / `LEO-YM-CI` / `LEO-YM-CE` |
| EL BANDIDO | MYM | HF / Harvest EOD | `BAN-MYM-H` — **Pine-pariteit open, niet live** |
| EL PRINCIPE | MNQ | Balanced | research, niet live |
| EL MINERO | — | gereserveerd | toekomstige HF/commodity |

- ⛔ **Er is op dit moment GEEN geldige rangorde.** De oude volgorde (REY › MATADOR ›
  TESORO › LEON › PATRON › BANDIDO › PRINCIPE) is **ingetrokken** — die viel al onder de
  research-invalidatieregel. De vloot-sweep van 25-08 (trap 0→9) leverde een verse meting,
  maar die is maar voor één engine bruikbaar:

  | Engine | Gemeten payout-$/account-dag (1 contract) | Status |
  |---|---|---|
  | MATADOR (MES) | $30,59 — P1 na 85 dagen | ✅ bruikbaar, pariteitspoort dicht (`data_parity`) |
  | LEON (MYM) | $17,48 — P1 na 118 dagen | ⛔ **ongeldig**, harde poort open |
  | REY (MNQ) | $13,21 — P1 na 161 dagen | ⛔ **ongeldig**, harde poort open |
  | PATRON · TESORO · BANDIDO | funderen niet op 1 contract | ⚠️ voorlopig — zie MGC-voorbehoud |

  "Ongeldig" is niet mijn woord maar dat van de pijplijn zelf: `state.py` noemt onvervulde
  harde poorten de poorten die downstream-cijfers *"invalid rather than merely early"*
  maken. Behandel LEON en REY dus niet als "indicatief maar ongeveer goed" — als de poort
  dichtgaat kan het cijfer een andere kant op bewegen. **Rangorde ≠ accounttoewijzing.**
- ⚠️ **MGC-voorbehoud:** beide MGC-engines zijn gemeten op de **GC-twin** omdat echte
  MGC-data ontbreekt. Elk MGC-oordeel — ook een afwijzing — staat daarmee onder voorbehoud.
- 🔴 **De bevroren volle contractgrootte is niet fresh-account-funderbaar** (sweep 25-08,
  mechanisme-niveau vastgesteld en onafhankelijk van de rangorde). Op volle grootte breken
  alle engines op trap 7/8; op 1 contract fundeert elke engine wél. Twee bindende muren:
  de **$2.000 trailing drawdown** van een vers account (een verliesreeks van ~$2.700 breekt
  hem voordat de buffer de floor vergrendelt) en de **$1.000 DLL** (MATADOR met 6 MES-
  contracten à $150 stop gaat er met één slechte dag overheen). De `.pine`-bron schaalt
  contracten in via `derisk`/`deriskPA`; **de bevroren config doet dat niet.** Dat gat is
  een openstaande ontwerpkeuze, geen bug — zie D-53.
- **Doel is niet PF maar gebankte payout-$ per bezette account-dag.** Account-mechanica kan
  de rangorde van twee identieke engines omdraaien.
- **Correlatie:** MGC is de enige niet-aandelenbucket; MNQ/MES/MYM zijn alle drie
  index-exposure. Claim geen decorrelatie vóór 20–30 actieve dagen gemeten P&L-correlatie.
- 🔴 **OOS is forward, niet historisch** (besluit Ferry 25-08, D-18). De drie jaar 2023–2026
  heten **validatie**. Echte out-of-sample loopt **vooruit vanaf het bevriezen van een config**.
  De `v1_0_0`-vloot was bevroren op 23-08-2026, **maar vijf scripts zijn op 25-08 gedragsmatig
  gewijzigd**: `skipMonEarly` is eruit in PATRON, TESORO en de vier EL TORO's, dus maandag
  00:00–02:00 ET handelt daar nu mee (besluit Ferry). **Hun OOS-klok begint dus op 25-08-2026,
  niet op 23-08.** Voor de overige acht staat de klok op 23-08. Hoe dan ook: dagen, geen jaren.
  **Claim nergens dat deze vloot out-of-sample bewezen is** — niet op de site, niet in een
  rapport, niet tegenover een prop firm. Ook de sweep-cijfers van 25-08 vallen volledig
  binnen het validatievenster.
- Fine-grained day×hour cherry-picking blijft OOS-ruis (weerlegd). Regimes mogen alleen
  economisch vooraf gedefinieerd.
- Bevroren parameters per engine: `.claude/skills/strategy-validation-pipeline/references/frozen-engines.md`.
  **Die zijn bevroren** — wijzigen is een nieuwe onderzoeksronde vanaf trap 1, geen tweak.

## Middleware = control plane (NOT a copy-trader)
One alert per strategy → middleware maps strategy→accounts and fans out. Per account YOU set
firm/asset/volume/channel; not identical mirroring. Channels:
- **Execution**: PMT→Tradovate (Apex/MFFU), PineConnector→MT5 (FTMO). PMT is the execution
  bridge, not the fan-out; could later be replaced by direct Tradovate order API.
- **Notify**: Discord live per trade. **Journal**: internal sqlite + LifeOS Trade Journal.
- **Tracking**: Tradovate P&L poller → LifeOS Fleet Performance.
- **Reconciliation (Phase 6)**: intended (TradingView) vs actual fills (Tradovate + MT5 via
  MetaAPI) → slippage/latency/qty per venue → LifeOS Reconciliation. P&L-deviation staged.
- Safety: DRY_RUN default, kill-switch, idempotency, retries, per-account risk gate.
- Deploy: Render blueprint (easiest) or VPS one-command (`middleware/deploy/setup.sh`).

## LifeOS (Notion) dashboards
- Fleet Performance `ae5105393828447e84a1a87d31562d7d`
- Trade Journal `c3e9d05525404849ad484b648c82fd59`
- Reconciliation `2e674ed0a07f4b2cb77822b9b456f350`
- Content Hub data source `6cfcd7fa-1e15-439e-b7ab-274a907788f3`
- ⚠️ Deze id's zijn deels dood: *MEX Reconciliation* heeft 0 rijen (geverifieerd 19-08) —
  de laag is gebouwd maar heeft nooit geschreven. Fleet Performance en Trade Journal nog
  ongecontroleerd. Zie `docs/SPRINT.md` D-20.
### Rolstructuur — CLO, SM, en de ChatGPT CoS (25-08)

Sinds 25-08 zit er boven de MEX Scrum Master een overkoepelende Claude-rol:
de **Chief LifeOS Officer (CLO)** — zie `.claude/skills/chief-lifeos-officer/SKILL.md`.
Opstelling:

- **CLO** (Claude, overkoepelend) doet strategisch overzicht + cross-domain
  coördinatie + rol-governance. Raakt geen operationele items op het MEX-bord
  en geen code — signaleert, delegeert. Wordt opgeroepen bij grote beslissingen
  en voor de wekelijkse briefing. Zit **boven** de SM op strategie, **naast**
  de ChatGPT CoS op peer-niveau.
- **Scrum Master** (Claude, MEX) blijft eigenaar van SPRINT.md, DECISIONS.md,
  D-nummer-uitgifte, en cross-chat coördinatie voor de dev-rollen. Operationeel.
- **LifeOS Chief of Staff** (ChatGPT, hieronder) blijft eigenaar van de
  non-MEX LifeOS. Peer met CLO; coördineren via Approval Queue en de gedeelde
  `briefing`-skill.

Bij twijfel welke rol: strategisch/cross-domain/rol-vraag → CLO; MEX-item
of dev-coördinatie → SM; niet-MEX LifeOS-item → CoS.

### ⚠️ Er is een tweede agent in deze workspace

**LifeOS Chief of Staff** (Operating Spec v1.4, 21-08) beheert de **non-MEX** LifeOS:
familie, gezondheid, persoonlijke financiën, huis/verbouwing, administratie, ontwikkeling,
lifestyle en LifeOS-governance. De grens is wederzijds vastgelegd:

- **Van ons:** trading-executie, strategie, backtesting, MEX-development, middleware,
  fleet-operations en de MEX technical backlog. *"These remain owned by the Claude Scrum
  Master / El Presidente."* De CoS mag MEX-state **lezen** voor tijd-, agenda- en
  cross-domain-afwegingen — **visibility does not imply authority**; hij herprioriteert
  onze backlog niet en overschrijft ons niet.
- **Van hen:** niet overnemen. Geen parallel taken-, backlog- of kennissysteem bouwen, en
  geen non-MEX LifeOS-governance wijzigen zonder afstemming.
- **Tasks heeft een nieuwe property `Route`** (Zelf/Aannemer/Elektricien/…). Die is voor
  non-MEX uitvoerder-routing; **laat hem leeg op `🛠️ MEX Dev ·`-taken**.
- **Approval Queue — ook voor MEX** (besluit Ferry 24-08). Beslissingen die op Ferry
  wachten gaan in de 📥 Inbox-database (`collection://d0c8311b-b464-4132-b156-836250502aab`)
  met `Type = Approval`, `Status = Inbox` en titel `🛠️ MEX D-xx — <beslissing>`.
  De `Notitie` draagt vast: **CONTEXT · AANBEVELING · (ALTERNATIEF) · IMPACT · NA AKKOORD**.
  Eén wachtrij voor beide agenten. Na verwerking `Status = Verwerkt`.
  `docs/inbox.md` blijft het kanaal *tussen chats onderling*; de Approval Queue is het
  kanaal *naar Ferry*. Dump er geen backlog in — alleen wat echt op hem wacht.
- **Visuele standaard:** navy/sand/gold/azure/rose komt uit de goedgekeurde MEX
  Traders-mockup en is nu LifeOS-breed. Relevant voor `web/**` (D-17, D-34).
- Hun hub: *🎩 El Presidente — management & oversight* is de MEX-autoriteitspagina.

- MEX Dev loopt via de bestaande LifeOS-databases — geen aparte structuur:
  **Tasks** met voorvoegsel `🛠️ MEX Dev ·`, en **Notes** `🛠️ MEX Dev — Architectuur /
  Besluitregister / Documentatieregister`. Beide gekoppeld aan Area *MEX Traders* en
  project *MEX PROP TRADER*. Werkwijze in `docs/CHAT_INSTRUCTIE.md`.

## Dev conventions
- **Eén branch: `claude/middleware-setup-guide-afhvtk`.** Develop/commit/push daar en nergens
  anders zonder toestemming. **Begin elke sessie met `git pull origin claude/middleware-setup-guide-afhvtk`** —
  het bord, de inbox en dit bestand staan daar en lopen anders achter. De chat-branches zijn
  **bevroren**: `pine-dev` en `legacy` zijn opgenomen (24-08), `analyses` botst nog (D-43) en
  `discord-notify` is dood materiaal sinds D-04. Push er niets nieuws heen — werk dat op een
  eigen branch blijft staan bereikt niemand, en dat is precies hoe de analyses-chat dagen op een
  ingetrokken aanname doorwerkte. Do not create PRs unless asked. (`claude/mcp-trader-dev-sse-ibl64y`
  is dood — volledig opgenomen in de werkbranch, liep 186 commits achter.)
- **Eigenaarstabel** (compleet sinds D-19/D-29, besluit Ferry 25-08):
  `backtest/**` Backtest Setup · `pine/**` Pine Dev · `middleware/**` Middleware App ·
  `web/**` Web · **`docs/**` Scrum Master** · **`tools/**` Backtest Setup** ·
  **`validation/**` Backtest Setup** · `data/propfirms.json` gedeeld.
  Uitzondering: `tools/gen_pine_firms.py` blijft bij **Pine Dev** — dat bestand genereert Pine.
  **`validation/` is append-only:** bewijs wordt nooit herschreven als een conclusie vervalt,
  het krijgt een notitie dat het ingetrokken is. Zo bleef het GC+ES-bewijs bruikbaar als
  historie toen de conclusie eronder wegviel (23-08).
  Buiten je eigen map: niet muteren, maar melden in `docs/inbox.md`.
- **`middleware/app/main.py`, `router.py` en `brokers/` draaien NIET live.** Het live
  executiepad is `mex-receiver` (.NET). Verifieer met `systemctl cat` vóór je aanneemt
  dat een wijziging de executie raakt.
- **Lees `docs/SPRINT.md` vóór je begint** en claim één item (status `wip` + owner +
  losse commit) — dat is het slot dat dubbel werk voorkomt. Beslissing die een ander
  raakt? Eén regel in `docs/DECISIONS.md`.
- Alle vastlegging in Notion loopt via de Scrum Master — chats schrijven daar niet zelf.
- **Wat er live draait staat in `docs/runtime-snapshot.md`** — checksum en regelaantal van
  `Program.cs`, de mtime van de binary, wanneer de service startte, en welke env-namen gezet
  zijn (namen, nooit waarden). Ververst elk uur door `mex-runtime-snapshot.timer`. **Kijk daar
  eerst** voor je iemand vraagt iets op de VPS na te kijken. Is de tabel oud, dan draait de
  timer niet — en dat is zelf ook informatie.
- Never commit secrets: middleware `.env`, `accounts.yaml`, `*.db` are git-ignored.
- Pine is indentation-sensitive: 4-space indent, **no tabs**.
