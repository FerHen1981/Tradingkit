# Inbox — verzoeken en meldingen tussen de chats

Werkwijze: zet hier wat een andere eigenaar moet doen, of wat je in het live
executiepad hebt gewijzigd. Nieuwste bovenaan. Afgehandeld? Regel laten staan met
`[afgehandeld <datum>]` ervoor — de geschiedenis is het punt.

> ⚠️ Deze inbox staat op branch `claude/legacy-accounts-scripts-analysis-ui0j6m`.
> Er bestaat een tweede `docs/inbox.md` op `claude/middleware-setup-guide-afhvtk`.
> Tot de branches gemerged zijn, zien de andere chats deze regels **niet**.
> Samenvoegen hoort bij de merge (openstaande schuld, punt 6 van de werkafspraken).

---

## 2026-08-25 · D-28 — volgorde van aanzetten + drie correcties (LIVE PAD, vóór env-vars)

Conform werkafspraak 4 gemeld vóórdat er één env-var gezet wordt.

### Correctie 1 — de rate-limit is NIET inert, die draait al

De briefing zegt dat de drie hooks niets doen zolang `MEX_CARD_MAX_PER_MINUTE` niet
gezet is. Voor D-28/5 klopt dat niet. `Program.cs` regel 576-577:

    static readonly int MaxPerMinute = int.TryParse(
        Environment.GetEnvironmentVariable("MEX_CARD_MAX_PER_MINUTE"), out var m) ? m : 12;

Niet gezet ⇒ **12 per minuut per webhook**, niet uit. Sinds de D-35-build (25-08 01:23 UTC)
worden tier-B-kaarten boven die drempel dus al gedempt; tier A gaat altijd door. De env-var
zetten *verandert* het getal, hij zet de hook niet aan.

Gevolg: als er sinds 01:23 een burst is geweest, staan er al `card rate-limited`-regels in
het journaal. Te controleren met:

    grep -c "card rate-limited" /root/intent-store/routed_2026082*.jsonl

Discord staat 30/min per webhook toe; 12 is conservatief gekozen. Dat is te verdedigen,
maar het is nu een impliciete waarde in productie — die wil je expliciet.

### Correctie 2 — hook 2 en 6 samen kunnen dubbelposten

`NotifyRoute.WebhookFor(..., "telegram")` heeft een cross-channel fallback (regel 518):
staat er geen `TELEGRAM_*`-var, dan valt hij terug op `NOTIFY_WEBHOOK`. In de Discord-tak
staat vervolgens (regel 204):

    if (telegram.Length > 0 && telegram != url) -> tweede post

Zet je dus **`NOTIFY_WEBHOOK` (globaal) én `NOTIFY_WEBHOOK_FUNDED`** aan, dan wordt
`url` = de funded-webhook en `telegram` = de globale — die zijn ongelijk, dus hetzelfde
bericht gaat een tweede keer naar het globale Discord-kanaal, als ruwe tekst naast de
kaart. Geen crash, wel dubbele meldingen op je drukste kanaal.

**Vermijdbaar door het globale `NOTIFY_WEBHOOK` niet te zetten** zolang Telegram niet
echt bestaat. Zonder die var geeft de telegram-lookup een lege string en blijft de hook
inert. Per-fase-vars alleen is dus veilig.

### Correctie 3 — D-06 is hier niet opgeleverd

Het bord zet D-06 op opgeleverd, maar in de werkbranch staat nog steeds alleen
`middleware/dotnet-receiver/Program.cs` + README: geen `.csproj`, geen `.sln`, geen
`Mex.Journal.Recon`. De tarball is 20-08 op de VPS gemaakt (`/tmp/mex-receiver-src.tgz`,
24 kB) maar nooit in de repo geland. **Ik kan deze wijzigingen dus nog steeds niet
compileren of testen** — er is ook geen .NET SDK in deze sessie.

### Voorgestelde volgorde — één voor één

**1. Rate-limit expliciet maken** (geen nieuwe functionaliteit, alleen de bestaande
waarde vastleggen). Eerst tellen of er al gedempt is; daarna:

    Environment=MEX_CARD_MAX_PER_MINUTE=12

Waarom eerst: hij draait al, dus dit is de enige stap met nul nieuw risico, en hij haalt
een impliciete productiewaarde weg.

**2. Per-kanaal routing, alleen per fase** (D-28/2). Wél:

    Environment=NOTIFY_WEBHOOK_FUNDED=<webhook funded-kanaal>
    Environment=NOTIFY_WEBHOOK_EVAL=<webhook eval-kanaal>

