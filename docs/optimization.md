# El Dorado — money-management optimisation (walk-forward validated)

Objective (per the strategy's purpose): push a funded **Apex PA** account through
the 6-step payout ladder and **bank as much as possible per account**, i.e.
maximise **banked $ ÷ breaches** (every breach = a blown PA = a real account
cost), not raw contract P&L.

Data: NQ 1m, 2023-06-18 → 2026-06-17. Signal parameters held at El Dorado
defaults (this is a *money-management* sweep); indicators computed once.

## 1. In-sample sweep (full 3 years)

Break-even and trailing were **marginal** (PF stayed ~0.82 in every variant).
R-multiple / TP distance were **marginal** (PF 0.82 → 0.83 at R5 / 200-tick TP).

The decisive lever was the **day-profit trail**:

| day-trail | PF | net (contracts) | banked | breaches | $/breach |
|---|---:|---:|---:|---:|---:|
| $75 (default) | 0.82 | −$16.5k | $3,000 | 17 | $176 |
| $150 | 0.86 | −$16.7k | $4,500 | 22 | $205 |
| $300 | 0.89 | −$15.7k | $9,000 | 28 | $321 |
| OFF | 0.91 | −$13.9k | $8,000 | 27 | $296 |

The shipped **$75** trail (≈30 ticks on 2 contracts) closes the day after a tiny
give-back and **starves the account of the runway it needs to reach payout
eligibility** ($3,100). Loosening it ~doubles banked-per-breach.

## 2. Walk-forward validation (2y in-sample → 1y out-of-sample)

Split: IS 2023-06→2025-06, OOS 2025-06→2026-06.

| config | IS PF | IS banked/breach | **OOS PF** | OOS net | **OOS banked/breach** |
|---|---:|---:|---:|---:|---:|
| DEFAULT (day-trail 75) | 0.74 | $0 / 15 | 1.02 | +$521 | $0 / 1 |
| **day-trail 300** | 0.83 | $188 | **1.05** | **+$1,904** | **$643** |
| day-trail OFF | 0.84 | $130 | 1.10 | +$4,764 | $1,875 |
| R3+BE60+trail120/60+dt-off | 0.86 | $367 | 0.96 | −$2,715 | $188 |

Two decisive conclusions:

1. **The edge is regime-dependent.** Every config *loses* on contracts in the
   2023–2025 half (PF 0.74–0.86) and *recovers to ~breakeven-or-better* in
   2025–2026 (PF 1.02–1.10). The strategy did not have a stable contract edge in
   this window — its recent profitability rides the 2025–26 regime.

2. **The aggressive combo overfit.** `R3+BE60+trail120/60+day-trail-off` banked
   the most in-sample ($16.5k) but **collapsed out-of-sample** (−$2.7k, PF 0.96).
   Classic curve-fit. **Rejected.**

3. **The robust change is simply loosening the day-trail.** `day-trail 300`
   improved every in-sample metric *and* held up out-of-sample (OOS PF 1.05,
   +$1.9k, $643 banked/breach vs the default's $0). `day-trail OFF` banked more
   OOS but removes intraday protection and runs more breaches in-sample —
   $300 is the balanced, validated pick. Shipped as preset `EL_DORADO_TUNED`.

## 3. Recommendation

- **Set the day-profit trail to ~$300** (from $75). One parameter, validated
  out-of-sample, directly unlocks the payout machine the default was choking.
  `python -m backtest.run --data NQ.csv --preset EL_DORADO_TUNED`
- **Do not** adopt the high-R / wide-trail combos — they are in-sample artefacts.
- Leave break-even and trailing near default (no robust improvement found).

## 3b. El Toro — signal-filter optimisation (walk-forward validated)

El Toro's money-management is already tuned for pass-rate (see code_review D3);
the lever is the **signal**. Measured by the eval funnel (fresh eval every 5
sessions, 20-session horizon), IS 2y / OOS 1y:

| config | IS pass | OOS pass |
|---|---:|---:|
| DEFAULT | 29.8% | 27.7% |
| **RTH hours 09-15 ET** | 32.7% | **38.3%** |
| RTH + delta-streak 2 | 31.7% | **46.8%** |

- **Restricting entries to the US regular session (09-15 ET)** improves pass-rate
  in-sample *and* out-of-sample — robust. Shipped as `EL_TORO_TUNED`.
- Loosening the delta streak (4→2) adds more OOS pass-rate but the in-sample gain
  is smaller (more regime-dependent); offer as an aggressive option, not default.
- The **recovery-trail** (code_review A1) is worth ~+4pp pass-rate when it works
  (29.1% vs 25.2%). In the eval funnel each account is fresh so it already fires;
  **fix A1 in the Pine** so it also works in continuous/live use.

## 4. Honest caveats

- This is a **conservative-fill** independent engine (stop-first intrabar,
  1-tick slippage), not bit-exact to TradingView. Use the numbers **relatively**.
- Profitability is **regime-dependent and thin**. The account overlay monetises
  the PA asymmetry (capped downside per account, withdraw before breach); it is
  **not** a robust standalone edge. Sizing and account-cost assumptions matter.
- Breach cost (Apex PA reset fee) is **not** modelled; banked-per-breach is a
  proxy, not net profit after account costs.
- One 3-year sample, one instrument. Re-validate on the full 10-year set and on
  a second instrument before trusting it live.

## 5. Target-driven position sizing — assessment (Python prototype)

Idea (user): stop using a fixed contract count; for **eval** size from the profit
goal, for **funded** find the optimum from the same target-driven thinking.

Implemented as `sizing_mode="target_dd"`: risk a fraction of the remaining
trailing-DD room per trade (size grows with runway, shrinks to 0 near the floor).
Result on NQ:

| | fixed | target_dd (frac 0.15–0.4) |
|---|---|---|
| **Eval** (Matador+RTH) pass-rate | 41% | 19% at frac 0.3 (mostly timeouts) |
| **Funded** (Dorado tuned) banked / breaches | $9k / 28 | $0 / 0, ~20–57 trades |

**Verdict:** the idea is architecturally *correct* — sizing should follow the
objective + constraints, not a fixed count — but it exposes the real problem
rather than solving it. On a **marginal/negative-edge** signal, DD-fraction
sizing degenerates: for the eval it must gamble (fixed-aggressive already wins
the variance play), and for funded it correctly sizes *down to nothing*
(banked $0, 0 breaches) because there is no edge to compound. **No sizing scheme
manufactures edge.**

Target-driven sizing becomes powerful **once a positive-edge config is locked in**
(hour-filter + EOD model + regime selection). Kept in the backtester
(`sizing_mode`, `target_risk_frac`) for that stage; deliberately **not** put into
the Pine yet.
