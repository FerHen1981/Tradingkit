# Code review — MEX ΞL TORO v6.8.7 & ΞL DORΛDO v6.8.12

Scope: the two Pine v6 scripts, reviewed line-by-line against a faithful Python
re-implementation (`backtest/`) that was run on 3 years of NQ 1-minute data.
Line numbers refer to the original `.pine` files.

The two scripts are the **same engine**; they differ only in default inputs and
account phase (Toro = Apex Eval, Dorado = Apex PA). Findings below apply to both
unless noted.

---

## A. Correctness / latent bugs

### A1. Recovery-trail is effectively dead in the shipped presets  🟠
`useRecovTrail` (Eval-only) gates on `attemptTradeNo == 1 and attemptFirstLoss`
(Toro L1194/L1217). Those counters increment on every closed trade
(L1106–1108) but are **only reset inside the `evalTrack` block** (L1344/1350),
which is **off by default** — the presets drive the account through the
`accountPhase` phase-layer instead, which never resets them.

Consequence: `attemptTradeNo == 1` is true only during the **2nd trade of the
entire run**; after that the recovery-trail can never arm again. The feature is
inert in backtest and live for the shipped El Toro config. (Confirmed: it never
appears in exit reasons in the re-implementation.)

*Fix:* reset `attemptTradeNo`/`attemptFirstLoss` when a new eval attempt begins
in the phase layer too (on `acctHalted`/PA reset / first bar of a fresh attempt),
not only inside `evalTrack`.

### A2. `attemptTradeNo` never resets per trading day either  🟡
Even ignoring A1, "trade #2 after a first-trade loss" reads as a *per-attempt*
or *per-day* notion in the tooltip, but the counter is monotonic across the
whole backtest. Decide the intended scope (per eval attempt vs per day) and reset
accordingly; today it is neither.

### A3. `useGoalTp` clamp can produce sub-tick targets  🟡
`f_tpFixDist` (Dorado L859) shrinks the fixed TP so the trade *just* reaches the
eval goal, then `math.max(_d, 4*mintick)`. Only active with `useGoalTp` (off in
presets), but if enabled with tiny remaining goal it forces 4-tick TPs that will
mostly be eaten by commission+slippage. Guard with a minimum R, not a minimum
tick count.

---

## B. Repaint / look-ahead

### B1. Bias filter uses `lookahead_on` (disabled by default) — keep it off  🟡
`request.security(..., lookahead=barmerge.lookahead_on)` (L540/553) is fed
`[close[1], highest[..][2], lowest[..][2]]`, i.e. the offsets are meant to
neutralise the look-ahead. This is correct **only** as written; if anyone edits
those offsets while `useBiasFilter` is on, it will silently repaint. Since
`useBiasFilter=false` in both presets it's inert, but it's a foot-gun. Prefer
`lookahead_off` with explicit `[1]` offsets.

### B2. Everything else is repaint-safe  🟢
FVG uses confirmed bars (`barstate.isconfirmed`), pivots are confirmed `k` bars
late (`ta.pivotlow/high(_, k, k)` + `fixnan`), the delta streak and VWAP veto use
closed-bar values. No intrabar signal recomputation (`calc_on_every_tick=false`).
Good.

---

## C. Apex-rule modelling accuracy

### C1. Intraday trailing-DD ratchets on *unrealised* peak — very punishing  🟠
`ddModel="Intraday"` (both presets) trails `acctHwm` on `acctPnL` which includes
`strategy.openprofit` (L650/663). A trade that runs to large open profit and
reverses to its stop can breach even though realised P&L never approached the
limit. The re-implementation shows this directly: El Toro (5 contracts,
$25/tick) blows a fresh eval on a **single** trade that goes to ~+$1,750 open
then reverses. This faithfully matches Apex's real intraday trailing threshold,
but it means **the drawdown model, not the signal, dominates El Toro's
outcome.** See D2 for the implication.

### C2. `paBacktestMode` reset rebases on realised, not on breach equity  🟡
On a PA breach (L680–688) `paResetPnLPrev := strategy.netprofit` (realised),
while the breach test used `acctPnL` (incl. open). If a position is open at the
breach instant, the overlay resets but the position is **not** force-closed —
the trade keeps running on the "new" account. Defensible as a model, but the
banked/breach accounting is slightly optimistic on the breach bar. Document or
close-on-breach for cleaner books.

### C3. Consistency rule is checked but qualifying-day gate is coarse  🟡
`consistencyOK = bestDaySince/profitSince < consistencyPct/100` and `qualDays>=5`
gate payouts. Correct in spirit, but `profitSince`/`bestDaySince` accrue only on
**new trading day** using yesterday's realised delta (L606–611); an open trade
spanning midnight is attributed to the wrong day. Minor at 1m, worth noting.

---

## D. Money-management observations (from the backtest)

### D1. El Dorado exits invert the R:R  🟠
Native PA over 3y: win 54–62% but **PF 0.82**, avgWin ≈ $172 vs avgLoss ≈ $392.
Break-even (20 ticks) and the trail cut winners to ~scratch while losers pay the
full swing stop. A high win-rate with PF<1 is the classic "cut winners, keep
losers" signature. This is the single biggest money-management lever (sweep in
progress).

### D2. Day-trail at $75 closes days extremely early  🟠
`dayExitMode="Day-trail (keep peak)"`, `dayTrailUSD=75` with 2 contracts = a
**30-tick** give-back ends the whole trading day. In the run, `Day-trail` is the
2nd-most-common exit (223 of 811). It caps upside hard and likely suppresses the
compounding needed to clear a payout ladder. Prime candidate to widen or disable.

### D3. El Toro money-management is already near-optimal *for pass-rate*  🟢
Counter-intuitively, adding break-even / trailing or cutting size **lowers**
El Toro's eval pass-rate (29% → 22% at 2 ct; 14% at 1 ct), because a negative-
edge signal must reach +$3,000 in as few trades as possible before the trailing
DD catches it. The aggressive default is correct for the "gun the eval"
objective; the only real lever for El Toro is the **signal edge** itself.

---

## E. Highest-value optimisation targets

| script | lever | rationale |
|---|---|---|
| El Dorado | day-trail $ (D2) | tight $75 caps daily upside |
| El Dorado | BE trigger / trail start (D1) | winners cut to scratch |
| El Dorado | R-multiple / TP (D1) | avgWin << avgLoss |
| El Toro | signal filters (D3) | MM already tuned; edge is the lever |
| both | fix recovery-trail reset (A1) | dead feature today |

All optimisation must be **walk-forward validated** (tune on an in-sample slice,
confirm out-of-sample) — the 3-year sample is one regime and these are ~40-input
strategies with ample room to overfit.
