# Institutional Multi-Market Trading Framework — design & mapping

> De architectuur achter de **generator** en de **4e-variant builder** van de
> Backtest Lab. Dit doc bevriest *hoe* we strategieën samenstellen: niet als
> een zak losse indicatoren, maar als een **hiërarchisch decision-framework**
> waarin iedere indicator een vaste laag, rol en informatiewaarde heeft.
>
> Status: **design freeze** (v1). Bouwstappen staan onderaan (§10). Repo:
> `ferhen1981/tradingkit`, branch `claude/middleware-setup-guide-afhvtk`.

---

## 0. Waarom dit doc bestaat

De huidige generator (`backtest/generator.py::sample_spec`) pakt een
**willekeurige subset** van 2–8 indicator-groepen uit een vlakke pool van 25,
sampled de params op een grid en repareert een handvol harde constraints. Er is
**geen hiërarchie, geen regime-gate, geen rolverdeling**. RSI, VWAP,
market-structure en ATR zijn inwisselbare "confirmaties" die door elkaar
gehusseld worden. Gevolg:

1. **Onduidelijk spectrum** — we testen indicatoren tegen elkaar zonder dat een
   strategie een coherente these heeft.
2. **Double-counting** — de sampler kan `rsi + stochastic + macd_histogram`
   kiezen en telt dat als drie bevestigingen, terwijl het driemaal hetzelfde
   momentum-signaal is.

Dit framework vervangt de random-subset door **compositie per rol**: een
strategie is een *stack van slots* met een vaste beoordelingsvolgorde. Dat
haalt de randomness eruit én maakt double-counting structureel onmogelijk.

**Fundamentele regel:** *Regime bepaalt welke strategie is toegestaan.
Lagere-timeframe indicatoren mogen nooit zelfstandig een hoger-timeframe regime
overrulen.* Een RSI-, MACD-, VWAP- of candlestick-signaal is dus nooit op
zichzelf voldoende voor een trade.

---

## 1. De 10-laags decision engine (vaste volgorde)

Markten worden altijd in deze volgorde beoordeeld. Elke laag heeft een functie;
lagere lagen leveren *context* aan hogere, nooit andersom.

| # | Laag | Functie | Kernvraag |
|---|------|---------|-----------|
| **L0** | Cross-Market / Macro | intermarket-context | Staat de wind mee? (DXY, yields, VIX, breadth) |
| **L1** | Market Regime | trend × volatility classificatie | Welk speelveld is dit? |
| **L2** | Directional Bias | long / short / neutral | Welke kant mag ik? |
| **L3** | Market Structure | HH/HL/LH/LL, BOS, CHoCH | Wat dóet de prijs echt? |
| **L4** | Location | waar staat prijs? (VWAP, levels, zones) | Is dit een goede plek? |
| **L5** | Participation / Flow | volume, delta, OI, breadth | Doet het geld mee? |
| **L6** | Momentum | RSI, ROC, MACD-hist | Versnelt of vertraagt het? |
| **L7** | Volatility | ATR, percentiel, compressie | Hoe hard beweegt het? → sizing & stops |
| **L8** | Setup Classification | trend-pullback / breakout / MR / reversal | Welk type trade is dit? |
| **L9** | Execution Trigger | sweep, reclaim, BOS, retest | Nu instappen? |
| **L10** | Risk & Position Sizing | stop op structure, ATR-min, %-risk | Hoeveel? |
| → | **Verdict** | | TRADE / REDUCED SIZE / NO TRADE |

De **setup-class (L8)** is de spil: het regime (L1) bepaalt welke setup-classes
zijn toegestaan (zie §7 matrix), en pas als een class is toegestaan mag de
execution-trigger (L9) vuren.

---

## 2. Scope-grens — wat is *nu* backtestbaar

De lab leest **één instrument, OHLCV-bars** (Quantower/ATAS-CSV → genormaliseerd).
Er is geen tweede datafeed en geen order-flow tape. Dat bepaalt hard wat we
vandaag kunnen valideren:

