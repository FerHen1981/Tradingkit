# D-77 · Het canonieke event — schema v3

_Eigenaar: Scrum Master. Opgesteld 28-09-2026. Fase 0 van `docs/PLAN-2026-09-27-herijking.md`._
_Review gevraagd aan **Pine Dev** (is elk veld te produceren?) en **Middleware App**_
_(is elke huidige payload eruit te bouwen?)._

> **Wat dit is.** Eén bericht dat Pine naar de middleware stuurt, waaruit de middleware
> zélf elke uitgaande payload bouwt. Vandaag stuurt Pine vijf verschillende berichten naar
> hetzelfde endpoint en beslist het script zelf welke kanalen aan staan. Straks stuurt Pine
> dit ene bericht en beslist de **configuratie** (D-78) waar het heen gaat.

---

## 0. 🔴 Belangrijkste vondst: deze route bestaat al, half

Bij het uitzoeken bleek dit **geen nieuw ontwerp** maar het afmaken van iets dat er al ligt.
🔴 **Correctie 29-09, aangedragen door Pine Dev: het is geen toggle.** In alle dertien
scripts staat sinds v3.2.0 `bool routeMiddleware = false` als **constante** — Pine Dev heeft
hem destijds zelf van input naar constante gezet (D-51) omdat de route niets deed op het live
pad. Aanzetten is dus een **code-wijziging, geen instelling**. De route-*code* ligt er wel,
en dat deel van mijn vondst klopt. Voor de raming van fase 3 scheelt het minder dan ik
schreef: de winst is de bestaande berichtopbouw, de kost is dat er een knop bij moet.

`MEX_EL_MATADOR_MES_PROD_EOD_v1_0_0.pine` heeft naast de vijf routes die we kenden ook:

```pine
bool routeMiddleware = false   // CONSTANTE sinds v3.2.0 (D-51), geen input   // r. 972
mwSecret   = input.string("", "Middleware secret", …)                    // r. 970
mwStrategy = input.string("MAT-MES-P", "Middleware strategy key", …)     // r. 971
```

En `f_sendExec` stuurt daar al een bericht heen (r. 1864):

```json
{"secret":"…","strategy":"MAT-MES-P","event":"ENTRY","action":"buy","symbol":"MES1!",
 "price":5321.25,"order_type":"MKT","dollar_sl":150,"dollar_tp":300,"qty":6}
```

Dat is bijna het canonieke event. **Twee redenen waarom het vandaag niets doet:**

1. **Het was gericht op een middleware die niet meer bestaat.** De tooltip van `mwStrategy`
   zegt *"moet overeenkomen met de sleutel in `accounts.yaml`"* — dat is de **dode Python-route**
   (`middleware/app/router.py`), verwijderd in D-05.
2. **De .NET-receiver herkent het bericht niet.** De routeherkenning test op
   `multiple_accounts` (PMT) · `embeds`/`content` (Discord) · `type=journal`/`csv` (journaal)
   · niet-JSON (PineConnector). Dit bericht matcht geen van die vier en valt door naar de
   *Fase C*-tak, die `node["account"]` leest — een veld dat er **niet in zit**. Resultaat: het
   belandt als generieke intent in `intents_<datum>.jsonl` met een **leeg accountveld**, plus
   een nietszeggende Discord-regel.

➡️ **Gevolg voor fase 3:** Pine hoeft geen nieuwe route te krijgen, alleen een vollediger
bericht op een route die er al is. Dat scheelt aanzienlijk in D-86.

---

## 1. Ontwerpregel

**Het event draagt wat de strategie deed. De configuratie draagt waar het heen gaat.**

Alles wat vandaag per script in TradingView staat en *niet* over de handel gaat — token,
licentie, account-id, webhook-URL, welke kanalen aan — hoort in D-78 en **niet** in dit event.
Alles wat per trade verschilt hoort hier en nergens anders.

---

## 2. Het event

