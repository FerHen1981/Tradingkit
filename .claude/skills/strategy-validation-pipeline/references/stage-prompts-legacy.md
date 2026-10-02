# Stage prompt templates (upgraded from AI_Trading_Prompt_Library)

Each template replaces the original one-liner. Fill the `<...>` slots; do not remove gate lines.
Original one-liners are kept at the top of each block for provenance.

## Stage 1 — Idea survey
> Original: "Generate 20 published trading strategies. Explain edge, market, timeframe, entry, exit, risk, references."

Survey candidate strategies for <instrument, e.g. NQ intraday>. For each candidate give: stated edge and WHY it should exist (behavioral/structural/flow), market + timeframe, entry/exit sketch, risk logic, and a source label: [PUBLISHED — verified via web search with link], [FOLKLORE — practitioner claim, unverified], or [HYPOTHESIS — generated here]. Do not fabricate citations. 8-12 well-labeled candidates beat 20 vague ones.
**Gate:** at least 3 candidates whose edge is falsifiable (you can state what result would disprove it) survive a first-pass sanity discussion.

## Stage 2 — Selection & exact rules
> Original: "Reject curve-fit ideas. Keep only robust strategies. Write exact rules."

For each surviving candidate: write fully mechanical rules (a stranger could code them without asking questions), count free parameters and justify each, state the pre-registered hypothesis and the exact gate thresholds for Stages 3-5 BEFORE any data is touched. Reject candidates whose edge story is really a fit story ("it worked when I added the third filter").
**Gate:** rules mechanical, ≤ ~6 free parameters or explicit justification, pre-registration written to the stage artifact.

## Stage 3 — Engine validation
> Original: "Train 2010-2022. Test 2023-present. No look-ahead. Include costs and slippage."

Replace the calendar split with: rolling 12-month walk-forward over the full data (for NQ: the 10y 1m dataset), always reporting per-regime-year. Verify no look-ahead (shift entry signals by one bar and confirm results change accordingly), costs on (commission + ≥1 tick slippage per side), and reproducibility (same config file → same numbers).
**Gate:** look-ahead check passed, ≥100 in-sample trades, run reproducible from config alone.

## Stage 4 — Bulk backtest
> Original: "Run all strategies. Report CAGR, Sharpe, Sortino, MaxDD, PF, Trades."

Run all survivors on identical data/config. Report per strategy AND per regime-year: PF, MaxDD, trade count, Sharpe/Sortino, plus the Apex translation: startdag-sweep breach % and median gross on the 50K EOD ruleset.
**Gate:** PF ≥ 1.2 after costs in the most recent 12 months, and the strategy's edge is not exclusively in years that no longer resemble the current regime.

## Stage 5 — Robustness
> Original: "Run walk-forward, Monte Carlo, parameter sensitivity and regime tests."

Walk-forward efficiency (OOS/IS performance ratio), ±20% perturbation on every free parameter, Monte Carlo trade-order resampling (report p5/p50/p95 drawdown and end equity), regime split (trend/chop/vol tercile). One-shot OOS applies: this stage runs ONCE per registered rule set.
**Gate:** WFE ≥ 0.5; all ±20% perturbations remain profitable; MC p5 drawdown survivable under Apex trailing DD.

## Stage 6 — Portfolio / fleet fit
> Original: "Build inverse-volatility portfolio. Show correlation matrix and benchmark comparison."

Correlate daily PnL against every active fleet script (El Toro/Matador/Dorado/Patron generation). Then rerun the fleet startdag-sweep WITH the candidate added and compare median and p10 outcomes against the fleet without it.
**Gate:** pairwise correlation < 0.7 against each active script AND fleet median improves without materially worsening p10.

## Stage 7 — Stress test
> Original: "Stress test using crisis periods, slippage and higher commissions."

Crisis windows relevant to the data (2020-03, 2022 rate shock, plus the worst regime-year found in Stage 4), 2-tick slippage, doubled commissions, and gap-through-stop simulation. Express through the Apex EOD simulator.
**Gate:** no simulated account breach under stress parameters at intended position size.

## Stage 8 — Risk management
> Original: "Risk 0.5-1% per trade. Cap positions. Daily/weekly/monthly loss limits."

Encode (in the script, not in a document): per-trade risk 0.5-1% of account, max position cap, daily loss limit (prior MEX finding: ~$955 daily stop moved the median outcome dramatically — re-derive for this strategy, don't copy blindly), weekly/monthly circuit breakers.
**Gate:** limits are enforced by code and verified with a forced-loss test run.

## Stage 9 — Live guardrails
> Original: "Monitor drawdown, Sharpe, slippage and strategy decay. Auto stop if limits break."

Define auto-stop triggers: trailing DD threshold, rolling 20-trade PF floor, live-vs-backtest slippage divergence, signal-frequency anomaly (too many/few trades vs backtest). Wire the alert path (TradingView alert → webhook → notification) and test-fire it.
**Gate:** every trigger has a numeric threshold and a tested alert; a kill procedure is written down.

## Stage 10 — Paper trading
> Original: "Deploy to paper trading. Log every order. Compare live vs backtest weekly."

Minimum 4 weeks on paper/sim with full order logging (journal pipeline). Weekly comparison: fill quality, slippage, trade frequency, PnL trajectory vs backtest expectation bands (from Stage 5 Monte Carlo).
**Gate:** live tracks within the p5-p95 backtest band, or every divergence has a verified mechanical explanation. Only then is fleet promotion discussed — as a decision for the user, never made by the pipeline.
