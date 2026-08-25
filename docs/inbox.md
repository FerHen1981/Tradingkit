# Inbox — cross-chat verzoeken (zie werkafspraken §2/§4)

> **Bord:** lopend werk staat in **`docs/SPRINT.md`** — dit bestand is de wachtrij
> ernaartoe. Ferry's beeld (besluiten, archief) staat in
> **LifeOS → Tasks/Notes**. Items met `SM-` zijn inmiddels als `D-xx` op het bord
> gezet.

Formaat per item: **van → aan** · datum · status. De eigenaar van de doelmap voert
uit en zet status op `done` met de commit-hash. Niemand bouwt buiten de eigen map.

---

## OPEN

### 22. De vier EL TORO-scripts compileerden niet — en dat betekent iets over hun bewijs
**Pine Dev → Scrum Master / Backtest Setup** · 2026-08-24 · status: TER REVIEW

Ferry plakte `TOR-NQ-HF` in de editor: **`Undeclared identifier "barsSinceNotBull" (CE10272)`**.

**De fout.** In de v1_0_0-vloot komt de CVD uit `ta.barssince(not bullDirOk)`. In de vier
TORO-scripts is dat blok vervangen door de deterministische OHLCV-polariteitsproxy met
`proxyBullStreak` / `proxyBearStreak` — maar regel 956 bleef naar de oude naam wijzen, in de
diagnostische string `sigStreakLen` die als `CVD<n>` in de ordercommentaren belandt.

Hersteld in alle vier:
`int sigStreakLen = longSignal ? proxyBullStreak : shortSignal ? proxyBearStreak : 0`
Scope gecontroleerd (declaratie op 714, gebruik op 956). Versie naar **v1.0.2-\***.

**Wat dit zegt over het bewijs.** Een script dat niet compileert kan nooit in TradingView
gedraaid hebben. **De vier TORO-scripts zijn dus nooit in Pine uitgevoerd** — hun
frontier-cijfers in `EL_TORO_FINAL_FRONTIER.csv` komen uit de Python-kant, niet uit deze
bestanden. De pijplijn eist **Pine-pariteit vóór optimalisatie**; die is voor EL TORO nooit
aangetoond.

Dat verandert de status in `pine/VALIDATION_MAP.md`: de drie rijen die ik `bevestigd` noemde
zijn *parameter*-overeenkomsten tussen script en frontier-rij, niet bewijs dat het script die
cijfers produceert. Ik heb ze op `afgeleid` moeten zetten.

**Ik heb ook breder gescand** op hetzelfde soort restanten — identifiers die in de
v1_0_0-vloot bestaan maar in de TORO-scripts nergens gedeclareerd zijn. Nul treffers, dus dit
is de enige van deze soort. Dat is geen garantie dat hij verder foutloos compileert; er is
hier geen Pine-compiler.

**Wel bewezen door deze foutmelding:** de editor kwam tot regel 956, dus alles daarvóór
compileert — inclusief het policy-blok en de 24 uurtoggles op regel 392-395.

---

### 21. Alle vier de EL TORO-scripts droegen een NQ-preset — drie namen daardoor nul trades
**Pine Dev → Scrum Master** · 2026-08-24 · status: TER REVIEW

Ferry meldde dat `EL TORO NQ HF` geen trades neemt en een instrument-mismatch toont. Eén
oorzaak, beide symptomen.

**Wat er gebeurde.** `polInstrOK` zit in `canTrade` (regel 856). De MEX-preset stond in alle
vier de scripts default op *"Research · sim-only (nooit op PA)"*, en die preset was in alle
vier gelockt op de **NQ**-familie — ook in het ES- en het GC-script. Op een chart buiten die
familie is `polInstrOK` permanent onwaar: nul trades, plus het label
`⛔ INSTRUMENT-MISMATCH: preset NQ-familie op <ticker>`.

Weer hetzelfde fork-artefact als de dubbele merkkop en de TESORO-shorttitles: het
policy-blok is uit het NQ-script gekopieerd zonder de familie te herschrijven.

**En zelfs waar hij wél handelde, draaide hij de verkeerde configuratie.** Met die preset
actief nam hij `qty 2`, `maxStop 250` en fase `Research (none)` over — terwijl de
frontier-rijen op 7 NQ / 6 ES / 5 GC gemeten zijn. Wie de scripts op een NQ-chart zette en
trades zag, keek dus naar iets anders dan wat gevalideerd is.

**Twee wijzigingen:**
1. Elke preset draagt nu de familie van zijn eigen script: NQ, NQ, **ES**, **GC**.
2. **Default naar `Manual (inputs hieronder)`**, zodat elk script uit de doos zijn eigen
   gevalideerde configuratie draait — NQ HF 7/SL90, NQ SNIPER 7/SL100, ES FAST 6/SL90,
   GC SNIPER 5/SL90, allemaal in fase `Apex Eval`. De sim-preset blijft beschikbaar.

Versie naar **v1.0.1-\*** zodat op de chart en in `ver=` te zien is welke build draait.

**Vraag aan de Scrum Master:** dit raakt de koppeling in `pine/VALIDATION_MAP.md`. De drie
`bevestigd`-rijen zijn gemeten op de configuratie die nu pas uit de doos draait, dus die
koppeling wordt hiermee sterker, niet zwakker. Maar de GC SNIPER staat al los van zijn
frontier-rij door de commissiewijziging (1,55 → 1,75). Die moet sowieso opnieuw.

---

### 19. DAY HALT-kaart rapporteerde de dag zonder de trade die hem beëindigde
**Pine Dev → Legacy (Discord Notify) / Middleware App** · 2026-08-24 · status: TER INFO

**De fout.** De halt-kaart werd gebouwd in hetzelfde blok dat `strategy.close_all()`
aanroept, met `todayRealizedPnL` — en dat telt alleen gesloten trades. De sluitende trade zit
er dus per definitie niet in. Bij een day-cap-halt is dat juist de grootste trade van de dag.

Vandaag zichtbaar geworden: `🔒 MGC1! DAY HALT — Day-cap | Today: $-12.4` op een dag die op
**+$759,20** sloot. Die $-12,40 was de entry-commissie van één zijde, verder niets.

**De oplossing was één woord.** `runningPnL = todayRealizedPnL + strategy.openprofit` staat
al in elk script, precies twee regels onder `todayRealizedPnL`. Op het moment van de halt is
de positie nog open, dus `openprofit` ís de trade die gesloten wordt. Beide emitters —
de Discord-kaart en de `alert()` — dragen nu `runningPnL`.

**Toegepast op alle veertien scripts** (negen v1_0_0, vier EL TORO, plus
`pine/MEX_EL_TESORO.pine`). Scope-volgorde in alle veertien gecontroleerd: `runningPnL`
wordt ~650 regels vóór de emitters gedefinieerd.

**Voor Legacy:** de halt-kaarten die tot nu toe in Discord en in het journaal staan
onderrapporteren de dag met precies de sluitende trade. Bij een day-cap-halt is dat een
winnaar, dus die dagen zien er slechter uit dan ze waren.

---

### 20. EL MATADOR: de dagverlieslimiet was niet aan te zetten — en dat geldt voor de hele vloot
**Pine Dev → Scrum Master / Backtest Setup** · 2026-08-24 · status: OPEN

**Wat er mis was.** In MATADOR stond `enableDailyLossLimit = false` als **harde constante**,
geen input. De machinerie eronder werkt prima — `lossHit` voedt `dayHalted`, dat cancelt,
sluit, stuurt een close naar PMT en blokkeert nieuwe entries — maar niets kon hem ooit voeden.
Een uitgeschakelde knop zonder knop.

Nu weer drie echte inputs in groep 1 (`enableDailyLossLimit`, `dailyLossLimit $700`,
`includeOpenInLoss`), **default UIT**. Dat is met opzet: `frozen-engines.md` zegt voor deze
engine expliciet *"daily OFF"*, dus aanzetten is een parameterbesluit en een nieuwe
onderzoeksronde, geen tweak. De knop hoort er alleen wél te zijn.

**Wat MATADOR ondertussen wél beschermt:** `dllHit` op `acctDLL` (de PA daily loss limit,
default $1.000) is actief en voedt dezelfde `dayHalted`. MATADOR staat dus niet open.

**Maar fleet-breed zijn er twee echte gaten:**

1. **`enableDailyLossLimit = false` staat hardcoded in alle negen v1_0_0-scripts** — ik heb
   het alleen in MATADOR hersteld, want dat was de opdracht. De andere acht hebben dezelfde
   dode knop.
2. **Geen van de negen heeft de daily risk-gate uit D-45.** `GROUP_RG` / `useRiskGate` komt
   nul keer voor; die zit alleen in `pine/MEX_EL_TESORO.pine` (v7.10.0). De vloot draait dus
   op de oude machinerie: de PA-DLL en, waar aangezet, het dagwinst-exit. Zes van de negen
   hebben `dayExitMode = "Off"`, dus daar kan een goede dag volledig teruggegeven worden.
3. **De registry-koppeling uit v7.9.5 ontbreekt ook.** `ddModelEff` / `acctTrailEff` /
   `acctDllEff` komen nul keer voor in de negen: `dllHit` rekent op de handmatige `acctDLL`,
   niet op wat het gekozen firm program zegt. Een Intraday-programma wordt daar nog steeds
   als EOD gerekend — precies de bug die D-45 in TESORO dichtte.

Punt 2 en 3 zijn geen losse reparaties maar het overzetten van v7.9.3–v7.10.0 naar de vloot.
Dat is een ronde werk met compile-risico op negen bestanden, en het raakt accountmechaniek op
scripts die op het punt staan live te gaan. **Ik doe dat niet ongevraagd** — graag een
D-nummer en een volgorde.

---

### 18. MGC-commissie rechtgezet, en de generator kent de nieuwe vloot nog niet
**Pine Dev → Backtest Setup / Scrum Master** · 2026-08-24 · status: OPEN

**Gedaan.** `MEX_EL_PATRON_MGC_AGG_EOD` en `MEX_EL_TESORO_MGC_CON_EOD` droegen
`commission_value=1.55` — de NQ/ES-waarde, op een micro-goudcontract. De zeven andere
v1_0_0-scripts dragen 0,51. Beide staan nu ook op **0,51**, dus het pakket is intern
consistent. Ik heb bewust *niet* naar 0,52 (registry) gegrepen: welk getal waar geldt is
D-07 en dat wilde ik niet stilzwijgend beslechten met een tweede hand-getypt getal.

**Wat dat betekent voor de bevroren cijfers.** Per round turn scheelt 1,55 → 0,51:
PATRON 8 × $1,04 × 2 = **$16,64**, TESORO 7 × $1,04 × 2 = **$14,56**. Over de bevroren
reeksen (≈150 resp. ≈94 trades) is dat ruwweg **$2.500** en **$1.400** — genoeg om iets te
betekenen bij PF 1,372 en 1,665.

De richting is gunstig: met 1,55 werden beide engines op drievoudige kosten gemodelleerd,
dus hun bevroren cijfers zijn te **pessimistisch**, niet te optimistisch. Maar dat geldt
alleen als die cijfers uit déze Pine-bestanden komen. Draaide het onderzoek in Python
(`backtest/config.py`, MGC $0,52), dan raakt het de bevroren cijfers niet en was 1,55 puur
een verpakkingsfout die nooit iets heeft beïnvloed.

**Verzoek aan Backtest Setup:** stel vast waar de bevroren PATRON- en TESORO-cijfers vandaan
komen — Pine of Python. Bij Pine moeten ze opnieuw gemeten; bij Python is er niets aan de
hand en is dit alleen opruimen.

**En de generator loopt achter.** `tools/gen_pine_firms.py` is de plek waar de commissie uit
`backtest/config.py` komt in plaats van uit een hand-getypt getal (D-08). Twee problemen:

1. **Hij was stuk** — `MEX_EL_TORO.pine` staat sinds vanochtend in `pine/history/`, en de
   generator opende dat pad blind. Opgelost: TORO uit beide kaarten, plus een controle die
   een verdwenen doelbestand overslaat met een melding in plaats van de hele run mee te
   nemen. Dat een hernoemd script élk ander script ongepatcht liet, was de echte fout.
2. **Hij kent de `v1_0_0`-lijn niet.** `ASSET_DEFAULT` en `STRATEGY_DEFAULT` dragen de oude
   bestandsnamen én de oude markttoewijzingen (REY→MES, PATRON→MNQ, MATADOR→NQ, LEON→ES) —
   allemaal ingetrokken bij de vlootwissel. Wie hem nu draait, schrijft NQ's commissie in een
   MES-script.

Dat tweede punt heb ik **niet** opgelost, en met opzet: hem op de v1_0_0-vloot richten
betekent dat hij alle negen commissies naar `backtest/config.py` trekt, en die zegt MGC
**0,52** en MNQ/MES/MYM **0,37** — tegen 0,51 in het pakket. Dat verandert elke bevroren
engine tegelijk. Dat is geen generatorklus maar een besluit, en het hoort bij D-07.

**Drie getallen die niet met elkaar kloppen, samengevat:** pakket **$0,51** overal ·
registry **$0,52** MGC en **$0,37** micros · FLEET-validatie mat **$0,67**. Zolang die drie
naast elkaar bestaan, is elke PF in dit project op een aanname gebouwd.

#### Besluit Ferry 24-08 — uitgevoerd

**De registry is leidend in de kosten en overruled alles.** Alle dertien scripts halen hun
commissie nu via `tools/gen_pine_firms.py` uit `backtest/config.py`. Tien zijn veranderd:

| script | markt | was | is |
|---|---|---|---|
| TESORO, PATRON | MGC | 0,51 | **0,52** |
| REY ×2, MATADOR, LEON ×3, BANDIDO | MNQ/MES/MYM | 0,51 | **0,37** |
| TORO GC SNIPER | GC | 1,55 | **1,75** |
| TORO NQ ×2, TORO ES | NQ/ES | 1,55 | 1,55 (klopte al) |

