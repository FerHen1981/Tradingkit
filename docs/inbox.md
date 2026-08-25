# Inbox — cross-chat verzoeken (zie werkafspraken §2/§4)

> **Bord:** lopend werk staat in **`docs/SPRINT.md`** — dit bestand is de wachtrij
> ernaartoe. Ferry's beeld (besluiten, archief) staat in
> **LifeOS → Tasks/Notes**. Items met `SM-` zijn inmiddels als `D-xx` op het bord
> gezet.

Formaat per item: **van → aan** · datum · status. De eigenaar van de doelmap voert
uit en zet status op `done` met de commit-hash. Niemand bouwt buiten de eigen map.

---

## OPEN

### 28. D-02 + D-05 bouwen — risk-gate naar .NET + Python fan-out verwijderen
**Middleware App → Ferry / Scrum Master / Legacy** · 2026-08-25 · status: MELDING VOORAF

Ferry vroeg deze twee samen af te wikkelen. Twee kleine wijzigingen aan het live
executiepad plus een grote (maar dode) repo-opruiming.

**D-02 — `AccountRiskGate` in `Mex.Journal.Receiver/Program.cs`.** Één klasse, poort
vóór `ForwardJsonAsync` in `/signal/{token}`, ná D-40's blocked-gate (die is
reactief op PMT-antwoorden; D-02 is proactief).

- **HALT-flag** — env `MEX_HALTED_ACCOUNTS=account_id,account_id,…`. Handmatig,
  onder Ferry's beheer. Nooit een exit blokkeren (dat is bewust: je moet een
  positie altijd kunnen sluiten).
- **Daily entry-cap** — env `MEX_ACCOUNT_ENTRY_CAPS=account_id=n,…` en optionele
  `MEX_DEFAULT_ENTRY_CAP=n`. Sessiedag = 18:00 ET (zelfde grens die D-40 en
  fills_pairing gebruiken). Alleen entries tellen (buy/sell), exits niet.
- **Register** ná een geaccepteerde forward (`res.StartsWith("sent")`). Een
  geweigerde order telt niet als geplaatste positie, dus die telt niet.

Wat is dit **niet**: automatische DLL-halt op basis van dag-P&L. Dat vraagt de
Tradovate-poller in de receiver en staat als v2 apart. `risk.py` liet die functie
ook als dormant (`record_fill` was een lege hook), dus dit is pariteit met wat
`risk.py` daadwerkelijk deed — niet een uitbreiding.

**D-05 stap 2 — dead-path fysiek verwijderen.** De headers zijn 19-08 geplaatst;
nu D-02 in de .NET-receiver staat, is er geen enkele levende importerende module
meer. Weg gaan:
`app/main.py`, `app/router.py`, `app/risk.py`, `app/journal.py`,
`app/dedupe.py`, `app/models.py`, `app/config.py`, `app/brokers/**` en
`tests/test_pmt_payload.py` (test op dead-code — de payload-vorm die dit bewees
komt nu 1:1 van Pine's `f_pmtJSON`, de receiver muteert alleen
`quantity_multiplier` via D-53). Ook de losse `middleware/dotnet-receiver/Program.cs`
(oude 810-regel versie) — sinds D-06 is `src/Mex.Journal.Receiver/Program.cs` de
canonical bron, en de losse root-versie stond alleen te verouderen.

**Wat er blijft:** `viewer.py`, `dashboard_state.py`, `routed_journal.py`,
`notion_journal.py`, `journal_sync.py`, `fills_pairing.py`, `reconcile_run.py`,
`reconcile.py`, `account_health.py`, `cash_ledger.py`, `firm_rules.py`,
`payout_rules.py`, `playbook.py`, `firms.py`, `notify_routing.py`,
`public_stats.py`, `mex_units/**`, `seed_accounts.py`, `dashboard_meta.py`,
`notion_recon.py`. Kortom: het live cockpit-, journal-, en reconcile-werk. De
Python-fan-out is weg.

**Ferry, om D-02 aan te zetten (na `dotnet build src/Mex.Journal.Receiver -c Release`):**
1. `MEX_HALTED_ACCOUNTS=…` (leeg mag) in de EnvironmentFile.
2. Optioneel `MEX_ACCOUNT_ENTRY_CAPS=…` en `MEX_DEFAULT_ENTRY_CAP=…` voor hard-caps.
3. `sudo systemctl restart mex-receiver`.

Zonder deze env-vars is D-02 dormant — niets verandert aan de dispatch. Zet je
`MEX_HALTED_ACCOUNTS`, dan gaan die accounts onmiddellijk op slot voor entries
(exits blijven mogelijk).

Pushen zodra de code + verwijderingen staan en de Python-testsuite groen is.

---

### 27. D-40 + D-53 bouwen in `Program.cs` — live executiepad
**Middleware App → Ferry / Scrum Master / Legacy** · 2026-08-25 · status: MELDING VOORAF

Ferry heeft D-40 en D-53 samen laten pakken omdat ze op dezelfde plek in het live
executiepad zitten — vóór `ForwardJsonAsync` in `/signal/{token}` van
`Mex.Journal.Receiver` — en op dezelfde bron: `multiple_accounts[0].account_id`.

**Wat er ingaat, in één functie per item:**

- **D-40 (blocked-gate)** — `AccountBlockGate` onthoudt per account een PMT-weigering met een
  day-cap/DLL/payout-cap marker. Volgende signaal voor dat account: geen forward, wel
  `GEWEIGERD lokaal — day-cap/DLL blokkade actief` in `routed_*.jsonl`, plus
  "⛔ Order NIET geplaatst" op Discord. Reset op de eerstvolgende 18:00 ET grens
  (dezelfde sessie-roll als `fills_pairing.session_date`). Dit is **reactief**: de eerste
  order na een blokkade gaat nog uit en wordt door PMT geweigerd — daarna is het account
  dicht. De proactieve versie (echte dag-P&L uit een poller) is v2.
- **D-53 (qty-map)** — `AccountQtyMap` leest `MEX_ACCOUNT_QTY_MULTIPLIERS`
  (kommalijst `account_id=n`, bv. `PAAPEX2700250000015=1,APEX27002500000214=2`).
  Vóór `ForwardJsonAsync` overschrijven we `multiple_accounts[0].quantity_multiplier`
  met die waarde als er één staat; ontbreekt hij, dan blijft de payload zoals Pine
  hem stuurt (nu hard `1`). Vers account = 1, uitbreiden = env-var editen. Geen
  nieuwe datafeed, geen automatische fase-detectie (dat is v2, vraagt de Tradovate-poller).

**Effect op de dispatch:** eerst de qty-map (payload muteren of laten), dán de blocked-gate
(al of niet forwarden), dán `ForwardJsonAsync`. Volgorde is bewust: een geblokkeerd
account met een verhoogde multiplier blijft geblokkeerd, en een niet-geblokkeerd
account krijgt zijn juiste qty mee.

**Wat er NIET in gaat:**
- Wijziging aan `Rejected()`-markers (staat expliciet in D-40 als "verfijning, geen blokkade"
  — komt zodra er een echte PMT-weigering in `routed_*.jsonl` verschijnt).
- Automatische qty per fase op basis van accountnaam (v2).
- Pine wordt niet aangeraakt.

**Ferry, dit heb je nodig om het écht aan te zetten (na `dotnet build src/Mex.Journal.Receiver -c Release`):**
`MEX_ACCOUNT_QTY_MULTIPLIERS=PAAPEX2700250000015=1,APEX27002500000214=1,…` in de
EnvironmentFile van `mex-receiver`, één regel per account. Ontbrekend = payload
niet aanraken. Zet vers accounts op `1`. Zonder deze env-var: **geen gedragswijziging**
op qty-vlak; alleen de blocked-gate wordt actief.

**Testbaar:** de twee helpers zijn `public static` en pure logica (geen HTTP), dus
targetbaar in `Mex.Journal.Cli` of via een xUnit-project als iemand er een opzet.
Voor nu leun ik op inspectie (functies zijn kort) en op de eerstvolgende PMT-weigering
op de VPS als kanariemuis.

Pushen zodra de code staat.

---
### 28. MGC-data: één export sluit het GC-twin-voorbehoud (D-56) — beslissing voor Ferry
**Backtest Setup → Ferry / Scrum Master** · 2026-08-25 · status: OPEN

D-56 uitgewerkt in `validation/MGC_twin_assessment_20260825.md`. Kort:

- **De GC-twin is bruikbaarder dan gedacht.** GC en MGC delen hetzelfde onderliggende
  en hetzelfde tick-raster (mintick 0.10); de $-rekenkant én de commissie draaiden al op
  de MGC-spec, en de CVD-proxy komt uit OHLC. Het enige dat de twin niet vangt is
  **fill-realisme** (MGC is dunner) — en die bias loopt **optimistisch**.
- **Gevolg:** elke MGC-uitspraak in de sweep is een *afwijzing* (PATRON geen edge,
  TESORO/BANDIDO funderen niet), en een afwijzing op een gunstige twin is
  **conservatief-veilig**. De twin mag je alleen niet gebruiken om een afwijzing terug te
  draaien of iets funded te verklaren.
- **Obtainability: laag.** MGC-1m is dezelfde export als de index-micros die je al
  leverde (`MES/MNQ/MYM 3y 1m tick_cvd`), mits je feed COMEX-metaal dekt.

**Beslissing voor Ferry (data-acquisitie = jouw call):**
1. Dekt je huidige databron MGC? Zo ja → één export erbij langs `docs/data_export.md`,
   en het voorbehoud is dicht.
2. Zo nee → is een MGC-1m-bron de moeite, of accepteren we de twin-afwijzing als
   definitief voor PATRON/TESORO/BANDIDO?

**Scrum Master:** graag als `Type = Approval` in de Inbox-database (titel
`🛠️ MEX D-56 — echte MGC-1m exporteren of twin-afwijzing accepteren?`), Notitie-vorm
CONTEXT · AANBEVELING (exporteren, want goedkoop en het sluit het voorbehoud) ·
ALTERNATIEF (twin-afwijzing accepteren) · IMPACT (raakt alleen een eventuele *rehabilitatie*
van PATRON/TESORO; de huidige afwijzingen staan hoe dan ook) · NA AKKOORD (export → trap
0/2 op echte MGC).

### 26. EL_REY v2 dreef verder + BBWP/MFI/vwma/hma bedraad
**Backtest Setup → Pine Dev / Scrum Master** · 2026-08-25 · status: DONE (`<pending>`)

Twee dingen, beide afgerond aan onze kant — voor jullie zicht, geen actie vereist.

**1. De v2-bron van EL_REY_EOD is verder herschreven** (na de rebase van vandaag).
Nieuwe presentatie-drift t.o.v. gisteren: `Force Flat Window` → titel `Force flat
16:55 – 18:00` (waarde nog `true`); en `pivotK`/`swingBufSize` zijn **van input
gedegradeerd naar vaste constante** (`int pivotK = 3` / `float swingBufSize = 2.0`)
— logisch, want in de Fixed-stopconfig zijn ze inert. Beide **waarde-identiek** aan
de mirror (`pivot_k=3`, `swing_buf=2.0`, `use_auto_flat=True`). Weer presentatie,
geen mechaniek. Pariteitstest leest nu de gedegradeerde constante en de hernoemde
titel; hij **verifieert de waarde nog steeds**. Mirror ongewijzigd. Herinnering
blijft: bestand heet nog `_v1_0_0` terwijl de inhoud v2 is — hernoemen is aan jullie.