- 🟢 **Backtestbaar nu** (single-instrument OHLCV + volume):
  L1 Regime, L2 Bias, L3 Structure, L4 Location (VWAP/levels/sessies),
  L6 Momentum, L7 Volatility, L8 Setup, L9 Trigger, L10 Risk.
- 🟡 **Ondiep L5 Participation — IN SCOPE** — alleen wat uit bar-volume +
  afgeleide CVD komt (`cvd_delta`, relative volume). Dit integreren we in v1.
- 🔴 **L0 Cross-Market — TOEKOMST (bouwbaar)** — DXY, yields, VIX, breadth,
  sectorrotatie. Vereist een tweede, op timestamp uitgelijnde datafeed, maar dat
  zijn óók gewoon OHLCV-series: de bestaande `normalize.py` + dataset-catalogus
  kan meerdere series inladen. Begrensde bouw, geen externe API's — kandidaat
  voor de eerste uitbreiding ná v1.
- ⛔ **Diep L5 — LOSGELATEN (besluit)** — TICK, advance/decline, Open Interest,
  funding, liquidations, footprint/delta-tape. Vereist databronnen die we niet
  hebben (en die achteraf op OHLCV-bars niet te reconstrueren zijn). **Bewust uit
  scope, geen stub.** De `footprint`-groep is uit de registry verwijderd.

**Consequentie voor v1:** we bouwen de engine rond de 🟢-lagen + ondiep L5.
L0 krijgt een *expliciete stub* (rol bestaat in de architectuur, levert nu
`neutral`, datalaag later aan te sluiten zonder de rolstructuur te herzien).
Diep L5 laten we volledig los — niet als stub, gewoon weg.

---

## 3. Role-map — alle 25 registry-groepen naar een laag

Elke groep krijgt één **primaire laag** (waar hij in de sampler zijn slot vult)
en optioneel **secundaire** bijdragen. `wired` = de engine handelt er echt naar;
`decorative` = staat in de registry maar wordt nog niet berekend (kandidaat om
te wiren of te schrappen). Dit is de tag die als `layer:` per groep in
`registry.yaml` landt (§10, stap 1).

### Family A — price action / order flow (13)

| Groep | Primaire laag | Secundair | Status |
|-------|---------------|-----------|--------|
| `moving_average`* | L1 Regime | L2 Bias | wired |
| `market_structure` | L3 Structure | L9 Trigger (BOS/CHoCH) | wired |
| `order_block` | L4 Location | L3, L9 | wired |
| `liquidity_eqhl` | L4 Location | L9 Trigger (sweep) | wired |
| `premium_discount_ote` | L4 Location | — | decorative |
| `vwap` | L4 Location | L2 Bias (VWAP-side) | wired |
| `kill_zones` | L4 Location | session-gate | decorative |
| `cvd_delta` | L5 Participation (ondiep) | L2 Bias | wired |
| `momentum` | L6 Momentum | L9 Trigger (impulse) | wired |
| `divergence` | L6 Momentum | L5, L9 (CVD-div reversal) | wired |
| `fvg` | L9 Trigger | L3 Structure | wired |
| `silver_bullet` | L8 Setup | L4+L9 (composiet) | wired |
| `swing_stops` | L10 Risk | — | wired |

\* `moving_average` staat in family A alleen als kruisverwijzing; hij hoort
registry-technisch bij `classic` maar vervult de regime-rol. Zie hieronder.

### Family B — classic (12)

| Groep | Primaire laag | Secundair | Status |
|-------|---------------|-----------|--------|
| `moving_average` | L1 Regime | L2 Bias | wired |
| `ema_cross` | L2 Bias | L9 Trigger (cross) | wired |
| `supertrend` | L1 Regime | L2 Bias | decorative |
| `ichimoku` | L1 Regime | L2 Bias | decorative |
| `adx_dmi` | L1 Regime | trendkracht-gate | decorative |
| `donchian` | L3 Structure | L9 Trigger (breakout) | wired |
| `rsi` | L6 Momentum | — | wired |
| `stochastic` | L6 Momentum | — | decorative |
| `macd` | L6 Momentum | L2 Bias (trendcomp.) | wired |
| `bollinger_bands` | L7 Volatility | L4 Location, MR-trigger | wired |
| `keltner` | L7 Volatility | L4 Location | decorative |
| `atr` | L7 Volatility | L10 Risk (stop-sizing) | decorative |

