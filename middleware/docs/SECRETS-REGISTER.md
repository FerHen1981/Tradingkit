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

## Register — execution & tracking (bestaande middleware)

| Secret / login | Waar de waarde leeft | Gebruikt door | Kluis-locatie | Laatst geroteerd |
|---|---|---|---|---|
| `MIDDLEWARE_SECRET` | `.env` op VPS | webhook-auth, /journal, /killswitch | _(vul in)_ | _(vul in)_ |
| `PMT_URL` | `.env` | PickMyTrade dispatch | | |
| `PMT_TOKEN` | `.env` / `accounts.yaml` (`${PMT_TOKEN}`) | PMT → Tradovate execution | | |
| `PC_URL` | `.env` | PineConnector dispatch (MT5/FTMO) | | |
| `PC_LICENSE` | `.env` / `accounts.yaml` (`${PC_LICENSE}`) | PineConnector EA-licentie | | |
| `TRADOVATE_NAME` | `.env` | live P&L-tracking | | |
| `TRADOVATE_PASSWORD` | `.env` | live P&L-tracking | | |
| `TRADOVATE_APPID` / `TRADOVATE_CID` / `TRADOVATE_SEC` | `.env` | Tradovate API (tracking + later close-capability) | | |
| `METAAPI_TOKEN` | `.env` | MT5/FTMO fills (reconciliation + later close) | | |
| `METAAPI_ACCOUNT_ID` | `.env` | MetaAPI-account | | |
| `NOTION_TOKEN` | `.env` | LifeOS-sync | | |
| `NOTION_DB_ID` / `NOTION_JOURNAL_DB` / `NOTION_RECON_DB` | `.env` | LifeOS-databases (id's = referenties, laag risico) | | |
| `ALERT_WEBHOOK` / `NOTIFY_WEBHOOK` | `.env` | Discord/Telegram-notificaties | | |

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
| 2026-08-05 | Architectuur vastgelegd: split brain/faces · volledige web-controle (2FA+audit) · Postgres/Supabase · Next.js. Zie ARCHITECTURE.md. |
| 2026-08-05 | Secrets-beleid: alleen referenties in LifeOS, waarden in kluis. |

## Rotatie-afspraak (aanrader)

- Roteer `MIDDLEWARE_SECRET`, broker- en API-tokens minimaal **elke 3–6 maanden** en
  direct bij elk vermoeden van lek. Noteer de datum in de kolom "Laatst geroteerd".
- Bewaar 2FA-backup-codes op een **andere** plek dan het wachtwoord.
