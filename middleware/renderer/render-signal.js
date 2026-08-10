// MEX Signal Renderer v2 — HTML -> PNG via Playwright (headless Chromium).
// Contract: payload in $MEX_SIGNAL_JSON, output naar $MEX_SIGNAL_OUT.
// Eén template per goedgekeurd event (mockups 10-08); onbekend event -> generieke kaart.
// Verwijderd conform besluit: REGIME_FLIP, DAILY_RECAP (server-route). SIGNAL_BLOCKED -> ops (tekst).
// Optioneel: $MEX_CHROMIUM_PATH om een vaste Chromium-binary te forceren.
import { chromium } from 'playwright';

const d = JSON.parse(process.env.MEX_SIGNAL_JSON ?? JSON.stringify({
  event: 'FILL', asset: 'MGC', dir: 'LONG', strategy: 'ΞL MINΞRO',
  entry: '4407.0', stop: '4397.0', target: '4432.0', riskPt: '10.0', rr: '2.5',
  qty: 3, pctAcct: 6, beAt: '4417.0', beTrig: '+10', beOff: '+2',
  trailAt: '4422.0', trailBuf: '12t', toTarget: '820', toFail: '1,240',
  session: 'New York AM', sessN: 63, pf: '2.11', hit: '76', avgR: '+1.3',
  fingerprint: 'FVG12 · CVD0 · AGE0 · H20 · D5 · SL100t', chartUrl: ''
}));

const FOOT = 'System plan, not advice · mex-traders.com';
const row = (l, v, cls = '') => v == null ? '' : `<tr><td class="lbl">${l}</td><td class="val ${cls}">${v}</td></tr>`;