**Observatie:** de wired-groepen dekken L1–L10 af. De expliciete L1
regime-classifier is inmiddels gewired (§11 stap 3): een objectieve
trend×volatility-tag uit MA-stack + ADX + ATR-percentiel
(`indicators.classify_regime`). `adx_dmi`/`atr` doen nu echt werk als
regime-inputs; `supertrend`/`ichimoku` blijven decorative tot ze als
alternatieve regime-bron gewired worden.

---

## 4. De role-composing sampler (kern van de verandering)

**Nu** (`sample_spec`): kies random subset van de pool → sample → repair →
validate.

**Straks:** vul **per laag maximaal één slot**, in volgorde, waarbij elk slot
alleen groepen aanbiedt die bij die laag zijn getagd én compatibel zijn met de
al gekozen bovenliggende lagen.

```
compose_strategy(regime_hint, rng):
    L1  regime_filter   = pick_one(groups[L1])          # verplicht
    L2  bias            = pick_one(groups[L2] | none)
    L3  structure       = pick_one(groups[L3] | none)
    L4  location        = pick_one(groups[L4] | none)
    L5  participation   = pick_one(groups[L5] | none)   # 🟡 alleen cvd/volume nu
    L6  momentum        = pick_one(groups[L6] | none)   # ← max één! redundancy-guard
    L7  volatility      = pick_one(groups[L7] | none)   # stuurt sizing/stops
    L8  setup_class     = derive(regime, gekozen slots) # zie §7 matrix
    L9  trigger         = pick_one(triggers geldig voor setup_class)
    L10 risk            = pick_one(groups[L10]) ⊕ ATR-min
    → spec  (repair harde constraints, validate)
```

Eigenschappen die we hiermee **gratis** krijgen:

- **Geen double-counting** — max één slot per informatiecategorie (§5).
- **Coherente strategieën** — een breakout-setup krijgt geen mean-reversion
  trigger aangeboden; de setup-class filtert de geldige triggers (§7).
- **Regime-respect** — L1 is verplicht en gekozen vóór alle lagere lagen; een
  L6/L9-signaal kan L1 niet overrulen.
- **Backwards-compatible** — de output is nog steeds één geldige spec die door
  dezelfde `validate_spec` → `spec_to_config` → engine-funnel gaat. De funnel
  (screen → refine → OOS) verandert niet; alleen *welke* kandidaten hij krijgt.

`describe_config` (bestaat al) blijft de eerlijke lezer: entries / filters /
exit / family. We breiden hem uit zodat hij ook de **laag-per-laag rolinvulling**
teruggeeft — dat is precies de live-preview van de 4e-variant builder.

---

## 5. Redundancy-guard — één signaal per informatiecategorie

Sterk gecorreleerde indicatoren mogen niet als onafhankelijke bevestigingen
tellen. De sampler kiest **max één** groep per categorie; de builder-UI groepeert
per categorie en laat er één aanvinken.

| Categorie | Groepen (kies max 1 als *confirmatie*) |
|-----------|----------------------------------------|
| Trend/regime | `moving_average`, `supertrend`, `ichimoku`, `adx_dmi` |
| Momentum | `rsi`, `stochastic`, `macd`(-hist), `momentum`, `divergence` |
| Volatility | `atr`, `bollinger_bands`(width), `keltner` |
| Participation | `cvd_delta`, relative-volume  *(diep L5 losgelaten)* |
| Location | `vwap`, `order_block`, `liquidity_eqhl`, `premium_discount_ote`, levels |
| Structure | `market_structure`, `donchian`, `fvg` |

Uitzondering: een groep mag in zijn **primaire** rol én als **execution-trigger**
dienen (bv. `donchian` als structure-breakout dat óók de trigger is) — dat is
geen double-count maar dezelfde bouwsteen in twee lagen, wat we expliciet
labelen.