```json
{
  "v": 1,
  "id": "MAT-MES-P:1727539200000:order:1",
  "ts": "2026-09-28T14:30:00Z",
  "strategy": "MAT-MES-P",
  "symbol": "MES1!",
  "kind": "order",
  "action": "buy",
  "qty": 6,
  "price": 5321.25,
  "order_type": "MKT",
  "dollar_sl": 150,
  "dollar_tp": 300,
  "risk": { "trail": false, "trail_stop": 0, "trail_trigger": 0, "trail_freq": 0,
            "breakeven": 0, "breakeven_offset": 0 },
  "text": { "title": "📈 MES1! LONG MARKET", "body": "…", "color": 3447003 },
  "journal": { "event": "ENTRY", "dir": "long", "status": "…", "entry": 5321.25,
               "stop": 5296.25, "target": 5371.25, "qty": 6, "pnl": null,
               "regime": "FAVORABLE", "balance": null, "dist_target": null, "dist_fail": null }
}
```

| Veld | Verplicht | Waarom het zo is |
|---|---|---|
| `v` | ja | Schemaversie. Zonder dit kan de middleware oude en nieuwe berichten niet uit elkaar houden tijdens de schaduwdraai van D-88. |
| `id` | ja | **Idempotentiesleutel, `strategy:ts:kind:seq`** — het volgnummer is nodig omdat twee sluitingen op dezelfde bar kunnen vuren (§3b, blokkade 3). De receiver ontdubbelt vandaag op een SHA-256 van de hele body binnen 5 seconden. Dat faalt twee kanten op: twee identieke signalen op verschillende bars binnen 5 s worden onterecht als duplicaat weggegooid, en een retry ná 5 s wordt onterecht dubbel uitgevoerd. Een expliciete sleutel lost beide op. |
| `ts` | ja | **`timenow`**, UTC, ISO-8601 met `Z` (§3b, voorwaarde 4). De sessie-roll van 18:00 ET wordt in de middleware berekend, niet in Pine. |
| `strategy` | ja | De shorttitle. **Dit is de sleutel waarop de configuratie accounts opzoekt** — `mwStrategy` doet dat al. |
| `symbol` | ja | `syminfo.ticker`. De PineConnector-symboolvertaling (`pcSymbol`) is **configuratie**, geen event-veld. |
| `kind` | ja | `order` · `fill` · `halt` · `derisk` · `payout` · `config` · `info`. ⚠️ **`order` en `fill` zijn bewust gesplitst** — zie §3b, blokkade 2. Bepaalt tevens welke kanalen in aanmerking komen. |
| `action` | bij order/fill | `buy` · `sell` · `close` · **`cancel`** (§3b, voorwaarde 2). |
| `qty` | bij order/fill | Bij `order`: contracten zoals de strategie ze bedoelt. **Bij een sluitende `fill`: de WERKELIJKE positie** (§3b, voorwaarde 1). ⚠️ De **qty-override** (D-53) grijpt hierná in, in de middleware — zie §4. |
| `price` | bij entry/exit | Signaalprijs. Bij een limietorder de limietprijs. |
| `order_type` | bij entry/exit | `MKT` · `LMT`. |
| `dollar_sl` / `dollar_tp` | bij entry | **Afstanden, geen niveaus.** Pine rekent vandaag al zo en PineConnector reconstrueert de absolute prijzen eruit (`price ± afstand`). Houd dat zo; niveaus zouden bij een limietorder meerdere waarheden hebben. |
| `risk` | bij order | Trailing en break-even zoals Pine ze **berekent** uit `useTrail`/`useBreakEven`. 🔴 **Geen constanten** — zie §3c punt 1. |
| `text` | ja | Zie §3. `color` is optioneel; ontbreekt hij, dan kiest de middleware een neutrale kleur. |
| `journal` | **bij `fill`** | De huidige journaalregel als velden in plaats van als kommastring. Bij `kind:"order"` afwezig. Draagt ook **`acct_name`**, omdat die in Pine wordt afgeleid en niet in de middleware nagebouwd mag worden (§3b, voorwaarde 5). |

---

