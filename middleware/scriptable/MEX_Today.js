// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: gray; icon-glyph: magic;
// ==========================================================
// MEX FLEET — ORANGE
// ONE SCRIPT / FOUR WIDGET PARAMETERS
//
// Parameters:
// today
// yesterday
// week
// total
//
// ==========================================================

const ENDPOINT =
  "https://app.mex-traders.com/api/widget"

const DASHBOARD =
  "https://app.mex-traders.com"

const TOKEN =
  "dedicatedAPItokenIphone"

const DEMO = false


// ==========================================================
// COLORS
// ==========================================================

const C = {

  txt:
    new Color("#F4F4F5"),

  sub:
    new Color("#A5A5AC"),

  dim:
    new Color("#66666D"),

  orange:
    new Color("#FF7E16"),

  orangeLight:
    new Color("#FFB66F"),

  ok:
    new Color("#35C88A"),

  bad:
    new Color("#EF6B53")

}


// ==========================================================
// DATA
// ==========================================================

async function getData() {

  if (!DEMO) {

    const url =
      ENDPOINT +
      (
        TOKEN
          ? (
              ENDPOINT.includes("?")
                ? "&"
                : "?"
            ) +
            "token=" +
            encodeURIComponent(TOKEN)

          : ""
      )


    try {

      const j =
        await new Request(url).loadJSON()

      if (
        j &&
        !j.error
      ) {

        return j

      }

    }

    catch (e) {}

  }


  // fallback / demo
  return {

    _demo: true,

    spark:
      [
        30,
        45,
        38,
        60,
        52,
        70,
        64,
        82,
        78
      ],

    today: -653.44,

    // D-105 · Demo laat "last session" zien met een echte sessiedag (vrijdag
    // 25-09) en met een niet-nul net, zodat de yesterday-tak in demo-mode ook
    // de nieuwe splitrij + label rendert.
    yesterday: {

      net: 421.87,

      trades: 6,

      winrate: 66.7,

      pf: 1.94,

      session_date: "2026-09-25"

    },

    week: {

      net: -653.44,

      trades: 4,

      winrate: 50.0,

      pf: 0.20

    },

    // D-105 · genormaliseerde eval-tellers voor de splitrij (accountontwikkeling,
    // geen bedragen — D-74). Waarden matchen wat _build_eval_stats zou uitrekenen
    // voor bv. 6 passed (50k-eq) en 1 breached (50k-eq).
    eval_stats: {

      unit: "50k-equivalent",

      counts_50k_eq: {

        passed: 6.0,

        breached: 1.0,

        running: 12.0

      },

      raw_counts: {

        passed: 4,

        breached: 1,

        running: 12

      },

      n_accounts: 17,

      win_rate: 80.0

    },

    stacks: {

      all: {

        realized: 20943.91,

        week: -653.44,

        today: -653.44,

        trades: 543,

        winrate: 48.3,

        pf: 2.46,

        accounts: 21,

        breached: 0,

        buffer: 55501.27

      },

      funded: {

        realized: 17909.41,

        week: -653.44,

        today: -653.44,

        accounts: 8

      },

      eval: {

        realized: 3034.50,

        week: 0,

        today: 0,

        accounts: 13

      }

    }

  }

}


// ==========================================================
// BASIC HELPERS
// ==========================================================

const num =
  (n, fallback) =>
    (
      n === null ||
      n === undefined ||
      isNaN(n)
    )
      ? fallback
      : Number(n)


const money = n => {

  const v =
    Number(n || 0)

  return (
    v >= 0
      ? "+$"
      : "−$"
  ) +
  Math
    .abs(
      Math.round(v)
    )
    .toLocaleString("en-US")

}


const moneyK = n => {

  const v =
    Number(n || 0)

  const a =
    Math.abs(v)

  const s =
    v >= 0
      ? "+$"
      : "−$"

  return (
    a >= 1000
      ? s +
        (a / 1000).toFixed(1) +
        "k"

      : s +
        Math.round(a)
  )

}


const pfStr =
  p =>
    Number(
      num(p, 0)
    ).toFixed(2)


const dig =
  (o, path) =>
    path
      .split(".")
      .reduce(
        (v, k) =>
          (
            v === undefined ||
            v === null
          )
            ? undefined
            : v[k],
        o
      )


