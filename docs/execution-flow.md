# Execution flow — wat we doorlaten en op welke manier

> **Kernregel (Ferry, 05-09):** een trade telt pas als PMT bevestigt. Alles wat
> Pine simuleert zonder PMT-bevestiging is een signaal-poging, geen trade. Boekingen
> mogen wel getoond worden als `unconfirmed`, maar nooit als P&L.

**Eigenaar van dit document: Scrum Master.** Eerste versie geschreven door CLO
op 07-09 (item 30 in `docs/inbox.md`), ter correctie voorgelegd aan SM. Wijzigingen
aan de tabellen hieronder lopen via SM; wijzigingen aan de kernregels boven de
tabellen lopen via CLO.

Complementair aan **`docs/execution-contract.md`** (Pine Dev, Pine→receiver→PMT
contract op payload-niveau). Waar `execution-contract` beschrijft **wat er verstuurd
wordt en wat PMT ervan verwacht**, beschrijft dit document **welke gates een signaal
in het live pad passeert, wat de boekingseffecten zijn, en wat er per account-type
gepubliceerd mag worden**.

---

## 1. Uitgangspunten (drie regels waar de rest op leunt)

1. **Trade telt pas als PMT bevestigt.** Zonder `sent 200` en zonder klopfout-vrij
   antwoord van PMT is er geen trade — hoogstens een intentie. Op dashboards,
   widgets en de publieke site is dat verschil onmiskenbaar zichtbaar.
2. **Verspreide config is drift.** Elke datum, elke cap, elke webhook heeft één
   bron. Elke andere plek die diezelfde waarde leest, doet dat via die bron.
   Waar dat vandaag nog niet zo is, staat het bovenaan de openstaande D-items
   (D-53, item 31 in `inbox.md`, D-11).
3. **Elke gate schrijft eenduidig.** Naam, uitkomst, reden en account gaan in
   dezelfde vorm in het routed-log, ongeacht welke gate. Uniformiteit maakt de
   flow controleerbaar zonder dat je code hoeft te lezen.

---

## 2. Tabel 1 — Gate-flow

De keten die een signaal doorloopt vanaf binnenkomst op `/signal/{token}` tot
publicatie in het dashboard. Volgorde is bindend: elke gate ná deze rij ziet
alleen wat de voorgaande hebben doorgelaten. `pass` = gate laat door en registreert
niets bijzonders; `reject` = gate stopt de flow en registreert een reden.