---

## 6. Setup × Regime matrix (L1 → L8)

Regime (L1) bepaalt welke setup-classes zijn toegestaan. Score 1–5 = geschiktheid.

| Regime | Trend-Pullback | Breakout | Mean-Reversion | Reversal |
|--------|:---:|:---:|:---:|:---:|
| Strong Trend | 5 | 5 | 1 | 1 |
| Controlled Trend | 5 | 3 | 2 | 1 |
| Compression | 1 | 4 | 3 | 1 |
| Low-Vol Range | 1 | 1 | 5 | 3 |
| High-Vol Range | 2 | 1 | 4 | 3 |
| Exhaustion | 1 | 1 | 3 | 5 |
| Transition | 2 | 2 | 2 | 3 |
| Indecision | — | — | — | — → **No Trade** |

Regimes worden objectief vastgesteld (L1-inputs): prijs vs 200-MA + slope,
50/200-kruising, 20/50, HTF-structure, ADX, ATR-percentiel, BB-width,
range-expansie/-contractie. De matrix is de gate tussen L1 en L9: een
breakout-trigger in een Low-Vol Range krijgt geen groen licht.

---

## 7. Setup-classes (L8) — de vijf toegestane types

- **A. Trend-Pullback** — strong/controlled trend; pullback naar VWAP/AVWAP/prior
  breakout binnen de bias.
- **B. Momentum-Breakout** — strong trend of compression→expansion; range-break
  met participation-bevestiging.
- **C. Mean-Reversion** — range, lage ADX, vlakke VWAP; fade van extremen.
- **D. Reversal / Exhaustion** — exhaustion, failed breakout, structural reversal.
- **E. No Trade** — conflicterende signalen, slechte location, onvoldoende
  liquidity, onduidelijk regime, event-risk.

---

## 8. Scoring model — **prior + display, funnel is de rechter**

Een 0–100 gewogen score is een **leesbare setup-grade en een ranking-prior**,
géén poort. De **OOS-funnel** (PF/expectancy op holdout) bepaalt of een kandidaat
doorgaat. Reden: een met-de-hand-gewogen score is zelf een overfit-risico; we
laten gerealiseerde edge de waarheid zijn, niet een gewichtenvector.

Startgewichten (per markt herijkbaar):

| Component | Gewicht |
|-----------|:---:|
| Cross-Market Context (L0) | 10 |
| Regime (L1) | 15 |
| Direction (L2) | 10 |
| Structure (L3) | 15 |
| Location (L4) | 15 |
| Participation (L5) | 10 |
| Momentum (L6) | 5 |
| Volatility (L7) | 10 |
| Execution Trigger (L9) | 5 |
| Risk Quality (L10) | 5 |
| **Totaal** | **100** |

Grades: **90–100 A+ · 80–89 A · 70–79 B (reduced) · 60–69 observation · <60 no
trade**. Grade drijft *sizing-suggestie en sortering*, niet de accept/reject in
de backtest.

### 8a. Bias-discipline — regime als *gemeten uitkomst*, niet als aanname

Kernregel: **je gaat zonder bias de test in.** De backtest observeert de
omstandigheden causaal (bar-voor-bar, geen look-ahead/repaint — bewezen: 0/1000
labels veranderen als je toekomstige bars toevoegt) en het vonnis komt uitsluitend
van de gerealiseerde OOS-edge. Concreet ingebouwd:

- **Generatie is default ongebiast** — `compose_batch` zonder `regimes=` sampelt
  uniform over de setup-classes. De §6-matrix-weging is **opt-in** (`--regimes`),
  puur voor *targeted search* als je al een hypothese hébt.
- **De rechter is realized PF** — de mill selecteert/sorteert op OOS-PF, nooit op
  de prior-score. De score kleurt en rangschikt alleen.
- **Regime wordt een uitkomst, geen input** — `metrics.edge_by_regime` tagt élke
  trade met het objectieve regime op z'n **entry-bar** (causaal) en breekt de
  realized PF/expectancy/n per regime uit. Zo vertelt de data *waar* de edge zit,
  in plaats van dat wij het opleggen.

