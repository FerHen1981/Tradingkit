# EL TESORO Multi-Market Research Pipeline

## Purpose
A repeatable research protocol for taking one futures market from raw 1-minute data to a Pine/TradingView-validated PA strategy, then comparing it with other markets for portfolio diversification.

## Core business objective
Do **not** optimize for headline net profit or nominal win rate.
Primary objective:

**Maximize banked payout dollars per occupied PA account-day (time-for-money)**

subject to:
- positive intrinsic strategy edge after costs;
- realistic Pine/TradingView execution parity;
- prop-firm drawdown/DLL/payout rules;
- acceptable breach/churn rate;
- robustness across time and regimes;
- minimal overfitting.

## Anti-overfit principles
1. Do not optimize arbitrary Hour-of-Day or Day-of-Week combinations as primary filters.
2. Hour/day may be used diagnostically after the fact.
3. Market-regime windows are allowed only when economically defined in advance (Asia, London, pre-cash, cash open, opening range, post-OR, lunch, power hour, settlement/rollover).
4. Prefer simple parameter plateaus over a single sharp optimum.
5. Do not reward nominal win rate. Track meaningful winners after costs and flag BE/scratch wins.
6. Avoid adding filters unless they improve out-of-sample / walk-forward behavior or payout economics.

## Stage 0 - Data audit
For each instrument:
- verify date coverage and timezone;
- normalize decimal formats;
- verify OHLC continuity and missing bars;
- inspect volume/tick coverage;
- inspect native Delta/CVD coverage;
- confirm tick size, point value, commission and slippage assumptions;
- identify contract/session roll artifacts.

Output: data-quality report and normalized research dataset.

## Stage 1 - Pine parity engine
Reproduce the Pine strategy semantics before optimizing:
- FVG is detected only on confirmed bars;
- midpoint limit order becomes fillable only after the signal bar;
- pending order replacement and expiry follow Pine state logic;
- historical fills are pessimistic where intrabar order is ambiguous;
- existing stop/target is processed before new BE/trail updates on a bar;
- BE/trail updates become effective only after Pine has processed the bar;
- commissions and slippage match Pine;
- flat window and session gate match Pine.

### CVD
Maintain two separate concepts:
1. **Pine-parity CVD**: reconstruct the same directional lower-timeframe volume logic Pine/TradingView can reproduce.
2. **Native tick delta**: use the supplied bid/ask/tick delta only as a diagnostic/research factor unless an exact Pine implementation exists.

Never mix the two silently.

## Stage 2 - Structural edge, from scratch
Do not seed another market with MGC's optimum.
Search broadly on:
- LONG/SHORT both enabled initially;
- FVG size/range;
- CVD streak/threshold;
- VWAP veto if part of base architecture;
- SL;
- R/TP;
- BE OFF vs late BE;
- trail OFF vs late trail.

Initial score should emphasize:
- PF after costs;
- average trade expectancy;
- meaningful win rate;
- MFE/MAE distribution;
- max drawdown/tail losses;
- trade count and temporal distribution.

Do not introduce PA sizing/daily caps until a positive intrinsic edge exists.

## Stage 3 - Market-regime diagnostics
With structural settings approximately stable, evaluate fixed regimes:
- Asia;
- London open;
- pre-cash;
- cash open;
- OR30 / OR60;
- post-OR;
- lunch;
- power hour;
- settlement/close;
- Globex reopen / rollover.

For every regime report:
- IN performance;
- OUT performance;
- ALL baseline;
- PF, expectancy, MFE/MAE, full-stop frequency and trade count.

Only turn a regime into a filter if the economic effect is robust and explainable.

## Stage 4 - Local robustness / plateau search
Around the best structural families:
- tighten the grid around SL, R, FVG and CVD;
- compare neighboring settings;
- prefer a broad plateau to a sharp maximum;
- split by year/quarter and rolling windows;
- verify LONG/SHORT separately without automatically disabling one side.

## Stage 5 - Contract size and pro-rata risk
Sweep contract size independently for the instrument.
Consider both:
- fixed dollar account constraints;
- pro-rata comparable stop exposure.

Do not assume more contracts improve the edge; size should change payout throughput/risk, not intrinsic PF in an unconstrained model.

Track:
- full-stop dollar risk;
- DLL interaction;
- max drawdown;
- payout speed;
- breach rate;
- banked dollars per account-day.

