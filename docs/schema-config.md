# D-78 · De configuratie — schema v1

_Eigenaar: Scrum Master. Opgesteld 28-09-2026. Fase 0 van `docs/PLAN-2026-09-27-herijking.md`._
_Review gevraagd aan **Middleware App**. Dit is de bron die de settings-tab (fase 2) beheert_
_en die de receiver herleest zonder herstart (fase 1)._

> **Wat dit is.** Alles wat vandaag als environment-variabele op de VPS staat of als
> chart-input in TradingView, komt hierheen. Ferry (antwoord 4): *"de instellingen voor
> kanalen, tokens en weburls wil ik volledig inzichtelijk en beheersbaar hebben in een
> settings tab in de webapp."*

---

## 0. Twee vondsten die het schema bepalen

**🔴 De middleware raadt vandaag firma en fase uit de accountnáám.** `NotifyRoute` in de
live receiver:

```csharp
if (a.StartsWith("PA"))   return "FUNDED";
if (a.StartsWith("APEX")) return "EVAL";
if (a.Contains("APEX"))   return "APEX";
if (a.Contains("FTMO"))   return "FTMO";
```

Dat werkt vandaag **bij toeval**, omdat elk account `PAAPEX27002500000xx` heet. Het gaat stuk
zodra Blue Guardian, Top One of TradeDay erbij komen met een andere naamgeving, en het kan
nu al geen onderscheid maken tussen Apex Legacy 50K, Legacy 250K en Intraday 50K — terwijl
die **andere regels** hebben (het consistency-percentage is 30% respectievelijk 50%, op
28-09 geverifieerd). ➡️ **Firma, programma en fase worden expliciete velden. Nooit meer een
gok op een naam.**

**🔴 Alle instellingen worden gelezen in een static constructor.** `AccountQty`,
`AccountBlockGate` en `AccountRiskGate` lezen hun env-variabelen één keer, bij procesnstart.
Daarom kan een wijziging vandaag niet zonder herstart. Dat is wat D-79 oplost.

---

## 1. Vorm

Eén bestand, JSON, met een schema ernaast zoals `data/propfirms.json` dat ook heeft.
Atomair geschreven (tmp + rename), zodat de receiver nooit een half bestand leest.

```json
{
  "version": 7,
  "updated": "2026-09-28T14:30:00Z",
  "updated_by": "settings-tab",
  "channels": { … },
  "accounts": { … },
  "defaults": { … }
}
```

`version` telt bij elke schrijfactie op. De receiver logt welke versie hij geladen heeft;
daarmee is achteraf te zien onder welke configuratie een order de deur uit ging. Dat is de
enige manier om een verkeerde order te reconstrueren.

---

## 2. Niveau 1 — `channels`: kanaal, token en herkomst

Ferry (antwoord 9): *"welke propfirm, welk token en welk kanaal."*

```json
"channels": {
  "apex_50k_legacy_pa": {
    "firm": "Apex",
    "program": "apex_50k_legacy_pa",
    "transport": "pmt_tradovate",
    "url_ref": "pmt_tradovate",
    "token_ref": "apex_pmt",
    "discord_webhook_ref": "discord_funded"
  },
  "blueguardian_50k_funded": {
    "firm": "Blue Guardian",
    "program": "blueguardian_50k_funded",
    "transport": "pmt_tradovate",
    "…": "…"
  }
}
```

| Veld | Toelichting |
|---|---|
| `program` | **Verwijst naar een sleutel in `data/propfirms.json`.** Geen tweede firmalijst — dat is de §5-regel van de skill. Ontbreekt de sleutel daar, dan is de configuratie ongeldig en laadt hij niet (D-80). Dit is de koppeling met **D-104**. |
| `transport` | `pmt_tradovate` · `pmt_rithmic` · `pineconnector`. Bepaalt welke payload de middleware bouwt. Vandaag wordt Rithmic gekozen op een kommalijst van account-id's (`MEX_PMT_RITHMIC_ACCOUNTS`) omdat *"PMT-Tradovate en PMT-Rithmic een IDENTIEKE payload sturen"* — die lijst verdwijnt hierin. |
| `*_ref` | ⚠️ **Verwijzingen, geen waarden.** Zie §5. |

---

## 3. Niveau 2 — `accounts`

Ferry (antwoord 9): *"per account hard caps (zoals ik nu in Tradovate zet), wel of niet
publiceren toggle, status van een account instelbaar, een Discord webhook per kanaal."*

