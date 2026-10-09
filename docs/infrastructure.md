# Infrastructure — getting off the local PC

Goal: the PC can be switched off without anything stopping, everything is
reachable from a phone, and files live in one canonical place instead of
scattered across `C:\`.

## What actually needs to run 24/7

| Needs 24/7 | Why |
|---|---|
| Middleware webhook | TradingView fires at any hour; a missed webhook is a missed trade |
| Tradovate P&L poller, reconciliation, journal DB | continuous measurement |
| The two dashboards (Goal A, Goal B) | must answer when opened on a phone |
| Scheduled recaps | run unattended |

| Does **not** need 24/7 | Why |
|---|---|
| **Quantower** | it is a *research source*, not live infrastructure. The corpus is refreshed monthly at most; live data comes from the broker. |
| Backtests and sweeps | on demand — but run them on the server, because they are heavy and the results need to be mobile-visible |

So this is not "move everything". It is three moves: the **data corpus** out of
`C:\` into object storage, the **analysis runs** onto the box the middleware needs
anyway, and the **outputs** into dashboards. Quantower stays on the PC as an
occasional export tool.

Removing the PC entirely later means replacing Quantower with a data API that the
server pulls from directly (Databento serves real CME order flow). That is a cost
decision, not a today decision.

## Target shape

```
  Quantower (PC, occasional)          ← the only thing left local
        │  export 1m + volume analysis
        │  tools/validate_dataset.py --to-parquet
        ▼
  Object storage  ──────────────────  canonical corpus
   GitHub Releases (data-v1) or Cloudflare R2
   indexed by data/manifest.json — not in the manifest = does not exist
        │
        ▼
  One VPS (24/7) ────────────────────  Caddy → HTTPS on pipsandpalmtrees.com
   ├─ middleware (systemd, deploy/setup.sh already does this)
   ├─ journal + reconciliation sqlite  (on the volume, backed up nightly)
   ├─ scheduled jobs: recap, dataset refresh, fleet report
   └─ dashboards: /goal-a (eval throughput), /goal-b (payout throughput)
        │
        ▼
  Phone — two URLs, behind auth
```

## VPS, not Render, for this box

`render.yaml` is the beginner path and is fine for the webhook alone. It is the
wrong host once analyses move onto the same machine: the starter plan is ~0.5 vCPU
/ 512 MB, and a single 5M-row dataset is ~400 MB in pandas *per copy*. The sqlite
journal also wants a disk that survives a redeploy.

Recommended: one small VPS — **2-4 vCPU, 8 GB RAM, 80 GB disk** (Hetzner CX32 or
equivalent, well under €10/month). That comfortably runs the middleware, holds a
local cache of the corpus, and executes sweeps.

`middleware/deploy/setup.sh` already installs Python, Caddy, the systemd unit and
HTTPS in one command. The box exists as a script; it just has not been created.

## Order of work

1. **Inventory before moving.** `tools/inventory_local.py` walks the local folders,
   classifies what it finds, flags duplicates and stale files, and writes a CSV.
   Copying `C:\` to a server relocates the mess; triage removes it.
2. **Provision the VPS**, point a subdomain at it, run `deploy/setup.sh`.
   *(Middleware chat.)*
3. **Publish the validated corpus** to object storage; `data/manifest.json` becomes
   the index. *(Analyses & Data chat.)*
4. **Move the analysis jobs** onto the box, scheduled.
5. **Dashboards**, one per goal. *(Middleware builds; Analyses & Data specifies
   what goes on them.)*
6. **Backups**: nightly dump of the sqlite journal off-box. The corpus is
   reproducible from Quantower; the journal is not.

## Rules that keep it from re-scattering

- One canonical place per class of thing: datasets in the bucket, code in the
  repo, results in the dashboards, notes in `docs/inbox.md`.
- Naming: `<SYMBOL>_1m_<FIRST>_<LAST>.parquet`.
- **Secrets never move to the bucket.** `.env`, `accounts.yaml` and `*.db` are
  git-ignored and stay that way; they live on the box only.
- Anything not registered goes to an `_attic` folder — archived, not deleted.

## Lane split

| Chat | Owns here |
|---|---|
| **Middleware dev** | provisioning the VPS, Caddy/systemd, dashboard implementation, backups |
| **Analyses & Data** | the corpus, `data/manifest.json`, validator, inventory/triage, scheduled analysis jobs, dashboard content spec |
