// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: gray; icon-glyph: magic;
// MEX Fleet — Scriptable widget (small). Tap opens the dashboard.
// Paste this SAME code into 6 scripts named: all · funded · eval · week · today · yesterday
// (the code detects the mode from the script name). Then set each home-screen
// widget's Script to the matching one. A widget Parameter
// (all|funded|eval|week|today|yesterday) overrides the name if you set one.

const ENDPOINT  = "https://app.mex-traders.com/api/widget"
const DASHBOARD = "https://app.mex-traders.com"
const TOKEN     = "dedicatedAPItokenIphone"      // when VIEWER_PASSWORD is set, put the VIEWER_API_TOKEN here
const DEMO      = false

const C = { txt:new Color("#EAF4F1"), sub:new Color("#84A8A3"), dim:new Color("#5C807C"),
  gold:new Color("#F0B64D"), aqua:new Color("#3FD0BD"), ok:new Color("#35C88A"), bad:new Color("#EF6B53") }

async function getData() {
  if (!DEMO) {
    const url = ENDPOINT + (TOKEN ? (ENDPOINT.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(TOKEN) : "")
    try { const j = await new Request(url).loadJSON(); if (j && !j.error) return j } catch (e) {}
  }
  // fallback — placeholderwaarden, gemarkeerd zodat de widget dat toont
  return { _demo: true, goal: 0, dataThrough: "", spark: [30, 45, 38, 60, 52, 70, 64, 82, 78],
    today: -653.44,
    yesterday: { net: 1240.50, trades: 8, winrate: 62.5, pf: 2.10 },
    week: { net: -653.44, trades: 4, winrate: 50.0, pf: 0.2 },
    stacks: {
      all:    { realized: 20943.91, week: -653.44, today: -653.44, yesterday: 1240.50, trades: 543, winrate: 48.3, pf: 2.46, accounts: 21, breached: 0, buffer: 55501.27 },
      funded: { realized: 17909.41, week: -653.44, today: -653.44, yesterday: 1240.50, trades: 510, winrate: 46.5, pf: 2.38, accounts: 8,  breached: 0, buffer: 23001.27 },
      eval:   { realized: 3034.50,  week: 0,       today: 0,       yesterday: 0,       trades: 33,  winrate: 75.8, pf: 2.75, accounts: 13, breached: 0, buffer: 32500.00 },
    } }
}

const num = (n, f) => (n === null || n === undefined || isNaN(n)) ? f : n
const money = n => (n >= 0 ? "+$" : "−$") + Math.abs(Math.round(n)).toLocaleString("en-US")
const moneyK = n => { const a = Math.abs(n), s = n >= 0 ? "+$" : "−$"
  return a >= 1000 ? s + (a / 1000).toFixed(1) + "k" : s + Math.round(a) }
const pfStr = p => Number(num(p, 0)).toFixed(2)

// today/yesterday kan op verschillende manieren binnenkomen: als los getal, als
// object met dezelfde vorm als `week`, of als losse velden. We zoeken alle
// plausibele paden af en verzinnen niets als het er niet is.
const dig = (o, path) => path.split(".").reduce(
  (v, k) => (v === undefined || v === null) ? undefined : v[k], o)

function firstNum(d, paths) {
  for (const p of paths) {
    const v = dig(d, p)
    if (v !== undefined && v !== null && typeof v !== "object" && !isNaN(v)) return Number(v)
  }
  return null
}

function todaySnapshot(d) {
  const st = d.stacks || {}
  const sumStacks = key => {
    const parts = ["funded", "eval"].map(k => dig(st, k + "." + key))
      .filter(v => v !== undefined && v !== null && !isNaN(v))
    return parts.length ? parts.reduce((a, b) => a + Number(b), 0) : null
  }
  const net = firstNum(d, ["today", "today.net", "day.net", "daily.net",
                           "stats.today.net", "stacks.all.today"])
  const trades = firstNum(d, ["today.trades", "day.trades", "daily.trades",
                              "stats.today.trades", "todayTrades",
                              "stacks.all.todayTrades"]) ?? sumStacks("todayTrades")
  const winrate = firstNum(d, ["today.winrate", "day.winrate", "daily.winrate",
                               "stats.today.winrate", "todayWinrate",
                               "stacks.all.todayWinrate"])
  const pf = firstNum(d, ["today.pf", "day.pf", "daily.pf",
                          "stats.today.pf", "todayPf", "stacks.all.todayPf"])
  return { net: net === null ? 0 : net, trades, winrate, pf,
    ev: firstNum(d, ["stacks.eval.today", "eval.today", "today.eval"]) ?? 0,
    fu: firstNum(d, ["stacks.funded.today", "funded.today", "today.funded"]) ?? 0 }
}

function yesterdaySnapshot(d) {
  const st = d.stacks || {}
  const yd = d.yesterday || {}
  const net = firstNum(d, ["yesterday.net", "stacks.all.yesterday"])
  const trades = firstNum(d, ["yesterday.trades", "stacks.all.yesterdayTrades"])
  const winrate = firstNum(d, ["yesterday.winrate", "stacks.all.yesterdayWinrate"])
  const pf = firstNum(d, ["yesterday.pf", "stacks.all.yesterdayPf"])
  return { net: net === null ? 0 : net, trades, winrate, pf,
    ev: firstNum(d, ["stacks.eval.yesterday", "eval.yesterday"]) ?? 0,
    fu: firstNum(d, ["stacks.funded.yesterday", "funded.yesterday"]) ?? 0 }
}

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

// Mode: explicit Parameter wins; else derive from the script's name; else "all".
function detectMode() {
  const p = (args.widgetParameter || "").toString().trim().toLowerCase()
  if (["all", "funded", "eval", "week", "today", "yesterday"].includes(p)) return p
  let nm = ""
  try { nm = (Script.name() || "").toLowerCase() } catch (e) {}
  if (nm.includes("yesterday") || nm.includes("gisteren")) return "yesterday"
  if (nm.includes("today")) return "today"
  if (nm.includes("week"))  return "week"
  if (nm.includes("fund"))  return "funded"
  if (nm.includes("eval"))  return "eval"
  return "all"
}
const param = detectMode()

// pick the view: all/funded/eval (stage stacks), week, today, or yesterday
let title, lbl, big, breached, rows, split = null
if (param === "yesterday") {
  const y = yesterdaySnapshot(d)
  const all = (d.stacks || {}).all || {}
  title = "YESTERDAY"; lbl = "Prev session"; big = y.net
  breached = num(all.breached, 0)
  rows = [["Trades", y.trades === null ? "—" : String(y.trades)],
          ["Win / PF", (y.winrate === null ? "—" : y.winrate + "%") + " · " +
                       (y.pf === null ? "—" : pfStr(y.pf))]]
  split = { label: "Eval / Funded", a: moneyK(y.ev), b: moneyK(y.fu) }
} else if (param === "today") {
  const t = todaySnapshot(d)
  const wk = d.week || {}
  const all = (d.stacks || {}).all || {}
  title = "TODAY"; lbl = "Today"; big = t.net
  breached = num(all.breached, 0)
  if (t.trades !== null || t.pf !== null) {
    rows = [["Trades", t.trades === null ? "—" : String(t.trades)],
            ["Win / PF", (t.winrate === null ? "—" : t.winrate + "%") + " · " +
                         (t.pf === null ? "—" : pfStr(t.pf))]]
  } else {
    rows = [["Buffer", moneyK(num(all.buffer, 0))],
            ["Week W/PF", num(wk.winrate, 0) + "% · " + pfStr(wk.pf)]]
  }
  split = { label: "Eval / Funded", a: moneyK(t.ev), b: moneyK(t.fu) }
} else if (param === "week") {
  const wk = d.week || {}
  title = "WEEK"; lbl = "This week"; big = num(wk.net, 0); breached = num((d.stacks && d.stacks.all || {}).breached, 0)
  rows = [["Today", moneyK(num(todaySnapshot(d).net, 0))], ["Trades", String(num(wk.trades, 0))],
          ["Win / PF", num(wk.winrate, 0) + "% · " + pfStr(wk.pf)]]
} else {
  const s = (d.stacks || {})[param] || {}
  title = param.toUpperCase(); lbl = "All-time"; big = num(s.realized, 0); breached = num(s.breached, 0)
  rows = [["Week", moneyK(num(s.week, 0))], ["Win / PF", num(s.winrate, 0) + "% · " + pfStr(s.pf)],
          ["Accounts", num(s.accounts, 0) + " · " + num(s.breached, 0) + " br"]]
}

const w = new ListWidget()
w.url = DASHBOARD
w.refreshAfterDate = new Date(Date.now() + 5 * 60 * 1000)   // hint iOS to refresh ~5 min (iOS decides the real cadence)
w.setPadding(13, 13, 11, 13)
const bg = new LinearGradient(); bg.locations = [0, 1]; bg.startPoint = new Point(0, 0); bg.endPoint = new Point(1, 1)
bg.colors = [new Color("#0B2428"), new Color("#06171A")]; w.backgroundGradient = bg

const head = w.addStack(); head.layoutHorizontally(); head.centerAlignContent()
const t = head.addText("MEX · " + title); t.font = Font.boldSystemFont(11); t.textColor = C.aqua
head.addSpacer()
if (d._demo) {                       // endpoint niet bereikbaar — geen echte cijfers
  const dm = head.addText("demo"); dm.font = Font.systemFont(8); dm.textColor = C.gold
  head.addSpacer(4)
}
const dot = head.addText("●"); dot.font = Font.systemFont(9); dot.textColor = breached > 0 ? C.bad : C.ok
w.addSpacer(4)

const l = w.addText(lbl); l.font = Font.systemFont(9); l.textColor = C.sub
const pnl = w.addText(money(big)); pnl.font = Font.boldSystemFont(22); pnl.textColor = big >= 0 ? C.ok : C.bad
w.addSpacer(4)
w.addImage(sparkline(d.spark, 120, 22, C.gold))
w.addSpacer(6)

for (const [k, v] of rows) {
  const r = w.addStack(); r.layoutHorizontally()
  const a = r.addText(k); a.font = Font.systemFont(10); a.textColor = C.sub
  r.addSpacer()
  const b = r.addText(v); b.font = Font.boldSystemFont(10); b.textColor = C.txt
  b.lineLimit = 1
  w.addSpacer(1)
}

if (split) {
  const r = w.addStack(); r.layoutHorizontally(); r.centerAlignContent()
  const a = r.addText(split.label); a.font = Font.systemFont(10); a.textColor = C.sub
  r.addSpacer()
  // eval in goud, funded in aqua — zelfde kleurcodering als de rest van de fleet
  const e = r.addText(split.a); e.font = Font.boldSystemFont(10); e.textColor = C.gold
  e.lineLimit = 1; e.minimumScaleFactor = 0.8
  const sep = r.addText(" / "); sep.font = Font.systemFont(10); sep.textColor = C.dim
  const f = r.addText(split.b); f.font = Font.boldSystemFont(10); f.textColor = C.aqua
  f.lineLimit = 1; f.minimumScaleFactor = 0.8
  w.addSpacer(1)
}

if (config.runsInWidget) { Script.setWidget(w) } else { await w.presentSmall() }
Script.complete()
