# Prop-firm & platform layer — research + design proposal

Goal: model **all** prop firms, asset classes, account sizes and rules **once**,
in a single source of truth that the backtester, a Pine library, and the future
alert middleware all consume — so we never re-do this per script. Plus: let Claude
**monitor** firms for rule changes/new firms, and design the **one-alert →
many-platforms** fan-out.

> This is a proposal (research + design). Nothing here is built yet beyond the
> existing `firms.py` prototype. Decide the schema first; then we fill + wire it.

---

## Part A — The landscape (2026)

### A1. Futures firms (CME/CBOT/COMEX/NYMEX + micros)
| Firm | Eval | Drawdown | DLL | Notable | Platforms |
|---|---|---|---|---|---|
| **Apex** | 1-step | intraday **or** EOD trailing | none (newer plans add) | 25k–300k, 100% first $25k, payout cap (4.0) | Rithmic, Tradovate, Quantower, NT |
| **Topstep** | 1-step (Combine) | **EOD** trailing, locks at start | optional $1k | 12+ yr, weekly payouts, 90/10 | Rithmic, Tradovate, Quantower |
| **MyFundedFutures** | 1-step / instant | EOD trailing | **none** in eval | no fees, ~1-min payouts | Rithmic, Tradovate, ProjectX |
| **Take Profit Trader** | 1-step | EOD trailing | daily | CME/CBOT/COMEX/NYMEX + micros | 50+ platforms |
| **Tradeify** | instant / 1-step | EOD trailing | daily | instant funding, 90% | Tradovate, others |
| **Bulenox / Legends / Elite Trader Funding** | 1-step | trailing | varies | (verify — some sites unverified) | Rithmic/Tradovate |

### A2. Forex / CFD firms (FX, metals, indices, crypto CFDs)
| Firm | Eval | Drawdown | DLL | Split | Notable |
|---|---|---|---|---|---|
| **FTMO** | 2-step (10%/5%) | **static** 10% overall | 5% | 80→90% | fee refunded on 1st payout |
| **FundedNext** | 2-step (8%/5%) | static 10% | 5% | up to 90% | **15% profit share during eval** |
| **The5ers** | bootcamp/hyper-growth | static ~5% | varies | to 100% | scaling to ~$4M |
| **FundingPips** | 1/2-step | static 10% | 5% | up to 95% | consistency-gated split |
| **E8 / Alpha Capital / Blueberry / …** | 1/2-step | static 10% | 5% | to 100% | MT4/5, cTrader, DXtrade, Match-Trader, TradeLocker |

**The big split:** futures firms = **trailing** drawdown (intraday/EOD), sized in
**contracts**, executed via **Rithmic/Tradovate/Quantower**. Forex/CFD firms =
**static** drawdown (fixed % max-loss + daily), sized in **lots/%risk**, executed
via **MT4/5/cTrader**. Our engine currently models trailing; static is the gap.

---

## Part B — The rule dimensions (the schema to design once)

Every field that varies across firms/programs — the registry must carry all of
these (even if unused today) so we don't re-migrate:

**Identity:** firm, program key, display name, asset_class, region eligibility,
currency, as_of, source, status (active/paused/shutdown).

**Structure:** stage (eval/funded/instant), eval_steps (1/2/instant),
account_size, price (fee), refundable_fee, reset_price.

**Targets & limits (per step):** profit_target (% or $), max_daily_loss (% or $ /
none), max_overall_loss (% or $), drawdown_type (static | eod_trailing |
intraday_trailing | scaling), trailing_locks_at, balance_vs_equity basis for each.

**Trading rules:** min_trading_days, max_trading_days, consistency_rule
(type + %), overnight_allowed, weekend_allowed, news_trading_allowed,
max_position (contracts/lots), max_lot_per_symbol, scaling_plan.

**Funded economics:** profit_split (+ scaling schedule), payout_cadence,
first_payout_wait, min_payout, payout_cap, in_eval_profit_share (FundedNext),
activation_fee.

**Execution mapping:** platforms[], data_feed, symbol_map (firm/broker symbol per
canonical asset), sizing_unit (contracts | lots | pct_risk), point/tick specifics
(→ links to the existing `CONTRACTS` registry).

---

## Part C — Architecture: one source, three consumers

```
            data/propfirms.json   ← SINGLE SOURCE OF TRUTH (versioned, in git)
                   │
      ┌────────────┼───────────────────────────┐
      ▼            ▼                             ▼
 backtest/firms.py   generated Pine library     middleware (future)
 (loads JSON)        (auto-generated presets)    (rule-enforce + route)
```