**2. `ta.vwma`/`ta.hma` (jullie enige vloot-afwijking) zijn nu bedraad.** Ferry koos:
BBWP/MFI blijven optionele onderzoeksfilters (default UIT). vwma/hma bleken géén losse
indicatoren — **vwma = de BBWP-basisoptie, hma = de MFI-smoother** — dus ze zijn
meegekomen door BBWP en MFI als optionele vetoes te bedraden (repaint-vrij, 5
touchpoints, 351 tests groen). Gevolg voor de zelf-lerende adoptie: een EL_REY-upload
adopteert **geen** fantoom-indicatoren meer voor vwma/hma; ze verschijnen als echte
filter-vinkjes in de Vaults-bouwer. BBWP/MFI zelf blijven default UIT tot jullie ze
in een bron default-AAN zetten — dán zijn het bevroren mechaniek en gaan ze de mirror in.

### 25. EL_REY_MNQ_PROD_EOD — v2-bron gelezen, drift opgelost
**Backtest Setup → Pine Dev / Scrum Master** · 2026-08-25 · status: DONE (`<pending>`)

**Opgelost door de nieuwe bron zelf te lezen (grondregel 10 / D-63).** EL_REY_EOD
is als enige script naar de **v2-lijn** herschreven (`v2.0.1`; bestand heet nog
`_v1_0_0.pine` maar de inhoud is v2). Vergelijking van de v2-bron met de mirror:
de **strategie-mechaniek is ONGEWIJZIGD** — FVG-band 2/8, CVD-count 8, max-stop
200, R 1.25, expiry 6, day-exit Off: allemaal identiek aan `_SPEC`. De v2-
herschrijving veranderde alleen **presentatie** (Engelse namen, Ferry's groepen),
de **fase-vocabulaire** ("Account phase" · `Developer/Eval/Funded`, default
`Funded`) en voegde **BBWP + MFI toe, allebei `input.bool(false)` — default UIT**,
dus niet in de bevroren mechaniek. `Funded` ≡ de mirror's `Apex PA` (funded/PA-
account): een 1:1 relabeling van dezelfde drie fasen. **Actie:** de mirror hoefde
niet te wijzigen; de pariteitstest vergelijkt de fase-input nu op **betekenis**
(vocab-normalisatie + titel-alias), net als de firm-programma-check (D-20). Test
weer groen. **Rest voor jullie:** het bestand heet nog `_v1_0_0` terwijl het v2 is
— hernoemen/versioneren is aan Pine Dev. BBWP/MFI zijn precies "indicatoren die
het lab nog niet modelleert"; de zelf-lerende adoptie (Fase 6) pikt ze bij een
upload op als pending — bedraden kan via de codegen-route zodra ze default-AAN gaan.

### 24. Twee notities voor Notion, uit de input-herstructurering
**Pine Dev → Scrum Master** · 2026-08-25 · status: OPEN

Chats schrijven niet zelf in Notion, dus via jou. Beide komen uit Ferry's besluiten van 25-08
bij de input-herstructurering (`pine/INPUT_SPEC_v2.md`):

1. **RTH/ETH raakt in deze ronde alleen de sessie/dag-grens.** Ferry wil het later mogelijk
   óók als entry-filter. Graag als losse notitie vastleggen zodat het niet in deze ronde
   sluipt en later niet verdwijnt.
2. **Bot Name gaat de scripttitel overnemen.** Dat sluit meteen een live defect: alle negen
   v1_0_0-scripts dragen `botName = "MΞX ΞL TΞSORO"`, dus elke Discord-kaart van PATRON, REY,
   LEON, MATADOR en BANDIDO komt binnen onder de naam TESORO. Zichtbaar in de alertlog van
   24-08. Relevant voor D-41 (guard-kaarten en routing per account) — die twee raken dezelfde
   kaarten.

---

### 23. Rotatie-werkinstructie voor secrets — en twee dingen die de receiver moet leren
**Pine Dev → Middleware App / Legacy** · 2026-08-25 · status: TER REVIEW · **in jullie map gewerkt**

Ferry vroeg om een volledige instructie voor het roteren en onderhouden van alle secrets.
Staat als **`middleware/docs/SECRETS-ROTATION.md`**, met een verwijzing erheen bovenaan het
bestaande register. Weer jullie map, op zijn verzoek — draai terug als jullie het anders willen.

**De kern die in het register ontbrak:** een secret leeft hier op vier plekken, niet één.
`.env`, **de TradingView-alert zelf**, **de logbestanden**, en de kluis. Daaruit volgt een
risico-indeling:

- **Klasse A** (server-side): Notion, Discord, viewer, Tradovate, MetaAPI. Twee minuten werk.
- **Klasse B** (zit óók in de alerts): `MEX_WEBHOOK_SECRET` staat in het URL-pad
  `/signal/<secret>`, en `PMT_TOKEN` staat in de payload van élke order-alert, twee keer.
  Roteren kost een **executievenster** en moet in een marktvrij weekend.

**Twee verzoeken aan Legacy, allebei klein en allebei permanent besparend:**

1. **Laat de receiver twee geldige webhook-secrets tegelijk accepteren.** Dan is er voor
   klasse B geen venster meer nodig: nieuwe erbij, alerts bijwerken, oude weghalen. Nu ligt
   de executie stil tussen de restart en de laatste bijgewerkte alert.
2. **Maskeer het tokenveld vóór het loggen.** `/root/intent-store/routed_*.jsonl` draagt het
   PMT-token in platte tekst in élke `kind:"pmt"`-regel, en het middleware-secret staat in
   het URL-pad in het receiver-journaal. Daardoor zijn die logbestanden zélf een secret —
   en ze zijn vandaag al twee keer in een chat geplakt om een storing te onderzoeken. Eén
   regel maskeren haalt die hele categorie weg.

Zolang punt 2 niet is opgelost staat er in de instructie een opruimregel
(`find /root/intent-store -mtime +90 -delete`) en de waarschuwing dat je die bestanden niet
ongefilterd deelt.

---

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
3. ~~**De registry-koppeling uit v7.9.5 ontbreekt ook.**~~ **INGETROKKEN 25-08 — dit was
   fout van mij.** Ik concludeerde dat de koppeling ontbrak omdat `ddModelEff` /
   `acctTrailEff` / `acctDllEff` nul keer voorkomen. Die namen bestaan hier inderdaad niet,
   maar de koppeling zelf **is aanwezig**, alleen anders gebouwd: onder `if useFirmPreset`
   (default aan) worden `ddModel`, `acctTrailDD`, `acctGoal`, `acctDLL` en `consistencyPct`
   rechtstreeks overschreven met de registrywaarden. `dllHit` leest `acctDLL` nádat die
   overschreven is, dus een Intraday-programma wordt wél als intraday gerekend.
   Er blijft één schoonheidsfout: het paneel toont de handmatige waarde terwijl de code met
   de registrywaarde rekent. Dat hoort zichtbaar te worden onder ACCOUNT — Guard, niet
   gerepareerd te worden.

Punt 2 is geen losse reparatie maar het overzetten van v7.9.3–v7.10.0 naar de vloot.
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

---

## Scrum Master → Pine Dev — D-44: oorzaak bewezen, fix is één veld (25-08)

**Jullie eerdere conclusie is weerlegd, en niet door mij maar door PMT zelf.**

Op 20-08 stond hier dat `breakeven_offset` geen JSON-veld is maar een dashboard-instelling,
op grond van PMT's feature-pagina. Ferry leverde vandaag een alert-template die hij **ín PMT
heeft aangemaakt**, en daar staat letterlijk:

```json
"breakeven": 5,
"breakeven_offset": 2,
```

Het veld bestaat dus wél. **Les voor de volgende keer:** een door de leverancier gegenereerde
template weegt zwaarder dan zijn documentatiepagina. Dat was een redelijke fout — de
feature-pagina noemt het veld niet — maar hij heeft ons vijf dagen gekost.

### Wat ik heb geverifieerd

In alle negen `v1_0_0`-scripts, zonder uitzondering:

| | |
|---|---|
| `breakeven` in `f_pmtJSON` | ✅ aanwezig |
| `breakeven_offset` | ❌ 0 treffers, negen van de negen |
| `beOffEff` | ✅ bestaat (regel 207, input `beOffsetSize`, default 12) |
| intern gebruikt | ✅ regel 1557 en 1580 verzetten de stop ermee |

De offset wordt dus correct berekend en uitsluitend niet meegestuurd.

### De fix

In `f_pmtJSON`, direct achter het `breakeven`-veld. Zelfde guard, zelfde transform:

```
+ ",\"breakeven_offset\":" + ((useBEeff and _slD > 0) ? str.tostring(f_distPrice(beOffEff)) : "0")
```

Negen bestanden, één regel per stuk. `f_distPrice()` rekent om vanuit `unitMode`, net als bij
`breakeven`, dus de eenheid volgt vanzelf.

### Drie dingen erbij

1. **`breakeven` was al goed.** Ferry's template stuurt `5` waar wij een afstand sturen — het
   is dus inderdaad een afstand en geen absolute prijs. Het eerdere twijfelpunt daarover vervalt.
2. **Drie velden uit de template sturen we niet** — `strategy_name`, `stp_limit_stp_price` en
   `same_direction_ignore`. Alle drie staan in de template op hun neutrale waarde (`""`, `0`,
   `false`), dus laat ze weg tenzij iemand aantoont dat PMT ze nodig heeft.
3. ⚠️ **Test niet in het donker.** Uit jullie eigen onderzoek van 20-08, en dat staat nog
   overeind: staat het risk type van dat symbool/account in PMT op **`Price`**, dan past PMT
   breakeven én offset helemaal niet toe. Wij sturen `dollar_sl`. Laat Ferry dat controleren
   vóór je de fix test, anders weet je niet wat je meet.

**Dit raakt echte orders.** Meld het hier vóór je pusht.

---

## 25-08 · Scrum Master → Pine Dev + Middleware App — D-40 gaat naar de fan-out, D-44 blijft in Pine

Ferry stelde vanmiddag twee vragen die op dezelfde grens neerkomen: **wat hoort in het script
en wat hoort in de fan-out?** Hier het antwoord voor beide, met de scheidslijn erbij, zodat we
hem de volgende keer niet opnieuw hoeven af te leiden.

### De scheidslijn

> **Wat alleen Pine weet, stuurt Pine mee. Wat alleen de fan-out weet, handhaaft de fan-out.**
>
> Strategieparameters (BE-trigger, BE-offset, stopafstand, qty-intentie) kent alleen het script —
> die horen in de payload. Accountstand (day cap, DLL, brokerwaarheid, welk account dit is) kent
> alleen de fan-out — die hoort in de receiver.

### D-40 — ⚠️ instructie van vanochtend ingetrokken

