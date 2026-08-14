// MEX Fleet — Scriptable home-screen widget (iOS)
// Shows the live fleet from the cockpit's /api/state: realized today, open positions,
// trades, win rate. Read-only. Works as Small or Medium widget.
//
// Setup (once):
//   1. Server: set VIEWER_API_TOKEN=<a-long-random-string> in the middleware .env and
//      restart mex-viewer (so the widget can read without the owner password).
//   2. iPhone: install "Scriptable" (App Store) → new script → paste this file.
//   3. Fill BASE + TOKEN below.
//   4. Home screen → add a Scriptable widget (Small or Medium) → pick this script.
//      Optionally set "When Interacting: Run Script" or leave "Open URL" via the tap below.

const BASE  = "https://app.mex-traders.com";     // your cockpit URL
const TOKEN = "PASTE_YOUR_VIEWER_API_TOKEN";      // == VIEWER_API_TOKEN on the server

// ---- palette (matches the cockpit) ----
const C = {
  bgTop:  new Color("#0a0e13"),
  bgBot:  new Color("#16212c"),
  text:   new Color("#e8eef4"),
  muted:  new Color("#8496a6"),
  faint:  new Color("#5b6b7a"),
  accent: new Color("#2dd4bf"),
  profit: new Color("#46c96a"),
  loss:   new Color("#f7645a"),
};

const money = n => (n >= 0 ? "+" : "−") + "$" + Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
const pnlColor = n => (n > 0 ? C.profit : n < 0 ? C.loss : C.muted);

async function getState() {
  const req = new Request(`${BASE}/api/state?token=${encodeURIComponent(TOKEN)}`);
  req.timeoutInterval = 12;
  return await req.loadJSON();
}

function bg(w) {
  const g = new LinearGradient();
  g.colors = [C.bgTop, C.bgBot];
  g.locations = [0, 1];
  w.backgroundGradient = g;
}

function header(w) {
  const row = w.addStack();
  row.centerAlignContent();
  const title = row.addText("🌴 MEX FLEET");
  title.font = Font.semiboldSystemFont(11);
  title.textColor = C.muted;
  row.addSpacer();
  const dot = row.addText("● live");
  dot.font = Font.mediumSystemFont(9);
  dot.textColor = C.accent;
}

function stat(stack, label, value, color) {
  const col = stack.addStack();
  col.layoutVertically();
  const v = col.addText(String(value));
  v.font = Font.semiboldSystemFont(15);
  v.textColor = color || C.text;
  const l = col.addText(label);
  l.font = Font.systemFont(9);
  l.textColor = C.faint;
}

async function build() {
  const w = new ListWidget();
  bg(w);
  w.setPadding(14, 15, 14, 15);
  w.url = BASE;                       // tap opens the full cockpit

  let s;
  try { s = await getState(); } catch (e) { s = null; }

  header(w);

  if (!s || s.error || !s.fleet) {
    w.addSpacer(6);
    const t = w.addText(TOKEN.startsWith("PASTE") ? "Set BASE + TOKEN" : "Geen verbinding");
    t.font = Font.mediumSystemFont(13);
    t.textColor = C.loss;
    return w;
  }

  const f = s.fleet;
  w.addSpacer(8);

  // hero: realized today
  const hero = w.addText(money(f.realized_today));
  hero.font = Font.boldSystemFont(config.widgetFamily === "small" ? 26 : 34);
  hero.textColor = pnlColor(f.realized_today);
  const cap = w.addText("realized vandaag");
  cap.font = Font.systemFont(10);
  cap.textColor = C.muted;

  w.addSpacer(config.widgetFamily === "small" ? 6 : 12);

  if (config.widgetFamily === "small") {
    const row = w.addStack();
    stat(row, "open", f.open_positions);
    row.addSpacer();
    stat(row, "win%", f.win_rate == null ? "—" : f.win_rate);
  } else {
    const row = w.addStack();
    row.spacing = 18;
    stat(row, "open posities", f.open_positions);
    stat(row, "trades", f.trades_today);
    stat(row, "win rate", f.win_rate == null ? "—" : f.win_rate + "%");
    stat(row, "profit factor", f.profit_factor == null ? "—" : f.profit_factor);
    row.addSpacer();
  }

  w.addSpacer(6);
  const ago = s.as_of ? new Date(s.as_of).toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" }) : "—";
  const foot = w.addText("bijgewerkt " + ago);
  foot.font = Font.systemFont(8);
  foot.textColor = C.faint;

  return w;
}

const widget = await build();
widget.refreshAfterDate = new Date(Date.now() + 5 * 60 * 1000);  // hint iOS to refresh ~5 min
if (config.runsInWidget) {
  Script.setWidget(widget);
} else {
  await widget.presentMedium();   // preview when run inside the app
}
Script.complete();
