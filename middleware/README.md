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

### Non-order events — the other cards
A TradingView alert posts **every** `alert()` the script fires to the same URL, so
`/webhook` receives two different bodies. The lean `Signal` is an order and gets fanned
out. Everything *else* a strategy reports — **limit expired, auto flat, signal blocked,
config**, day halt, payout, derisk, risk-off, trail, fill — comes from Pine's
`f_sendDiscord(...)` as a Discord-embed body. That is not a `Signal`, so it used to be
rejected with a 422 (journalled as `kind='error'`, `reason='validation'`) and never
reached the renderer.

`/webhook` now recognises those bodies and renders a card per event kind, with real
fields: blocked-by reasons as a list, the limit price, and the whole `cfgStr` broken out
into a **Config** card. Nothing changes in Pine and no alert has to be re-created.

**Pine v6.9.2 and up** sends signal-blocked, auto-flat and config as a *structured* notice
via `f_mwNotice` — secret in the body, exactly like an order — so nothing extra is needed
on the alert URL. Those three used to leave the script only through `f_sendDiscord`, which
is gated on `useDiscord` (and config sat behind `useJournal` in an `else if` chain), so
routing Discord through the middleware silenced them.

**Older scripts / the raw Pine Discord body** carry no `secret`, so there the alert URL has
to supply it — add `?secret=<MIDDLEWARE_SECRET>` to the webhook URL you already use.
Orders keep authenticating on the secret inside their body, so one URL serves everything:
```
https://<your-app>/webhook?secret=<MIDDLEWARE_SECRET>          # optionally &strategy=ES
```
`strategy=` is derived from the ticker (`ES1!`/`ESZ2025` → `ES`); set it explicitly only if
an account trades a micro (`MES1!`) under the ES strategy. Notices go to every channel that
strategy's accounts route to, so the funded/eval split holds here too. `POST /notice` takes
the same bodies, for when these events do come in on their own alert.

A structured body is accepted as well, if you'd rather not rely on text parsing:
```json
{"kind": "signal_blocked", "symbol": "ES1!", "data": {"direction": "Short", "reasons": ["MAE guard"]}}
```
A notice never dispatches an order — it only notifies and journals (`kind='notice'`). A
**malformed order still 422s** rather than being downgraded to a card, so a dropped trade
can't hide as a pretty message. `NOTICE_SUPPRESS` (default `entry_intent`) drops kinds that
would duplicate the trade card; set it empty to see everything.

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
- [x] Notice cards — limit expired, auto flat, signal blocked, config + the rest of the Pine
      `f_sendDiscord` events, rendered on the same `/webhook` instead of 422-ing
- [ ] Go-live — VPS deploy, tokens, TradingView alerts, flip one account to DRY_RUN=false
