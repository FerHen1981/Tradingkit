# Tradingkit — project memory

## Brand & philosophy
- **Pips and Palm Trees** — website **pipsandpalmtrees.com**.
- Core framing: *the whole game is about pips and ticks.* Execution quality (slippage in
  ticks on futures, pips on FX) is a first-class metric, not an afterthought — which is why
  the middleware has a full reconciliation layer measuring it per trade × venue.

## What this repo is
An automated prop-firm trading system with three parts:
- `backtest/` — Python bar-by-bar backtester + walk-forward eval funnel + prop-firm registry.
- `pine/` — 8 Pine v6 strategies (one engine, differ by phase/DD model). Spanish "El ___" names.
- `middleware/` — the control plane: one TradingView alert → fan-out across channels.

## The strategies & the edge (validated, 3y OOS)
- **Real funded edges: GC + ES only** (both halves PF>1). GC (El Tesoro/El Minero) = robust
  workhorse; ES (El Rey/El Leon) = strongest OOS after the factory.
- NQ (El Toro/Matador/Dorado/Patron) + YM = **eval-only** (H2≈1.00, no funded edge) — use as
  variance lottery tickets, never compound funded.
- **Roll/OpEx/News factory (v6.9.x)**: selectable event-regime filters (avoid quarterly
  roll/triple-witching, week-after-OpEx, FOMC/NFP) per strategy·type·phase. Mechanism-backed;
  lifts ES funded H2 1.00→1.16. Fine-grained day×hour cherry-picking is OOS noise (disproven).

## Middleware = control plane (NOT a copy-trader)
One alert per strategy → middleware maps strategy→accounts and fans out. Per account YOU set
firm/asset/volume/channel; not identical mirroring. Channels:
- **Execution**: PMT→Tradovate (Apex/MFFU), PineConnector→MT5 (FTMO). PMT is the execution
  bridge, not the fan-out; could later be replaced by direct Tradovate order API.
- **Notify**: Discord live per trade. **Journal**: internal sqlite + LifeOS Trade Journal.
- **Tracking**: Tradovate P&L poller → LifeOS Fleet Performance.
- **Reconciliation (Phase 6)**: intended (TradingView) vs actual fills (Tradovate + MT5 via
  MetaAPI) → slippage/latency/qty per venue → LifeOS Reconciliation. P&L-deviation staged.
- Safety: DRY_RUN default, kill-switch, idempotency, retries, per-account risk gate.
- Deploy: Render blueprint (easiest) or VPS one-command (`middleware/deploy/setup.sh`).

## LifeOS (Notion) dashboards
- Fleet Performance `ae5105393828447e84a1a87d31562d7d`
- Trade Journal `c3e9d05525404849ad484b648c82fd59`
- Reconciliation `2e674ed0a07f4b2cb77822b9b456f350`
- Content Hub data source `6cfcd7fa-1e15-439e-b7ab-274a907788f3`

## Working split — read `docs/state.md` first, update it last
Three chats, one source of truth (`docs/chats.md`): **Analyses & Data** (`backtest/`,
`data/`, recap), **Middleware dev** (`middleware/`), **Pine dev** (`pine/`). Regular
chats own nothing — they capture into `docs/inbox.md`. Two goals, deliberately kept
apart: **A** pass evals fast, **B** milk funded accounts to 6/6 payouts.

**CVD is never disabled.** No real per-bar `Delta` → the analysis stops and a solution
is proposed for approval. `use_cvd_filter=False` backtests a *different* strategy than
the one running live (`indicators.py:162-173`).

## Dev conventions
- One branch per chat; never push to another chat's branch without permission.
  Analyses & Data → `claude/analyses-data-*`, Middleware → `claude/mcp-trader-dev-*`,
  Pine → `claude/pine-dev-*`. Do not create PRs unless asked.
- Never commit secrets: middleware `.env`, `accounts.yaml`, `*.db` are git-ignored.
- Pine is indentation-sensitive: 4-space indent, **no tabs**.
