# Fleet-platform — architectuur & routekaart

Beslisdocument voor het uitbouwen van de middleware naar een volledig
fleet-platform: eigen login, live monitoring, controle (incl. posities sluiten),
consistency/payout per account, publieke zichtbaarheid per account, en later een
"meekijk"-portal voor websitebezoekers met recaps.

> Dit legt de **gekozen richting** vast zodat we gefaseerd bouwen zonder later te
> hoeven ombouwen. Zie `SETUP.md` voor het draaiend krijgen van de huidige middleware.

---

## De genomen beslissing (locked)

| Vork | Keuze | Waarom |
|---|---|---|
| Opzet | **Split — "brain" (privé control-plane) + "faces" (publieke web-app)** | Publiek verkeer + follower-logins raken nooit de box die je funded accounts bestuurt |
| Web-controle | **Volledige controle incl. positie sluiten/flatten** | Vanaf de owner-console alles kunnen; vereist harde beveiliging (zie onder) |
| Database | **Postgres vanaf nu** | Eén gedeelde store voor control-plane + viewers/followers; geen latere migratie |
| Frontend | **Next.js / React** | Volwaardige merk-site + follower-portal + owner-console; beste publieke UX |

**Directe consequentie van "volledige controle":** elke muterende actie (sluiten,
flatten, halt, zichtbaarheid) staat achter **verplichte 2FA + een append-only
audit-log**. Een gekaapte login mag nooit ongemerkt een funded positie kunnen sluiten.

---

## Herziene richting (v2 — bevestigd)