| # | Gate | Plek | Criterium | Pass-log | Reject-log | Beheer |
|---|---|---|---|---|---|---|
| **0** | Time-gate | Pine: `[validFrom, validUntil]` per script · .NET: `MEX_ACCOUNT_ACTIVE_UNTIL` per account (dubbelslot) | `now ∈ [validFrom, validUntil]` — hard-stop op entries, rolling grace 24u op exits | *(geen speciale regel)* | `gate=time outcome=reject reason=outside window` + Discord soft-notify eenmalig op de grens | Pine Dev (bron) + Middleware App (dubbelslot). **Openstaand: item 31 in `inbox.md`** |
| **1** | Auth | `.NET Program.cs:114` | `token == MEX_WEBHOOK_SECRET` | *(geen)* | HTTP 401 | Middleware App |
| **2** | Deduplicatie | `.NET Program.cs:122-128` | body-hash niet in 5s-window | *(geen)* | `duplicate` | Middleware App |
| **3** | Kill-switch | `Runtime.Armed` | `Armed == true` én signaal is entry (buy/sell) | *(geen)* | `blocked: kill-switch` | Ferry (env) |
| **4** | Qty-override (D-53) | `AccountQtyMap` in `Program.cs:157` | er is een `MEX_ACCOUNT_QTY_MULTIPLIERS`-entry voor dit account | body `multiple_accounts[0].quantity_multiplier` wordt overschreven; `body` wordt herbouwd en die gewijzigde versie gaat verder de keten in | *(geen reject — deze gate stopt nooit)* | Ferry (env) + Middleware App |
| **5** | Blocked-gate (D-40) | `AccountBlockGate` in `Program.cs` | account niet op slot na eerdere PMT-weigering met day-cap/DLL/payout-cap marker; reset op 18:00 ET | *(geen)* | `GEWEIGERD lokaal — day-cap/DLL blokkade actief (eerder: <marker>)` + Discord `⛔ Order NIET geplaatst` | Middleware App |
| **6** | Risk-gate (D-02) | `AccountRiskGate` in `Program.cs` | account niet in `MEX_HALTED_ACCOUNTS`, entry-cap niet overschreden voor huidige sessiedag (18:00 ET roll) | `RegisterEntry` na succesvolle forward | `GEWEIGERD lokaal — risk-gate: <reden>` + Discord | Ferry (env) + Middleware App |
| **7** | Auto-DLL/target halt | **⚠️ te bouwen** — leest firm-registry (`firms.py`) + PMT-fills-som per sessiedag; halt bij X% van cap; hard halt bij 100% | binnen firm-caps voor huidige sessiedag | *(geen)* | `[DLL]` / `[TARGET]` / `[PAYOUT-CAP]` + Discord | Middleware App + Legacy. **Openstaand: item 32 in `inbox.md`, gate #7 in de exit-echo-scope** |
| **8** | Routing (Tradovate/Rithmic) | `Program.cs` | account in `MEX_PMT_RITHMIC_ACCOUNTS`? dan Rithmic, anders Tradovate | *(geen)* | *(geen — altijd één doel)* | Ferry (env) |
| **9** | Forward | `ForwardJsonAsync` in `Program.cs` | HTTP POST naar PMT slaagt (< 400) | *(status wordt aan Rejected() gegeven)* | HTTP 4xx/5xx of netwerk-error → `error …` | Middleware App |
| **10** | Rejected() na forward | `Rejected()` in `Program.cs` (na fix 25-08) | reply bevat expliciete fout-indicator (`error:true` / non-lege error-string / `success:false` / `status:false` / tekst-marker) | `sent 200 (poging N)` | `GEWEIGERD 200 door doelserver: <reply>` + Discord | Middleware App |
| **11** | Executiepoort (D-46b) | `routed_journal.pair_events_with_report()` | voor een FILL-card is er een PMT-record met `sent 200` binnen `PMT_MATCH_WINDOW_S` (900s) op zelfde account + symbool + richting | trade komt in `trades`-lijst | fill komt in `unconfirmed`-lijst — geen boeking in LIVE-tab | Middleware App |
| **12** | Exit-echo (⚠️ te bouwen) | `routed_journal.pair_events_with_report()` — nieuwe uitbreiding | voor elke EXIT-card is er een PMT-close-record binnen `PMT_MATCH_WINDOW_S` | trade `closed = true`, P&L geboekt | trade blijft `closed = false`, EXIT-card markeert `pending-echo` — geen P&L-boeking | Middleware App. **Openstaand: item 32 in `inbox.md`. Vóór bouw: grep-check of PMT `sent 200` überhaupt op bracket-exits schrijft** |
| **13** | Sessie-bucket | `dashboard_state._aggregate()` + `fills_pairing.session_date()` | sessiedag rolt om 18:00 ET; trade telt in de sessie waarin hij CLOSED is | trade in `today`/`yesterday`/`week` window | trade in oudere periode | Middleware App |

### 2.1 SM-correcties op de eerste versie (07-09)

Getoetst tegen `Program.cs` op de werkbranch. Drie dingen weken af; de rest van de
tabel klopte, inclusief de regelnummers voor auth (114) en dedup (122-128), de
`PMT_MATCH_WINDOW_S` van 900s, en alle genoemde functienamen
(`pair_events_with_report`, `_aggregate`, `session_date`).

**a. De volgorde klopte niet, en dit document maakt de volgorde bindend.**
De qty-override stond als #7, ná de blocked-gate en de risk-gate. In de code draait
hij op **regel 157** — dus vóór de blocked-gate (168) en vóór de risk-gate (185).
Hij is verplaatst naar **#4** en de gates daarachter zijn doorgenummerd; de
verwijzingen naar de auto-DLL-gate in §5 en §7 zijn meegeschoven van #6 naar #7.