function firstNum(
  d,
  paths
) {

  for (
    const p of paths
  ) {

    const v =
      dig(d, p)

    if (
      v !== undefined &&
      v !== null &&
      typeof v !== "object" &&
      !isNaN(v)
    ) {

      return Number(v)

    }

  }

  return null

}


// ==========================================================
// TODAY
// ==========================================================

function todaySnapshot(d) {

  const st =
    d.stacks || {}


  const net =
    firstNum(
      d,
      [
        "today",
        "today.net",
        "day.net",
        "daily.net",
        "stats.today.net",
        "stacks.all.today"
      ]
    )


  const trades =
    firstNum(
      d,
      [
        "today.trades",
        "day.trades",
        "daily.trades",
        "stats.today.trades",
        "todayTrades",
        "stacks.all.todayTrades"
      ]
    )


  const winrate =
    firstNum(
      d,
      [
        "today.winrate",
        "day.winrate",
        "daily.winrate",
        "stats.today.winrate",
        "todayWinrate",
        "stacks.all.todayWinrate"
      ]
    )


  const pf =
    firstNum(
      d,
      [
        "today.pf",
        "day.pf",
        "daily.pf",
        "stats.today.pf",
        "todayPf",
        "stacks.all.todayPf"
      ]
    )


  const ev =
    firstNum(
      d,
      [
        "stacks.eval.today",
        "eval.today",
        "today.eval"
      ]
    )


  const fu =
    firstNum(
      d,
      [
        "stacks.funded.today",
        "funded.today",
        "today.funded"
      ]
    )


  return {

    net:
      net ?? 0,

    trades,

    winrate,

    pf,

    ev:
      ev ?? 0,

    fu:
      fu ?? 0

  }

}


// ==========================================================
// YESTERDAY
// ==========================================================

function yesterdaySnapshot(d) {

  const net =
    firstNum(
      d,
      [
        "yesterday",
        "yesterday.net",
        "prevDay.net",
        "previousDay.net",
        "dayYesterday.net",
        "stats.yesterday.net",
        "stacks.all.yesterday"
      ]
    )


  const trades =
    firstNum(
      d,
      [
        "yesterday.trades",
        "prevDay.trades",
        "previousDay.trades",
        "stats.yesterday.trades",
        "yesterdayTrades",
        "stacks.all.yesterdayTrades"
      ]
    )


  const winrate =
    firstNum(
      d,
      [
        "yesterday.winrate",
        "prevDay.winrate",
        "previousDay.winrate",
        "stats.yesterday.winrate",
        "yesterdayWinrate",
        "stacks.all.yesterdayWinrate"
      ]
    )


  const pf =
    firstNum(
      d,
      [
        "yesterday.pf",
        "prevDay.pf",
        "previousDay.pf",
        "stats.yesterday.pf",
        "yesterdayPf",
        "stacks.all.yesterdayPf"
      ]
    )


  const ev =
    firstNum(
      d,
      [
        "stacks.eval.yesterday",
        "eval.yesterday",
        "yesterday.eval"
      ]
    )


  const fu =
    firstNum(
      d,
      [
        "stacks.funded.yesterday",
        "funded.yesterday",
        "yesterday.funded"
      ]
    )


  return {

    net,

    trades,

    winrate,

    pf,

    ev,

    fu

  }

}


// ==========================================================
// EVAL / FUNDED SPLIT
// ==========================================================
//
// D-105 · Één bron voor de splitrij, in alle vier de standen (today · yesterday
// · week · total). Twee doorsneden:
//
//   funded  → SALDO-ontwikkeling in dollars — de period-net van de funded-stack.
//   eval    → ACCOUNTONTWIKKELING in aantallen — de 50k-genormaliseerde tellers
//             uit `d.eval_stats.counts_50k_eq`. Geen bedragen. D-74 verbiedt
//             eval-saldo's op publieke oppervlakken; dit widget staat op een
//             auth-gated endpoint maar is Ferry's dagelijkse oppervlak.
//
// De eval-half is een STAND (snapshot van de vloot nu), geen periode-delta —
// we hebben vandaag geen historische snapshots om "passed op einde van dag X"
// tegen te zetten. Ferry's ask van 27-09 (antwoord 11) noemt het bewust
// "accountontwikkeling" en niet "eval-P&L", en een stand hoort daar bij tot
// een historische bron beschikbaar is.
//
// Format eval-half: `<passed>p·<breached>b` in 50k-eq (bv. "6p·1b"). Beide 0
// → "—". Format funded-half: `moneyK(bedrag)` of "—" als er geen bedrag is.
function evalFundedSplit(d, fundedAmount) {

  const counts =
    (d.eval_stats || {}).counts_50k_eq || {}

  const passed =
    num(counts.passed, 0)

  const breached =
    num(counts.breached, 0)

  const evText =
    (passed === 0 && breached === 0)
      ? "—"
      : (
          fmtCount(passed) + "p·" + fmtCount(breached) + "b"
        )

  const fuText =
    (fundedAmount === null || fundedAmount === undefined)
      ? "—"
      : moneyK(fundedAmount)

  return {

    label:
      "Eval / Funded",

    a:
      evText,

    b:
      fuText

  }

}


