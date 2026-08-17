# MEX trade middleware

The switchboard between TradingView and your broker accounts. TradingView sends **one
lean signal per strategy** (`GC`, `ES`); the middleware looks up which accounts
subscribe to that strategy and dispatches each account's real broker order (Phase 1 =
PickMyTrade → Tradovate). That is what lets you run 11+ accounts from 2 alerts instead
of hand-maintaining one alert per account per strategy.

```
                        ┌─ EXEC ── PMT ──────▶ Tradovate account 1..N   (per acct: firm/asset/vol)
TradingView alert ─▶ middleware ┼─ EXEC ── PineConnector ▶ MT5/FTMO
   (strategy "GC")   (control    ├─ NOTIFY ─ Discord/Telegram (live embed per trade; funded|eval split)
                      plane)     ├─ JOURNAL ─ sqlite (internal) + LifeOS Trade Journal
                                 └─ TRACK ── Tradovate P&L ▶ LifeOS Fleet Performance
```
Not a copy-trader: you control per account which firm/asset/volume/channel. One alert →
the middleware fans out across execution AND notification channels and keeps you informed.

## Safety model
- **DRY_RUN=true by default** — payloads are built and journalled but NOT sent. Wire
  everything end-to-end first; flip to `false` only when you're ready for live orders.
- **Kill-switch**: `POST /killswitch?secret=...&armed=false` halts all dispatch instantly.
- **Shared secret** on every request; nothing secret is committed (`.env`, `accounts.yaml`
  and `*.db` are git-ignored).

## Run it locally (Phase 0 — do this first)
```bash
cd middleware
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set MIDDLEWARE_SECRET (keep DRY_RUN=true)
cp accounts.example.yaml accounts.yaml
set -a; . ./.env; set +a
uvicorn app.main:app --reload --port 8000
```
Then send a test signal (this is exactly what TradingView will POST):
```bash
curl -s localhost:8000/webhook -H 'content-type: application/json' -d '{
  "secret":"'"$MIDDLEWARE_SECRET"'","strategy":"GC","event":"ENTRY","action":"buy",
  "symbol":"GC1!","price":2650.5,"order_type":"LMT","dollar_sl":100,"dollar_tp":250,"qty":1
}' | python -m json.tool
curl -s "localhost:8000/journal?secret=$MIDDLEWARE_SECRET&limit=5" | python -m json.tool
```
You should see the built PMT payload per subscribed account with `"status":"dry_run"`.
That's Phase 0+1 proven with zero risk.

## Go live (later)
1. Put your real accounts in `accounts.yaml`; set `PMT_URL` + `PMT_TOKEN` in `.env`.
2. Test on ONE demo/eval account first.
3. Set `DRY_RUN=false`, restart, fire one signal, confirm the order in Tradovate.

## Easiest deploy — Render (no VPS, no terminal)
Best for beginners. Render runs the app straight from GitHub and gives you an HTTPS URL.
1. Make a free account at https://render.com and connect your GitHub.
2. **New + → Blueprint →** pick this repo. Render reads `middleware/render.yaml` and creates
   the service (plan: *starter*, ~$7/mo — the free plan sleeps and would miss webhooks).
3. In the service **Environment** tab, fill the blanks:
   - `MIDDLEWARE_SECRET` — any long random text (your password).
   - `ACCOUNTS_YAML` — paste your whole account map (the contents of `accounts.example.yaml`,
     edited with your accounts). No file needed.
   - `PMT_URL`, `PMT_TOKEN` — from your PickMyTrade dashboard.
   - leave `DRY_RUN=true`.
4. Deploy. Your webhook URL is `https://<your-app>.onrender.com/webhook`.
Flip `DRY_RUN=false` only after you've watched the dry-run journal and tested one account.

## Deploy on a VPS — one command (persistent journaling + live tracking)
On a fresh Ubuntu VPS, clone the repo, then from `middleware/` run:
```bash
sudo bash deploy/setup.sh middleware.yourdomain.com
```
It installs Python + Caddy, builds the app, writes `.env` (auto-generates your secret,
keeps `DRY_RUN=true`), installs the systemd service, and sets up HTTPS. Then edit `.env`
with your tokens and `sudo systemctl restart mex-middleware`. Point your domain's A-record
at the VPS first. Live fleet tracking to LifeOS: set `TRADOVATE_*` and
`NOTION_TOKEN` + `NOTION_DB_ID` (the "MEX Fleet Performance (live)" database) in `.env`.

## Deploy on a VPS (manual steps — public HTTPS for TradingView)
```bash
# on the VPS, as a non-root user 'mex'
sudo mkdir -p /opt/mex-middleware && sudo chown mex /opt/mex-middleware
# copy this middleware/ folder there, then:
cd /opt/mex-middleware
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in; DRY_RUN=true until tested
sudo cp deploy/mex-middleware.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now mex-middleware
# HTTPS via Caddy (auto Let's Encrypt); edit the domain in deploy/Caddyfile
sudo apt install -y caddy && sudo cp deploy/Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy
```
TradingView webhook URL becomes `https://middleware.yourdomain.com/webhook`.

## Notify channel (Discord / Telegram)
Every fan-out posts a **rich embed** per trade and pings a separate alert channel when a
dispatch fails. Both are best-effort — a dead webhook can never break the order path.

