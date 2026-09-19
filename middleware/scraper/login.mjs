// One-time Tradovate login — run this on a machine WITH a screen (your Windows PC).
// It opens a real browser; you log in by hand (username/password + any 2FA), then press
// ENTER here. The session is written to auth.json, which the headless server scraper reuses
// (copy it to the server as MEX_AUTH or scraper/auth.json). Re-run whenever the session dies.
//
//   npm install
//   npx playwright install chromium   # only the first time
//   node login.mjs                     # writes auth.json
import { chromium } from 'playwright';

const AUTH = process.env.MEX_AUTH || 'auth.json';

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ acceptDownloads: true });
const page = await ctx.newPage();
await page.goto('https://trader.tradovate.com/welcome');

console.log('\n────────────────────────────────────────────────────────');
console.log(' Log in to Tradovate in the browser window that opened.');
console.log(' When you can SEE YOUR ACCOUNTS, come back here and press ENTER.');
console.log('────────────────────────────────────────────────────────\n');

process.stdin.resume();
await new Promise(res => process.stdin.once('data', res));

await ctx.storageState({ path: AUTH });
console.log(`\n✅ Session saved → ${AUTH}`);
console.log('   Copy this file to the server (scraper/auth.json or MEX_AUTH=/path/auth.json).');
await browser.close();
process.exit(0);
