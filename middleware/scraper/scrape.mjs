// MEX Tradovate Fills scraper — downloads a per-account Fills CSV to EXPORT_DIR.
// Built from the recorded export flow (account-item-<id> to pick an account; changing
// the date-range combobox triggers the CSV download inside the "MEX Fleet Quad Legacy"
// workspace). Uses a PERSISTENT browser profile so the Tradovate login survives between
// runs — log in ONCE headful, then it runs headless on a timer.
//
// Env:
//   MEX_EXPORT_DIR   default ~/exports          where the CSVs land (the ingest picks them up)
//   MEX_PROFILE_DIR  default ~/.mex-browser     persistent login profile
//   MEX_ACCOUNTS     comma-separated ids, else read scraper/accounts.json {"accounts":[...]}
//   MEX_HEADFUL=1    show the browser (first-time login / debugging)
//   MEX_PERIOD       date-range option label that triggers the export (default "This quarter")
import { chromium } from 'playwright';
import { fileURLToPath } from 'url';
import fs from 'fs';
import path from 'path';

const EXPORT_DIR = process.env.MEX_EXPORT_DIR || `${process.env.HOME}/exports`;
const PROFILE_DIR = process.env.MEX_PROFILE_DIR || `${process.env.HOME}/.mex-browser`;
const HEADFUL = process.env.MEX_HEADFUL === '1';
const PERIOD = process.env.MEX_PERIOD || 'This quarter';
const TOGGLE = PERIOD === 'This quarter' ? 'Last quarter' : 'This quarter';

// A saved Tradovate session (from login.mjs). On a headless server there's no screen to log
// in with, so we reuse a storageState captured on a machine that HAS one. If MEX_AUTH isn't
// set we fall back to auth.json next to this script, then to a persistent profile (headful).
const localAuth = new URL('./auth.json', import.meta.url);
const AUTH = process.env.MEX_AUTH || (fs.existsSync(localAuth) ? fileURLToPath(localAuth) : '');

const accounts = process.env.MEX_ACCOUNTS
  ? process.env.MEX_ACCOUNTS.split(',').map(s => s.trim()).filter(Boolean)
  : JSON.parse(fs.readFileSync(new URL('./accounts.json', import.meta.url))).accounts;

const stamp = new Date().toISOString().slice(0, 10).replaceAll('-', '');
fs.mkdirSync(EXPORT_DIR, { recursive: true });

// Two ways in: a saved session file (headless, server) or a persistent profile (headful login).
let browser = null, ctx;
if (AUTH) {
  browser = await chromium.launch({ headless: !HEADFUL });
  ctx = await browser.newContext({ acceptDownloads: true, storageState: AUTH });
  console.error(`(using saved session ${AUTH})`);
} else {
  ctx = await chromium.launchPersistentContext(PROFILE_DIR, { headless: !HEADFUL, acceptDownloads: true });
}
const closeAll = async () => { await ctx.close(); if (browser) await browser.close(); };
const page = ctx.pages()[0] || await ctx.newPage();
page.setDefaultTimeout(30000);

await page.goto('https://trader.tradovate.com/welcome', { waitUntil: 'domcontentloaded' });

// "new customer"/welcome-screen quirk → reload until the app (account caret) is present
for (let i = 0; i < 4; i++) {
  if (await page.locator('.caret').first().isVisible().catch(() => false)) break;
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);
}

// still no app after the reloads → the session is dead (or absent). Say so clearly.
if ((await page.locator('.caret').count()) === 0) {
  console.error('⛔ Not logged in / session expired. Recreate the session on a machine WITH a screen:');
  console.error('   node login.mjs   → produces auth.json → copy it to this server (MEX_AUTH or ./auth.json).');
  await closeAll(); process.exit(1);
}
await page.getByText('Close').click({ timeout: 3000 }).catch(() => {});

// load the report workspace that holds the export panel
await page.getByTestId('bar-button-link').first().click({ timeout: 15000 }).catch(() => {});
await page.getByText('MEX Fleet Quad Legacy').click({ timeout: 15000 }).catch(() => {});
await page.waitForTimeout(2500);

// Select the "Fills" report type. Tries the ways Tradovate might render the selector and
// returns true on the first one that clicks; false if none matched (caller warns).
async function selectFillsReport(page) {
  const attempts = [
    () => page.getByRole('tab', { name: 'Fills', exact: true }),
    () => page.getByRole('button', { name: 'Fills', exact: true }),
    () => page.getByRole('link', { name: 'Fills', exact: true }),
    () => page.getByText('Fills', { exact: true }),
  ];
  for (const make of attempts) {
    try {
      const el = make().first();
      if (await el.isVisible({ timeout: 1500 }).catch(() => false)) {
        await el.click({ timeout: 3000 });
        return true;
      }
    } catch { /* try next strategy */ }
  }
  // last resort: a <select> whose options include "Fills"
  try {
    await page.getByRole('combobox').nth(0).selectOption({ label: 'Fills' });
    return true;
  } catch { return false; }
}

const gathered = [];
for (const acct of accounts) {
  try {
    // pick the account
    await page.locator('.caret').first().click({ timeout: 15000 });
    await page.getByTestId(`account-item-${acct}`).locator('a').click({ timeout: 15000 });
    await page.waitForTimeout(1500);

    // choose the FILLS report type (there's a Fills/Orders/Performance selector that must
    // be clicked). We only need Fills — Orders + Performance are derivable from the fills.
    // Tradovate may render this as a tab, a button, a combobox option, or plain text, so try
    // each until one sticks; if none matches we fall through to whatever is already selected.
    if (!(await selectFillsReport(page))) {
      console.error(`WARN ${acct}: could not confirm the Fills report tab — check the download`);
    }
    await page.waitForTimeout(1000);

    // trigger the export: toggling the date-range combobox re-generates + downloads the CSV.
    await page.getByRole('combobox').nth(1).selectOption(TOGGLE).catch(() => {});
    await page.waitForTimeout(1000);
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 180000 }),   // the report can be slow
      page.getByRole('combobox').nth(1).selectOption(PERIOD),
    ]);
    const dest = path.join(EXPORT_DIR, `${stamp}_${acct}_Fills.csv`);
    await download.saveAs(dest);
    gathered.push(dest);
    console.log(`OK   ${dest}`);
  } catch (e) {
    console.error(`FAIL ${acct}: ${e.message}`);
  }
}

console.log(`\n${gathered.length}/${accounts.length} downloaded → ${EXPORT_DIR}`);
await closeAll();