## Stage 6 - Daily profit/loss management
Only after the trade engine is stable, sweep:
- strategy DLL (if useful beyond firm DLL);
- daily profit activation;
- giveback amount;
- hard daily cap;
- max trades/day / stop-after-loss / stop-after-win only if justified.

Daily controls must be judged on payout economics, not cosmetic equity smoothing.

## Stage 7 - PA lifecycle models
Run at least:
- Apex 50K EOD PA;
- Apex 50K Intraday PA.

Model:
- drawdown floor/HWM;
- tier-based DLL;
- qualifying-day requirement;
- consistency rule;
- payout safety net/min balance;
- payout ladder;
- up to six payouts;
- account breach and replacement.

For Intraday PA, explicitly model unrealized MFE raising the trailing HWM. If exact tick sequence is unavailable, use a pessimistic ordering and label the result as conservative.

## Stage 8 - Time-for-money objective
Primary KPI:

**Banked payout $ / occupied account-day**

Also report:
- payout #1 conversion;
- P2-P6 completion;
- average payouts/account;
- days to P1;
- later payout intervals;
- breach before P1;
- total breach rate;
- banked $ before breach;
- qualifying-day cadence;
- consistency utilization;
- DLL hits;
- time to Intraday threshold lock.

If funded replacements are readily available, do not overvalue account longevity for its own sake.

## Stage 9 - Production vs Harvest variants
Normally retain two candidates:

### Production / Quality
Higher intrinsic PF/expectancy, lower churn, fewer but better trades.

### Harvest / Aggressive
Higher trade/payout throughput, accepts more PA churn if banked $/account-day is superior.

Neither variant may rely on arbitrary hour/day cherry-picking.

## Stage 10 - TradingView validation
Before blind PA deployment:
1. generate full Pine variants without deleting alerts/routing/account logic;
2. set explicit defaults/presets;
3. run TradingView exports over the same period;
4. compare trade count, entry timestamps, exit reasons, P&L, MFE/MAE and PF against the external simulator;
5. investigate the first divergent trades rather than re-optimizing immediately.

A simulator result is not accepted if TradingView materially disagrees.

## Stage 11 - Multi-market portfolio diversification
After each market has independently passed the above funnel:
- compare daily P&L correlation;
- compare losing-day and breach-day overlap;
- compare event/regime sensitivity;
- optimize account allocation across markets for banked payout $ and reduced simultaneous breach risk.

The best portfolio is not necessarily the collection of individually highest-PF strategies.

## Standard deliverables per market
1. Data audit.
2. Structural edge table.
3. MFE/MAE analysis.
4. Regime IN/OUT report.
5. Robustness/plateau table.
6. Contract-size sweep.
7. Daily-risk sweep.
8. EOD PA lifecycle.
9. Intraday PA lifecycle.
10. Production and Harvest Pine files.
11. TradingView calibration report.
12. Portfolio correlation/breach-overlap contribution.

## Current research lesson summary
- Pine parity before optimization.
- CVD5/6-style conclusions are instrument-specific; never transfer them blindly.
- FVG ranges are instrument-specific; never transfer MGC tick ranges blindly.
- Early BE can inflate win rate while destroying economic expectancy.
- Daily profit protection can be a core monetization mechanism, especially on Intraday trailing accounts.
- Contract size and SL must be evaluated together.
- Time-for-money and banked payouts are more relevant than maximum strategy equity.
- Account mechanics can reverse the ranking of otherwise identical trade engines.



## Hard parity rule — intrabar fill leakage is forbidden

For any limit/stop entry filled inside an OHLC bar, the research engine must **not** reuse the full High/Low of that same bar as if all of it occurred after the fill.

Mandatory conservative handling:
- If exact lower-timeframe/tick ordering is unavailable, do not award a same-bar target after an intrabar limit fill merely because the bar High/Low crossed both levels.
- Prefer one of:
  1. lower-timeframe/tick replay;
  2. deterministic broker-emulator path matching Pine;
  3. pessimistic no-exit-on-fill-bar assumption for research validation.
- Round entry, stop and target to valid `syminfo.mintick` prices before execution.
- Apply slippage and commissions at the same semantic level as Pine/TradingView (per side vs round-turn must be explicit).
- Force-flat windows must close existing positions in the simulator if Pine uses `strategy.close_all()`.
- Prop-account interventions (DLL, intraday HWM, cap-lock) are applied only after strategy-level Pine parity is proven.

