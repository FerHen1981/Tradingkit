# Herijking 27-09-2026 — het platformplan

_Eigenaar: Scrum Master. Vastgesteld met Ferry op 27-09 in achttien vragen en antwoorden._
_Dit document vervangt de ad-hoc prioritering op `docs/SPRINT.md` als leidraad. Het bord_
_blijft het werkinstrument; dit is de reden waarom een item erop staat._

---

## 0. Waarom dit document bestaat

Ferry: *"Voor we op deze manier verder gaan moeten we eerst herijken wat de initiële
bedoeling was en waar we nu staan."* Het bord was gegroeid naar 77 items waarvan er veel
onderzoek waren en weinig platform. Dit document zet de vier oorspronkelijke pijlers terug
vooraan en leidt daar een volgorde uit af.

**Ferry's randvoorwaarde bij dit plan** (antwoord 16 en 18): *"een volledig stappenplan
zodat we kunnen voorkomen of minimaliseren dat er tussentijds taken bijkomen"* en
*"zoveel tijd als nodig, want anders gaan we door op halffabricaten en dat levert helemaal
niets."* Beide zijn ontwerpeisen aan dit plan, geen wensen. Daarom staat vóór elke bouwstap
met een onbekende eerst een **meting**, en sluit elke fase af met een expliciete lijst
**wat we in deze fase NIET doen**.

---

## 1. De vier pijlers, en waar ze echt staan (gemeten 24-09 t/m 27-09)

| Pijler | Stand |
|---|---|
| **1. Fan-out** TradingView → middleware → kanalen | **Grotendeels gebouwd.** De live receiver (`Program.cs`, 1134 regels) doet exact dit. Bestemmingen die werken: PMT-Tradovate, PMT-Rithmic, PineConnector, Discord, journal-CSV. **Ontbreekt:** Notion (0 treffers in de receiver; D-20 bewees dat de schrijfkant nooit automatisch draaide) en de webapp (die leest bestanden, hij ontvangt niets). |
| **2. Webapp** actuals · vooruitblik · advies · beheer · widget | **Het grote gat.** Actuals bestaan half (`/api/state`, `/api/widget`), vooruitblik en advies draaien op een **ingetrokken doctrine** (zie §2.3), beheer ontbreekt volledig. |
| **3. Pine-ruimte** | `pine/` bestaat, 13 scripts van de `v1_0_0`-lijn. Ferry (antwoord 12): **"alleen versies"** — de behoefte is versiebeheer, verder niets. |
| **4. Backtest** | 12-traps pijplijn + lab-cockpit op `bck.mex-traders.com`. Maar het is een **herimplementatie** van de Pine-logica, en Ferry wil (antwoord 14) dat de backtester het `.pine`-bestand zélf leest. |

---

## 2. De vier keerpunten

Dit zijn de plekken waar het systeem fundamenteel anders wordt. Alles in §4 volgt hieruit.

### 2.1 Configuratie verhuist van Pine en env-vars naar één beheerde bron

**Vandaag.** De kanaalkeuze staat **in elk Pine-script afzonderlijk**. Gemeten in
`MEX_EL_MATADOR_MES_PROD_EOD_v1_0_0.pine`:

```
routePMT · routeRithmic · routePineConnector · routeDiscord · routeJournal   (5 toggles)
pmtToken · pcLicense · pcSymbol · accountID                                   (4 waarden)
```