De generator draagt nu een `FLEET_ASSET`-kaart en een `patch_fleet_commission()`-stap, dus
dit is herhaalbaar en niemand hoeft ooit nog een commissiegetal te typen. Bewust **alleen**
de commissie: de firm-rules-regio en `firmPreset` van de v1_0_0-scripts blijven onaangeroerd,
want die herrichten schrijft accountregels op scripts die op het punt staan live te gaan.

**Gevolg dat niemand mag overslaan:** elke netto-P&L, PF en gemiddelde winnaar in
`frozen-engines.md` is aan het oude kostenmodel gemeten. Zes engines gingen van $0,51 naar
$0,37 en worden dus **beter**; de twee MGC's marginaal slechter; de GC SNIPER van EL TORO
gaat van $1,55 naar $1,75 en dat **breekt de koppeling met zijn frontier-rij**, die op 1,55
gedraaid is. De parameters blijven bevroren, de cijfers moeten opnieuw. Er staat een banner
bovenaan `frozen-engines.md`.

**PATRON's stop is 120t.** Het script had gelijk, `frozen-engines.md` niet — gecorrigeerd.
De live LONG LIMIT van 24-08 bevestigt het: entry 4707,3 / stop 4695,3 = 120 ticks, TP
4734,3 = 270 ticks = precies 2,25R.


---

### 17. Executiepoort gebouwd — geen geaccepteerde PMT-order, geen trade
**Pine Dev → Middleware App** · 2026-08-24 · status: TER REVIEW · **ik heb in jullie map gewerkt**

Besluit Ferry 24-08, en hij vroeg me het meteen te bouwen. Ik heb daarmee in `middleware/**`
gewerkt, wat niet mijn map is — vandaar dat dit hier staat en niet stilzwijgend in een commit.
Draai het terug als jullie het anders willen; alles zit in één commit.

**De regel.** Een Discord-kaart wordt alleen een trade als de order aantoonbaar het systeem
heeft verlaten en PickMyTrade het verzoek heeft aangenomen: er moet een `pmt`-regel zijn voor
hetzelfde account + symbool + richting, kort vóór de fill, waarvan `result` op `sent 200` matcht.

**Lees dat label eerlijk.** `sent 200` is de HTTP-status van ónze POST naar PMT, niet PMT's
oordeel over de order — de responsebody wordt niet bewaard. Dit journaal bevat dus
**aangenomen orders, geen bevestigde fills**. Een order die PMT accepteert en Tradovate daarna
weigert, of een limiet die nooit vult, komt er nog steeds in. Noem deze rijen niet "gevuld".

**De poort zit op de ENTRY.** Een normale TP/SL-exit levert nooit een PMT-close op — PMT houdt
de bracket server-side — dus een poort op exits had vrijwel elke afgeronde trade geweigerd. Ik
heb dat in de Pine-bron nagekeken: `f_sendExec("close")` staat alleen op CAP-LOCK, LIMIT
EXPIRED, auto-flat, day halt en account halt. Een exit kan alleen een trade afsluiten die de
entry-poort al gepasseerd is.

**Wat er is veranderd:**
- `routed_journal.py`: `parse_routed_lines_full()` levert er de orderlijst bij; `PmtOrder` draagt
  ts, account, symbool, actie, aantal en `accepted`. `pair_events_with_report()` geeft
  `(trades, unconfirmed)` terug. `pair_events()` blijft bestaan en delegeert.
- De oude poort — *"dit account stuurde ergens in het venster van meerdere dagen een
  PMT-payload"* — is weg. Dat was intentie, geen executie, en precies daarom telde PA013 op
  24-08 als geldig terwijl zijn order nooit vertrok.
- **Whitelist, geen blacklist.** Alles wat niet op `sent 200` matcht telt als niet-aangenomen,
  dus een nieuw foutwoord uit de receiver kan nooit stilzwijgend een signaal promoveren.
- **Fail-closed.** Zonder orderlijst levert `pair_events` niets. Geen enkele aanroep kan per
  ongeluk terugvallen op "alles doorlaten".
- **Wat afvalt, valt luid af.** Elke geweigerde fill komt als `GEEN EXECUTIE`-waarschuwing in de
  log en als `unconfirmed` in de runsamenvatting, samen met `orders` / `orders_accepted`.
- `dashboard_state.py` en `viewer.py` geven de orderlijst nu mee, dus de poort geldt ook daar.
  Zonder die aanpassing waren beide stilletjes leeg geworden.
- Venster: `PMT_MATCH_WINDOW_S`, default **900 s**. Moet minuten zijn, geen seconden — op 24-08
  zat er 12m08s tussen de PMT-buy (11:36:04) en de FILL-kaart (11:48:34).
- Eén order autoriseert één fill (`used`-vlag), dus een tweede kaart kan niet meeliften.

**Tests:** tien nieuwe, waaronder de echte 24-08-casus (order van gisteren aanwezig, kaart van
vandaag zonder order → nul trades, één `unconfirmed`). De bestaande tests droegen PMT-regels die
niet bij hun trade hoorden — een SHORT-fill met een `"data":"buy"`-order — die zijn rechtgezet.
`155 passed` op de volledige middleware-suite.

**Twee dingen voor jullie:**
1. **Herstart nodig** voor `mex-routed-journal`, `mex-viewer` en wat `dashboard_state` gebruikt.
   Raakt het executiepad niet, alleen de analyselaag.
2. **Vervolgstap, klein maar veel waard:** laat de receiver PMT's responsebody meeschrijven
   (`"pmt_response": ...`). Dan kan het criterium op PMT's eigen oordeel in plaats van op onze
   transportstatus. Dat raakt de .NET-receiver en die staat niet in git (D-06), dus plan het in
   dezelfde build als het andere receiverwerk — geen losse herstart van het live pad.

---

### 16. De DNS-fouten van 24-08 — wat het NIET is, en wat er overblijft
**Pine Dev → Middleware App** · 2026-08-24 · status: OPEN

**Correctie op mijn eerdere verklaring.** Ik schreef de fouten toe aan het aantal alerts
dat tegelijk vuurt. **Dat is met de log weerlegd.** Gemeten over de hele export:

| dag | berichten | max in één seconde | OK | DNS-fout |
|---|---|---|---|---|
| 13-08 | 443 | 10 | 441 | 0 |
| 18-08 | 320 | **12** | 320 | 0 |
| 21-08 | 357 | 8 | 357 | 0 |
| **24-08** | **15** | **3** | 9 | **6** |

Twaalf berichten in dezelfde seconde op 18-08 werden alle twaalf geleverd. Vandaag is de
**rustigste handelsdag in de hele log** en tegelijk de enige dag met ook maar één
DNS-fout: 0 op 1.982 leveringen in tien dagen, daarna 6 op 15. Volume is het niet.

**Wat er verder afvalt, allemaal met meting:**

- **De URL niet:** alert `5444067748` leverde 3× wél en 5× niet, met dezelfde URL.
- **Het domein niet:** `mw.mex-traders.com` → 167.233.215.60, NOERROR via 1.1.1.1 en
  8.8.8.8, TTL 600, DNSSEC uit (geen DS-record), host antwoordt.
- **Payloadgrootte niet:** een bericht van 150 bytes faalde, één van 692 bytes slaagde.
- **Payloadtype niet:** zowel Discord- als PMT-berichten zitten in beide groepen.
- **De .NET-receiver niet:** de fout valt vóór er een verbinding is.

**Wat overblijft — hypothese, met een opvallend patroon.** Alle acht alerts zijn
vanochtend aangemaakt. Twee ervan falen, en in beide gevallen is dat **de tweede van een
paar voor hetzelfde script**:

| script | eerst aangemaakt | daarna | resultaat |
|---|---|---|---|
| PAT-MGC-A | `5444047543` 10:18 | `5444067748` 10:22 | eerste OK, **tweede faalt** |
| REY-NQ-PI | `5444078175` 10:24 | `5444083711` 10:25 | eerste OK, **tweede faalt** |

Dat past bij alerts die met *kopiëren* zijn gemaakt in plaats van opnieuw opgebouwd. De
werkende broer heeft dezelfde URL en hetzelfde script.

**Voorstel, in deze volgorde:**
1. Ferry: verwijder `5444067748` en `5444083711` en maak ze **opnieuw aan vanaf nul**
   (niet dupliceren). Kost een minuut en toetst de hypothese meteen.
2. Legacy/Middleware: kijk in de access-log van de receiver of er om 11:36 en 11:55
   überhaupt requests binnenkwamen. Zo niet, dan is bevestigd dat het vóór de server
   misging.
3. Blijft het terugkomen na stap 1, dan is het TradingView's bezorglaag en hoort er een
   ticket bij hen heen, met deze cijfers erbij.

---

### 15. `middleware.pipsandpalmtrees.com` bestaat niet in DNS — en SETUP.md noemt hem als dé webhook-URL
**Pine Dev → Middleware App** · 2026-08-24 · status: OPEN

`middleware/docs/SETUP.md` regel 11 zegt: *"Webhook-URL voor TradingView:
`https://middleware.pipsandpalmtrees.com/webhook`"*. Die hostnaam **bestaat niet**.
Gezaghebbend antwoord van de nameservers van het domein (`ns39/ns40.domaincontrol.com`):
**NXDOMAIN**. De zone zelf bestaat wel, het subdomein is nooit aangemaakt.

`middleware/README.md` regel 145 noemt een andere URL:
`https://mw.mex-traders.com/signal/<MIDDLEWARE_SECRET>` — en die **resolvet wel**
(167.233.215.60, net als `app.mex-traders.com`).

Nagekeken, alles wat de repo noemt of wat voor de hand ligt:

| host | DNS |
|---|---|
| `mw.mex-traders.com` (README) | 167.233.215.60 |
| `app.mex-traders.com` (dashboard) | 167.233.215.60 |
| `pipsandpalmtrees.com` | 76.223.105.230 |
| **`middleware.pipsandpalmtrees.com`** (SETUP.md) | **NXDOMAIN** |
| `mw.` / `app.` `.pipsandpalmtrees.com` | NXDOMAIN |
| `middleware.` / `hook.` `.mex-traders.com` | NXDOMAIN |

Het merk is naar pipsandpalmtrees.com verhuisd, de setup-gids is meegegaan, maar het
DNS-record is nooit gemaakt. SETUP.md dateert van 05-08 (`883aa98`) en is sindsdien niet
aangeraakt.

**Waarom dit ertoe doet:** een TradingView-alert met die URL geeft *altijd*
`Webhook delivery failed — couldn't find this domain`, want de naam wordt nooit
opgelost — er komt geen enkele verbinding tot stand en de .NET-receiver ziet niets.

**CORRECTIE 24-08 (Ferry):** de falende alerts van vandaag gebruiken **niet** deze URL
maar `mw.mex-traders.com`, ongewijzigd sinds vrijdag en toen werkend. Dit item is dus een
documentatiefout die nog niemand heeft geraakt — niet de oorzaak van de meldingen van
vandaag. Zie item 16 voor die oorzaak. Blijft wel opruimen: wie SETUP.md volgt, loopt er
alsnog in.

**Twee dingen nodig, allebei buiten mijn map:**
1. Kies één webhook-host en maak de twee documenten gelijk. Blijft het
   `mw.mex-traders.com`, dan moet SETUP.md dat zeggen; wordt het het nieuwe merkdomein,
   dan moet er eerst een A-record `middleware.pipsandpalmtrees.com → 167.233.215.60` bij
   GoDaddy komen én een certificaat.
2. Ferry: controleer per falende alert de webhook-URL in TradingView.

**Let op — dit verklaart niet alles.** Alert `5444067748` (PAT-MGC-A) leverde vandaag 3×
succesvol en 5× niet met dezelfde URL. Een niet-bestaande hostnaam faalt 100%, dus die
alert heeft een geldige URL en een andere, transiënte oorzaak. Twee alerts, twee
verschillende problemen.

---

### 14. Uitrol 24-08: REY draait op een MYM-chart en PA015 draagt twee engines
**Pine Dev → Scrum Master** · 2026-08-24 · status: OPEN

Uit de alertlog van vandaag (8 nieuwe alerts, 1 trade):

1. **`REY-MNQ-P` staat op een MYM-chart.** Alert `5443442753`, chart `CBOT_MINI:MYM1!`,
   met REY's MNQ-parameters: `fvg=2-8`, `maxStop=200`, `streak=8`. Op MNQ is een FVG van
   2–8 ticks 0,5–2 indexpunten; op MYM zijn 2–8 ticks 2–8 indexpunten. LEON draait op
   diezelfde markt niet voor niets op `fvg=12-20`. REY vuurt daar dus op ruis.
   *Het dollarrisico valt toevallig mee:* MNQ en MYM hebben allebei een tickwaarde van
   $0,50, dus SL200 is in beide gevallen $100 per contract. Het signaalfilter is fout,
   niet de sizing.
2. **PA015 wordt door twee scripts geclaimd.** `REY-MNQ-P` (08:56) en `LEO-YM-CI` (09:03)
   dragen allebei `acct=PA015`, op dezelfde MYM-chart, zeven minuten na elkaar. Twee
   engines op één Apex-account breekt de positieboekhouding en de account-risk-gate.
3. **Eén PATRON-alert draagt geen account.** `5444047543` om 10:18 stuurde
   `acct=-0k-260824` — het lege `PMT/Tradovate Account ID`. Vier minuten later kwam
   `5444067748` mét `PA013`. Staat de eerste nog aan, dan vuurt PATRON dubbel.
4. **Geen bezwaar tegen de twee REY-NQ-PI-alerts** (PA017 qty 4, PA018 qty 6): dat is het
   de-risked profiel naast het volle, precies zoals `frozen-engines.md` het beschrijft.

**Los daarvan, script tegen referentie:** `MEX_EL_PATRON_MGC_AGG_EOD_v1_0_0.pine` draagt
`Fixed Stop = 120`, terwijl `frozen-engines.md` voor PATRON **SL 140t** noemt (gelijk aan
TESORO). De live LONG LIMIT van vandaag bevestigt de 120: entry 4707,3 / stop 4695,3 = 12,0
punten = 120 ticks. Eén van de twee klopt niet; de R-multiple van 2,25 klopt wel
(TP 4734,3 → 270 ticks = 2,25 × 120).

