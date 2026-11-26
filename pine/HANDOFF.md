# Pine-strategieën — handoff

> Plak dit als openingsbericht in een nieuwe chat om met de Pine-thread verder te
> gaan. Volledige stand: wat er is, hoe het in elkaar zit, wat af is en wat open
> staat. Repo: `ferhen1981/tradingkit`, branch
> **`claude/middleware-setup-guide-afhvtk`**.

## 1. Wat dit is
De **8 TradingView Pine v6-strategieën** — één gedeelde engine (mean-reversion),
die onderling verschillen in **asset · fase (Eval/Funded) · DD-model (Intraday/EOD)**.
Spaanse "El ___"-namen. Elk script ~1.7k regels; samen ~13.8k regels.

## 2. De fleet (strategie → asset · fase · type)
| Script | Asset | Fase | Type | Edge |
|---|---|---|---|---|
| **MEX_EL_TESORO** | GC | Funded | EOD | Robuuste workhorse (sterkste, met El Minero) |
| **MEX_EL_MINERO** | GC | Eval | EOD | idem |
| **MEX_EL_REY** | ES | Funded | EOD | Sterkste OOS na de factory |
| **MEX_EL_LEON** | ES | Eval | EOD | idem |
| **MEX_EL_TORO** | NQ | Eval | Intraday | Eval-only (geen funded edge) |
| **MEX_EL_MATADOR** | NQ | Eval | EOD | Eval-only |
| **MEX_EL_DORADO** | NQ | Funded | Intraday | Eval-only variantie-lot |
| **MEX_EL_PATRON** | NQ | Funded | EOD | Eval-only variantie-lot |

**Gevalideerd (3j OOS): alleen GC + ES hebben een echte funded edge** (beide
helften PF>1). De NQ-vier (+ YM) zijn **eval-only** (H2≈1.00) — variantie-loten,
nooit funded compounden.

## 3. Architectuur
- **Eén engine, 8 configs.** Inputs zijn per concern gegroepeerd; een
  **firm-preset dropdown** (groep *8b*) stelt het prop-firm-DD-model in.
- **PropFirms-library** (`pine/lib/PropFirms.pine`) — **auto-generated, NIET met
  de hand bewerken**. Single source of truth = `data/propfirms.json`; draai
  `python3 tools/gen_pine_firms.py` opnieuw na een wijziging, dan blijven de
  Python-backtester én de Pine-scripts in sync. Exporteert
  `rules(preset) -> [ddType, maxLoss$, goal$, dll$, consPct, acctSize$]`.
- **Alert-routing** (groep *9 · EXECUTION*) — onafhankelijke toggles per
  bestemming: `PMT Tradovate`, `Discord`, `Journal`, `PineConnector`, en de
  `→ Middleware (fan-out)` route.

## 4. Laatste versie — v6.9.x
- **v6.9.1 "→ Middleware" route** (alle 8 scripts): `f_sendExec` emit een lean
  JSON-signaal
  `{secret, strategy, event, action, symbol, price, order_type, dollar_sl, dollar_tp, qty}`
  i.p.v. elk account in de alert te bakken. De middleware mapt `strategy` →
  accounts en herbouwt per account de PMT/PineConnector-payload → **11+ accounts
  uit twee alerts (GC, ES) + een configfile**. Nieuwe inputs: `mwSecret`,
  `mwStrategy`. De emit-shape is geverifieerd tegen het middleware `Signal`-model;
  webhook-URL zet je op de TradingView-alert zelf.
- **v6.9.0 Roll/OpEx/News-factory** (hele fleet): input-groep *8b* met een
  `Preset (strategy · type · phase)`-dropdown. `Auto` = gevalideerde default;
  of leen een andere config; of `Off/Custom` met 7 toggles (avoid quarterly roll
  ±N dagen, news-override, avoid triple-witching week, avoid week-na-OpEx, block
  FOMC, block NFP). Kalender-math is native (3rd-Friday resolver + 1st-Friday
  NFP); **FOMC-datums zijn een hardcoded tabel 2022–2026 (2026 projected — jaarlijks
  bijwerken)**. Mechanisme-backed; tilt ES funded H2 1.00→1.16.
  - Preset-defaults: ES → avoid roll (news-override) + week-na-OpEx;
    GC → geen filter (robuust); YM → avoid roll + witching; NQ → block FOMC.

## 5. Stand van zaken
- Alle 8 scripts staan op v6.9.1, gecommit op de branch.
- De middleware-seam is er: Pine emit → `middleware/` fan-out (zie de App-thread /
  `middleware/`-samenvatting).
- PineConnector-brug (MT4/5, FTMO/spot FX·CFD) is gedocumenteerd in
  `pine/PINECONNECTOR_INTEGRATION.md`.

## 6. Open taken / next
1. **Compile-verificatie.** Deze omgeving kan **geen Pine compileren**. Wijzigingen
   moet je in de TradingView-editor plakken; plak compile-errors terug, dan fix ik
   ze. Stapel geen ongeteste changes — bevestig eerst dat de huidige versie compileert.
2. **FOMC-tabel 2027** toevoegen wanneer de datums bekend zijn (nu t/m 2026, 2026
   projected).
3. **PineConnector bakken in de volgende versie** (was gepland ná een bevestigde
   compile), voor de niet-futures leg.
4. **v6.9.1 emit end-to-end roken** tegen de live middleware (één alert → fan-out →
   Tradovate/MT5) zodra je in DRY_RUN wilt valideren.

## 7. Werkafspraken
- **Pine is indentatie-gevoelig: 4-spaties-indent, GEEN tabs.**
- `pine/lib/PropFirms.pine` nooit met de hand editen — via `data/propfirms.json` +
  `tools/gen_pine_firms.py`.
- Ontwikkelen/committen/pushen op **`claude/middleware-setup-guide-afhvtk`**.
- Changelog bijhouden in `pine/CHANGELOG.md` (nu op v6.9.1).
