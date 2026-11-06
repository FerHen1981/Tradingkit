# Trade Journal-pipeline — live uit het routed-log

Doel: **trades verschijnen in het Notion Trade Journal zodra ze er zijn** — puur uit data die
de server zelf al genereert. Geen browser, geen Tradovate-login, geen CSV nodig voor het live
beeld.

---

## De doorbraak: alles staat al in `routed_*.jsonl`

De executor schrijft `/root/intent-store/routed_YYYYMMDD.jsonl`. Dat log bevat de **complete
trade per account** in zijn Discord-kaarten:

| Kaart | Voorbeeld | Levert |
|---|---|---|
| 📥 **FILL** | `PA015-0k-260813 \| 5ct @ 4403.1 \| SL 4413.1 \| TP 4378.1` | account, aantal, **echte instapprijs**, SL, TP |
| 📤 **EXIT** | `PA015 \| short closed @ 4397.7 \| TRAIL \| PnL +$263.3 \| MFE 79t · MAE 3t` | **echte uitstapprijs, reden, P&L, MFE/MAE** |
| 📈 **LIMIT** | `Entry 4449.8 \| Stop 4439.8 \| TP 4474.8 \| Qty 8` | bedoelde prijs → **slippage** |
| `pmt` record | `account: APEX27002500000209` | volledige account-id (kort `AP209` → vol) |

De accounts komen dus óók uit dit log — nieuwe accounts verschijnen vanzelf, weggevallen
accounts verdwijnen vanzelf. **Fleet-churn lost zichzelf op.**

---

## Architectuur — twee lagen

```
Laag 1 — LIVE (elke minuut, server-side, kan niet stuk door een UI-wijziging)
  routed_*.jsonl ─▶ [routed_journal] parse FILL/EXIT/LIMIT
                     pair FILL↔EXIT per (account, symbool, richting)
                     resolve account (kort→vol) · framework (instrument+fase)
                  ─▶ Notion Trade Journal upsert (rij opent bij FILL, sluit bij EXIT)
       via systemd-timer  mex-routed-journal.timer  (OnUnitActiveSec=1min)

Laag 2 — RECONCILIATIE (optioneel, 1×/dag) — alleen als extra controle / commissies
  Fills-CSV ─▶ [fills_pairing] ─▶ match op de bestaande live-rij ─▶ echte commissie/controle
       download = scraper/ (draait op een ingelogde pc), NIET in het live-pad
```

### Huidige stand

| Stuk | Status | Waar |
|---|---|---|
| Signalen → intent-store + routed-log | ✅ live | `mex-receiver.service` → `/root/intent-store/` |
| routed-log → completed trades (parse + pair) | ✅ **gebouwd + getest** | `app/routed_journal.py` |
| completed trade → Notion-rij (mapping) | ✅ gebouwd (956/956 gevalideerd) | `app/notion_journal.py` |
| live timer (elke minuut) | ✅ klaar om te deployen | `deploy/mex-routed-journal.{service,timer}` |
| fills-CSV verwerking (reconciliatie) | ✅ gebouwd (optioneel) | `app/journal_sync.py`, `scraper/` |

---

## Wat een rij in Notion krijgt

- **Bij FILL (open):** richting, contract, instapprijs, aantal, SL/TP, framework, status `Open`.
- **Bij EXIT (dicht):** uitstapprijs, **gerealiseerde P&L**, reden (TRAIL/SL/TP), MFE/MAE, status
  `Closed`. Idempotent op een entry-gebaseerde `Webhook ID`, dus de rij die opende wordt
  bijgewerkt — nooit een dubbele.
- **Slippage:** instap-fill vs de bedoelde LIMIT-prijs → `Slippage Entry (ticks)`.

---

## Deploy (op mex-mw-01)

```bash
cd /root/mex-journal/middleware
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # eenmalig
# .env:  NOTION_TOKEN=...  NOTION_JOURNAL_DB=1ddb61ea444d813294f8e4eac39809e4  ROUTED_DIR=/root/intent-store

# eerst DRY (zonder token in de omgeving) — laat zien wat het ZOU schrijven:
ROUTED_DIR=/root/intent-store .venv/bin/python -m app.routed_journal

# daarna live op een timer van 1 minuut:
sudo cp deploy/mex-routed-journal.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now mex-routed-journal.timer
```

Elke run logt zijn uitkomst (`files/events/trades/new/updated/skipped`) — geen
"ik-wist-het-niet": je ziet precies wat er verwerkt is.

---

## Openstaand / later

- **Commissies & harde P&L-controle:** laag 2 (fills-CSV) 1×/dag om commissie in te vullen en
  de executor-P&L te verifiëren tegen de broker.
- **Framework-exactheid:** de El___-namen worden afgeleid uit instrument + account-fase; als de
  strategie de scriptnaam in het signaal meestuurt, kunnen we die 1-op-1 overnemen.
- **Status-opties in Notion:** `Open` / `Closed` / `Closed (SL)` worden automatisch aangemaakt
  bij de eerste write.