```json
"accounts": {
  "PAAPEX2700250000013": {
    "channel": "apex_50k_legacy_pa",
    "strategy": "MAT-MES-P",
    "broker_account_id": "PAAPEX2700250000013",
    "status": "active",
    "caps": { "daily_loss": 1200, "entries_per_day": 8 },
    "publish": true,
    "verified_amount": null,
    "verified_at": null,
    "discord_webhook_ref": null,
    "payouts": [ { "date": "2026-09-10", "amount": 1500, "nr": 1 } ]
  }
}
```

| Veld | Toelichting |
|---|---|
| `channel` | Wijst naar niveau 1. Daarmee liggen firma, programma, transport en token vast. |
| `strategy` | De shorttitle uit het event (D-77). **Hier wordt `strategy → accounts` bepaald** — de fan-out. Vandaag deed `mwStrategy` dat via `accounts.yaml`, en dat bestand is met de Python-route verdwenen. |
| `status` | `active` · `halted` · `blocked` · `archived`. Vervangt `MEX_HALTED_ACCOUNTS`. |
| `caps` | Vervangt `MEX_ACCOUNT_ENTRY_CAPS` en `MEX_DEFAULT_ENTRY_CAP`. ⚠️ Ferry zet deze nu **in Tradovate**; dit is dus een tweede plek. Zie §6. |
| `publish` | De poort van D-74: mag dit account op de site en in de widget. |
| `verified_amount` / `verified_at` | Per account, optioneel, default `null`. Vervangt de vloot-brede `FUNDED_VERIFIED_*`-vlag (§3b). Zonder deze twee mag een funded saldo niet als geverifieerd gepubliceerd worden — zie D-93. |
| `payouts` | 🔴 **Nieuw en niet weg te laten.** Een payout verlaagt de balans maar staat **niet in de fills**, dus zonder deze lijst krijgt T3 (D-92) de balans nooit sluitend. Gemeten op PA013: fills gaven $1.903 minder dan de brokerbalans, waarvan $1.500 exact de op 10-09 ontvangen payout was. Stand 28-09: dit is de **enige** payout in de hele vloot (bevestigd door Ferry). |

⛔ **Geen `contracts`-veld.** Ferry (antwoord 9): *"aantal contracten zit in het advies en
beheer ik in pine."* De qty-override (D-53) blijft bestaan als **vangnet** onder een andere
sleutel, maar krijgt geen veld in de settings-tab — anders ontstaan er twee plekken die het
aantal contracten bepalen en weet niemand meer welke wint.

---

## 3b. ✅ Review Middleware App verwerkt — drie toevoegingen

Zij auditeerden **alle 19 `MEX_*`-vars uit `Program.cs` plus 25 Python-app-envs** tegen §3 en
§7 en bevestigden dat de acht uit de migratietabel letterlijk kloppen. Drie categorieën vielen
er nog buiten; alle drie overgenomen:

1. ✅ **`FUNDED_VERIFIED_AT` + `FUNDED_VERIFIED_WINDOW`** staan vandaag als **één vlag voor de
   hele funded-stack** (de noodgreep uit D-74), terwijl tabel 2 van `execution-flow.md`
   per-account `verified_amount` + `verified_at` voorschrijft. **Overgenomen als twee
   optionele velden op `accounts[]`, default `null`.** Daarmee valt D-93 hier vanzelf op zijn
   plek en verdwijnt de vloot-brede vlag bij de migratie. Goede vangst — dit was een stille
   generalisatie die niemand had opgemerkt.
2. ✅ **`WIDGET_GOAL`** → `defaults` (§4).
3. ✅ **`MEX_SIGNAL_JSON` en `MEX_SIGNAL_OUT`** vallen inderdaad onder *renderpaden* in §6 —
   bevestigd, machine-eigenschappen en geen vloot-instelling.

⏸️ **`PMT_MATCH_WINDOW_S`** (900 s in `routed_journal.py`) laten we bewust staan. Hun
redenering klopt: dat is reconciliatie-tuning die bij het bevestigingsvenster van fase 4 hoort,
en nu in `defaults` zetten is te vroeg. Komt terug bij **D-91**.

---

## 4. `defaults`

Wat vandaag globale env-variabelen zijn en per installatie geldt: de Discord-kaart-tier,
het rendermaximum per minuut, de standaard entry-cap. **Niet** `MEX_DRY_RUN` en **niet**
de kill-switch — zie §6.

---

## 5. 🔴 Geheimen: verwijzingen in de config, waarden in een aparte kluis

Ferry wil tokens in de settings-tab kunnen beheren. Dat mag niet betekenen dat de tokens
zelf in het configbestand terechtkomen dat de webapp leest en dat in een auditspoor
belandt.

