# Runbook — Discord-meldingen herstellen (D-116 · D-117 · D-118)

> Opgesteld 29-09-2026 door de Scrum Master, op verzoek van Ferry: *"Maak dan nu een cmd die
> alles hersteld zodat de juiste meldingen terugkomen en alles weer werkt op live."*
>
> 🔴 **Waarom dit geen één-knops-herstel is.** De oorzaak is nog niet vastgesteld — er staan drie
> kandidaten open en ik heb er vandaag al twee van mijn eigen hypotheses moeten intrekken. Een
> blinde fix op een pad met `dryRun:false` en `armed:true` is precies wat je niet wil. Dit runbook
> doet het daarom in twee stappen: **stap 1 stelt vast, stap 2 herstelt.** Stap 2 is bewust zo
> gekozen dat hij veilig is ongeacht welke van de drie oorzaken het is.
>
> ⛔ **Geen enkele stap hieronder raakt het orderpad.** Niet `MEX_DRY_RUN`, niet de kill-switch,
> niet `MEX_ACCOUNT_QTY` (die blijft leeg — D-53), niet PMT of PineConnector. Alles hier gaat
> over **notify**.

---

## Stap 1 — vaststellen (leest alleen, wijzigt niets)

Eén paste. Schrijft het script, voert het uit, en print **nooit** een webhook-URL of token —
alleen namen en HTTP-statussen.

```bash
sudo tee /root/mex-discord-doctor.sh >/dev/null <<'DOCTOR'
#!/usr/bin/env bash
# MEX Discord doctor - D-116/D-117/D-118. LEEST ALLEEN. Wijzigt niets.
# Print nooit een webhook-URL of token: alleen namen en HTTP-statussen.
set -uo pipefail
STORE="${MEX_STORE:-/root/intent-store}"
PID="$(systemctl show mex-receiver -p MainPID --value 2>/dev/null || echo 0)"

echo "=== 1. service en binary ==="
systemctl is-active mex-receiver 2>/dev/null || true
systemctl show mex-receiver -p ActiveEnterTimestamp --value 2>/dev/null || true
systemctl cat mex-receiver 2>/dev/null | grep -iE 'EnvironmentFile|ExecStart' || true
ls -l --time-style=long-iso \
  /root/mex-middleware-b/src/Mex.Journal.Receiver/bin/Release/*/Mex.Journal.Receiver.dll 2>/dev/null | tail -2

ENVF="/proc/$PID/environ"
if [ ! -r "$ENVF" ]; then
  echo; echo "!! kan $ENVF niet lezen (run als root, of de service draait niet)"; exit 1
fi

echo; echo "=== 2. relevante env-NAMEN (geen waarden) ==="
tr '\0' '\n' < "$ENVF" | cut -d= -f1 \
  | grep -E 'WEBHOOK|CARD|RENDER|DISCORD|DRY_RUN|ACCOUNT_QTY|KILL' | sort -u

echo; echo "=== 3. webhook-test: naam + HTTP-status, nooit de URL ==="
while IFS= read -r line; do
  n="${line%%=*}"; v="${line#*=}"
  case "$n" in *WEBHOOK*) ;; *) continue ;; esac
  if [ -z "$v" ]; then printf '%-34s LEEG (valt door naar de volgende)\n' "$n"; continue; fi
  code="$(curl -s -o /dev/null -w '%{http_code}' -m 10 "$v" 2>/dev/null || echo 000)"
  case "$code" in
    200)          printf '%-34s %s  OK\n' "$n" "$code" ;;
    401|403|404)  printf '%-34s %s  <== DOOD / INGETROKKEN\n' "$n" "$code" ;;
    000)          printf '%-34s ---  onbereikbaar of geen URL\n' "$n" ;;
    *)            printf '%-34s %s  ?\n' "$n" "$code" ;;
  esac
done < <(tr '\0' '\n' < "$ENVF")

echo; echo "=== 4. wat de receiver vandaag met Discord deed ==="
F="$STORE/routed_$(date -u +%Y%m%d).jsonl"
if [ ! -f "$F" ]; then echo "geen $F - er is vandaag NIETS geregistreerd"; exit 0; fi
python3 - "$F" <<'PY'
import json, sys, collections
cnt = collections.Counter(); tot = 0
for line in open(sys.argv[1], encoding='utf-8', errors='replace'):
    try: r = json.loads(line)
    except Exception: continue
    tot += 1
    k = r.get("kind") or ""
    if "discord" not in k: continue
    cnt[(k, (r.get("result") or "")[:58])] += 1
print(f"(totaal {tot} regels in het journaal vandaag)")
if not cnt: print("GEEN ENKELE discord-regel -> de alerts komen niet eens aan")
for (k, res), n in cnt.most_common(25):
    print(f"{n:5d}  {k:14s} {res}")
PY
DOCTOR
sudo bash /root/mex-discord-doctor.sh
```

### Hoe je de uitkomst leest