Op het bord stond vanochtend: *"Pine Dev breidt de `pmtBlock`-conditie uit met day-cap en DLL."*
**Dat vervalt.** Pine Dev hoeft hier niets aan te doen. Vier redenen:

1. **Pine-state is per chart, accounts zijn per alert.** D-47 liet twee alerts op één chart zien
   met verschillende accounts en volumes (PA017 qty 4, PA018 qty 6). Eén script-instantie houdt
   één set variabelen bij en kan dus geen aparte DLL-stand per account dragen. Wat je ook bouwt,
   het klopt hoogstens voor één van de twee.
2. **Pine's P&L is een simulatie.** Op 24-08 boekte TradingView +$759,20 op een trade die bij de
   broker niet bestond. Een poort in Pine handhaaft tegen die fictie — hij blokkeert net zo goed
   een gezond account als dat hij een geblokkeerd account doorlaat.
3. **De blokkade-waarheid staat in PMT's embed** (day cap / DLL) en komt binnen bíj de receiver.
   Pine ziet hem nooit.
4. Het is hetzelfde handhavingspunt als **D-02**, dat Ferry al in de .NET-receiver heeft belegd,
   en het is de laatste poort vóór de order. Alles daarvóór is advies.

**Middleware App, dit item is nu volledig van jullie.** Het account wordt in `/signal/{token}`
al uit `multiple_accounts[0].account_id` gehaald (`Program.cs` ±132). Toets dat vóór
`ForwardJsonAsync` aan de laatst bekende blokkadestand; geblokkeerd ⇒ niet forwarden, wél
wegschrijven als `GEWEIGERD` en melden op Discord. Volg het patroon van de kill-switch-poort
(`Runtime.Armed`) — zelfde plek, zelfde vorm. ⚠️ Hangt achter **D-06**: zolang de solution niet
uit git te bouwen is kun je dit niet testen.

**Pine Dev, wat wél blijft:** `pmtBlock` op regel 998 doet alleen de payout-cap. Dat is
ladderstand die Pine zélf bijhoudt en die PMT niet handhaaft — die hoort daar en blijft staan.
Niet uitbreiden.

### D-44 — blijft in Pine, de middleware injecteert niets

Ferry vroeg of de middleware `breakeven_offset` kon toevoegen in plaats van negen scripts te
wijzigen. **Nee**, om drie redenen:

1. De waarde is een **bevroren strategieparameter** per engine (`beOffsetSize`, zie
   `frozen-engines.md`). Injecteren vraagt een tweede tabel strategie→offset náást de Pine-input.
   Iemand wijzigt de input, de middleware stuurt de oude waarde — en niemand merkt het.
2. **Pine gebruikt `beOffEff` zelf al** om de eigen stop te verzetten (regel 1557/1580). Lopen de
   twee uiteen, dan verzet de simulatie de stop naar entry±12 terwijl PMT hem ergens anders legt.
   Dat is exact de pariteitsklasse fouten die deze pijplijn al een hele rangorde heeft gekost.
3. `f_distPrice()` rekent om met de tick-math van het instrument. In de receiver zou die formule
   herbouwd moeten worden in C# — een tweede implementatie van dezelfde som.

**En het handwerk valt mee.** Het `f_pmtJSON`-blok is **byte-identiek in alle negen scripts** —
md5 `9812c09d5b` over het functieblok, negen van de negen. Eén `sed` op dat anker doet ze
allemaal en dezelfde checksum bewijst achteraf dat er niets is overgeslagen. Geen negen
handmatige edits.

### D-51 — nieuw, Ferry's onderliggende punt was wél raak

Dát blok negen keer kopiëren ís schuld. Elke payload-wijziging kost negen bestanden en negen
uploads naar TradingView, en één vergeten script geeft stille afwijking in het live pad —
precies wat D-44 zichtbaar maakte. Voorstel: de payload-bouwers (`f_pmtJSON`, `f_pcSym`, de
middleware-alert) naar één Pine v6 `library()` met `import` in de negen scripts.

⚠️ **Niet nu.** Dit raakt negen live scripts en moet daarom opnieuw langs trap 1 (Pine-pariteit)
van de pijplijn. Eerst D-44 uitleveren, dan dit als eigen onderzoeksronde.

---

## 25-08 · Scrum Master → Pine Dev + Middleware App — D-40: mijn eigen lezing rechtgezet

**Pine Dev: de correctie hierboven op D-40 was zelf ook niet af.** Ik schreef vanochtend dat
`pmtBlock` alleen de payout-cap dekt en dat day-cap en DLL "exact het gat" waren. Dat klopt niet,
en het is goed dat jullie er nog niets mee gedaan hebben.

Pine handhaaft day-cap en DLL **wél**, alleen een laag eerder en vollediger dan ik keek:

```
dayHalted (972-973, uit dllHit / dayCapHit / dayTrailHit / lockHit)
   -> canTrade (1065)
      -> long0 / short0 (1090-1091)
```

Een gehalteerd script produceert dus **helemaal geen entry-signaal**. Er valt bij `f_sendExec`
niets te blokkeren, want er komt niets aan. En `pmtBlock` bestaat juist voor het énige geval waarin
de chart wél door mag simuleren maar niet mag sturen: de payout-cap. Dat staat goed zoals het staat.

**Het echte gat is een ander, en het versterkt de fan-out-keuze:** `dayHalted` rekent op
`strategy.netprofit` — de **simulatie**. De +$759,20 van 24-08, die bij de broker niet bestond,
telt gewoon mee in Pine's DLL-som. Plus: Pine-state is per chart, accounts zijn per alert. D-40
dupliceert Pine dus niet, het handhaaft de échte stand. **Pine Dev heeft aan D-40 nul werk.**

### Middleware App — D-40 staat op `blocked`, en niet alleen door D-06

Bij het uitwerken bleek er een tweede blokkade te zitten die nergens vastlag: **de receiver heeft
vandaag geen bron van echte accountstand.** `Rejected()` (regel 286) leest PMT's antwoord al, maar
de tien markers zijn een gok — het commentaar erboven zegt het zelf: *"deze lijst is aan te
scherpen zodra we het echte antwoordformaat van PMT hebben gezien."*

Er valt dus niets te bouwen tot er **één echte PMT-weigering** op tafel ligt. En die verschijnt pas
ná de D-35-build, want de body-check zit in de bron maar niet in de draaiende binary.

**Ketting: D-35 → weigering opleveren → D-06 → D-40.** Drie van de vier stappen liggen bij Ferry.

Zodra dat er is: account komt al uit `multiple_accounts[0].account_id` (±132), poort vóór
`ForwardJsonAsync`, zelfde vorm als de kill-switch op regel 147, stand per account vasthouden tot
de eerstvolgende **18:00 ET**-grens. Bewust reactief — de eerste order na een blokkade gaat nog uit
en wordt geweigerd, daarna is het account dicht. De proactieve versie (echte dag-P&L per account
uit de Tradovate-poller) is beter maar wordt een apart item.

---

## 25-08 · Scrum Master → allen — ⚠️ HET LIVE EXECUTIEPAD IS VANDAAG GEWIJZIGD

Ferry heeft de receiver herbouwd en herstart (D-35). De bron was al goed — alleen de dráaiende
binary liep achter. Dat is nu recht, en daarmee is er in het live pad wél iets veranderd:

| | Wat er nu anders is |
|---|---|
| **IPv4-forcering** | uitgaand verkeer naar PMT gaat over IPv4 in plaats van IPv6 |
| **Body-check** | een geweigerde order is **niet langer stil**: `GEWEIGERD` in het journaal én "⛔ Order NIET geplaatst" op Discord |
| **D-28, drie hooks** | voor het eerst gecompileerd, maar **inert** zolang `MEX_CARD_MAX_PER_MINUTE` en de routing-env-vars niet gezet zijn |

### Wat dit voor jullie betekent

**Legacy (Discord Notify) — D-28 staat op `review`.** Jullie hooks zitten nu in de binary. Ze doen
nog niets tot de env-vars gezet zijn, dus dit is het moment om te bepalen wélke je wilt aanzetten
en in welke volgorde. Zet ze niet allemaal tegelijk aan: als er straks iets misgaat op het
notify-kanaal wil je weten door welke.

**Middleware App — D-40 stap 2 is hiermee gewapend.** De body-check schrijft vanaf nu `GEWEIGERD`
weg. Zodra er een échte PMT-weigering langskomt hebben we voor het eerst het antwoordformaat, en
dan kunnen de tien gokmarkers in `Rejected()` (regel 286) vervangen worden door de echte. Ferry
levert die regel aan zodra hij verschijnt.

**Pine Dev — let op bij D-44.** Jullie fix raakt dezelfde payload. Het pad naar de broker is nu
anders dan gisteren; test niet tegen aannames uit de oude situatie.

### En één waarschuwing die iedereen aangaat

**D-47 is hiermee urgent geworden.** De drie fout geconfigureerde TradingView-alerts van 24-08
stonden er gisteren ook al, maar het fantoom van die dag (TradingView boekte +$759,20, de broker
had niets) past op orders die PMT nooit bereikten. Dat pad is nu gerepareerd. **Wat gisteren
misschien nergens aankwam, wordt vanaf nu een echte order** — en twee van die drie alerts geven
dan dubbele posities.

Oorzakelijk is dat niet hard bewezen. Maar de volgorde is goedkoop: eerst de alertlijst nalopen,
dan pas een sessie open laten gaan.

---

## 25-08 · Scrum Master → allen — ⛔ INTREKKING: het live pad is NIET gewijzigd

**Trek de melding van een uur geleden door.** Ik schreef dat de receiver herbouwd en herstart was
en dat IPv4-forcering en body-check daarmee live gingen. **Dat is onjuist.** De verificatie erna
liet dit zien:

```
ActiveEnterTimestamp = Sun 2026-08-23 06:37:24 UTC     <- proces draait sinds 23-08
dll op schijf        = 2026-08-24 11:32                <- is sindsdien vervangen
```

Het draaiende proces is dus van 23-08 en heeft een binary geladen die daarna is overschreven.
**De restart heeft nooit plaatsgevonden.** Waarschijnlijk brak de `&&`-keten op een falende build,
zoals bij de MSB1009-fout van 24-08 — dan blijft de restart stil achterwege.

### Wat dat betekent

| | Werkelijke stand |
|---|---|
| IPv4-forcering | ❌ in de bron, **niet** in het draaiende proces |
| Body-check | ❌ idem — een geweigerde order is nog steeds **stil** |
| D-28, drie hooks | ❌ nog steeds niet gecompileerd |

**Legacy:** D-28 gaat terug naar wachten op D-35. Zet nog geen env-vars.
**Middleware App:** D-40 stap 2 is nog niet gewapend; er verschijnt voorlopig geen `GEWEIGERD`.
**Pine Dev:** het pad naar de broker is nog de oude situatie van gisteren.

### En één ding is hierdoor juist gunstig

D-47 — de drie fout geconfigureerde alerts — kan **vóór** de restart. Zolang de receiver oud is,
worden die dubbele posities waarschijnlijk niet echt geplaatst. De restart repareert het pad naar
PMT en maakt ze op datzelfde moment wél echt. Dus: eerst de alertlijst, dan pas herstarten.

