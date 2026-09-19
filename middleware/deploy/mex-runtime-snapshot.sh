#!/usr/bin/env bash
# MEX runtime snapshot — D-31.
#
# Waarom dit bestaat: op 24-08 kostte de vraag "welke versie van de receiver draait er
# eigenlijk" een half gesprek, drie mislukte bestandsoverdrachten en een verkeerde
# grep-uitkomst. Eén checksum beantwoordde hem uiteindelijk. Die checksum staat nu
# gewoon in de repo, elk uur ververst.
#
# Bewust GEEN ops-endpoint: dat zou runtime-waarheid opnieuw aan een draaiende service
# hangen, en precies dat is wat misging. Een bestand in git veroudert zichtbaar.
#
# VEILIGHEID: `systemctl cat` bevat Environment=-regels met secrets. Die worden hier
# gefilterd. Voeg niets toe dat de omgeving ongefilterd uitleest.

set -uo pipefail

REPO="${SNAPSHOT_REPO:-/root/mex-journal}"
OUT="$REPO/docs/runtime-snapshot.md"
SRC="${RECEIVER_SRC:-/root/mex-middleware-b/src/Mex.Journal.Receiver}"
DLL="$SRC/bin/Release/net10.0/Mex.Journal.Receiver.dll"

field() { printf '| %-24s | %s |\n' "$1" "${2:-—}"; }

svc_started() { systemctl show mex-receiver -p ActiveEnterTimestamp --value 2>/dev/null; }
svc_state()   { systemctl is-active mex-receiver 2>/dev/null; }

gen() {
  echo "# Runtime-snapshot — mex-mw-01"
  echo
  echo "> Gegenereerd door \`mex-runtime-snapshot.timer\`. **Niet met de hand bijwerken.**"
  echo "> Veroudert deze tabel, dan draait de timer niet — dat is zelf ook informatie."
  echo
  echo "**Gemaakt:** $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo
  echo "## mex-receiver"
  echo
  echo "| | |"
  echo "|---|---|"
  field "service"        "$(svc_state)"
  field "gestart"        "$(svc_started)"
  field "bron"           "\`$SRC/Program.cs\`"
  field "bron md5"       "\`$(md5sum "$SRC/Program.cs" 2>/dev/null | cut -d' ' -f1)\`"
  field "bron regels"    "$(wc -l < "$SRC/Program.cs" 2>/dev/null)"
  field "bron gewijzigd" "$(stat -c '%y' "$SRC/Program.cs" 2>/dev/null | cut -d'.' -f1)"
  field "binary"         "$(stat -c '%y' "$DLL" 2>/dev/null | cut -d'.' -f1)"
  field "binary bytes"   "$(stat -c '%s' "$DLL" 2>/dev/null)"
  field "dotnet"         "$(dotnet --version 2>/dev/null)"
  echo
  echo "**Binary ouder dan de bron?** $(
    if [ "$DLL" -ot "$SRC/Program.cs" ]; then echo '⚠️ JA — er is gewijzigd zonder te bouwen'
    else echo 'nee'; fi)"
  echo
  echo "## Andere units"
  echo
  echo '| unit | actief | laatst gestart |'
  echo '|---|---|---|'
  for u in mex-viewer mex-reconcile.timer mex-public-stats.timer mex-routed-journal.timer caddy; do
    printf '| %s | %s | %s |\n' "$u" \
      "$(systemctl is-active "$u" 2>/dev/null)" \
      "$(systemctl show "$u" -p ActiveEnterTimestamp --value 2>/dev/null)"
  done
  echo
  echo "## Unit-definitie mex-receiver"
  echo
  echo "Zonder \`Environment=\`-regels — die dragen secrets."
  echo
  echo '```ini'
  systemctl cat mex-receiver 2>/dev/null | grep -v '^Environment=' | grep -v '^EnvironmentFile='
  echo '```'
  echo
  echo "## Gezette omgevingsvariabelen"
  echo
  echo "Alleen de namen, nooit de waarden."
  echo
  systemctl show mex-receiver -p Environment --value 2>/dev/null \
    | tr ' ' '\n' | grep -o '^[A-Z_][A-Z0-9_]*' | sort -u | sed 's/^/- `/; s/$/`/'
  # Altijd 0: draait er geen systemd of ontbreekt een unit, dan is een halve snapshot
  # nog steeds bruikbaar. Zonder dit gooide een falende systemctl het hele bestand weg.
  return 0
}

mkdir -p "$(dirname "$OUT")"
gen > "$OUT.tmp"
mv "$OUT.tmp" "$OUT"
cat "$OUT"

# Committen mag mislukken — het bestand staat er dan nog steeds en journalctl toont het.
if git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
  if ! git -C "$REPO" diff --quiet -- docs/runtime-snapshot.md 2>/dev/null; then
    git -C "$REPO" add docs/runtime-snapshot.md
    git -C "$REPO" -c user.name="mex-mw-01" -c user.email="ops@mex-traders.com" \
        commit -q -m "runtime-snapshot: $(date -u '+%Y-%m-%d %H:%M UTC')" \
      && git -C "$REPO" push -q origin HEAD 2>/dev/null \
      && echo "-- gecommit en gepusht" || echo "-- lokaal bijgewerkt, push niet gelukt"
  else
    echo "-- ongewijzigd sinds de vorige ronde"
  fi
else
  echo "-- $REPO is geen git-repo; snapshot staat alleen lokaal in $OUT"
fi
