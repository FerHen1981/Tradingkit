# Mex.Journal.Receiver — Fase D (de trechter)

Vervangt `src/Mex.Journal.Receiver/Program.cs` op de VPS. **Fase C-gedrag blijft
exact intact**: onbekende/eigen payloads worden nog steeds als intent opgeslagen
en via `DiscordNotifier` gemeld. Nieuw is dat het endpoint per bericht herkent
wat het is en het naar de juiste bestemming stuurt.

| Binnenkomend | Herkenning | Actie |
|---|---|---|
| PMT-JSON | `multiple_accounts` of (`token` + `data`) | POST naar `MEX_PMT_URL` (of `MEX_PMT_RITHMIC_URL` als het account in `MEX_PMT_RITHMIC_ACCOUNTS` staat) |
| Discord-embed | `embeds` of `content` | 1:1 POST naar de Discord-webhook |
| Journal | `{"type":"journal"}` / `csv` / CSV-regel | alleen opslaan |
| PineConnector | `<license>,buy\|sell\|exit,<symbol>,…` | POST naar `MEX_PC_URL` |
| overig | — | Fase C: intent + Discord-melding |

Extra's: idempotency-dedupe (5s op body-hash), kill-switch (`POST /killswitch?token=…&armed=false`,
exits nooit geblokkeerd), append-only audit in `routed_<datum>.jsonl`, retries op
netwerk/5xx (niet op 4xx).

## Env

    MEX_WEBHOOK_SECRET=...        # bestaand
    MEX_DISCORD_WEBHOOK=...       # bestaand
    MEX_PMT_URL=https://api.pickmytrade.trade/v2/add-trade-data-latest?t=1162
    MEX_PMT_RITHMIC_URL=          # alleen als je die route gebruikt
    MEX_PMT_RITHMIC_ACCOUNTS=     # kommalijst account-id's op Rithmic
    MEX_PC_URL=                   # PineConnector-webhook (FTMO/MT5)
    MEX_DRY_RUN=true              # NIETS wordt doorgestuurd tot dit false is

## Uitrollen

    cd /root/mex-middleware-b
    cp src/Mex.Journal.Receiver/Program.cs src/Mex.Journal.Receiver/Program.cs.bak
    # nieuwe Program.cs plaatsen
    dotnet build -c Release
    systemctl restart mex-receiver
    curl -s localhost:PORT/health

Terug bij problemen: `cp Program.cs.bak Program.cs && dotnet build -c Release && systemctl restart mex-receiver`.