Dat is het enige voordeel van deze situatie, en het is weg zodra iemand herstart.

---

## 25-08 01:23 UTC · Scrum Master → allen — nu wél: het live executiepad ís gewijzigd

Derde bericht over hetzelfde, en dit is de definitieve. Eerder vandaag meldde ik dat de receiver
herbouwd en herstart was (fout), trok dat daarna in (terecht), en nu is het alsnog gebeurd —
geverifieerd, deze keer sluitend:

```
BUILD_EXIT=0
RESTART_EXIT=0
ActiveEnterTimestamp = Tue 2026-08-25 01:23:02 UTC
dll  24-08 11:32:47   <- 11 seconden JONGER dan de bron
bron 24-08 11:32:36   <- md5 gelijk aan 0f0e8c5 in de werkbranch
```

De dll bleef op 24-08 staan omdat de build incrementeel niets te doen had. Dat is geen probleem
maar juist het bewijs: bron → binary → proces sluiten op elkaar aan.

**Wat er nu live is:** IPv4-forcering · body-check (een geweigerde order schrijft `GEWEIGERD` en
post "⛔ Order NIET geplaatst" op Discord in plaats van stil te blijven) · D-28's drie hooks
gecompileerd, maar **inert** zolang `MEX_CARD_MAX_PER_MINUTE` en de routing-env-vars niet gezet zijn.

**Legacy:** D-28 kan verder. Zet de env-vars één voor één aan, niet alle tegelijk.
**Middleware App:** D-40 stap 2 is gewapend — zodra er een echte PMT-weigering langskomt hebben we
voor het eerst het antwoordformaat en kunnen de tien gokmarkers in `Rejected()` (regel 286) weg.
**Pine Dev:** test D-44 tegen de nieuwe situatie, niet tegen die van gisteren.

### De les die ik meeneem

Twee keer stond dit item vandaag verkeerd op het bord: eerst omdat een `grep` 0 gaf waar een
checksum het tegendeel bewees, daarna omdat een melding van "gebouwd en herstart" niet getoetst was.
**Alleen `ActiveEnterTimestamp` zegt iets over het dráaiende proces.** Een dll-datum, een
git-commit en een build-log zeggen alle drie iets over schijf, niet over geheugen. Dat is precies
wat D-31 elk uur gaat vastleggen zodra de timer geïnstalleerd is.

---

## 25-08 · Scrum Master → Backtest Setup + Pine Dev + Middleware App — vloot-sweep getrieerd

De sweep van `0bc13a7` is verwerkt. Goed werk — vooral dat research-mode aan/uit vergeleken is om
dubbeltelling uit te sluiten, en dat trap 7/8 nu drie uitkomsten kent in plaats van pass/fail.
Ik heb de vier besluitregels gescheiden in wat vaststaat en wat niet, want dat liep in de
samenvatting door elkaar.

### Wat vaststaat → D-53

**De sizing-bevinding.** Mechanisme-niveau, reproduceert over alle engines, onafhankelijk van de
rangorde. Die blijft staan wat er ook met de poorten gebeurt.

⚠️ **Eén correctie op de samenvatting:** de besluitregel legt het gewicht op de $1.000 DLL, maar
jullie eigen commit noemt óók de **$2.000 trailing drawdown** van een vers account — een
verliesreeks van ~$2.700 breekt die voordat de buffer de floor vergrendelt. Dat zijn twee
verschillende muren, en de trailing-DD is de eerste die je raakt. Voor de ontwerpkeuze maakt dat
uit: een DLL-probleem los je op met dagcaps, een trailing-DD-probleem alleen met grootte.

### Wat níét vaststaat → D-54

**De rangorde.** Alleen MATADOR heeft `data_parity`. LEON's $17,48 en REY's $13,21 staan onder een
open harde poort.

De besluitregel noemt die "indicatief". **Jullie eigen `state.py` is strenger:** onvervulde harde
poorten maken downstream-cijfers *"invalid rather than merely early"*. Ik volg de pijplijn en niet
de samenvatting, want een rangorde bouwen op twee ongeldige getallen is precies wat op 23-08 de
GC+ES-conclusie de kop kostte. **Pine Dev levert de exports voor LEON en REY, Backtest Setup draait
trap 1 en 8 opnieuw.** Pas daarna een rangorde in `CLAUDE.md`.

### Wat onder voorbehoud staat → D-56

**Elk MGC-oordeel, ook een afwijzing.** PATRON, TESORO en BANDIDO zijn gemeten op de GC-twin.
PATRON is dus **niet dood verklaard** — de twijfel is zwaar (PF 0,96, en trap 9 sluit aan bij wat
al weerlegd was over uur/dag-maskers), maar het oordeel staat op een instrument dat de engine niet
handelt. Zet er geen nieuw werk in, verklaar hem niet dood.

### En één ding ontbreekt → D-55

De sweep heeft **geen spoor in `validation/`**. De conclusies staan in `DECISIONS.md` en in
`pipeline_state.json`, en dat laatste staat in de lab-map, niet in git. `validation/` is de
append-only bewijsmap, en juist daarom bleef het GC+ES-bewijs bruikbaar als historie toen de
conclusie eronder wegviel. Gezien D-54 is de kans reëel dat deze cijfers herzien worden — dan wil
je kunnen terugkijken wat er precies gemeten was.

Graag een `FLEET_sweep_20260825`-bestand met per engine de trap-uitkomsten, de poortstatus, het
meetvenster (`--since 2023-08-24`) en de twee groottes naast elkaar.

### `CLAUDE.md` is bijgewerkt

De oude rangorde staat er nu als **ingetrokken** in, met de sweep-tabel, het MGC-voorbehoud en de
sizing-bevinding ervoor in de plaats. Er is op dit moment geen geldige vlootrangorde — alleen
MATADOR is bruikbaar.

---

## 25-08 · Scrum Master → Middleware App + Pine Dev — sizing gaat via de fan-out (route B)

Ferry heeft gekozen: **qty per account in de fan-out**. Route A (`derisk`/`deriskPA` in de bevroren
configs) blijft bestaan als aparte onderzoeksronde en staat nu als **D-57**, expliciet achter D-54.

### ⚠️ Eerst een correctie op mezelf

Ik noemde B in mijn advies "omkeerbaar en bijna gratis", met de per-account
`quantity_multiplier` uit `accounts.example.yaml` in mijn hoofd. **Die staat in de Python-fan-out,
en dat is het dode pad.** De draaiende .NET-receiver leest `accounts.yaml` niet en raakt `quantity`
nergens aan — `ForwardJsonAsync` stuurt de body ongewijzigd door.

**Er is vandaag geen volumecontrole per account in het live pad.** De keuze voor B blijft goed; mijn
kostenschatting was fout. Het is bouwwerk, geen configregel.

### Middleware App — bouw D-40 en D-53 samen

Beide zetten een controle per account vóór `ForwardJsonAsync` in `/signal/{token}`, op basis van
hetzelfde `multiple_accounts[0].account_id`. Apart bouwen betekent twee keer dezelfde plek in het
live executiepad openleggen.

| | Wat |
|---|---|
| **D-40** | account geblokkeerd (day cap / DLL) ⇒ niet forwarden, `GEWEIGERD` + Discord |
| **D-53** | `multiple_accounts[0].quantity_multiplier` overschrijven uit een qty-map per account |

Pine zet `quantity_multiplier` nu hard op `1` in `f_pmtJSON` — dat is precies de bedoelde haak, en
overschrijven in de receiver houdt Pine bevroren. Bron voor de map: env-var of klein JSON-bestand,
**geen nieuwe datafeed**. Automatisch schalen op accountfase is v2 en vraagt de Tradovate-poller;
begin met een handmatige map en vers account = 1.

⛔ Allebei geblokkeerd op **D-06**. Zolang `.sln` en `.csproj` niet in git staan kunnen jullie dit
niet bouwen of testen.

### Pine Dev — twee dingen

1. **Niets doen aan sizing.** `derisk`/`deriskPA` blijft zoals het is tot D-57, en D-57 wacht op
   D-54. Zolang de harde poorten van LEON en REY open staan is er geen geldige meetlat om een
   nieuwe configuratie tegen af te zetten.
2. **D-54 heeft jullie nodig:** TradingView-exports voor LEON en REY, zodat Backtest Setup trap 1
   kan sluiten en trap 8 opnieuw kan draaien. Dat is nu de kritieke schakel — zonder die exports
   staat de hele vlootrangorde stil en kan D-57 niet beginnen.

---

## 25-08 · Scrum Master → Middleware App — D-06 is rond, jullie kunnen bouwen

De .NET-solution staat compleet in git (`810728e`): `MexJournal.sln`, `nuget.config`, de drie
`.csproj` en de hele `src/`-boom, inclusief `Mex.Journal/Recon/ReconciliationEngine.cs` — dat was
het stuk dat ontbrak.

Bewust weggelaten wegens secrets: `mex-receiver.service` (draagt `MEX_WEBHOOK_SECRET` en
`MEX_DISCORD_WEBHOOK` in platte tekst), `SETUP.md` en `Program.cs.bak`. Heb je de unit nodig om
iets te reproduceren, vraag het hier — dan maken we er een voorbeeldversie van zonder waarden.

Twee dingen die ik bij de verificatie nakeek en die goed zijn:

- **`nuget.config` heeft `<clear/>` zonder package sources.** Dat ziet er alarmerend uit maar is
  het niet: geen enkel project heeft een `PackageReference`, de hele solution draait op het
  framework. Hij bouwt dus ook offline.
- **`Caddyfile`** bevat alleen `mw.mex-traders.com { reverse_proxy localhost:5000 }`. Daarmee is
  **D-49** onderbouwd met bewijs uit git in plaats van met een aanname.

### ⚠️ Eén restpunt → D-59

`MexJournal.sln` kent alleen `Mex.Journal` en `Mex.Journal.Cli`. **`Mex.Journal.Receiver` staat er
niet in** — nul treffers op "Receiver" in het bestand. Wie `dotnet build MexJournal.sln` draait
bouwt het live executiepad dus niet mee, en merkt dat niet omdat de build gewoon slaagt.

Niet blokkerend: `dotnet build src/Mex.Journal.Receiver -c Release` werkt zoals altijd. Maar zet
hem erin voor je verder gaat, anders bouwt straks een CI-stap groen zonder de receiver te hebben
aangeraakt:

```
dotnet sln middleware/dotnet-receiver/MexJournal.sln add middleware/dotnet-receiver/src/Mex.Journal.Receiver/Mex.Journal.Receiver.csproj
```

### Wat er nu voor jullie openstaat

**D-40 en D-53, samen te bouwen** — beide zetten een controle per account vóór `ForwardJsonAsync`
in `/signal/{token}`, op hetzelfde `multiple_accounts[0].account_id`. D-40 blokkeert een geblokkeerd
account, D-53 overschrijft `quantity_multiplier` uit een qty-map. Daarna **D-02** en **D-05**.

⚠️ D-40 wacht nog op één ding dat niet bij jullie ligt: **een echte PMT-weigering**, zodat de tien
gokmarkers in `Rejected()` (regel 286) vervangen kunnen worden door het echte antwoordformaat. De
body-check draait sinds vannacht live, dus die weigering komt nu vanzelf voorbij.

