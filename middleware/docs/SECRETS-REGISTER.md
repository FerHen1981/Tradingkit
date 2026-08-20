# Secrets-register & belangrijke notities (referenties, GEEN waarden)

> ⚠️ **Hier staan GEEN echte tokens, wachtwoorden of sleutels.** Alleen: welke secret
> bestaat, waar de echte waarde leeft, wie 'm gebruikt en wanneer hij geroteerd is.
> De **waarden** horen in een kluis (Bitwarden / 1Password / Supabase Vault) of in de
> `.env` op de VPS — nooit in git, nooit als platte tekst in een gedeelde LifeOS-pagina.
>
> Dit bestand is bedoeld om over te nemen in LifeOS als bijhoud-register. Vul de
> kolommen **"Kluis-locatie"** en **"Laatst geroteerd"** in; laat **"Waarde"** leeg.

## Waar de echte waarden leven

- **Op de server**: `middleware/.env` en `middleware/accounts.yaml` (beide git-ignored).
- **Kluis** (aanrader): een map "Pips & Palm Trees / Fleet platform" in Bitwarden of 1Password.
- **Later**: Supabase Vault voor server-side secrets van het platform.

---

## 🔴 Roteren NU — checklist (D-11)

Deze secrets zijn tussen 9-aug en 19-aug langs chats gekomen (Discord-webhook,
Notion-token, Fase C endpoint-token) of in een sessie-transcript beland
(`VIEWER_PASSWORD`, `MEX_WEBHOOK_SECRET`). Roteer ze en zet in de laatste kolom
`✅ <datum>`.

| Secret | Waar roteren | Waar de nieuwe waarde opslaan | Wie herstart | Geroteerd |
|---|---|---|---|---|
| `NOTION_TOKEN` | notion.so → Settings → Connections → jouw integration → *Rotate token* | `.env` op VPS (`NOTION_TOKEN=…`) + Bitwarden | `sudo systemctl restart mex-viewer mex-reconcile.timer routed-journal.timer` (elke service die naar Notion schrijft) | ☐ |
| `NOTIFY_WEBHOOK` (Discord) | discord.com → server settings → Integrations → Webhooks → *Reset webhook URL* | `.env` op VPS + Bitwarden | `sudo systemctl restart mex-receiver` (.NET-receiver leest webhook uit env) | ☐ |
| Fase C endpoint-token | endpoint-eigenaar (Ferry) — genereer nieuw token en update de config aan de kant die het endpoint aanroept | `.env` op VPS + Bitwarden | de service die het endpoint aanroept opnieuw starten | ☐ |
| `VIEWER_PASSWORD` | zelfgekozen sterk wachtwoord (min 20 tekens, geen hergebruik) | `.env` op VPS + Bitwarden | `sudo systemctl restart mex-viewer` | ☐ |
| `MEX_WEBHOOK_SECRET` | zelfgekozen willekeurige string (`openssl rand -hex 32`) | `.env` op VPS + Bitwarden; ook bijwerken in TradingView-alerts die deze meesturen | `sudo systemctl restart mex-receiver` | ☐ |
| `VIEWER_API_TOKEN` | zelfgekozen willekeurige string (`openssl rand -hex 24`) | `.env` op VPS + Bitwarden; ook in Scriptable-scripts op iPhone bijwerken | `sudo systemctl restart mex-viewer` | ☐ |

**Verificatie na rotatie** — geen 401/403 in de logs:
```bash
sudo journalctl -u mex-viewer -u mex-receiver -u mex-reconcile.service -n 100 | grep -E "401|403|auth|token"
```

**Als iets stukloopt na rotatie:** de oude waarde blijft geldig totdat je 'm bij de
uitgever intrekt — laat dat kort na, niet meteen bij het schrijven van de nieuwe.
Windowsafspraak: 24 uur oud + nieuw tegelijk geldig, daarna oude intrekken.

---

## Register — execution & tracking (bestaande middleware)