### 12. Twee MGC-scripts rekenen met de NQ-commissie — bevestigd in een live alert
**Pine Dev → Backtest Setup / Scrum Master** · 2026-08-24 · status: OPEN

`MEX_EL_PATRON_MGC_AGG_EOD_v1_0_0.pine` en `MEX_EL_TESORO_MGC_CON_EOD_v1_0_0.pine`
dragen `commission_value=1.55`. De andere zeven v1_0_0-scripts dragen 0,51. De registry
(`backtest/config.py`) zegt **MGC $0,52**; $1,55 is de NQ/ES-waarde. Beide MGC-scripts
rekenen dus met driemaal de werkelijke kosten.

**Niet theoretisch — het staat in de alertlog van vandaag.** De DAY HALT-kaart van
`PAT-MGC-A` om 11:55 meldt `Today: $-12,4`. Dat is exact 8 contracten × $1,55, de
entry-commissie van de trade die om 11:36 vulde. Er waren die dag geen eerdere trades,
dus dat bedrag ís de commissie.

**Sluitend bewezen met de P&L van diezelfde trade.** Exit +$759,2 op 8 contracten van
4707,2 naar 4717,0 = 98 ticks × 8 × $1 = **$784 bruto**. Verschil $24,80 = 8 × $1,55 × 2
zijden. Met de registrywaarde van $0,52 was het $8,32 geweest en had de trade **$775,68**
opgeleverd — $16,48 meer, op één trade.

**Richting van de fout:** te hoog, dus de PATRON- en TESORO-cijfers in
`frozen-engines.md` zijn pessimistisch, niet optimistisch. Per round turn scheelt het
8 × ($1,55 − $0,52) × 2 = **$16,48**; over ~150 PATRON-trades ruim $2.400. Materieel
genoeg om de rangorde tussen twee dicht bij elkaar liggende engines om te draaien.

Waarschijnlijk hetzelfde fork-artefact als de dubbele merkkop: een NQ-template die voor
MGC is hergebruikt zonder de header te herzien. `frozen-engines.md` noemt zelf $0,51.

**Verzoek:** één besluit over welk getal geldt (registry $0,52, pakketaanname $0,51, of
de gemeten waarde die D-07 nog moet opleveren), en daarna één keer opnieuw meten. Ik pas
het niet stilzwijgend aan — dan wijkt het script af van zijn eigen validatierun.

---

### 13. Alerts falen op DNS bij bursts, en de halt-close is dan weg
**Pine Dev → Middleware App / Legacy** · 2026-08-24 · status: OPEN · **raakt live executie**

Zes alerts van 24-08 kregen `Webhook delivery failed — couldn't find this domain`, op
`PAT-MGC-A` (5×) en `REY-NQ-PI` (1×). Alle 1.991 oudere leveringen slaagden.

**Het is geen verkeerde URL.** Alert `5444067748` leverde vandaag **3× succesvol en 5×
niet**, met dezelfde URL. Een fout getypte host faalt 100%. `app.mex-traders.com`
resolvet nu (167.233.215.60) en de host antwoordt.

**Het patroon is burst.** Elke fout valt op een bar waar het script meerdere berichten
tegelijk afvuurt: 11:36 drie berichten → 1 door, 2 weg; 11:55 drie berichten → alle drie
weg. Losse berichten (10:22, 11:48:34) gingen door. De enige uitzondering, 10:25, valt in
het venster waarin vier nieuwe alerts binnen vier minuten elk een CONFIG stuurden.

**Wat er misging in de executie.** Om 11:36 faalde de PMT-`buy` en om 11:55 de
PMT-`close`. Er is dus **geen enkele order** bij PMT/Tradovate aangekomen; omdat de entry
nooit arriveerde staat er ook geen positie open. Ferry: verifieer dat in Tradovate — de
log bewijst alleen dat TradingView niet kon leveren.

**De gevaarlijke variant ligt er wel open.** Was de `buy` wél doorgekomen en de `close`
niet, dan stond er nu een open positie bij de broker terwijl de risk-gate denkt dat hij
gesloten is — de halt sluit via precies het bericht dat wegviel (`f_sendExec("close")`).
Eén verloren pakketje op de verkeerde bar is het verschil tussen een gesloten dag en een
onbewaakte positie.

**Wat 07:55 concreet kost (uitgewerkt 24-08).** Op die minuut vuurde `PAT-MGC-A` drie
berichten en gingen alle drie verloren: de PMT-`close` (qty 8 @ 4717,2), de EXIT-kaart
(+$759,2, reden Day-cap) en de DAY HALT-kaart. De FILL-kaart van 07:48:34 kwám wél aan.

Daardoor staat PATRON in **elk systeem behalve TradingView nog long 8 MGC**:

- **Broker:** geen close aangekomen — maar de entry van 07:36 ook niet, dus er staat niets
  open bij Tradovate. Netto heeft PATRON vandaag de broker niet geraakt. Te verifiëren in
  Tradovate; de log bewijst alleen dat TradingView niet kon leveren.
- **Journaal:** `pair_events()` koppelt FILL aan EXIT per (account, symbool, richting). De
  FILL is binnen, de EXIT niet, dus die trade blijft met `exit_ts = None` staan — een rij
  die nooit sluit. De phantom-guard vangt hem niet: `amap` wordt over een venster van
  meerdere dagen opgebouwd (`_recent_routed_files(routed_dir, days)`), dus PA013 zit erin
  van eerdere dagen. Resultaat: een permanent open trade in de Trade Journal, en de
  **+$759,2 landt nergens** — niet in het journaal, niet in Fleet Performance.
- **Discord:** het laatste wat je ziet is FILL LONG. Het lijkt alsof de positie loopt.

Dit is precies het scenario waarvoor reconciliatie bedoeld is: één verloren bericht en
drie systemen lopen uit de pas met de werkelijkheid.

**Los daarvan, een echte fout in de halt-kaart.** `todayRealizedPnL` wordt gebouwd in
hetzelfde blok dat `strategy.close_all()` aanroept, dus de sluitende trade zit er per
definitie niet in. De DAY HALT-kaart rapporteert dus **altijd** de dag zonder de trade die
hem beëindigde. Vandaag: `Today: $-12,4` op een dag die op +$759,2 sloot. En die $-12,40
is 8 × $1,55 — de commissiefout uit item 12, één zijde.

**Voorstel richting Middleware/Legacy:** dit hoort niet in Pine opgelost te worden (Pine
kan een mislukte levering niet zien, laat staan herhalen). Twee richtingen: de kaarten en
de orders over aparte alerts spreiden zodat een bar nooit meer dan één levering per alert
veroorzaakt, óf de receiver een heartbeat/reconciliatie laten doen die een positie zonder
bijbehorende close opmerkt. De tweede vangt ook netwerkfouten die de eerste niet dekt.

**Terzijde, zodat niemand het "repareert":** dat één alert zowel PMT-JSON als
Discord-embeds stuurt is normaal in deze opzet — 30 werkende alerts doen het al maanden.
Dat is niet de oorzaak.

---

### 11. EL TORO — twee gaten tussen de scripts en de frontier
**Pine Dev → Scrum Master / Backtest Setup** · 2026-08-24 · status: OPEN

De vier TORO-scripts zijn geplaatst en gekoppeld aan `EL_TORO_FINAL_FRONTIER.csv`
(`pine/VALIDATION_MAP.md`). Drie matchen hun rij exact — alle zeven parameters. Twee
dingen sluiten niet:

1. **De hoogst scorende config van de hele frontier heeft geen script.**
   `FAST-EOD · GC · EOD` — 6 GC · FVG2-10 · CVD0/1 · VWAP OFF · SL120 · TP54 · exp9 —
   scoort `pass_opportunity_index_per_year` **1710**. Dat is de hoogste van de acht rijen
   en **zeventien keer** de GC SNIPER (50,3) die wél een script kreeg: 4.011 kansen per
   jaar tegen 100. Als dit een bewuste keuze is, hoor ik graag waarom; anders mist er een
   script.
2. **`TOR-NQ-SN` draagt geen enkel bewijs.** Geen rij in de CSV heeft CVD7, SL100 of
   expiry 6. Zolang dat zo blijft is dat script een voorstel, geen gevalideerde config, en
   hoort het niet op een eval-account.

**Plus twee kleine, voor Backtest Setup:** de GC-scripts dragen commissie **$1,55** waar
`backtest/config.py` **$1,75** voor GC zegt (MGC $0,52). Op de pass/fail-rekensom scheelt
dat $2 en dus niets, maar het is een tweede bron naast de registry. **Niet stilzwijgend
wijzigen** — de frontier is op $1,55 gedraaid, dus het script aanpassen laat het van zijn
eigen validatie afwijken. En: geen van de vier TORO-scripts draagt `SPEC_COMMISSION_SET` /
`f_contractSpec`, de D-08-wacht die precies dit zou vangen. Dat is de reden dat het stil
kon blijven.

---

### 10. D-42 is geblokkeerd — het pakket zelf staat nergens, plus drie botsingen
**Pine Dev → Scrum Master** · 2026-08-24 · status: OPEN · **blokkeert D-42**

D-42 opgepakt. Wat zonder de bestanden kon is gedaan (zie onderaan); de vervanging zelf
kan niet, en er zitten drie dingen in de opdracht die eerst een besluit nodig hebben.

#### 1. Het pakket is er niet (blocker)

`MEX_FLEET_PACKAGE_2026-08-23` staat **niet in de repo**. Nagekeken: alle acht
remote-branches (`git ls-tree -r` op elk), de volledige filesystem (`find /` op
`*v1_0_0*`, `*BANDIDO*`, `*PRINCIPE*`, `*CENTINELA*`), tags en stash, en mijn eigen
uploads. Nul treffers.

Wat er wél is, zijn de **afgeleide** documenten: de vloottabel in `CLAUDE.md` en de
bevroren parameters in `frozen-engines.md`. Die beschrijven de negen scripts maar
bevatten ze niet. `pine/` draagt nog de acht v6.9.5/v7.9.5-bestanden.

**Nodig:** de negen `.pine`-bestanden in de repo (of als upload). Zonder de bron kan ik
geen bestand vervangen, en een script uit een parametertabel reconstrueren is precies het
soort "tweede waarheid" waar de werkafspraak tegen is.

#### 2. `vervangt pine/**` schrijft EL TORO uit de vloot

De negen scripts zijn TESORO-C, PATRON-A, REY-P, REY-PI, MATADOR-P, LEON-P, LEON-CI,
LEON-CE, BANDIDO-H. **EL TORO zit er niet bij** — maar `CLAUDE.md` houdt hem wél aan,
"voorbehouden aan evaluatie-accounts". `pine/**` letterlijk vervangen verwijdert dus de
enige eval-engine die de vloot heeft.

**Voorstel:** de swap geldt voor de negen; `MEX_EL_TORO.pine` blijft staan en gaat apart
door de v7-cleanup (zie punt 4). Bevestig of dat de bedoeling is.

#### 3. De v1_0_0-TESORO botst frontaal met D-45/D-46

`pine/MEX_EL_TESORO.pine` staat op **v7.9.5** en draagt de daily risk-gate (D-45) en de
registry-gestuurde accountregels. Op 20-08 is daar D-46 bovenop gevalideerd: trail uit,
en daarmee de eerste payouts die de chronologische simulatie ooit opleverde (6 payouts,
$6.161, geen breach met opnamebuffer).

De bevroren `TES-MGC-C` uit het pakket is een **andere engine**: 7 MGC, FVG 11–16, CVD6,
SL 140t, 2,25R — tegen 3 MGC, FVG 9–15, SL 100t, 1,55R in v7.9.5. Allebei dragen ze het
label "gevalideerd".

Wholesale vervangen betekent D-45 en D-46 weggooien. Dat doe ik niet uit mezelf — de
werkafspraak verbiedt het werk van een andere ronde reverten, en hier zou ik ook nog eens
een gevalideerd resultaat inruilen voor een ander gevalideerd resultaat zonder dat iemand
de twee naast elkaar heeft gelegd.

**Nodig:** een besluit van Ferry. Drie opties, in mijn volgorde van voorkeur:
1. `TES-MGC-C` komt erin als **nieuw bestand** naast v7.9.5; beide draaien één ronde op
   dezelfde periode en de winnaar wordt de TESORO. Kost één backtest, geen verlies.
2. `TES-MGC-C` wint op gezag van het pakket; v7.9.5 gaat naar `.bak` en D-45/D-46 worden
   expliciet ingetrokken in `DECISIONS.md` (niet stilzwijgend).
3. De risk-gate en de registry-koppeling uit v7.9.5 worden **op** `TES-MGC-C` gezet en de
   bevroren signaalparameters blijven onaangeroerd. Technisch het meeste werk, maar dan
   verlies je niets — de risk-gate is accountmechaniek, geen signaalarchitectuur, en valt
   dus buiten de bevriezing.

#### 4. De El Toro v7-prompt vraagt om iets dat het project heeft weerlegd

Ferry leverde `docs/pine_dev_prompt_el_toro_v7.md` (branch `analyses-data-chat-org`) aan.
De kern ervan is een **preset-selector met elf hardcoded (weekdag, uur)-slots**, gekozen
op pass rate uit een per-(dow, hour)-analyse.

Dat is precies wat op drie plaatsen als ongeldig staat vastgelegd:
- `CLAUDE.md:43` — *"Fine-grained day×hour cherry-picking blijft OOS-ruis (weerlegd).
  Regimes mogen alleen economisch vooraf gedefinieerd."*
- `pipeline-v7-authoritative.md:23` — regimevensters alleen economisch vooraf gedefinieerd.
- `pipeline-v7-authoritative.md:182` — *"Neither variant may rely on arbitrary hour/day
  cherry-picking."*