**Daarom:** `token_ref` en `url_ref` zijn **namen**. De waarden staan in een apart bestand
met strakke rechten, dat alleen de receiver leest en dat de settings-tab **schrijft maar
nooit teruggeeft**. Het scherm toont `apex_pmt · ✓ gezet · laatst gewijzigd 12-09` en een
veld om te vervangen — nooit de waarde zelf.

Drie regels die daaruit volgen en die in D-81 en D-82 moeten zitten:
1. Het **auditspoor logt de naam en het feit dat er iets wijzigde, nooit de waarde.** Dat is
   dezelfde regel als in `runtime-snapshot.md`, dat bewust alleen env-**namen** draagt.
2. Beide bestanden staan in `.gitignore`. Nooit committen — de bestaande regel geldt hier
   onverkort.
3. Roteren wordt hiermee een handeling in het scherm. **Dat verandert D-11 van karakter**,
   met één uitzondering: `MEX_WEBHOOK_SECRET` **is de alert-URL** (`/signal/{token}`), dus
   dat roteren breekt alle dertien TradingView-alerts tot ze opnieuw gezet zijn. Dat hoort
   daarom bij fase 3, wanneer de alerts toch allemaal aangeraakt worden.

---

## 6. Wat NIET naar de config gaat, en waarom

| Blijft env / apart | Reden |
|---|---|
| `MEX_DRY_RUN` | Een noodrem die je wilt kunnen omzetten zonder dat een fout in de webapp hem kan omzetten. |
| De kill-switch (`/killswitch`) | Zelfde reden. Hij heeft al een eigen endpoint; laat dat zo. |
| `MEX_WEBHOOK_SECRET` | Dit is de URL, niet een instelling. |
| `MEX_FORCE_IPV4`, renderpaden, `MEX_NODE` | Eigenschappen van de machine, niet van de vloot. |

⚠️ **`caps` is een tweede plek en dat moet zichtbaar blijven.** Ferry zet zijn harde caps
vandaag in Tradovate; die zijn bindend want de broker handhaaft ze. Wat hier staat is de
grens die de **middleware** bewaakt. Twee plekken die hetzelfde bedoelen is precies wat §5
van de skill verbiedt — maar hier kan het niet anders, want wij kunnen Tradovate niet
uitlezen. **Eis aan de settings-tab: toon deze waarde expliciet als *"wat de middleware
bewaakt"* en zet erbij dat Tradovate zijn eigen limiet kent.** Een stille afwijking tussen
die twee is erger dan twee zichtbare getallen.

---

## 7. Migratie uit de huidige env-variabelen

| Vandaag | Straks |
|---|---|
| `MEX_ACCOUNT_QTY` | blijft env — vangnet, geen settings-veld (§3) |
| `MEX_HALTED_ACCOUNTS` | `accounts[].status = "halted"` |
| `MEX_ACCOUNT_ENTRY_CAPS` · `MEX_DEFAULT_ENTRY_CAP` | `accounts[].caps` · `defaults.caps` |
| `MEX_PMT_RITHMIC_ACCOUNTS` | `channels[].transport = "pmt_rithmic"` |
| `MEX_PMT_URL` · `MEX_PMT_RITHMIC_URL` · `MEX_PC_URL` | de kluis, via `url_ref` |
| `MEX_DISCORD_WEBHOOK` + de `NotifyRoute`-varianten | `discord_webhook_ref` per kanaal en per account |
| `MEX_CARD_TIER_OVERRIDES` · `MEX_CARD_MAX_PER_MINUTE` | `defaults` |

D-81 zet dit eenmalig om en laat daarna een startwaarschuwing zien als iemand een oude
variabele nog gezet heeft — dezelfde aanpak die Middleware App bij `MEX_ACCOUNT_QTY` al
gebruikte.

---

## 8. Acceptatiecriteria

1. ✅ **Middleware App heeft geauditeerd** (28-09): 19 `MEX_*`-vars plus 25 Python-envs
   getoetst, de acht uit §7 kloppen letterlijk, drie gaten gemeld en alle drie overgenomen
   (§3b). **Akkoord zonder blokkers.**
2. Elk `program` resolvet naar een bestaande sleutel in `data/propfirms.json` — dus **D-104
   moet af zijn** voordat de configuratie voor alle acht firma's geldig kan zijn.
3. Er ligt één voorbeeldconfiguratie die de huidige vloot exact beschrijft, en het gedrag
   daaronder is aantoonbaar gelijk aan vandaag.
4. Geen enkele waarde uit de kluis komt voor in het configbestand of in het auditspoor.
