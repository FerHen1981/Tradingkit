# Tradingkit — project memory

## Brand & philosophy
- **Pips and Palm Trees** — website **pipsandpalmtrees.com**.
- Core framing: *the whole game is about pips and ticks.* Execution quality (slippage in
  ticks on futures, pips on FX) is a first-class metric, not an afterthought — which is why
  the middleware has a full reconciliation layer measuring it per trade × venue.

## What this repo is
An automated prop-firm trading system with three parts:
- `backtest/` — Python bar-by-bar backtester + walk-forward eval funnel + prop-firm registry.
- `pine/` — Pine v6 strategies, Spanish "El ___" names. **De v6.9.5-familie is vervangen**
  door de `v1_0_0`-lijn uit `MEX_FLEET_PACKAGE_2026-08-23` (zie hieronder).
- `middleware/` — the control plane: one TradingView alert → fan-out across channels.

## De vloot (stand 2026-08-23 — vervangt de oude GC+ES-conclusie)

> ⚠️ **De regel "funded edge = alleen GC + ES, NQ/YM eval-only" is INGETROKKEN** (Ferry, 24-08).
> Die kwam uit de funnel van vóór de pariteitscorrecties. Onder de research-invalidatieregel
> van de pijplijn vervallen alle rankings die onder een materiële pariteitsfout tot stand
> kwamen — en dat gold voor die conclusie. Zie `docs/DECISIONS.md`.

Merknaam = vaste strategie-persoonlijkheid. Titel codeert MARKT + CON/AGG/PROD/HF + EOD/INTRA.
Shorttitle ≤ 10 tekens. **EL TORO is voorbehouden aan evaluatie-accounts.**

| Merk | Markt | Profiel | Shorttitle |
|---|---|---|---|
| EL TESORO | MGC | Conservative EOD | `TES-MGC-C` |
| EL PATRON | MGC | Aggressive EOD | `PAT-MGC-A` |
| EL REY | MNQ | Production EOD / Intraday | `REY-MNQ-P` / `REY-NQ-PI` |
| EL MATADOR | MES | Production CVD6 EOD | `MAT-MES-P` |
| EL LEON | MYM | Production / recovery | `LEO-MYM-P` / `LEO-YM-CI` / `LEO-YM-CE` |
| EL BANDIDO | MYM | HF / Harvest EOD | `BAN-MYM-H` — **Pine-pariteit open, niet live** |
| EL PRINCIPE | MNQ | Balanced | research, niet live |
| EL MINERO | — | gereserveerd | toekomstige HF/commodity |

- **Rangorde:** REY (MNQ) › MATADOR (MES) › TESORO (MGC) › LEON (MYM) › PATRON (MGC) ›
  BANDIDO (specialist) › PRINCIPE (research). Rangorde ≠ accounttoewijzing.
- **Doel is niet PF maar gebankte payout-$ per bezette account-dag.** Account-mechanica kan
  de rangorde van twee identieke engines omdraaien.
- **Correlatie:** MGC is de enige niet-aandelenbucket; MNQ/MES/MYM zijn alle drie
  index-exposure. Claim geen decorrelatie vóór 20–30 actieve dagen gemeten P&L-correlatie.
- Fine-grained day×hour cherry-picking blijft OOS-ruis (weerlegd). Regimes mogen alleen
  economisch vooraf gedefinieerd.
- Bevroren parameters per engine: `.claude/skills/strategy-validation-pipeline/references/frozen-engines.md`.
  **Die zijn bevroren** — wijzigen is een nieuwe onderzoeksronde vanaf trap 1, geen tweak.

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
- ⚠️ Deze id's zijn deels dood: *MEX Reconciliation* heeft 0 rijen (geverifieerd 19-08) —
  de laag is gebouwd maar heeft nooit geschreven. Fleet Performance en Trade Journal nog
  ongecontroleerd. Zie `docs/SPRINT.md` D-20.
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
- Never commit secrets: middleware `.env`, `accounts.yaml`, `*.db` are git-ignored.
- Pine is indentation-sensitive: 4-space indent, **no tabs**.