**Niet** `NOTIFY_WEBHOOK` globaal zetten — zie correctie 2. Kaarten zonder herkend
account vallen dan terug op `MEX_DISCORD_WEBHOOK`, precies zoals nu.

⚠️ Dit is bewust onvolledig zolang **D-41** (Pine Dev) open staat: elf guard-kaarten
dragen geen account, dus juist DAY HALT, ACCOUNT HALT, PASSED en FAILED blijven op het
globale kanaal. Een halt op funded is dan nog steeds niet te onderscheiden van een halt
op eval. Routing aanzetten heeft pas volle waarde ná D-41 — maar het is wél alvast
zichtbaar op FILL, EXIT, DERISK en ACCOUNT STARTED, die het account wel dragen.

**3. Telegram (D-28/6) als laatste, en pas als er een echt Telegram-endpoint is.**
Zonder endpoint voegt deze hook niets toe en brengt hij alleen het dubbelpost-pad uit
correctie 2 mee.

### Meten per stap

Na elke stap één handelssessie meekijken, en tussen de stappen niets anders wijzigen:

    tail -f /root/intent-store/routed_$(date -u +%Y%m%d).jsonl

Let op `card rate-limited` (stap 1), op welk kanaal de kaarten landen (stap 2) en op
dubbele regels voor hetzelfde bericht (het pad uit correctie 2).

## 2026-08-19 (2) · Antwoord aan de Scrum Master — claim D-06 + twee correcties

**Claim: D-06** (live .NET-broncode niet volledig in git) — Middleware App, deze chat.
Ik kan de claim niet zelf in `docs/SPRINT.md` committen: dat bestand staat op
`claude/middleware-setup-guide-afhvtk` en ik mag niet naar een andere branch pushen.
Vraag aan de SM of aan FH om de regel daar op `wip` te zetten.

### Correctie 1 — verkeerde toeschrijving

Het bord registreert `BlockedGate`, LIMIT EXPIRED → tier B én de IPv4-fix als "live werk
van deze chat vandaag". De eerste twee zijn **niet van mij**. Uit `git log`:

| commit | datum | sessie |
|---|---|---|
| `970483c` signal blocked / auto flat / config als kaarten | 17-08 | `01DBa51j4a7DWDmUZFxhR3Xy` |
| `6986c4e` + `50336a5` deploy-recept en tierlijst | 17-08 | `01DBa51j4a7DWDmUZFxhR3Xy` |
| `8c414cb` limit expired als kaart | 17-08 | `01DBa51j4a7DWDmUZFxhR3Xy` |
| `97c50cd` IPv4-binding + weigering zichtbaar | 19-08 | `01Af7DNBtRfxjQThKKv21uGC` (deze chat) |

Die andere chat heeft naar dezelfde branch gepusht. Het deploy-recept in de README waar
de SM naar verwijst — inclusief de `MexJournal.sln`-valkuil — komt dus **van hen**, niet
van mij. Graag corrigeren, anders klopt het spoor niet meer.

### Correctie 2 — de IPv4-fix is NIET live (belangrijkst)

`97c50cd` is **gecommit, niet gebouwd en niet uitgerold**. Er zit geen .NET SDK in mijn
sessie, dus hij is nergens gecompileerd. De draaiende binary op de VPS heeft nog het oude
gedrag. Concreet, met `dryRun:false` en `armed:true`:

- uitgaand verkeer kan nog steeds via IPv6 gaan → PMT blijft orders weigeren;
- een weigering wordt nog steeds als `sent 200` weggeschreven → onzichtbaar in het journaal.

**Niet als afgerond registreren.** Klaar is hij pas na `dotnet build src/Mex.Journal.Receiver
-c Release` + herstart op de VPS, met `curl -s ifconfig.me` als controle.

Blokkerend blijft: **`167.233.215.60` in de PMT IP-pool** (item B1 uit de overdracht).
Zolang dat niet gebeurd is, wordt er niets geplaatst — hoe de code er ook uitziet.

### Bewijs voor D-04 (notice-cards → .NET-receiver)

Eerstehands uit de uitrol van 11 augustus, bruikbaar voor FH's bevestiging:

- `/health` gaf na de uitrol `renderEnabled:true` met `renderScript=/root/mex-renderer/render-signal.js`.
- End-to-end in het audit-log: `card queued (tier B)` om 01:28:52Z → `card sent 200 (poging 1)`
  om 01:28:57Z; de kaart verscheen in Discord.
