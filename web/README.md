# web/ — de publieke sites

| Wat | Waar | Wat het is |
|---|---|---|
| `sites/mex` | www.mex-traders.com | Corporate site. Statisch. |
| `sites/ppt` | www.pipsandpalmtrees.com | Blog, gidsen en begrippenlijst. Statisch. |
| `handover/mex_units` | — | Module ter overname door Middleware App, zie `docs/inbox.md`. |

**Geen dashboard hier.** Dat draait al: `mex-viewer` op app.mex-traders.com,
bron `middleware/app/viewer.py`. De sites linken ernaartoe; ze vervangen het
niet.

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
heeft. Zet dat in CI.

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

---

## De units-laag (ter overname)

`handover/mex_units/` bevat de omrekening naar ticks, pips en R, plus de
rolgrens die een `viewer` alleen units laat zien. Die module is hier gebouwd
maar hoort in `middleware/app/`; zie `handover/mex_units/README.md` en het
verzoek in `docs/inbox.md`.

```bash
python3 -m pytest web/handover/mex_units/tests -q
```

---

## De publieke cijfers

De statische sites lezen `sites/mex/src/data/public-stats.json`. De site doet
dus nooit een API-call: er staat geen poort open naar de handelsdata, en de
publicatie kan bewust vertraagd worden.

**Dat bestand wordt nog niet geproduceerd.** Het hoort gemaakt te worden uit de
gezaghebbende bronnen — trades via `fills_pairing.py`, balansen via
`cash_ledger.py` — met `mex_units.roles` voor de omrekening en
`assert_no_currency()` als laatste controle. Dat verzoek staat in
`docs/inbox.md`; de Web-chat kan het niet zelf doen, want het leest uit
`middleware/**`.

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

---

## Ontwikkelen

```bash
make install        # dependencies
make dev-mex        # corporate site + CMS
make dev-ppt        # blog + CMS
make build          # beide sites statisch bouwen
make test           # units/rolgrens-tests
make check-glossary # faalt op een kapot bron-id of een dode verwijzing
make check          # alles
```

### Huisstijl en lettertypen

Het palet, de typografie en het beeldmerk komen uit het merkpakket
*MEX Traders — merkidentiteit v2*. Twee regels daaruit staan in code vast:

- **Goud is voor het merkteken en accenten**, niet voor vlakken en niet voor
  lopende tekst. Er is daarom geen token dat goud als paneelachtergrond
  aanbiedt.
- **Op en neer zijn azure en rose**, niet groen en rood. Dat is geen smaak: het
  paar meet ΔE 20,7 bij protanopie, waar groen/rood juist het klassieke
  probleemgeval is.

Het beeldmerk zit in `packages/brand/src/components/Logo.astro`; de losse
bestanden staan in `sites/mex/public/brand/`. Pips & Palm Trees gebruikt dat
merkteken bewust **niet** — dat hoort bij het bedrijf, niet bij het weblog.

De drie lettertypen worden zelf gehost. Niet uit voorkeur: de CSP van beide
sites is `default-src 'self'`, en een verzoek aan de Google-CDN is een verzoek
aan een derde partij bij elke paginaweergave — precies wat de privacyverklaring
zegt dat de site niet doet, en de reden dat er geen cookiebanner nodig is.

De bestanden staan in `packages/brand/src/fonts` en worden door
`make sync-fonts` naar elke plek gekopieerd die ze serveert. Dat is nodig omdat
Vite relatieve `url()`'s in CSS uit een workspace-pakket ongemoeid laat en de
bestanden niet meebouwt — ze geven dan stilzwijgend 404 op de gebouwde site.
`make check` faalt wanneer een doelmap afwijkt.

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
