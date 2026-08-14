# Trade Journal-pipeline — near-real-time voorstel

Doel: **trades verschijnen automatisch in het Notion Trade Journal zodra ze er zijn**
(near-real-time, elke paar minuten), zonder handwerk. Dit legt de huidige stand vast,
het einddoel, de te bouwen stukken en de openstaande keuzes.

---

## Huidige stand (geverifieerd op `mex-mw-01`)

| Stuk | Status | Waar |
|---|---|---|
| Signalen ontvangen → intent-store | ✅ live | `mex-receiver.service` → `/root/intent-store/intents_*.jsonl` + `routed_*.jsonl` |
| Fills (Tradovate) → CSV | ⚠️ **handmatig** | `/root/exports/YYYYMMDD_<acct>_Fills.csv` |
| Fills → completed trades (pairing) | ✅ **gebouwd + gevalideerd** | `app/fills_pairing.py` |
| Completed trade → Notion-rij (mapping) | ✅ **gebouwd + 956/956 gevalideerd** | `app/notion_journal.py` |
| Verwerking koppelen + plannen | ❌ te bouwen | (deze pipeline) |
| Download automatiseren | ❌ te bouwen | (de echte real-time-knop) |

De oude .NET-verwerker (`MEX_Middleware_FaseA/B`) op de server = verouderd, vervangen we.

---

## Doel-pipeline (automatisch, near-real-time)

```
TradingView-alerts ─▶ mex-receiver ─▶ intent-store (signaalprijs, strategie)   [LIVE]
                                            │  (join op account+symbool+tijd)
Tradovate ─▶ [AUTO fills ophalen, elke N min] ─▶ fills
                                            ▼
                          [fills_pairing]  fills → completed trades
                                            ▼
                    join intent  → Signal Price (slippage) + Framework
                                            ▼
                     [notion_journal]  → Trade Journal upsert (Webhook ID)
              alles elke ~5-10 min via systemd-timer op mex-mw-01
```

---

## De download automatiseren — twee wegen (voorkeur = API)

**Weg A — Tradovate-API fills pollen (aanrader, schoonst).**
De middleware authenticeert al bij de Tradovate-API voor P&L (`app/tradovate.py`). "Directe
API" was onmogelijk voor *order-plaatsing* — maar **lezen** werkt aantoonbaar (P&L komt
binnen). Fills lezen is één endpoint erbij (`/fill/list` of `/execution/list`). Als dat met
je bestaande creds werkt: **geen CSV-download en geen browser-automation meer nodig** — de
runner pollt fills direct → pairt → journal. Te testen op de server met de huidige creds.

**Weg B — browser-automation (fallback).**
Werkt de API-read niet voor fills, dan automatiseren we de rapport-export zoals je
charts-crawler al doet (Playwright → inloggen → Fills-report per account exporteren →
`/root/exports/`). Meer werk (login/sessie/auth-verloop), maar bewezen aanpak in jouw stack.

→ **Eerst Weg A testen** (kost weinig, kan alles vereenvoudigen); anders Weg B.

---

## Wat er nog gebouwd moet worden (de backlog)

1. **Fills-bron** — Weg A (API-fills-poll in `tradovate.py`) of Weg B (browser-export). *[keuze na test]*
2. **Runner** `app/journal_sync.py` — scant fills-bron → `pair_fills` → completed trades. *[bouwen]*
3. **Intent-join** — match trade ↔ signaal (account + symbool + entry-tijd) → `Signal Price`
   (slippage) + `Framework`/strategie. *[bouwen]*
4. **Framework-resolutie** — uit `routed_*.jsonl` als de strategie daar staat, anders afleiden
   (instrument + account-fase: GC/MGC·funded→El Tesoro, ES·eval→El Leon, …; NQ = 4 varianten,
   vereist de intent). *[1 check: staat strategie in routed_?]*
5. **Idempotentie/state** — incrementeel verwerken (bijhouden welke fills al gedaan zijn);
   Notion-upsert op `Webhook ID` vangt dubbels sowieso af. *[bouwen]*
6. **Scheduling** — systemd-timer(s) elke ~5-10 min (fetch + process). *[leveren]*
7. **Observability ("geen ik-wist-het-niet")** — elke run logt zijn uitkomst; bij fout een
   Discord-ping. *[bouwen]*
8. **Reconciliatie** — intended (intent) vs actual (fill) → slippage/latency per trade, in de
   bestaande `Slippage`-kolommen. *[valt samen met de join]*
9. **Backfill** — bestaande `/root/exports` (+ archive) eenmalig doorlopen om gaten te vullen;
   idempotent, dus veilig naast de al ingevulde 457 rijen. *[eenmalig]*

---

## Openstaande keuzes

- **Fills-bron:** eerst Weg A (Tradovate-API) testen op de server? (aanrader)
- **Framework:** staat de strategie/El___-naam in `routed_*.jsonl`? Zo ja → exact; zo nee →
  afleiden uit instrument+fase (+ intent voor NQ).

## Volgorde

1. Test Weg A (API-fills) → bepaalt de fills-bron.
2. Runner + intent-join + Framework → complete rijen.
3. Systemd-timer + observability → automatisch & near-real-time.
4. Backfill → gaten dicht.