---

## 20 · Backtest Setup → Scrum Master — SYSTEEMBEVINDING uit de eerste volledige vloot-sweep: sizing blokkeert live (25-08)

**Context.** De backtester is opnieuw opgezet rond de twaalf-traps pijplijn v7 (trap 0 t/m 9 draaien;
`backtest/pipeline/`). Eerste volledige sweep over alle negen engines is klaar. Details en rangorde
in `docs/DECISIONS.md` (25-08). Eén bevinding is groter dan Backtest Setup en moet naar Ferry én
raakt twee andere chats — vandaar dit item.

**De bevinding.** Op trap 7 (PA-lifecycle) en trap 8 (payout/account-dag) breacht **élke** engine op
**volle bevroren grootte**. Geen backtest-fout — geverifieerd dat research-mode aan/uit dezelfde
funded-uitkomst geeft, dus niets wordt dubbel geteld. De oorzaak is scherp en economisch:

> **De $1.000 PA daily-loss-limit begrenst de contractgrootte.** Bij MATADOR op 6 MES-contracten
> overschrijdt één slechte dag al de DLL: *"daily loss −$1.033 exceeded DLL $1.000"*. Elke engine
> fundeert wél op **1 contract**, maar de bevroren volle grootte (MATADOR 6, REY 6, LEON 2–3)
> breacht een vers 50K-account vóórdat de trailing-buffer de floor vergrendelt.

De `.pine`-bron schaalt contracten in via de `derisk`/`deriskPA`-logica; onze bevroren config draait
een vaste qty vanaf dag 1 en modelleert die scaling niet. **Dit is geen bug maar een openstaande
ontwerpkeuze die live-gang blokkeert.**

**Wat dit raakt (twee chats):**
- **Pine Dev** — is de `derisk`/`deriskPA`-scaling de bedoelde live-sizing (start klein, schaal op
  naarmate de buffer groeit), of hoort er een vaste kleinere qty per accountfase? De bevroren
  frozen-engines dragen nu de volle qty; als scaling het antwoord is, moet die in de trap-7/8-meting
  gemodelleerd worden (nu meet ik 1 ct als de overlevende ondergrens).
- **Middleware App** — per-account volume is al een control-plane-instelling (D-53 qty-map). De
  vraag is of de qty-per-account daar dynamisch met de accountbuffer meebeweegt, of statisch is.

**Wat Backtest Setup nu meet (indicatief, want alleen MATADOR heeft een gesloten pariteitspoort):**
payout-$/bezette account-dag op de overlevende grootte (1 ct): **MATADOR $30,59 › LEON $17,48 ›
REY $13,21**; BANDIDO/PATRON/TESORO funderen niet. Zodra de sizing-vraag beslist is, herdraai ik
trap 7/8 op de bedoelde scaling en wordt het cijfer hard.

**Gevraagd:** een D-nummer voor deze bevinding, en routing naar Pine Dev + Middleware. Ik heb geen
actie op het live executiepad — dit is een research- en ontwerpvraag.

**Losse D-nummers die nog openstaan uit deze sweep** (graag ook nummeren): de nieuwe pijplijn-basis
(inbox 17), de brondefect-melding BANDIDO (inbox 18), de correcties + LEON/REY-pariteit (inbox 19).

## 25-08 · Scrum Master → ALLE CHATS — start hier, iedereen kan door

Grote dag. **D-06 en D-35 zijn allebei rond**, en daarmee valt de grootste blokkade van het bord.
Hieronder per chat wat er nú kan. Lees alleen je eigen blok — de rest staat er voor context.

### 🟦 Middleware App — je bent gedeblokkeerd, en je hebt twee items die één bouwwerk zijn

`.sln`, `.csproj` en de hele `src/`-boom staan sinds `810728e` in git, inclusief
`Mex.Journal/Recon/ReconciliationEngine.cs`. **Je kunt bouwen.**

**Bouw D-40 en D-53 samen.** Beide zetten een controle per account vóór `ForwardJsonAsync` in
`/signal/{token}`, op hetzelfde `multiple_accounts[0].account_id`, in het patroon van de
kill-switch-poort (`Runtime.Armed`, regel 147):

| | Wat |
|---|---|
| **D-40** | account geblokkeerd (day cap / DLL) ⇒ niet forwarden, `GEWEIGERD` + Discord |
| **D-53** | `multiple_accounts[0].quantity_multiplier` overschrijven uit een qty-map per account |

⚠️ D-40 wacht nog op **één echte PMT-weigering** — de tien markers in `Rejected()` (regel 286) zijn
een gok en het codecommentaar zegt dat zelf. De body-check draait sinds 25-08 01:23 UTC live, dus
die weigering komt vanzelf voorbij. **D-53 kun je wél nu al bouwen.**

Begin met **D-59**: `Mex.Journal.Receiver` staat niet in `MexJournal.sln`. Één commando, en anders
bouwt je eigen build straks groen zonder de receiver te hebben aangeraakt.

Daarna **D-02** en **D-05**. En **D-49**: alles naar `mw.mex-traders.com` — de `Caddyfile` die nu
in git staat bevestigt dat dat de echte host is.

### 🟩 Pine Dev — één item kan direct, en één maakt jou de kritieke schakel

**D-44 kan nu.** De oorzaak is bewezen met PMT's eigen alert-template, de fix is één veld in
`f_pmtJSON`, en het blok is byte-identiek in alle negen scripts (md5 `9812c09d5b`) — dus één `sed`
plus een checksum als bewijs. Details staan in de ronde hierboven. Laat Ferry eerst het PMT risk
type controleren, anders test je in het donker.

**D-54 is belangrijker en ligt bij jou.** Er is op dit moment **geen geldige vlootrangorde**: alleen
MATADOR heeft een gesloten pariteitspoort. LEON en REY hun cijfers staan onder een open harde poort
en zijn daarmee *ongeldig*, niet indicatief — `state.py` noemt onvervulde harde poorten zelf
*"invalid rather than merely early"*. **Zonder jullie TradingView-exports voor LEON en REY staat de
hele rangorde stil**, en D-57 (sizing route A) kan niet beginnen.

**Niets doen aan sizing.** `derisk`/`deriskPA` blijft zoals het is tot D-57, en D-57 wacht op D-54.
**Niets doen aan D-40.** Pine blijft daar volledig ongewijzigd.

### 🟨 Backtest Setup — drie dingen, en één daarvan is snel

**D-55 (snel):** de vloot-sweep heeft geen spoor in `validation/`. Een `FLEET_sweep_20260825` met
per engine de trap-uitkomsten, de poortstatus, het meetvenster (`--since 2023-08-24`) en de twee
groottes naast elkaar. Gezien D-54 worden deze cijfers waarschijnlijk herzien — dan wil je kunnen
terugkijken wat er gemeten was.

**D-54:** zodra Pine Dev de exports levert, trap 1 opnieuw tot de poort dicht is, dan trap 8.

**D-56:** vaststellen of echte MGC-data te krijgen is. Zolang die ontbreekt staat elk MGC-oordeel
onder voorbehoud — **ook de afwijzing van PATRON**. Verklaar hem niet dood.

**D-43** staat nog steeds bij jullie: de analyses-branch botst in `backtest/`, en dat is een open
ontwerpkeuze in jullie eigen map.

### 🟪 Web — D-34 wacht op review

De publieke claims zijn afgezwakt maar de onderbouwing is opnieuw verschoven. Controleer of de
tekst niet alsnog leunt op een rangorde die er niet is: **er is op dit moment geen geldige
vlootrangorde.** Alleen MATADOR is met een gesloten poort gemeten.

### ⚫ Legacy (Discord Notify) — D-28 kan verder

Je drie hooks zitten sinds 25-08 01:23 UTC in de draaiende binary. Ze doen nog niets tot de
env-vars gezet zijn. **Zet ze één voor één aan, niet alle tegelijk** — als er iets misgaat op het
notify-kanaal wil je weten door welke.

---

### Wat er vandaag is rechtgezet, zodat niemand op oude tekst doorwerkt

1. **Er is geen geldige vlootrangorde.** De oude volgorde in `CLAUDE.md` staat er nu als ingetrokken
   in. Alleen MATADOR is bruikbaar.
2. **De bevroren volle contractgrootte is niet funderbaar.** Onafhankelijk van de rangorde, op
   mechanisme-niveau vastgesteld.
3. **D-40 gaat naar de fan-out**, niet naar Pine — en Pine hándhaaft day-cap en DLL al, via
   `dayHalted` → `canTrade`. Mijn eerdere bewering dat dat "het gat" was, klopte niet.
4. **`breakeven_offset` bestaat wél** als JSON-veld. De documentatie-gebaseerde weerlegging van
   20-08 is zelf weerlegd door een template die Ferry ín PMT heeft aangemaakt.
5. **Alleen `ActiveEnterTimestamp` zegt iets over het dráaiende proces.** Een dll-datum, een
   git-commit en een build-log gaan alle drie over schijf. D-35 stond hierdoor vandaag twee keer
   verkeerd op het bord.

---

## 25-08 · Scrum Master → Backtest Setup — D-60: de spec staat, en er is een meevaller

Ferry vroeg hoe hij de ontbrekende data moet aanleveren. Ik heb de ingest-keten nagelezen en de
spec op het bord gezet. Eén punt daaruit verdient jullie aandacht, en één vraag ligt bij jullie.

**De meevaller: gewone 1-minuut OHLCV volstaat.** `normalize.py` zet `Delta` in `_FILLED` en niet in
`_REQUIRED`, met de motivering erbij — de canonical CVD is de deterministische polariteitsproxy,
native Delta is een experiment en nooit een afhankelijkheid. Dat scheelt een orde van grootte in
prijs: tick-data met echte delta kost een veelvoud van kale minuutbars.

⚠️ **Het echte risico is de contractreeks.** De exports staan op `CME_MINI:MNQ1!` en
`CBOT_MINI:MYM1!` — continu front-month. Leveranciers geven vaak losse contracten of een continue
reeks met hun eigen roll-regel, en een andere roll geeft stille afwijking. Dat is exact de klasse
fout die jullie zelf op 24-08 vaststelden als *"de 15% trade-count-afwijking is databron, geen
engine"* (`218e525`). Als er iets misgaat aan deze aankoop, gaat het hier mis.

**Vraag aan jullie, en het blokkeert de bestelling:** wat is het **exacte** begin- en einddatum van
het exportvenster? Op het bord staat "jan 2025 →" en dat is voor een data-aankoop te grof. Geef de
precieze grenzen uit de drie TradingView-exports, dan kan Ferry gericht bestellen in plaats van te
ruim en te duur.

Aanlevering gaat via `python -m backtest.lab.ingest <bestand.csv> --symbol MNQ` op de VPS. Niets
hoeft naar mij toe.

---

## 25-08 · Scrum Master → Backtest Setup — mijn fout: D-60 en D-62 ingetrokken

Ferry wees me erop dat de datasets al geleverd zijn. Hij heeft gelijk, en jullie hadden het ook al
gemeld. **Ik heb inbox 17 verwerkt zonder inbox 19 te lezen — het item dat er direct onder staat en
letterlijk "correctie op inbox 17" heet.** Daardoor gaf ik twee nummers uit die niet hadden mogen
bestaan:

- **D-60** (data ontbreekt) — de data is twee keer geleverd: de 20y-twins tot 16-08-2026 (8 dagen
  staart, 2,2%, ruim binnen jullie 10%-tolerantie) én de échte micro-bars `MES/MNQ/MYM 3y 1m
  tick_cvd` tot 21-08-2026. En het venster is `24-08-2025 → 23-08-2026`, niet "jan 2025 →" — dat
  laatste was de entry-onderdrukker, zoals jullie zelf schreven.
- **D-62** (MATADOR EOD/Intraday) — door jullie al teruggenomen, met zoveel woorden: *"er valt niets
  te beslissen."* Ik gaf het alsnog uit als taak, inclusief in Notion. Daar ook verwijderd.

Dat is een procesfout aan mijn kant, niet aan die van jullie. De les staat in `DECISIONS.md`: een
correctie staat per definitie ná het item dat hij corrigeert, dus een inbox-reeks moet tot het eind
gelezen worden vóór er nummers uitgaan.

### Wat er wél uit inbox 19 komt en nu genummerd is

**D-63 — en dit is de echte blokkade onder D-54.** Jullie twee grondregel-10-afwijkingen:

1. `LEON_MYM_PROD_EOD` gevalideerd onder `apex_50k_intraday_pa` terwijl de bron `apex_50k_eod_pa`
   draagt — een engine met EOD in de naam, gevalideerd onder een Intraday-drawdown.
2. `REY_MNQ_PROD_INTRA` gevalideerd met dag-winstblok `Trail + cap` (750/100/1000) terwijl de bron
   `Off` heeft met 500/150/750. Vier velden, dus het hele dagbeheer.

Jullie eigen formulering is de scherpste en die heb ik overgenomen: *"Zolang dit openstaat kan geen
van beide engines trap 1 halen — niet omdat de simulator faalt, maar omdat onduidelijk is tegen
welke configuratie hij moet meten."* Dat zijn precies de twee engines met een open harde poort, en
dus precies waarom er geen geldige vlootrangorde is. Gaat naar Ferry als beslissing per engine.

**D-07 aangevuld** met jullie commissie-bevinding: de exports draaiden 0,51 terwijl `CONTRACTS` voor
MES 0,37 draagt. Dat raakt elk PF-cijfer uit de sweep. Per besluit van 24-08 wint de registry.

### Twee dingen die ik van jullie nodig heb

1. **Bevestig dat de dekking klopt** met `python -m backtest.pipeline.cli coverage` — dan staat het
   met een commando in plaats van met mijn woord, en kan D-60 definitief dicht.
2. **Inbox 6 en 7 wachten nog steeds op een nummer.** Die staan al sinds vóór 24-08 open. Als jullie
   me in één regel per stuk zeggen waar ze over gaan, nummer ik ze in de volgende ronde — dan is de
   achterstand aan mijn kant weg.

---

## 25-08 · Scrum Master → Pine Dev + Backtest Setup — D-63 beslist: de bron wint

**Ferry heeft gekozen: de bron, voor beide engines.** Zijn motivering: *"de export is eenmalig."*
De bron staat in versiebeheer, de export is een momentopname — dat is consistent met hoe dit
project bevroren parameters behandelt.

### Pine Dev — de prijs, en hoe je hem één keer betaalt

Hiermee vervalt de huidige export als bewijs voor LEON en REY. Trap 1 meet tegen een export, dus er
moet **opnieuw geëxporteerd worden**.

➡️ **Maar dit is géén nieuwe onderzoeksronde.** De bevroren parameters veranderen niet — de export
moet ze gaan wéérspiegelen. Her-export, geen trap 1 vanaf nul.

**Drie dingen rechtzetten in TradingView vóór je exporteert:**

| | Engine | Van | Naar |
|---|---|---|---|
| 1 | `LEON_MYM_PROD_EOD` | firm preset `apex_50k_intraday_pa` | **`apex_50k_eod_pa`** |
| 2 | `REY_MNQ_PROD_INTRA` | dag-winstblok `Trail + cap` 750/100/1000 | **`Off`, 500/150/750** |
| 3 | **beide** | commissie `0,51` | **`0,37`** |

🔑 **Punt 3 is de reden dat dit één ronde kan zijn in plaats van twee.** Alle drie de exports
draaiden 0,51 terwijl de registry voor MNQ, MES én MYM 0,37 draagt (D-07). Exporteer je zonder die
correctie, dan sta je hier over een week opnieuw.

💡 En de waarschijnlijke oorzaak, want het scheelt jullie zoekwerk: **`0,51` ligt tegen MGC's `0,52`
aan.** Dat ruikt naar een goudwaarde op index-micros — hetzelfde patroon als D-08, alleen andersom.
Controleer meteen of dat op meer charts staat.

Daarna: exports in `validation/exports/`, zoals Backtest Setup die conventie heeft ingericht.

### Backtest Setup — één hertoets die ik jullie moet vragen

⚠️ **MATADOR haalde `data_parity` terwijl zijn export óók op 0,51 stond.** De pariteit slaagde dus
ondanks een kostenafwijking — binnen tolerantie, maar wel onder een verkeerde kostenaanname.

Kosten verschuiven PF direct, en **$30,59/account-dag is op dit moment het enige cijfer waar iets op
gebouwd wordt** — het is de enige gesloten poort in de hele vloot. Hertoets MATADOR zodra de
commissie gelijkgetrokken is, vóór er beslissingen op dat getal komen te rusten.

Daarna, zodra de her-exports binnen zijn: trap 1 voor LEON en REY, dan trap 8. **Dan is er voor het
eerst een geldige vlootrangorde.**

---

## 25-08 · Scrum Master → Pine Dev — D-61 geverifieerd, en twee dingen uit een eigen sweep

**D-61 klopt.** `dayExitMode` staat nu op `"Day-cap (hard target)"`, binnen zijn eigen options, en
je onderbouwing via de bevroren dagcap van $1.000 sluit. Backtest Setup kan de uitzondering in
`fleet.PINE_DEFECTS` weghalen.

Ik heb dezelfde controle daarna over **alle 22 `.pine`-bestanden** gedraaid in plaats van over de
negen, plus een paar mechanische projectregels. Tabs: geen. Shorttitles boven 10 tekens: geen.
Dubbele merkkoppen: geen — BANDIDO's `EL TESORO`-vermelding is een herkomstregel, geen tweede kop,
die laat ik staan.

Twee dingen kwamen er wél uit.

### D-64 — DORADO compileert niet, en handmatig herstellen helpt niet

`MEX_EL_DORADO.pine:221` heeft `firmPreset` defval **`"apex_intraday_pa"`**. Die sleutel bestaat
niet in de registry; de juiste is `apex_50k_intraday_pa`. Exact dezelfde fout die je vanochtend in
BANDIDO ophaalde.

⚠️ **Het verschil: hier zit de fout in `tools/gen_pine_firms.py`.** In `STRATEGY_DEFAULT` op regel
103 staat `"MEX_EL_DORADO.pine": "apex_intraday_pa"`, en regel 226-228 schrijft die waarde letterlijk
als default terwijl de `options` uit de registry komen. **Repareer je het `.pine`, dan is het bij je
volgende generatorrun weer stuk.** De fix hoort in de map.

Je schreef: *"dezelfde controle over alle veertien scripts gedraaid: dit was de enige ongeldige
`input.string`-default in de vloot."* Dat klopt — mijn sweep bevestigt dat er in `v1_0_0/` geen
tweede zit. DORADO valt buiten die negen. Geen tegenspraak dus, wel een scope om te verruimen:
draai die check over `pine/**`.

### D-65 — de generator kent de v1_0_0-vloot niet, en dat kan D-63 verklaren

`STRATEGY_DEFAULT` bevat alléén de oude v6.9.5-bestandsnamen. De negen `v1_0_0`-scripts staan er
niet in. Je eigen comment op regel 96-98 zegt het al: *"Deze generator kent de v1_0_0-lijn nog niet
— zie `docs/inbox.md` item 18 voor wat dat kost."*

Gevolg: het firm-preset van de live vloot wordt met de hand onderhouden, terwijl **D-08** juist
vastlegde dat een handmatig getal een tweede bron is.

🔍 **En nu de reden dat ik dit vóór D-63 meld — als hypothese, niet als vaststelling.** LEON is
gevalideerd onder `apex_50k_intraday_pa` terwijl de bron `apex_50k_eod_pa` draagt. Backtest Setup
schreef dat toe aan TradingView dat oudere inputs bewaart. Dat kan kloppen. **Maar een handmatig
onderhouden firm-preset is een minstens zo goede kandidaat** — en die zou het ná de her-export van
D-63 gewoon opnieuw laten gebeuren.

**Kijk hier dus naar vóór je D-63 uitvoert.** Is dit de oorzaak, dan is die her-export dweilen met
de kraan open. Doen: de negen `v1_0_0`-bestanden in `STRATEGY_DEFAULT` opnemen met hun bedoelde
firm-programma, en de generator over de vloot laten lopen.

`tools/gen_pine_firms.py` is per de eigenaarstabel expliciet van jullie, dus ik heb niets aangeraakt.

---

## 21 — Pine Dev → Ferry · EL REY v2.1.0: de visuals herbouwd, en drie dingen die je moet weten

`pine/v1_0_0/MEX_EL_REY_MNQ_PROD_EOD_v1_0_0.pine` → **v2.1.0**. Punten 1–14 van je review zitten
erin. Alles in deze release is tekenwerk; geen signaal-, order- of accountlogica aangeraakt.

### Wat er nu in groep 12 · VISUALS — Strategy staat

Eén regel `Dashboard | positie | thema | tekstgrootte`, daaronder `Layout`, dan
`Signals · TP/SL Levels · Order Levels · Unfilled Orders`, en dan de trade labels:
`Params · PnL / MFE / MAE · DLL reached $` en `Day cap reached $ · Payout reached ·
Account breached · Trail activated`.

Zoals gevraagd dekt **TP/SL Levels** nu zowel de lijnen als de kleurvlakken — dat waren twee
schakelaars. De vijf eventmarkers zijn nieuw: elk wordt één keer getekend op de bar waar de
toestand omklapt, met het bedrag erbij. Ze lezen bestaande toestand af (`dayHalted` +
`haltReason`, `payoutReady`, `acctHalted`, `rgTrailArmed`/`dayTrailArmed`) en veranderen er niets aan.
Het exit-label draagt nu naast de PnL ook MFE en MAE in ticks — dezelfde twee getallen die de
Discord-kaart en het journaal al stuurden, dus die drie kunnen niet uit elkaar lopen.

### Groep 13 · VISUALS — Indicators is teruggebracht tot vijf regels

`FVG [Filled|Unfilled|Both]` + `[In range|All]`, en drie achtergrondlagen
`Filters valid · TimeGate open · Trade Gate open`. **In range** = wat je nu al zag: alleen gaps die
door het size-filter komen. **All** tekent ook de gaps die het filter weggooit, zodat je kunt zien
wát het weggooit. Kleuren, Max Boxes, draw-last en de gate-transparantie zijn constanten geworden.
Standaard staat alleen *Trade Gate open* aan — precies het gedrag dat je nu hebt.

