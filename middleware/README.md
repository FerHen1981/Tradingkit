# MEX trade middleware

The switchboard between TradingView and your broker accounts. TradingView sends **one
lean signal per strategy** (`GC`, `ES`); the middleware looks up which accounts
subscribe to that strategy and dispatches each account's real broker order (Phase 1 =
PickMyTrade → Tradovate). That is what lets you run 11+ accounts from 2 alerts instead
of hand-maintaining one alert per account per strategy.

```
TradingView alert ──POST /webhook──▶  middleware  ──▶ PMT (Tradovate)  ──▶ account 1
   (strategy: "GC")                   │  account-map     PineConnector  ──▶ account 2  (later)
                                       └─ journal (sqlite)                    ...
```

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
- [ ] Go-live — VPS deploy, tokens, TradingView alerts, flip one account to DRY_RUN=false