## 3. ✅ BESLIST 28-09 (Ferry): route B — Pine schrijft de tekst

Pine stelt vandaag **ongeveer twintig verschillende kaartteksten** samen: `FILL`, `EXIT`,
`DERISK L1/L2`, `PA DERISK`, `PAYOUT READY`, `CAP LOCK`, `SIGNAL BLOCKED`, `ACCOUNT STARTED`,
`RISK OFF`, `LIMIT EXPIRED`, `CONFIG` en meer — elk met eigen opmaak, emoji en berekende
waarden in de tekst.

**Route A — de middleware rendert.** Het event draagt alleen gestructureerde velden per
`kind`; de middleware bouwt de tekst. Zuiver, en je kunt de kaart wijzigen zonder Pine aan te
raken. **Maar:** twintig sjablonen porteren, elk met eigen berekeningen, en elk verschil is
een verkeerde kaart.

**Route B — Pine schrijft de tekst, de middleware bepaalt de bestemming.** Het event draagt
`text.title` en `text.body` zoals Pine ze nu al samenstelt; de middleware kiest de webhook, de
tier en of hij een kaart rendert. ✅ **GEKOZEN door Ferry op 28-09.**

Waarom B: Ferry's doel (antwoord 4) is *"de instellingen voor kanalen, tokens en weburls
volledig inzichtelijk en beheersbaar in een settings tab"*. Dat gaat over **routing en
credentials**, niet over wie de kaarttekst schrijft. Route A verdrievoudigt fase 3 zonder dat
het dat doel dichterbij brengt. B kan later alsnog naar A groeien — de velden staan er dan al.

Het schema hierboven veronderstelde al B en blijft dus ongewijzigd. ➡️ **Gevolg voor D-87:**
de middleware bouwt de PMT-JSON, het PineConnector-commando en de journaalregel, maar neemt
voor Discord `text.title` en `text.body` **ongewijzigd** over en beslist alleen over webhook,
tier en rendering. De ~20 kaartsjablonen blijven in Pine. Wil je later alsnog naar A, dan
zijn de velden er al — dat is dan een aparte ronde en geen herbouw.

---

## 3b. ✅ Review Pine Dev verwerkt — drie blokkades opgelost, vijf voorwaarden

Pine Dev toetste het schema tegen de dertien scripts en antwoordde op acceptatiecriterium 1
met **nee**: niet elk veld was te produceren. Hun review is grondig en leverde één correctie
op mijn eigen vondst (hierboven) plus acht punten. Dit is de afhandeling.

### 🔴 Blokkade 1 — `journal.*` bestaat niet op een uitvoerende chart

`f_journal` opent met `if useJournal and not execInstance`. Op élke chart die daadwerkelijk
uitvoert wordt de journaalregel dus nooit geschreven — juist daar waar het om gaat. Pine Dev
vroeg of de clausule eruit mag; dat is een gedragswijziging op live charts (een extra
`alert()` per event).

**Besluit: niet weghalen — hij lost zichzelf op.** In fase 3 smelten `f_sendExec`,
`f_sendDiscord` en `f_journal` samen tot **één** `alert()`; het `journal`-object rijdt daarin
mee. De guard wordt dan irrelevant in plaats van verwijderd, er komt **geen** extra alert bij,
en we winnen journaaldata precies op de charts waar die vandaag ontbreekt. ⚠️ Dat is wél
nieuwe data op een bestaande route, dus het valt onder de byte-vergelijking van **D-88**.
*Pine Dev: bevestig dat dit klopt tegen de code voordat D-86 begint.*

### 🔴 Blokkade 2 — order en fill zijn twee momenten

`f_sendExec` vuurt bij het **plaatsen**, `f_journal("FILL")` en de fill-kaart pas nadat de
fill **gedetecteerd** is — bij een limietorder tot `expiryBars` later. Eén `kind:"entry"` dat
zowel `order_type`/`price` als `journal.entry`/`journal.status` draagt, beschrijft dus twee
verschillende momenten.