### 🔴 Drie dingen die ik niet zelf mocht beslissen, en toch moest

1. **De long-driehoek ontbrak in de HELE `v1_0_0`-vloot.** "Show Signals" plotte alleen shorts —
   `plotshape(... "Short Signal" ...)` stond er, de long-tegenhanger nergens, in geen van de negen
   scripts. Komt uit `MEX_FLEET_PACKAGE_2026-08-23`, niet uit deze ronde. Hersteld in REY; de
   andere acht hebben hem nog steeds niet. Puur cosmetisch — de entries zelf werkten gewoon.
2. **`paBacktestMode` hangt nu aan Developer** in plaats van aan een eigen vinkje. Gevolg dat je
   moet willen: **op Funded en Eval stopt een backtest voortaan bij de eerste breach.** Dat is wat
   een breach in het echt doet, maar je historische REY-exports op Funded liepen dóór na een
   breach. Vergelijk je oud met nieuw, dan is dát het verschil — niet de strategie.
3. **Wait-for-cap staat nu hard op `true`.** Je vroeg of dat al in het firm-programma zat. **Nee.**
   De registry levert de laddertrede en de minimum payout; "aanvragen op de volle trede" versus
   "aanvragen zodra het mag" is een beleidskeuze die nergens anders vastligt. Ik heb hem op je
   huidige stand bevroren. Wil je hem terug als knop, zeg het — het is één regel.

### Nog niet gedaan

De groepsnummering heeft gaten (0, 3–9, 11–14; geen 1, 2 en 10) omdat *Reference Timezone* en
*Trading Boundary* onder TIME GATE zijn blijven zitten. Ik heb ze **bewust niet hernummerd** midden
in je review — dat zou je referentiepunten verschuiven. Zeg het als je ze aaneengesloten wilt.
De uitrol naar de andere acht `v1_0_0`-scripts en de vier TORO's wacht op jouw akkoord op REY.

---

## 25-08 · Scrum Master → ALLE CHATS — bord-audit: zeven items stonden stil zonder reden

Ferry vroeg om een volledige controle op verdeling, eigenaarschap en stilstand. Uitkomst: **het
bord loog op zeven plekken**, allemaal in dezelfde richting — werk dat kón, stond geparkeerd.

### 🟦 Middleware App — vier items zijn los, en jullie waren de enige die het niet konden weten

`blocked` → `todo`, alle vier omdat **D-06 vanochtend is opgeleverd**:

| | Wat |
|---|---|
| **D-40** | account-blokkade vóór `ForwardJsonAsync` |
| **D-53** | `quantity_multiplier` per account uit een qty-map |
| **D-05** | Python fan-out afvoeren (hing aan D-02, dat aan D-06 hing) |
| **D-07** | commissie per contract — hing aan D-08 dat al `done` was |

**D-40 en D-53 samen bouwen**, zelfde functie, zelfde plek. En bij D-40: de echte PMT-weigering is
nog steeds nodig om de tien gokmarkers in `Rejected()` te vervangen, **maar dat is een verfijning
van één functie en geen reden om niet te beginnen.** Bouw de poort.

Bij **D-07** is de openstaande vraag inmiddels ook beantwoord: per besluit van Ferry 24-08 wint de
registry, dus **0,37** voor MNQ/MES/MYM. Wat resteert is verifiëren tegen `Cash_History`.

Start met **D-59** (`Mex.Journal.Receiver` in de `.sln`) — één commando, en anders bouwt jullie
eigen build groen zonder het live pad aan te raken.

### 🟨 Backtest Setup — één commando deblokkeert drie items

⚠️ **D-10 staat sinds 20-08 stil op iets dat al af is.** `D-36` — de NQ pilot-export — is die dag
opgeleverd. Het item zegt "wacht op validator-output", maar er wordt op niets gewacht: er moet
iemand `python tools/validate_dataset.py` draaien.

**Keten: D-10 → D-18 (Ferry beslist het OOS-venster) → D-34 (Web kan de publieke claims afronden).**
Drie items los met één commando, en Web staat er al vijf dagen op te wachten zonder het te weten.

Verder open bij jullie: D-54, D-55, D-56, D-43, D-50, D-15, D-16, D-38, D-39, D-25, D-27.

### 🟩 Pine Dev — D-61 is afgerond, en er liggen er nu zes

**D-61 staat op `done`** — ik heb hem geverifieerd, en Backtest Setup kan de uitzondering in
`fleet.PINE_DEFECTS` weghalen.

Open: **D-64** en **D-65** (nieuw, uit mijn sweep — begin bij D-65, want dat kan D-63 verklaren),
**D-44**, **D-63**, **D-41**, **D-42**, **D-51**, **D-57**.

### 🟪 Web — je stond geblokkeerd zonder dat het op het bord stond

**D-34 heeft twee remmen, en geen van beide ben jij:** mijn review, en **D-18** (Ferry's besluit over
het OOS-venster). Zolang dat besluit niet valt kun je de publieke claims niet definitief maken.
D-18 staat nu op `todo` in plaats van `blocked` — het is vandaag beslisbaar.

---

### Wat ik van mezelf moest rechtzetten

- **Drie items droegen de verkeerde eigenaar.** D-03, D-11 en D-31 stonden op een chat terwijl de
  volgende handeling op de VPS of in een dashboard plaatsvindt. Die zijn nu van Ferry. D-31 stond
  zelfs op míjn naam terwijl het bouwwerk al klaar was — dan kijkt niemand ernaar.
- **D-17 en D-34 staan op `review`, en dat betekent dat ze op mij wachten**, niet op hun eigenaar.
  Staat op mijn lijst.
- **De les uit D-10, en die geldt voor het hele bord:** schrijf een item als een opdracht, niet als
  een toestand. *"Wacht op validator-output"* nodigt uit tot wachten, ook als de invoer allang
  binnen is. *"Draai `tools/validate_dataset.py`"* doet dat niet.

---

## 25-08 · Scrum Master → ALLE CHATS — 🔴 D-18 beslist: OOS is forward, niet historisch

**Ferry heeft optie B gekozen.** Dit raakt iedereen die iets over prestaties opschrijft, dus lees dit
ook als je denkt dat het niet over jouw map gaat.

### Wat er nu geldt

> De drie jaar **2023–2026 heten validatie**, niet out-of-sample.
> **Echte OOS loopt forward vanaf het bevriezen van een config.**

De `v1_0_0`-configs zijn bevroren op **23-08-2026**. Er is dus op dit moment **twee dagen** echte
out-of-sample-historie.

⚠️ **Dat betekent: claim nergens dat deze vloot out-of-sample bewezen is.** Niet op de site, niet in
een rapport, niet tegenover een prop firm. **Ook de sweep-cijfers van 25-08 vallen volledig binnen
het validatievenster** — MATADOR's $30,59/account-dag is een validatiecijfer, geen OOS-cijfer.

Vastgelegd in `CLAUDE.md` zodat niemand het per ongeluk anders opschrijft.

### 🟪 Web — D-34 is hiermee gedeblokkeerd

Je kunt de publieke claims nu definitief maken. De juiste formulering is **"gevalideerd op drie jaar
(2023–2026)"**, niet "3 jaar out-of-sample". Wil je iets over OOS zeggen, dan is het eerlijke antwoord
dat het forward-tracking is dat op 23-08-2026 begonnen is.

Daarna blijft het op `review` wachten op mij.

### 🟨 Backtest Setup — D-10 vervalt

Dat item bestond uitsluitend om **optie A** mogelijk te maken (een pre-2023 OOS-venster
herselecteren). Die route is er niet meer.

*Correctie op wat ik een uur geleden schreef: ik noemde D-10 "één commando dat drie items
deblokkeert". Dat klopte op dat moment, maar Ferry heeft D-18 direct beslist en daarmee is de route
overbodig geworden. Draai dat commando niet.*

Wil je de CVD-diepte alsnog weten, dan mag dat — maar het is nu nieuwsgierigheid, geen blokkade, en
`normalize.py` behandelt de canonical CVD toch als deterministische OHLCV-proxy.

### Iedereen — één ding om in je achterhoofd te houden

Vanaf nu bouwt elke handelsdag echte OOS-historie op. Dat maakt de **forward-tracking van de vloot**
(Fleet Performance, de reconciliatielaag, D-03) belangrijker dan hij gisteren was: het is straks het
enige out-of-sample-bewijs dat we hebben.

---

## 22 — Pine Dev → Ferry · uitrol v2.2.0: zeven scripts klaar, twee kunnen niet mee

Nummering en uitrol gedaan. **Zeven van de negen `v1_0_0`-scripts staan op v2.2.0.**

### De paneelnummering loopt nu aaneengesloten 0–13

Precies de volgorde uit `INPUT_SPEC_v2.md`. *Reference Timezone* en *Trading Boundary* kregen
hun eigen groep (1 en 2), Alerts 11→10, Visuals Strategy 12→11, Visuals Indicators 13→12,
Developer 14→13. De gaten (er was geen 1, 2 en 10) zijn weg.

Om de paneelvolgorde numeriek te krijgen zijn twee inputblokken **fysiek verplaatst**: het
TIME GATE-blok naar boven, de visuals-inputs naar achter de alert-routering. Alleen de
declaratievolgorde van inputs; er is geen enkele berekening verplaatst, en de statische
controle (haakjesbalans, dubbele declaraties, verweesde vervolgregels, scope-voor-gebruik)
is op alle zeven schoon.

| Script | Inputs | Regels |
|---|---|---|
| EL REY MNQ PROD EOD | 170 | 2079 |
| EL REY MNQ PROD INTRA | 170 | 2079 |
| EL MATADOR MES PROD EOD | 173 | 2087 |
| EL LEON MYM PROD EOD | 170 | 2079 |
| EL LEON MYM CON EOD Q2 | 170 | 2079 |
| EL LEON MYM CON INTRA Q2 | 170 | 2079 |
| EL BANDIDO MYM HF EOD | 170 | 2080 |

MATADOR heeft er drie extra: zijn dagverlieslimiet-knoppen. Die stonden in het verkeerde blok
en zetten groep 8 vóór groep 7 in het paneel; verplaatst naar ACCOUNT — Guard.

**Elk script houdt zijn eigen presets.** Ik heb ze niet overgetypt maar per script
drieweg-gemerged tegen de gemeenschappelijke basis, en daarna geverifieerd dat het verschil
met EL REY exact en alleen de eigen parameters is: contractgrootte, expiry, stop, FVG-venster,
CVD-count, R-multiple, day-cap, firm-preset, commissie, titel en shorttitle. `SCRIPT_NAME` is
per script gezet, dus de Discord-kaarten dragen eindelijk de juiste naam.

### 🔴 EL PATRON en EL TESORO kunnen hier niet mee — en de reden is groter dan de uitrol

Die twee komen uit een **oudere generatie van het vendor-pakket** dan de andere zeven: 1871
regels tegen 1931, met de stability-preset-laag er nog in (63 verwijzingen naar `stabilityOn`,
`GROUP_STAB`, de richtings-uurkaarten) en de oude zes regimevensters.

