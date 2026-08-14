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
import fs from 'fs';
import path from 'path';

const EXPORT_DIR = process.env.MEX_EXPORT_DIR || `${process.env.HOME}/exports`;
const PROFILE_DIR = process.env.MEX_PROFILE_DIR || `${process.env.HOME}/.mex-browser`;
const HEADFUL = process.env.MEX_HEADFUL === '1';
const PERIOD = process.env.MEX_PERIOD || 'This quarter';
const TOGGLE = PERIOD === 'This quarter' ? 'Last quarter' : 'This quarter';

const accounts = process.env.MEX_ACCOUNTS
  ? process.env.MEX_ACCOUNTS.split(',').map(s => s.trim()).filter(Boolean)
  : JSON.parse(fs.readFileSync(new URL('./accounts.json', import.meta.url))).accounts;

const stamp = new Date().toISOString().slice(0, 10).replaceAll('-', '');
fs.mkdirSync(EXPORT_DIR, { recursive: true });

const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
  headless: !HEADFUL, acceptDownloads: true,
});
const page = ctx.pages()[0] || await ctx.newPage();
page.setDefaultTimeout(30000);

await page.goto('https://trader.tradovate.com/welcome', { waitUntil: 'domcontentloaded' });

if (await page.getByRole('button', { name: 'Login' }).isVisible().catch(() => false)) {
  console.error('⛔ Not logged in. Run once with MEX_HEADFUL=1 and log in by hand; the profile keeps the session.');
  await ctx.close(); process.exit(1);
}

// "new customer"/welcome-screen quirk → reload until the app (account caret) is present
for (let i = 0; i < 4; i++) {
  if (await page.locator('.caret').first().isVisible().catch(() => false)) break;
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);
}
await page.getByText('Close').click({ timeout: 3000 }).catch(() => {});

// load the report workspace that holds the export panel
await page.getByTestId('bar-button-link').first().click({ timeout: 15000 }).catch(() => {});
await page.getByText('MEX Fleet Quad Legacy').click({ timeout: 15000 }).catch(() => {});
await page.waitForTimeout(2500);

const gathered = [];
for (const acct of accounts) {
  try {
    // pick the account
    await page.locator('.caret').first().click({ timeout: 15000 });
    await page.getByTestId(`account-item-${acct}`).locator('a').click({ timeout: 15000 });
    await page.waitForTimeout(1500);

    // TODO(verify): if there is a report-TYPE selector (Fills / Orders / Performance),
    // set it to Fills here. The recording only touched the date-range combobox (nth 1).
    // await page.getByRole('combobox').nth(0).selectOption('Fills').catch(() => {});

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
await ctx.close();
