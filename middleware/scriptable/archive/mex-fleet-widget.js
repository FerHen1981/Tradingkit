// MEX Fleet — Scriptable widget (small). Tap opens the dashboard.
// TWO ways to pick which stack a widget shows (all · funded · eval · week):
//   1. Script NAME — name the script "All Mex" / "Funded Mex" / "Eval Mex" / "Week Mex"
//      and the code auto-detects the mode from the name. Paste the SAME code in all 4.
//   2. Widget Parameter — long-press widget → Edit Widget → Parameter = all|funded|eval|week
//      (overrides the name). Empty parameter + unknown name = "all".
// Numbers match the dashboard exactly: realized = ledger per stage; week = the Week window.

const ENDPOINT  = "https://app.mex-traders.com/api/widget"
const DASHBOARD = "https://app.mex-traders.com"
const TOKEN     = ""      // when VIEWER_PASSWORD is set, put the VIEWER_API_TOKEN here
const DEMO      = false

const C = { txt:new Color("#EAF4F1"), sub:new Color("#84A8A3"), dim:new Color("#5C807C"),
  gold:new Color("#F0B64D"), aqua:new Color("#3FD0BD"), ok:new Color("#35C88A"), bad:new Color("#EF6B53") }

async function getData() {
  if (!DEMO) {
    const url = ENDPOINT + (TOKEN ? (ENDPOINT.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(TOKEN) : "")
    try { const j = await new Request(url).loadJSON(); if (j && !j.error) return j } catch (e) {}
  }
  return { goal: 250, dataThrough: "", spark: [30, 45, 38, 60, 52, 70, 64, 82, 78], today: 137,
    week: { net: 620, trades: 14, winrate: 57, pf: 1.85 },
    stacks: {
      all:    { realized: 22088, week: 620, today: 137, trades: 717, winrate: 44, pf: 1.35, accounts: 24, breached: 1, buffer: 58155 },
      funded: { realized: 18259, week: 400, today: 212, trades: 600, winrate: 45, pf: 1.40, accounts: 7,  breached: 0, buffer: 20000 },
      eval:   { realized: 3829,  week: 220, today: -75, trades: 117, winrate: 42, pf: 1.20, accounts: 17, breached: 1, buffer: 38155 },
    },
    // D-74 §3.1 — genormaliseerde eval-tellers, alleen aantallen, geen bedragen.
    eval_stats: { unit: "50k-equivalent", counts_50k_eq: { passed: 6.0, breached: 1.0, running: 12.0 },
                  raw_counts: { passed: 4, breached: 1, running: 12 }, n_accounts: 17, win_rate: 80.0 },
    // D-74 §3.1 — funded-verified vlag (hand-input, 7-daags venster).
    funded_verified: { verified: false, verified_at: null, days_ago: null } }
}

const num = (n, f) => (n === null || n === undefined || isNaN(n)) ? f : n
const money = n => (n >= 0 ? "+$" : "−$") + Math.abs(Math.round(n)).toLocaleString("en-US")
const moneyK = n => { const a = Math.abs(n), s = n >= 0 ? "+$" : "−$"
  return a >= 1000 ? s + (a / 1000).toFixed(1) + "k" : s + Math.round(a) }
const pfStr = p => Number(num(p, 0)).toFixed(2)

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
  if (["all", "funded", "eval", "week"].includes(p)) return p
  let nm = ""
  try { nm = (Script.name() || "").toLowerCase() } catch (e) {}
  if (nm.includes("week"))  return "week"
  if (nm.includes("fund"))  return "funded"
  if (nm.includes("eval"))  return "eval"
  return "all"
}
const param = detectMode()

