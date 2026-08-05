# Middleware opzetten — stap-voor-stap (voor beginners)

Deze gids neemt je van niks naar een werkende, altijd-aan middleware op je eigen
server (VPS), met veilig HTTPS, persistente journaling en live feedback van je
brokers (Tradovate + PineConnector/MT5) over echte fills en slippage.

Je hoeft **geen** Linux-expert te zijn. Bijna alles gebeurt met één installatie-commando.

**Wat je aan het eind hebt:**
- Een server die 24/7 draait, ook als al je apparaten uitstaan.
- Webhook-URL voor TradingView: `https://middleware.pipsandpalmtrees.com/webhook`
- Een journal (sqlite) dat bewaard blijft: elk signaal, elke order, elke P&L-snapshot.
- Reconciliation: *intended* (TradingView) vs *actual* fills → slippage per venue.
- Een kill-switch om alles direct te stoppen.

**Belangrijkste veiligheidsregel:** de middleware staat standaard op `DRY_RUN=true`.
Hij bouwt en logt orders wél, maar stuurt ze **niet** echt door. Je zet 'm pas op
`false` als alles end-to-end getest is. Zo bouw je alles op met nul risico.

---

## Hoeveel tijd kost dit?

| Fase | Wat | Tijd |
|---|---|---|
| 1 | Account + VPS aanmaken | ~10 min |
| 2 | Termius installeren + verbinden | ~10 min |
| 3 | Domein (GoDaddy) A-record instellen | ~5 min (+ tot ~30 min wachten op DNS) |
| 4 | Repo clonen + `setup.sh` draaien | ~10 min |
| 5 | `.env` invullen met je tokens | ~15 min |
| 6 | Testen in DRY_RUN | ~10 min |
| 7 | Één account live zetten | ~10 min |

**Actief bezig: ~1 tot 1,5 uur.** Daar komt wat wachttijd bij voor DNS (het domein dat
"doorzet" over het internet — je kunt in de tussentijd gewoon doorwerken).

Als je vastloopt: elke stap hieronder heeft een "check" waarmee je ziet of het goed ging
voordat je verder gaat.

---

## Wat je vooraf nodig hebt

- [ ] Een creditcard of PayPal (voor de VPS, ~€5/maand).
- [ ] Je domein `pipsandpalmtrees.com` (heb je al, via GoDaddy).
- [ ] Je PickMyTrade-gegevens: `PMT_URL` + `PMT_TOKEN` (uit je PMT-dashboard).
- [ ] (Optioneel, voor live tracking) je Tradovate-login + API-gegevens.
- [ ] (Optioneel, voor reconciliation van MT5/FTMO) je MetaAPI-token.
- [ ] (Optioneel, voor LifeOS-dashboards) je Notion-integratietoken + database-id's.

De optionele dingen kun je later toevoegen — je kunt eerst gewoon de basis draaien.

---

## Fase 1 — De VPS aanmaken

Een VPS is een kleine Linux-computer die 24/7 in een datacenter draait. Je bereikt
'm op afstand vanaf elk apparaat. Voor jouw setup (op Curaçao, orders via TradingView
naar Amerikaanse brokers) kies je een **US-East** datacenter: dat zit dicht bij zowel
TradingView's webhook-servers als Tradovate/PickMyTrade.

### Aanrader

| | Keuze |
|---|---|
| Provider | **Hetzner Cloud** (goedkoop) of **DigitalOcean** (makkelijkst dashboard) |
| Locatie | **US-East** — Hetzner: *Ashburn (Virginia)* · DigitalOcean: *New York* |
| Type | Kleinste betaalde tier (bv. Hetzner CPX11 / CX22, of DO Basic $6) |
| OS | **Ubuntu 24.04 LTS** |

> Waarom niet dicht bij Curaçao? Omdat jouw huis niet in de signaalroute zit. De
> keten is TradingView → middleware → broker, allemaal Amerikaanse servers. Jij
> bereikt de VPS alleen af en toe om te beheren, en daar maakt de afstand niet uit.

### Stappen (DigitalOcean-voorbeeld — Hetzner is vrijwel identiek)

1. Maak een account op de provider en voeg een betaalmethode toe.
2. Klik **Create → Droplet** (Hetzner: **Add Server**).
3. Kies:
   - **Region / Location:** New York (DO) of Ashburn (Hetzner).
   - **Image / OS:** Ubuntu 24.04 (LTS).
   - **Size:** de kleinste betaalde optie (~$5–6/maand). Genoeg — de middleware is licht.