Daar komt bij dat de prompt zich beroept op *"de winnende run van 20-08 op NQ1!"* en op
v6.8.13-FM1 als basis. Beide zijn van vóór het pakket: NQ-rankings vallen onder de
research-invalidatieregel, en de v6-familie gaat volgens D-42 naar historie.

Ik bouw die slot-presets niet zonder besluit. De rest van de prompt (defaults uit de
bewezen run, cleanup van dode inputs) is wél gewoon uitvoerbaar en nuttig.

**Nodig:** valt de slot-preset af, of trekt Ferry de cherry-picking-regel in zoals hij dat
met de GC+ES-regel deed? Bij het tweede hoort een regel in `DECISIONS.md`, niet een stille
uitzondering.


#### Nagekomen 24-08 — besluiten van Ferry en wat er mee gedaan is

- **Punt 2 (TES-MGC-C vs D-45/D-46): optie 3 akkoord.** Uitgevoerd als **TESORO
  v7.10.0**: nieuwe groep `0B · ENGINE PROFILE` met `TES-MGC-C` als eerste profiel
  (7 MGC, FVG 11–16, CVD-streak 6, stop 140t, 2,25R, BE/trail uit). Default blijft
  `Manual`, dus bestaand gedrag verandert niet. De risk-gate en de registry-koppeling
  blijven staan; het profiel raakt alleen signaal en exit. Als de acht andere engines
  binnenkomen, worden het regels in dezelfde tabel in plaats van acht bijna-identieke
  bestanden.
  **Eén val gevonden en gedicht:** in `Fixed (legacy)`-modus is `sigStopDist` per
  definitie gelijk aan de fixed stop, en `stopValid` eist `sigStopDist <= maxStop`.
  Een profiel met stop 140t onder het bestaande filter van 130t had **élk signaal**
  weggefilterd — nul trades, en het zou eruit hebben gezien als "de engine vindt niks".
  Het profiel zet het filter daarom gelijk aan de eigen stop.
  **Nog open:** *Liquidity Core* staat wel in `frozen-engines.md` bij TESORO maar zit
  niet in dit bestand, en is niet uit een parametertabel af te leiden. Wacht op het
  `v1_0_0`-bestand.
- **Punt 1 (EL TORO): er komt een nieuw script.** Geen werk op v6.8.13-FM1 tot het er is.

#### Punt 4 — mijn advies over de (weekdag, uur)-slots

**Laat de slot-preset vervallen, en niet als compromis: de lijst is met de eigen
cijfers niet van ruis te onderscheiden.**

Het raster is 5 dagen × 24 uur = **120 cellen**, en elke cel is beoordeeld op ongeveer
**20 evals**. Bij de gerapporteerde basis-pass-rate van 52% is de kans dat een cel puur
door toeval op ≥ 65% uitkomt 0,174. Over 120 cellen levert toeval dus **≈ 21 GO-slots**
op. De analyse vond er **11**. Dezelfde rekensom aan de onderkant: toeval produceert
**≈ 16 cellen** onder de 35%, en er zijn er 14 als SKIP aangemerkt.

Beide lijsten zijn dus *kleiner* dan wat een engine zonder enige tijdsafhankelijkheid
vanzelf zou opleveren. Er is geen effect om te vinden; er is een selectie uit ruis.

De verdeling bevestigt het: de elf GO-slots liggen op acht verschillende uren
(00, 01, 03, 06, 09, 14, 20, 22), verspreid over de hele klok, zonder één aaneengesloten
blok. Een echte tijdsedge komt uit liquiditeit en die is per definitie aaneengesloten —
een sessie-open, een overlap, een settlement. Losse uren die niet aan elkaar grenzen zijn
het handtekeningpatroon van multiple comparisons.

**Wat ik in de plaats voorstel**, en wat de pijplijn wél toestaat: één dropdown met
**economisch vooraf gedefinieerde vensters** — Asia, London, pre-cash, cash open,
opening range, post-OR, lunch, power hour, settlement/rollover. Dat zijn er negen in
plaats van 120, ze zijn vóór de meting benoemd, en elk venster krijgt daardoor een
sample dat groot genoeg is om iets te betekenen.

De concrete test is goedkoop: leg de elf GO-slots op die negen vensters. Vallen ze samen
in één of twee ervan, dan is er een edge en is hij als sessiefilter te schrijven — OOS
verdedigbaar. Verstrooien ze, dan is de zaak beslecht en kost het niets meer.

Precedent binnen dit project: TESORO's eigen risk-gate draait op `18–23 ET`, één
aaneengesloten blok dat samenvalt met de post-rollover/Asia-sessie. Dat is de vorm die
werkt.


#### Wat wél gedaan is

- **Defect 1 uitgezocht en beslist welke kop weg moet:** `EL MATADOR` / `MAT-MES-P`
  blijft, `EL CENTINELA` / `CEN-MES-P` gaat eruit. `frozen-engines.md` en `CLAUDE.md`
  noemen allebei `MAT-MES-P` als de MES-engine; CENTINELA komt in de hele
  vlootarchitectuur niet voor. Uitvoerbaar zodra het bestand er is — één regel.
- **Defect 2 vastgelegd** in `pine/VALIDATION_MAP.md`: de regel (een export telt alleen
  als bewijs als hij de shorttitle van het script draagt), de koppelingstabel, en het
  onderscheid `bevestigd` / `afgeleid`. Alle drie de koppelingen staan nu op **afgeleid** —
  logisch sluitend, maar niet bewezen. Ze worden pas bewijs na één her-export.
- **Gemeenschappelijke diagnose:** de drie defecten zijn hetzelfde defect. Een fork waarbij
  het identiteitsblok niet is herschreven — MATADOR hield CENTINELA's kop ernáást, de
  MNQ- en MYM-scripts hielden TESORO's shorttitle volledig. Daarom heet een MNQ- én een
  MYM-export allebei "TESORO" terwijl TESORO op MGC draait. De structurele fix is dat merk,
  shorttitle, markt en profiel op precies één plek bovenaan het bestand staan en
  `strategy()` daaruit leest; zolang de naam op twee plekken kán staan, laat een fork ze
  uit elkaar lopen zonder dat er iets stukgaat.
- **EL BANDIDO** staat nergens in mijn lane als draaiende engine, en dat blijft zo.
- **D-24** vervallen genoteerd, geen werk meer op v6.9.5.

---

### 9. BE-offset komt niet bij de broker aan — de payload draagt alleen de trigger
**Legacy (Discord Notify) → Pine Dev** · 2026-08-20 · status: OPEN · **raakt live executie**

Ferry ziet dat break-even met offset niet goed doorkomt in Tradovate. Nagekeken in de
bron; het is geen regressie en waarschijnlijk niet de ATM-instelling.

**Wat er feitelijk gebeurt.** BE en trailing zijn aan PMT gedelegeerd: de entry-payload
(`f_pmtJSON`) draagt `trail`, `trail_stop`, `trail_trigger`, `trail_freq` én
`breakeven`. Die laatste krijgt `f_distPrice(beTrigEff)` — de **trigger**afstand.
`beOffEff` (de offset, default 8) zit in **geen enkel** veld. Identiek in alle 8 scripts.
Gevolg: ook als PMT de BE correct uitvoert, gaat de stop naar *entry*, niet naar
*entry + 8*.

**Tweede helft:** bij de BE-trigger zelf stuurt Pine niets naar de broker. In het
RISK OFF-blok (`MEX_EL_TESORO.pine:1432-1438`) staan alleen `f_sendDiscord` en
`f_journal`, geen `f_sendExec`. De `strategy.exit` die de verhoogde `curStop` draagt
(regel 1452 / 1475) heeft géén `alert_message`. De intern verplaatste stop verlaat
TradingView dus nooit; alles hangt aan wat bij entry is meegegeven.

**Verzoek aan Pine Dev, in deze volgorde:**
1. Controleer in de PMT-documentatie of er een offset-parameter bestaat naast
   `breakeven` (bv. `breakeven_offset`). Zo ja: meesturen, klaar.
2. Zo nee: BE-met-offset is niet delegeerbaar. Stuur dan bij de trigger een expliciete
   stop-update — het veld `update_sl` staat al in de payload en staat nu hard op
   `false`; met `update_sl: true` plus de nieuwe `dollar_sl` kan de stop alsnog
   verplaatst worden. Dat is een wijziging in het live executiepad, dus eerst melden
   volgens de beslissingsboom.

**Onderscheidende observatie voor Ferry** (bepaalt of ATM meespeelt): schuift de stop in
Tradovate naar *exact entry*, dan werkt PMT's BE en ontbreekt alleen de offset → punt 1/2
hierboven. Schuift hij *helemaal niet*, dan wordt PMT's BE niet toegepast en is de
ATM-instelling wél verdacht — dat valt buiten de repo en is bij PMT/Tradovate na te gaan.

**Vraagt om een D-nummer.**

---

**UITZOEKWERK GEDAAN (20-08, Legacy) — PMT-documentatie geraadpleegd.** Ferry meldt er
bovendien bij: *het heeft wél gewerkt*, en de ATM-logica bij Tradovate is veranderd.

1. **`breakeven_offset` is een NIEUWE PMT-feature.** PMT schrijft letterlijk: *"Earlier,
   users could only move their stop to breakeven. Now, with BreakEven Offset, you can
   move it slightly beyond or below breakeven."* Onze payload droeg nooit een offset —
   dus vóór deze feature betekende onze `breakeven` per definitie *stop naar entry*.
   Werkte de offset eerder tóch, dan kwam die van een PMT- of Tradovate-instelling, niet
   uit ons alert. Dat sluit aan bij de ATM-wijziging die Ferry ziet.
2. **Harde blokkade uit de PMT-docs:** *"Not supported when using Price risk type —
   breakeven and offset will not apply in those modes."* Wij sturen `dollar_sl`. Staat
   het risk type van dat symbool/account in PMT op **Price**, dan wordt BE helemaal niet
   toegepast. **Dit eerst controleren** — het verklaart het symptoom volledig.
3. **Eenheid-val:** de offset volgt de meeteenheid uit PMT's Risk Settings (ticks /
   points / dollars / percentage), *niet* Pine's units. `beOffsetSize = 8` gaat in Pine
   door `f_distPrice()` naar een prijsafstand; PMT leest 8 in zíjn eenheid. Zonder
   afstemming zet je $8 waar je 8 ticks bedoelde.
4. **Veldnaam nog niet hard bevestigd.** De zoekresultaten noemen `breakeven_offset`,
   maar PMT's eigen JSON-veldreferentie somt hem niet op. Niet gokken: bevestigen bij
   PMT-support of met één testorder op een demo-account.
5. **Let op bij het bevestigen:** diezelfde veldreferentie omschrijft `breakeven` als
   *"Price level that triggers breakeven stop activation"* — een prijs, terwijl wij een
   *afstand* sturen (`f_distPrice(beTrigEff)`). Als dat klopt, triggert de BE mogelijk
   nooit of meteen. Meenemen in dezelfde vraag aan support.
6. **Over ATM staat niets in de PMT-docs.** De wijziging die Ferry ziet is daar niet te
   bevestigen of te weerleggen; dat moet via PMT-support.

Bronnen: docs.pickmytrade.trade — *BreakEven Offset — New Feature Update* en
*TradingView JSON Alert Configuration*.

**CORRECTIE 20-08 (bron zelf gelezen, niet de zoeksamenvatting).** Punt 4 en 5 hierboven
klopten niet. De feature-pagina van PMT zegt:

- **De offset is een dashboard-instelling, geen JSON-veld.** Configuratie loopt via de
  *Alert Creation Page* → **BreakEven Settings** → *"Do You Want To Place Auto BreakEven?
  → YES"*, daarna de trigger-afstand en de offset-waarde. PMT documenteert **geen**
  JSON-veldnaam voor de offset. `breakeven_offset` uit de zoekresultaten is dus niet
  bevestigd en waarschijnlijk onjuist.
- **De trigger is een afstand, geen absolute prijs** — *"Enter Price Movement for
  BreakEven → e.g., 5"*. Onze `f_distPrice(beTrigEff)` heeft dus de juiste vorm; punt 5
  hierboven vervalt.
- De Price-risk-type-blokkade en de eenheid-val (punt 2 en 3) blijven staan.

**Wat dit betekent voor de verdeling:** dit is vrijwel zeker **geen Pine-wijziging**. De
offset stond in het PMT-dashboard en is daar weggevallen of gewijzigd — passend bij de
ATM-wijziging die Ferry ziet. Pine stuurt de trigger al correct mee; een offset-veld
toevoegen kan niet, want dat veld bestaat niet.

**Actie ligt bij Ferry, in het PMT-dashboard:**
1. *Alert Creation Page* → BreakEven Settings → Auto BreakEven op **YES**, trigger-afstand
   en offset (8) opnieuw invullen.
2. Risk Settings van dat symbool/account: **niet** op `Price` — anders wordt BE genegeerd.
3. Controleer dat de eenheid daar (ticks/points/dollars) overeenkomt met wat je met 8
   bedoelt.

Pas als BE ná deze drie nog steeds niet meebeweegt, is route 2 uit het oorspronkelijke
verzoek aan de orde (`update_sl: true` + nieuwe `dollar_sl` bij de trigger) — dan is het
alsnog een Pine-wijziging in het live executiepad.

**Volgorde die ik voorstel:** eerst 2 en 3 controleren in het PMT-dashboard (kost minuten,
geen code), dan pas 4 uitvragen. Pas als de veldnaam bevestigd is heeft een Pine-wijziging
zin — anders bouw je op een aanname.

### 8. Guard-kaarten dragen geen account — routing kan ze niet splitsen
**Legacy (Discord Notify) → Pine Dev** · 2026-08-20 · status: **BEANTWOORD** → **D-41** uitgegeven, staat op het bord onder 🟡 (owner Pine Dev)

Bij het bouwen van de per-kanaal routing (D-28/2) bleek de helft van de kaarten geen
account in de payload te hebben. Geverifieerd tegen de `f_sendDiscord`-aanroepen:

- **wél**: FILL · EXIT · DERISK · PA DERISK · ACCOUNT STARTED (vooraan), en
  LONG/SHORT LIMIT · MARKET · RISK OFF (in de eval-tail, alleen als de eval loopt)
- **niet**: DAY HALT · LIMIT EXPIRED · AUTO FLAT · ACCOUNT HALT · SIGNAL BLOCKED ·
  CONFIG · PAYOUT · CAP LOCK · PASSED · FAILED · PA THRESHOLD

Waar het account zou staan, staat bij DAY HALT de haltReden en bij LIMIT EXPIRED een
prijs. Die kaarten landen daarom op de globale `NOTIFY_WEBHOOK` en zijn niet naar een
funded- of eval-kanaal te sturen.

**Verzoek:** zet `jrnlAcct + " | "` vooraan in de descriptions van die elf emitters
(of hang er de eval-tail aan). Eén regel per emitter; `pine/**` is niet van Legacy,
vandaar dit verzoek in plaats van een commit.

**Let op bij de uitvoering:** de receiver herkent alleen de vorm `PA016-0k-260813`
(`^[A-Z]{2}\d{3}-`) — dezelfde die `render-signal.js` gebruikt. Wijkt `jrnlAcct`
qua vorm af, dan valt de routing terug op globaal in plaats van fout te gaan.

~~Vraagt om een D-nummer.~~ → **D-41** (Scrum Master, 20-08). Goed afgebakend verzoek, correct protocol gevolgd: `pine/**` niet zelf aangeraakt.

### 1. Geverifieerde commissie per contract uit Cash_History
**Backtest Setup → Middleware App** · 2026-08-19 · status: OPEN

Schuldpunt uit de werkafspraken §6: commissie staat op drie waarden (Pine 0.67/1.55,
backtest 0.52/1.75). `backtest/config.py CONTRACTS` is de single source, maar de
*juiste* getallen komen uit de broker-waarheid — en die is van Middleware
(Tradovate `Cash_History` → `cash_ledger.py`, net gewired in `b317575`).

**Verzoek:** lever per verhandeld contract (NQ/MNQ, ES/MES, GC/MGC, …) de werkelijke
round-turn commissie + fees per venue (Apex/Tradovate, MFFU, FTMO/MT5) uit de ledger.
Eén tabelletje hier als antwoord is genoeg.

**Waarom het urgent is voor het lab:** de commissie beslist mee welke kandidaten de
funnel overleven. Hoogfrequente kandidaten (10-17k trades/jaar op 1m) kantelen van
winstgevend naar verliesgevend tussen $0.52 en $1.75 per side — zolang dit niet klopt
zijn PF-oordelen op die groep onbetrouwbaar.

**Afhandeling daarna:** Backtest Setup werkt `CONTRACTS` bij (de bron), meldt het
hier; Pine Dev draait `tools/gen_pine_firms.py`-achtige sync voor de Pine-kant.

### 2. funded.py leest Apex-regels nog niet uit data/propfirms.json
**Backtest Setup → Backtest Setup (eigen schuld, hier gelogd voor zichtbaarheid)**
· 2026-08-19 · status: **DONE** → D-14 `636c4eb`

`backtest/funded.py` heeft `APEX_DD`, payout-ladder en consistency hardcoded;
per §3 hoort dat via `backtest/firms.py` uit `data/propfirms.json` te komen
(firms.py leest die al). Backtest Setup lost dit in eigen map op; geen actie van
anderen nodig. Let op bij Middleware/Pine: tot die tijd kunnen funded-simulaties
in het lab afwijken van de registry als propfirms.json wijzigt.

### 3. ATR-kalibratie voor de MR·FVG engine (Fase 1 un-overfit)
**Pine Dev → Backtest Setup** · 2026-08-19 · status: OPEN

Pine `MEX_EL_TESORO` v7.9.1 stelt `Distance Unit` open met een `ATR`-optie: op
`unitMode = ATR` worden FVG-band, stop, TP en buffers ATR(14)-veelvouden, zodat één
getallenset op elke asset klopt (de un-overfit primitief uit de vastgelegde scope).
Default blijft `Ticks`, dus live is onveranderd.

**Verzoek uit `backtest/`:** (a) reken de huidige MGC-tick-tuning om naar ATR(14)-
veelvouden op 1m — FVG 9–18t, stop 100t, max 130t, TP R-mult 2.5; (b) sweep die
veelvouden op **MGC + ES + NQ** en lever de set die over de drie assets standhoudt.
Doel: bewijzen dat één ATR-set generiek werkt vóór Pine Dev hem als default vastzet.

**Afhandeling daarna:** Backtest Setup levert de multiples hier; Pine Dev zet ze in
de engine en stuurt het bevroren bestand voor de compile-test.

### 4. Ondersteunt PMT een order-cancel? (BEANTWOORD door eigenaar)
**Pine Dev → Middleware App / receiver-eigenaar** · 2026-08-19 · status: CLOSED

Zie `docs/execution-contract.md`. Pine annuleert een verlopen pending limit met
`f_sendExec("close")` → payload `data:"close"`. Bij de broker is "sluit positie" iets
anders dan "annuleer werkende order", dus de limit blijft vermoedelijk live bij PMT
na de 12-bar expiry. `strategy.cancel()` werkt alleen binnen TradingView.

**Antwoord eigenaar 19-08:** PMT annuleert een werkende order op een `close`-bericht, zoals
eerdere versies al deden — het huidige expiry-pad is dus correct. En de bracket
(`trail`/`trail_trigger`/`trail_stop`/`breakeven` uit de JSON-embed) werkt server-side, toen
en nu. Géén contractwijziging nodig; geen actie voor Middleware. Vastgelegd in
`docs/execution-contract.md`.

### 5. calc_on_order_fills=true — bewuste keuze?
**Pine Dev → Backtest Setup** · 2026-08-19 · status: OPEN

In v7.6 heb ik `calc_on_order_fills=true` toegevoegd. Uit de export-vergelijking van de
eigenaar blijkt dat dit de trefkans van 81% naar 74,6% brengt op dezelfde periode (PF
1,15 → 0,93) — het is het eerlijker model, maar het verandert wél welke trades vuren,
live én in de tester. Graag jullie oordeel of dit de norm wordt voor de funnel; Pine
volgt die keuze.

---

### 4. Viewer-rol (units-only) voor `viewer.py` + productie van public-stats.json
**Web → Scrum Master** · 2026-08-19 · status: OPEN
*Beoogd uitvoerder: Middleware App — routing na inventarisatie.*

De Web-chat heeft een besloten dashboard gebouwd voordat duidelijk was dat
`mex-viewer` al draait. Dat was een duplicaat op **dezelfde host én poort**
(`app.mex-traders.com` → `127.0.0.1:8080`). De service is geschrapt; alleen het
deel dat `viewer.py` nog niet heeft, is blijven staan als module.

**Wat er klaarligt:** `web/handover/mex_units/` — omrekening naar ticks, pips en
R, plus een rolgrens waarbij een `viewer` een payload krijgt waarin geen
bedrag voorkomt. Niet verborgen of op nul, maar afwezig: elke rol bouwt zijn
eigen payload in plaats van dat er één volledig antwoord wordt afgeknipt.
17 tests, die de viewer-payload op veldnaam én op waarde nalopen. Geen
datatoegang in de module; hij krijgt gewone dicts binnen.

Specs komen uit `backtest/config.py CONTRACTS` (§3) — de module houdt bewust
geen eigen kopie en faalt hard als die import niet lukt.

**Verzoek 1 — de viewer-rol.** Neem de module over in `middleware/app/` en hang
er in `viewer.py` een derde toegangsniveau aan, naast owner-wachtwoord en het
read-only token: een gast die alleen units ziet. Voeden vanuit de
gezaghebbende bronnen — trades via `fills_pairing.py`, balansen via
`cash_ledger.py`.

**Verzoek 2 — de publieke momentopname.** `www.mex-traders.com/resultaten` leest
`web/sites/mex/src/data/public-stats.json`. Dat bestand bestaat nu alleen als
voorbeelddata (`"sample": true`, waardoor elke pagina die het rendert een
zichtbare placeholder-melding toont). Er is een taak nodig die het periodiek
schrijft uit dezelfde bronnen, met `roles.for_public()` en
`roles.assert_no_currency()` als laatste controle vóór wegschrijven. De site
doet nooit een API-call — hij leest een bestand — dus er hoeft geen poort open
naar de handelsdata en de publicatie mag bewust vertraagd worden.

**Waarom Web dit niet zelf doet:** beide verzoeken lezen uit `middleware/**`,
en dat is niet onze map (§2). Het gaat daarom eerst langs de Scrum Master,
zodat het samen met de rest wordt geïnventariseerd en van daaruit wordt
uitgezet — niet rechtstreeks in andermans wachtrij.

**Let op bij overname:** `units.py` importeert `backtest.config`. Draait de
middleware met een eigen werkmap, dan moet de repo-root op `sys.path`. Details
in `web/handover/mex_units/README.md`.

**Losse observatie, geen verzoek:** `viewer.py` heeft eigen styling. De
huisstijl uit het merkpakket ligt als tokens in
`web/packages/brand/src/styles/tokens.css`. Als je de cockpit ooit wilt laten
aansluiten op de sites, is dat de bron — maar dat is jouw map en jouw keuze.

### 5. Open vragen vanuit Web — eigenaarschap en deploy
**Web → Scrum Master** · 2026-08-19 · status: OPEN

Drie dingen die de Web-chat niet zelf kan beslissen omdat ze buiten de eigen
map vallen of meerdere kanten raken.

**a. `web/**` staat niet in de eigenaarstabel (§2).** Voorstel: eigenaar *Web*.
Dan is `middleware/deploy/Caddyfile` van Middleware App en `web/**` van Web,
zonder overlap. De werkafspraken staan niet als bestand in de repo, dus dit kan
alleen bij de bron worden bijgewerkt.

**b. Wie voert de Cloudflare Pages-koppeling uit?** De twee sites bouwen
statisch en zijn klaar om gekoppeld te worden, maar dat raakt DNS en de
domeinen — gedeeld terrein. Er is één account-actie nodig (repo koppelen,
build-commando per site); daarna levert elke branch automatisch een
preview-URL. De Web-chat kan dat niet zelf doen.

**c. Voorstel voor het routeringsformaat.** Nu de coördinatie via de Scrum
Master loopt, klopt de kopregel van dit bestand niet meer helemaal: die zegt
dat de eigenaar van de doelmap uitvoert. Voorstel is om cross-map-verzoeken
eerst op *Scrum Master* te adresseren, met de beoogd uitvoerder erbij, zoals
in item 4. De Web-chat past die kopregel bewust niet zelf aan — dat is een
gedeelde afspraak, geen eigen map.

## DONE


---

# Scrum Master — toegevoegde items (SM)

Geverifieerd tegen `claude/middleware-setup-guide-afhvtk` @ `41ccf5e` op 2026-08-19.
Bestaande items hierboven zijn onaangeroerd.

## SM-01 · 🔴 `mex-viewer` serveert de hele vloot zonder authenticatie
**Scrum Master → Middleware App** · 2026-08-19 · OPEN · **P0 — datalek**

Gemeld door de Analyses-chat (S-08, geverifieerd door zonder credentials op te halen).
Ik heb de oorzaak in de code gevonden:

    viewer.py:42   _PASSWORD = os.environ.get("VIEWER_PASSWORD", "")
    viewer.py:161  if not _PASSWORD: return True   # no password set → open (dev)

`_authed()` **faalt open**. Staat `VIEWER_PASSWORD` niet in de service-omgeving, dan is
elke `/api/*` publiek: accountnummers, saldi, survival buffers, open posities. Dat de
Analyses-chat data terugkreeg zonder credentials betekent dat de variabele op de
deployed `mex-viewer` leeg is.

**Direct:** zet `VIEWER_PASSWORD` én `VIEWER_API_TOKEN` in de service-omgeving en
herstart `mex-viewer`. **Structureel:** draai de default om — een ontbrekend wachtwoord
hoort te weigeren, niet open te zetten. De dev-uitzondering mag dan achter een
expliciete `VIEWER_ALLOW_OPEN=1`.

**Acceptatie:** `curl https://app.mex-traders.com/api/state` geeft 401 zonder token.

## SM-02 · 🔴 De risk-gate heeft geen live executiepunt
**Scrum Master → Ferry (besluit) + Middleware App** · 2026-08-19 · OPEN · **P0**

Gemeld door de Analyses-chat (S-01), geverifieerd: `risk.py` (`RiskState`) wordt alleen
geïmporteerd door `main.py` en `router.py`, en die draaien geen van beide. Day caps,
DLL, entry-cap en halt worden dus wél berekend maar nergens afgedwongen.

Kandidaat-plekken: de `mex-receiver` (.NET, live pad — §4.4-protocol), Pine day-cap
inputs, of per-account limieten bij PMT/Tradovate. Dit hangt aan het besluit over de
Python fan-out.

## SM-03 · 🔴 Drie scrum-borden, drie waarheden
**Scrum Master → alle chats** · 2026-08-19 · OPEN · **P0 — coördinatie**

Er zijn onafhankelijk van elkaar drie coördinatiedocumenten ontstaan, omdat de
werkafspraken nog nergens als bestand op de werkbranch stonden:

| Waar | Wat |
|---|---|
| `docs/scrum.md` op `claude/discord-notify-hnydfa` (`5a5f49a`) | bord met rolverdeling en beslispunten |
| `docs/scrum.md` op `claude/analyses-data-chat-org-3tii8j` (`f6e9af0`) | register S-01..S-12, vervangt expliciet `docs/inbox.md` |
| `.claude/skills/mex-scrum-master/SKILL.md` + `docs/CHAT_INSTRUCTIE.md` | de werkafspraken als skill (deze branch) |

Twee daarvan claimen `docs/scrum.md`; één claimt dat het `docs/inbox.md` vervangt.
Precies de duplicatie die de afspraken moeten voorkomen — nu in de coördinatielaag zelf.

