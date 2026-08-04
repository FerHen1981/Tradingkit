#!/usr/bin/env bash
# One-shot VPS setup for the MEX middleware (fresh Ubuntu 22.04/24.04).
#
# Usage (as root, from inside the cloned repo's middleware/ folder):
#   sudo bash deploy/setup.sh middleware.yourdomain.com
#
# It installs Python + Caddy, builds the app, writes a .env (auto-generates the secret),
# installs a systemd service, and configures HTTPS via Caddy. You then fill your tokens
# into .env and restart. DRY_RUN stays true until you flip it.
set -euo pipefail

DOMAIN="${1:-}"
if [ -z "$DOMAIN" ]; then
  echo "Usage: sudo bash deploy/setup.sh <your-domain, e.g. middleware.example.com>"; exit 1
fi

APPDIR="$(cd "$(dirname "$0")/.." && pwd)"   # the middleware/ folder
RUNUSER="${SUDO_USER:-root}"
echo "==> App dir: $APPDIR   run-user: $RUNUSER   domain: $DOMAIN"

echo "==> Installing packages (python, caddy)…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3-venv python3-pip debian-keyring debian-archive-keyring apt-transport-https curl
if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy
fi

echo "==> Building the app…"
cd "$APPDIR"
python3 -m venv .venv
.venv/bin/pip install --quiet -r requirements.txt

if [ ! -f .env ]; then
  echo "==> Writing .env (auto-generating MIDDLEWARE_SECRET; DRY_RUN=true)…"
  cp .env.example .env
  SECRET="$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9')"
  sed -i "s|^MIDDLEWARE_SECRET=.*|MIDDLEWARE_SECRET=${SECRET}|" .env
  echo "    -> your secret: ${SECRET}   (also in .env; you'll need it in TradingView)"
fi
chown -R "$RUNUSER":"$RUNUSER" "$APPDIR"

echo "==> Installing systemd service…"
sed -e "s|/opt/mex-middleware|$APPDIR|g" -e "s|^User=.*|User=$RUNUSER|" \
    deploy/mex-middleware.service > /etc/systemd/system/mex-middleware.service
systemctl daemon-reload
systemctl enable --now mex-middleware

echo "==> Configuring HTTPS (Caddy) for $DOMAIN…"
cat > /etc/caddy/Caddyfile <<EOF
$DOMAIN {
    reverse_proxy 127.0.0.1:8000
}
EOF
systemctl reload caddy || systemctl restart caddy

echo ""
echo "================ DONE ================"
echo "Webhook URL : https://$DOMAIN/webhook"
echo "Health      : https://$DOMAIN/health"
echo "Next:"
echo "  1) Edit $APPDIR/.env — add PMT_URL, PMT_TOKEN, ACCOUNTS_YAML (or accounts.yaml),"
echo "     TRADOVATE_* and NOTION_TOKEN/NOTION_DB_ID. Keep DRY_RUN=true for now."
echo "  2) sudo systemctl restart mex-middleware"
echo "  3) Check:  curl https://$DOMAIN/health"
echo "  4) In TradingView, point the '→ Middleware' alert at the webhook URL above."
echo "====================================="
