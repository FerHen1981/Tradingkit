# Fase C — Signaal-endpoint livegang (mw.mex-traders.com)

## Vooraf (jij, kan parallel)
1. **GoDaddy DNS**: A-record `mw` → 167.233.215.60
2. **Hetzner firewall**: inbound TCP 443 én 80 open (0.0.0.0/0)
3. Check: `nslookup mw.mex-traders.com` geeft 167.233.215.60

## Op de server
```bash
# 1. Code binnenhalen (via de zip, uitgepakt in ~/mex-middleware-b)
cd ~/mex-middleware-b
sed -i 's|net8.0|net10.0|' src/Mex.Journal.Receiver/Mex.Journal.Receiver.csproj
dotnet publish src/Mex.Journal.Receiver -c Release

# 2. Caddy installeren (regelt TLS automatisch)
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install -y caddy

# 3. Caddyfile plaatsen
cp src/Mex.Journal.Receiver/Caddyfile /etc/caddy/Caddyfile
systemctl reload caddy    # Caddy haalt nu automatisch het TLS-cert op

# 4. Eigen geheim kiezen en het endpoint als service draaien
SECRET=$(openssl rand -hex 16); echo "JOUW TOKEN: $SECRET"   # bewaar dit!
sed -i "s|VERVANG_DIT_DOOR_EIGEN_GEHEIM|$SECRET|" src/Mex.Journal.Receiver/mex-receiver.service
sed -i "s|VERVANG_DOOR_DISCORD_WEBHOOK_URL|$MEX_DISCORD_WEBHOOK|" src/Mex.Journal.Receiver/mex-receiver.service
cp src/Mex.Journal.Receiver/mex-receiver.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now mex-receiver

# 5. Test
curl https://mw.mex-traders.com/health          # -> {"status":"alive",...}
curl -X POST https://mw.mex-traders.com/signal/$SECRET \
  -H 'Content-Type: application/json' \
  -d '{"account":"PAAPEX2700250000015","symbol":"MES1!","action":"BUY","price":5900.25}'
# -> {"stored":true,...} + een bericht in Discord
```

## In TradingView (bij de v7.0-FM alert-uitrol)
Webhook-URL van de alert: `https://mw.mex-traders.com/signal/JOUW_TOKEN`
Deze komt NAAST de PMT-webhook — één alert, twee bestemmingen. PMT blijft executeren.

## Dry-run
Laat het endpoint een paar sessies MEELUISTEREN terwijl PMT gewoon draait.
Controleer ~/intent-store/intents_YYYYMMDD.jsonl vult zich. Pas als dat klopt,
bouwen we de reconciliatie intent<->fill en de journal-verrijking met MFE/MAE (volgende stap).
