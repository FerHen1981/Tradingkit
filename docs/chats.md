# Working split — three chats, one source of truth

The repo is the single source of truth. Chats are workers, not memory. Anything
that must survive a session becomes a file here (or a Notion record), never a
chat scrollback.

## The three chats

| Chat | Owns | Durable output | Branch |
|---|---|---|---|
| **Analyses & Data** | `backtest/`, `data/`, datasets, recap, every number and decision | dataset manifest, analysis reports, `docs/decisions/`, `docs/state.md` | `claude/analyses-data-*` |
| **Middleware dev** | `middleware/`, deploy, El Presidente dashboard | code + runbook | `claude/mcp-trader-dev-*` |
| **Pine dev** | `pine/`, CHANGELOG, parity with the backtester | `.pine` + CHANGELOG | `claude/pine-dev-*` |

Regular (mobile / non-code) chats own **nothing**. They may observe and capture
into `docs/inbox.md`; the Analyses & Data chat drains that inbox. A regular chat
never decides — only Analyses & Data promotes a number to "true".

## Rules

1. **Read `docs/state.md` first, update it last.** Every chat, every session.
2. **Stay in your lane.** If work belongs to another chat, write it to
   `docs/inbox.md` and say so — do not do it here.
3. **One branch per chat.** Never push to another chat's branch.
4. **CVD is never disabled.** If a dataset lacks a real per-bar `Delta`, the
   analysis stops and a solution is proposed for approval. Running with
   `use_cvd_filter=False` backtests a *different strategy* than the one live
   (`indicators.py:162-173` turns the filter into a pass-through).
5. **No number without a dataset id.** Every result cites the dataset it came
   from, so results stay comparable across weeks.

## Why the split

Both goals below pull in opposite directions, and mixing them in one
conversation is how contradictory settings end up live:

- **Goal A — pass evals fast.** Optimises for speed and pass probability;
  tolerates breaches (an eval is a cheap lottery ticket).
- **Goal B — milk funded accounts to 6/6 payouts.** Optimises for survival and
  payout cadence; tolerates lower returns.

Each goal gets its own analysis cycle and its own dashboard.