| Secret / login | Waar de waarde leeft | Gebruikt door | Kluis-locatie | Laatst geroteerd |
|---|---|---|---|---|
| `MIDDLEWARE_SECRET` | `.env` op VPS | webhook-auth (dead path — zie D-05) | _(vul in)_ | _(vul in)_ |
| `MEX_WEBHOOK_SECRET` | `.env` op VPS | .NET-receiver webhook-auth (live) | _(vul in)_ | _(vul in — zie boven)_ |
| `PMT_URL` | `.env` | PickMyTrade dispatch (via .NET-receiver) | | |
| `PMT_TOKEN` | `.env` / `accounts.yaml` (`${PMT_TOKEN}`) | PMT → Tradovate execution | | |
| `PC_URL` | `.env` | PineConnector dispatch (MT5/FTMO — dead path) | | |
| `PC_LICENSE` | `.env` / `accounts.yaml` (`${PC_LICENSE}`) | PineConnector EA-licentie (dead path) | | |
| `TRADOVATE_NAME` | `.env` | live P&L-tracking (niet actief op prop-sub-accounts) | | |
| `TRADOVATE_PASSWORD` | `.env` | live P&L-tracking | | |
| `TRADOVATE_APPID` / `TRADOVATE_CID` / `TRADOVATE_SEC` | `.env` | Tradovate API (tracking + later close-capability) | | |
| `METAAPI_TOKEN` | `.env` | MT5/FTMO fills (reconciliation + later close) | | |
| `METAAPI_ACCOUNT_ID` | `.env` | MetaAPI-account | | |
| `NOTION_TOKEN` | `.env` | LifeOS-sync (Trade Journal, Reconciliation, Fleet) | _(vul in)_ | _(vul in — zie boven)_ |
| `NOTION_DB_ID` / `NOTION_JOURNAL_DB` / `NOTION_RECON_DB` | `.env` | LifeOS-databases (id's = referenties, laag risico) | | |
| `NOTIFY_WEBHOOK` / `ALERT_WEBHOOK` | `.env` | Discord-notificaties | _(vul in)_ | _(vul in — zie boven)_ |
| `VIEWER_PASSWORD` | `.env` | `app.mex-traders.com` cockpit-login | _(vul in)_ | _(vul in — zie boven)_ |
| `VIEWER_API_TOKEN` | `.env` | Scriptable iPhone-widget read-only endpoint | _(vul in)_ | _(vul in — zie boven)_ |
| `VIEWER_SECRET` | `.env` (optioneel) | session-cookie signing (default afgeleid van `VIEWER_PASSWORD`) | | |

## Register — infrastructuur (nieuw, bij het platform)

| Secret / login | Waar de waarde leeft | Gebruikt door | Kluis-locatie | Laatst geroteerd |
|---|---|---|---|---|
| VPS root/SSH-login | kluis + Termius | serverbeheer | | |
| Domein-login (GoDaddy) | kluis | DNS `pipsandpalmtrees.com` | | |
| Supabase — project-URL + `anon` key | Vercel env (publiek, laag risico) | faces-frontend | | |
| Supabase — `service_role` key | Supabase Vault / VPS `.env` | Brain (server-side) | | |
| Supabase — Postgres-wachtwoord | kluis | DB-toegang | | |
| Vercel-login | kluis | faces-deploy | | |
| Owner-login platform (jij) | kluis | owner-console | | |
| Owner 2FA (TOTP-seed / backup-codes) | kluis (backup-codes apart) | 2FA owner-console | | |

## Register — accounts (prop-firms)

> Referenties, geen wachtwoorden. Voeg per account een regel toe; het wachtwoord in de kluis.

| Account (alias) | Firm / programma (`firms.py`-key) | Broker-kanaal | Login in kluis | Notitie |
|---|---|---|---|---|
| _(bv. apex_f1)_ | _(bv. apex_50k_...)_ | pmt_tradovate | _(vul in)_ | |
| _(bv. ftmo_mt5_1)_ | _(bv. ftmo_...)_ | pineconnector | | |

---

## Belangrijke notities (log)

Kort bijhouden wat belangrijk is — beslissingen, wijzigingen, to-checks. Nieuwste boven.

| Datum | Notitie |
|---|---|
| 2026-08-19 | D-11: rotatie-checklist bovenaan toegevoegd. Zes secrets die sinds 9-aug in sessies/chats zijn langsgekomen (`NOTION_TOKEN`, `NOTIFY_WEBHOOK`, Fase C endpoint-token, `VIEWER_PASSWORD`, `MEX_WEBHOOK_SECRET`, `VIEWER_API_TOKEN`) moeten geroteerd worden. |
| 2026-08-05 | Architectuur vastgelegd: split brain/faces · volledige web-controle (2FA+audit) · Postgres/Supabase · Next.js. Zie ARCHITECTURE.md. |
| 2026-08-05 | Secrets-beleid: alleen referenties in LifeOS, waarden in kluis. |

## Rotatie-afspraak (aanrader)

- Roteer `MIDDLEWARE_SECRET`, broker- en API-tokens minimaal **elke 3–6 maanden** en
  direct bij elk vermoeden van lek. Noteer de datum in de kolom "Laatst geroteerd".
- Bewaar 2FA-backup-codes op een **andere** plek dan het wachtwoord.
- **Als een secret in een chat / transcript / commit heeft gestaan**, geldt hij als
  gelekt — zet 'm in de "Roteren NU"-tabel bovenaan en verwerk binnen 48 uur.
