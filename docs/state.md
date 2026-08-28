# Live state

Read this first in every chat. Update it last. If it is stale, nothing below it
can be trusted.

_Last updated: 2026-08-28 (Analyses & Data chat)_

## Live settings

Per-account sizing en day-target/DLL zijn **buffer-gedreven** (D-43). DLL en
day-target worden **hard in Tradovate** ingesteld, niet via de Pine risk-gate.
Basisstrategie: El Tesoro MGC1! met Fixed TP 85t, Fixed Stop 100t, BE/Trail off,
Day-trail activation $500 / giveback $100, Day-cap hard $750 (Pine-instellingen
zoals in backtest `91469a71` — de "afgelopen 2 weken haal je target op de mediaan
al" run).

| Account | Balance | Buffer (Dist Liq) | Modus | Qty | Day Target ↑ | DLL ↓ |
|---|---:|---:|---|---:|---:|---:|
| PA013 | $54.164 | $4.064 | payout-buildup (34.9% cons., nog $1.042) | 6 | +$500 | −$500 |
| PA015 | $50.478 | $581 🚨 | herstel — krap | 2 | +$200 | −$200 |
| PA017 | $49.338 | $785 🚨 | herstel — krap | 2 | +$250 | −$300 |
| PA018 | $53.479 | $3.379 | payout-buildup | 5 | +$450 | −$450 |
| PA021 | $49.243 | $1.096 | opbouw — voorzichtig | 3 | +$300 | −$350 |
| PA022 | $50.069 | $2.014 | normale | 4 | +$400 | −$400 |

**Herzien op deze triggers**, niet op tijd:
- Payout uitbetaald → qty terug naar basis van nieuwe buffer, cyclus opnieuw
- Buffer < $1.000 → qty naar 2, target $200, DLL $200
- Buffer $1.000-2.000 → qty 3, target $300, DLL $300-350
- Buffer $2.000-4.000 → qty 4-5, target $400-450, DLL $400-450
- Buffer > $4.000 → qty 5-6, target $500, DLL $500
- Buffer > $5.000 EN payout-eligible → payout nemen, nieuwe cyclus

## D-43 — Buffer-gedreven per-account sizing + hard Tradovate-limits (28 aug 2026)

**Waarom.** Fleet-optimalisatie-analyse op de MGC1! 1-jaars backtest (config
`91469a71`, TP 85t Fixed) laat zien: mediaan-dag ligt op qty 5-6 tussen $400-500
= precies in target. Netto/jaar wordt niet gedood door lage winrate maar door
~1-op-10 tilt-dagen van −$3k tot −$6k. Concreet voorbeeld: 2 weken 14-28 aug
2026 leverden qty 5 in totaal +$1.826 op — maar 10 van de 11 handelsdagen waren
gemiddeld +$568 (in target). Eén dag (17 aug, −$3.862) at 10 winstdagen op.

**Beslissing.** Twee dingen tegelijk:
1. **Day-target en DLL worden hard in Tradovate ingesteld** (niet via de Pine
   `Daily risk-gate`). Reden: Ferry heeft controle in het broker-platform, geen
   afhankelijkheid van Pine-phase (Developer vs Apex PA). Verlies daarmee wél de
   simulatie-mogelijkheid in de backtester — accepteren, want live-fills wegen
   toch al 2× (evidence-weighting hoger in dit document).
2. **Sizing is per-account, gedreven door DIST TO AUTO LIQ** (= runway naar
   trailing-DD-liq). Formule staat hierboven onder "Live settings". Kern: qty
   moet zó laag zijn dat één full-loss trade (`qty × 100t × $1`) niet meer dan
   ~40% van de dagelijkse DLL raakt.

**Waarom niet DLL uit en discount-accounts vervangen.** Discount-accounts kosten
$19/stuk (Ferry heeft pipeline). Reset-kosten dus niet de bottleneck. Maar
opportunity-cost is dat wél: elk gebreached account levert 0 payout ipv de
$16-41k/jaar per overlevend account. DLL AAN verlaagt breach-rate van ~50-60%
naar ~5-15% op basis van Python-sim over de 1-jaars data. Delta = $18-22k/maand
fleet-winst. Discount-economics vervangen dat niet.

**Waarom niet één vaste qty over alle 6 accounts.** PA015 met qty 6 = één SL
van $600 op $581 buffer = instant breach. Uniform sizen negeert de spread in
buffer-staat en verspilt de kleinere accounts. Buffer-modes maken elke account
op zijn eigen tempo bruikbaar.

**Openstaande validatie.** Deze regels zijn afgeleid uit één 1-jaars backtest
en één 2-weken live-slice. Herzien na 2 handelsweken live (uiterlijk 11 sep
2026): klopt de mediaan-dag met de backtest-verwachting per qty? Zo nee — de
regels aanpassen, geen nieuwe fleet-uitrol tot de discrepantie verklaard is.

**Niet in scope:** BE-lock / trail-tick-parameters. Vorige poging (backtest
`4d22f520`) toonde dat die knoppen de edge doden (jaar-netto −$302k op MGC).
Blijven uit.

## Datasets

## Datasets

Tracked in `data/manifest.json` (not yet created). No analysis may cite a dataset
that is not registered there.

| Symbol | Range | CVD valid from | Rows | Source | Status |
|---|---|---|---|---|---|
| NQ | 2023-06-18 → 2026-06-17 | **unknown** | ~1.1M | TradingView 1m export | in use, CVD depth unverified |

## In-sample / out-of-sample

Defined on the **CVD-valid window**, not the calendar.

- **In-sample**: everything before the final 3 years.
- **Out-of-sample**: the **last 3 years**, reserved — this is the window intended
  for the public track record on the site.
- **Walk-forward**: `funnel.py` restarts a fresh eval at many points inside the
  in-sample window. This is how configs get chosen; the 3-year block is not
  touched during selection.
- **Sealed holdout**: the most recent 12 months sit *inside* the OOS block and are
  opened last, once a config is frozen. One look, one verdict.

⚠ **The 2023-2026 window is currently burnt.** The roll/OpEx factory was tuned on
it (`CLAUDE.md`: "validated, 3y OOS"), so as things stand it is in-sample by use
and cannot honestly be presented as out-of-sample on a public site. Two ways back:

1. **Re-select on pre-2023 only** and leave the 3 years genuinely untouched. Clean,
   and it makes the site claim true — but it needs CVD history reaching back
   before 2023, which is exactly the open question.
2. **Relabel** the 3 years as *validation* and let the true out-of-sample be
   forward: live results from the day a config is frozen.

Option 2 always works and costs nothing but patience. Option 1 depends on the feed.

## Evidence weighting — actual overrules backtest

Live fills carry more information than simulated ones, so they weigh **2×**:

```
E_blend = (2·N_live·E_live + N_bt·E_bt) / (2·N_live + N_bt)
```

Two things this must not become:

- **A number that never moves.** Live samples are dozens of trades against
  thousands of backtest trades, so even at 2× the blend barely shifts early on.
  Report `N_live` next to every blended figure, or the weighting is decoration.
- **An average that hides a broken model.** When live *disagrees structurally* —
  slippage per venue, fill rates, latency — the backtest is not one noisy opinion
  to be averaged, it is **miscalibrated and must be re-run** with the measured
  values. That is what "actual overrules" means. The Phase 6 reconciliation layer
  already measures slippage in ticks per trade × venue, so this veto is instrumented;
  it just needs wiring into the metrics.

## Units — how pips and ticks are made comparable

Three different jobs, three different normalisations. Mixing them is how a
"9-tick gap" gets copied from NQ to GC and quietly means something else.

| Layer | Unit | Why |
|---|---|---|
| Signal geometry (gap size, stop, TP, trail) | **ATR multiples** (`--unit-mode ATR`) | Ticks are instrument-native and do not port. ATR self-scales to each instrument's volatility. |
| Trade outcome | **R** (risk multiples) | Every trade risks 1R by construction, so R compares across instruments and strategies. |
| Account / goal outcome | **DD-units** = % of that account's trailing-drawdown allowance | This is the prop-firm-native unit. Both goals are *defined* in it: an eval is "+target before -1.0 DD", funded survival is "never touch -1.0 DD". |

DD-units are the primary reporting unit. They make GC on a 50k Apex directly
comparable to 6E on a 100k FTMO, which dollars and percentages of balance do not.

## Open decisions (blocking)

1. **How far back does real per-bar `Delta` actually go?** Source is **Quantower**,
   so depth is set by the *connection* behind it, not by Quantower. Run
   `tools/validate_dataset.py` on a single pilot export — it prints the CVD
   boundary. That boundary is the research window. See `docs/data_export.md`.
   → *Needed from Ferry: which data connection/vendor.*
2. **Data hosting.** ~500 MB CSV per symbol per 15y: too large for git (100 MB/file
   hard limit) and for the LFS free tier. Proposed: Parquet+zstd (4-10× smaller,
   `validate_dataset.py --to-parquet`) published as **GitHub Release assets**,
   fetched per analysis. Requires a Parquet branch in `backtest/data.py` (not yet
   built).
3. **Continuous-contract stitching** — back-adjusted or raw-spliced? This strategy
   reads 3-bar fair-value gaps, and a raw roll gap can manufacture a signal that
   never traded. Roll dates, if exportable, let us mask instead of guess.
4. **BTC**: CME futures start Dec 2017 (max ~8.5y). Contract spec in `config.py:42`
   marked **verify** (BTC=5 vs MBT micro).
5. **FX futures multipliers** (`6E/6B/6J/6A/6S/6C`) marked **verify** in
   `config.py:44-49`. Both 4 and 5 resolve from Quantower's Symbol Info panel:
   tick size, tick value, multiplier, full-size vs micro.

## Settled

- **Micros**: not exported. Same price series as full-size; only the multiplier
  differs and it already lives in `config.py` `CONTRACTS`. CVD is read from the
  liquid full-size contract even when trading micros.
- **QQQ and other non-tradables**: not strategy datasets, but they *do* go through
  the mill as **context series** for correlation work (see below).
- **1-minute is the storage base.** `data.py:resample()` is session-aligned and
  sums `Delta`/`BuyVolume`/`SellVolume`; volume delta is additive, so every higher
  timeframe is derivable. Only intrabar ordering is lost — a short tick or 1s
  window would let us price the engine's pessimistic stop-first assumption.

## The fleet problem — why accounts liquidate together

Four accounts hitting liquidation at once is not four bad accounts, it is **one
position held four times**. `middleware/app/risk.py` gates per account
(`_halted` is a per-account, per-day set); nothing sees the portfolio. And the
funded edges are NQ/ES/GC — NQ and ES correlate around 0.9, so fanning one
strategy across them is leverage wearing the costume of diversification.

This makes correlation analysis (incl. the non-tradable context series) a
first-class part of Goal B, not a curiosity, and it means the Goal-B tooling must
model the **fleet**: N accounts, correlated returns, per-firm rules → distribution
of accounts alive at T, accounts reaching 6/6, and P(≥k simultaneous breaches).
`funnel.py` today models one account at a time.

## Infrastructure

Target and migration order in `docs/infrastructure.md`. Short version: only the
middleware, journal, dashboards and scheduled jobs need 24/7 — Quantower does not,
because the corpus is a monthly refresh, not live infrastructure. One VPS
(2-4 vCPU / 8 GB / 80 GB) runs everything; `middleware/deploy/setup.sh` already
provisions it in one command. Nothing has been created yet.

Before anything moves: `tools/inventory_local.py` over the local folders, so the
scattered `C:\` files get triaged rather than relocated.

## Skills

| Skill | Goal | State |
|---|---|---|
| `/eval-throughput` | A — pass evals fast | built; terminal report, dashboard pending |
| `/payout-throughput` | B — milk to 6/6 payouts | built; terminal report, dashboard pending |
| `/heatmap` | — | demoted to diagnostic; no longer a decision instrument |

Metrics live in `backtest/goals.py`, reachable as
`python3 -m backtest.run --goal {eval,payout}`. Both walk-forward via `funnel.py`;
both refuse a dataset that is not CVD-valid.

## Not started

- **The two dashboards** (one URL per goal) — waiting on real data so they can be
  verified against real output rather than synthetic.
- **The fleet model** — N accounts, correlated returns, per-firm rules,
  P(≥k simultaneous breaches). This is what answers the 4×-liquidation question;
  the per-account report explicitly does not.
- `recap` skill (fixed weekly format).
- Parquet reader in `backtest/data.py` (the loader is CSV-only).
- Wiring reconciliation's measured slippage into the metrics, so "live overrules"
  recalibrates rather than averages.
