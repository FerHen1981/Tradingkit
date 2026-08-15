// MEX Fleet — Scriptable widget (small + medium)
// Install: Scriptable → + → paste → name "MEX Fleet". Home screen → Scriptable widget → pick it.
// Data comes from the cockpit's /api/widget. Set TOKEN once the site login is enabled.

const ENDPOINT = "https://app.mex-traders.com/api/widget"
const TOKEN    = ""      // when VIEWER_PASSWORD is set, put the VIEWER_API_TOKEN here
const DEMO     = false

const C = {
  txt:   new Color("#EAF4F1"),
  sub:   new Color("#84A8A3"),
  dim:   new Color("#5C807C"),
  gold:  new Color("#F0B64D"),
  aqua:  new Color("#3FD0BD"),
  ok:    new Color("#35C88A"),
  bad:   new Color("#EF6B53"),
  line:  new Color("#1C3F43"),
}

async function getData() {
  if (!DEMO) {
    const url = ENDPOINT + (TOKEN ? (ENDPOINT.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(TOKEN) : "")
    try { const j = await new Request(url).loadJSON(); if (j && !j.error) return j } catch (e) {}
  }
  return { todayPnl: 140, goal: 250, weekPnl: 620, trades: 14, winrate: 57, pf: 1.85,
           spark: [30, 45, 38, 60, 52, 70, 64, 82, 78], totalPnl: 22088, accounts: 24,
           breached: 1, buffer: 58155, bestAsset: "MGC", bestAssetNet: 11712, dataThrough: "" }
}

const num = (n, f) => (n === null || n === undefined || isNaN(n)) ? f : n
const money = n => (n >= 0 ? "+$" : "−$") + Math.abs(Math.round(n)).toLocaleString("en-US")
const moneyK = n => { const a = Math.abs(n); const s = n >= 0 ? "+$" : "−$"
  return a >= 1000 ? s + (a / 1000).toFixed(1) + "k" : s + Math.round(a) }

function sparkline(vals, w, h, col) {
  const dc = new DrawContext(); dc.size = new Size(w, h); dc.opaque = false; dc.respectScreenScale = true
  if (!vals || vals.length < 2) return dc.getImage()
  const mn = Math.min(...vals), mx = Math.max(...vals), p = new Path()
  vals.forEach((v, i) => {
    const x = i / (vals.length - 1) * w
    const y = h - ((v - mn) / (mx - mn || 1)) * (h - 4) - 2
    i === 0 ? p.move(new Point(x, y)) : p.addLine(new Point(x, y))
  })
  dc.addPath(p); dc.setStrokeColor(col); dc.setLineWidth(3); dc.strokePath()
  return dc.getImage()
}

const d = await getData()
const today = num(d.todayPnl, 0), week = num(d.weekPnl, 0), total = num(d.totalPnl, 0)
const wr = num(d.winrate, 0), pf = num(d.pf, 0), trades = num(d.trades, 0)
const accounts = num(d.accounts, 0), breached = num(d.breached, 0), buffer = num(d.buffer, 0)
const fam = config.widgetFamily || "medium"

const w = new ListWidget()
const bg = new LinearGradient()
bg.locations = [0, 1]; bg.startPoint = new Point(0, 0); bg.endPoint = new Point(1, 1)
bg.colors = [new Color("#0B2428"), new Color("#06171A")]
w.backgroundGradient = bg

const todayCol = today >= 0 ? C.ok : C.bad

function statusDot(stack) {
  const dot = stack.addText("●")
  dot.font = Font.systemFont(9)
  dot.textColor = breached > 0 ? C.bad : C.ok
}

function kv(stack, k, v, col) {
  const r = stack.addStack(); r.layoutHorizontally()
  const a = r.addText(k); a.font = Font.systemFont(11); a.textColor = C.sub
  r.addSpacer()
  const b = r.addText(v); b.font = Font.boldSystemFont(11); b.textColor = col || C.txt
  stack.addSpacer(2)
}

if (fam === "small") {
  w.setPadding(13, 13, 11, 13)
  const head = w.addStack(); head.layoutHorizontally(); head.centerAlignContent()
  const t = head.addText("MEX FLEET"); t.font = Font.boldSystemFont(10); t.textColor = C.aqua
  head.addSpacer(); statusDot(head)
  w.addSpacer(4)
  const lbl = w.addText("Today"); lbl.font = Font.systemFont(9); lbl.textColor = C.sub
  const pnl = w.addText(money(today)); pnl.font = Font.boldSystemFont(23); pnl.textColor = todayCol
  w.addSpacer(4)
  w.addImage(sparkline(d.spark, 120, 24, C.gold))
  w.addSpacer(6)
  kv(w, "Week", moneyK(week), week >= 0 ? C.ok : C.bad)
  kv(w, "WR / PF", wr + "% · " + pf.toFixed(2), pf >= 1 ? C.ok : C.sub)
  kv(w, "At risk", breached + " breached", breached > 0 ? C.bad : C.sub)
} else {
  w.setPadding(15, 17, 13, 17)
  const head = w.addStack(); head.layoutHorizontally(); head.centerAlignContent()
  const t = head.addText("MEX FLEET"); t.font = Font.boldSystemFont(12); t.textColor = C.aqua
  head.addSpacer()
  const tot = head.addText(moneyK(total) + " all-time"); tot.font = Font.systemFont(10); tot.textColor = C.sub
  head.addSpacer(6); statusDot(head)
  w.addSpacer(8)

  const top = w.addStack(); top.layoutHorizontally(); top.centerAlignContent()
  const left = top.addStack(); left.layoutVertically()
  const lbl = left.addText("Today"); lbl.font = Font.systemFont(10); lbl.textColor = C.sub
  const pnl = left.addText(money(today)); pnl.font = Font.boldSystemFont(26); pnl.textColor = todayCol
  top.addSpacer()
  const right = top.addStack(); right.layoutVertically(); right.bottomAlignContent()
  right.addImage(sparkline(d.spark, 120, 40, C.gold))
  w.addSpacer(10)

  const grid = w.addStack(); grid.layoutHorizontally()
  const c1 = grid.addStack(); c1.layoutVertically()
  kv(c1, "Week", moneyK(week), week >= 0 ? C.ok : C.bad)
  kv(c1, "Trades", String(trades), C.txt)
  grid.addSpacer(18)
  const c2 = grid.addStack(); c2.layoutVertically()
  kv(c2, "Win rate", wr + "%", wr >= 50 ? C.ok : C.sub)
  kv(c2, "Profit factor", pf.toFixed(2), pf >= 1.5 ? C.ok : (pf >= 1 ? C.txt : C.sub))
  grid.addSpacer(18)
  const c3 = grid.addStack(); c3.layoutVertically()
  kv(c3, "Accounts", String(accounts), C.txt)
  kv(c3, "Breached", String(breached), breached > 0 ? C.bad : C.ok)
}

if (config.runsInWidget) { Script.setWidget(w) } else { fam === "small" ? await w.presentSmall() : await w.presentMedium() }
Script.complete()
