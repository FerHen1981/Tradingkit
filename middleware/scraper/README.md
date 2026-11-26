# MEX Tradovate Fills scraper

Downloads a **per-account Fills CSV** from Tradovate into `EXPORT_DIR` so the
Notion Trade Journal sync (`app.journal_sync`) can pair + upsert them. This is
the download half; the pairing/upsert half runs on `mex-journal-sync.timer`.

There is **no Tradovate API** — this drives the real web UI with a browser.

## Where it has to run: a machine WITH a screen (your PC), not the headless VPS

Tradovate keeps the logged-in token in the browser's **`sessionStorage`**, which
Playwright's saved-session file (`storageState`/`auth.json`) does **not** carry.
So a session captured on your PC will *not* authenticate when copied to the
server — it lands back on the login page. The download therefore runs on the
machine where you actually log in (Windows/Mac), and only the resulting CSVs are
shipped to the server, where the Notion sync takes over.

A **persistent profile** (`~/.mex-browser`) keeps you logged in between runs on
that machine, so after the first login it can run without prompting until
Tradovate expires the session.

## First run — log in once (headful)

```bash
cd middleware/scraper
npm install                       # installs playwright
npx playwright install chromium   # first time only
MEX_HEADFUL=1 node scrape.mjs     # opens a window
```

A browser opens. Log in (password + any 2FA); when you see your accounts, come
back to the terminal and press **ENTER**. It then downloads every account in
`accounts.json` to `EXPORT_DIR`. The login is saved in the profile dir.

> **Welcome-screen quirk:** the first page sometimes shows a "new customer"
> screen — the scraper reloads a few times until the trading app appears, which
> is what a manual refresh does.

## Steady state (same machine, can run headless)

```bash
node scrape.mjs                   # writes EXPORT_DIR/<YYYYMMDD>_<acct>_Fills.csv
```

If the profile is still logged in this runs with no window. Ship the CSVs to the
server (e.g. `scp EXPORT_DIR/*_Fills.csv root@HOST:/root/exports/`); the
`mex-journal-sync` timer upserts them to Notion within ~5 min.

## Config (env)

| var | default | meaning |
|-----|---------|---------|
| `MEX_EXPORT_DIR` | `~/exports` (Win: `%USERPROFILE%\exports`) | where CSVs land |
| `MEX_PROFILE_DIR` | `~/.mex-browser` | persistent login profile |
| `MEX_ACCOUNTS` | *(reads `accounts.json`)* | comma-separated ids to override the list |
| `MEX_HEADFUL` | *(unset)* | `1` shows the browser + enables the login prompt |
| `MEX_PERIOD` | `This quarter` | date-range option that triggers the export |

Edit `accounts.json` when the fleet changes. Never commit `~/.mex-browser`,
`auth.json` or any CSV — those are private (session + fills).

> `login.mjs` / `MEX_AUTH` (saved-session file) are kept only for a same-machine
> headless setup; they do **not** work across machines (see the note above).
