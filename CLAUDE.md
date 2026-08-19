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
- MEX Dev loopt via de bestaande LifeOS-databases — geen aparte structuur:
  **Tasks** met voorvoegsel `🛠️ MEX Dev ·`, en **Notes** `🛠️ MEX Dev — Architectuur /
  Besluitregister / Documentatieregister`. Beide gekoppeld aan Area *MEX Traders* en
  project *MEX PROP TRADER*. Werkwijze in `docs/CHAT_INSTRUCTIE.md`.

## Dev conventions
- Develop/commit/push only to branch `claude/middleware-setup-guide-afhvtk`; never push
  elsewhere without permission. Do not create PRs unless asked. (`claude/mcp-trader-dev-sse-ibl64y`
  is dood — volledig opgenomen in de werkbranch, liep 186 commits achter.)
- Ownership: `backtest/**` Backtest Setup · `pine/**` + `tools/gen_pine_firms.py` Pine Dev ·
  `middleware/**` Middleware App · `data/propfirms.json` gedeeld. Buiten je eigen map:
  niet muteren, maar melden in `docs/inbox.md`.
- **`middleware/app/main.py`, `router.py` en `brokers/` draaien NIET live.** Het live
  executiepad is `mex-receiver` (.NET). Verifieer met `systemctl cat` vóór je aanneemt
  dat een wijziging de executie raakt.
- **Lees `docs/SPRINT.md` vóór je begint** en claim één item (status `wip` + owner +
  losse commit) — dat is het slot dat dubbel werk voorkomt. Beslissing die een ander
  raakt? Eén regel in `docs/DECISIONS.md`.
- Alle vastlegging in Notion loopt via de Scrum Master — chats schrijven daar niet zelf.
- ⚠️ De Notion-id's hieronder zijn deels dood: *MEX Reconciliation* heeft 0 rijen
  (geverifieerd 19-08); Fleet Performance en Trade Journal nog ongecontroleerd.
- Never commit secrets: middleware `.env`, `accounts.yaml`, `*.db` are git-ignored.
- Pine is indentation-sensitive: 4-space indent, **no tabs**.