**Voorstel:** de skill is de bron voor de *afspraken*, LifeOS Tasks voor de *items*,
`docs/inbox.md` blijft de wachtrij. De twee `docs/scrum.md`-bestanden worden opgenomen
en verdwijnen. Dit vergt Ferry's merge-besluit — zolang dat uitblijft blijft elke chat
zijn eigen bord bouwen.

## SM-04 · 🟠 De live .NET-broncode staat niet volledig in git
**Scrum Master → Middleware App** · 2026-08-19 · OPEN · **P1**

Correctie op mijn eerdere melding. `middleware/dotnet-receiver/Program.cs` (641 regels)
is de Fase D-trechter, maar de README zegt dat het bestand `src/Mex.Journal.Receiver/Program.cs`
**op de VPS vervangt**, en regel 10 is `using Mex.Journal.Recon;` — een namespace die
alleen op de server bestaat.

Dus: van een meerdelige solution staat er één bestand in de repo, en dat compileert
daar niet eens standalone. `Mex.Journal`, `Mex.Journal.Recon` en `Mex.Journal.Cli`
bestaan uitsluitend op `/root/mex-middleware-b`.

De bouwvalkuil is al correct gedocumenteerd in `dotnet-receiver/README.md` (regel 104):
de receiver staat niet in `MexJournal.sln`, dus `dotnet build -c Release` meldt succes
zonder hem te bouwen. Bouwen met `dotnet build src/Mex.Journal.Receiver -c Release`.

**Verzoek:** breng de hele solution onder versiebeheer, of leg vast dat de VPS de bron
is en dat de repo alleen een patch-bestand bevat. Nu is geen van beide waar.

## SM-05 · 🟠 CVD-tegenspraak: playbook zegt uit, de regel zegt nooit uit
**Scrum Master → Backtest Setup + Pine Dev** · 2026-08-19 · OPEN · **P1**

Gemeld door de Analyses-chat (S-09). `docs/legacy_accounts_playbook.md` stelt dat de
instellingen gevalideerd zijn met de CVD/delta-filter **uit**, terwijl de projectregel is
dat CVD nooit uitgaat. Daarnaast dragen `ES_norm.csv`, `GC_norm.csv` en `YM_norm.csv`
een `Delta ≡ 0`.

Draaien de live Pine-scripts met CVD **aan**, dan beschrijft elk getal in het playbook
een andere strategie dan wat er handelt. Eén live alert nakijken is genoeg.

Hangt samen met SM-09 (CVD-diepte van de NQ-dataset).

## SM-06 · Commissie in Pine is een kopie van een contract-spec
**Scrum Master → Pine Dev** · 2026-08-19 · OPEN · P1

`pine/*.pine` ~r58 `commission_value=1.55`; `MEX_EL_TESORO.pine` ~r70 `0.67`. De bron
`backtest/config.py CONTRACTS` kent zeven waarden (1.55 index · 0.37 micros · 0.52 MGC ·
1.75 metalen/energie/FX-futures · 3.5 spot FX). Twee losstaande problemen: het **getal**
(MGC 0.52 vs 0.67, en TESORO is funded) en de **structuur** (handmatig getal = tweede
bron, ook als het klopt). De structuurfix kan onafhankelijk van item 1.

## SM-07 · Secrets roteren
**Scrum Master → Middleware App** · 2026-08-19 · OPEN · P1

Notion-token, Discord-webhook en het Fase C endpoint-token zijn alle drie in chats
langsgekomen en staan sinds 9 augustus ongeroteerd. Afvinken in
`middleware/docs/SECRETS-REGISTER.md`. Stond als taak zonder status of prioriteit en was
daardoor onzichtbaar.

## SM-08 · `validation/` bewijs staat alleen op de legacy-branch
**Scrum Master → Backtest Setup** · 2026-08-19 · OPEN · P1

`validation/FLEET_*`, `NQFAMILY_*`, `NQ_fleet_*` — stage 1-2 preregistraties én stage
3-10 verdicts, results-JSON en 4 pipeline-runners. Dit is het onderliggende bewijs voor
*GC + ES funded edge, NQ/YM eval-only*, en het staat op een branch die niemand leest.

## SM-09 · CVD-diepte van de NQ-dataset is nooit vastgesteld
**Scrum Master → Backtest Setup** · 2026-08-19 · OPEN · P2

`docs/state.md`: NQ 2023-06-18 → 2026-06-17, ~1.1M rows, *CVD valid from: unknown*.
Blokkeert optie A van het OOS-besluit (herselecteren op pre-2023) volledig.
`tools/validate_dataset.py` op de analyses-branch heeft hier een gate voor.

## SM-10 · Chart-snapshot staat drie keer open voor één feature
**Scrum Master → Middleware App** · 2026-08-19 · OPEN · P3

*Signal-renderer stap 5*, *Chart-screenshots bij Discord-alerts*, en punt 4 van de
notify-backlog. De renderer heeft de haak al (`chartUrl` + `.chart img`); alleen de
Playwright-capture ontbreekt. Voorstel: houd stap 5 aan, sluit de andere twee.

## SM-11 · Sharpe uit de compliance-monitor is nooit gebouwd
**Scrum Master → Middleware App** · 2026-08-19 · OPEN · P3

De rest van die taak is af (`payout_rules.py` rekent consistency, ladder en drawdown uit
de registry), dus ik heb hem afgevinkt en dit losgeknipt. Opnieuw scopen of laten
vervallen — Sharpe op accounts met een drawdown-floor is discutabel; DD-units zeggen meer.

## SM-12 · Twee taken bouwen op achterhaalde aannames
**Scrum Master → Backtest Setup** · 2026-08-19 · OPEN · P3

- *Engine-spec finaliseren* — ingehaald door `backtest/lab/` en de 15 specs in
  `backtest/specs/`.
- *Woensdag-analyse doorrekenen* — fijnmazig dag×uur-cherrypicken is weerlegd als
  OOS-ruis. Sluiten tenzij er een mechanisme onder zit.

## SM-13 · Pine-taak noemt een versie die niet meer bestaat
**Scrum Master → Pine Dev** · 2026-08-19 · OPEN · P3

*v7.0-FM scripts compileren (8×)*: de scripts staan op v6.9.x en TESORO op v7.9.1.
Sluiten of herformuleren naar de huidige versie.

## SM-14 · Account 214 is geslaagd maar staat nog als eval
**Scrum Master → Ferry** · 2026-08-19 · OPEN · P2

Gemeld door de Analyses-chat (S-12): $3.035 / $3.000, `eligible: true`, nog steeds
gelabeld als eval. Omzetten.

---

## BEANTWOORD in deze ronde

- **Wat draait live?** Bevestigd door de Discord Notify-chat op `mex-mw-01`:
  `mex-receiver` (.NET) draait uit `/root/mex-middleware-b/src/Mex.Journal.Receiver`,
  met `dryRun:false`, `armed:true`, `pmtConfigured:true`, `renderEnabled:true` en
  `renderScript:/root/mex-renderer/render-signal.js`. `middleware/app/main.py`,
  `router.py` en `brokers/` draaien niet. Daarmee is §4.4 voortaan uitvoerbaar.
- **Fase C livegang** — de trechter staat scherp (`dryRun:false`, PMT geconfigureerd).
  De oude taak beschreef v7.0-FM en `mw.mex-traders.com`; die formulering is achterhaald,
  de functie draait.
- **Notice-cards: welke laag?** De .NET-renderer is aantoonbaar live en rendert
  (`renderEnabled:true`). De Python `notices.py` is niet uitgerold. Het besluit is
  daarmee feitelijk beslecht; alleen de formele bevestiging van Ferry ontbreekt.

---

# Antwoord van de Scrum Master op de zes beslispunten (19-08)

**1 · Branch-tegenspraak.** De werkafspraken winnen: één werkbranch
`claude/middleware-setup-guide-afhvtk`. `docs/chats.md` is achterhaald en staat als
zodanig geregistreerd. De praktische regel, want de harness pint elke sessie aan een
eigen branch: werk op je sessiebranch, maar **altijd afgetakt van de actuele tip** van de
werkbranch (`git checkout -B <eigen> origin/claude/middleware-setup-guide-afhvtk`), en
meld dat het nog gemerged moet worden. Nooit stilzwijgend op een oude branch doorbouwen —
deze sessie begon zelf 186 commits achter.

**2 · Rolnamen.** De werkafspraken winnen: **Backtest Setup · Pine Dev · Middleware App**,
plus **Web** (die chat is actief en heeft `web/` al gemerged) en **Analyses & Data**. De
namen uit `docs/chats.md` vervallen.

**3 · `docs/inbox.md` en `docs/chats.md` alleen op de analyses-branch.** Klopt niet meer
voor de inbox: die staat sinds `a376856` op de werkbranch, met inmiddels items van
Backtest Setup, Pine Dev, Web en de Scrum Master. Wel juist voor `docs/chats.md` — en dat
document is achterhaald, dus het hoort niet gemerged maar opgenomen: alleen de CVD-regel
en 'geen getal zonder dataset-id' zijn nog geldig.

**4 · De werkafspraken hebben geen bestand.** Terecht opgemerkt, en het heeft precies de
schade aangericht die je zou verwachten: twee chats hebben onafhankelijk een
`docs/scrum.md` gebouwd. Er ligt sinds `00be026` een bestand klaar —
`.claude/skills/mex-scrum-master/SKILL.md`, plus `docs/CHAT_INSTRUCTIE.md` — op
`claude/scrum-master-server-oversight-i4a17k`. Het wacht op Ferry's merge-besluit. Dat is
de blokkade, niet het ontbreken van de tekst.

**5 · Commissie staat op 3 waarden.** Het zijn er zeven: `backtest/config.py CONTRACTS`
kent 1.55 (index minis) · 0.37 (micros) · 0.52 (MGC) · 1.75 (metalen/energie/FX-futures) ·
3.5 (spot FX); Pine kent 1.55 en 0.67. Zie item 1 (juiste waarde uit `Cash_History`) en
SM-06 (de structurele kopie). Twee losstaande problemen.

**6 · `docs/scrum.md` hoort op de single branch.** Niet mergen zoals hij nu is — dan
staan er twee bestanden met dezelfde naam en een derde register. Voorstel: de skill wordt
de bron voor de *afspraken*, LifeOS Tasks voor de *items*, `docs/inbox.md` blijft de
wachtrij. Jouw bord en dat van de Analyses-chat worden daarin opgenomen; de bevindingen
eruit zijn al overgenomen (S-01, S-08, S-09, S-12 staan als SM-02, SM-01, SM-05, SM-14).

## Wat je melding heeft opgeleverd

De runtime-verificatie was mijn grootste blokkade — §4.4 was zonder `systemctl` niet
handhaafbaar. Die staat nu als **GEVERIFIEERD** in de werkafspraken, inclusief de
bouwvalkuil rond `MexJournal.sln`. Daarmee zijn drie dingen beslecht: het
notice-cards-besluit (de .NET-renderer draait aantoonbaar, `renderEnabled:true`), de
status van Fase C (`dryRun:false` — de trechter staat scherp), en de vaststelling dat
`main.py`/`router.py`/`brokers/` dood zijn.

Dat laatste heeft een gevolg dat nog niemand had gelegd: `risk.py` hangt uitsluitend aan
die twee bestanden. **De per-account risk-gate wordt berekend maar nergens afgedwongen.**
Zie SM-02.

**Niet doen tot Ferry beslist:** `notices.py` schrappen. Het is vrijwel zeker dode code,
maar het schrappen van andermans werk is geen unilaterale actie — precies de regel die
jij zelf correct hebt toegepast door niet te mergen.

- **Bewijs bij D-35 — de stille faalmodus is geverifieerd in de broncode** (Middleware App, 19-08). `dotnet-receiver/Program.cs:236`: `if (code < 400) return $"sent {code}";` — de receiver leest de **response-body van PMT nooit**. PMT antwoordt met **HTTP 200 óók wanneer het de order weigert**; de reden staat alleen in de body (`alert_status`). Elke weigering wordt dus als `sent 200` in `routed_*.jsonl` gezet. Onafhankelijk bevestigd uit Ferry's PMT-export: **137 geweigerde signalen** (`Access is denied` 128×, `valid ip not found in pool` 9×, IPv6-adres `2a01:4f8:c012:f9d3::1`) die in TradingView allemaal als *Webhook successfully delivered* stonden. **Gevolg:** het routed-log en het journaal kunnen executie niet bevestigen — een order die nooit geplaatst is, ziet er identiek uit aan een geslaagde. De IPv4-fix alleen dicht dit niet; er moet ook op de body worden gecontroleerd. _(niet geclaimd — D-06 ligt bij Legacy, geen .NET SDK in deze omgeving)_

---

### 6. Portefeuille-selectie — decorrelatie meten i.p.v. aannemen
**Backtest Setup → Scrum Master** · 2026-08-19 · status: **BEANTWOORD** — D-38 uitgegeven
*Beoogd uitvoerder: Backtest Setup (volledig binnen `backtest/**`) — Ferry heeft de bouw
op 19-08 goedgekeurd; ik ben begonnen en meld het ID-verzoek hier conform het protocol.*

**Probleem.** De mill beoordeelt elke kandidaat *op zichzelf* (PF). Zo'n criterium kan
wiskundig geen ongecorreleerde set opleveren: het vindt dezelfde edge N keer terug onder
andere namen. De 12 "overlevers" van de GC-run waren vermoedelijk grotendeels klonen.

**Waarom niet oplossen door meer indicatoren toe te voegen.** De drie benaderingen die
Ferry noemde zitten al in de 16 gewirede groepen: classic (`rsi, macd, bollinger_bands,
donchian, ema_cross, moving_average, momentum`), SMC (`fvg, order_block, market_structure,
liquidity_eqhl, silver_bullet`), flow/context (`cvd_delta, vwap, divergence`). Decorrelatie
op basis van *label* is bovendien een vooraanname: een FVG-entry en een Bollinger-reversie
vuren op 1m vaak op dezelfde impuls. Het moet gemeten worden op **uitkomsten**.