// ---- template per event: {icon, tone(gold|blue|rose|dim), title, badge?, badgeTone?, rows, stats?, fp?, foot?}
const T = {
  LIMIT_PLACED: () => ({ icon: d.dir === 'LONG' ? '↗' : '↘', tone: d.dir === 'LONG' ? 'blue' : 'rose',
    title: `${d.asset} · ${(d.dir || '').toLowerCase()} limit placed`, badge: d.risk ? `${d.risk} risk` : null,
    rows: [row('Account', d.account), row('Strategy', d.strategy), row('Session', d.session),
           row("Today's plan", d.outlook, d.outlookTone || 'blue'), row('Expiry', d.expiry ? `${d.expiry} bars` : null)] }),
  MARKET_ORDER: () => ({ icon: '⚡', tone: d.dir === 'LONG' ? 'blue' : 'rose',
    title: `${d.asset} · ${(d.dir || '').toLowerCase()} market order`, badge: d.risk ? `${d.risk} risk` : null,
    rows: [row('Account', d.account), row('Strategy', d.strategy), row('Session', d.session),
           row("Today's plan", d.outlook, d.outlookTone || 'blue')] }),
  LIMIT_EXPIRED: () => ({ icon: '✕', tone: 'dim', title: `${d.asset} · limit expired — no fill`,
    rows: [row('Waited', d.expiry ? `${d.expiry} bars` : null), row('Price', 'moved away from retrace level'),
           row('Plan', 'intact — next signal re-arms', 'blue')] }),
  ACCOUNT_STARTED: () => ({ icon: '▶', tone: 'gold', title: `Account armed · ${d.strategy}`, badge: d.phase,
    rows: [row('Account', d.account), row('Phase', d.phaseLong), row('Target', d.targetLine),
           row('Progress to target', d.progress ?? '0% — fresh start'), row('Config', 'pinned · CONFIG logged')] }),
  FILL: () => ({ icon: d.dir === 'SHORT' ? '↘' : '↗', tone: 'gold',
    title: `${d.asset} · ${d.dir} FILLED`, badge: 'live',
    rows: [row('Entry / Stop / Target', `${d.entry} / ${d.stop} / ${d.target}`),
           row('Risk / Reward', `${d.riskPt} pt · R ${d.rr}`),
           row('Size', `${d.qty} ct · ${d.pctAcct}% of account`),
           row('Break-even at', `${d.beAt} (${d.beTrig}, offset ${d.beOff})`),
           row('Trail arms at', `${d.trailAt} (buf ${d.trailBuf})`),
           row('To target / to fail', `$${d.toTarget} · $${d.toFail}`, 'gold')],
    stats: true, fp: d.fingerprint }),
  RISK_OFF: () => ({ icon: '⛨', tone: 'gold', title: `${d.asset} · risk off — stop to break-even`, badge: '+$0 locked',
    rows: [row('Stop moved', d.stopMove), row('Open P/L', d.openPl, 'blue'),
           row('Target still', d.targetLine), row('Initial risk', 'off the table', 'blue')] }),
  TRAIL_ACTIVE: () => ({ icon: '∿', tone: 'gold', title: `${d.asset} · trailing engaged`, badge: d.locked ? `locked ${d.locked}` : null,
    rows: [row('Trail level', d.trailAt), row('Captured so far', d.captured, 'blue'),
           row('Distance to target', d.distance), row('Mode', d.mode || 'keep-peak')] }),
  DERISK: () => ({ icon: '▼', tone: 'gold', title: `${d.asset} · derisk ${d.level || ''} — size reduced`, badge: 'guard',
    rows: [row('Quantity', d.qtyChange), row('Trigger', d.trigger),
           row('Open position', 'unchanged — applies to next entry'), row('Restores', d.restores)] }),
  EXIT: () => { const win = String(d.pnl || '').startsWith('+');
    return { icon: win ? '✓' : '✕', tone: win ? 'blue' : 'rose', title: `${d.asset} · exit — ${d.reason}`,
      badge: d.pnl, badgeTone: win ? 'blue' : 'rose',
      rows: [row('Closed / result', d.closedLine), row('Planned vs captured', d.captureLine, win ? 'blue' : 'rose'),
             row('MAE (heat taken)', d.mae), row('Account progress', d.progress, 'blue')],
      foot: win ? 'A win to plan is a good trade · mex-traders.com'
                : 'A loss to plan is still a good trade · mex-traders.com' }; },
  AUTO_FLAT: () => ({ icon: '‖', tone: 'dim', title: `${d.asset} · auto flat — session window`,
    rows: [row('Window', d.window || '16:55–18:00 ET'), row('Closed', d.closedLine),
           row('Session P/L', d.pnl, String(d.pnl || '').startsWith('+') ? 'blue' : 'rose'), row('Resumes', '18:00 ET')] }),
  DAY_HALT: () => ({ icon: '‖', tone: 'rose', title: `${d.asset} · day halted`, badge: d.reasonShort, badgeTone: 'rose',
    rows: [row('Reason', d.reason), row('Day P/L', d.pnl, String(d.pnl || '').startsWith('+') ? 'blue' : 'rose'),
           row('Entries blocked until', '18:00 ET'), row('Exits', 'never blocked', 'blue')] }),
  ACCOUNT_HALT: () => ({ icon: '‖', tone: 'rose', title: `${d.asset} · account halted`, badge: d.reasonShort, badgeTone: 'rose',
    rows: [row('Reason', d.reason), row('DD-room at halt', d.ddRoom),
           row('Resumes', d.resumes || 'automatically at 18:00 ET'), row('Exits', 'remain possible', 'blue')] }),
  PASS_LOCK: () => ({ icon: '▮', tone: 'gold', title: `${d.strategy} · pass-lock armed`, badge: 'EVAL',
    rows: [row('Distance to target', d.progress, 'blue'), row('Lock', 'intra-trade close at target + buffer'),
           row('Cost buffer', d.buffer || '4t for fees/slippage'), row('Account', d.account)] }),
  EVAL_PASSED: () => ({ icon: '✓✓', tone: 'gold', title: `${d.strategy} · EVAL PASSED`, badge: '100%',
    rows: [row('Final', d.final, 'gold'), row('Journey', d.journey),
           row('Next', d.next || 'PA activation → fleet matrix slot'), row('Account', d.account)],
    foot: 'Discipline compounds · mex-traders.com' }),
  EVAL_FAILED: () => ({ icon: '✕✕', tone: 'rose', title: `${d.strategy} · eval failed`, badge: 'breach', badgeTone: 'rose',
    rows: [row('Cause', d.reason), row('Damage', d.damage, 'rose'),
           row('Post-mortem', d.postmortem), row('Reset', d.reset)] }),
  PA_THRESHOLD: () => ({ icon: '$', tone: 'gold', title: `${d.strategy} · safety net reached`, badge: 'PA',
    rows: [row('Banked above net', d.banked, 'gold'), row('Payout track', d.cycle),
           row('Qualifying days', d.qual), row('Account', d.account)] }),
  PAYOUT_READY: () => ({ icon: '$', tone: 'gold', title: `${d.strategy} · payout ${d.payoutNr} ready`, badge: d.cap ? `cap ${d.cap}` : null,
    rows: [row('Withdrawable', d.withdrawable, 'gold'), row('Cycle', d.cycle),
           row('Consistency', d.consistency, 'blue'), row('Qualifying days', d.qual, 'blue')],
    foot: 'Harvest, then protect · mex-traders.com' }),
  HEARTBEAT_LOST: () => ({ icon: '⚠', tone: 'rose', title: `${d.strategy} · no events for ${d.gap} in session`, badge: 'ops', badgeTone: 'rose',
    rows: [row('Last event', d.lastEvent), row('Expected', d.expected),
           row('Check', 'alert active? chart open? PMT mapping?'), row('Middleware', d.mwState || '/health OK — chart side suspect')] }),
};

