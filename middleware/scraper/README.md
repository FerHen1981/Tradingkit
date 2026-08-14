# MEX Tradovate Fills scraper

Downloads a **per-account Fills CSV** from Tradovate into `EXPORT_DIR` so the
Notion Trade Journal sync (`app.journal_sync`) can pair + upsert them. This is
the download half; the pairing/upsert half already runs on `mex-journal-sync.timer`.

There is **no Tradovate API** — this drives the real web UI with a persistent
login profile, so you log in **once** and it runs unattended afterwards.

## First run (log in once, headful)

On the machine that will run it (mex-mw-01), with a desktop/X or over VNC:

```bash
cd middleware/scraper
npm install                       # installs playwright
npx playwright install chromium   # skip on the server: chromium is pre-provisioned
MEX_HEADFUL=1 node scrape.mjs     # opens a window — log in to Tradovate by hand
```

The login is saved in `~/.mex-browser` (the `MEX_PROFILE_DIR`). After that the
session persists and it can run headless.

> **Login quirk:** the first page sometimes shows a "new customer"/welcome
> screen — the scraper already reloads up to 4× until the trading app (the
> account caret) appears, which is what a manual refresh does.

## Steady state (headless, on a timer)

```bash
node scrape.mjs                   # headless; writes EXPORT_DIR/<YYYYMMDD>_<acct>_Fills.csv
```

Then `mex-journal-sync` picks the CSVs up within 5 min and upserts to Notion.

## Config (env)

| var | default | meaning |
|-----|---------|---------|
| `MEX_EXPORT_DIR` | `~/exports` | where CSVs land (must match `EXPORTS_DIR` of the sync) |
| `MEX_PROFILE_DIR` | `~/.mex-browser` | persistent login profile |
| `MEX_ACCOUNTS` | *(reads `accounts.json`)* | comma-separated account ids to override the list |
| `MEX_HEADFUL` | *(unset)* | `1` shows the browser — first login / debugging |
| `MEX_PERIOD` | `This quarter` | date-range option that triggers the export |

Edit `accounts.json` when the fleet changes. Never commit `~/.mex-browser` or any
downloaded CSV — the session cookies and fills are private.

## Deploy on a timer

```bash
sudo cp ../deploy/mex-scrape.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mex-scrape.timer
```

Adjust `WorkingDirectory`/`ExecStart` paths in `mex-scrape.service` to match
where you deployed `middleware/`.
