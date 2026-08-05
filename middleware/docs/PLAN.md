# Fleet-platform — bouwplan & voortgang

Het uitvoeringsplan voor het platform dat in `ARCHITECTURE.md` is ontworpen. Dit is de
actielijst (taken · volgorde · status); `ARCHITECTURE.md` is het ontwerp en de
beslissing, `SETUP.md` is de VPS-basis.

> **Bedoeld voor LifeOS.** Plak dit als project in LifeOS (Notion). De taaltabel per
> fase is gemaakt om als Notion-database over te nemen (kolommen = properties).

---

## Doel

Van de huidige middleware (control plane) naar een compleet fleet-platform met:
eigen login, live monitoring, volledige controle (incl. posities sluiten), consistency/
payout per account, publieke zichtbaarheid per account, en een meekijk-portal met recaps.

## Vastgelegde beslissingen (zie ARCHITECTURE.md)

- **Split**: privé control-plane ("brain") + publieke web-app ("faces").
- **Volledige web-controle** incl. close/flatten → **2FA + audit-log verplicht**.
- **Postgres** vanaf nu (aanrader provider: **Supabase** — Postgres + auth + RLS + realtime).
- **Next.js/React** voor de faces (Vercel).
- **Secrets**: alleen referenties in LifeOS; echte waarden in een kluis (zie `SECRETS-REGISTER.md`).

**Herziene richting (v2 — bevestigd):**
- **Hosting: eigen VPS bevestigd** (Render/PaaS afgewezen — te veel abstractie voor volledige controle + live feeds).
- **Directe Tradovate order-API vanaf dag 1; PMT eruit.** Behouden: PineConnector (MT5), Discord, MetaAPI.
- **Live websocket-feeds** (Tradovate + MetaAPI) i.p.v. polling → realtime fills/PnL.
- **Geen "ik wist het niet"**: elke dispatch logt zijn échte uitkomst; reconciliatie bedoeld vs werkelijk.
- **Volledige web-controle over accounts, fleet én trades** vanuit de owner-console (2FA + audit).
- **Krachtige backend, simpele knoppen** — geen capaciteitslimieten, wel eenvoudige opties.
- **Owner beheert ook de view-only accounts** — aanmaken/intrekken/scopen; één console voor fleet én toegang.

## Al aanwezig (herbruikbaar, niet opnieuw bouwen)

`/performance` + Tradovate-poller · reconciliation-engine (`reconciler.py`,`metaapi.py`) ·
`/halt` + kill-switch · journal (`journal.py`) · Notion-sync · **`backtest/firms.py`**
(prop-firm regels: target, DD, consistency, payout) · `RiskState.record_fill`-haakje.

---

## Fasen

Ruwe effort is indicatief (afhankelijk van hoeveel we samen live testen). S = klein,
M = middel, L = groot.

### Fase 0 — Basis live (voorwaarde)
De middleware draaiend op de VPS volgens `SETUP.md`, in `DRY_RUN`, webhook getest.
*Zonder dit fundament heeft de rest geen live data.*

### Fase A — Backbone (Brain) · ~L
De datalaag en de "waarheid" per account waar alles op leunt.
- Postgres opzetten (Supabase) + schema (zie ARCHITECTURE.md datamodel).
- sqlite → Postgres migreren (`events`, `perf` → nieuw schema).
- Fill-feed aan `RiskState.record_fill` → DLL + consistency live (nu dormant).
- **Directe Tradovate order-API** (execution vanaf dag 1; PMT eruit) + **live fill-feed via websocket** (Tradovate + MetaAPI) — realtime, geen polling.
- **Per-kanaal statusfeedback**: elke dispatch (Tradovate / PineConnector / Discord) logt zijn échte uitkomst — geen stille fouten.
- **State Engine**: per account → balans · DD-ruimte · DLL · consistency % · payout-beschikbaar · status.
- Auth + rollen (owner/follower) + **2FA (TOTP)** + audit-log.
- Viewer API (alleen-lezen, gefilterd) + Control API (owner-only) als aparte oppervlakken.

### Fase B — Owner-console (privé Face) · ~L
Jouw dagelijkse cockpit met volledige controle.
- Next.js console: fleet-overzicht + per-account cards + open/closed trades.
- Control-acties: halt/resume · **close/flatten** (Tradovate order-API + MetaAPI trade-API) · kill-switch.
- Zichtbaarheid togglen per account (`is_public`).
- Elke muterende actie: 2FA-bevestiging + audit-log-regel.

### Fase C — Publieke site + follower-portal (publieke Faces) · ~M
Bezoekers kunnen (alleen-lezen) meekijken met wat jij vrijgeeft.
- Marketing-site `pipsandpalmtrees.com`.
- Follower-signup/login → Viewer API gescoped op publieke accounts.
- Meekijk-view: overall viewer + trades (open & closed) + status (bv. Risk-Off).

### Fase D — Recaps onder follower-login · ~S/M
- Outlook/recap-content via de Viewer API aan ingelogde followers.