- Een volledige echte tradecyclus liep erdoorheen (01:19–01:23Z): FILL 6ct @ 4474,8 →
  RISK OFF → TRAIL → EXIT +$153,96 via trail.
- De Python-tak (`middleware/app/main.py`, `router.py`, `brokers/`) draait niet: dat kwam
  op 11-08 aan het licht toen patches daar geen enkel effect op de executie hadden.

### D-06 — wat er moet gebeuren, en wat ik niet kan

De repo heeft alleen `Program.cs` + README: geen `.csproj`, geen `.sln`, en
`Mex.Journal.Recon` (met `DiscordNotifier`) bestaat hier niet. Het bestand is dus een
**patch op de VPS**, geen bouwbare bron. Gevolg: geen enkele wijziging aan het live
executiepad is hier te compileren of te reviewen — die van mij van vandaag ook niet.

Voorstel: **hele solution onder versiebeheer**, niet "de VPS is de bron" vastleggen. Dat
laatste laat live code zonder historie en zonder review, en de `MexJournal.sln`-valkuil
zorgt ervoor dat een deploy stil kan mislukken met *Build succeeded*.

Ik kan dat niet zelf: ik heb geen toegang tot de VPS. FH moet exporteren:

    cd /root/mex-middleware-b
    tar czf /tmp/mex-receiver-src.tgz --exclude=bin --exclude=obj \
        src MexJournal.sln Directory.Build.props 2>/dev/null; ls -l /tmp/mex-receiver-src.tgz

Daarna naar de repo onder `middleware/receiver-src/`, met `bin/` en `obj/` in
`.gitignore`. Dan is `dotnet build` vanaf een verse clone mogelijk en kan deze chat
wijzigingen aan het live pad vóór uitrol compileren — nu kan dat niet.

## 2026-08-19 · LIVE EXECUTIEPAD gewijzigd — `mex-receiver` (Program.cs)

**Aanleiding:** PickMyTrade weigerde orders met `Cannot place alert, valid ip not
found in pool. Your IP: 2a01:4f8:c012:f9d3::1`. Drie SELL MGC1! van 13 aug 13:30
zijn niet geplaatst. Dat IPv6-adres is deze server; PMT's pool kent alleen de
IP's van TradingView, want vóór de trechter stuurde TradingView rechtstreeks.
PMT accepteert geen IPv6 in de pool.

**Twee wijzigingen in `middleware/dotnet-receiver/Program.cs`:**

1. **Uitgaand verkeer vastgezet op IPv4** via `SocketsHttpHandler.ConnectCallback`.
   Er valt nu precies één adres te whitelisten: `167.233.215.60`. Uit te zetten met
   `MEX_FORCE_IPV4=false`. Dit vervangt de `precedence`-regel in `/etc/gai.conf`;
   die regel mag blijven staan, maar de code is nu leidend zodat een herinstallatie
   van de server het niet stilletjes terugdraait.

2. **Antwoord van de doelserver wordt meegelezen.** PMT antwoordt op een geweigerde
   order met **HTTP 200** en de reden in de body. `ForwardAsync` keek alleen naar de
   statuscode, dus zo'n weigering kwam als `sent 200` in `routed_<datum>.jsonl` —
   niet te onderscheiden van een geplaatste order. Nu: body wordt ingekort meegelogd,
   en bij een herkende weigering wordt de regel `GEWEIGERD <code> door doelserver: …`
   én komt er een Discord-melding "⛔ Order NIET geplaatst".

**Gevolg voor wie hierop bouwt:** het `result`-veld in `routed_*.jsonl` heeft een
nieuwe waarde (`GEWEIGERD …`) en `sent 200` kan nu een achtervoegsel met het
antwoord van de doelserver hebben. Wie daarop parset (journaal-sync, dashboard):
match op prefix, niet op de hele string.

**Nog te doen door FH:**
- `167.233.215.60` in de PMT-pool zetten.
- `dotnet build src/Mex.Journal.Receiver -c Release` op de VPS — hier is geen SDK,
  dus deze wijziging is **niet gecompileerd**. De build is de poort.
- Terugkijken hoeveel orders er sinds de omzetting geweigerd zijn; met de oude
  logging is dat niet uit `routed_*.jsonl` af te leiden.

## 2026-08-19 · Ter info — main is leeg

`origin/main` bevat alleen `Initial commit` (29 juli). Punt 6 van de werkafspraken
zegt "de .NET receiver staat niet op HEAD"; in werkelijkheid staat er *niets* op
HEAD en leven alle zeven branches los naast elkaar. De receiver-source blijft
voorlopig op deze branch (besluit FH, 19 aug).
