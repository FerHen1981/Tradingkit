# D-77 · Het canonieke event — schema v1

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
`MEX_EL_MATADOR_MES_PROD_EOD_v1_0_0.pine` heeft een **zesde routetoggle** naast de vijf die
we kenden:

```pine
useMiddleware = routeMiddleware                                          // r. 972
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
  "id": "MAT-MES-P:1727539200000:entry",
  "ts": "2026-09-28T14:30:00Z",
  "strategy": "MAT-MES-P",
  "symbol": "MES1!",
  "kind": "entry",
  "action": "buy",
  "qty": 6,
  "price": 5321.25,
  "order_type": "MKT",
  "dollar_sl": 150,
  "dollar_tp": 300,
  "text": { "title": "📈 MES1! LONG MARKET", "body": "…" },
  "journal": { "event": "ENTRY", "dir": "long", "status": "…", "entry": 5321.25,
               "stop": 5296.25, "target": 5371.25, "qty": 6, "pnl": null,
               "regime": "FAVORABLE", "balance": null, "dist_target": null, "dist_fail": null }
}
```

| Veld | Verplicht | Waarom het zo is |
|---|---|---|
| `v` | ja | Schemaversie. Zonder dit kan de middleware oude en nieuwe berichten niet uit elkaar houden tijdens de schaduwdraai van D-88. |
| `id` | ja | **Idempotentiesleutel.** De receiver ontdubbelt vandaag op een SHA-256 van de hele body binnen 5 seconden. Dat faalt twee kanten op: twee identieke signalen op verschillende bars binnen 5 s worden onterecht als duplicaat weggegooid, en een retry ná 5 s wordt onterecht dubbel uitgevoerd. Een expliciete sleutel lost beide op. |
| `ts` | ja | UTC, ISO-8601. De sessie-roll van 18:00 ET wordt in de middleware berekend, niet in Pine. |
| `strategy` | ja | De shorttitle. **Dit is de sleutel waarop de configuratie accounts opzoekt** — `mwStrategy` doet dat al. |
| `symbol` | ja | `syminfo.ticker`. De PineConnector-symboolvertaling (`pcSymbol`) is **configuratie**, geen event-veld. |
| `kind` | ja | `entry` · `exit` · `halt` · `derisk` · `payout` · `config` · `info`. Bepaalt welke kanalen überhaupt in aanmerking komen. |
| `action` | bij entry/exit | `buy` · `sell` · `close`. |
| `qty` | bij entry/exit | Contracten zoals de strategie ze bedoelt. ⚠️ De **qty-override** (D-53) grijpt hierná in, in de middleware — zie §4. |
| `price` | bij entry/exit | Signaalprijs. Bij een limietorder de limietprijs. |
| `order_type` | bij entry/exit | `MKT` · `LMT`. |
| `dollar_sl` / `dollar_tp` | bij entry | **Afstanden, geen niveaus.** Pine rekent vandaag al zo en PineConnector reconstrueert de absolute prijzen eruit (`price ± afstand`). Houd dat zo; niveaus zouden bij een limietorder meerdere waarheden hebben. |
| `text` | ja | Zie §3. |
| `journal` | ja | De zestien kolommen van de huidige journaalregel, als velden in plaats van als kommastring. |

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

## 4. Wat de middleware eruit bouwt

| Uitgaand | Uit het event | Uit de configuratie (D-78) |
|---|---|---|
| **PMT-JSON** | `symbol` · `ts` · `action` · `qty` · `price` · `dollar_sl` · `dollar_tp` · `order_type` | `token` · `account_id` · trail-instellingen · breakeven · `pyramid` · `reverse_order_close` · Tradovate of Rithmic |
| **PineConnector** | `action` · `price` ± `dollar_sl`/`dollar_tp` | `license` · symboolvertaling · `risk` |
| **Discord** | `text.title` · `text.body` · `kind` | webhook per account/kanaal · tier · wel of geen kaart |
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

1. **Pine Dev bevestigt** dat elk verplicht veld uit een script te produceren is, en meldt
   welke niet.
2. **Middleware App bevestigt** dat elke huidige uitgaande payload hieruit te bouwen is —
   getoetst op een echt bericht per route, niet op papier.
3. ✅ Het besluit uit §3 is genomen: **route B** (Ferry, 28-09).
4. Er ligt één voorbeeldbericht per `kind`.

Pas daarna begint fase 1. Schuift dit schema later alsnog, dan moet fase 1 opnieuw — dat is
de reden dat het hier staat en niet halverwege.