// Ronding waarmee 50k-eq getallen leesbaar blijven zonder onwaar precies te
// worden: onder 10 → één decimaal (2.5), 10 en hoger → geheel (12). Nul valt
// hier niet doorheen — die filtert `evalFundedSplit` er eerder al uit.
function fmtCount(n) {

  const v =
    Number(n || 0)

  return Math.abs(v) < 10
    ? v.toFixed(1)
    : String(Math.round(v))

}


// D-105 · ISO-datum ("2026-09-25") → korte weergave ("Fri 25 Sep"). Ongeldige
// input → null zodat de aanroeper kan terugvallen. Wij vermijden bewust een
// locale-afhankelijke format — de widget-strings zijn EN.
const WEEKDAYS =
  ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

const MONTHS =
  ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

function fmtSessionDate(iso) {

  if (
    typeof iso !== "string" ||
    iso.length < 10
  ) {
    return null
  }

  const d =
    new Date(iso + "T12:00:00Z")

  if (
    isNaN(d.getTime())
  ) {
    return null
  }

  return (
    WEEKDAYS[d.getUTCDay()] +
    " " +
    d.getUTCDate() +
    " " +
    MONTHS[d.getUTCMonth()]
  )

}


// ==========================================================
// SPARKLINE
// ==========================================================

function sparkline(
  vals,
  width,
  height
) {

  const dc =
    new DrawContext()

  dc.size =
    new Size(
      width,
      height
    )

  dc.opaque =
    false

  dc.respectScreenScale =
    true


  if (
    !vals ||
    vals.length < 2
  ) {

    return dc.getImage()

  }


  const mn =
    Math.min(...vals)

  const mx =
    Math.max(...vals)


  function buildPath() {

    const p =
      new Path()


    vals.forEach(
      (v, i) => {

        const x =
          i /
          (vals.length - 1) *
          width


        const y =
          height -
          (
            (v - mn) /
            (mx - mn || 1)
          ) *
          (height - 8) -
          4


        if (i === 0) {

          p.move(
            new Point(x, y)
          )

        }

        else {

          p.addLine(
            new Point(x, y)
          )

        }

      }
    )


    return p

  }


  // glow
  dc.addPath(
    buildPath()
  )

  dc.setStrokeColor(
    new Color(
      "#FF7E16",
      0.20
    )
  )

  dc.setLineWidth(7)

  dc.strokePath()


  // main line
  dc.addPath(
    buildPath()
  )

  dc.setStrokeColor(
    C.orange
  )

  dc.setLineWidth(2.5)

  dc.strokePath()


  return dc.getImage()

}


// ==========================================================
// MODE
// ==========================================================

function detectMode() {

  const p =
    (
      args.widgetParameter ||
      ""
    )
      .toString()
      .trim()
      .toLowerCase()


  if (
    [
      "today",
      "yesterday",
      "week",
      "total"
    ]
      .includes(p)
  ) {

    return p

  }


  // fallback via scriptnaam

  let nm = ""


  try {

    nm =
      (
        Script.name() ||
        ""
      )
        .toLowerCase()

  }

  catch (e) {}


  if (
    nm.includes("yesterday")
  ) {

    return "yesterday"

  }


  if (
    nm.includes("today")
  ) {

    return "today"

  }


  if (
    nm.includes("week")
  ) {

    return "week"

  }


  if (
    nm.includes("total")
  ) {

    return "total"

  }


  return "total"

}


// ==========================================================
// LOAD DATA
// ==========================================================

const d =
  await getData()


const mode =
  detectMode()


// ==========================================================
// BUILD VIEW
// ==========================================================

let title
let lbl
let big
let breached = 0
let rows = []
let split = null


// ==========================================================
// TODAY
// ==========================================================