### Fast-strategy robustness rule
For strategies with very short holding times, tight stops/targets, high trade frequency, or small net edge per trade, the optimizer must penalize:
- excessive same-bar exits;
- edge that disappears after +1 tick extra slippage;
- edge dominated by transaction costs;
- payoff ratios that require unrealistically precise fills.

A fast strategy is not accepted as Production/Harvest unless it remains profitable under:
- baseline TradingView slippage/fees;
- +1 tick adverse slippage sensitivity;
- and a conservative intrabar execution model.

### Pine-first calibration gate
Before optimizing a new market:
1. choose one fixed baseline;
2. compare Python vs Pine on the same period;
3. require near-parity in trade count and materially similar win-rate/PF;
4. if not, debug engine semantics before any new parameter search.

Parameter optimization is invalid while baseline execution parity is unresolved.



## Trading-day boundary parity

Prop-firm and Pine research must use the actual trading-day boundary, not calendar midnight.

For CME/Apex futures:
- Daily Loss Limit resets at 18:00 ET.
- Daily P&L, qualifying-day counts, consistency days, daily caps/trails and payout lifecycle must be grouped by the 18:00 ET session boundary.
- A bar at or after 18:00 ET belongs to the next trading session/day for lifecycle accounting.
- Calendar-date grouping is invalid for PA lifecycle analysis unless the firm explicitly defines it that way.

## Research invalidation rule

If a material execution/parity flaw is discovered after optimization (for example same-bar fill leakage, wrong tick/unit semantics, wrong commission semantics, or wrong trading-day grouping):
- all parameter rankings generated under that flaw are invalidated;
- they may be retained only as research history;
- the market must restart from a neutral search space after the engine is corrected;
- old winners must not be used as priors in the restarted optimization.



## Reconstructed OHLCV Delta/CVD proxy — canonical multi-market research version

When native bid/ask Delta is incomplete over the historical sample, the default full-history research CVD is a deterministic 1-minute OHLCV price-polarity proxy. It is independent of `ta.requestVolumeDelta()` and independent of the CSV native Delta column.

Per 1-minute bar:
1. if `close > open`: direction = +1;
2. if `close < open`: direction = -1;
3. if doji and `close > previous close`: direction = +1;
4. if doji and `close < previous close`: direction = -1;
5. if still unresolved: carry previous polarity.

CVD streak N means N consecutive proxy-direction bars in the FVG trade direction.

Research requirements:
- This proxy must be implemented identically in Python/.NET and Pine before calling it parity.
- Native bid/ask Delta and `ta.requestVolumeDelta()` are separate experimental factors and must not silently replace this proxy.
- CVD threshold must be re-optimized independently per market.
- A CVD filter is accepted only if it produces a broad threshold plateau and remains robust across time segments, LONG/SHORT and adverse-slippage stress.

## MES scratch/CVD lessons learned — 2026-08

### 1. Preserve the canonical synthetic CVD layer
- Do not discard CVD merely because native historical bid/ask Delta is incomplete.
- The canonical full-history research layer is the deterministic OHLCV price-polarity proxy defined above, not the CSV Delta column and not `requestVolumeDelta()`.
- Treat native Delta / lower-TF volume Delta as separate experiments; never silently substitute them for the canonical proxy.

### 2. Re-run the search when an information layer was omitted
- A pre-CVD optimum is only a pre-CVD candidate once CVD is known to be part of the canonical strategy family.
- Adding a material information layer requires reopening FVG, stop, R and expiry jointly rather than testing CVD only on the old winner.
- MES demonstrated why: the ranking changed materially after CVD became a first-class axis.

### 3. Prefer threshold plateaus over one best CVD value
- Search neighboring CVD thresholds and require robustness across them.
- MES produced a CVD4–6 quality plateau; CVD6 was the strongest/broadest quality zone while CVD4 supported higher throughput.
- A single high-PF CVD threshold without neighboring support is not sufficient for production selection.

### 4. Higher R can become viable after quality filtering
- Do not assume the pre-filter optimal R remains optimal after CVD filtering.
- MES showed that stronger CVD filtering can support materially higher R while reducing dependence on frequent, thin-edge trades and transaction costs/slippage.
- Re-test R jointly with stop size, FVG range and expiry after adding a quality filter.

