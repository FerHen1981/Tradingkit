# Secrets roteren en onderhouden — werkinstructie

> Naast `SECRETS-REGISTER.md`, dat *bijhoudt welke secrets bestaan*. Dit bestand
> beschrijft *hoe je ze vervangt zonder de executie te breken*, en hoe je het bijhoudt.
> **Hier staan geen waarden.** Ook niet tijdelijk, ook niet in een voorbeeld.

## 1. Waarom dit niet één handeling is

Een secret in dit systeem kan op **vier** plekken tegelijk leven. Wie er één vergeet,
breekt de executie of laat het lek openstaan:

| Plek | Wat er staat | Bijwerken hoe |
|---|---|---|
| `middleware/.env` op de VPS | vrijwel alle server-side secrets | tekstbestand + `systemctl restart` |
| **De TradingView-alert zelf** | `PMT Token`, `Middleware secret` — die zitten **in de alert-JSON** | per alert handmatig, in TradingView |
| **Logbestanden** | `/root/intent-store/routed_*.jsonl` draagt de PMT-token in élke orderregel; de webhook-URL draagt het middleware-secret in het **pad** | opruimen of accepteren, zie §6 |
| Kluis (Bitwarden/1Password) | de administratie | handmatig |

De tweede rij is de gevaarlijke. Een server-secret roteer je in twee minuten; een
**alert-gedragen** secret vraagt dat je élke actieve alert aanpast, en tussen de restart en
de laatste alert vallen signalen weg.

## 2. Inventaris naar risicoklasse

**Klasse A — server-side, veilig te roteren, geen alerts raken**
`NOTION_TOKEN` · `NOTIFY_WEBHOOK` (Discord) · `VIEWER_PASSWORD` · `VIEWER_API_TOKEN` ·
`TRADOVATE_*` · `METAAPI_TOKEN` · `METAAPI_ACCOUNT_ID`

**Klasse B — zit óók in TradingView-alerts, rotatie kost een venster**
`MEX_WEBHOOK_SECRET` / `MIDDLEWARE_SECRET` (staat in het URL-pad `/signal/<secret>`) ·
`PMT_TOKEN` (staat in de payload van élke order-alert, twee keer: op hoofdniveau en in
`multiple_accounts[]`)

**Klasse C — bij een derde partij, niet door jou te genereren**
PickMyTrade-account · Tradovate-login · Apex-portaal · GitHub · Notion-workspace.
Hier roteer je een **wachtwoord**, en zet je waar mogelijk 2FA aan.

## 3. Rotatie — klasse A (de gewone gevallen)

Doe er één tegelijk. Nooit vier in één keer: als er iets breekt wil je weten wat.

```bash
# 1. nieuwe waarde maken (voorbeeld voor een willekeurig token)
openssl rand -hex 32

# 2. bij de uitgever de nieuwe waarde aanmaken
#    Notion  -> Settings > Connections > integratie > Rotate token
#    Discord -> Server Settings > Integrations > Webhooks > Reset webhook URL
#    Viewer  -> zelfgekozen, min. 24 tekens

# 3. .env bijwerken — NOOIT met een editor die een .swp/.bak achterlaat
sudo nano /root/mex-journal/middleware/.env

# 4. alleen de diensten herstarten die deze secret lezen
sudo systemctl restart mex-viewer            # VIEWER_PASSWORD, VIEWER_API_TOKEN
sudo systemctl restart mex-receiver          # NOTIFY_WEBHOOK
#   NOTION_TOKEN wordt door timer-diensten gelezen: die pakken hem vanzelf op
#   bij de volgende ronde (oneshot). Forceren mag:
sudo systemctl start mex-routed-journal mex-journal-sync

# 5. verifiëren
sudo journalctl -u mex-viewer -u mex-receiver -n 100 --no-pager | grep -Ei "401|403|unauthor|token"
```

Daarna pas de **oude** waarde bij de uitgever intrekken. Houd 24 uur allebei geldig waar
dat kan; bij Discord en Notion kan dat niet — die vervangen direct.

## 4. Rotatie — klasse B (met een executievenster)

Dit is de enige rotatie die je **plant**, niet tussendoor doet. Kies een moment dat de
markt dicht is: **vrijdag na 17:00 ET tot zondag 18:00 ET**. Daarbuiten verlies je orders.

### `MEX_WEBHOOK_SECRET` (het pad `/signal/<secret>`)

1. Nieuwe waarde: `openssl rand -hex 32`.
2. **Eerst** `.env` bijwerken en `sudo systemctl restart mex-receiver`.
   → vanaf dit moment weigert de receiver de oude URL: alle alerts staan stil.
3. In TradingView **elke** alert openen en de webhook-URL vervangen. Loop de lijst af op
   `Alerts` → sorteer op naam; er is geen bulk-edit, dus turf ze.
4. Eén testalert handmatig vuren en in de log bevestigen dat hij binnenkomt.

