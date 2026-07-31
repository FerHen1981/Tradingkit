#!/usr/bin/env python3
"""Generate an interactive time-of-day x weekday heatmap for one strategy+asset.

Reuses the repo's backtest package. Writes a self-contained HTML file (publish it
with the Artifact tool) and prints the key read to stdout.

    python3 .claude/skills/heatmap/generate.py --preset EL_DORADO_TUNED \
        --data NQ_1m.csv --symbol NQ --out /tmp/hm.html [--native]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# make the repo's `backtest` package importable regardless of CWD
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)

from backtest import data as data_mod            # noqa: E402
from backtest import indicators as ind_mod       # noqa: E402
from backtest import heatmap as hm               # noqa: E402
from backtest.config import PRESETS, contract    # noqa: E402
from backtest.engine import Engine               # noqa: E402

TEMPLATE = r'''<!-- content only; wrapped at publish -->
<title>__TITLE__</title>
<style>
  :root{--bg:#fff;--surface:#f7f8fa;--ink:#1a1d24;--muted:#6b7280;--line:#e5e7eb;--pos:#2166ac;--neg:#b2182b;--mid:#cbd0d6;}
  @media (prefers-color-scheme:dark){:root{--bg:#0f1216;--surface:#171b21;--ink:#e8eaed;--muted:#9aa2ad;--line:#2a3038;--mid:#3a424c;}}
  :root[data-theme=dark]{--bg:#0f1216;--surface:#171b21;--ink:#e8eaed;--muted:#9aa2ad;--line:#2a3038;--mid:#3a424c;}
  :root[data-theme=light]{--bg:#fff;--surface:#f7f8fa;--ink:#1a1d24;--muted:#6b7280;--line:#e5e7eb;--mid:#cbd0d6;}
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
  .wrap{max-width:1180px;margin:0 auto;padding:24px 20px 60px}
  h1{font-size:20px;margin:0 0 4px} .sub{color:var(--muted);font-size:13px;margin:0 0 18px}
  .controls{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px;align-items:center}
  button.m{background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:7px;padding:6px 11px;font-size:12.5px;cursor:pointer}
  button.m[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
  .scroll{overflow-x:auto} table{border-collapse:separate;border-spacing:2px;margin-top:6px}
  th{font-weight:600;color:var(--muted);font-size:11px;padding:2px 4px;text-align:center} th.rh{text-align:right;padding-right:8px}
  td.cell{width:40px;height:34px;text-align:center;font-size:10.5px;border-radius:4px;color:#fff;cursor:default;font-variant-numeric:tabular-nums}
  td.empty{background:transparent;color:var(--muted);opacity:.25} td.marg{background:var(--surface);color:var(--ink);font-weight:600;border:1px solid var(--line)}
  .legend{display:flex;align-items:center;gap:10px;margin-top:16px;font-size:12px;color:var(--muted)}
  .bar{height:12px;width:220px;border-radius:3px;background:linear-gradient(90deg,var(--neg),var(--mid),var(--pos))}
  .tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--bg);padding:8px 10px;border-radius:7px;font-size:12px;opacity:0;transition:opacity .1s;z-index:9;white-space:nowrap;box-shadow:0 4px 16px rgba(0,0,0,.25)}
  .note{color:var(--muted);font-size:12px;margin-top:20px;max-width:760px}
  .toggle{margin-left:auto;font-size:12px;color:var(--muted);cursor:pointer;background:none;border:1px solid var(--line);border-radius:7px;padding:6px 10px}
</style>
<div class="wrap">
  <h1>__TITLE__</h1>
  <p class="sub">__SUBTITLE__</p>
  <div class="controls" id="ctrl"></div>
  <div class="scroll"><div id="grid"></div></div>
  <div class="legend"><span id="legmin"></span><div class="bar"></div><span id="legmax"></span><span style="margin-left:12px" id="legmet"></span></div>
  <p class="note" id="insight">__INSIGHT__</p>
</div>
<div class="tip" id="tip"></div>
<script>
const CELLS=__PAYLOAD__;
const DAYS=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].filter(d=>CELLS.some(c=>c.weekday===d));
const HOURS=[...Array(24).keys()];
const METRICS={expectancy:{label:"Expectancy $/trade",center:0,fmt:v=>(v>=0?"+":"")+Math.round(v),div:true},
 pf:{label:"Profit factor",center:1,fmt:v=>v.toFixed(2),div:true},
 win_pct:{label:"Win %",center:25,fmt:v=>v.toFixed(0)+"%",div:true},
 net:{label:"Net $ (bucket)",center:0,fmt:v=>(v>=0?"+":"")+(Math.round(v/1000))+"k",div:true},
 trades:{label:"Trade count",center:null,fmt:v=>v,div:false},
 avg_hold_min:{label:"Avg hold (min)",center:null,fmt:v=>Math.round(v),div:false}};
const idx={};CELLS.forEach(c=>idx[c.weekday+"_"+c.hour]=c);
let metric="expectancy";
function lerp(a,b,t){return a.map((x,i)=>Math.round(x+(b[i]-x)*t))}
const NEG=[178,24,43],MIDc=[203,208,214],POS=[33,102,172],LO=[241,243,246],HI=[33,102,172];
function color(v,m){const M=METRICS[m];
 if(!M.div){const vals=CELLS.map(c=>c[m]),mn=Math.min(...vals),mx=Math.max(...vals);return `rgb(${lerp(LO,HI,(v-mn)/(mx-mn||1)).join(",")})`;}
 const vals=CELLS.map(c=>c[m]-M.center),span=Math.max(...vals.map(Math.abs))||1;let t=Math.max(-1,Math.min(1,(v-M.center)/span));
 const c=t<0?lerp(MIDc,NEG,-t):lerp(MIDc,POS,t);return `rgb(${c.join(",")})`;}
function render(){const M=METRICS[metric];let h="<table><thead><tr><th class=rh></th>";
 HOURS.forEach(hr=>h+=`<th>${String(hr).padStart(2,"0")}</th>`);h+="<th class=rh>Σ/day</th></tr></thead><tbody>";
 DAYS.forEach(d=>{h+=`<tr><th class=rh>${d}</th>`;let dn=0;
  HOURS.forEach(hr=>{const c=idx[d+"_"+hr];if(!c){h+=`<td class="cell empty">·</td>`;return}dn+=c.net;
   h+=`<td class="cell" style="background:${color(c[metric],metric)}" data-k="${d}_${hr}">${M.fmt(c[metric])}</td>`;});
  h+=`<td class="cell marg">${(dn>=0?"+":"")+Math.round(dn/1000)}k</td></tr>`;});
 h+="<tr><th class=rh>all</th>";HOURS.forEach(hr=>{const cs=DAYS.map(d=>idx[d+"_"+hr]).filter(Boolean);
  if(!cs.length){h+="<td class='cell empty'>·</td>";return}const tr=cs.reduce((s,c)=>s+c.trades,0),net=cs.reduce((s,c)=>s+c.net,0),e=net/tr;
  h+=`<td class="cell" style="background:${color(e,'expectancy')}">${(e>=0?"+":"")+Math.round(e)}</td>`;});
 h+="<td class=marg></td></tr></tbody></table>";document.getElementById("grid").innerHTML=h;
 document.getElementById("legmet").textContent=M.label;document.getElementById("legmin").textContent=M.div?"◀ worse":"low";
 document.getElementById("legmax").textContent=M.div?"better ▶":"high";bind();}
function bind(){const tip=document.getElementById("tip");document.querySelectorAll("td.cell[data-k]").forEach(td=>{
 td.onmousemove=e=>{const c=idx[td.dataset.k];tip.innerHTML=`<b>${c.weekday} ${String(c.hour).padStart(2,"0")}:00 ET</b><br>trades ${c.trades} · win ${c.win_pct}% · PF ${c.pf}<br>exp ${(c.expectancy>=0?"+":"")+Math.round(c.expectancy)} · net ${(c.net>=0?"+":"")+Math.round(c.net)}<br>hold ${Math.round(c.avg_hold_min)}m · worst ${Math.round(c.worst)}`;
  tip.style.opacity=1;tip.style.left=Math.min(e.clientX+14,innerWidth-190)+"px";tip.style.top=(e.clientY+14)+"px";};
 td.onmouseleave=()=>tip.style.opacity=0;});}
const ctrl=document.getElementById("ctrl");Object.entries(METRICS).forEach(([k,M])=>{const b=document.createElement("button");
 b.className="m";b.textContent=M.label;b.setAttribute("aria-pressed",k===metric);
 b.onclick=()=>{metric=k;document.querySelectorAll("#ctrl button").forEach(x=>x.setAttribute("aria-pressed","false"));b.setAttribute("aria-pressed","true");render();};ctrl.appendChild(b);});
const tg=document.createElement("button");tg.className="toggle";tg.textContent="◐ theme";
tg.onclick=()=>{const r=document.documentElement,cur=r.getAttribute("data-theme");r.setAttribute("data-theme",cur==="dark"?"light":"dark");};ctrl.appendChild(tg);
render();
</script>'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", required=True, choices=list(PRESETS))
    ap.add_argument("--data", required=True)
    ap.add_argument("--symbol", default="NQ")
    ap.add_argument("--out", required=True)
    ap.add_argument("--native", action="store_true", help="use account overlay (default: research)")
    a = ap.parse_args()

    cfg = PRESETS[a.preset].with_(contract=contract(a.symbol))
    df = data_mod.load(a.data)
    ind = ind_mod.compute(df, cfg)
    res = Engine(cfg, df, ind, research_mode=not a.native).run()
    if not res.trades:
        print("No trades — nothing to plot.")
        return

    full = hm.build(res)
    cells = full[["weekday", "wd", "hour", "trades", "win_pct", "pf",
                  "expectancy", "net", "avg_hold_min", "worst"]].to_dict("records")

    mh = hm.marginal(res, "hour").sort_values("expectancy", ascending=False)
    best = list(zip(mh["hour"].head(5), mh["expectancy"].head(5).round(0)))
    worst = list(zip(mh["hour"].tail(5), mh["expectancy"].tail(5).round(0)))
    insight = (f"<b>Read:</b> best hours {', '.join(f'{h:02d} (+{int(e)})' for h,e in best)} ET; "
               f"worst {', '.join(f'{h:02d} ({int(e)})' for h,e in reversed(worst))} ET. "
               "In-sample — any hour-filter must be walk-forward validated before use.")

    mode = "account overlay" if a.native else "research (all signals)"
    title = f"{a.preset} · {a.symbol} — heatmap by ET hour × weekday"
    sub = (f"{len(res.trades):,} trades · {res.first_time.date()} → {res.last_time.date()} · "
           f"{mode}. Color = selected metric; hover for all axes.")

    html = (TEMPLATE.replace("__PAYLOAD__", json.dumps(cells, default=str))
            .replace("__TITLE__", title).replace("__SUBTITLE__", sub)
            .replace("__INSIGHT__", insight))
    with open(a.out, "w") as f:
        f.write(html)

    print(f"Heatmap written: {a.out}")
    print(f"{a.preset} on {a.symbol}: {len(res.trades):,} trades")
    print("BEST hours (exp $/trade):", best)
    print("WORST hours:", worst)
    mw = hm.marginal(res, "weekday")
    print("Weekday:", mw[["weekday", "trades", "win_pct", "pf", "expectancy", "net"]].to_dict("records"))


if __name__ == "__main__":
    main()