4. **Authentication:** kies **SSH Key** als je die al hebt; anders kies **Password**
   en verzin een sterk root-wachtwoord (schrijf het op). SSH-key is veiliger, maar
   met een wachtwoord kom je ook prima door deze gids heen.
5. Geef 'm een naam (bv. `pmt-middleware`) en klik **Create**.

Na ~1 minuut krijg je een **IP-adres**, bijvoorbeeld `203.0.113.45`. **Noteer dit** —
je hebt het straks twee keer nodig (Termius + GoDaddy).

**Check:** je ziet in het dashboard je server met status "Running" en een IP-adres.

---

## Fase 2 — Verbinden met Termius (iOS + Windows)

Je bedient de server via "SSH": een versleutelde terminalverbinding. **Termius** is
gratis, werkt op **iOS én Windows**, en synct je servers tussen je apparaten — je zet
'm één keer op en hebt 'm overal.

1. Installeer **Termius** (App Store op iPhone, of termius.com op Windows). Maak een
   gratis account zodat je apparaten synchroniseren.
2. Klik **New Host** en vul in:
   - **Address:** het IP-adres van je VPS (uit fase 1).
   - **Username:** `root`
   - **Password:** het root-wachtwoord dat je koos (of selecteer je SSH-key).
3. Sla op en klik op de host om te verbinden. De eerste keer vraagt 'ie om de
   "fingerprint" te vertrouwen → accepteer.

**Check:** je ziet een prompt zoals `root@pmt-middleware:~#`. Typ `whoami` + Enter →
het antwoord is `root`. Je zit nu op je server.

> Tip: comfortabeler typen doe je op je Windows-pc. Daarna kun je 'm gewoon vanaf je
> iPhone in Termius openen om te checken.

---

## Fase 3 — Domein koppelen (GoDaddy)

TradingView eist `https://`, en daarvoor heb je je domein nodig. Je gebruikt **één
subdomein** voor de middleware; de rest van `pipsandpalmtrees.com` (je website en
andere LifeOS-plannen) blijft gewoon vrij.

1. Log in op **GoDaddy** → **My Products** → bij `pipsandpalmtrees.com` klik **DNS**
   (of "Manage DNS").
2. Klik **Add** (nieuw record) en vul in:

   | Veld | Waarde |
   |---|---|
   | Type | **A** |
   | Name / Host | `middleware` |
   | Value / Points to | *het IP-adres van je VPS* |
   | TTL | 600 (of laat standaard staan) |

3. Opslaan.

Dit maakt `middleware.pipsandpalmtrees.com` wijzen naar je server. Je hoofddomein en
`www` raak je **niet** aan — die houd je vrij voor je website.

**Check (na een paar minuten tot ~30 min):** typ op je VPS in Termius:
```bash
dig +short middleware.pipsandpalmtrees.com
```
Zie je het IP-adres van je VPS terug? Dan is DNS doorgezet en kun je verder. Zo niet,
even wachten en opnieuw proberen (DNS heeft soms tijd nodig).

---

## Fase 4 — De middleware installeren (één commando)

Nu de kern. Je haalt de code op en draait het installatiescript. Dat installeert
Python + Caddy (voor automatisch HTTPS), bouwt de app, genereert je geheime sleutel,
installeert de app als service die vanzelf herstart, en zet HTTPS aan.

Voer op je VPS (in Termius) uit, regel voor regel:

```bash
# 1. Git installeren (als het er nog niet is)
apt-get update -y && apt-get install -y git

# 2. De repo clonen
git clone https://github.com/ferhen1981/tradingkit.git
cd tradingkit/middleware

# 3. Het installatiescript draaien met JOUW subdomein
sudo bash deploy/setup.sh middleware.pipsandpalmtrees.com
```

Het script print aan het eind onder andere **je automatisch gegenereerde
`MIDDLEWARE_SECRET`**. **Kopieer en bewaar die** — je hebt 'm nodig in TradingView en
voor de kill-switch.

**Check:** open in je browser `https://middleware.pipsandpalmtrees.com/health`.
Zie je een OK-antwoord (en een geldig slotje/HTTPS)? Dan draait de app met HTTPS.

> Duurt HTTPS even? Caddy haalt bij de eerste keer automatisch een gratis
> Let's Encrypt-certificaat op. Dat kan een halve minuut duren en werkt alleen als je
> DNS uit fase 3 al is doorgezet.

---

## Fase 5 — Je tokens invullen in `.env`