if (
  mode === "today"
) {

  const t =
    todaySnapshot(d)


  const all =
    (
      d.stacks || {}
    ).all || {}


  title =
    "TODAY"

  lbl =
    "Today"

  big =
    t.net


  breached =
    num(
      all.breached,
      0
    )


  rows = [

    [
      "Trades",

      t.trades === null
        ? "—"
        : String(t.trades)
    ],

    [
      "Win / PF",

      (
        t.winrate === null
          ? "—"
          : t.winrate + "%"
      )
      +
      " · "
      +
      (
        t.pf === null
          ? "—"
          : pfStr(t.pf)
      )
    ]

  ]


  split =
    evalFundedSplit(d, t.fu)

}


// ==========================================================
// YESTERDAY
// ==========================================================

else if (
  mode === "yesterday"
) {

  const y =
    yesterdaySnapshot(d)


  const all =
    (
      d.stacks || {}
    ).all || {}


  title =
    "LAST SESSION"

  // D-105 · lbl toont de daadwerkelijke sessiedag ("Fri 26 Sep") als de API
  // hem meestuurt onder `yesterday.session_date`. Dat is de laatste dag mét
  // activiteit, niet de vorige kalenderdag — op maandag is dat vrijdag, na
  // een stille dag schuift hij door. Zonder datum val je terug op de generieke
  // tekst, dan is de label geen leugen maar wel minder scherp.
  lbl =
    fmtSessionDate(
      (d.yesterday || {}).session_date
    ) || "Last session"


  // Geen data beschikbaar?
  if (
    y.net === null
  ) {

    big = 0


    rows = [

      [
        "Status",
        "No data"
      ],

      [
        "Endpoint",
        "Last session missing"
      ]

    ]

  }

  else {

    big =
      y.net


    rows = [

      [
        "Trades",

        y.trades === null
          ? "—"
          : String(y.trades)
      ],

      [
        "Win / PF",

        (
          y.winrate === null
            ? "—"
            : y.winrate + "%"
        )
        +
        " · "
        +
        (
          y.pf === null
            ? "—"
            : pfStr(y.pf)
        )
      ]

    ]


    split =
      evalFundedSplit(
        d,
        y.fu === null ? null : y.fu
      )

  }


  breached =
    num(
      all.breached,
      0
    )

}


// ==========================================================
// WEEK
// ==========================================================

else if (
  mode === "week"
) {

  const wk =
    d.week || {}


  const all =
    (
      d.stacks || {}
    ).all || {}


  title =
    "WEEK"

  lbl =
    "This week"

  big =
    num(
      wk.net,
      0
    )


  breached =
    num(
      all.breached,
      0
    )


  rows = [

    [
      "Today",

      moneyK(
        todaySnapshot(d).net
      )
    ],

    [
      "Trades",

      String(
        num(
          wk.trades,
          0
        )
      )
    ],

    [
      "Win / PF",

      num(
        wk.winrate,
        0
      )
      +
      "% · "
      +
      pfStr(
        wk.pf
      )
    ]

  ]


  // D-105 · Eval/Funded-splitrij hoort ook in de week-stand (antwoord 11).
  // Funded-half = week-net van de funded-stack; eval-half = accountontwikkeling
  // (huidige 50k-eq snapshot — dat is een stand, geen periode-delta).
  const funded =
    d.stacks && d.stacks.funded || {}

  split =
    evalFundedSplit(
      d,
      typeof funded.week === "number" ? funded.week : null
    )

}


// ==========================================================
// TOTAL
// ==========================================================

else {

  const all =
    (
      d.stacks || {}
    ).all || {}


  title =
    "TOTAL"

  lbl =
    "All-time"

  big =
    num(
      all.realized,
      0
    )


  breached =
    num(
      all.breached,
      0
    )


  rows = [

    [
      "Week",

      moneyK(
        num(
          all.week,
          0
        )
      )
    ],

    [
      "Win / PF",

      num(
        all.winrate,
        0
      )
      +
      "% · "
      +
      pfStr(
        all.pf
      )
    ],

    [
      "Accounts",

      num(
        all.accounts,
        0
      )
      +
      " · "
      +
      num(
        all.breached,
        0
      )
      +
      " br"
    ]

  ]


  // D-105 · Eval/Funded-splitrij hoort ook in de total-stand (antwoord 11).
  // Funded-half = all-time realized van de funded-stack; eval-half = accountontwikkeling.
  const funded =
    d.stacks && d.stacks.funded || {}

  split =
    evalFundedSplit(
      d,
      typeof funded.realized === "number" ? funded.realized : null
    )

}


