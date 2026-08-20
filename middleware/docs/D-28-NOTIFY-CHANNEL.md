# D-28 · Notify-kanaal — status van de zes uitbreidingen

> **Status per uitbreiding**, met bewijs. Legacy eigenaar voor de .NET-kant,
> Middleware App eigenaar voor de config-tabel en de routing-lookup.
>
> Bron van de zes: `middleware/docs/DISCORD_NOTIFY_HANDOFF.md`, §5, commit
> `5d08fa1` (17-aug-2026).

## Waar de notificaties nu vandaan komen

Live-pad = **`mex-receiver` (.NET)** met `renderEnabled:true` en
`renderScript:/root/mex-renderer/render-signal.js`. De oude Python `notify.py`
staat als DEAD PATH gemarkeerd (D-05). Deze doc gaat over uitbreidingen op de
draaiende .NET-kant.

## De zes uitbreidingen

| # | Uitbreiding | Status | Bewijs / plan |
|---|---|---|---|
| 1 | **Rich embeds** — kleur per win/loss, velden per account, thumbnail | ✅ **live** | `routed_*.jsonl` toont embeds met title/description en kleur-emoji: `📥 MGC1! FILL SHORT` (entry) en `📤 MGC1! EXIT 🟢/🔴` (exit) worden door `routed_journal.parse_routed_lines()` uit de Discord-embeds gehaald |
| 2 | **Per-kanaal routing** — funded/eval/per-firm gescheiden | ⚙️ **klaar in config, wacht op .NET** | `app/notify_routing.py` legt de env-vars en de prioriteit vast; de .NET-receiver kan dezelfde vars lezen (zie *Env* hieronder). Legacy: één lookup in de renderer op `firm/phase` → webhook — dan is dit klaar |
| 3 | **P&L op close** — realized $ + MFE/MAE bij exit | ✅ **live** | exit-cards dragen `PnL +$263.3 \| MFE 79t · MAE 3t` (zie `routed_journal._PNL/_MFE/_MAE`); dag-tally staat nog niet in de kaart maar wel op het dashboard |
| 4 | **Chart-snapshot** bij entry/exit | ⚙️ **haak bestaat, capture ontbreekt** | zie D-22 (`chartUrl` bestaat in de renderer; Playwright-capture nog te bouwen). Aparte D-nummer — niet dubbelen |
| 5 | **Failure-severity** — tiering + rate-limit/batching | ⚙️ **tiering ja, rate-limit nee** | log toont `card queued (tier B)` → tier B wordt onderscheiden. Rate-limit/batching bij bursts ontbreekt nog — Legacy |
| 6 | **Telegram-pariteit** — kanaal naast Discord | ⚙️ **routing klaar, kanaal ontbreekt** | `app/notify_routing.py` kent `TELEGRAM_*_WEBHOOK` en valt terug op de Discord-vars (want de `_post`-helper stuurde altijd al `{content, text}` — één webhook kan beide bedienen). Ontbreekt: een Telegram-endpoint dat de tekst afvangt. Legacy |

**Score:** 2 volledig live (1, 3), 4 klaar of half (2, 4, 5, 6). "De helft zit in
de receiver" uit de bord-tekst klopt.

## Wat Middleware App levert (deze commit)

- **`middleware/app/notify_routing.py`** — pure lookup:
  `webhook_for(account, kind, channel)` → webhook-URL. Prioriteit: per-firm >
  per-fase > globaal. Failure-alerts gaan naar hun eigen `ALERT_WEBHOOK`.
  Retourneert een lege string als niets geconfigureerd is (nooit `None`).
- **`middleware/app/notify_routing.describe(account)`** — debug-lookup die
  vertelt welke env-var *gekozen zou zijn*, zonder de URL zelf terug te geven
  (die is een secret; zie D-11).
- **10 tests** die borgen dat `describe()` en `webhook_for()` in sync blijven —
  elke kandidaat die `describe()` noemt moet ook door de echte routing gekozen
  worden als hij als enige gezet is. Anders lopen debug en runtime uit de pas.

De module is **niet dead-path**: hij doet zelf geen HTTP, dus hij hangt niet aan
de Python fan-out. De reconcile-runner en `journal_sync` kunnen hem gebruiken
voor hun eigen failure-alerts, en de .NET-receiver kan dezelfde env-var-tabel
lezen zonder een tweede routing te dragen.

## Env-tabel (nieuw)

Voeg toe aan `middleware/.env`:

```ini
# Trades — globale fallback (bestaat al)
NOTIFY_WEBHOOK=https://discord.com/api/webhooks/…globale…

# Trades — per fase (nieuw). Winnen van de globale.
NOTIFY_WEBHOOK_FUNDED=https://discord.com/api/webhooks/…funded…
NOTIFY_WEBHOOK_EVAL=https://discord.com/api/webhooks/…eval…

# Trades — per firm (nieuw). Winnen van fase én globaal.
NOTIFY_WEBHOOK_APEX=https://discord.com/api/webhooks/…apex…
# NOTIFY_WEBHOOK_FTMO=… (als FTMO in beeld komt)

# Failures — apart kanaal (bestaat al)
ALERT_WEBHOOK=https://discord.com/api/webhooks/…errors…

# Rate-limit op kaarten (nieuw). Discord staat 30/min/webhook toe.
# MEX_CARD_MAX_PER_MINUTE=12

# Telegram-pariteit (nieuw). Wordt gebruikt als je Telegram-kanaal aan wilt zetten;
# ontbrekend = val terug op de Discord-vars (want _post stuurt {content, text}).
# TELEGRAM_NOTIFY_WEBHOOK=…
# TELEGRAM_NOTIFY_WEBHOOK_FUNDED=…
# TELEGRAM_ALERT_WEBHOOK=…
```

## Legacy-deel opgeleverd (20-08, `c8216ac` op de legacy-branch)

Alle drie de hooks zitten in `middleware/dotnet-receiver/Program.cs`:

| # | Klasse | Gedrag |
|---|---|---|
| 2 | `NotifyRoute` | `WebhookFor(account, kind, channel)` — spiegelt `app/notify_routing.py` regel voor regel. Account komt uit het eerste pipe-deel van de embed-description. Niets gezet ⇒ lege string ⇒ `MEX_DISCORD_WEBHOOK` blijft het doel |
| 5 | `PostRate` | Teller per webhook per minuut (`MEX_CARD_MAX_PER_MINUTE`, default 12). Boven de grens: geen kaart, wel `card rate-limited` in het journaal; de eerstvolgende kaart meldt `(+N gedempt)`. **Tier A gaat altijd door** |
| 6 | — | Telegram krijgt dezelfde body zodra `TELEGRAM_NOTIFY_WEBHOOK*` gezet is. Bewust **ná** de blocked-poort: wat Discord niet mag halen, mag Telegram ook niet halen |

⚠️ **Niet gecompileerd.** Geen dotnet in de sessie, en de receiver is niet uit git te
bouwen (D-06). `dotnet build src/Mex.Journal.Receiver -c Release` op de VPS is de eerste
echte controle.

### De twee kanten synchroon houden

`NotifyRoute` en `notify_routing.py` moeten dezelfde kandidaten in dezelfde volgorde
opleveren. Verandert er één, verander dan beide:

```
trade   · discord   NOTIFY_WEBHOOK_<FIRM> → NOTIFY_WEBHOOK_<PHASE> → NOTIFY_WEBHOOK
trade   · telegram  TELEGRAM_NOTIFY_WEBHOOK_<FIRM> → …_<PHASE> → TELEGRAM_NOTIFY_WEBHOOK → NOTIFY_WEBHOOK
failure · discord   ALERT_WEBHOOK
failure · telegram  TELEGRAM_ALERT_WEBHOOK → ALERT_WEBHOOK
FIRM    apex | ftmo | mff   (substring in de account-string)
PHASE   PA* = FUNDED · APEX*/AP* = EVAL · anders geen fase-kandidaat
```

## Wat er voor Legacy resteerde (.NET-kant)

Drie kleine hooks in `Mex.Journal.Receiver`; alle drie leunen op de env-tabel
hierboven en hoeven geen tweede routing-tabel te dragen:

1. **Uitbreiding 2 — per-kanaal routing.** In de dispatch: lees dezelfde env-vars
   en pas dezelfde prioriteit toe. In Python:
   `webhook_for(account, "trade", "discord")` — vertaalbaar naar 6 regels C#.
2. **Uitbreiding 5 — rate-limit.** Simpele in-memory teller per webhook: bij >N
   posts/minuut een korte batch-melding sturen i.p.v. individuele kaarten.
   Tier-A blijft altijd doorgaan (dat is het "iets is heel erg mis"-signaal).
3. **Uitbreiding 6 — Telegram-endpoint.** Als `TELEGRAM_*_WEBHOOK` gezet is,
   post daar dezelfde payload heen. De helper stuurt al `{content, text}`;
   alleen de HTTP-call ontbreekt aan die kant.

## Wat NIET in deze commit zit

- **Chart-snapshot** — dat is D-22, aparte scope met eigen Playwright-werk.
- **Aanpassingen aan de dead-path `notify.py`** — die staat DEAD PATH (D-05);
  daar wordt niets meer aan gebouwd.

## Board-status

D-28 status blijft `blocked` — 3 uitbreidingen (2, 5, 6) hebben Legacy nodig.
Middleware App heeft geleverd wat zonder .NET-code kán. Zodra Legacy die drie
oppikt, kan D-28 naar `review`.
