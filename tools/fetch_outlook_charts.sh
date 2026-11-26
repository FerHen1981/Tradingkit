#!/usr/bin/env bash
# Haalt de outlook-charts van de dag op naar schijf, zodat een run ze kan LEZEN.
#
# Waarom dit bestaat: de charts zijn afbeeldingen. WebFetch levert tekst en kan
# candlesticks niet tonen — die route is per definitie kansloos. De enige
# werkende volgorde is: downloaden naar een bestand, dan het bestand lezen (de
# Read-tool toont afbeeldingen visueel).
#
# Gebruik:
#   tools/fetch_outlook_charts.sh                 # ET-datum van vandaag
#   tools/fetch_outlook_charts.sh 20260810        # expliciete dag
#   MEX_CHART_ASSETS="NQ ES" tools/fetch_outlook_charts.sh
#
# Exit 0 = alle charts binnen. Exit 1 = er ontbreekt er minstens één; het script
# zegt precies welke en waarom. Bij exit 1 hoort GEEN analyse te volgen: liever
# geen outlook dan een verzonnen outlook.

set -uo pipefail

BASE="${MEX_CHARTS_BASE_URL:-https://mw.mex-traders.com/charts}"
ASSETS="${MEX_CHART_ASSETS:-NQ ES GC QQQ BTC}"
# De crawler draait om 08:00 ET en benoemt bestanden op ET-datum, niet UTC.
# Na 20:00 ET is het in UTC al morgen — dan zou een UTC-datum de verkeerde map zoeken.
DATE="${1:-$(TZ=America/New_York date +%Y%m%d)}"
DEST="${MEX_CHART_DIR:-charts}/${DATE}"

mkdir -p "$DEST"
missing=()

for a in $ASSETS; do
  url="${BASE}/${DATE}/${DATE}_${a}.png"
  out="${DEST}/${DATE}_${a}.png"
  read -r code type bytes <<<"$(curl -sS -o "$out" \
      -w '%{http_code} %{content_type} %{size_download}' --max-time 30 "$url" 2>/dev/null)"

  if [ "$code" != "200" ]; then
    missing+=("$a: HTTP ${code:-geen antwoord} — $url")
    rm -f "$out"
  elif [ "${type%%;*}" != "image/png" ]; then
    # Een allowlist-blok of proxy-foutpagina geeft 200 met text/html; die val je
    # anders pas op als je "chart" een HTML-pagina blijkt te zijn.
    missing+=("$a: kreeg ${type:-onbekend} in plaats van image/png (proxy/allowlist?)")
    rm -f "$out"
  elif [ "${bytes:-0}" -lt 10000 ]; then
    missing+=("$a: slechts ${bytes}b — waarschijnlijk een foutpagina")
    rm -f "$out"
  else
    printf '%-4s %s (%sb)\n' "$a" "$out" "$bytes"
  fi
done

if [ ${#missing[@]} -gt 0 ]; then
  printf '\nONTBREEKT (%d):\n' "${#missing[@]}" >&2
  printf '  %s\n' "${missing[@]}" >&2
  cat >&2 <<'EOF'

Geen analyse maken met een onvolledige set. Twee bekende oorzaken:
  1. Host niet op de allowlist van deze omgeving -> content_type text/html of HTTP 403.
     Oplossen in de omgevings-instellingen (netwerk-policy), niet in dit script.
  2. Crawler heeft nog niet gedraaid (cron 08:00 ET) -> HTTP 404 op de dagmap.
EOF
  exit 1
fi