**b. Gevolg van die volgorde, en het is geen cosmetisch punt.** De qty-override
herschrijft `body` vóórdat de blocked- en risk-gate mogen weigeren. Weigert een van
die twee, dan schrijft `AppendAsync` de **gewijzigde** body naar `routed_*.jsonl` —
inclusief een `quantity_multiplier` die nooit verstuurd is. Wie later dat journaal
leest ziet een order-grootte die niet bestaan heeft. Niet gevaarlijk, wel misleidend
bij precies het soort forensiek waar §4 op leunt. **Melden bij Middleware App:
overweeg de override ná de gates te zetten, of de onbewerkte body te loggen bij een
reject.**

**c. 🔴 De pass-log van de qty-override beweerde iets onwaars, en dat is de
belangrijke correctie.** De eerste versie noteerde *"ontbrekend account = Pine's `1`
blijft"*, wat leest als: een account zonder entry in de map handelt met 1 contract.
**Dat is niet zo.** Pine stuurt naast de multiplier zijn eigen `"quantity"` — bij
MATADOR **6 contracten** — en die wordt door deze gate niet aangeraakt. De multiplier
op 1 laten betekent dus **Pine's volle bevroren grootte**, precies de grootte die de
vloot-sweep als niet-fresh-account-funderbaar aanwijst.