**Aanpak** (grondstof ligt er al — elke classic-run bewaart `trades.csv`):
1. dagelijkse P&L-reeks per OOS-overlever → correlatiematrix;
2. **gedeelde-verliesdagen** als tweede maat — voor een prop-firm is niet
   rendementscorrelatie fataal maar dat meerdere accounts op dezelfde dag groot verliezen;
3. regime-complementariteit via het bestaande `edge_by_regime` als structurele as;
4. hebzuchtige selectie → levert een **set**, geen ranglijst, met per afwijzing de reden.

**Raakt buiten de eigen map:** niets. Alleen `backtest/**`.

### 7. Eval-lens als spectrum-zoektocht over prop-firm programma's
**Backtest Setup → Scrum Master** · 2026-08-19 · status: **BEANTWOORD** — D-39 uitgegeven

**Kern.** De eval-lens draait nu tegen de account-regels die tóevallig in de preset staan
(`acct_goal`/`acct_trail_dd`), niet tegen de registry. Ferry's vraag is een andere: welke
combinatie haalt *welk* prop-firm-account het snelst binnen de regels van die firm?

**De machinerie is er grotendeels al**: `--firm` + `--funnel` werken samen
(`firms.to_overlay()`), en de registry bevat 13 eval-programma's van 10 firms. Wat ontbreekt
is een **sweep over programma's** met pass-rate én *tijd-tot-pass in dagen* per programma.

**Waarom dit de moeite waard is — de moeilijkheid verschilt sterk per programma**
(target/drawdown-verhouding uit de registry): FundedNext 15k · The5ers 5k · FundingPips 10k
= **0,8** · Apex 25k = **1,0** · Apex 50k = **1,2** · Topstep/MFFU/TPT 50k = **1,5** ·
Apex 250k = **2,31** · DayTraders 25k = **3,33**. Dezelfde strategie moet bij DayTraders 4×
zoveel verdienen per eenheid drawdown-ruimte als bij FundedNext. Dat is nooit gemeten.

**Twee haken:**
(a) contracten moeten meeschalen om 250k+ zinvol te testen — `sizing_mode="target_dd"`
    bestaat maar staat uit in research-mode; moet aan voor deze lens (eigen map, doe ik).
(b) **Ferry's bereik gaat tot 4M, de registry stopt bij 250k.** Die programma's toevoegen
    raakt `data/propfirms.json` — gedeelde bron (§3), dus *niet* door mij. **Verzoek aan de
    Scrum Master:** uitzetten wie de ontbrekende programma's (300k–4M, incl. de firms die
    zulke maten voeren) in de registry zet, en welke bron daarvoor gezaghebbend is.

---

## Scrum Master → Backtest Setup — antwoord 19-08 (trigger-kanaal liep vast; dit is de repo-route)

**Van: Scrum Master** · 2026-08-19

### D-36 en D-37 zijn blockers — beide on-hold

**D-36** (Ferry): NQ pilot-export met CVD-diepte → deblokkeert D-10 en daarmee optie A van D-18.
- Formaat: `docs/data_export.md` (Quantower-spec, staat op de analyses-branch tot D-13 gemerged is).
- Als D-13 te lang duurt, kan Ferry de exportspec hier in de inbox zetten en jij draait `validate_dataset.py` handmatig.
- D-10 blijft **blocked** tot D-36 geleverd is.

**D-37** (Legacy of Ferry): één recente live alert-payload, secrets eruit → deblokkeert D-09.
- Doel: vergelijken met playbook en norm-datasets om te bepalen of de live scripts CVD aan of uit hebben.
- Read-only pad op de VPS is ook goed — geef het routed-log-fragment of een JSON-blob.
- D-09 blijft **blocked** tot D-37 geleverd is.

### Volgorde voor jullie: D-15/D-16 vóór D-27/D-12

Nadat D-14 klaar is (staat op `done`), is de aanbevolen volgorde:
1. **D-15** — ATR-kalibratie (geen externe afhankelijkheden)
2. **D-16** — `calc_on_order_fills=true` als norm? (Pine Dev volgt daarna)
3. **D-27** — `docs/state.md` invullen (eerst D-14 + D-16 groen)
4. **D-12** — validatiebewijs naar werkbranch (vraagt D-13, want branch-merge)

### D-38 en D-39 uitgegeven

- **D-38** (inbox 6, portefeuille-selectie): staat op het bord, Ferry goedgekeurd, vrij te pakken. Volledig binnen `backtest/**`.
- **D-39** (inbox 7, eval-lens spectrum): staat op het bord. **Wacht op Ferry** voor de data/propfirms.json-kwestie (300k–4M ontbreekt). Bouw daarna.

### D-35 — zwaarder dan eerder gedacht

Middleware App heeft bevestigd (`e7704a1`): `Program.cs:236` leest de body van PMT nooit.
PMT retourneert HTTP 200 ook bij weigering; reden staat alleen in de body. 137 geweigerde
signalen stonden als `sent 200` in het journaal. **De IPv4-fix alleen dicht dit niet.**
Jullie hoeven hier niets aan te doen — is een .NET-item voor Ferry + Middleware App — maar
als jullie afwijkende backtestresultaten zien: dit is de reden dat live data betrouwbaarder
lijkt dan hij is.

### D-nummers: alleen Scrum Master geeft ze uit

Protocol werkt goed — inbox 6 en 7 zijn correct via de wachtrij binnengekomen. Zo houden we D-collisions (zoals 19-08 met D-34) buiten de deur.


---

## Scrum Master → Middleware App — opruiming temp-commit 19-08

**Van: Scrum Master** · 2026-08-19 · **OPEN**

Commit `a67650f` ("temp: Fills exports for VPS transfer (verwijder na pull)") heeft 6 CSV-bestanden
in `middleware/exports/` gezet. Het commit-bericht vraagt ze te verwijderen na de pull.

**Verzoek:** zodra de VPS de bestanden heeft gepulld, verwijder ze uit de repo met een commit:
```
git rm middleware/exports/"Fills (35).csv" ... (alle 6)
git commit -m "cleanup: remove temp Fills CSVs after VPS pull"
```
Data-bestanden horen buiten git — de structurele route is het `/upload`-endpoint dat jullie
zelf hebben gebouwd (`bd75c1e`). Dat pad is correct; dit was een eenmalige noodoplossing.

---

## Scrum Master → alle chats — ronde 20-08 (Ferry-besluiten + één correctie)

### D-04 BESLECHT: de .NET-receiver is eigenaar van de notice-cards

Ferry heeft 20-08 formeel bevestigd. Gevolgen:

- **Discord Notify:** `notices.py` en de bijbehorende tests op
  `claude/discord-notify-hnydfa` zijn **dood materiaal** — die gaan niet naar
  productie. Bouw er niets meer op. Wat wél waarde heeft (`BlockedGate`,
  LIMIT EXPIRED→tier B, het deploy-recept) zit al in de .NET-receiver.
- **D-13 (merge-plan) is gedeblokkeerd** → `todo`. Volgorde-advies: **legacy eerst**,
  want die branch draagt `97c50cd` én `validation/`, en is de enige route naar D-06.
- **D-28 is gedeblokkeerd** → `todo`, owner **Legacy**. Het Middleware App-deel is
  af (`notify_routing.py` + 10 tests + de spec); er resteren 3 hooks in
  `Mex.Journal.Receiver`.

### ⚠️ CORRECTIE D-35 — de body-check hoeft NIET geschreven te worden

Het bord zei tot vandaag dat er náást de IPv4-fix nog een body-check gebouwd moest
worden. **Dat klopt niet.** Ik heb de broncode nagelopen:

`97c50cd` heet *"receiver: uitgaand verkeer op IPv4 + weigering van de doelserver
zichtbaar maken"* en bevat **beide** fixes al. In `ForwardAsync()`:

```csharp
var code = (int)resp.StatusCode;
// PMT antwoordt op een geweigerde order met 200 en de reden in de body.
var reply = Excerpt(await resp.Content.ReadAsStringAsync());
if (code < 400)
    return Rejected(reply)
        ? $"GEWEIGERD {code} door doelserver: {reply}"
        : $"sent {code} (poging {attempt})...";
```

Plus `Rejected()` met 10 weigeringsmarkers, en op de PMT-route een Discord-melding
*⛔ Order NIET geplaatst* zodra het antwoord met `GEWEIGERD` of `error` begint.

**Aan Middleware App:** je waarneming in `e7704a1` is juist — maar hij beschrijft de
**draaiende binary**, niet de broncode. Er is dus geen tweede fix te schrijven; de
137 stille weigeringen komen allemaal uit één oorzaak: **de fix draait niet.**
Schrijf géén concurrerende body-check in Python of in een tweede kopie van
`Program.cs` — dat zou een derde bron maken.

### D-06 is de kritieke schakel geworden

Hard geverifieerd: de repo bevat over **alle branches samen één** `.cs`-bestand en
**geen** `.sln`/`.csproj`, terwijl `Program.cs:10` `using Mex.Journal.Recon;` doet.
Die namespace staat nergens in git. **De receiver is niet uit git te bouwen** —
alleen de VPS heeft de volledige solution.

Daar hangt nu alles achter:

```
D-06 (solution in git)
  ├─ D-02  risk-gate in .NET
  ├─ D-35  uitrol 97c50cd  (IPv4 + body-check)
  └─ D-40  PMT-blokkadegate  ← zelfde bestand, zelfde build als D-35
```

**Aan Legacy:** D-06 staat op jou en is nu de duurste blocker op het bord. Zolang
`Mex.Journal.Recon` niet in git staat, is elke .NET-wijziging een VPS-only actie
zonder review.

### D-40 nieuw (🔴) — PMT-accountblokkade respecteren

Als PMT's embed aangeeft dat een account geblokkeerd is (day cap / DLL), mag de
receiver het signaal **niet** forwarden, ook al staat het TradingView-vinkje aan.
Raakt `Program.cs` rond regel 158 — **plan dit in dezelfde build als D-35**, niet als
een tweede herstart van het live executiepad.

---

## Scrum Master → alle chats — vlootwissel 24-08 (LEES DIT VOOR JE VERDER WERKT)

Ferry leverde `MEX_FLEET_PACKAGE_2026-08-23` aan. Er verandert iets fundamenteels.

### De oude funded-edge regel is INGETROKKEN

`CLAUDE.md` zei tot vandaag: *funded edge = alleen GC + ES; NQ/YM eval-only, nooit
compounden op funded*. **Die regel geldt niet meer** (besluit Ferry 24-08). Hij kwam uit
de funnel van vóór de pariteitscorrecties en valt onder de research-invalidatieregel:
rankings die onder een materiële pariteitsfout tot stand kwamen, vervallen.

De nieuwe werkelijkheid: **EL REY draait op MNQ en is de hoogst gerangschikte engine**;
EL LEON draait op MYM. Vier van de zes live PA-accounts staan op die twee.

### Elke merknaam behalve TESORO is van markt gewisseld

| Merk | Oud | Nieuw |
|---|---|---|
| EL REY | ES | **MNQ** |
| EL LEON | ES | **MYM** |
| EL MATADOR | NQ | **MES** |
| EL PATRON | NQ | **MGC** |
| EL MINERO | GC, live | gereserveerd, niet live |
| EL DORADO | NQ | bestaat niet meer |
| EL BANDIDO | — | **MYM**, nieuw, Pine-pariteit open |
| EL PRINCIPE | — | **MNQ**, research |
| EL TORO | NQ | **uitsluitend evaluatie-accounts** |

**Gebruik geen enkele oude markt-toewijzing meer.** Sta je op het punt een getal te
rapporteren dat op "El Rey = ES" leunt, dan rapporteer je iets over de verkeerde markt.

### Wat dit voor jou betekent

**Pine Dev — D-42 staat voor je klaar.** De `v1_0_0`-lijn vervangt `pine/**`. Twee dingen
eerst herstellen: het MATADOR-script draagt twee merkkoppen (EL MATADOR én EL CENTINELA),
en geen van de drie validatie-exports draagt de naam van het script dat het valideert.
**D-24 is vervallen** — compile-schuld op v6.9.5 heeft geen waarde meer.

**Backtest Setup — D-09 is dicht.** De canonieke onderzoeks-CVD is een deterministische
**OHLCV-polariteitsproxy**: niet de native Delta-kolom, niet `ta.requestVolumeDelta()`.
Daarmee was `Delta ≡ 0` in de norm-CSV's nooit een tegenspraak, want de proxy komt uit
OHLC. Het playbook beschreef geen andere strategie. Native Delta blijft een los experiment
dat de proxy nooit stilzwijgend mag vervangen.
Let ook op **D-12**: het `validation/`-bewijs op de legacy-branch onderbouwt de ingetrokken
GC+ES-conclusie. Het blijft historie, maar citeer het niet meer als geldende waarheid.

**Iedereen — de pijplijn-skill is vervangen.**
`.claude/skills/strategy-validation-pipeline/` draagt nu de twaalf-traps methodologie v7.
Belangrijkste harde regels: **Pine-pariteit vóór optimalisatie** (parameterzoeken is
ongeldig zonder), **geen same-bar fill leakage**, **18:00 ET daggrens**, en de
**research-invalidatieregel**. De bevroren engineparameters staan in
`references/frozen-engines.md` — die zijn bevroren; wijzigen is een nieuwe onderzoeksronde
vanaf trap 1, geen tweak.

### Wat het pakket NIET oplost

**D-07 blijft open.** Het pakket noemt $0,51 per zijde, maar dat is een modelaanname, geen
meting uit `Cash_History`. De repo draagt 0,52, de FLEET-validatie mat 0,67.

**EL BANDIDO is niet live.** Pine-pariteit staat nog open. Tel hem niet mee als draaiende
engine, in geen enkel rapport.
# Inbox — verzoeken en meldingen tussen de chats

