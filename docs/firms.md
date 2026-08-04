# Prop-firm registry — generic, callable account rules

The strategy was hard-coded for **Apex futures**. `backtest/firms.py` pulls the
account rules out into a **data registry**: one entry per firm × program × size,
so the backtester runs *any* firm/asset by selecting a program instead of editing
the engine.

```bash
python -m backtest.run --data NQ_1m.csv --preset EL_MATADOR --firm apex_100k_eod
python -m backtest.run --data NQ_1m.csv --preset EL_TORO   --firm topstep_50k_eval
```

`--firm` overlays the firm's account rules (drawdown type, size, target, DLL,
consistency) and picks a default contract. The **signal** still comes from the
preset; only the **account overlay** comes from the firm. Validated: building the
Apex-50k-EOD program from the registry reproduces the hard-coded `EL_MATADOR`
pass-rate exactly (35.8%).

## Schema (`Program`)

`firm, key, asset_class, stage(eval|funded), account_size, profit_target,
max_daily_loss, drawdown, drawdown_type, trailing_locks_at, min_days,
consistency_pct, profit_split, activation_fee, payout_cadence, default_contract,
notes, source, as_of`.

`drawdown_type` ∈ `intraday_trailing | eod_trailing | static` decides execution.

## What runs today vs. what's data-only

| drawdown_type | firms (seed) | status |
|---|---|---|
| intraday_trailing / eod_trailing | **Apex**, **Topstep** (futures) | ✅ runs on the current overlay |
| static (fixed max-loss + daily) | **FTMO**, FundedNext (forex) | ✅ runs (FTMO/static overlay shipped; NQ-mechanics-validated, real FX needs FX data + lot sizing) |

The current `engine._account` models trailing-drawdown (Apex/Topstep) firms.
Static-drawdown firms (FTMO and most forex/CFD firms) are stored as data and map
to `phase="Research"` until the dedicated FTMO overlay (profit-target / max-daily
/ max-overall + challenge funnel) is built.

## Seed coverage (VERIFY — rules change)

- **Apex** — 25k–300k, eval + PA, both Intraday and EOD trailing. Profit targets
  ~6%, trailing DD per size, 50% consistency on the PA, 6-step payout ladder.
  Apex 4.0 (Mar 2026): no overnight, per-account payout cap.
- **Topstep** — 50k Combine: $3k target, $2k EOD trailing, optional $1k DLL, floor
  locks at start balance.
- **FTMO** — 50k / 100k challenges: 10% target, 5% daily, 10% **static** max loss.

## ⚠️ Honest caveats

- **These numbers are a seed, not gospel.** Prop-firm rules change often and vary
  by plan/promo. Every entry has a `source` and an `as_of`. **Confirm against the
  firm's rulebook before trading a real eval.** propfirmmatch.com blocked direct
  fetch (403); values were grounded via 2026 review sources (below) plus the
  well-known Apex model this project already validated.
- This is a **living file** — add firms/sizes and correct numbers freely; the
  engine consumes whatever is in the registry.
- The **funded** side is modelled for Apex (payout ladder); other firms' funded
  economics (splits, payout cadence, scaling) are captured as data but not all
  simulated yet.

## Extending it

Add a `Program(...)` to `_SEED` in `firms.py` with a unique `key`, the rule
numbers, a `source`, and `as_of`. Trailing-DD firms run immediately; static-DD
firms wait on the FTMO overlay. Send me a firm's rulebook (or the propfirmmatch
page text) and I'll add it accurately.

## Sources (2026, verify)
- https://propfirmmatch.com/ (comparison; blocked direct fetch)
- https://velotrade.com/blog/apex-trader-funding-review
- https://tradetanto.com/learn/apex-trader-funding-rules-what-you-need-to-know
- https://quantcrawler.com/learn/apex-trader-funding-rules
- https://phidiaspropfirm.com/education/apex-vs-topstep
- https://lunefi.com/blog/ftmo-an-in-depth-guide-rules-review-and-discount
- https://journalplus.co/compare/ftmo-vs-apex-trader-funding/

---

## Prepared for Pine (simple inputs)

The scripts will consume the registry through a **tiny** input surface — the
firm's rules resolve from one dropdown, so the user picks a firm, not 8 numbers.

Minimal inputs to add (group `L6 · Account`):
```pine
firmPreset = input.string("apex_50k_eod_eval", "Firm program",
     options=[ /* auto-generated from data/propfirms.json keys */ ])
// The generated pf library returns the rule set for the chosen preset:
[ddType, trailDD, goal, dll, consPct, acctSize] = pf.rules(firmPreset)
```
`ddType` → the existing `ddModel` path (`"Intraday"`/`"EOD"`), plus a new
`"static"` branch (the FTMO overlay). `trailDD/goal/dll/consPct` feed the account
inputs that already exist — so wiring is: replace the hand-typed account numbers
with `pf.rules(...)` outputs. Manual override inputs stay for edge cases.

The `pf` library + the `options=[...]` list are **auto-generated** from
`data/propfirms.json` by a small build script (planned, step 5) so Pine and the
backtester never diverge. Static-DD firms light up once the FTMO overlay ships.