Het script maakte een `.env`-bestand aan met veilige standaardwaarden
(`DRY_RUN=true`, en een gegenereerd secret). Nu vul je je eigen gegevens in.

Open het bestand in Termius met een simpele editor:
```bash
cd ~/tradingkit/middleware
nano .env
```
In `nano`: pijltjestoetsen om te bewegen, typen om te bewerken, **Ctrl+O** + Enter om
op te slaan, **Ctrl+X** om te sluiten.

### Minimaal nodig om te starten (execution via PickMyTrade)

```ini
DRY_RUN=true            # LAAT DIT OP TRUE tot je alles getest hebt
PMT_URL=...             # je PickMyTrade webhook-URL (uit je PMT-dashboard)
PMT_TOKEN=...           # je PickMyTrade API-token
```

### Je accounts koppelen

De middleware moet weten welke accounts onder welke strategie vallen. Kopieer het
voorbeeld en pas het aan:
```bash
cp accounts.example.yaml accounts.yaml
nano accounts.yaml
```
Zet onder `strategies:` je strategieën (`GC`, `ES`) met de accountnamen eronder, en
onder `accounts:` de echte account-id's. Zie de commentaarregels in het bestand — die
leggen elk veld uit (broker, token, `account_id`, `quantity_multiplier`,
`max_entries_per_day`, enz.). `accounts.yaml` is git-ignored, dus je zet er veilig
echte gegevens in.

### Live tracking van Tradovate (echte P&L in je journal)

Wil je dat de server je echte P&L ophaalt (voor `/performance` en de LifeOS Fleet-
dashboard), vul dan ook in:
```ini
TRADOVATE_BASE=https://live.tradovateapi.com/v1   # demo: https://demo.tradovateapi.com/v1
TRADOVATE_NAME=...        # je Tradovate-gebruikersnaam
TRADOVATE_PASSWORD=...    # je Tradovate-wachtwoord
TRADOVATE_APPID=...       # API key / app id (uit Tradovate API Access)
TRADOVATE_CID=...         # API cid (indien uitgegeven)
TRADOVATE_SEC=...         # API secret (indien uitgegeven)
```
> Geen API-gegevens bij de hand? Zet tijdelijk `TRADOVATE_MOCK=true` om de tracker met
> nepdata te draaien en de flow te zien, zonder echte credentials.

### Reconciliation — echte fills & slippage (Phase 6)

Dit is precies waar het jou om gaat: *intended* (TradingView) vs *actual* fills →
slippage in ticks/pips per venue.
```ini
# MT5 / FTMO fills via MetaAPI (voor de PineConnector-kant)
METAAPI_TOKEN=...         # metaapi.cloud auth-token
METAAPI_ACCOUNT_ID=...    # je MT5 account-id in MetaAPI
METAAPI_BASE=https://mt-client-api-v1.new-york.agiliumtrade.ai   # jouw MetaAPI-regio
```
De Tradovate-kant van de reconciliation gebruikt de `TRADOVATE_*` gegevens hierboven.
> Om eerst de flow te zien zonder token: `METAAPI_MOCK=true`.

### (Optioneel) LifeOS / Notion-dashboards

```ini
NOTION_TOKEN=...          # Notion integratie-token (deel de database met de integratie)
NOTION_DB_ID=...          # Fleet Performance database-id
NOTION_JOURNAL_DB=...     # Trade Journal database-id (optioneel)
NOTION_RECON_DB=...       # Reconciliation database-id (optioneel)
```

Sla op (Ctrl+O, Enter, Ctrl+X) en herstart de service zodat de nieuwe waarden laden:
```bash
sudo systemctl restart mex-middleware
```

**Check:** `curl https://middleware.pipsandpalmtrees.com/health` geeft weer OK.

---

## Fase 6 — Testen in DRY_RUN (nul risico)

Nu bewijs je dat alles werkt, zonder één echte order te versturen. Vervang
`JOUW_SECRET` door je `MIDDLEWARE_SECRET`.

Stuur een testsignaal — dit is exact wat TradingView straks stuurt:
```bash
curl -s https://middleware.pipsandpalmtrees.com/webhook \
  -H 'content-type: application/json' -d '{
  "secret":"JOUW_SECRET","strategy":"GC","event":"ENTRY","action":"buy",
  "symbol":"GC1!","price":2650.5,"order_type":"LMT","dollar_sl":100,"dollar_tp":250,"qty":1
}'
```
Je hoort per gekoppeld account een gebouwde order terug te zien met
`"status":"dry_run"`. Dat betekent: correct opgebouwd, maar **niet** verstuurd.