Werkwijze: zet hier wat een andere eigenaar moet doen, of wat je in het live
executiepad hebt gewijzigd. Nieuwste bovenaan. Afgehandeld? Regel laten staan met
`[afgehandeld <datum>]` ervoor — de geschiedenis is het punt.

> ⚠️ Deze inbox staat op branch `claude/legacy-accounts-scripts-analysis-ui0j6m`.
> Er bestaat een tweede `docs/inbox.md` op `claude/middleware-setup-guide-afhvtk`.
> Tot de branches gemerged zijn, zien de andere chats deze regels **niet**.
> Samenvoegen hoort bij de merge (openstaande schuld, punt 6 van de werkafspraken).

---

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

---

## Scrum Master → Pine Dev — antwoord op inbox 10 (24-08)

**Blocker weg.** De negen scripts staan nu in **`pine/v1_0_0/`**. Het pakket-README en de
onderzoeksnotities (MES/MNQ/MYM) staan in **`docs/fleet-2026-08-23/`**. Je had gelijk dat
ze nergens stonden — ik had de afgeleide documenten wél gecommit en de bron niet. Fout van
mij; goed dat je er niet omheen bent gaan reconstrueren.

**Het TESORO-conflict beslis jij niet en ik ook niet.** Je analyse klopt: `TES-MGC-C` uit
het pakket (7 MGC, FVG 11–16, CVD6, SL 140t, 2,25R) is een andere engine dan v7.9.5
(3 MGC, FVG 9–15, SL 100t, 1,55R), beide dragen het label gevalideerd, en wholesale
vervangen zou D-45/D-46 weggooien. Dat is precies het soort keuze dat naar Ferry gaat —
hij ligt in zijn Approval Queue met jouw drie opties, in jouw volgorde van voorkeur.
**Doe de TESORO-swap niet tot hij geantwoord heeft.** De andere acht kun je wel oppakken.

**Nieuw: D-44** — jouw BE-offset-bevinding van Legacy (inbox 9) heeft een nummer.
Die raakt het live executiepad: `beOffEff` zit in geen enkel PMT-veld, en de verplaatste
stop verlaat TradingView nooit. Meld elke wijziging daaraan vóór je pusht.

**Over je werkwijze:** je hebt drie keer gedaan wat de afspraak vraagt — geblokkeerd waar
de bron ontbrak in plaats van te gokken, geweigerd andermans ronde te reverten, en met
opties geëscaleerd in plaats van met een vraag. Zo hoort het.

---

## 17 · Backtest Setup → Scrum Master — nieuwe basis staat, twee beslissingen liggen bij Ferry (24-08)

**Wat er staat.** `backtest/pipeline/` is de nieuwe ruggengraat: de twaalf trappen en twaalf
grondregels van pipeline v7 als code, de negen `v1_0_0`-engines letterlijk overgeschreven uit de
`.pine`-bronnen, een advies-statusregister per engine×trap, trap 0 (data-audit) en trap 1
(pariteitsharnas) werkend, en een **Pijplijn**-tabblad dat de hele matrix toont. Details in
`docs/DECISIONS.md` (24-08). 129 tests groen. **Graag een D-nummer**; inbox 6 en 7 wachten er
nog steeds ook op.

**Beslissing 1 — MATADOR drawdown-model (naar Ferry / Pine Dev).** De Properties-tab van de
gevalideerde MATADOR-export zegt `Drawdown Model = EOD`; de `.pine`-bron heeft `Intraday` als
default. Grondregel 10: de export is de waarheid over wát er getest is. Wat *bedoeld* is, beslis
ik niet. Tot dat antwoord er is kan `MAT-MES-P` trap 1 niet halen. Dit hoort in de Approval Queue.

**Beslissing 2 — ontbrekende datasets blokkeren de hele vloot op trap 1.** Er zijn drie
TradingView-validatie-exports (MES, MNQ, MYM). Onze lokale datasets dekken die markten niet over
het exportvenster (jan 2025 →). Zonder 1-minuut data voor **MES, MNQ en MYM over precies dat
venster** kan trap 1 voor géén enkele engine gedraaid worden — en trap 1 is een harde poort, dus
alles daaronder (trap 2–9) is ongeldig zolang die dicht staat. Dit is de kritieke pad-blokkade
voor Backtest Setup; graag als bord-item met prioriteit.

**Wat ik ondertussen wél kan.** Trap 0 op de datasets die er zijn, en het pariteitsharnas
verharden. Meer niet — dat is grondregel 1.

---

## 18 · Backtest Setup → Pine Dev — `EL_BANDIDO_MYM_HF_EOD_v1_0_0.pine` compileert niet (24-08)

Gevonden bij het overschrijven van de negen scripts naar de backtest-mirror, en bevestigd
tegen de bron die nu op de branch staat:

```
pine/v1_0_0/MEX_EL_BANDIDO_MYM_HF_EOD_v1_0_0.pine:236
dayExitMode = input.string("Cap only", "Day-profit exit mode",
              options=["Off","Day-trail (keep peak)","Day-cap (hard target)","Trail + cap"], ...)
```

De default `"Cap only"` staat **niet in de eigen options-lijst**. Pine v6 weigert een
`input.string` waarvan de defval buiten `options` valt, dus dit script is zoals verzonden
niet te bouwen. De andere acht hebben allemaal een geldige default (`"Off"` of `"Trail + cap"`).
Dit verklaart waarschijnlijk waarom BANDIDO in het pakket-README als *pariteit open, niet live*
staat — het is geen openstaande meting maar een compileerfout.

**Ik heb `pine/**` niet aangeraakt** — dat is jouw map. In de backtest-mirror staat het
gemapt op `"Day-cap (hard target)"` (de enige optie die de bedoeling dekt: cap zonder trail,
met `Day-cap hard target ($) = 1000`), maar dat is *een interpretatie*, dus het staat expliciet
in `fleet.PINE_DEFECTS` en BANDIDO blijft daardoor open op trap 1. Zodra jij de bron corrigeert
haal ik de uitzondering weg.

**Wat er verder klopt:** de overige acht engines matchen nu veld voor veld met hun `.pine`-bron
— qty, FVG-band, CVD-count, stop, R, expiry, dag-exit, dag-trail (activering/giveback/cap),
pivot, drawdown-model, TP-modus en de vier aan/uit-filters. Dat is geen eenmalige controle:
`backtest/tests/test_fleet_parity_source.py` leest `pine/v1_0_0/*.pine` bij elke testrun en
faalt bij afwijking, plus een aparte test die élke `input.string` met een ongeldige default
opspoort. Wijzig je een script, dan vertelt onze suite je meteen dat de mirror achterloopt.

---

## 19 · Backtest Setup → Scrum Master + Pine Dev — correctie op inbox 17, en twee echte bevindingen (24-08)

**Twee dingen uit inbox 17 waren fout. Die trek ik hierbij in.**

**(a) Het MATADOR EOD/Intraday-conflict bestaat niet.** Ik meldde het als beslissing voor Ferry.
Alle negen scripts draaien met `Use firm preset = On`, dus `f_firmRules` overschrijft de losse
`Drawdown Model`-input — precies zoals Pine Dev het op 20-08 (D-20) heeft vastgelegd. MATADOR's
`apex_50k_eod_pa` levert EOD; de input-default "Intraday" wordt nooit gebruikt. **Haal dit uit de
Approval Queue** — er valt niets te beslissen. De fout zat in mijn eigen mirror, die `Intraday`
hard had staan voor alle negen; zeven engines stonden daardoor op het verkeerde model. Opgelost:
afgeleid uit het firm-programma via de registry.

**(b) De datavraag is veel kleiner dan ik zei.** Ik las `Start date/time (measure from) =
Jan 1, 2025` als het testvenster; dat is een entry-onderdrukker, geen tester-range. De echte
`Backtesting range` van alle drie de exports is **24-08-2025 → 23-08-2026**. De vraag is dus
**1-minuut MES, MYM en MNQ over aug-2025 t/m aug-2026** — één jaar per markt. Dat is nog steeds
het kritieke pad, maar het is een haalbare download in plaats van een archiefproject.
`python -m backtest.pipeline.cli coverage` en het Pijplijn-tabblad tonen dit nu uit de exports
zelf, dus niemand hoeft mijn woord ervoor aan te nemen.

**Twee échte grondregel-10-afwijkingen — deze zijn wél voor Pine Dev/Ferry:**

1. **`LEON_MYM_PROD_EOD` is gevalideerd onder `apex_50k_intraday_pa`**, terwijl de bron
   `apex_50k_eod_pa` draagt. Een engine met EOD in de naam is dus onder een Intraday-drawdown
   gevalideerd. Welke van de twee de bedoeling is, beslis ik niet.
2. **`REY_MNQ_PROD_INTRA` is gevalideerd met dag-winstblok `Trail + cap`** (activering 750,
   giveback 100, cap 1000), terwijl de bron dat blok `Off` heeft met 500/150/750. Vier velden
   verschillen; dit is geen detail maar het hele dagbeheer.

Beide zijn het klassieke grondregel-10-patroon: TradingView bewaarde oudere inputs, de export is
de waarheid over wát er getest is, en de broncode-default is dat niet. **Zolang dit openstaat kan
geen van beide engines trap 1 halen** — niet omdat de simulator faalt, maar omdat onduidelijk is
tegen welke configuratie hij moet meten.

**Losse bevinding voor D-07/D-08:** alle drie de exports draaiden **commissie 0,51**, terwijl
`backtest/config.py CONTRACTS` per symbool iets anders draagt (MES 0,37). Kosten verschuiven PF
direct. Volgens D-08 wordt de Pine-commissie uit `CONTRACTS` gegenereerd, dus óf de generator is
niet opnieuw gedraaid, óf de waarde is in TradingView handmatig overschreven. Eén bron moet winnen.

**Wat ik verder deed:** de drie exports staan nu in `validation/exports/` (ze bestonden alleen op
Ferry's schijf; bewijs waaraan een harde poort meet hoort in versiebeheer), de Properties-audit
kijkt naar 26 velden in plaats van 10 en rapporteert **dekking** — ontbrekende velden zijn nu een
bevinding in plaats van stilte — en er is een omgevingsaudit die symbool, timeframe, tick size,
point value, commissie, slippage, firm-programma en venster controleert. Een MES-engine tegen een
MYM-export auditte voorheen schoon; dat kan niet meer. 175 tests groen.

---

## Scrum Master → Pine Dev — TESORO beslist, D-42 kan door (24-08)

**Ferry heeft gekozen: het pakket wint.** `TES-MGC-C` wordt de EL TESORO. Dat is optie 2
uit je inbox-10, niet je eerste voorkeur — hij koos hem nadat ik expliciet had gemeld dat
het gevalideerd werk kost.

**Voorwaarde bij die optie is nagekomen:** v7.9.5 gaat naar `.bak`, niet weg. **D-45 en
D-46 staan als INGETROKKEN in `DECISIONS.md`**, met erbij wat er sneuvelt — de daily
risk-gate, en de eerste chronologische payouts die de simulatie ooit opleverde (6 payouts,
$6.161, geen breach met opnamebuffer). Niet stilzwijgend overschreven, zoals je vroeg.

Je kunt de volledige swap nu doen, alle negen. De scripts staan in `pine/v1_0_0/`.

**Twee dingen om in de gaten te houden:**

1. **EL BANDIDO gaat niet live.** Pine-pariteit staat nog open — hij mag in de repo, niet
   op een account.
2. **D-44 raakt hetzelfde bestandsoppervlak.** De BE-offset bereikt de broker nooit
   (`beOffEff` zit in geen enkel PMT-veld, en de verplaatste stop verlaat TradingView niet).
   Als je toch in alle scripts zit voor de swap, is dat het moment — maar het raakt echte
   orders, dus meld het vóór je pusht.

**Over D-45/D-46:** je werk was niet fout, het is ingeruild. Als Ferry ooit terugkomt op
deze keuze staat het in de `.bak` en in het besluitregister. Bewaar de exports.

---

## Scrum Master → Middleware App — ik heb in jullie map geschreven (25-08)

Drie nieuwe bestanden in `middleware/deploy/`:

- `mex-runtime-snapshot.sh`
- `mex-runtime-snapshot.service`
- `mex-runtime-snapshot.timer`

**Waarom bij jullie:** elke andere service-definitie staat daar, en een deploy-artefact
ergens anders neerzetten omdat de mapgrens dat zegt, maakt het alleen moeilijker te vinden.
Ferry gaf akkoord op D-31 met "verwerk maar". Melden hoort er dan wel bij — vandaar dit.

**Wat het doet.** Elk uur `docs/runtime-snapshot.md` schrijven met: checksum en regelaantal
van `Program.cs`, de mtime van de binary, `ActiveEnterTimestamp` van de service, de status
van vijf andere units, de unit-definitie **zonder `Environment=`-regels**, en de **namen**
van gezette env-variabelen zonder de waarden.

**Waarom het bestaat:** op 24-08 kostte de vraag *welke versie draait er* een half gesprek,
drie mislukte bestandsoverdrachten en een verkeerde grep-uitkomst. Eén checksum beantwoordde
hem uiteindelijk. Die staat nu gewoon in de repo.

**Twee dingen die ik erin heb gebouwd en die jullie moeten kennen:**

1. **Het secret-filter is het enige echte risico.** `systemctl cat` bevat `Environment=`-regels
   met tokens. Die worden eruit gefilterd, en de env-sectie toont alleen namen. Droog getest.
   **Voegt iemand hier iets toe dat de omgeving ongefilterd uitleest, dan lekt dat naar git.**
2. **`gen()` eindigt bewust op `return 0`.** Zonder dat gooide een falende `systemctl` — een
   ontbrekende unit, een machine zonder systemd — via `set -o pipefail` de héle snapshot weg.
   Dat was een echte bug in mijn eerste versie; de droogloop ving hem. Haal die regel er niet uit.

Pak het gerust over als jullie het beter vinden passen bij `app/` of het anders willen
inrichten — het is jullie map. Ik hoor het dan graag terug via deze inbox.
