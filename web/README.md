# web/ — de sites en het portal

Drie dingen, één huisstijl:

| Wat | Waar | Wat het is |
|---|---|---|
| `sites/mex` | www.mex-traders.com | Corporate site. Statisch. |
| `sites/ppt` | www.pipsandpalmtrees.com | Blog, gidsen en begrippenlijst. Statisch. |
| `portal` | app.mex-traders.com | Besloten dashboard. Draait op de VPS. |

`packages/brand` bevat de gedeelde huisstijl — kleuren, typografie, ritme en de
Astro-componenten. Een tweede site is een kopie van `site.config.ts` plus eigen
content, geen tweede codebase. `sites/ppt/src/styles/theme.css` laat zien hoe je
de toon verandert (warmere amber, schreefletter voor koppen) zonder de rest aan
te raken.

---

## Dagelijks gebruik

### Een blogpost schrijven

```bash
cd web
npm install          # eenmalig
npm run dev:ppt      # start op http://localhost:4321
```

Open **http://localhost:4321/keystatic**. Dat is de beheeromgeving: nieuwe post
aanmaken, tekst typen, afbeelding slepen, tags invullen, opslaan. Wat je opslaat
is een gewoon `.mdx`-bestand in `src/content/posts/`. Committen en pushen zet
het live.

Een post met **Concept** aangevinkt komt niet in de build voor. Dat is een echte
publicatiegrendel, geen aanduiding in de admin.

Vul je een **YouTube-id** in, dan wordt het een vlog-post: de video verschijnt
bovenaan als klikbare poster en laadt pas ná die klik. Zolang er niet geklikt
is, wordt er geen verbinding met YouTube gemaakt en worden er dus ook geen
cookies geplaatst — dat is precies waarom de site geen cookiebanner nodig heeft.

Voor de corporate site werkt het identiek met `npm run dev:mex`.

### Een begrip toevoegen aan de begrippenlijst

In dezelfde admin, onder **Naslag → Begrippen**. Een begrip bestaat uit één zin
(die staat in het overzicht en in de zoekresultaten), een categorie, eventuele
synoniemen, en een langere toelichting.

Twee velden verdienen aandacht:

- **Steunt op een officiële bron.** Alleen aanvinken wanneer een toezichthouder,
  beurs of wet het begrip daadwerkelijk definieert. De pagina toont dan een
  badge, en die badge moet iets waard blijven.
- **Bronnen.** Vul id's in uit `sites/ppt/src/data/sources.json`. Staat je bron
  daar nog niet, voeg hem daar dan eerst toe — één plek, zodat een dode link
  maar één keer gerepareerd hoeft te worden en elke citatie dezelfde vorm heeft.

`make check-glossary` faalt op een onbekend bron-id, een verwijzing naar een
begrip dat niet bestaat, en op een begrip dat wel de badge draagt maar geen bron
heeft. Zet dat in CI naast `check-tokens`.

### Een gids schrijven

Onder **Schrijven → Gidsen**. Gidsen staan op onderwerp in plaats van op datum
en worden bijgewerkt in plaats van opnieuw geschreven — vandaar het verplichte
veld "bijgewerkt op", dat op de pagina zichtbaar is.

`order` bepaalt de plek in het leerpad op `/start-hier`. Dat pad verwijst naar
gidsen op hun slug; verwijder je er een, dan verdwijnt die stap stilzwijgend uit
het pad in plaats van de build te breken. Controleer `/start-hier` dus even na
het verwijderen of hernoemen van een gids.

### Vanaf je telefoon publiceren

Zet de CMS in GitHub-modus, dan zit de admin op de live site en schrijf je
overal vandaan:

1. Maak een GitHub OAuth-app aan met callback
   `https://www.pipsandpalmtrees.com/api/keystatic/github/oauth/callback`.
2. Zet in de Cloudflare Pages-omgeving:
   `KEYSTATIC_MODE=github`, `KEYSTATIC_GITHUB_CLIENT_ID`,
   `KEYSTATIC_GITHUB_CLIENT_SECRET`, `KEYSTATIC_SECRET`.
3. Deploy opnieuw.

De build schakelt dan automatisch de Cloudflare-adapter in (zie
`astro.config.mjs`), zodat alleen de admin-routes serverzijdig draaien; de rest
van de site blijft gewone bestanden. Opslaan in de admin maakt een commit, en
die commit triggert een deploy.

### Iemand toegang geven tot het dashboard

Voeg een regel toe aan `users.yaml` op de server (zie `portal/users.example.yaml`):

```yaml
users:
  - email: iemand@voorbeeld.nl
    name: Iemand
    role: viewer
```

Daarna in het portal → **Beheer** → *users.yaml opnieuw laden*. Klaar. Die
persoon vraagt zelf een link aan op de inlogpagina.

| Rol | Ziet |
|---|---|
| `owner` | alles in dollars, plus /admin (sessies, audit, intrekken) |
| `partner` | alles in dollars, alleen lezen |
| `viewer` | **alleen units** — ticks, R, percentages |

Toegang intrekken: haal de regel weg en laad opnieuw. Dat werkt ook midden in
een lopende sessie, omdat de rol bij élke aanvraag opnieuw uit dat bestand komt.

---

## Hoe "geen bedragen voor viewers" is afgedwongen

