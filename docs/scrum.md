# Scrum board — één register, één plek

**Read this first. Update it last.** Every chat, every session.

This file replaces `docs/inbox.md` and owns the ownership table. If a question
touches another chat's map, or nobody's map, it becomes an item here — it does not
get solved in a chat and forgotten.

## How an item works

`ID · title · owner · state · raised · blocks`

States: **OPEN** (no owner yet) · **ASSIGNED** · **BLOCKED** (waiting on another
item) · **DONE** (with the commit that closed it).

Anyone may *add* an item. Only the Scrum Master assigns an owner. Only the owner
closes one.

## Ownership

| Map | Owner |
|---|---|
| `backtest/**` | Backtest Setup |
| `pine/**`, `tools/gen_pine_firms.py` | Pine Dev |
| `middleware/**` | Middleware App |
| `data/propfirms.json` | shared — read from source, never copy |
| `docs/**`, `tools/**` (rest), `validation/**` | **unassigned — item S-02** |

## Board

### Blocking money or safety

| ID | Item | Owner | State |
|---|---|---|---|
| **S-01** | **Day caps / DLL / qty per funded account have nowhere live to land.** `risk.py` is only reachable from `middleware/app/main.py`, which is not live. The numbers are computed and correct; the execution point is not decided. Candidates: `mex-receiver` (.NET, live path → §4.4 protocol), Pine day-cap inputs, or PMT/Tradovate per-account limits. **Until this lands, no funded account can satisfy consistency and the 6/6 ladder does not move.** | OPEN | OPEN |
| **S-08** | **`app.mex-traders.com/api/command` and `/api/state` serve the full fleet — account numbers, balances, buffers, open positions — with no authentication.** Verified by fetching both without credentials. | OPEN | OPEN |
| **S-09** | **CVD contradiction.** `docs/legacy_accounts_playbook.md` states settings were validated with "CVD / delta filter: OFF"; the project rule is that CVD is never disabled. The NQ-family run independently found `ES_norm.csv` / `GC_norm.csv` / `YM_norm.csv` carry `Delta ≡ 0`. **If the live Pine scripts run CVD ON, every number in the playbook describes a different strategy than what trades.** Five-minute check on one live alert. | OPEN | OPEN |
| **S-12** | **Account 214 passed its eval** ($3,035 / $3,000, `eligible: true`) and is still listed as an eval. Convert it. | OPEN | OPEN |

### Sources of truth that do not exist or cannot be reached

| ID | Item | Owner | State |
|---|---|---|---|
| **S-04** | `middleware/app/playbook.py` (STRAT_ASSET) and `middleware/app/firm_rules.py` are named as sources of truth but exist **on no branch**. | OPEN | OPEN |
| **S-05** | `cash_ledger.py` and `fills_pairing.py` exist only on `claude/middleware-setup-guide-afhvtk`. From any other branch, three of the five sources of truth are unreadable — so "never keep a second copy" cannot currently be honoured without switching branches. | OPEN | OPEN |
| **S-06** | **Commission is at three different values**: `backtest/config.py` has NQ 1.55 / GC 1.75; Pine has 0.67 / 1.55; the FLEET validation measured micro 0.67. Every backtest net P&L therefore differs from what Tradovate settles. | OPEN | OPEN |
| **S-07** | The .NET receiver is not in the repo at HEAD — source lives only on `claude/legacy-accounts-scripts-analysis-ui0j6m`. | OPEN | OPEN |

### Process

| ID | Item | Owner | State |
|---|---|---|---|
| **S-02** | **No owner for `docs/**`, `tools/**` or `validation/**`.** All three are actively written by more than one chat. | OPEN | OPEN |
| **S-03** | **Branch conflict.** The working agreement names one branch (`claude/middleware-setup-guide-afhvtk`); this chat is assigned `claude/analyses-data-chat-org-3tii8j`, which the agreement itself lists as unmerged debt. Unresolved, so nothing from this chat can reach the others. | OPEN | OPEN |
| **S-11** | The three Notion database ids in `CLAUDE.md` (Fleet Performance, Trade Journal, Reconciliation) are **empty** — 0 rows each. The live cockpit uses a different backend. The ids in `CLAUDE.md` are stale. | OPEN | OPEN |

### Data / reconciliation

| ID | Item | Owner | State |
|---|---|---|---|
| **S-10** | **`realized_net` $21,597.35 vs `window_net` $31,424.81 — a $9,827.46 gap.** The ledger reconciles internally (funded $18,562.85 + account 214's $3,034.50), but the fills export totals nearly ten thousand more. This is what the reconciliation layer exists to catch, and it is not catching it. | OPEN | OPEN |
| **S-13** | **Pilot NQ export + validator output still outstanding.** Until it lands, the CVD-valid window is unknown and every analysis window is a guess. Blocks the two goal dashboards and the fleet model. | Backtest Setup | BLOCKED (waiting on export) |

## Unmerged work

| Branch | Contains |
|---|---|
| `claude/analyses-data-chat-org-3tii8j` | `docs/` (chats, state, data_export, infrastructure, this file), `tools/validate_dataset.py`, `tools/inventory_local.py`, `backtest/goals.py`, `/eval-throughput` + `/payout-throughput` skills, three engine fixes (halt bar, cumulative payout counter, the DST crash in `data.py`) |
| `claude/legacy-accounts-scripts-analysis-ui0j6m` | .NET receiver, renderer, `validation/**` |