**Besluit: `kind` wordt gesplitst.** `order` (plaatsing: `action` · `qty` · `price` ·
`order_type` · `dollar_sl` · `dollar_tp`, **geen** `journal`) en `fill` (uitvoering:
`journal.*` verplicht). Dat sluit aan op wat de code werkelijk doet. ➡️ En het lost blokkade 1
mee op: op een `order` is er geen journaalregel nodig, op een `fill` wel — precies het
moment waarop `f_journal` vandaag al zou draaien als de guard er niet stond.

### 🔴 Blokkade 3 — `strategy:ts:kind` is niet uniek

`f_sendExec("close", …)` staat op **zes** plekken, waarvan vier alleen bewaakt worden door
`if posSize != 0` zonder onderlinge uitsluiting. Twee daarvan kunnen op dezelfde bar vuren.
Beide events zouden dan dezelfde sleutel krijgen en de middleware gooit er één weg — precies
de fout die `id` moest voorkomen.

**Besluit: `id` wordt `strategy:ts:kind:seq`**, met een `var int seq` die per verstuurd event
ophoogt. Stabiel binnen een realtime bar, dus retries ontdubbelen nog steeds goed.

🔴 **En de terzijde van Pine Dev is geen terzijde:** dat diezelfde vier plekken allemaal
`strategy.close_all()` kunnen aanroepen op één bar is een **dubbele sluiting op het live
pad**. Dat staat los van dit schema en heeft een eigen nummer gekregen — **D-107**.

### ⚠️ Voorwaarde 1 — `qty` bij een exit

Vijf van de zes close-aanroepen geven `t_qty` mee: de qty die bij de **entry** gezet is.
Alleen de cap-lock gebruikt `math.abs(strategy.position_size)`, de werkelijke positie. Normaal
vallen die samen; **na een gederiskte of gecapte fill niet.**

**Besluit voor het schema: bij `kind:"fill"` met een sluitende actie is `qty` de WERKELIJKE
positie.** Reden: de middleware bouwt hier een sluitorder uit. Sluit je de signaal-qty terwijl
de echte positie kleiner is, dan draai je door naar de andere kant; is hij groter, dan blijft
er een restpositie staan. ⚠️ **Dit betekent dat het huidige gedrag op vijf van de zes plekken
waarschijnlijk al fout is** wanneer derisk of cap heeft ingegrepen. Dat is een live-pad-
bevinding, geen schemakeuze — meegenomen in **D-107**.

### ⚠️ Voorwaarde 2 — "resting order annuleren" gaat als `close` de deur uit

r. 2065 vuurt terwijl `isFlat` waar is: een niet-opgepikte limietorder wordt ingetrokken en
gaat als `f_sendExec("close", …)` naar buiten — op PMT een sluitorder voor een positie die
niet bestaat. **Besluit: `action` krijgt `cancel`** naast `buy`/`sell`/`close`. Eén woord, en
het onderscheid is hard.

### ⚠️ Voorwaarde 3 — `text.*` gaat ongeschermd de JSON in

Werkt vandaag alleen omdat geen enkele kaarttekst een `"` bevat — Pine Dev verifieerde dat,
nul treffers. **Besluit: akkoord met hun voorstel om er `f_jsonEsc()` omheen te bouwen.**
Discipline die op een garantie lijkt is een stille faalmodus.

### ⚠️ Voorwaarde 4 — welke klok

**Besluit: `timenow`, omgerekend naar UTC, ISO-8601 met `Z`.** Dat is het moment waarop het
signaal werkelijk ontstaat. Lukt `str.format_time` met `'T'`- en `'Z'`-literals niet
betrouwbaar, bouw hem dan uit losse delen — de vorm telt, niet de methode.

### ⚠️ Voorwaarde 5 — `jrnlAcct` is afgeleid, niet ingevuld

`f_autoAcctName()` leidt kolom 3 van het journaal af uit `accountID`, `evalStartBal` én
`validFrom`. Verhuist `account_id` naar de configuratie, dan zou de middleware die afleiding
**exact** moeten overnemen — en doet hij dat niet, dan verandert die kolom stilletjes en
breekt de koppeling met bestaande journaalregels.

