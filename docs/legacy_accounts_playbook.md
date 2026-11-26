# Legacy accounts playbook — 3×250k + 1×300k (Apex pre-4.0)

Validated on your uploaded NQ/ES/GC/YM 1m data (2022-2026), conservative-fill
engine, CVD/delta OFF (the exports carry no order-flow; delta adds no edge and
GC's edge was validated without it). Numbers are relative, single-sample —
re-validate before trading real size.

## TL;DR

| Asset | Role | Script (eval / funded) | Edge (research PF) |
|---|---|---|---|
| **ES** | **EVAL vehicle** | El León / El Rey | **1.09** (H1 1.15 / H2 1.07) ✅ |
| **GC** | **FUNDED workhorse** | El Minero / El Tesoro | **1.06** (H1 1.22 / H2 1.03) ✅ |
| NQ | gamble-only | El Toro / El Dorado | 0.96 — edgeless |
| YM | skip | — | 0.92 |

**Key idea:** Apex accounts aren't instrument-locked — **pass the eval on ES**
(positive edge, lowest breach), **harvest funded on GC** (best banked/breach).

**Realized income:** ~**$53k/yr** for the fleet (churn-adjusted, best funded
sizing). Fees are marginal (break-even ≈ $2-3k banked per breach vs a few-hundred
refund).

---

## Exact settings (TradingView / Pine inputs)

**Common to every script:**
- Unit mode: **Ticks**
- Stop: **fixed 100 ticks** (Swing-structure stop **OFF**)
- Take-profit: **R-multiple**
- CVD / delta filter: **OFF**, CVD streak **OFF**
- Event filter (roll/OpEx/news): **Auto** (per-script validated default)
- Day-exit: **Off** on eval; funded see below

### ES — El León (eval) & El Rey (funded)   [ES = $12.50/tick]
| Input | Value |
|---|---|
| FVG band (min–max) | **9 – 15 ticks** (do not widen — 9-15 is ES's optimum) |
| Confirmation window | **2 bars** |
| VWAP veto | **OFF** |
| Fixed stop | 100 ticks | 
| TP R-multiple | **1.5** (eval and funded) |
| Contract size (eval) | **2–3** |

### GC — El Minero (eval) & El Tesoro (funded)   [GC = $10/tick]
| Input | Value |
|---|---|
| FVG band (min–max) | **9 – 18 ticks** (RECOVERED — wider than the old 6-12; this is the edge) |
| Confirmation window | **0 bars** |
| VWAP veto | **ON** |
| Fixed stop | 100 ticks |
| TP R-multiple | **1.5 eval / 2.5 funded** |
| Contract size (funded) | **250k → 2 ct, 300k → 3 ct** (nominal; MAE-guard scales up as you bank) |

### NQ — El Toro (only if you want a one-shot gamble)   [NQ = $5/tick]
- Hours: **RTH 09:00–15:59 ET**, FVG 9-15, one-shot size **~13-18 ct**.
- Edgeless (PF 0.96) — accept it's pure variance; not for reliable funding.

### Funded PA money-management (El Tesoro / El Rey / El Dorado)
| Input | Value |
|---|---|
| Day-profit trail | **$300** (validated; NOT the $75 default) |
| MAE guard | **ON** (auto-scales size with banked profit — this is the flywheel) |
| Wait-for-cap | **ON** (capped-ladder discipline banks more per breach than max withdrawals) |
| Breakeven / trail | per El Dorado defaults |

---

## Account overlays (Apex legacy pre-4.0, intraday trailing)

| Account | Profit target | Trailing DD | dd_model | Consistency | DLL |
|---|---|---|---|---|---|
| 250k | $15,000 | $6,500 | Intraday | 50% | none (legacy) |
| 300k | $20,000 | $7,500 | Intraday | 50% | none (legacy) |

Overnight/news holding **allowed** (legacy). No per-account payout cap (legacy).

---

## Fleet inrichting

**Eval phase** (decorrelate — don't all trade the same bar):
| Account | Eval asset | Size | Why |
|---|---|---|---|
| 250k-A | ES | 2-3 ct | best edge, lowest breach |
| 250k-B | ES | 2-3 ct | staggered start |
| 250k-C | GC | 2-3 ct | decorrelate from ES |
| 300k | ES | 2-3 ct | hardest account → safest asset |

**Funded phase** (once passed — flip all to GC): El Tesoro, 250k → 2 ct, 300k → 3 ct,
capped/wait-for-cap. All fund from one GC alert.

**Realized income (churn-adjusted, best sizing):** 250k ≈ $13.4k/yr each · 300k ≈ $12.8k/yr →
**fleet ≈ $53k/yr**. Uptime 63% (250k) / 48% (300k) — the rest is re-qualifying after breaches.

### middleware `accounts.yaml`
```yaml
strategies:
  ES:                        # El León eval alert -> accounts still in eval
    accounts: [apex_250k_a, apex_250k_b, apex_300k]
  GC:                        # El Minero (eval) + El Tesoro (funded) both tag "GC"
    accounts: [apex_250k_c]              # + each account once it is funded
accounts:
  apex_250k_a: {broker: pmt_tradovate, account_id: "APEX-…", quantity_multiplier: 2}
  apex_250k_b: {broker: pmt_tradovate, account_id: "APEX-…", quantity_multiplier: 3}
  apex_250k_c: {broker: pmt_tradovate, account_id: "APEX-…", quantity_multiplier: 2}
  apex_300k:   {broker: pmt_tradovate, account_id: "APEX-…", quantity_multiplier: 2}
```
On passing, move an account from the `ES` list to the `GC` list (now El Tesoro funded).

---

## The three layers that carry the income (in order)
1. **Propfirm asymmetry** — banked/breach ($2-4k) ≫ refund cost; this makes it net positive, not the signal.
2. **Uptime / survival** — keeping accounts funded (right size) beats banking big.
3. **Market edge** — thin (ES 1.09, GC 1.06); it supplies the banked, but is the most fragile layer.

## Reproduce (tools/)
```
python tools/normalize_upload.py                 # raw exports -> *_norm.csv
python tools/edge_sweep.py ES|GC|NQ|YM           # split-half signal sweep
python tools/legacy_accounts_analysis.py ES GC   # eval funnel (pass/breach) x size
python tools/funded_flywheel_sim.py GC ES        # funded banked/breach x size x model
python tools/net_income_model.py                 # net €/yr x fee scenario
python tools/churn_throughput_model.py           # churn/uptime-adjusted realized €/yr
```

## Caveats
- Reconstructed edges (GC 1.06, ES 1.09) are conservative-fill, single-sample, delta-off.
  The documented GC winner was ~1.13 on other data — treat these as a validated floor, not a ceiling.
- Churn model assumes re-fund after each funded breach; uptime is the dominant real-world haircut.
- Verify Apex legacy rules (instrument freedom, ladder caps, consistency %) against your own dashboard.