Daarmee is de §6-matrix een **hypothese die je toetst**, niet een bias: de
run-detail zet "assumed" (regime-fit in de score) naast "realized"
(edge-by-regime), zodat je de matrix kunt bevestigen óf weerleggen. Vindt de data
dat mean-reversion óók in een Strong Bull Trend werkt, dan zie je dat — de matrix
onderdrukt het niet.

**Regime-gate (finetune-tool).** Zodra `edge_by_regime` laat zien *waar* de edge
zit, zet je dat om in een échte verbetering met `cfg.regime_filter`: entries
vuren dan alléén in de gekozen regimes (causaal via `classify_regime`, gecheckt
op zowel signaal- als fill-bar, zodat elke trade — en dus de attributie —
consistent binnen de filter valt). Leeg filter = alle regimes (no-op, nul kosten).
CLI: `run.py --regime-filter "Strong Bull Trend,Controlled Bull Trend"`. Cruciaal:
het effect wordt daarna **opnieuw ongebiast op OOS gemeten** — lift het de PF
echt, of snoei je toevallige trades weg? De gate verzint geen edge (op ruis blijft
het een no-op); hij concentreert een bestaande edge.

**Hard veto's** (blokkeren ongeacht score — dit zijn wél poorten):
major macro-release imminent · onacceptabel grote/technisch onmogelijke stop ·
extreme volatility-event · onvoldoende participation/liquidity · slechte
reward/risk · te grote correlated exposure · conflicterende HTF-structure.

---

## 9. Markt-specifieke varianten

Één master-engine, vier configuraties. Verschil zit in *welke* groepen per laag
zwaar wegen en welke datalagen beschikbaar zijn.

- **Equities/Spot** — hiërarchie `Market → Sector → Stock → Catalyst → RelStrength
  → Volume → Location → Setup → Trigger`. Zwaar: RVOL, AVWAP, opening-gap,
  premarket, breadth. (🔴 sector/breadth = toekomst.)
- **Futures** (ES/NQ/GC/CL) — zwaar: centralized volume, VWAP/profile,
  overnight H/L, opening-range, RTH vs ETH, ondiepe delta/CVD. **Dit is de best
  gedekte variant nu** (de bestaande specs draaien hier). *(TICK/breadth =
  diep L5, losgelaten.)*
- **Forex** — géén centralized volume: leun op relative currency strength, DXY,
  yield-differentials, sessie-structuur (Asia/London/NY-overlap), sessie-H/L,
  ATR, HTF-trend, sweeps. Tick-volume ≠ centralized volume.
- **Crypto** — spot + perp, 24/7 vol-structuur, VWAP/AVWAP, weekly levels,
  ondiepe CVD/volume. Het klassieke onderscheid gezonde spot-move
  (`prijs↑ + spot-vol↑ + OI↓`) vs. leveraged/crowded
  (`prijs↑ + OI↑↑ + funding+ + zwak spot-vol`) vergt OI/funding — *diep L5,
  losgelaten*. Zonder die feeds blijft crypto op de 🟢-lagen + ondiep L5.

---

## 10. Gestandaardiseerde output per instrument

Het framework produceert per instrument een vaste kaart:

```
Instrument:  NQ            Market:      Futures
Regime:      Controlled Bull Trend      Volatility:  Normal
HTF Bias:    Long          Intraday:    Long
Structure:   HH/HL         Location:    VWAP Pullback
Participation: Positive     Momentum:    Reset → Re-acceleration
Setup:       Trend-Pullback  Execution:  5m Sweep + Reclaim + BOS
Risk:        Normal        Score:       84/100  (Grade A)
Action:      Long allowed
```
…of `Action: No Trade` met exacte reden (welke laag/veto blokkeerde).

---

## 11. Bouwplan (gefaseerd, backtestbaar-eerst)

