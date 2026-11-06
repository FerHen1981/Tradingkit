#!/usr/bin/env bash
# Healthcheck voor de MEX-middleware. Curlt /health; bij falen (of ok!=true):
# herstart de service en meldt het op de failure-webhook (ALERT_WEBHOOK uit .env).
# Draait via mex-healthcheck.timer (elke minuut).
set -u
ENV_FILE=/opt/mex-middleware/.env
URL="http://127.0.0.1:8000/health"
[ -f "$ENV_FILE" ] && source <(grep -E '^ALERT_WEBHOOK=' "$ENV_FILE") || true

body=$(curl -fsS --max-time 5 "$URL" 2>/dev/null)
if [ $? -ne 0 ] || ! grep -q '"ok":true' <<<"$body"; then
    systemctl restart mex-middleware
    if [ -n "${ALERT_WEBHOOK:-}" ]; then
        curl -fsS --max-time 5 -H "Content-Type: application/json" \
             -d '{"content":"⚠️ MEX middleware healthcheck faalde — service herstart."}' \
             "$ALERT_WEBHOOK" >/dev/null 2>&1 || true
    fi
    exit 1
fi
exit 0