// pick the view: all/funded/eval (stage stacks) or week
let title, lbl, big, breached, rows, isMoney = true
if (param === "week") {
  const wk = d.week || {}
  title = "WEEK"; lbl = "This week"; big = num(wk.net, 0); breached = num((d.stacks && d.stacks.all || {}).breached, 0)
  // "· all" is niet cosmetisch: d.today is command_state("day") ZONDER stage, dus
  // eval + funded opgeteld. In de stack-standen hieronder komt Today uit de stack zelf.
  rows = [["Today · all", moneyK(num(d.today, 0))], ["Trades", String(num(wk.trades, 0))],
          ["Win / PF", num(wk.winrate, 0) + "% · " + pfStr(wk.pf)]]
} else if (param === "eval") {
  // D-74 §3.1 — de eval-stand rendert AANTALLEN, geen bedragen. `realized` en
  // `buffer` in dollars vielen precies onder Ferry's opmerking van 05-09
  // ("we publiceren nu saldo's van eval accounts, die bedragen zeggen niets").
  // Big number = passed genormaliseerd op 50k; rows dragen breached/running en
  // een winrate op basis van beslist verkeer (passed / (passed + breached)).
  const e = d.eval_stats || {}
  const c50k = e.counts_50k_eq || {}
  const raw = e.raw_counts || {}
  title = "EVAL"; lbl = "Passed · 50k-eq"; isMoney = false
  big = num(c50k.passed, 0)
  breached = num(raw.breached, 0)
  const wr = e.win_rate == null ? "—" : (Number(e.win_rate).toFixed(0) + "%")
  rows = [
    ["Breached", num(c50k.breached, 0).toFixed(1) + " · " + num(raw.breached, 0) + " raw"],
    ["Running",  num(c50k.running, 0).toFixed(1)  + " · " + num(raw.running, 0)  + " raw"],
    ["Win-rate", wr],
    ["N accounts · unit", num(e.n_accounts, 0) + " · 50k-eq"],
  ]
} else {
  const s = (d.stacks || {})[param] || {}
  title = param.toUpperCase(); lbl = "All-time"; big = num(s.realized, 0); breached = num(s.breached, 0)
  // Today komt hier uit de stack (s.today = command_state("day", stage)), niet uit het
  // top-level d.today — anders toont een FUNDED-widget de som van funded EN eval.
  rows = [["Today", moneyK(num(s.today, 0))], ["Week", moneyK(num(s.week, 0))],
          ["Win / PF", num(s.winrate, 0) + "% · " + pfStr(s.pf)],
          ["Accounts", num(s.accounts, 0) + " · " + num(s.breached, 0) + " br"]]
  // D-74 §3.1 — funded-stack krijgt een verified-label onder All-time, zodat je
  // ziet of het bedrag brokerwaarheid of Pine-simulatie is. Zonder verified_at
  // is de default expliciet "⚠ unverified" — geen aanname op ongeziene bron.
  if (param === "funded") {
    const fv = d.funded_verified || {}
    lbl = fv.verified ? ("✓ verified " + fv.verified_at)
                     : (fv.verified_at ? ("⚠ unverified since " + fv.verified_at)
                                       : "⚠ unverified")
  }
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
const dot = head.addText("●"); dot.font = Font.systemFont(9); dot.textColor = breached > 0 ? C.bad : C.ok
w.addSpacer(4)

const l = w.addText(lbl); l.font = Font.systemFont(9); l.textColor = C.sub
// D-74: eval-stand toont een 50k-genormaliseerd getal, geen bedrag — dus geen
// dollarteken en geen +/-kleuring. De rest blijft geld.
const bigStr = isMoney ? money(big) : Number(big).toFixed(1)
const pnl = w.addText(bigStr); pnl.font = Font.boldSystemFont(22)
pnl.textColor = isMoney ? (big >= 0 ? C.ok : C.bad) : C.gold
w.addSpacer(4)
w.addImage(sparkline(d.spark, 120, 18, C.gold))
w.addSpacer(4)

for (const [k, v] of rows) {
  const r = w.addStack(); r.layoutHorizontally()
  const a = r.addText(k); a.font = Font.systemFont(10); a.textColor = C.sub
  r.addSpacer()
  const b = r.addText(v); b.font = Font.boldSystemFont(10); b.textColor = C.txt
  w.addSpacer(1)
}

if (config.runsInWidget) { Script.setWidget(w) } else { await w.presentSmall() }
Script.complete()