1. ~~**Registry hertaggen**~~ — ✅ **DONE** (registry v2): `layer:` + `role:` +
   `info_category:` (+ `secondary:`) per groep in `registry.yaml` (§3);
   `footprint` verwijderd (diep L5 losgelaten). Puur data, geen gedrag; 83 tests
   groen.
2. ~~**`describe_config` uitbreiden**~~ — ✅ **DONE**: `describe_config` geeft nu
   een `stack` (L0..L10, rol + actieve groepen per laag) + `stack_summary`.
   Zichtbaar in de Strategy Library én — via `run.json` — in de run-detail
   (dekt open taak 2 uit de handoff). 85 tests groen.
3. ~~**L1 regime-classifier wiren**~~ — ✅ **DONE**: `indicators.classify_regime`
   = MA-stack (20/50/200 EMA) + slow-slope + ADX + ATR-percentiel → een
   objectieve trend×volatility-tag per bar (7 regimes + Indecision warm-up,
   framework §6). Elke run slaat nu z'n regime-distributie op (`meta.regime`),
   zichtbaar in de run-detail + als annotatie op de L1-stackregel. 89 tests groen.
4. ~~**Role-composing sampler**~~ — ✅ **DONE**: `generator.compose_strategy` /
   `compose_batch` — kiest een setup-class (regime-hint → §6-matrix-gewogen),
   dan één primaire entry, dan optionele coherente filters onder de
   redundancy-guard (max één groep per `info_category`), plus altijd een
   swing-stop. Vervangt de random-subset; standaard in de mill
   (`generate.py --sampler role`, met `--regimes`). Legacy random-subset blijft
   via `--sampler random`. 95 tests groen; end-to-end door de engine bewezen.
5. ~~**Scoring als prior**~~ — ✅ **DONE**: `scoring.score_strategy` → 0–100
   setup-grade (A+/A/B/Observation/No-Trade, §8-gewichten) uit de decision-stack
   + regime-fit. Puur **prior/display**: getoond in de Strategy Library (grade-pill),
   run-detail (score-blok) en de candidates-leaderboard; de **OOS-funnel blijft de
   rechter**. Ongevulde optionele lagen krijgen een neutrale baseline (niet nul) —
   trouw aan de "meer ≠ beter"-ethos. 100 tests groen.
5b. ~~**Per-regime edge-attributie**~~ — ✅ **DONE** (bias-discipline, §8a):
   `metrics.edge_by_regime` tagt élke trade met het causale regime op z'n
   entry-bar (geen look-ahead, bewezen) en breekt realized PF/expectancy/n per
   regime uit — opgeslagen per run (`meta.edge_by_regime`), getoond in de
   run-detail als "Realized edge by regime". Zo is regime een **gemeten uitkomst**
   die de §6-matrix toetst, geen aanname die hem oplegt. 103 tests groen.
5c. ~~**Regime-gate op entries**~~ — ✅ **DONE** (§8a): `cfg.regime_filter` —
   entries vuren alléén in gekozen regimes (causaal, gecheckt op signaal- én
   fill-bar → consistent met de attributie). Leeg = alle regimes (no-op). CLI
   `run.py --regime-filter`. Sluit de ontdek→finetune-lus: `edge_by_regime` zegt
   *waar* de edge zit, de gate handelt er alléén nog daar, effect opnieuw
   ongebiast op OOS gemeten. 106 tests groen.
6. **4e-variant builder UI** — vink per laag een rol aan → live `describe`-preview
   → opslaan als spec → runnen. De role-getagde registry ís het skelet.
   ← **volgende stap**
7. **Later (🔴 data, optioneel):** L0 cross-market feed (DXY/VIX/yields als
   uitgelijnde OHLCV-series). Rolstructuur ligt er dan al; alleen de datalaag
   koppelen. *Diep L5 is losgelaten — geen onderdeel meer van het plan.*

---

*Kernboodschap: we bouwen geen verzameling indicatorstrategieën, maar één
multi-market decision engine waarin iedere indicator een vaste laag, rol en
informatiewaarde heeft. De randomness verdwijnt doordat we per rol componeren,
niet per toeval combineren.*