De formulering komt uit het codecommentaar zelf (`Program.cs:156`: *"Vers account =
1"*), dus CLO heeft hem te goeder trouw overgenomen — de fout zit in de bron. Die
staat sinds 25-08 als openstaande review-bevinding bij D-53: de gate kan met een
integer-multiplier ≥ 1 alleen gelijkhouden of verhogen, nooit naar beneden schalen.

⚠️ **Zolang D-53 niet gefixt is, is `MEX_ACCOUNT_QTY_MULTIPLIERS` geen rem maar
hoogstens een gaspedaal.** Zet die env-var niet in de veronderstelling dat een vers
account er klein mee handelt.

Notify-kaarten (Discord, Telegram, tier-A/B/C) lopen door dezelfde pipeline maar
zijn geen executie — die zitten in tabel 3 van `middleware/docs/D-28-NOTIFY-CHANNEL.md`
en worden hier niet herhaald.

---

## 3. Tabel 2 — Publicatie-semantiek per account-type

**Metriek per account-klasse verschilt fundamenteel.** Wat we voor de ene groep tellen
(bedragen) is voor de andere groep niet-informatief (evals). Dit is geen UI-toggle
maar een andere set aan berekeningen die het account-type activeert.

| Type | Definitie | Publiceer | Onderdruk | Bron voor bedrag | UI-default |
|---|---|---|---|---|---|
| **Eval — actief** | account-id begint met `APEX*` / `AP*` en niet `PA*` | `passed`-teller, `breached`-teller, `nog-lopend`-teller — **elk genormaliseerd naar 50k-equivalent** (grootte / 50 000; 100k = 2×, 300k = 6×) | bedragen, saldo | — | ☑ Aantallen · ☑ 50k-genormaliseerd |
| **Eval — passed** | eval-account met `PASSED`-record in het log | telt mee als +1 in `passed`-teller (× 50k-factor) | | — | zelfde |
| **Eval — breached** | eval-account met `BREACHED`-record | telt mee als +1 in `breached`-teller (× 50k-factor) | | — | zelfde |
| **Funded (PA) — geverifieerd** | account-id begint met `PA` én draagt `verified_amount + verified_at` binnen 7 dagen | saldo + winrate op basis van saldo · label `✓ verified <datum>` | ongeverifieerde bedragen | `verified_amount` in `dashboard_meta` of Fleet Performance DB | ☑ Saldo tonen |
| **Funded (PA) — ongeverifieerd** | idem, maar geen recente `verified_at` | naar keuze: onderdrukt, of "laatste bekende saldo (ongeverifieerd)" met waarschuwing | huidige realtime pretensie | Pine-simulatie (te vervangen door broker-truth) | ☑ Verberg (default aan) |
| **Fantoom-account** | Discord-cards zonder PMT-record (PA019-scenario) | *niets* | alles | — | (structureel gefilterd door `amap`-check in `pair_events()`) |

### 3.1 Widget-labels (verplicht)

Elke Scriptable-widget-view draagt een klein label direct onder het bedrag, zodat
Ferry in één oogopslag weet welk regime hij bekijkt:

- **Eval-views**: `50k-eq · N=<aantal>` (bijvoorbeeld `50k-eq · N=12` voor 12
  50k-equivalente passes).
- **Funded-views**: `✓ verified <ISO-datum>` als de saldo's binnen 7 dagen
  geverifieerd zijn; `⚠ unverified since <ISO-datum>` anders.

Zonder label leest Ferry het widget niet correct.

### 3.2 UI-toggles voor de viewer (owner-mode)

- **Account-type filter**: ☐ Eval  ☐ Funded — welke groep tonen.
- **Weergave-modus**: ○ Aantallen  ○ Saldo's  ● Combinatie.
- **50k-normalisering**: ☑ Genormaliseerd (default aan voor evals).
- **Alleen geverifieerd saldo**: ☑ Verberg ongeverifieerd (default aan voor funded).
- **Verberg spook-trades**: ☑ Verberg trades geblokkeerd door DLL/target/kill (default aan).
- **Bron**: ☑ PMT-bevestigd  ☑ Pine-simulatie (met markering per rij).

### 3.3 Publieke site (`web/**`)

- `mex_units.roles.for_public()` (units-only, geen currency-fields) blijft de gate.
- Uitbreiding: `mex_units.roles.for_public_evals()` — levert **aantallen genormaliseerd**
  zonder bedragen. Nieuwe test: verzeker dat geen enkele eval-metric door `for_public()`
  glipt.
- Funded-saldo's mogen alleen op de publieke site als ze `verified` én expliciet
  vrijgegeven zijn (default: niet). Precisie later te bepalen; nu-default is *geen*
  funded-saldo publiek.

---

## 4. Bron-van-waarheid per fase

Waar leunt de flow op broker-truth, en waar op een proxy?

| Fase | Bron | Broker-truth? | Wat als de bron liegt? |
|---|---|---|---|
| Signaal-intent (Pine denkt "koop MGC bij 4700") | Pine-simulatie | ❌ proxy | onvermijdelijk — Pine ís de intentiebron |
| Order-verzending naar PMT | `sent 200` in `routed_*.jsonl` | ⚠️ semi-proxy (bevestigt POST, niet dispatch naar broker) | vandaag beleefd bij Rejected()-bug: valse GEWEIGERDs voor geslaagde orders → dashboard-lek |
| Order-acceptatie door PMT | PMT reply body (`Successfully send / error:false`) | ⚠️ semi-proxy (PMT's woord over Tradovate's actie) | Rithmic-poller zou dit vervangen door broker-echo |
| Fill (broker plaatst positie) | Discord FILL-card van Pine | ❌ proxy (Pine's aanname op basis van eigen bracket-simulatie) | spook-P&L; oorsprong van PATRON $759 op 24-08 (D-48) |
| Fill (broker-side echt) | Fills-CSV export uit Tradovate | ✅ broker-truth, T+1 handmatig | vandaag: enige echte bevestiging, maar met vertraging |
| Exit + P&L-boeking | Discord EXIT-card van Pine | ❌ proxy (Pine's aanname dat bracket sloot) | **kernregel-gat — zie gate #12** |
| Exit + P&L echt | Fills-CSV pairing | ✅ broker-truth, T+1 handmatig | de reconciliatie-laag (D-03) meet drift, mits ingelezen |
| Positie-status live | Pine's positie-state | ❌ proxy | vandaag geen live broker-echo; Rithmic zou dit vervangen |
| Saldo funded-account | Handmatige `verified_amount` | ⚠️ hand-input | vraagt discipline, is de expliciete afspraak (Ferry, 07-09) |
| Aantallen eval-accounts | `PASSED` / `BREACHED` cards + prop-firm-dashboard | ✅ event-based en van broker | betrouwbaar bij één datapunt per gebeurtenis |

---

## 5. Bekende blinde vlekken

Punten waar de flow **structureel** iets niet ziet. Bewust benoemd zodat we ze niet
per ongeluk vergeten.

- **Handmatige acties bij de broker.** Vandaag geen dekking; Ferry heeft 05-09 en 07-09
  bevestigd *"ik grijp nergens op in"* — de blinde vlek is dus bewust geaccepteerd.
  Als dat verandert: dit doc wijzigen én een detectie-workflow inbouwen (halt-first,
  manual-override-knop, of Rithmic).
- **PMT-close-echo bij bracket-exits.** Onbekend of PMT een `sent 200` schrijft
  wanneer TP/SL server-side worden uitgevoerd. **Openstaande grep-check in item 32
  van `inbox.md`.** Antwoord bepaalt of gate #12 met huidige middelen bouwbaar is.
- **Tradovate-side weigeringen ná PMT's `sent 200`.** PMT accepteert onze POST,
  Tradovate kan alsnog weigeren (buiten uur, symbool niet beschikbaar, account-issue).
  Vandaag zichtbaar via een latere PMT-callback of via Fills-CSV drift, niet realtime.
- **Broker-initiated acties** (margin call, forced close, exchange halt). Niet-real-time
  detecteerbaar zonder API. Fills-CSV vangt ze wel op met T+1 vertraging.
- **Cross-firm-consistentie in metrieken.** Als jij morgen MFFU/TPT/Day Traders erbij
  neemt, respecteert de gate-flow dat automatisch (broker-agnostisch); de publicatie-
  semantiek van tabel 2 óók (50k-normalisering geldt per firm-grootte). Als één firm
  een andere DLL-semantiek heeft, moet gate #7's registry-lookup dat weerspiegelen.

---

## 6. Route-check (openstaand)

**Vóór item 32 gebouwd wordt:** Middleware App draait één grep-check op
`/root/intent-store/routed_*.jsonl` (~4 weken data) om te bepalen of PMT `sent 200`
schrijft bij bracket-exits, en om vier meetpunten te leveren die de kernregel toetsen:

1. % FILL-cards met een PMT-record binnen 15 min → sterkte van de PMT-echo op entries.
2. % PMT-records zonder FILL-card → hoeveel orders vullen niet (limit-time-outs
   verwacht; ander patroon = signaal).
3. % EXIT-cards met een PMT-close-echo → bestaat de exit-echo überhaupt?
4. Cross-check tegen Fills-CSV voor overlappende periode → broker-fills zonder
   Pine/PMT-record = handmatig of dead-letter; Pine/PMT-records zonder broker-fill =
   spook.

Uitkomst hoort terug in **§5 (Bekende blinde vlekken)** en bepaalt of gate #12
haalbaar is met huidige middelen, of dat exit-verifikatie op Fills-CSV/Rithmic moet
leunen. Zonder deze check is item 32 een gok.

---

## 7. Waar deze basis het volgende stuk raakt

Dit document is de basis. Openstaande D-items die er op leunen (moment van schrijven):

- **Item 31 in `inbox.md`** — één centrale time-gate in Pine (gate #0 wordt daarmee
  reëel).
- **Item 32 in `inbox.md`** — PMT-echo op exit-kant (gate #12) + notificatie-taxonomie
  (verrijking van gate #10's Discord-melding).
- **Item 33 in `inbox.md`** — publicatie-semantiek per account-type (tabel 2 wordt
  geïmplementeerd in `dashboard_state`, `viewer`, en `web/**`).

Wijzigingen aan deze drie items die de gate-flow of publicatie-semantiek raken,
worden hier weerspiegeld — één bron, zoals in §1 regel 2 afgesproken.