**Besluit: niet overnemen maar meesturen.** `journal.acct_name` wordt een veld in het event.
De afleiding blijft waar de kennis zit; een kopie in de middleware zou een tweede bron zijn
voor iets dat maar één waarheid heeft. Dit is dezelfde regel als §5 van de Scrum
Master-skill.

---

## 3c. ✅ Review Middleware App verwerkt — schema naar v3

Zij toetsten alle vier de uitgaande routes tegen **echt verkeer** (4539 rijen
`routed_*.jsonl`, `NotifyRoute`, `Program.cs:348`, `journal_sync.py`) en antwoordden op
acceptatiecriterium 2 met **ja**: elke payload is hieruit te bouwen. Drie punten om op te
helderen. Op één daarvan wijk ik van hun voorstel af, en dat is het belangrijkste punt van
deze ronde.

### 🔴 Punt 1 — zes van de "twaalf constanten" zijn geen constanten

Zij zagen twaalf PMT-velden die in hun steekproef altijd `0` of `false` waren en stelden
voor ze als **PMT-format-constanten** in de builder te zetten. **Zes daarvan zijn dat niet.**
Nagemeten in de Pine-bron:

```pine
"trail":            (f_trailOn(_slD) ? "1" : "0")
"trail_stop":       (f_trailOn(_slD) ? f_distPrice(trBufEff) : 0)
"trail_trigger":    (f_trailOn(_slD) ? f_distPrice(trStartEff) : 0)
"trail_freq":       (f_trailOn(_slD) ? f_distPrice(trailUpdateStep) : 0)
"breakeven":        ((useBEeff and _slD > 0) ? f_distPrice(beTrigEff) : "0")
"breakeven_offset": ((useBEeff and _slD > 0) ? f_distPrice(beOffEff) : "0")
```

Die zes worden **berekend** uit `useTrail` en `useBreakEven` — twee inputs die per script
aan of uit kunnen. In hun steekproef stonden ze uit, en de getoonde regel was bovendien een
`close`, waar breakeven per definitie 0 is.

⚠️ **Waarom dit niet als constante mag: dat is exact de faalmodus van D-44.** Dat item heette
*"de BE-offset bereikt de broker nooit"* en is net dichtgezet. Zet de middleware deze zes
hard op 0, dan stopt de dag dat Ferry trailing of break-even aanzet die instelling
stilzwijgend bij de middleware — en niemand ziet het, want de order gaat gewoon door.

**Besluit: het event krijgt een `risk`-object** dat deze zes draagt. Ze horen bij de
strategie, net als `dollar_sl`, en niet bij de configuratie.

**De andere zes zijn wél literalen** in de Pine-bron — `tp` · `percentage_tp` · `sl` ·
`percentage_sl` · `update_tp` · `update_sl` (plus `risk_percentage`). Die zet de middleware
als PMT-formaatconstanten, met het codecommentaar dat zij voorstelden. Geen `pmt_defaults`
in de configuratie: dat suggereert dat het instellingen zijn.

### Punt 2 — de Discord-kleur: `text.color`, niet een tabel in de middleware

Zij vroegen of de middleware de kleur uit `kind`+`action` mag afleiden via een tabel van
~8 paren, met als argument dat `CardTier` dat al doet voor de tier. Redelijk, maar
**ik kies (b): `text.color` als optioneel veld in het event.**

Reden: route B trekt de grens bij *Pine bepaalt hoe de kaart eruitziet, de middleware
bepaalt waar hij heen gaat*. Een kleurtabel zet de helft van het uiterlijk aan de andere
kant van die grens. En het faalgedrag verschilt: komt er een nieuw kaarttype in Pine, dan
valt een tabel stil terug op een standaardkleur — terwijl een meegestuurd veld vanzelf
meekomt. Bij 29 `f_sendDiscord`-aanroepen per script is die stille drift een kwestie van
tijd.

