# Inbox — cross-chat verzoeken

**Dit is een wachtrij, geen archief.** De open lijst met status, prioriteit en
afhankelijkheden staat in **LifeOS → Tasks**, met het voorvoegsel `🛠️ MEX Dev ·` en
gekoppeld aan Area *MEX Traders* / project *MEX PROP TRADER*.
Die is leidend. Hieronder staat alleen de index plus het aanleverformaat.

Zie `docs/CHAT_INSTRUCTIE.md` voor de volledige werkwijze.

---

## Open — stand 2026-08-19

Alle items hieronder zijn geverifieerd tegen `claude/middleware-setup-guide-afhvtk`
@ `21a1100` en staan in de Notion-backlog.

| # | Item | Van → eigenaar | Prio | Status |
|---|---|---|---|---|
| 1 | Geverifieerde commissie per contract uit `Cash_History` | Backtest Setup → **Middleware App** | P1 | OPEN |
| 2 | `backtest/funded.py` leest Apex-regels niet uit `data/propfirms.json` | Backtest Setup → **Backtest Setup** | P1 | OPEN |
| 3 | ATR-kalibratie voor de MR·FVG engine (Fase 1 un-overfit) | Pine Dev → **Backtest Setup** | P1 | OPEN |
| 4 | Commissie in de Pine-scripts is een kopie van een contract-spec | Scrum Master → **Pine Dev** | P1 | NIEUW |
| 5 | CVD-diepte van de NQ-dataset is nooit vastgesteld | Scrum Master → **Backtest Setup** | P2 | NIEUW |
| 6 | `validation/` bewijs staat alleen op de legacy-branch | Scrum Master → **Backtest Setup** | P1 | NIEUW |
| 7 | Secrets roteren — 3 secrets staan sinds 9 aug ongeroteerd | Scrum Master → **Middleware App** | P1 | NIEUW |
| 8 | Chart-snapshot bestaat als 3 losse taken, het is 1 feature | Scrum Master → **Middleware App** | P3 | NIEUW |
| 9 | Draait 'Fase C livegang' al? Runtime-bevestiging nodig | Scrum Master → **Middleware App** | P2 | NIEUW |
| 10 | Sharpe uit de compliance-monitor is nooit gebouwd | Scrum Master → **Middleware App** | P3 | NIEUW |
| 11 | Taak 'v7.0-FM scripts compileren' noemt een dode versie | Scrum Master → **Pine Dev** | P3 | NIEUW |
| 12 | Twee backlog-taken bouwen op achterhaalde aannames | Scrum Master → **Backtest Setup** | P3 | NIEUW |

### 1 · Geverifieerde commissie per contract uit Cash_History
**Backtest Setup → Middleware App** · 2026-08-19 · OPEN

`backtest/config.py CONTRACTS` is de single source, maar de *juiste* getallen komen uit
broker-waarheid: Tradovate `Cash_History` → `cash_ledger.py`. Die aggregeert commissies
al, maar de uitsplitsing per contract ontbreekt — dat is de deliverable.

**Gevraagd:** per verhandeld contract (NQ/MNQ, ES/MES, GC/MGC, …) de werkelijke
round-turn commissie + fees per venue (Apex/Tradovate, MFFU, FTMO/MT5).

**Waarom urgent:** kandidaten met 10-17k trades/jaar op 1m kantelen van winstgevend naar
verliesgevend tussen $0.52 en $1.75 per side. PF-oordelen op die groep zijn onbetrouwbaar
zolang dit open staat.

### 2 · funded.py leest Apex-regels niet uit de registry
**Backtest Setup → Backtest Setup** · 2026-08-19 · OPEN

`backtest/funded.py:19` heeft `APEX_DD` hardcoded, plus payout-ladder en consistency.
`backtest/firms.py` leest `data/propfirms.json` al correct. Tot dit opgelost is kunnen
funded-simulaties afwijken van de registry zodra de JSON verandert.

### 3 · ATR-kalibratie voor de MR·FVG engine
**Pine Dev → Backtest Setup** · 2026-08-19 · OPEN

`MEX_EL_TESORO` v7.9.1 stelt `Distance Unit` open met een ATR-optie (`unitMode`, regel
118): op ATR worden FVG-band, stop, TP en buffers ATR(14)-veelvouden. Default blijft
`Ticks`, dus live is onveranderd.

**Gevraagd:** (a) huidige MGC-tick-tuning omrekenen naar ATR(14)-veelvouden op 1m —
FVG 9-18t, stop 100t, max 130t, TP R-mult 2.5; (b) die veelvouden sweepen op
**MGC + ES + NQ**; (c) de set leveren die over de drie assets standhoudt.

### 4 · Commissie in Pine is een kopie van een contract-spec — NIEUW
**Scrum Master → Pine Dev** · 2026-08-19 · OPEN

`pine/*.pine` regel ~58 zet `commission_value=1.55`; `MEX_EL_TESORO.pine` regel ~70 zet
`0.67`. De bron `backtest/config.py CONTRACTS` kent zeven waarden (1.55 index · 0.37
micros · 0.52 MGC · 1.75 metalen/energie/FX-futures · 3.5 spot FX).

Twee losstaande problemen: het **getal** klopt niet (MGC 0.52 vs 0.67, en TESORO is
funded), en de **structuur** klopt niet — een handmatig getal in Pine is een tweede
source of truth, ook als het getal juist is. `PropFirms.pine` wordt al gegenereerd; de
contract-specs niet.

Wacht op item 1 voor de juiste waarde; de structuurfix kan onafhankelijk.

### 5 · CVD-diepte van de NQ-dataset is nooit vastgesteld — NIEUW
**Scrum Master → Backtest Setup** · 2026-08-19 · OPEN