| Wat je ziet | Wat het betekent | Naar welke stap |
|---|---|---|
| In **§3** staat bij `NOTIFY_WEBHOOK_APEX` of `_FUNDED` een **401/403/404** | De per-firm webhook is dood. Kaarten **mét** account (FILL, EXIT, TP/SL, RISK OFF) gingen daarheen; CONFIG niet. **Dit is D-118 bevestigd.** | **2A** |
| In **§4** staan regels met **`card rate-limited`** | De demping gooit berichten weg. **D-116.** | **2B** |
| In **§4** staan regels met **`card exception`** of **`card failed`** | De render faalt; bij `exception` is er geen tekst-fallback. **D-116, tweede tak.** | **2B** |
| In **§4** staat **geen enkele discord-regel** | De alerts komen niet eens aan. Dan is het **TradingView**, niet de middleware — en helpt stap 2 niet. | zie onderaan |
| In **§2** staat `MEX_ACCOUNT_QTY` | ⚠️ Die moet leeg blijven (D-53). Meld het, wijzig niets zelf. | — |

---

## Stap 2 — herstellen

Beide ingrepen gaan via één **drop-in**, niet door een bestand te bewerken. Voordeel: terugdraaien
is één regel, en je ziet in `systemctl cat` precies wat er afwijkt van de basis.

### 2A — routing terugzetten naar de webhook die aantoonbaar wérkt

Zet de per-firm en per-fase webhooks leeg. `WebhookFor()` valt dan door naar de kale
`NOTIFY_WEBHOOK`, en anders naar `MEX_DISCORD_WEBHOOK` — hetzelfde kanaal waar CONFIG vandaag wél
aankomt. Je verliest de kanaalsplitsing; je krijgt alle meldingen terug.

### 2B — beide stille verliespaden uitschakelen

`MEX_RENDER_ENABLED=false` zet de kaart-rendering uit. Daarmee vervalt de hele tak die kan dempen
(D-116) **én** de `catch` zonder tekst-fallback: alles gaat als platte tekst via `ForwardJsonAsync`,
zonder rate-limit. Je verliest de PNG-kaarten; je krijgt elk bericht.

### De paste (2A + 2B samen — dat is de veilige combinatie)

```bash
sudo mkdir -p /etc/systemd/system/mex-receiver.service.d
sudo tee /etc/systemd/system/mex-receiver.service.d/99-notify-herstel.conf >/dev/null <<'EOF'
# Tijdelijk herstel 29-09-2026 - D-116/D-118. Terugdraaien = dit bestand weg + daemon-reload.
[Service]
# 2A - alle kaarten naar een webhook; de per-firm routing eruit
Environment=NOTIFY_WEBHOOK_APEX=
Environment=NOTIFY_WEBHOOK_FUNDED=
Environment=NOTIFY_WEBHOOK_EVAL=
# 2B - geen kaart-rendering, dus geen demping en geen catch-zonder-fallback
Environment=MEX_RENDER_ENABLED=false
EOF
sudo systemctl daemon-reload
sudo systemctl restart mex-receiver
sleep 3
systemctl is-active mex-receiver
sudo bash /root/mex-discord-doctor.sh | sed -n '/=== 2/,/=== 4/p'
```

De laatste regel herleest de env van het **draaiende** proces, dus je ziet meteen of de drop-in
echt is aangekomen. Een drop-in wordt ná de unit gelezen, dus deze `Environment=`-regels
overschrijven wat er in de `EnvironmentFile` staat.

### Terugdraaien

```bash
sudo rm /etc/systemd/system/mex-receiver.service.d/99-notify-herstel.conf
sudo systemctl daemon-reload && sudo systemctl restart mex-receiver
```

---

## Verifiëren dat het werkt

1. Wacht op het volgende trade-event, of forceer er een op een chart die je toch al test.
2. Verwacht in Discord: **FILL** en **EXIT** als platte tekst in plaats van als kaart.
3. En controleer het journaal — hier mag geen `rate-limited`, `exception` of `401` meer staan:

```bash
grep -c 'rate-limited\|card exception\|error 401' \
  /root/intent-store/routed_$(date -u +%Y%m%d).jsonl
```

---

## Als §4 leeg was

Dan komt er niets aan en zit het aan de TradingView-kant. Stap 2 verandert daar niets aan. Kijk dan
in deze volgorde:

1. Staan er vandaag **trades op de chart**? Zo niet, dan is er niets te melden en is Discord
   onschuldig.
2. Staat er een **rood uitroepteken** op het script, of een fout in je alert-overzicht?
3. Staat de alert-conditie op **"Order fills and alert() function calls"**? Alle Discord-kaarten
   gaan via `alert()`, dus die moet aan staan.

---

## Wat dit runbook NIET oplost

Dit is een **noodmaatregel**, geen fix. Wat er structureel moet gebeuren staat op het bord:

- **D-116** — een gedempte of gefaalde kaart moet doorvallen naar het platte bericht in plaats van
  verdwijnen. Dan kan de rendering weer aan.
- **D-117** — kanaalsplitsing per tier, zodat 2A niet meer nodig is.
- **D-118** — de oorzaak zelf, en of de webhook geroteerd is (**D-11**).
- **D-119** — het fan-out-statusvenster, zodat dit de volgende keer zichtbaar is in plaats van
  gemeld door jou.