1. **`data/propfirms.json`** — the registry as data (not Python), strict schema
   from Part B, one record per firm×program×size, each with `source`/`as_of`/
   `status`. `firms.py` becomes a thin loader over it.
2. **Pine library** — **yes, this works.** A Pine `library()` can't hold the full
   dataset, but it *can* export a compact preset table (firm/size → the handful of
   numeric rules the script needs: dd type, dd amount, target, DLL, consistency).
   We **auto-generate** the `.pine` library from the JSON with a small script, so
   Pine and Python never diverge. The strategy then does
   `import <you>/PropFirms/1 as pf` and `pf.rules("apex_50k_eod")`.
3. **Middleware** — reads the same JSON to enforce rules per account and to map
   canonical signals → each platform's symbol/sizing (Part E).

Single source → edit once → backtester, Pine, and middleware all update.

---

## Part D — Claude monitoring (rule-change watch)

A scheduled **Claude Routine** (I can set this up) that runs, say, weekly:
1. For each firm in the registry, fetch its rulebook / a comparison source.
2. Diff the live rules against `data/propfirms.json`.
3. On any change (rule edit, firm paused/shutdown, new firm), open a PR updating
   the JSON (bumping `as_of`, appending to a changelog) and ping you.

This keeps the single source current automatically. It matters doubly once the
middleware enforces these rules live — a stale max-loss could blow a real account.
(Caveat: many firm sites block scraping — the watch will lean on comparison
aggregators + the firm rulebooks it *can* read, and flag what it couldn't verify.)

---

## Part E — One alert → many platforms (the middleware end-state)

The reason to centralise now. Design:

```
strategy signal ──► TradeIntent (canonical)
                     { asset, side, size_intent, sl, tp, account_ref, tag }
                          │
                          ├─ rule gate (from propfirms.json: DLL/DD/news/session)
                          │
                          └─► fan-out adapters (per subscribed platform+account):
                                Tradovate   → contracts + bracket
                                Rithmic     → contracts + bracket
                                MT4/5       → PineConnector / EA (lots or %risk)
                                Quantower   → contracts
                                Discord     → human-readable embed
                                Telegram    → human-readable message
```

- **One canonical TradeIntent**, N adapters. Each adapter translates size
  (contracts ↔ lots ↔ %risk) and symbol (canonical ↔ platform symbol) using the
  registry's `symbol_map` + `sizing_unit` + the `CONTRACTS` specs.
- **Rule gate** uses `propfirms.json` to block/allow per account (session,
  overnight, DLL room, DD room, consistency) — the same rules the backtester used,
  now enforced live. This is exactly why the registry must be the single source.
- Fits the existing scripts: today they emit one alert string per destination;
  the middleware replaces per-destination strings with one TradeIntent it fans out
  — so the Pine side gets *simpler* (emit intent, not N payloads).

---

## Part F — Proposed plan (so we don't redo work)

1. **Lock the schema** (Part B) — one review pass with you.
2. **Externalise** `firms.py` → `data/propfirms.json` + thin loader.
3. **Populate + verify** the seed firms (Apex/Topstep/MFFU/TPT futures; FTMO/
   FundedNext/The5ers/FundingPips forex), each sourced. I draft; you sanity-check
   a few.
4. **Build the static/FTMO overlay** in the engine → unlocks all forex/CFD firms
   at once.
5. **Generate the Pine library** from the JSON (auto-gen script).
6. **Set up the Claude monitoring Routine**.
7. Middleware TradeIntent + adapters — later, when you move off PineConnector.

Doing 1–2 first is what prevents rework: every later piece reads the same JSON.

---

## Sources (2026 — verify; rules change)
- Futures: [velotrade](https://velotrade.com/blog/best-prop-firm-for-futures),
  [phidias](https://phidiaspropfirm.com/education/best-futures-prop-firms),
  [quantcrawler](https://quantcrawler.com/learn/futures-prop-firms),
  [futuresproptrading](https://futuresproptrading.com/top-10-best-futures-prop-trading-firms/)
- Forex/CFD: [tradezella](https://www.tradezella.com/blog/best-prop-firms-2026-rankings),
  [track360](https://track360.io/blog/best-prop-trading-firms-2026-operator-trader-guide),
  [fundednext](https://fundednext.com/blog/highest-paying-prop-trading-firms),
  [completetradersedge](https://completetradersedge.com/ftmo-vs-fundednext-vs-fundingpips/)
- Aggregator: https://propfirmmatch.com/ (blocked direct fetch; use in-browser)
