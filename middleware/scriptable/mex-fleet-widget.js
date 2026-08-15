// MEX Fleet — Scriptable widget (small + medium). Tap opens the dashboard.
// Install: Scriptable → + → paste → name "MEX Fleet". Home screen → Scriptable widget → pick it.
// Numbers match the dashboard exactly: realized = ledger per stage (All / Funded / Eval).

const ENDPOINT  = "https://app.mex-traders.com/api/widget"
const DASHBOARD = "https://app.mex-traders.com"
const TOKEN     = ""      // when VIEWER_PASSWORD is set, put the VIEWER_API_TOKEN here
const DEMO      = false

const C = { txt:new Color("#EAF4F1"), sub:new Color("#84A8A3"), dim:new Color("#5C807C"),
  gold:new Color("#F0B64D"), aqua:new Color("#3FD0BD"), ok:new Color("#35C88A"),
  bad:new Color("#EF6B53") }

async function getData() {
  if (!DEMO) {
    const url = ENDPOINT + (TOKEN ? (ENDPOINT.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(TOKEN) : "")
    try { const j = await new Request(url).loadJSON(); if (j && !j.error) return j } catch (e) {}
  }
  return { goal: 250, dataThrough: "2026-08-15", spark: [30, 45, 38, 60, 52, 70, 64, 82, 78],
    stacks: {
      all:    { realized: 22088, week: 0, today: 0, trades: 717, winrate: 44, pf: 1.35, accounts: 24, breached: 1, buffer: 58155 },
      funded: { realized: 18259, week: 0, today: 0, trades: 600, winrate: 45, pf: 1.40, accounts: 7,  breached: 0, buffer: 20000 },
      eval:   { realized: 3829,  week: 0, today: 0, trades: 117, winrate: 42, pf: 1.20, accounts: 17, breached: 1, buffer: 38155 },
    } }
}

const num = (n, f) => (n === null || n === undefined || isNaN(n)) ? f : n
const money = n => (n >= 0 ? "+$" : "−$") + Math.abs(Math.round(n)).toLocaleString("en-US")
const moneyK = n => { const a = Math.abs(n), s = n >= 0 ? "+$" : "−$"
  return a >= 1000 ? s + (a / 1000).toFixed(1) + "k" : s + Math.round(a) }

function sparkline(vals, w, h, col) {
  const dc = new DrawContext(); dc.size = new Size(w, h); dc.opaque = false; dc.respectScreenScale = true
  if (!vals || vals.length < 2) return dc.getImage()
  const mn = Math.min(...vals), mx = Math.max(...vals), p = new Path()
  vals.forEach((v, i) => { const x = i / (vals.length - 1) * w
    const y = h - ((v - mn) / (mx - mn || 1)) * (h - 4) - 2
    i === 0 ? p.move(new Point(x, y)) : p.addLine(new Point(x, y)) })
  dc.addPath(p); dc.setStrokeColor(col); dc.setLineWidth(3); dc.strokePath(); return dc.getImage()
}

const d = await getData()
const S = d.stacks || {}
const all = S.all || {}, funded = S.funded || {}, evalS = S.eval || {}
const breached = num(all.breached, 0)
const fam = config.widgetFamily || "medium"

const w = new ListWidget()
w.url = DASHBOARD          // tap the widget → open the dashboard
const bg = new LinearGradient(); bg.locations = [0, 1]; bg.startPoint = new Point(0, 0); bg.endPoint = new Point(1, 1)
bg.colors = [new Color("#0B2428"), new Color("#06171A")]; w.backgroundGradient = bg

function header(w) {
  const h = w.addStack(); h.layoutHorizontally(); h.centerAlignContent()
  const t = h.addText("MEX FLEET"); t.font = Font.boldSystemFont(12); t.textColor = C.aqua
  h.addSpacer()
  const b = h.addText("●"); b.font = Font.systemFont(9); b.textColor = breached > 0 ? C.bad : C.ok
  return h
}
function stackRow(w, name, s, big) {
  const r = w.addStack(); r.layoutHorizontally(); r.centerAlignContent()
  const lab = r.addText(name); lab.font = Font.boldSystemFont(big ? 12 : 11); lab.textColor = C.aqua
  r.addSpacer(8)
  const rl = num(s.realized, 0)
  const val = r.addText(money(rl)); val.font = Font.boldSystemFont(big ? 15 : 13); val.textColor = rl >= 0 ? C.ok : C.bad
  r.addSpacer()
  const sub = r.addText("wk " + moneyK(num(s.week, 0)) + " · " + num(s.winrate, 0) + "% · PF " + Number(num(s.pf, 0)).toFixed(2))
  sub.font = Font.systemFont(10); sub.textColor = C.sub
  w.addSpacer(3)
}

if (fam === "small") {
  w.setPadding(13, 13, 11, 13)
  header(w); w.addSpacer(4)
  const lbl = w.addText("All-time"); lbl.font = Font.systemFont(9); lbl.textColor = C.sub
  const rl = num(all.realized, 0)
  const pnl = w.addText(money(rl)); pnl.font = Font.boldSystemFont(22); pnl.textColor = rl >= 0 ? C.ok : C.bad
  w.addSpacer(4); w.addImage(sparkline(d.spark, 120, 24, C.gold)); w.addSpacer(6)
  const r = w.addStack(); r.layoutHorizontally()
  const a = r.addText("Week " + moneyK(num(all.week, 0))); a.font = Font.systemFont(10); a.textColor = C.sub
  r.addSpacer()
  const b = r.addText(num(all.winrate, 0) + "% · " + Number(num(all.pf, 0)).toFixed(2)); b.font = Font.boldSystemFont(10); b.textColor = C.txt
} else {
  w.setPadding(14, 17, 13, 17)
  const h = header(w)
  h.addSpacer(8); h.addImage(sparkline(d.spark, 96, 22, C.gold))
  w.addSpacer(9)
  stackRow(w, "All", all, true)
  stackRow(w, "Funded", funded, false)
  stackRow(w, "Eval", evalS, false)
  w.addSpacer(2)
  const foot = w.addText(num(all.accounts, 0) + " accounts · " + breached + " breached · buffer " + moneyK(num(all.buffer, 0)))
  foot.font = Font.systemFont(9.5); foot.textColor = C.dim
}

if (config.runsInWidget) { Script.setWidget(w) } else { fam === "small" ? await w.presentSmall() : await w.presentMedium() }
Script.complete()
