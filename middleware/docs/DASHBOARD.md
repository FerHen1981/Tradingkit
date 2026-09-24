# Owner cockpit — live fleet dashboard (app.mex-traders.com)

A read-only, own-login web dashboard showing the fleet live: per-account open positions,
today's closed trades, realized P&L, win rate, profit factor and status — refreshed every
10s. Reads the **routed-log** (the same live source as the Trade Journal), so it needs no
Tradovate access and nothing new to run besides one small process.

It's the **Viewer API seam** from `ARCHITECTURE.md`: a later Next.js face can consume the
same `/api/state` JSON. Control actions (halt/kill/close) come in a later phase.

- `app/viewer.py` — stdlib-only server (runs on the VPS's Python 3.14). Endpoints:
  `/` (login → dashboard), `/api/state` (JSON), `/login` (POST), `/healthz`.
- Owner-only: set `VIEWER_PASSWORD`; a signed `mexsession` cookie gates `/` and `/api/state`.

## Deploy on mex-mw-01

**1. Add the password to your env file** (`/root/mex-journal/middleware/.env`):
```
VIEWER_PASSWORD=<pick-a-strong-password>
VIEWER_SECRET=<any-long-random-string>
```

**2. Run it as a service:**
```bash
cd /root/mex-journal/middleware
sudo cp deploy/mex-viewer.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now mex-viewer
systemctl status mex-viewer --no-pager
curl -s localhost:8080/healthz     # -> ok
```

**3. DNS (GoDaddy):** add an **A-record** `app` → your VPS IP (167.233.215.60).

**4. TLS via Caddy** (automatic HTTPS):
```bash
sudo apt install -y caddy          # if not already installed
# ensure /etc/caddy/Caddyfile contains the app.mex-traders.com block from deploy/Caddyfile
sudo systemctl reload caddy
```

Then open **https://app.mex-traders.com**, log in with `VIEWER_PASSWORD`.

## Config (env)

| var | default | meaning |
|-----|---------|---------|
| `VIEWER_PASSWORD` | *(unset = open!)* | owner login password — set this in production |
| `VIEWER_SECRET` | derived from password | signs the session cookie |
| `VIEWER_API_TOKEN` | *(unset)* | read-only token for `/api/state` (iPhone widget etc.) |
| `ROUTED_DIR` | `/root/intent-store` | routed-log source |
| `VIEWER_PORT` | `8080` | local listen port (Caddy proxies to it) |
| `ROUTED_DAYS` | `2` | how many routed files back to read |

## iPhone widget (Scriptable)

`scriptable/mex-fleet-widget.js` renders the live fleet (realized today, open positions,
trades, win rate) on the home screen — Small or Medium.

1. Server: set `VIEWER_API_TOKEN=<long-random-string>` in `.env`, `sudo systemctl restart mex-viewer`.
2. iPhone: install **Scriptable** → new script → paste the file → set `BASE` (your cockpit URL)
   and `TOKEN` (== `VIEWER_API_TOKEN`).
3. Home screen → add a Scriptable widget → pick this script. Tapping it opens the full cockpit.

The token only grants read access to `/api/state`; it never exposes the owner password or any
control action.

## What it shows now / later

- **Now:** fleet KPIs (realized today, open positions, trades, win rate, profit factor),
  per-account rows with expandable open positions + today's closed trades, live status.
- **Later:** live unrealized P&L on open positions (needs a price feed), per-account
  consistency/payout (State Engine), and control actions (halt/kill now-capable; close/flatten
  once an order path exists). The public brand site + follower portal build on the same seam.