**Per-trade message** — colour by direction (green long / red short), grey on exits, and
**red when nothing got through** (a missed trade, not a degraded one). Fields: price, qty,
SL/TP, the accounts it routed to, plus per-account reasons for anything blocked or failed.
A `DRY RUN` footer while `DRY_RUN=true`. On exits it adds the fleet **day P&L** tally
(realized since midnight ET + open), which needs the Tradovate poller running — without it
the field is simply omitted. If the alert sends a `chart_url`, it becomes the embed image.

**Separate streams.** Give each account a `kind: funded|eval` (and optionally `firm:`) and
set the channels in `accounts.yaml`:
```yaml
notify:
  default: "${NOTIFY_WEBHOOK}"
  funded: "${NOTIFY_FUNDED_WEBHOOK}"
  eval: "${NOTIFY_EVAL_WEBHOOK}"
```
One signal hitting funded *and* eval accounts then posts **one message per channel**, each
listing only its own accounts. Resolution order, most specific first:
`account.notify` → `strategies.<name>.notify` → `kind` → `firm` → `default`. Existing
configs keep routing exactly as they did (the per-strategy override still wins over groups).

**Failure alerts carry a severity**, so a burst is readable at a glance:
| Severity | When | Meaning |
|---|---|---|
| 🚨 critical | 4xx, missing URL, unknown broker, or *every* account failed | won't fix itself — go look |
| ⚠️ warning | 5xx or network error after retries were exhausted | transient, partially routed |

Bursts are rate-limited per strategy+severity (`ALERT_MAX_PER_WINDOW` per
`ALERT_WINDOW_SECONDS`); suppressed alerts are counted and reported as `+N suppressed` on
the next one that goes out, so nothing is dropped silently.

### Non-order events (`POST /notice`) — the other cards
Entries and exits arrive as a `Signal` on `/webhook`. Everything *else* a strategy
reports — **limit expired, auto flat, signal blocked, config**, day halt, payout, derisk,
risk-off, trail, fill — is emitted by Pine's `f_sendDiscord(...)`, which posts **straight
to a Discord webhook** as a flat blue embed. Those never touched this renderer, which is
why they still looked like the old format.

**Fix (no Pine edit, no re-paste):** in the TradingView alert that currently points at
your Discord webhook, change the webhook URL to
```
https://<your-app>/notice?secret=<MIDDLEWARE_SECRET>&strategy=ES
```
The middleware parses the Pine body back into a typed notice and renders a card per event
kind: emoji, colour and real fields (blocked-by reasons as a list, the limit price, the
whole `cfgStr` broken out into a **Config** card). `strategy=` is optional — it is derived
from the ticker (`ES1!`/`ESZ2025` → `ES`) when omitted, but set it explicitly if an account
trades a micro (`MES1!`) under the ES strategy. Notices go to every channel that
strategy's accounts route to, so the funded/eval split holds here too.

A structured body works as well, if you'd rather not rely on text parsing:
```json
{"kind": "signal_blocked", "symbol": "ES1!", "data": {"direction": "Short", "reasons": ["MAE guard"]}}
```
`/notice` never dispatches an order — it only notifies and journals (`kind='notice'`).
`NOTICE_SUPPRESS` (default `entry_intent`) drops kinds that would duplicate the trade card;
set it to empty to see everything, or add kinds to quieten them down.

**Telegram** works on the same env vars — point `NOTIFY_WEBHOOK`/`ALERT_WEBHOOK` at
`https://api.telegram.org/bot<TOKEN>/sendMessage` and set `TELEGRAM_CHAT_ID` (or append
`?chat_id=...`). The message is sent as Telegram Markdown; the embed is Discord-only.

Test without posting anything real: keep `DRY_RUN=true` and point the webhooks at a
throwaway Discord channel, or run `python -m pytest tests` from `middleware/`.

## Wiring the Pine side (Phase 2)
The scripts already emit a rich PMT JSON. To use the middleware instead, add a
"→ Middleware" alert that posts the lean `Signal` shape above (strategy/action/
symbol/price/dollar_sl/dollar_tp/qty + secret) to `/webhook`. The account fan-out then
lives here, not in the alert. (Kept out of scope for Phase 0.)

## Roadmap
- [x] Phase 0 — receive + journal
- [x] Phase 1 — PMT (Tradovate) dispatch, DRY_RUN
- [x] Phase 2 — Pine "→ Middleware" alert (v6.9.1) — contract verified against the Signal model
- [x] Phase 4 — idempotency (dedupe within IDEM_TTL), PMT retries w/ backoff (5xx only), failure alerts
- [x] Phase 3 — PineConnector (MT5/FTMO) broker + cross-firm fan-out (one signal → Apex + FTMO)
- [x] Phase 5 — risk overlay: per-account daily entry cap + halt flag (`/halt`, `/risk`);
      exits never blocked. Full DLL/consistency ($) enforcement is dormant until a PnL
      feed is wired to `RiskState.record_fill` (Phase 5b).
- [x] Notify channel — rich Discord embeds, funded/eval channel split, severity + rate-limited
      failure alerts, Telegram parity, day-P&L on exits (chart image when the alert sends a URL)
- [x] Notice cards (`/notice`) — limit expired, auto flat, signal blocked, config + the rest of
      the Pine `f_sendDiscord` events, rendered instead of the flat blue embed
- [ ] Go-live — VPS deploy, tokens, TradingView alerts, flip one account to DRY_RUN=false