> Kan de receiver twee secrets tegelijk accepteren, dan is er geen venster nodig: zet de
> nieuwe erbij, werk de alerts bij, haal de oude weg. **Vraag Legacy of `Program.cs` een
> tweede geldig secret aankan** — dat is een kleine wijziging die deze rotatie voorgoed
> pijnloos maakt, en hij hoort thuis in dezelfde build als het andere receiverwerk.

### `PMT_TOKEN`

1. Nieuw token aanmaken in PickMyTrade.
2. In TradingView per script het veld **PMT Token** (groep 9 · EXECUTION) vervangen —
   dat is een *script-input*, dus je doet het op de chart, en daarna moet **elke alert van
   dat script opnieuw worden opgeslagen** om de nieuwe payload te dragen.
3. `.env` bijwerken (`PMT_TOKEN`) en `sudo systemctl restart mex-receiver`.
4. Oud token in PickMyTrade intrekken.

Let op de volgorde: de alert draagt het token, niet de server. Trek je het oude token
eerst in, dan worden alle openstaande alerts geweigerd terwijl je nog aan het bijwerken bent.

## 5. Verificatie na élke rotatie

```bash
# geen auth-fouten
sudo journalctl -u mex-viewer -u mex-receiver -u mex-reconcile -n 200 --no-pager \
  | grep -Ei "401|403|unauthor|invalid token|forbidden"

# de receiver ontvangt nog
tail -3 /root/intent-store/routed_$(date -u +%Y%m%d).jsonl

# de viewer antwoordt
curl -s -o /dev/null -w "%{http_code}\n" https://app.mex-traders.com/healthz
```

Een lege `routed_*.jsonl` na een rotatie op een handelsdag betekent dat er alerts niet
meer binnenkomen — dat is het signaal om terug te vallen op de oude waarde.

## 6. Wat je niet kunt roteren: de logs

`/root/intent-store/routed_*.jsonl` bevat het **PMT-token in platte tekst** in elke
`kind:"pmt"`-regel, en de receiver-journaal bevat het **middleware-secret in het URL-pad**.
Rotatie maakt die oude regels onschadelijk, maar zolang je niet roteert zijn die bestanden
zelf een secret.

Praktisch:
- Behandel `/root/intent-store/` en `journalctl`-uitvoer als vertrouwelijk. **Plak ze niet
  in een chat, ticket of document** zonder de tokenvelden te verwijderen.
- Ruim oud materiaal op: `find /root/intent-store -name 'routed_*.jsonl' -mtime +90 -delete`
  (pas de termijn aan op wat je voor reconciliatie nodig hebt).
- Vraag Legacy of de receiver het tokenveld kan maskeren vóór het loggen. Dat is één regel
  en het haalt deze hele categorie weg.

## 7. Onderhoud — het ritme

| Wanneer | Wat |
|---|---|
| **Bij elk vermoeden van een lek** | direct roteren, dezelfde dag. Geen afweging. |
| **Elk kwartaal** | klasse A volledig roteren; duurt een half uur |
| **Twee keer per jaar** | klasse B, in een marktvrij weekend |
| **Maandelijks** | `SECRETS-REGISTER.md` doorlopen: klopt de lijst nog, staat elke secret in de kluis, is er niets bijgekomen dat er niet in staat |
| **Bij elke nieuwe integratie** | eerst een regel in het register, dan pas de secret aanmaken |

**Wat telt als een lek:** de waarde is in een chat, transcript, screenshot, e-mail, ticket,
commit of gedeeld document beland — ook als dat "maar even" was en ook als het jouw eigen
omgeving was. Een secret die je hebt gezien buiten de kluis en de `.env`, is verbrand.

## 8. Als er iets lekt — volgorde

1. **Roteer eerst, onderzoek daarna.** De vraag "hoe erg is het" kost tijd die je niet hebt.
2. Bepaal de klasse (§2) en volg de bijbehorende procedure.
3. Kijk terug in de logs of de oude waarde gebruikt is door iemand anders:
   `sudo journalctl -u mex-receiver --since "-7 days" | grep -c "signal/"` — een sprong in
   het aantal requests, of requests buiten handelsuren, is het signaal.
4. Zet een regel in `SECRETS-REGISTER.md`: wat, wanneer, hoe geroteerd.

## 9. Bekend openstaand (25-08)

Deze zijn langs chats, transcripten of exports gekomen en staan op de rotatielijst:

| Secret | Hoe gelekt |
|---|---|
| `MEX_WEBHOOK_SECRET` | in het URL-pad in receiver-logs die in een chat zijn geplakt |
| `PMT_TOKEN` | in een TradingView-export en in `routed_*.jsonl`-regels in een chat |
| `NOTIFY_WEBHOOK` / `MEX_DISCORD_WEBHOOK` | `systemctl cat`-uitvoer in een chat |
| `NOTION_TOKEN` | `export $(grep …)`-uitvoer in een chat |
| `VIEWER_API_TOKEN` | in een `/api/state?token=…`-voorbeeld |
| `VIEWER_PASSWORD` | sessie-transcript |

Volgorde: eerst `MEX_WEBHOOK_SECRET` en `PMT_TOKEN` (klasse B, dus in een marktvrij
venster), daarna de vier uit klasse A op een willekeurige avond.