const spec = (T[d.event] ?? (() => ({ icon: '·', tone: 'dim', title: `${d.asset ?? ''} · ${d.event ?? 'event'}`,
  rows: Object.entries(d).filter(([k]) => !['event', 'chartUrl'].includes(k)).slice(0, 6)
        .map(([k, v]) => row(k, String(v))) })))();

const TONES = { gold: '#E8B54F', blue: '#5AA2FF', rose: '#E0796E', dim: 'rgba(242,235,218,.35)' };
const accent = TONES[spec.tone] ?? TONES.gold;
const badgeCol = TONES[spec.badgeTone ?? 'gold'];

const html = `<!doctype html><html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@600&family=Instrument+Sans:wght@400;500&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:#030F28;font-family:'Instrument Sans',sans-serif;width:640px}
  .card{padding:22px 24px}
  .head{display:flex;align-items:center;gap:10px;margin-bottom:14px}
  .icon{width:40px;height:40px;border-radius:50%;background:${accent};display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:20px;color:#030F28;font-weight:700}
  .title{font-family:'Bricolage Grotesque',sans-serif;font-weight:600;font-size:17px;color:#F2EBDA}
  .badge{margin-left:auto;font-size:12px;background:${badgeCol}26;color:${badgeCol};padding:3px 11px;border-radius:20px;font-family:'JetBrains Mono',monospace}
  .body{border-left:3px solid ${accent};padding-left:16px}
  table{width:100%;border-collapse:collapse;font-size:13.5px}
  td{padding:4px 0}
  .lbl{color:rgba(242,235,218,.6)}
  .val{text-align:right;font-family:'JetBrains Mono',monospace;color:#F2EBDA}
  .val.gold{color:#E8B54F}.val.blue{color:#5AA2FF}.val.rose{color:#E0796E}
  .sec{border-top:.5px solid rgba(242,235,218,.17);margin:12px 0;padding-top:11px}
  .seclbl{font-size:11px;color:rgba(242,235,218,.6);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px}
  .stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
  .stat{background:#0E2A5E;border-radius:8px;padding:9px 11px}
  .stat .k{font-size:11px;color:rgba(242,235,218,.6);margin-bottom:2px}
  .stat .v{font-size:18px;font-weight:600;font-family:'JetBrains Mono',monospace}
  .fp{font-family:'JetBrains Mono',monospace;font-size:11.5px;color:rgba(242,235,218,.6);background:#0B1428;border-radius:6px;padding:7px 10px;margin:10px 0 9px}
  .foot{font-size:11px;color:rgba(242,235,218,.6)}
  .chart{margin-top:14px;border-radius:8px;overflow:hidden;border:.5px solid rgba(242,235,218,.17)}
  .chart img{width:100%;display:block}
</style></head><body>
<div class="card">
  <div class="head">
    <div class="icon">${spec.icon}</div>
    <div class="title">${spec.title}</div>
    ${spec.badge ? `<div class="badge">${spec.badge}</div>` : ''}
  </div>
  <div class="body">
    <table>${spec.rows.join('')}</table>
    ${spec.stats ? `<div class="sec">
      <div class="seclbl">This session's edge · live from journal (${d.session}, n=${d.sessN})</div>
      <div class="stats">
        <div class="stat"><div class="k">Profit Factor</div><div class="v" style="color:#E8B54F">${d.pf}</div></div>
        <div class="stat"><div class="k">Hit rate</div><div class="v" style="color:#F2EBDA">${d.hit}%</div></div>
        <div class="stat"><div class="k">Avg R</div><div class="v" style="color:#F2EBDA">${d.avgR}</div></div>
      </div>
    </div>` : ''}
    ${spec.fp ? `<div class="fp">${spec.fp}</div>` : ''}
    <div class="foot">${spec.foot ?? FOOT}</div>
    ${d.chartUrl ? `<div class="chart"><img src="${d.chartUrl}"></div>` : ''}
  </div>
</div>
</body></html>`;

const outPath = process.env.MEX_SIGNAL_OUT ?? '/tmp/renderer/signal.png';
const launchOpts = process.env.MEX_CHROMIUM_PATH ? { executablePath: process.env.MEX_CHROMIUM_PATH } : {};
const browser = await chromium.launch(launchOpts);
const page = await browser.newPage({ deviceScaleFactor: 2 });
await page.setContent(html, { waitUntil: 'networkidle' });
await page.waitForTimeout(600);
const card = await page.$('.card');
await card.screenshot({ path: outPath });
await browser.close();
console.log(`✓ gerenderd: ${d.event} -> ${outPath}`);