Hun observatie dat `CardTier.For(title)` naar **`CardTier.For(kind, action)`** moet
migreren is wél overgenomen: de tier hoort bij de routing, de kleur bij de kaart.

### Punt 3 — de Notion-database-id hoort in D-78

Klopt, en goed dat ze het meldden uit deze audit in plaats van het te laten liggen. Die
komt vandaag uit `NOTION_JOURNAL_DB`. Toegevoegd aan `schema-config.md` §4.

---

## 4. Wat de middleware eruit bouwt

| Uitgaand | Uit het event | Uit de configuratie (D-78) |
|---|---|---|
| **PMT-JSON** | `symbol` · `ts` · `action` · `qty` · `price` · `dollar_sl` · `dollar_tp` · `order_type` · **`risk.*`** | `token` · `account_id` · `pyramid` · `reverse_order_close` · Tradovate of Rithmic. Plus zeven **formaatconstanten** die de middleware zelf zet: `tp` · `percentage_tp` · `sl` · `percentage_sl` · `update_tp` · `update_sl` · `risk_percentage` |
| **PineConnector** | `action` · `price` ± `dollar_sl`/`dollar_tp` | `license` · symboolvertaling · `risk` |
| **Discord** | `text.title` · `text.body` · `text.color` · `kind` · `action` | webhook per account/kanaal · wel of geen kaart. De **tier** komt uit `CardTier.For(kind, action)` — gemigreerd van `For(title)` |
| **Journaal** | `journal.*` | opslagpad |
| **Notion** (D-94) | `journal.*` | database-id |

⚠️ **De qty-override (D-53) verhuist mee.** Vandaag overschrijft de receiver
`multiple_accounts[0].quantity` in een payload die Pine al gebouwd heeft. Straks bouwt de
middleware die payload zelf en is de override gewoon *"welke qty schrijf ik op"*. Het gedrag
blijft gelijk, de plek wordt logischer. **De volgorde blijft dwingend: eerst de poorten, dan
de qty** — anders dragen geweigerde regels in `routed_*.jsonl` een bewerkte hoeveelheid, en
dat was precies de D-70-bevinding.

---

## 5. Wat er NIET in het event hoort

- `secret` — dat blijft de URL (`/signal/{token}`). Eén authenticatiemechanisme, niet twee.
- `account_id`, `pmtToken`, `pcLicense`, `pcSymbol`, `pcRisk` — configuratie.
- Welke kanalen aan staan — configuratie. **Dat is de hele kern van fase 3.**
- Berekende accountstanden (balans, ruimte, payoutvoortgang). Die komen uit T3 (D-92) en de
  registry, niet uit een simulatie in Pine. Het `journal`-object draagt wel `balance` en de
  twee afstanden, maar **als Pine's eigen kijk** — zo moeten ze ook gelabeld worden, anders
  komt er een tweede saldobron naast T3.

---

## 6. Acceptatiecriteria

1. ✅ **Pine Dev heeft getoetst** (28-09) en drie blokkades plus vijf voorwaarden gemeld.
   Alle acht zijn in §3b afgehandeld. **Resteert één bevestiging van hen:** klopt het dat
   blokkade 1 vanzelf oplost doordat de drie `alert()`-aanroepen in fase 3 samensmelten?
2. ✅ **Middleware App heeft getoetst** (28-09) tegen echt verkeer op alle vier de routes en
   antwoordde **ja**, met drie punten. Alle drie afgehandeld in §3c — op punt 1 wijk ik van
   hun voorstel af, met een meting erbij.
3. ✅ Het besluit uit §3 is genomen: **route B** (Ferry, 28-09).
4. Er ligt één voorbeeldbericht per `kind`.

✅ **Alle vier afgerond op 29-09; D-77 staat op `done`.** Fase 1 was al begonnen omdat D-78
als eerste dichtging — dat kon, want de config-store leunt op dat schema en niet op dit. Schuift dit schema later alsnog, dan moet fase 1 opnieuw — dat is
de reden dat het hier staat en niet halverwege.