Op basis van de nadere eisen ("alles zelf, directe API's, live feeds, geen black-box,
volledige web-controle"):

- **Hosting: eigen VPS — bevestigd.** Managed PaaS (Render) afgewezen: te veel
  abstractie voor de gewenste volledige controle, permanente live-feeds (websockets)
  en transparantie. De VPS is geen tussenpartij — jouw code praat direct met de
  API-providers, en niets anders.
- **Execution: directe Tradovate order-API vanaf dag 1 — PMT eruit.** De middleware
  plaatst orders zelf en leest echte fills via de Tradovate-websocket. PickMyTrade
  vervalt als brug (uitfaseren zodra Tradovate-direct bewezen is). Behouden:
  **PineConnector** (MT5/FTMO), **Discord** (notify), **MetaAPI** (MT5-fills/recon).
- **Live feeds — realtime.** Permanente websocket-verbindingen (Tradovate + MetaAPI)
  leveren fills/PnL live i.p.v. polling. Vraagt altijd-aan workers → onderstreept de VPS.
- **Geen "ik wist het niet".** Ontwerpprincipe: elke dispatch naar elk kanaal logt zijn
  échte uitkomst (verstuurd / bevestigd / gefaald / gevulde prijs); reconciliatie
  vergelijkt bedoeld vs werkelijk. Geen stille mislukkingen.
- **Volledige HTTPS-controle over accounts, fleet én trades.** Vanuit de owner-console:
  posities sluiten/flatten, accounts halt/resume, zichtbaarheid togglen, per-account
  instellen — alles achter 2FA + audit.
- **Ontwerpprincipe: krachtige backend, simpele knoppen.** Géén capaciteitslimieten in
  de control-plane; wél eenvoudige, duidelijke opties in de console.

**Gevolg voor de routekaart:** het directe-Tradovate-stuk + de live fill-feeds schuiven
naar voren (van Fase B naar de kern van Fase A) — ze zijn nu het executie-fundament
i.p.v. de PMT-brug.

---

## Kernprincipe: "Brain" gescheiden van "Faces"

```
              ┌──────────────────── BRAIN (privé control-plane, op de VPS) ────────────────────┐
 TradingView ─▶ middleware ─▶ [ State Engine: live fills+PnL  ×  firms.py-regels ]              │
              │               │                                                                 │
              │               ├─ Control API  (owner-only · muteert · 2FA · audit-log)          │
              │               │     halt/resume · CLOSE/FLATTEN · kill-switch · zichtbaarheid    │
              │               └─ Viewer API   (alleen-lezen · gefilterd op rol + zichtbaarheid)  │
              └───────────────────────────────┬─────────────────────────────────────────────────┘
                                              │  (alleen de Viewer API is publiek bereikbaar)
   FACES (Next.js, op Vercel)                 │
     ├─ Owner-console (privé)  ────────────────┤ praat óók met Control API (na 2FA)
     ├─ Follower-portal (meekijk + recap) ─────┤ praat alleen met Viewer API
     └─ Marketing-site (pipsandpalmtrees.com) ─┘
                                   LifeOS/Notion = analytische spiegel (blijft, read-model)
```

**De naad is de Viewer API.** Followers en de website lezen uitsluitend die
alleen-lezen, op zichtbaarheid gefilterde API. De owner-console is de enige die ook
de muterende Control API mag aanroepen — en pas na 2FA. Zo bouwen we de
follower-functie en de recap er later bovenop zonder iets te slopen.

---

## Componenten

### 1. Control plane ("Brain") — uitbouw van de huidige FastAPI-middleware
Blijft op de VPS (`middleware.pipsandpalmtrees.com`). Krijgt erbij:

- **State Engine** (nieuw, het hart) — combineert live fills/PnL (Tradovate +
  MetaAPI/MT5) met de regels uit `backtest/firms.py` en levert **per account**:
  balans, trailing/static DD-ruimte, DLL gebruikt, **consistency %**, voortgang naar
  target, **beschikbaar voor opname**, en een **status** (`Active` / `Risk-Off` /
  `Halted` / `Breached`). Dit voedt owner-console, follower-portal én LifeOS.
  → Activeert tegelijk de nu *dormante* DLL/consistency-checks: we wire de fill-feed
  aan `RiskState.record_fill` (het Phase 5b-haakje dat al in `app/risk.py` klaarstaat).
- **Close/flatten-capability** (nieuw) — bestaat nog niet; de middleware opent nu
  alleen orders. Bouwen via de **Tradovate order-API** (futures) en de **MetaAPI
  trade-API** (MT5/FTMO — MetaAPI zit al in de stack voor reconciliation, kan ook
  sluiten). CLAUDE.md voorziet dit al ("could later be replaced by direct Tradovate
  order API").
- **Auth + rollen** — `owner` (volledige controle) en `follower` (alleen-lezen).
  Owner-acties vereisen 2FA (TOTP). Sessies + wachtwoord-hashing.
- **Twee API-oppervlakken** — Control API (owner-only, muteert) en Viewer API
  (alleen-lezen, gescoped op rol + zichtbaarheidsvlaggen). Alleen de Viewer API is
  publiek bereikbaar; de Control API is owner-only (2FA, en optioneel IP-allowlist).
- **Audit-log** — append-only tabel: wie, wat, wanneer, op welk account, met welk
  resultaat. Elke muterende actie schrijft hierheen.

### 2. Data ("Postgres vanaf nu")
Migratie van de huidige sqlite-tabellen (`events`, `perf`) naar Postgres, plus het
nieuwe multi-account/multi-rol-model. Schets:

| Tabel | Doel |
|---|---|
| `users` | login, rol (owner/follower), wachtwoord-hash, 2FA-secret |
| `accounts` | firm, programma (`firms.py`-key), asset, contract, kanaal, **`is_public`-vlag** |
| `fills` | echte fills per venue (Tradovate + MT5) — bron voor P&L en slippage |
| `trades` | afgeleide open/closed posities per account (voor de journals/portals) |
| `account_state` | laatste snapshot uit de State Engine (balans, DD, consistency, payout, status) |
| `events` | het bestaande journal (signaal · dispatch · error) |
| `recaps` | recap-content (Outlook), gekoppeld aan zichtbaarheid, voor follower-login |
| `audit_log` | elke muterende owner-actie |

> Aanrader voor de DB-laag: **Supabase** of **Neon** (managed Postgres). Supabase geeft
> bovendien kant-en-klare auth + row-level security + realtime — dat mapt mooi op
> "followers zien alleen gefilterde data" en "live updates". Definitieve sub-keuze
> maken we bij de start van Fase A.

### 3. "Faces" — Next.js op Vercel
Eén Next.js-project, meerdere oppervlakken:
- **Marketing-site** → `pipsandpalmtrees.com` / `www`
- **Owner-console** (privé, achter login + 2FA) → praat met Control + Viewer API
- **Follower-portal** (meekijk) → praat alleen met Viewer API

### 4. LifeOS / Notion
Blijft de **analytische spiegel** (Fleet Performance, Trade Journal, Reconciliation).
De State Engine pusht ernaartoe (Notion-sync bestaat al). Notion is bewust *niet* de
live-actie-laag — dat is de control-plane.

---

## Deploy-topologie & subdomeinen (GoDaddy)

| Onderdeel | Waar draait het | Subdomein |
|---|---|---|
| Marketing-site | Vercel | `pipsandpalmtrees.com`, `www` |
| Owner-console + follower-portal | Vercel | `app.pipsandpalmtrees.com` |
| Viewer API (publiek, alleen-lezen) | VPS | `api.pipsandpalmtrees.com` |
| Control-plane / webhook (privé) | VPS | `middleware.pipsandpalmtrees.com` |

Elk subdomein = één DNS-record (A-record naar de VPS voor de API's; CNAME naar Vercel
voor de site/app). De middleware-webhook uit `SETUP.md` blijft ongewijzigd bestaan.

---

## Beveiliging (verplicht bij "volledige controle incl. sluiten")

- **2FA (TOTP)** op de owner-login — niet optioneel.
- **Audit-log** op elke muterende actie (sluiten, flatten, halt, zichtbaarheid, kill).
- **Rol-scheiding op API-niveau** — de Viewer API kan fysiek geen muterende actie
  aanroepen; followers hebben nooit een pad naar broker-acties.
- **Kill-switch blijft** — halt-alles onafhankelijk van de UI.
- **Bevestiging per gevoelige actie** (sluiten/flatten vraagt een expliciete confirm).
- Optioneel: **IP-allowlist** op de Control API, en losse read-only broker-credentials
  voor de State Engine gescheiden van de order-credentials.

---

## Gefaseerde routekaart

Elke fase is los bruikbaar; we bouwen op het bestaande fundament (niets weggooien).

### Fase A — Backbone (Brain)
- [ ] sqlite → **Postgres** (nieuw multi-account/rol-schema).
- [ ] Fill-feed aan `RiskState.record_fill` → DLL + consistency live.
- [ ] **State Engine**: per-account status (balans · DD · consistency · payout · status).
- [ ] Auth + rollen (owner/follower) + **2FA** + audit-log.
*Levert: de datalaag en de "waarheid" per account waar alles op leunt.*

### Fase B — Owner-console (privé Face)
- [ ] Next.js owner-console: fleet-overzicht + per-account cards + open/closed trades.
- [ ] Control-acties: halt/resume · **close/flatten** (Tradovate + MetaAPI) · kill-switch.
- [ ] **Zichtbaarheid togglen** per account (`is_public`-vlag).
*Levert: jouw dagelijkse cockpit met volledige controle.*

### Fase C — Publieke site + follower-portal (publieke Faces)
- [ ] Marketing-site `pipsandpalmtrees.com`.
- [ ] Follower-signup/login → Viewer API gescoped op publieke accounts.
- [ ] Meekijk-view: overall viewer **+** trades (open & closed) **+** status (bv. Risk-Off).
*Levert: bezoekers kunnen (alleen-lezen) meekijken met wat jij vrijgeeft.*

### Fase D — Recaps onder follower-login
- [ ] Outlook/recap-content via de Viewer API aan ingelogde followers.
*Levert: je recaps als afgeschermde content voor je meekijkers.*

---

## Waar jouw wensen landen

| Jouw wens | Component | Fase |
|---|---|---|
| Eigen login, live volgen (trades, balans) | Auth + Owner-console + State Engine | A→B |
| Positie sluiten vanaf web | Control API + close/flatten (Tradovate/MetaAPI) | B |
| Account-stop | Control API (halt bestaat al) | B |
| Accountstatus + consistency + payout-beschikbaar | State Engine (`firms.py`-regels) | A |
| Samenvallen in fleet-beheer (+ LifeOS) | State Engine → console + Notion-spiegel | A→B |
| Aan/uit welke accounts publiek zichtbaar zijn | `is_public`-vlag + Viewer-API-filter | B |
| Meekijk-account (viewer + trades + status) | Follower-portal + Viewer API | C |
| Outlook/recap onder meekijk-login | `recaps` + Viewer API | D |