// ==========================================================
// WIDGET
// ==========================================================

const w =
  new ListWidget()


w.url =
  DASHBOARD


w.refreshAfterDate =
  new Date(
    Date.now() +
    5 * 60 * 1000
  )


w.setPadding(
  13,
  13,
  11,
  13
)


// ==========================================================
// BACKGROUND
// ==========================================================

const bg =
  new LinearGradient()


bg.locations =
  [
    0,
    0.55,
    1
  ]


bg.startPoint =
  new Point(
    0,
    0
  )


bg.endPoint =
  new Point(
    1,
    1
  )


bg.colors = [

  new Color(
    "#111114"
  ),

  new Color(
    "#08080A"
  ),

  new Color(
    "#020203"
  )

]


w.backgroundGradient =
  bg


// ==========================================================
// HEADER
// ==========================================================

const head =
  w.addStack()


head.layoutHorizontally()

head.centerAlignContent()


const header =
  head.addText(
    "MEX · " +
    title
  )


header.font =
  Font.boldSystemFont(11)


header.textColor =
  C.orange


head.addSpacer()


if (
  d._demo
) {

  const dm =
    head.addText(
      "DEMO"
    )

  dm.font =
    Font.boldSystemFont(7)

  dm.textColor =
    C.orangeLight


  head.addSpacer(5)

}


const dot =
  head.addText(
    "●"
  )


dot.font =
  Font.systemFont(9)


dot.textColor =
  breached > 0
    ? C.bad
    : C.ok


w.addSpacer(5)


// ==========================================================
// LABEL
// ==========================================================

const smallLabel =
  w.addText(lbl)


smallLabel.font =
  Font.systemFont(9)


smallLabel.textColor =
  C.sub


// ==========================================================
// MAIN NUMBER
// ==========================================================

const pnl =
  w.addText(
    mode === "yesterday" &&
    yesterdaySnapshot(d).net === null

      ? "—"

      : money(big)
  )


pnl.font =
  Font.boldSystemFont(22)


pnl.textColor =

  big >= 0
    ? C.ok
    : C.bad


pnl.minimumScaleFactor =
  0.72


pnl.lineLimit =
  1


w.addSpacer(4)


// ==========================================================
// SPARKLINE
// ==========================================================

const spark =
  w.addImage(

    sparkline(
      d.spark,
      120,
      24
    )

  )


spark.resizable =
  false


w.addSpacer(5)


// ==========================================================
// DIVIDER
// ==========================================================

const divider =
  w.addStack()


divider.size =
  new Size(
    0,
    1
  )


divider.backgroundColor =
  new Color(
    "#FF7E16",
    0.22
  )


w.addSpacer(5)


// ==========================================================
// ROWS
// ==========================================================

for (
  const [key, value]
  of rows
) {

  const r =
    w.addStack()


  r.layoutHorizontally()

  r.centerAlignContent()


  const a =
    r.addText(key)


  a.font =
    Font.systemFont(9)


  a.textColor =
    C.sub


  r.addSpacer()


  const b =
    r.addText(value)


  b.font =
    Font.boldSystemFont(10)


  b.textColor =
    C.txt


  b.lineLimit =
    1


  b.minimumScaleFactor =
    0.72


  w.addSpacer(2)

}


// ==========================================================
// SPLIT
// ==========================================================

if (split) {

  const r =
    w.addStack()


  r.layoutHorizontally()

  r.centerAlignContent()


  const a =
    r.addText(
      split.label
    )


  a.font =
    Font.systemFont(9)


  a.textColor =
    C.sub


  r.addSpacer()


  const ev =
    r.addText(
      split.a
    )


  ev.font =
    Font.boldSystemFont(10)


  ev.textColor =
    C.orange


  const sep =
    r.addText(
      " / "
    )


  sep.font =
    Font.systemFont(9)


  sep.textColor =
    C.dim


  const funded =
    r.addText(
      split.b
    )


  funded.font =
    Font.boldSystemFont(10)


  funded.textColor =
    C.orangeLight

}


// ==========================================================
// PRESENT
// ==========================================================

if (
  config.runsInWidget
) {

  Script.setWidget(w)

}

else {

  await w.presentSmall()

}


Script.complete()