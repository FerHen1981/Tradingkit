# Discord trade-notificaties — handoff

> Plak dit als openingsbericht in een nieuwe chat om de Discord/Notify-thread
> apart verder te ontwikkelen. Repo: `ferhen1981/tradingkit`, branch
> **`claude/middleware-setup-guide-afhvtk`**.
>
> Scope: de **Notify-channel** van de middleware — live Discord-berichten per
> trade + failure-alerts. Dit is een dun maar zelfstandig onderdeel; deze chat is
> de plek om het uit te bouwen (rijkere embeds, per-kanaal routing, P&L, charts).

## 1. Wat het nu is
De middleware stuurt na elke fan-out een **live bericht naar Discord** en pingt bij
een mislukte dispatch. Het is een aparte channel náást Execution (Tradovate/MT5) en
Journal (sqlite/Notion): één Pine-signaal → middleware → **Notify + Execution + Journal**.

## 2. Waar het zit (technisch)
- **`middleware/app/notify.py`** (~48 regels), twee functies:
  - `notify_trade(webhook, sig, results)` — **live per-trade** notificatie.
  - `alert_failure(webhook, text)` — **failure-ping** (broken order blijft niet stil).
  - Beide via `_post(...)`, die JSON `{"content": ..., "text": ...}` post — Discord
    leest `content`, Telegram leest `text`, dus **één helper werkt voor beide**.
  - **Best-effort:** vangt alle excepties; notificaties mogen het request-pad
    nooit breken.
- **`format_trade(sig, results)`** bouwt de one-liner, bv:
  `🟢 **ES_Rey BUY** ES @ 5312.25 · 2ct · SL 400/TP 800  → 6 account(s), 1 blocked`
  (emoji + strategie·actie·symbool·prijs·qty·SL/TP + tellingen ok/blocked/failed).
- **Aangeroepen** vanuit `middleware/app/main.py:112`, ná de fan-out:
  `notify_trade(accounts.notify_for(sig.strategy) or settings.notify_webhook, sig, results)`.

## 3. Configuratie
| Env / veld | Waar | Betekenis |
|---|---|---|
| `NOTIFY_WEBHOOK` | `config.py:42` (`settings.notify_webhook`) | Globale Discord-webhook voor **elke** trade (live). |
| `ALERT_WEBHOOK` | `config.py:41` (`settings.alert_webhook`) | Discord/Telegram-webhook voor **failures**. |
| `strategies.<naam>.notify` | `accounts.yaml` → `notify_for(strategy)` (`config.py:80`) | **Per-strategie** webhook-override; valt terug op de globale. |

> Secrets (webhook-URLs) staan in `.env` / `accounts.yaml` — **git-ignored**, nooit
> committen.

## 4. Stand van zaken
- Functioneel: plain-text `content`, per-strategie routing werkt, failure-alerts werken.
- Bewust minimaal — nog **geen rich embeds, geen kleuren, geen P&L-op-close, geen
  charts, geen aparte funded/eval-kanalen**.

## 5. Open taken / next (waarom dit een eigen thread verdient)
1. **Rich embeds** i.p.v. platte `content`: kleur per win/loss, velden per account,
   thumbnail — Discord-embed-JSON in `_post`/`format_trade`.
2. **Per-kanaal routing** — aparte webhooks voor Funded vs Eval (of per firm), zodat
   de streams gescheiden zijn.
3. **P&L op close** — bij een exit het gerealiseerde resultaat + lopende dag-tally
   meesturen (koppelt aan `routed_journal` / `cash_ledger`).
4. **Chart-snapshot** meesturen bij entry/exit (image-attachment).
5. **Failure-severity** — duidelijker onderscheid/ernst in het alert-kanaal, evt.
   rate-limit/batching bij bursts.
6. **Telegram-pariteit** afmaken (de `_post`-helper stuurt al beide keys — alleen
   nog een kanaal/config-pad).

## 6. Werkafspraken
- Ontwikkelen/committen/pushen op **`claude/middleware-setup-guide-afhvtk`**.
- Draait mee in de middleware (`mex-middleware`/receiver) — geen aparte service.
- Notificaties blijven **best-effort**: nooit het order-pad laten breken.
- Test zonder echt te posten via DRY_RUN + een test-webhook.