### 5. Separate strategy quality from payout economics
- Production and Harvest are different optimization objectives.
- Production prioritizes survival, robustness, low breach rate, simple execution and stress resilience.
- Harvest prioritizes banked payout throughput/time-for-money and may rationally accept more account churn when replacement capacity is abundant.
- Do not select solely on PF, win rate, total net profit, or payout count.

### 6. Size only after structural edge is fixed
- Contract quantity is a lifecycle/risk variable, not an entry-edge optimizer.
- First determine the robust signal/exit family at 1-contract scale; then test quantity through PA DLL/drawdown/payout rules.
- Reject sizes whose nominal full-stop exposure is too close to or exceeds the applicable DLL before slippage/commission.

### 7. Daily management belongs after the raw strategy
- First validate the unmodified strategy in Pine.
- Only then test daily cap/trailing rules as a payout/lifecycle layer.
- Daily management may improve breach efficiency while reducing total strategy P&L; evaluate both explicitly.

### 8. Trade-level BE/trailing must earn its complexity
- A higher PF alone is not sufficient if BE/trailing reduces net profit, creates scratch-heavy outcomes, or weakens parity.
- MES did not show enough durable benefit to justify trade-level BE/trailing in the defaults; OFF remains the baseline.

### 9. Micro versus full-size futures is a sizing decision, not only a commission decision
- Compare costs at equivalent exposure.
- If the robust optimum is materially below one full-size contract equivalent, retain micros even when full-size commissions are cheaper per equivalent exposure.
- Do not round a 0.5–0.6 full-contract optimum up to one full contract merely to save fees.

### 10. Pine parity is a hard deployment gate
Before PA deployment, compare the fixed Python/.NET candidate with Pine on the same period and data semantics:
- trade count;
- win rate and PF;
- average winner/loss and payoff distribution;
- LONG versus SHORT counts/results;
- entry/fill timing and pending-order expiry;
- CVD proxy streak state;
- stop/target tick units and tick rounding;
- commission and adverse-slippage assumptions;
- no same-fill-bar future leakage;
- force-flat handling;
- 18:00 ET trading-day accounting.
If these materially diverge, stop optimization and fix parity first.

### 11. Current MES research checkpoints (not universal constants)
These are reproducible research checkpoints for the current MES dataset, not permanent market truths:
- Production candidate: FVG 10–22 ticks, SL 120 ticks, 1.75R, expiry 6, CVD6; initial Pine parity with daily management OFF; 6 MES only after lifecycle sizing validation.
- Harvest candidate: FVG 8–22 ticks, SL 120 ticks, 1.0R, expiry 12, CVD4; 5 MES with a $1,000 daily cap in the tested EOD lifecycle.
- These defaults must be revalidated when dataset, fee model, prop rules, execution assumptions or strategy implementation changes.

## TradingView saved-input state rule
TradingView can preserve prior input values when a script is updated or replaced, even when new source-code defaults were changed. A Pine validation is invalid until the exported Properties tab is checked against the intended research configuration.

Mandatory parity audit from every TradingView export:
- contract quantity;
- unit mode;
- FVG min/max;
- stop and R;
- pending-order expiry;
- CVD/filter enabled state, engine and streak count;
- session/regime settings;
- daily management;
- account preset;
- commission and slippage.

If an intended filter is OFF in the Properties export, the backtest must be labelled as the OFF/control variant rather than attributed to that filter. Do not infer that source-code defaults were active.

## Pine parity test-state rule
For the first parity validation of a newly researched market, prefer a dedicated test script whose critical research gate cannot be silently disabled by stale saved input state, or explicitly rename/reset critical inputs between versions. The exported Properties sheet is the ground truth of what TradingView actually tested.



## MYM lessons — wide-stop micro economics and PA-model separation

MYM research confirmed several general rules:
- Tick/point semantics must be instrument-specific: MYM tick size is 1 index point and tick value is $0.50 per MYM.
- A numerically large stop (e.g. 480 ticks) can still be reasonable in dollar risk because of the low micro tick value. Always optimize and report both ticks and dollars.
- High-R/wide-excursion strategies may look robust at the strategy layer yet perform materially worse under Intraday PA trailing drawdown. EOD-vs-Intraday must remain a lifecycle axis and must not be inferred from strategy PF.
- Production and Harvest can emerge from entirely different CVD/FVG regimes. Do not force a common entry family merely for implementation simplicity.
- When a local refinement helper or optimizer is found to have an argument-order or semantic error, invalidate only the affected results, identify which prior stages remain valid, and rerun the corrupted stage from its last clean checkpoint.