Dat alleen was op te lossen. Dit niet:

> **Beide MGC-scripts draaien de niet-canonieke delta-engine.** Ze gebruiken
> `ta.requestVolumeDelta` met een per-bar auto-guard en `ta.barssince`-streaks. De andere zeven
> gebruiken de deterministische OHLCV-polariteitsproxy — de canonieke engine uit **D-09**.

Het sjabloon van EL REY over ze heen leggen zou hun delta-engine stilzwijgend vervangen. Dat is
geen herstructurering meer, dat is een signaalwijziging op de twee engines waarvan het bewijs
sowieso al onder het MGC-voorbehoud staat. Ik heb ze daarom **onaangeraakt gelaten**.

Er zit nog een tweede addertje in: **`skipMonEarly` staat in PATRON op `true`.** Jouw besluit 7
("Skip Monday weg, oude aanname") is voor de andere zeven gedragsneutraal — daar stond hij uit.
Voor PATRON niet: hem weghalen zet de maandagochtend-blokkade áán het handelen. Dat is een
parameterbesluit, geen opruiming, en dat is aan jou.

**Wat ik voorstel:** PATRON en TESORO in één aparte ronde, waarin eerst de delta-engine-vraag
valt (canoniek maken = nieuwe onderzoeksronde vanaf trap 1, of laten staan en de
herstructurering met de hand op hún tekst doen). Zeg welke kant je op wilt.

### De vier EL TORO's staan ook nog

Andere, slankere lijn: 1662 regels, 131 inputs, 543 regels verschil met de basis. Hun
delta-engine is wél canoniek, dus daar zit het probleem niet — het is gewoon een tweede port.
Wachten op jouw akkoord op de zeven, dan is het één ronde werk.

---

## 23 — Pine Dev → Ferry · de vier EL TORO's staan op v2.2.0

Uitrol af voor de eval-vloot. **Alle vier de EL TORO-scripts** dragen nu dezelfde structuur
als de zeven `v1_0_0`-scripts: paneel aaneengesloten **0–13**, Engelse labels, dezelfde
groepsnamen, dezelfde visuals.

| Script | Inputs | Regels | Commissie |
|---|---|---|---|
| EL TORO NQ SNIP INTRA | 160 | 1968 | 1,55 |
| EL TORO NQ HF INTRA | 160 | 1968 | 1,55 |
| EL TORO ES FAST INTRA | 160 | 1969 | 1,55 |
| EL TORO GC SNIPER EOD | 160 | 1969 | 1,75 |

Dit was **geen merge maar een echte port.** EL TORO komt uit een andere, slankere lijn — 543
regels verschil met de basis van de andere zeven — dus het sjabloon van EL REY eroverheen
leggen was geen optie. Elke wijziging is los toegepast op TORO's eigen tekst, met een
controle per stap. Presets geverifieerd en ongewijzigd: contractgrootte, stop, TP, R-multiple,
FVG-venster, CVD-count, expiry, firm-preset, VWAP-veto en commissie staan er allemaal nog
precies zo in.

### Wat erbij kwam (allemaal default UIT)

De zes signaalfilters (BBWP, EMA, MFI, volumeprofiel, discount/premium, long/short) en de
**daily risk-gate uit D-45** — dat laatste was een openstaand uitrolpunt en zit nu ook hier.
Verder de negen regimevensters, de RTH/ETH-dag-grens, en de twee nieuwe visuals-groepen met
de FVG-dropdowns, de drie achtergrondlagen en de vijf account-eventmarkers. Het exit-label
draagt nu MFE en MAE. Bot Name komt uit de scripttitel, dus ook deze vier kwamen tot vandaag
binnen als *TESORO*.

**Hersteld:** ook hier ontbrak de long-entry driehoek. Dat maakt het compleet — het zat in
alle dertien scripts van beide pakketten.

### 🔴 Twee dingen die ik bewust NIET heb doorgevoerd

1. **`skipMonEarly` staat in alle vier op `true`** — net als in PATRON. Jouw besluit 7
   ("Skip Monday weg") was voor de zeven gedragsneutraal omdat hij daar uit stond. Hier niet:
   weghalen zet de maandagochtend-blokkade uit en dat verandert de trades. **De knop staat er
   dus nog**, onder TIME GATE. Zeg het als hij alsnog weg moet.
2. **De MEX policy-laag blijft staan.** In EL REY heb ik die verwijderd omdat hij op "Manual"
   stond en dus nooit iets deed. In EL TORO doet hij wél werk: hij levert de
   instrument-mismatch-waarschuwing die je gisteren zag, en overschrijft qty, max stop en
   day-cap als je een preset kiest. Weghalen zou die guard slopen. Idem voor `evalTrack`
   (stopt executies zodra de eval gehaald is) en `evalTrailEod`.

Daarmee is de hele vloot behalve **EL PATRON en EL TESORO** om. Die twee wachten nog op jouw
richting over de niet-canonieke delta-engine — zie item 22.

---

## 24 — Pine Dev → Ferry · PATRON en TESORO om (optie C). De hele vloot staat op v2.2.0

Alle **dertien** scripts dragen nu dezelfde structuur: paneel aaneengesloten 0–13, Engelse
labels, dezelfde groepen, dezelfde visuals, en `SCRIPT_NAME` per script — de Discord-kaarten
komen niet langer als *TESORO* binnen.

| | Inputs | Regels |
|---|---|---|
| EL PATRON MGC AGG EOD | 170 | 2070 |
| EL TESORO MGC CON EOD | 170 | 2070 |

Presets geverifieerd ongewijzigd: contractgrootte, stop, R-multiple, FVG-venster, CVD-count,
expiry, firm-preset, VWAP-veto, dag-exit, trail, BE, `tradeSunday`, `marketRegimeMode`,
commissie (0,52 = MGC).

### De delta-motor zit nu achter een dropdown, en de default verandert niets

Groep 9 draagt **"Delta engine"** met twee standen:

- **`TradingView volume delta` — DEFAULT.** Letterlijk de motor die deze twee altijd al
  draaiden: `ta.requestVolumeDelta`, `ta.barssince`-streaks, inclusief de auto-guard voor
  symbolen zonder volume. **Vandaag verandert er geen enkel signaal.**
- **`Research OHLCV proxy`.** De canonieke motor uit D-09 waar de Python-backtester op
  rekent (`backtest/indicators.py:41`, expliciet onafhankelijk van Pine's engine).

> ⚠️ **Zet dit door naar Backtest Setup:** de parity-breuk is hiermee zichtbaar gemaakt, niet
> opgelost. Zolang de dropdown op TV-delta staat, meet de sweep iets anders dan het script
> doet. Dat raakt hun D-56-notitie, die schrijft *"CVD is faithful… native Delta… is niet het
> default-pad"* — dat klopt voor de Python-kant, maar in deze twee `.pine`-bestanden ís native
> delta het default-pad, met `useCVDFilter` aan. Omzetten naar de proxy is een
> onderzoeksronde vanaf trap 1, geen tweak.

### Wat er verder weg is

De **stability-preset-laag** (stond op Manual, dus `stabilityOn` was false en `contractSizeEff`,
`maxStopSizeEff` en `slSizeLegacyEff` vielen alle drie al door naar de gewone inputs — 63
verwijzingen, allemaal inert) en de **richtings-uurkaarten** (`useDirectionalHours` stond uit).
Allebei gedragsneutraal op de default-stand.

### 🔴 Skip Monday is er in vijf scripts uit — en dat verandert wel trades

Jouw besluit. `skipMonEarly` stond op `true` in **PATRON, TESORO en alle vier de EL TORO's**.
Weg betekent dat **maandag 00:00–02:00 ET nu meehandelt** in die vijf. Bij de andere zeven
stond hij al uit, dus daar was het een opruiming; hier is het een parameterwijziging. Als de
eerstvolgende meting op deze vijf afwijkt van de vorige, is dít de eerste kandidaat.

### Stand van de vloot

Dertien scripts, één structuur. Wat nog openstaat is geen Pine-werk meer: de proxy-vraag voor
de MGC-bucket, en het punt uit `frozen-engines.md` dat de bevroren contractgrootte niet
fresh-account-funderbaar is (D-53).

---

## 25 — Pine Dev → Ferry · middleware-route in EL TORO, en een correctie op de vraag

Toegevoegd in alle vier de EL TORO-scripts: **`→ Middleware (fan-out)` + `Middleware secret` +
`Middleware strategy key`**, met de zendtak in `f_sendExec` en `useMiddleware` opgenomen in
`plainAlertsOK` en `execInstance`. Ze staan nu gelijk aan de negen andere.

### Twee dingen kloppen niet aan de aanname, en het tweede is het belangrijkste

**1. Het was niet weggehaald — het heeft nooit bestaan.** Ik heb het door de hele historie
gezocht: `git log -S'routeMiddleware'` op de TORO-bestanden geeft **nul** commits. Het zat niet
in het vendor-pakket en het is niet in de herstructurering gesneuveld.

**2. 🔴 Deze route voert op het live pad geen orders uit — ook niet in de negen andere scripts.**
Ik heb `middleware/dotnet-receiver/src/Mex.Journal.Receiver/Program.cs` nagelezen:

- De receiver authenticeert op de **token in de URL** (`/signal/{token}` tegen
  `MEX_WEBHOOK_SECRET`). Het veld `"secret"` in de body wordt niet gelezen.
- De uitvoerende tak is de **PMT-payload** — herkend op `multiple_accounts` of
  `token`+`data`. Dáár hangen de kill-switch, de qty-map van D-53 en de blocked-gate van
  D-40 aan.
- De `routeMiddleware`-JSON (`secret` / `strategy` / `event` / `action` / …) heeft geen van
  die sleutels en valt door naar de staart-tak "Fase C": opgeslagen als intent plus één
  Discord-regel. **Geen order.**

Dat contract is van de **Python**-middleware (`middleware/app`), en `CLAUDE.md` zegt zelf dat
die niet live draait. Wil je vandaag via de middleware handelen, dan is het antwoord:
**zet `→ PMT Tradovate` aan en richt de alert-URL op `mw.mex-traders.com/signal/<secret>`.**
Dat is het pad dat wél uitvoert, en dat is ook wat de andere scripts doen. Ik heb dat in de
tooltip van de schakelaar gezet zodat niemand er nog in trapt.

### Meegenomen: `mwStrategy` stond in alle negen op `"GC"`

Zelfde soort fout als `botName = "MΞX ΞL TΞSORO"`: één default die in het hele pakket bleef
staan. Op vier MYM-, twee MNQ- en één MES-script is `GC` gewoon de verkeerde sleutel. Alle
dertien staan nu op hun eigen **shorttitle** (`REY-MNQ-P`, `MAT-MES-P`, `TOR-NQ-SN`, …). Moet
overeenkomen met de sleutel in `accounts.yaml`.

⚠️ **Voor Middleware App:** `middleware/accounts.example.yaml` is achterhaald — de comments
koppelen *El Rey → ES* en *El Tesoro → GC*, wat niet meer bestaat. Als de shorttitle de
sleutel wordt, moet dat bestand mee.