`docs/state.md` (analyses-branch): NQ 2023-06-18 → 2026-06-17, ~1.1M rows,
*CVD valid from: unknown, CVD depth unverified*. De regel is dat CVD nooit uitgezet
wordt — met `use_cvd_filter=False` backtest je een andere strategie dan de live versie,
omdat de filter dan een pass-through wordt.

Dit blokkeert optie A van het OOS-besluit (herselecteren op pre-2023) volledig.
`tools/validate_dataset.py` op de analyses-branch heeft hier een CVD-gate voor.

### 6 · validation/ bewijs staat alleen op de legacy-branch — NIEUW
**Scrum Master → Backtest Setup** · 2026-08-19 · OPEN

De stage 1-10 preregistraties en verdicts voor de FLEET en de NQ-familie
(`validation/FLEET_*`, `NQFAMILY_*`, `NQ_fleet_*` + 4 pipeline-runners) staan uitsluitend
op `claude/legacy-accounts-scripts-analysis-ui0j6m`. Dat is het onderliggende bewijs voor
de kernclaim *GC + ES funded edge, NQ/YM eval-only*.

### 7 · Secrets roteren — NIEUW
**Scrum Master → Middleware App** · 2026-08-19 · OPEN · **P1**

Drie secrets zijn in chats langsgekomen en staan sinds 9 augustus ongeroteerd: het
Notion-token, de Discord-webhook en het Fase C endpoint-token. `middleware/docs/SECRETS-REGISTER.md`
is de plek om af te vinken. Dit stond als taak zonder status of prioriteit in LifeOS en
was daardoor onzichtbaar — nu P1.

### 8 · Chart-snapshot is één feature verdeeld over drie taken — NIEUW
**Scrum Master → Middleware App** · 2026-08-19 · OPEN

Dezelfde functionaliteit staat drie keer open: *Signal-renderer stap 5*,
*Chart-screenshots bij Discord-alerts*, en punt 4 van de notify-backlog in
`middleware/docs/DISCORD_NOTIFY_HANDOFF.md`.

De renderer heeft de ruimte al: `render-signal.js` kent een `chartUrl`-veld en
`.chart img`-CSS. Wat ontbreekt is de Playwright-capture. **Voorstel:** houd stap 5 aan
als de enige taak en sluit de andere twee.

### 9 · Draait 'Fase C livegang' al? — NIEUW
**Scrum Master → Middleware App** · 2026-08-19 · OPEN

De taak beschrijft een alert-webhook naar `mw.mex-traders.com/signal/<token>` voor
v7.0-FM. Maar `mex-receiver` draait live als signaal-relay en *Fase C starten* is
afgevinkt; Pine zit inmiddels op v6.9.x/v7.9.x, niet op v7.0-FM.

**Gevraagd:** bevestig met `systemctl cat mex-receiver` of deze route al live is. Zo ja,
sluiten. Ik kan dit niet zelf verifiëren — geen VPS-toegang.

### 10 · Sharpe uit de compliance-monitor is nooit gebouwd — NIEUW
**Scrum Master → Middleware App** · 2026-08-19 · OPEN

De compliance-monitor is grotendeels af — `payout_rules.py` rekent de 30%-consistency,
de payout-ladder per rung en de drawdown per programma uit `data/propfirms.json`. Eén
onderdeel uit de oorspronkelijke taak is nooit gebouwd: **Sharpe**. Ik heb de taak
afgevinkt op wat er wél staat en dit losgeknipt.

**Gevraagd:** opnieuw scopen of laten vervallen. Sharpe op prop-accounts met een
drawdown-floor is discutabel — DD-units zeggen meer dan volatiliteit.

### 11 · Taak 'v7.0-FM scripts compileren' noemt een versie die niet meer bestaat — NIEUW
**Scrum Master → Pine Dev** · 2026-08-19 · OPEN

De scripts staan op v6.9.x en TESORO op v7.9.1; 'v7.0-FM' bestaat niet meer als
generatie. Compileren blijft nodig bij elke uitrol, maar dan tegen de huidige versie.

**Gevraagd:** sluiten of herformuleren. Niet afgevinkt, omdat compileren geen
afgeronde handeling is.

### 12 · Twee backlog-taken bouwen op achterhaalde aannames — NIEUW
**Scrum Master → Backtest Setup** · 2026-08-19 · OPEN

- **'Engine-spec finaliseren + op middleware-backlog'** — grotendeels ingehaald door
  `backtest/lab/` en de 15 specs in `backtest/specs/`. Sluiten of herformuleren naar wat
  er nog ontbreekt.
- **'Woensdag-analyse doorrekenen (skip of kleiner)'** — fijnmazig dag×uur-cherrypicken
  is inmiddels weerlegd als OOS-ruis (`CLAUDE.md`, roll/OpEx-factory v6.9.x). Sluiten,
  tenzij er een mechanisme onder zit dat het rechtvaardigt.

---

## Aanleverformaat

```
### <korte titel>
**<van> → <naar/eigenaar>** · <datum> · status: OPEN

Probleem:
Waarom cross-chat:
Betrokken bestanden:
Benodigde wijziging:
Live-impact:      NONE / LOW / MEDIUM / HIGH
Acceptatiecriteria:
```

Raakt het het live executiepad, voeg toe: service · runtime geverifieerd (ja/nee + hoe) ·
huidig gedrag · nieuw gedrag · failure mode · rollback.

## Afhandeling

De eigenaar voert uit en meldt het hier met de commit-hash. De Scrum Master werkt de
Notion-backlog bij en haalt het item hier weg. Een item dat op een andere chat wacht is
**BLOCKED**, niet DONE.