Niet met CSS en niet met een filter. Elke rol heeft in `portal/app/stats.py` een
eigen functie die zijn eigen payload opbouwt. De viewer-payload bevat geen
dollarveld — niet verborgen, niet op nul, maar afwezig. Een filter zou elk veld
lekken dat iemand later toevoegt en vergeet te noteren; een aparte builder kan
dat niet.

`portal/tests/test_roles.py` bouwt een fleet die gegarandeerd geld bevat en
controleert daarna de viewer-payload op twee manieren: op veldnaam én op
waarde. Alle bedragen in de fixture hebben centen en gepubliceerde
unit-aantallen zijn gehele getallen, dus een match is altijd een echt lek en
nooit toeval.

Het publicatiebestand krijgt daarbovenop een expliciete poort:
`publish.assert_no_currency()` weigert te schrijven zodra er een veldnaam
langskomt die naar geld ruikt.

```bash
cd web/portal && python -m pytest tests -q
```

---

## De publieke cijfers

De statische sites lezen `sites/mex/src/data/public-stats.json`. Dat bestand
wordt geschreven door een taak op de VPS:

```bash
cd /opt/mex/web/portal
.venv/bin/python -m app.publish --dry-run   # eerst kijken
.venv/bin/python -m app.publish             # dan schrijven
```

De taak neemt een verse kopie van het handelsjournaal, laat alles weg dat
jonger is dan `PORTAL_PUBLIC_LAG_HOURS` (standaard 24 uur) en rekent alles om
naar units. De site doet dus nooit een API-call: er staat geen poort open naar
de handelsdata, en je kunt de publicatie bewust vertragen.

Zolang het meegeleverde bestand `"sample": true` bevat, toont elke pagina die de
cijfers rendert een zichtbare placeholder-melding. Illustratieve getallen kunnen
zo nooit voor een track record worden aangezien. De eerste echte publicatierun
zet die vlag om.

**Let op bij de eerste echte publicatie:** controleer de voorwaarden van je
prop-firms. Die beperken vaak wat je over rekeningen mag publiceren. De
publieke laag bevat daarom geen rekeningnummers en geen firmanamen — maar de
beslissing om überhaupt cijfers te tonen blijft die van jou.

---

## Deployen

### De twee sites → Cloudflare Pages

Per site één Pages-project:

| Instelling | mex | ppt |
|---|---|---|
| Root directory | `web` | `web` |
| Build command | `npm run build:mex` | `npm run build:ppt` |
| Output directory | `sites/mex/dist` | `sites/ppt/dist` |
| Env | `SITE_URL=https://www.mex-traders.com` | `SITE_URL=https://www.pipsandpalmtrees.com` |

Elke branch krijgt automatisch een preview-URL, dus je ziet een wijziging
voordat hij live staat. `public/_headers` regelt de beveiligingsheaders.

### Het portal → de VPS

```bash
# eenmalig, naast de bestaande middleware
sudo mkdir -p /etc/mex-portal /var/lib/mex-portal
sudo cp portal/.env.example /etc/mex-portal/portal.env
sudo cp portal/users.example.yaml /etc/mex-portal/users.yaml
sudo chown root:mex /etc/mex-portal/*.yaml /etc/mex-portal/portal.env
sudo chmod 640 /etc/mex-portal/*

cd /opt/mex/web/portal
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.auth        # genereert PORTAL_SECRET → in portal.env

sudo cp deploy/mex-portal.service /etc/systemd/system/
sudo cp deploy/mex-publish.service deploy/mex-publish.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mex-portal mex-publish.timer
```

Plak daarna `deploy/Caddyfile.snippet` in je Caddyfile en herlaad Caddy.

Het portal draait **naast** de middleware, niet erin: eigen proces, eigen poort,
eigen database, lagere CPU-prioriteit en een geheugenplafond. Webverkeer mag
nooit met een TradingView-webhook om resources concurreren. Het leest het
handelsjournaal alleen via een `VACUUM INTO`-kopie, read-only geopend op
driverniveau — zelfs een programmeerfout kan er niet in schrijven.

---

## Ontwikkelen

```bash
make install        # dependencies
make dev-mex        # corporate site + CMS
make dev-ppt        # blog + CMS
make build          # beide sites statisch bouwen
make test           # portal-tests
make check-tokens   # faalt als het palet van het portal is afgeweken
make check-glossary # faalt op een kapot bron-id of een dode verwijzing
make check          # alles
```

### Waarom het palet twee keer bestaat

De sites importeren `packages/brand/src/styles/tokens.css`. Het portal deployt
apart, op een andere machine, zonder de npm-workspace — het heeft dus een eigen
kopie in `portal/app/static/portal.css`. Twee kopieën van een palet lopen
stilletjes uit elkaar, dus `make check-tokens` vergelijkt ze en faalt bij
verschil. Zet dat in CI.

### Nog te doen vóór livegang

- **Juridische pagina's laten toetsen.** De teksten onder `juridisch/` zijn een
  zorgvuldige basis, geen juridisch advies. Ze staan met een zichtbare
  waarschuwing in de content; laat ze beoordelen en haal die waarschuwing dan
  weg.
- **Entiteitsgegevens invullen** in beide `site.config.ts` (`entity`,
  `registration`).
- **SPF, DKIM en DMARC** op het verzendende domein. Zonder werkende
  deliverability komt geen enkele inloglink aan.
- **OG-afbeelding** (`public/og-default.png`) per site, 1200×630.
- **Analytics** — cookieloos (Plausible/Umami) als je iets wilt meten; dat
  scheelt een cookiebanner. Voeg het script dan toe aan de CSP in `_headers`.