Dat is **13 scripts × 9 instellingen, met de hand in TradingView gezet**, plus geheimen die
als plaintext-input in een chart staan. De accountkant staat daarnaast in
**environment-variabelen op de VPS** (`MEX_ACCOUNT_QTY`, `MEX_HALTED_ACCOUNTS`,
`MEX_ACCOUNT_ENTRY_CAPS`, `MEX_PMT_RITHMIC_ACCOUNTS`, de drie webhook-URL's) die in
**static constructors** worden gelezen — dus **bevroren bij procesnstart**.

**Straks** (antwoord 4, 8, 9). Eén configuratiebron die de webapp beheert en de receiver
**herleest zonder herstart**. Pine stuurt één canoniek bericht; de middleware bepaalt wat
waarheen gaat en bouwt elke payload zelf.

> ⚠️ **Dit maakt de webapp onderdeel van het live executiepad.** Vandaag kan een fout in de
> webapp hooguit een verkeerd getal tonen. Straks kan hij orders sturen naar het verkeerde
> account of het verkeerde kanaal. Dat is geen reden het niet te doen — het is de reden dat
> fase 1 een validatielaag, een audit-spoor en een laatst-goede-config-terugval krijgt
> vóórdat er één instelling in een scherm komt.

### 2.2 Er komen drie waarheidslagen in plaats van één

Ferry (antwoord 5): *"we kunnen geen API gebruiken van Tradovate dus moeten een oplossing
hebben die qua getallen en timing het dichtst in de buurt komt van live."* Het voorstel
staat in §3. De kern: **elk bedrag in de webapp draagt zichtbaar zijn herkomst** —
gemodelleerd, bevestigd, of afgestemd tegen brokerwaarheid. Dat generaliseert het
`✓ verified` / `⚠ unverified`-label uit D-74 naar het hele systeem.

### 2.3 🔴 De adviesmotor draait vandaag op een ingetrokken conclusie

`middleware/app/playbook.py` (504 regels) is precies wat pijler 2 vraagt — *"per account
beslist het de TRACK en de PHASE, en toont de doctrine-preset"*. Maar zijn tabellen zijn die
van vóór 23-08:

```python
FUNDED_STRAT = {"GC": "El Tesoro", "ES": "El Rey"}
# "NQ/YM are eval-only variance lots — never on a funded account."
STRAT_ASSET  = {"El Rey": "ES", "El Matador": "NQ", "El León": "ES", "El Patrón": "NQ", ...}
```

Dat is de **GC+ES-regel die Ferry op 24-08 heeft ingetrokken**, plus een asset-mapping die
de vloottabel op vier engines tegenspreekt (El Rey is MNQ niet ES; El Matador is MES niet
NQ; El León is MYM niet ES; El Patrón is MGC niet NQ). El Minero staat er als
eval-strategie terwijl hij in de vloot "gereserveerd" is.

**Consequentie voor het plan:** de adviesmotor wordt niet gerepareerd maar **opgesplitst**.
Advies over *accountmechanica* (halt-niveau, op- en afschalen, welke accountgrootte past)
hangt aan firm-regels en actuals — dat kan nu en is wat Ferry in antwoord 15 vraagt. Advies
over *welke strategie op welk account* hangt aan de vlootrangorde — en die **bestaat op dit
moment niet**. Die splitsing is de enige manier om nu iets bruikbaars te bouwen zonder een
ingetrokken conclusie opnieuw in te bakken.

### 2.4 De pariteitsvraag lost zichzelf op

Ferry (antwoord 14): de backtester moet het `.pine`-bestand zelf lezen. Daarmee vervalt de
reden voor **D-66** — de vraag of de vloot op een andere CVD-motor draait dan de backtester
meet. Zodra er één implementatie is, is er geen pariteit meer te bewaken. **D-66 wordt niet
uitgevoerd maar geabsorbeerd**, en daarmee vervalt ook de keten D-63 → D-54 → D-57 die
erachter stond. Dat haalt in één keer de grootste blokkade van het bord.

---

## 3. Voorstel: hoe we zonder API zo dicht mogelijk bij live komen

Gevraagd in antwoord 5. Drie lagen, elk met een eigen snelheid en een eigen betrouwbaarheid.
Elk getal in de webapp draagt zijn laag als label.

| Laag | Bron | Latency | Wat het is |
|---|---|---|---|
| **T1 · gemodelleerd** | het canonieke event uit Pine (entry/exit, prijs, richting, qty) | direct | Wat de strategie *bedoelde*. Bevat geen slippage en geen echte commissie. |
| **T2 · bevestigd** | het **antwoordbericht van PMT** op de order | seconden | Of PMT de order heeft **aangenomen**. ✅ **Gemeten 28-09 (D-73), en de aanname eronder is weerlegd: er komt géén prijs.** |
| **T3 · afgestemd** | de wekelijkse fills/Cash_History-export | wekelijks | Brokerwaarheid: echte fills, echte commissies, funding en payouts. |

**Hoe ze samenwerken.** T1 vult het scherm onmiddellijk. T2 promoveert een regel van
"verstuurd" naar "geaccepteerd" of "geweigerd". T3 is de wekelijkse herijking die Ferry in
antwoord 6 beschrijft: de afwijking T1→T3 per account en per venue is meteen de
slippage-meting waar de reconciliatielaag voor bedoeld was.

✅ **GEMETEN 28-09 (D-73) — en de meting weerlegt de aanname waarop T2 was ontworpen.**
Middleware App analyseerde **4539 PMT-rijen over 41 bestanden**, niet de twintig die ik vroeg.
Uitkomst: **de antwoordbody draagt nooit een fill-prijs en nooit een order-id.** Verdeling:
90,4% `{"res":"Successfully send","error":false}` · 9,1% leeg · 0,5% `error 403`.

Drie gevolgen, en ze veranderen het ontwerp:

1. **T2 is een statuslaag, geen prijslaag.** Vier toestanden: `CONFIRMED` · `UNKNOWN` (lege
   body) · `REJECTED` · en verder niets. Er is dus **geen tussenliggende prijswaarheid**:
   de afwijking **T1→T3 blijft de enige slippage-meting** die we kunnen doen, en die is
   wekelijks. Dat is een echte beperking en geen implementatiedetail.
2. **`GEWEIGERD 200` kwam 0 keer voor in 4539 rijen.** De body-gebaseerde `Rejected()`-check
   in de live receiver heeft nooit iets afgevangen — niet omdat hij overbodig is, maar omdat
   **PMT `error:true` in de praktijk niet stuurt**. Een echte weigering komt als **HTTP 403**.
   De poort moet dus op de statuscode staan, niet op de body.
3. **`UNKNOWN` is geen restcategorie maar de kern.** 9,1% lege bodies zichtbaar maken is
   precies waar §2.2 om vroeg: onbevestigd is een **toestand**, geen poort die dichtvalt.

Volledige meting: `docs/D-73-pmt-bodies-2026-09-28.md`.

**Notion** (antwoord 1) wordt een **afnemer van dezelfde journaalregels**, niet een aparte
schrijfweg. Eén bron, twee vensters — dat is de enige manier om "dezelfde waarheid als de
webapp" waar te maken.

**De webapp-push** (antwoord 2) hangt aan dezelfde regels: de receiver stuurt bij elk event
met effect een seintje naar de viewer, die zijn state ververst. Geen polling.

---

## 4. De fasen

Volgorde is dwingend waar een pijl staat. Eigenaren volgen de eigenaarstabel in `CLAUDE.md`.

```
Fase 0  fundament ─┬─> Fase 1  config-store ──> Fase 2  settings-tab ──> Fase 3  Pine ontkoppelen
                   │                                      │
                   └─> Fase 4  drie waarheidslagen ───────┴──> Fase 5  vijf vooruitblikken
                                                                    └──> Fase 6  adviesmotor
                                                                            └──> Fase 7  widget

spoor B (parallel, Backtest Setup)   .pine lezen ──> door de hele molen
spoor C (parallel, Pine Dev)         versiebeheer
```

---

### Fase 0 — Fundament · Scrum Master + CLO

Geen code. Dit is de fase die de rest voorspelbaar maakt.

**0.1 Het bord opschonen** (antwoord 17). Zie §5 voor de volledige lijst. Van 33 open items
blijven er 12 staan; de rest wordt gearchiveerd of geabsorbeerd.

**0.2 Het canonieke event-schema.** Eén versienummerd document dat vastlegt wat Pine straks
stuurt: strategie, account-sleutel, richting, type (entry/exit/halt/derisk/info), prijs,
stop, target, tijdstempel, en een gebeurtenis-id voor idempotentie. **Dit is het scharnier
van fase 3 en het moet af zijn vóór iemand aan fase 1 begint** — de config-store moet weten
welke velden hij gaat routeren.

**0.3 Het configuratie-schema.** Wat er in de beheerde bron staat, in twee niveaus zoals
Ferry ze in antwoord 9 benoemt:

*Niveau 1 — kanaal en herkomst:* per prop-firm-programma (de registry `data/propfirms.json`
draagt er al **18**, ruim boven de tien uit antwoord 3): welk kanaal (PMT-Tradovate /
PMT-Rithmic / PineConnector), welke token, welke URL, welke Discord-webhook.

*Niveau 2 — per account:* harde caps (wat Ferry nu in Tradovate zet), publiceren ja/nee,
accountstatus, en de Discord-webhook per kanaal.

> **Contracten staan hier bewust NIET in** (antwoord 9): *"Aantal contracten zit in het
> advies en beheer ik in pine."* Dat betekent dat **D-53** — de qty-override in de receiver,
> nu net gebouwd — een *vangnet* is en geen besturingsknop. Hij blijft, maar de settings-tab
> krijgt er geen veld voor.

**0.4 Besluit dat op Ferry wacht:** zie §6, punt 1 (de OOS-klok).

**Wat we in fase 0 NIET doen:** niets bouwen, niets verwijderen, geen enkele Pine-wijziging.

**Klaar wanneer:** het event-schema en het config-schema liggen er als vastgesteld document,
het bord is opgeschoond, en de vraag over de OOS-klok is beantwoord.

---

### Fase 1 — De config-store met herlaadbaarheid · Middleware App · 🔴 LIVE PATH

Dit is de zwaarste technische stap en hij raakt echte orders.

1. **Configprovider** die één bestand leest in plaats van de static constructors in
   `AccountQty`, `AccountBlockGate` en `AccountRiskGate`. Zelfde gedrag, andere bron.
2. **Herlaadbaar** (antwoord 8: optie b) — een bestandswijziging wordt opgepikt zonder
   herstart.
3. **Validatie vóór activatie.** Een config die niet valideert wordt **niet** geladen; de
   laatst-goede blijft draaien en er gaat een luide melding uit. Stilte is hier de vijand:
   we hebben dit patroon al drie keer geraakt (de drawdown-fallback in D-68, de
   ledger-fallback in D-75, de push in D-31).
4. **Auditspoor.** Elke wijziging: wie, wat, wanneer, vorige waarde. Append-only.
5. **Migratie.** De huidige env-waarden worden eenmalig omgezet en daarna is de env-route
   dood — met een startwaarschuwing als iemand toch nog een oude variabele zet, precies
   zoals Middleware App dat bij `MEX_ACCOUNT_QTY` heeft gedaan.

**Acceptatie:** in `DRY_RUN` een wijziging doorvoeren, aantonen dat het gedrag meebeweegt
zonder herstart, een kapotte config aanbieden en aantonen dat de oude blijft draaien met een
zichtbare melding. Pas daarna scherp.

**Wat we in fase 1 NIET doen:** geen scherm, geen nieuwe instellingen, geen kanaalwijziging.
Alleen: dezelfde instellingen, andere bron, herlaadbaar.

---

### Fase 2 — De settings-tab · Web + Middleware App

De twee niveaus uit 0.3, als scherm. Leest en schrijft de config-store van fase 1.

- Niveau 1 komt uit `data/propfirms.json` — **geen tweede firm-lijst aanleggen.**
- Tokens en webhook-URL's worden hier beheerd. Dat betekent dat ze **uit de Pine-scripts
  verdwijnen** (waar ze nu als chart-input staan) en dat **D-11** verandert van karakter:
  roteren wordt een handeling in het scherm in plaats van een SSH-sessie.
- Authenticatie is hier geen bijzaak maar een ontwerpeis — dit scherm stuurt orders.
- Elke wijziging toont wat er verandert vóór het opslaan, en landt in het auditspoor.

**Wat we in fase 2 NIET doen:** geen contractvelden (zie 0.3), geen advieslogica, geen
strategie-instellingen. Het scherm beheert distributie, niet handel.

#### 2a — Eerst LEZEN, dan schrijven (toegevoegd 29-09 na vier incidenten op één dag)

Ferry, 29-09: *"Allemaal redenen waarom ik het beheer van de fanout in het settings dashboard
wil hebben, er gebeuren nu op de achtergrond ongecontroleerde dingen."* Dat is de goede
conclusie, en de incidenten van die dag scherpen hem op twee punten.

🔴 **Punt één: de settings-tab wordt gesplitst in een leeshelft en een schrijfhelft, en de
leeshelft gaat eerst.** Op 29-09 bleek ons beeld van de fan-out **twee keer in één uur
onjuist** — eerst werd de rate-limit als oorzaak aangewezen (weerlegd: CONFIG is tier B en
EXIT tier A, dus de limiter zou het omgekeerde doen), daarna een Pine-runtime-error (weerlegd:
de scripts op de charts waren niet gewijzigd). **Een scherm dat naar het live pad schrijft
terwijl ons model van dat pad onjuist is, is gevaarlijker dan PowerShell** — want het voelt
betrouwbaar. Dus: eerst een scherm dat toont wat de fan-out *doet*, geverifieerd tegen de
werkelijkheid, daarna pas de knoppen.

🔴 **Punt twee: een settings-tab toont configuratie, en dat is niet wat er vandaag miste.**
Van de vijf bevindingen van 29-09 zou het scherm er **drie** hebben voorkomen of binnen
seconden hebben gevonden — de webhook-routing per account (D-118), de dempingsdrempel van 12
tegen een budget van 30 (D-116), en de tier→kanaal-indeling (D-117). **Twee niet:** dat een
gedempte kaart wordt weggegooid in plaats van als tekst verstuurd, en dat de `catch` in
`RenderAndPostAsync` geen fallback heeft. Dat zijn codefouten van één soort — **een pad dat
stilvalt zonder het te melden** — en daar helpt geen instelling tegen.

➡️ **Daarom krijgt fase 2 een tweeling: een fan-out-statusvenster.** Niet "wat staat er
ingesteld" maar "wat is er de afgelopen periode gebeurd": per kanaal het aantal verstuurd ·
gedempt · mislukt, met de laatste foutcode. **De data bestaat al** — `routed_*.jsonl` draagt
per bericht `kind`, `account`, `transport` en `result`, inclusief `card rate-limited` en
`error 401`. Het is een lezing van een bestand dat al geschreven wordt, geen nieuwe telemetrie.

📌 **En het sluit een derde gat dat vandaag pijnlijk werd:** zeven commits raakten het live
pad in twee dagen en niemand — Ferry noch dit bord — kon vaststellen welke binary er draaide,
omdat `docs/runtime-snapshot.md` niet bestaat (**D-31**). Een statusvenster dat de draaiende
versie noemt maakt "ongecontroleerde dingen op de achtergrond" onmogelijk in plaats van
onwaarschijnlijk.

---

### Fase 3 — Kanaalrouting uit Pine · Pine Dev + Middleware App · 🔴 LIVE PATH

De breukstap. Pine stuurt straks **één** canoniek bericht in plaats van vijf routebepaalde
alerts; de middleware bouwt de PMT-JSON, de Discord-embed, het PineConnector-commando en de
journaalregel uit de config.

**De bewijslast ligt hier hoog en de methode is dwingend:** eerst draaien beide wegen naast
elkaar in `DRY_RUN` en worden de **oude en nieuwe payloads byte-voor-byte vergeleken** op
echt verkeer. Pas bij nul verschil over een volle handelsweek gaat de oude weg eruit. Een
verschil in een PMT-payload is een verkeerde order.

Dit verwijdert ~9 instellingen uit elk van 13 scripts. **D-47** (twee openstaande alerts)
wordt hierdoor achterhaald en gaat mee in deze fase.

**Wat we in fase 3 NIET doen:** geen enkele wijziging aan entry-, exit- of
risicologica in Pine. Alleen de alert-plumbing. Dat onderscheid is precies waar besluit 1
in §6 over gaat.

---

### Fase 4 — De drie waarheidslagen · Middleware App

Zoals uitgewerkt in §3.

1. **Meting eerst:** 20 echte PMT-antwoorden opslaan en bekijken. Wat T2 kan worden hangt
   hiervan af; daarvóór ontwerpen we niets. Dit is **D-73**, gepromoveerd.
2. **T1** uit het canonieke event van fase 3.
3. **T2** op basis van de meting.
4. **T3** — de wekelijkse export. Ferry levert; de import en de afstemming zijn code.
   **D-75** (wat ligt er in `/root/exports`) en **D-03** (de reconciliatie-timer) gaan hier
   in op.
5. **Elke waarde draagt zijn laag** tot in de widget. Dit is D-74's label, veralgemeend.
6. **Notion** wordt afnemer van dezelfde journaalregels (antwoord 1).
7. **De webapp-push** bij elk event met effect (antwoord 2).

**Hier vervalt D-72 in zijn huidige vorm.** Dat item vroeg om een keuze over een
executiepoort die op een exit-echo wacht die PMT nooit stuurt. Met een expliciete T2-laag is
"niet bevestigd" een *zichtbare toestand* in plaats van een poort die dichtvalt — dat is de
uitweg uit het fail-blind-probleem dat Web statisch had bewezen.

---

### Fase 5 — De vijf vooruitblikken · Middleware App

Antwoord 10: alle vijf, volledig uitgewerkt, per account:

1. dagen tot payout-eligible
2. ruimte tot de trailing drawdown
3. ruimte tot de daily loss limit, vandaag
4. de consistency-regel
5. kwalificerende dagen

Alle vijf lezen hun regels uit `data/propfirms.json`. **Geen hardgecodeerde drempels** — dat
is wat **D-68** in de backtest-pijplijn aan het licht bracht en dezelfde fout mag hier niet
opnieuw ontstaan. Ontbreekt een regel in de registry, dan faalt het hard in plaats van stil
op een aanname terug te vallen.

---

### Fase 6 — De adviesmotor · Middleware App

Vervangt het fleet-document dat Ferry nu met de hand bijhoudt (antwoord 6). **Adviseert
alleen**; Ferry verwerkt het zelf in de alerts (antwoord 7).

Gesplitst zoals §2.3 voorschrijft:

**6a — accountmechanica (kan nu).** Dit is wat antwoord 15 vraagt:
- Op welk niveau hoort een daily halt? Op x verliezen, x winsten, of op een bedrag? Dat is
  een meetbare vraag op de eigen historie, niet een meningsvraag.
- Wanneer op- en wanneer afschalen?
- Welke accountgrootte past het best bij welke regels?

**6b — strategiekeuze (geblokkeerd, en dat blijft zichtbaar).** Welke engine op welk account
hangt aan de vlootrangorde, en die is er niet. Het scherm toont hier expliciet *"geen geldige
rangorde"* in plaats van een oud getal. `playbook.py`'s ingetrokken tabellen worden
verwijderd, niet bijgewerkt.

---

### Fase 7 — De widget · Middleware App

Antwoord 11: **alleen weergave**, geen advies. Twee doorsneden en vier perioden:

- **funded** → saldo-ontwikkeling
- **eval** → accountontwikkeling (saldo doet niet ter zake)
- perioden: vandaag · laatste handelsdag · week · overall

"Laatste handelsdag" is nieuw en niet hetzelfde als "gisteren" — op maandag is dat vrijdag,
en na een stille dag schuift hij door. **D-74** (geen eval-bedragen) en **D-76** (Today per
stack) gaan hierin op.

---

### Spoor B — de backtester leest `.pine` · Backtest Setup · parallel vanaf dag 1

Antwoord 14. Dit is het langste traject en het raakt niets van fase 1 t/m 7, dus het loopt
ernaast. **Harde regel: dit spoor komt niet in `middleware/**` of `web/**`.**

Aanpak, in oplopende ambitie — we beginnen bij de kleinste die het doel haalt:

1. **Inventariseren welk deel van Pine onze scripts werkelijk gebruiken.** De 13 scripts
   komen uit één familie; de kans is groot dat de gebruikte taalconstructies een beperkte,
   opsombare verzameling zijn.
2. **Een interpreter voor precies die deelverzameling**, die **hard weigert** op alles wat
   hij niet kent. Dat laatste is essentieel: een interpreter die onbekende constructies
   stilzwijgend overslaat produceert plausibele en onjuiste backtests — hetzelfde
   faalpatroon als de stille fallbacks hierboven.
3. **Pas dan** door de bestaande molen: walk-forward, Monte Carlo, stress, prop-firm-simulatie.

**D-66** (de CVD-pariteitsvraag) gaat hierin op en wordt niet apart uitgevoerd — zie §2.4.

---

### Spoor C — Pine-versiebeheer · Pine Dev · klein, parallel

Antwoord 12: *"alleen versies."* Vastleggen welke versie van elk script op TradingView
draait, met datum en een korte reden. Handmatig plakken blijft (antwoord 13). Dit is een
conventie plus een bestand, geen bouwwerk.

---

## 5. Wat er van het bord af gaat

Antwoord 17: *"dit gaan we opnieuw doen als dit allemaal staat en kan nu
afgewikkeld/gearchiveerd worden als het niet direct bijdraagt."*

**Blijft staan (12):** D-53 · D-68 · D-69 · D-70 · D-71 · D-73 · D-74 · D-11 · D-17 ·
D-26 · D-31 · D-44 · D-58

**Gaat op in een fase (7):** D-75 en D-03 → fase 4 · D-72 en D-46b → fase 4 · D-47 → fase 3
· D-76 → fase 7 · D-66 → spoor B

**Gearchiveerd tot na dit plan (11):** D-54 · D-57 · D-63 · D-64 · D-15 · D-16 · D-25 ·
D-38 · D-39 · D-50 · D-27 · D-23

Archiveren betekent hier: het item blijft leesbaar met alles wat eronder is uitgezocht, maar
verdwijnt uit de actieve lijst en telt niet meer mee. **Bewijs wordt nooit weggegooid** —
dat is dezelfde regel als voor `validation/`.

---

## 6. Besluiten die nog op Ferry wachten

**1. 🔴 Zet fase 3 de OOS-klok op nul?** De regel is: elke config-wijziging zet de klok voor
de hele vloot op nul. Fase 3 haalt de alert-routing uit 13 scripts maar raakt geen entry-,
exit- of risicologica. *Aanbeveling: nee, mits we met een diff aantonen dat alleen
alert-plumbing wijzigde.* Maar dit is een besluit, geen constatering — en het moet vallen
vóór fase 3, niet erna.

**2. Welke tien van de achttien?** De registry draagt 18 programma's. Antwoord 3 noemt tien.
Moeten ze alle achttien selecteerbaar zijn, of komt er een selectie?

**3. Wie mag de settings-tab bedienen?** Vandaag alleen Ferry. Als dat zo blijft is een
simpel wachtwoord genoeg; komt er ooit iemand bij, dan is dat nu goedkoper te bouwen dan
later.

**4. De wekelijkse export (T3) — welke dag en welk formaat?** Dat bepaalt de import.