Bekijk je journal (het bewijslogboek dat bewaard blijft):
```bash
curl -s "https://middleware.pipsandpalmtrees.com/journal?secret=JOUW_SECRET&limit=5"
```
Je ziet het binnengekomen signaal én de dry-run-dispatches. Dit is Phase 0+1 bewezen.

**Check:** zie je je testorder terug in het journal met `dry_run`? Dan werkt de hele
keten TradingView-vorm → middleware → (klaar-om-te-versturen) order.

---

## Fase 7 — TradingView koppelen & voorzichtig live

1. **Koppel TradingView.** Zet in je "→ Middleware" alert als webhook-URL:
   ```
   https://middleware.pipsandpalmtrees.com/webhook
   ```
   en als bericht de lean JSON (strategy/action/symbol/price/dollar_sl/dollar_tp/qty +
   `secret`). Laat `DRY_RUN` nog op `true` en kijk een tijdje mee in het journal of de
   echte alerts netjes binnenkomen en correct worden opgebouwd.

2. **Test op ÉÉN demo/eval-account eerst.** Zorg dat er in `accounts.yaml` maar één
   (veilig) account gekoppeld is voor deze eerste live-test.

3. **Ga live.** Zet in `.env` `DRY_RUN=false`, herstart, en vuur één signaal af:
   ```bash
   nano .env       # DRY_RUN=false
   sudo systemctl restart mex-middleware
   ```
   Controleer de order in Tradovate. Klopt alles? Dan kun je stap voor stap meer
   accounts koppelen.

---

## Beheer & veiligheid — de commando's die je nodig hebt

**Kill-switch — stopt ALLE dispatch onmiddellijk:**
```bash
curl -X POST "https://middleware.pipsandpalmtrees.com/killswitch?secret=JOUW_SECRET&armed=false"
# weer aanzetten: ...&armed=true
```

**Service beheren (systemd):**
```bash
sudo systemctl status mex-middleware     # draait 'ie?
sudo systemctl restart mex-middleware    # herstart (na .env-wijziging)
sudo systemctl stop mex-middleware       # stoppen
journalctl -u mex-middleware -f          # live logs meekijken
```

**Code updaten (nieuwe versie ophalen):**
```bash
cd ~/tradingkit && git pull
cd middleware && .venv/bin/pip install -r requirements.txt
sudo systemctl restart mex-middleware
```

**Handige endpoints** (met `?secret=JOUW_SECRET`):
- `/health` — draait de app?
- `/journal?secret=...&limit=20` — laatste events (signalen + dispatches).
- `/performance?secret=...` — live P&L (als Tradovate-tracking aan staat).
- `/risk` en `/halt` — de per-account risk-overlay (dagelijkse entry-cap / halt).

---

## Snelle probleemoplossing

| Symptoom | Waarschijnlijke oorzaak | Oplossing |
|---|---|---|
| `/health` laadt niet / geen HTTPS | DNS nog niet doorgezet of poort dicht | `dig +short middleware.pipsandpalmtrees.com` moet je VPS-IP tonen; even wachten |
| Certificaat-fout in browser | Caddy kon nog geen certificaat halen | wacht ~1 min; check `journalctl -u caddy -f`; DNS moet eerst goed staan |
| Signaal geweigerd / geen dispatch | verkeerd `secret` of `DRY_RUN`/kill-switch | check dat je `secret` klopt en de kill-switch `armed=true` is |
| Geen P&L in `/performance` | `TRADOVATE_*` niet ingevuld | vul credentials in, of test met `TRADOVATE_MOCK=true` |
| Order niet in Tradovate na live | nog in DRY_RUN, of PMT-token fout | `DRY_RUN=false`, `PMT_URL`/`PMT_TOKEN` checken, service herstarten |

---

## Samengevat

1. VPS: **US-East, Ubuntu 24.04**, kleinste tier.
2. Verbinden via **Termius** (iOS + Windows).
3. GoDaddy: **A-record** `middleware` → VPS-IP.
4. `git clone` + `sudo bash deploy/setup.sh middleware.pipsandpalmtrees.com`.
5. `.env` + `accounts.yaml` invullen (`DRY_RUN=true` laten).
6. Testen in DRY_RUN via `/webhook` en `/journal`.
7. Eén account live: `DRY_RUN=false`, herstart, order in Tradovate checken.

Bewaar je `MIDDLEWARE_SECRET` goed en houd `DRY_RUN=true` tot je zeker bent. Veel succes!
