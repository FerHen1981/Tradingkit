# Mex.Journal.Receiver — Fase D (de trechter)

Vervangt `src/Mex.Journal.Receiver/Program.cs` op de VPS. **Fase C-gedrag blijft
exact intact**: onbekende/eigen payloads worden nog steeds als intent opgeslagen
en via `DiscordNotifier` gemeld. Nieuw is dat het endpoint per bericht herkent
wat het is en het naar de juiste bestemming stuurt.

| Binnenkomend | Herkenning | Actie |
|---|---|---|
| PMT-JSON | `multiple_accounts` of (`token` + `data`) | POST naar `MEX_PMT_URL` (of `MEX_PMT_RITHMIC_URL` als het account in `MEX_PMT_RITHMIC_ACCOUNTS` staat) |
| Discord-embed | `embeds` of `content` | Tier A/B → PNG-kaart als bijlage; Tier C → 1:1 POST |
| Journal | `{"type":"journal"}` / `csv` / CSV-regel | alleen opslaan |
| PineConnector | `<license>,buy\|sell\|exit,<symbol>,…` | POST naar `MEX_PC_URL` |
| overig | — | Fase C: intent + Discord-melding |

Extra's: idempotency-dedupe (5s op body-hash), kill-switch (`POST /killswitch?token=…&armed=false`,
exits nooit geblokkeerd), append-only audit in `routed_<datum>.jsonl`, retries op
netwerk/5xx (niet op 4xx).

## Kaarten (Discord als afbeelding)

Discord-berichten van Tier A/B (zie `../CARDS.md`) worden door
`renderer/render-signal.js` tot een PNG gerenderd en als bijlage gepost;
Tier C (ACCOUNT STARTED, LIMIT EXPIRED) blijft tekst. De renderer leest de
Pine-payload zelf: titel → event, description → velden.

`SIGNAL BLOCKED` valt onder geen van beide: dat beslist `BlockedGate`. Alleen een
blokkade die de handelsdag of het account beëindigt (`Day halt: …`, `Account: …`,
breach, eval passed) wordt een kaart, en dan één keer per symbool per categorie per
handelsdag. Routineblokkades en herhalingen gaan niet naar Discord maar staan wel in
`routed_<datum>.jsonl` als `blocked-notice suppressed`.

Renderen duurt seconden, dus het gebeurt ná het antwoord aan TradingView
(achtergrondtaak, max 2 Chromium-processen tegelijk). Mislukt het renderen —
node weg, timeout, Chromium stuk — dan gaat het **originele tekstbericht**
alsnog naar Discord. Een alert kan dus niet verdwijnen door een render-probleem.
Staat het script niet op `MEX_RENDER_SCRIPT`, dan blijft alles tekst.

## Env

    MEX_WEBHOOK_SECRET=...        # bestaand
    MEX_DISCORD_WEBHOOK=...       # bestaand
    MEX_PMT_URL=https://api.pickmytrade.trade/v2/add-trade-data-latest?t=1162
    MEX_PMT_RITHMIC_URL=          # alleen als je die route gebruikt
    MEX_PMT_RITHMIC_ACCOUNTS=     # kommalijst account-id's op Rithmic
    MEX_PC_URL=                   # PineConnector-webhook (FTMO/MT5)
    MEX_DRY_RUN=true              # NIETS wordt doorgestuurd tot dit false is

    # kaarten
    MEX_RENDER_SCRIPT=/root/mex-renderer/render-signal.js
    MEX_RENDER_ENABLED=           # 'false' zet kaarten uit (default: aan als het script bestaat)
    MEX_NODE=node                 # of /usr/bin/node
    MEX_RENDER_OUT_DIR=/tmp/mex-cards
    MEX_RENDER_TIMEOUT_MS=30000
    MEX_RENDER_KEEP=              # 'true' = PNG's niet opruimen (debuggen)
    MEX_CHROMIUM_PATH=            # vaste Chromium-binary voor Playwright
    MEX_CARD_TIER_OVERRIDES=      # bv. "AUTO FLAT=B,EXIT=C" — tier is data, geen code

## Uitrollen

Twee losse onderdelen. De renderer is een los bestand dat per bericht wordt aangeroepen,
dus die heeft géén herstart nodig — het volgende event pakt de nieuwe versie.

    RAW=https://raw.githubusercontent.com/FerHen1981/Tradingkit/claude/legacy-accounts-scripts-analysis-ui0j6m/middleware

    # 1 — renderer (geen herstart nodig)
    cp /root/mex-renderer/render-signal.js /root/mex-renderer/render-signal.js.bak
    curl -fsSL -o /root/mex-renderer/render-signal.js $RAW/renderer/render-signal.js

    # 2 — receiver
    cd /root/mex-middleware-b
    cp src/Mex.Journal.Receiver/Program.cs src/Mex.Journal.Receiver/Program.cs.bak
    curl -fsSL -o src/Mex.Journal.Receiver/Program.cs $RAW/dotnet-receiver/Program.cs
    dotnet build -c Release
    systemctl restart mex-receiver
    curl -s localhost:PORT/health        # renderEnabled + renderScript moeten kloppen

Rooktest zonder op een echte trade te wachten — post een nagebootst Pine-bericht:

    H='content-type: application/json'
    U="https://<host>/signal/$MEX_WEBHOOK_SECRET"
    curl -s -X POST "$U" -H "$H" -d '{"embeds":[{"title":"⚙️ MGC1! CONFIG","description":"ver=v6.9.2;acct=TEST;qty=4","footer":{"text":"MGC1!"}}]}'
    # -> {"accepted":true,"kind":"discord","tier":"B","card":"queued"}

    curl -s -X POST "$U" -H "$H" -d '{"embeds":[{"title":"⛔ MGC1! SIGNAL BLOCKED","description":"Long setup ... blocked by: Day halt: PA Daily Loss Limit","footer":{"text":"MGC1!"}}]}'
    # -> tier B, card queued   (de eerste terminale blokkade van vandaag)
    sleep 6   # body-hash-dedupe is 5s; anders meet je die i.p.v. de poort
    # ...zelfde commando nogmaals -> {"accepted":true,"kind":"discord","suppressed":true}

    curl -s -X POST "$U" -H "$H" -d '{"embeds":[{"title":"⛔ MGC1! SIGNAL BLOCKED","description":"Long setup ... blocked by: Stop invalid","footer":{"text":"MGC1!"}}]}'
    # -> suppressed (routineblokkade, komt nooit door)

Let op: met `MEX_DRY_RUN=true` wordt er niets gepost — de kaart rendert wel en het
resultaat staat in het journaal, maar Discord ziet niets.

Terug bij problemen: `cp Program.cs.bak Program.cs && dotnet build -c Release && systemctl restart mex-receiver`
(en `cp render-signal.js.bak render-signal.js` voor de renderer).