---

## Taaklijst (Notion-database-ready)

Kolommen → Notion-properties: **Fase · Taak · Status · Afhankelijk van · Effort · Notitie**

| Fase | Taak | Status | Afhankelijk van | Effort | Notitie |
|---|---|---|---|---|---|
| 0 | Middleware live op VPS (DRY_RUN, webhook getest) | Todo | — | M | volgens SETUP.md |
| A | Directe Tradovate order-API (execution; PMT eruit) | Todo | 0 | L | middleware plaatst orders zelf |
| A | Live fill-feed via websocket (Tradovate + MetaAPI) | Todo | Tradovate-API | L | realtime fills, geen polling |
| A | Per-kanaal statusfeedback (geen stille fouten) | Todo | fill-feed | M | elke dispatch logt echte uitkomst |
| A | Supabase-project + Postgres opzetten | Todo | 0 | S | provider-keuze bevestigen |
| A | DB-schema aanleggen (users/accounts/fills/trades/account_state/events/recaps/audit_log) | Todo | Supabase | M | zie ARCHITECTURE.md |
| A | sqlite → Postgres migratie | Todo | schema | M | events + perf overzetten |
| A | Fill-feed → `RiskState.record_fill` (DLL/consistency live) | Todo | schema | M | activeert dormant checks |
| A | State Engine (per-account status-berekening) | Todo | fill-feed, firms.py | L | het hart |
| A | Auth + rollen + 2FA + audit-log | Todo | schema | L | 2FA verplicht |
| A | Viewer API + Control API scheiden | Todo | auth | M | naad publiek/privé |
| B | Next.js owner-console (overzicht + cards + trades) | Todo | Viewer API | L | privé, achter 2FA |
| B | Close/flatten-capability (Tradovate order-API + MetaAPI) | Todo | Control API | L | nieuw; funded-gevoelig |
| B | Control-acties in console (halt/close/kill/zichtbaarheid) | Todo | close-capability | M | audit + confirm |
| B | Zichtbaarheid-toggle per account (`is_public`) | Todo | Control API | S | stuurt follower-view |
| B | Toegang/viewer-beheer (view-only accts aanmaken/intrekken/scopen) | Todo | auth | M | owner beheert wie wat ziet; per-viewer scope |
| C | Marketing-site pipsandpalmtrees.com | Todo | Next.js-basis | M | Vercel |
| C | Follower-signup/login | Todo | auth (follower-rol) | M | Supabase-auth |
| C | Meekijk-view (viewer + trades + status) | Todo | Viewer API, `is_public` | M | alleen-lezen |
| D | Recaps onder follower-login | Todo | follower-portal | S/M | Outlook-content |

Status-opties voor Notion: `Todo` · `In progress` · `Blocked` · `Done`.

---

## Volgorde & mijlpalen

1. **M1 — Live basis** (Fase 0): webhook ontvangt en journalt echt.
2. **M2 — Waarheid per account** (Fase A af): State Engine levert per account status,
   consistency en payout-beschikbaar; auth + audit staan.
3. **M3 — Cockpit** (Fase B af): jij bestuurt de hele fleet vanaf de owner-console.
4. **M4 — Publiek meekijken** (Fase C af): bezoekers zien wat jij vrijgeeft.
5. **M5 — Recaps** (Fase D af): recaps achter meekijk-login.

## Openstaande sub-beslissingen

- **Postgres-provider**: aanrader **Supabase** (auth + RLS + realtime meegeleverd).
  Alternatief: Neon (kaler) of Postgres op de VPS. → bevestigen bij start Fase A.
- **Hosting faces**: Vercel (aanrader bij Next.js). → bevestigen bij start Fase B/C.
- **2FA-methode**: TOTP (Authenticator-app) als standaard. → bevestigen bij auth-taak.

## Risico's & mitigaties

| Risico | Mitigatie |
|---|---|
| Gekaapte owner-login sluit funded posities | 2FA verplicht · audit-log · confirm per actie · kill-switch |
| Prop-firm regels veranderen (consistency/payout) | `firms.py` is data met `source`/`as_of`; per firm verifiëren |
| Publiek verkeer raakt trading-box | Split: alleen Viewer API publiek; Control API owner-only |
| Secrets lekken via LifeOS | Alleen referenties in LifeOS; waarden in kluis (SECRETS-REGISTER.md) |
| Close-capability plaatst verkeerde order | Eerst uitgebreid in DRY_RUN/demo; bevestiging + audit |

## Definition of done (per fase)

- **A**: één demo-account toont in de DB een correcte live status (balans/DD/consistency/
  payout) die klopt met de broker; owner kan inloggen met 2FA; elke actie logt.
- **B**: owner sluit een positie op een demo-account vanaf de console; actie staat in de audit-log.
- **C**: een testbezoeker maakt een follower-account en ziet exact de accounts die op `is_public` staan — niets meer.
- **D**: een ingelogde follower ziet de recap; een niet-ingelogde bezoeker niet.
