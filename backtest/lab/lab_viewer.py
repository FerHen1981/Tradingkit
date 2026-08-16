"""Backtest Lab cockpit — a stdlib HTTP view on the data room (bck.mex-traders.com).

Reads $LAB_DIR/index.json + results/<run_id>/ and renders the runs in the MEX
house style. Lets you upload a raw platform export straight from the browser:
it streams to disk, normalizes to the canonical schema, and catalogs it — no scp.

No numpy/pandas: the dashboard reads JSON and the upload path uses the stdlib
normalizer/catalog. Run:  LAB_DIR=/data/lab python -m backtest.lab.lab_viewer
Env: LAB_PORT (8090), LAB_PASSWORD (owner gate; unset = open), LAB_SECRET.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .datasets import write_catalog
from .insights import build_journey
from .normalize import to_canonical
from .paths import datasets_dir, ensure_dirs, results_dir
from .runs import load_index

_PASSWORD = os.environ.get("LAB_PASSWORD", "")
_SECRET = (os.environ.get("LAB_SECRET", "") or "mex-lab-dev-secret").encode()
_PORT = int(os.environ.get("LAB_PORT", "8090"))
_STARTED = time.monotonic()


# --------------------------------------------------------------------------- #
# Auth (optional signed cookie; disabled when LAB_PASSWORD is unset)
# --------------------------------------------------------------------------- #
def _sign(v: str) -> str:
    return hmac.new(_SECRET, v.encode(), hashlib.sha256).hexdigest()


def _make_cookie() -> str:
    exp = str(int(time.time()) + 7 * 86400)
    return f"{exp}.{_sign(exp)}"


def _cookie_ok(c: str) -> bool:
    try:
        exp, sig = c.split(".", 1)
        return hmac.compare_digest(sig, _sign(exp)) and int(exp) > time.time()
    except Exception:
        return False


def _authed(handler: "Handler") -> bool:
    if not _PASSWORD:
        return True
    raw = handler.headers.get("Cookie", "")
    for part in raw.split(";"):
        if part.strip().startswith("labauth="):
            return _cookie_ok(part.strip()[len("labauth="):])
    return False


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def _runs() -> list[dict]:
    idx = load_index()
    idx.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return idx


def _run_detail(run_id: str) -> dict | None:
    d = results_dir() / run_id
    rj = d / "run.json"
    if not rj.exists():
        return None
    try:
        return json.loads(rj.read_text())
    except Exception:
        return None


def _fleet_stats(runs: list[dict]) -> dict:
    assets = sorted({r.get("asset", "") for r in runs if r.get("asset")})
    strats = sorted({r.get("strategy", "") for r in runs if r.get("strategy")})
    best = None
    for r in runs:
        pf = (r.get("kpis") or {}).get("profit_factor")
        if pf is not None and (best is None or pf > best.get("kpis", {}).get("profit_factor", -1)):
            best = r
    return {"runs": len(runs), "assets": assets, "strategies": strats,
            "best": best, "latest": runs[0] if runs else None}


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "MEXLab/1.0"

    def log_message(self, *a):  # quiet
        pass

    # -- helpers --
    def _send(self, code, body, ctype="text/html; charset=utf-8", headers=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, default=str), "application/json")

    # -- GET --
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/healthz":
            return self._send(200, "ok", "text/plain")
        if u.path == "/favicon.svg":
            return self._send(200, _FAVICON, "image/svg+xml",
                              {"Cache-Control": "public, max-age=86400"})
        if u.path == "/login":
            return self._send(200, LOGIN_HTML)
        if not _authed(self):
            return self._send(200, LOGIN_HTML)
        if u.path == "/":
            return self._send(200, PAGE_HTML)
        if u.path == "/api/runs":
            runs = _runs()
            return self._json({"runs": runs, "stats": _fleet_stats(runs),
                               "status": {"uptime_s": int(time.monotonic() - _STARTED),
                                          "lab_dir": str(datasets_dir().parent),
                                          "auth": bool(_PASSWORD)}})
        if u.path == "/api/run":
            rid = (q.get("id") or [""])[0]
            det = _run_detail(rid)
            return self._json(det or {"error": "not found"}, 200 if det else 404)
        if u.path == "/api/journey":
            strat = (q.get("strategy") or [""])[0]
            return self._json(build_journey(_runs(), strat or None))
        return self._send(404, "not found", "text/plain")

    # -- POST --
    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/login":
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8", "replace")
            pw = urllib.parse.parse_qs(body).get("password", [""])[0]
            if _PASSWORD and hmac.compare_digest(pw, _PASSWORD):
                return self._send(303, "", headers={
                    "Location": "/", "Set-Cookie": f"labauth={_make_cookie()}; Path=/; HttpOnly; SameSite=Lax"})
            return self._send(200, LOGIN_HTML.replace("<!--ERR-->", "Wrong password."))
        if not _authed(self):
            return self._json({"error": "unauthorized"}, 401)
        if u.path == "/api/upload":
            return self._upload(q)
        return self._send(404, "not found", "text/plain")

    def _upload(self, q):
        name = (q.get("name") or ["dataset"])[0]
        symbol = (q.get("symbol") or [""])[0]
        # sanitize name -> a datasets/<name>/ folder
        safe = "".join(c for c in name if c.isalnum() or c in "-_") or "dataset"
        ddir = datasets_dir() / safe
        ddir.mkdir(parents=True, exist_ok=True)
        raw = ddir / "raw.csv"
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return self._json({"error": "empty body"}, 400)
        # stream body -> disk (chunked; big-file friendly)
        remaining, wrote = length, 0
        with open(raw, "wb") as f:
            while remaining > 0:
                chunk = self.rfile.read(min(1 << 20, remaining))
                if not chunk:
                    break
                f.write(chunk)
                remaining -= len(chunk)
                wrote += len(chunk)
        try:
            canon = ddir / "canonical.csv"
            _, rows = to_canonical(raw, canon)
            mpath = write_catalog(canon, symbol=symbol)
            manifest = json.loads(Path(mpath).read_text())
        except Exception as e:
            return self._json({"error": f"normalize/catalog failed: {e}",
                               "bytes": wrote}, 422)
        return self._json({"ok": True, "dataset": safe, "rows": rows,
                           "bytes": wrote, "canonical": str(canon), "manifest": manifest})


def main():
    ensure_dirs()
    srv = ThreadingHTTPServer(("0.0.0.0", _PORT), Handler)
    print(f"MEX Lab cockpit on :{_PORT}  (LAB_DIR={datasets_dir().parent}, "
          f"auth={'on' if _PASSWORD else 'OFF'})")
    srv.serve_forever()


# --------------------------------------------------------------------------- #
# Templates (MEX house style)
# --------------------------------------------------------------------------- #
_CSS = """
:root{
 --abyss:#030F28;--deep:#081D46;--surface:#0E2A5E;--line:rgba(242,235,218,.17);
 --sand:#F2EBDA;--sub:rgba(242,235,218,.60);--dim:rgba(242,235,218,.42);
 --gold:#E8B54F;--gold2:#B98526;--azure:#5AA2FF;--rose:#E0796E;
 --panel:rgba(14,42,94,.42);
 --display:'Bricolage Grotesque',system-ui,sans-serif;
 --body:'Instrument Sans',system-ui,sans-serif;--mono:'JetBrains Mono',ui-monospace,monospace}
*{box-sizing:border-box}
body{margin:0;color:var(--sand);font-family:var(--body);font-size:14px;line-height:1.55;background:var(--abyss)}
body::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;background:
 radial-gradient(1000px 560px at 84% -10%,rgba(232,181,79,.16),transparent 60%),
 radial-gradient(820px 620px at -2% 40%,rgba(90,162,255,.13),transparent 62%),
 linear-gradient(180deg,#030F28,#061735 45%,#030F28)}
a{color:var(--azure)}.wrap{max-width:1180px;margin:0 auto;padding:22px}
.brand{display:flex;align-items:center;gap:9px}
.brand .wm{font-family:var(--display);font-weight:800;letter-spacing:-.03em;font-size:18px;color:var(--sand)}
.brand .wm em{font-style:normal;font-weight:400;letter-spacing:.10em;margin-left:.35em;color:var(--sub)}
.tag-lab{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--gold);border:1px solid var(--line);padding:3px 8px;border-radius:2px;margin-left:12px}
.muted{color:var(--sub);font-family:var(--mono);font-size:11px;letter-spacing:.04em}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:14px 18px;min-width:130px}
.kpi .v{font-family:var(--display);font-size:26px;font-weight:600;letter-spacing:-.02em;color:var(--gold)}
.kpi .l{font-family:var(--mono);font-size:10px;color:var(--sub);text-transform:uppercase;letter-spacing:.14em;margin-top:6px}
.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:14px 0}
select,input,button{background:var(--deep);color:var(--sand);border:1px solid var(--line);border-radius:2px;padding:8px 11px;font-size:13px;font-family:var(--body)}
button{cursor:pointer;font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase}
button.go{background:linear-gradient(120deg,var(--gold),#F3CE7C);color:#0B1428;border:none;font-weight:700}
button.go:hover{filter:brightness(1.06)}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{padding:9px 10px;text-align:right;border-bottom:1px solid rgba(242,235,218,.08);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--sub);font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.12em;cursor:pointer}
tr:hover td{background:rgba(14,42,94,.5)}
.pill{padding:2px 8px;border-radius:2px;font-family:var(--mono);font-size:10px}
.pos{color:var(--azure)}.neg{color:var(--rose)}
.tag{background:var(--deep);color:var(--sub);padding:2px 8px;border-radius:2px;font-family:var(--mono);font-size:10px;letter-spacing:.06em}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:18px;margin-top:16px}
.up{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.foot{color:var(--dim);font-family:var(--mono);font-size:11px;margin-top:22px;border-top:1px solid var(--line);padding-top:12px}
#drop{border:1px dashed var(--line);border-radius:3px;padding:14px;text-align:center;color:var(--sub);flex:1;min-width:220px;cursor:pointer}
.hidden{display:none}#msg{font-size:12px}
.lens{border:1px solid var(--line);border-radius:4px;padding:14px 16px;margin-top:10px;background:rgba(8,29,70,.32)}
.lens h3{margin:0 0 2px;font-family:var(--display);font-weight:600;font-size:15px;color:var(--gold);letter-spacing:-.01em}
.lens .q{color:var(--sub);font-size:12px;margin-bottom:8px}
.ins{display:flex;gap:9px;align-items:flex-start;padding:5px 0;font-size:13px;border-top:1px solid rgba(242,235,218,.07)}
.ins:first-of-type{border-top:none}.dot{width:7px;height:7px;border-radius:50%;margin-top:6px;flex:none}
.t-good{background:var(--azure)}.t-warn{background:var(--gold)}.t-bad{background:var(--rose)}.t-info{background:var(--sub)}
.verdict{border-radius:3px;padding:12px 14px;font-weight:600;border:1px solid}
.v-good{background:rgba(90,162,255,.10);border-color:rgba(90,162,255,.40);color:var(--azure)}
.v-warn{background:rgba(232,181,79,.10);border-color:rgba(232,181,79,.40);color:var(--gold)}
.v-bad{background:rgba(224,121,110,.10);border-color:rgba(224,121,110,.40);color:var(--rose)}
.v-info{background:rgba(14,42,94,.50);border-color:var(--line);color:var(--sub)}
.lensrow{font-family:var(--mono);font-size:10px;color:var(--sub);margin-top:6px;letter-spacing:.06em}
"""

# Brand mark (the gold "M") for the header, and the favicon (served at /favicon.svg).
_MARK = ('<svg viewBox="0 0 100 100" width="22" height="22" aria-hidden="true">'
         '<defs><linearGradient id="navgold" x1="0" y1="0" x2="1" y2="1">'
         '<stop offset="0" stop-color="#E8B54F"/><stop offset="1" stop-color="#B98526"/></linearGradient></defs>'
         '<path d="M-10.55,69.29 L100.15,69.29 L100.15,72.93 L-10.55,72.93 Z" fill="#F2EBDA" opacity=".42"/>'
         '<path d="M16.85,78 L21.65,41.87 L40.46,69.29 L51.20,69.29 L78,42.03 L83.10,78 L94.92,78 '
         'L86.27,16.94 L46.29,57.59 L46.63,57.59 L14.07,10.13 L5.05,78 Z" fill="url(#navgold)"/></svg>')
_BRAND = f'<a class=brand href="/">{_MARK}<span class=wm>MEX<em>TRADERS</em></span></a>'
_FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#E8B54F"/><stop offset="1" stop-color="#B98526"/></linearGradient></defs>'
            '<rect width="100" height="100" fill="#030F28"/>'
            '<path d="M2,69.95 L98,69.95 L98,75.08 L2,75.08 Z" fill="#F2EBDA" opacity=".52"/>'
            '<path d="M15.57,79 L20.56,41.48 L40.10,69.95 L51.24,69.95 L79.08,41.65 L84.37,79 L96.64,79 '
            'L87.66,15.59 L46.15,57.80 L46.50,57.80 L12.69,8.52 L3.32,79 Z" fill="url(#g)"/></svg>')
_HEAD = ('<meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">'
         '<link rel="icon" type="image/svg+xml" href="/favicon.svg">'
         '<link rel=preconnect href="https://fonts.googleapis.com">'
         '<link rel=preconnect href="https://fonts.gstatic.com" crossorigin>'
         '<link rel=stylesheet href="https://fonts.googleapis.com/css2?'
         'family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&'
         'family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap">')

_JS = r"""
const $=s=>document.querySelector(s), money=n=>(n>=0?'+$':'-$')+Math.abs(Math.round(n)).toLocaleString('en-US');
let RUNS=[], STATS={};
function kpi(v,l){return `<div class=kpi><div class=v>${v}</div><div class=l>${l}</div></div>`}
function opt(sel,vals){const cur=sel.value;[...sel.querySelectorAll('option:not(:first-child)')].forEach(o=>o.remove());
  vals.forEach(v=>{const o=document.createElement('option');o.value=o.textContent=v;sel.appendChild(o)});sel.value=cur}
function k(r,path,d){const o=r.kpis||{};return o[path]!==undefined?o[path]:d}
function pfcls(p){return p>=1?'pos':'neg'}
function render(){
  const fa=$('#fAsset').value,fs=$('#fStrat').value,ft=$('#fTf').value,fl=$('#fLens').value;
  const rows=RUNS.filter(r=>(!fa||r.asset==fa)&&(!fs||r.strategy==fs)&&(!ft||r.timeframe==ft)&&(!fl||r.lens==fl));
  $('#count').textContent=rows.length+' / '+RUNS.length+' runs';
  $('#rows').innerHTML=rows.map(r=>{
    const pf=k(r,'profit_factor',null),net=k(r,'net_profit',0),exp=k(r,'expectancy',0),
      win=k(r,'win_rate_pct',null),tr=k(r,'trades',0),dd=k(r,'max_drawdown',0);
    return `<tr>
      <td title="${r.run_id}">${(r.run_id||'').slice(0,42)}</td><td>${r.asset||''}</td>
      <td>${r.strategy||''}</td><td><span class=tag>${r.timeframe||''}</span></td>
      <td><span class=tag>${r.lens||''}</span></td><td>${tr}</td>
      <td>${win==null?'':win.toFixed(0)}</td>
      <td class=${pf==null?'':pfcls(pf)}>${pf==null?'':pf.toFixed(2)}</td>
      <td class=${exp>=0?'pos':'neg'}>${exp?money(exp):''}</td>
      <td class=${net>=0?'pos':'neg'}>${net?money(net):''}</td>
      <td>${dd?'$'+Math.round(dd).toLocaleString():''}</td>
      <td class=muted>${(r.created_at||'').slice(0,16).replace('T',' ')}</td></tr>`}).join('');
}
function fillKpis(){
  const b=STATS.best,bl=b?((b.kpis||{}).profit_factor||0).toFixed(2):'—';
  $('#kpis').innerHTML=kpi(STATS.runs||0,'runs')+kpi((STATS.assets||[]).length,'assets')
    +kpi((STATS.strategies||[]).length,'strategies')+kpi(bl,'best PF')
    +kpi((STATS.latest&&STATS.latest.timeframe)||'—','latest TF');
}
function renderJourney(j){
  const v=j.verdict||{};$('#verdict').innerHTML=`<div class="verdict v-${v.tone||'info'}">${v.text||''}</div>`;
  $('#lenses').innerHTML=(j.lenses||[]).map(L=>{
    const ins=(L.insights||[]).map(i=>`<div class=ins><span class="dot t-${i.tone}"></span><span>${i.text}</span></div>`).join('');
    const tfs=(L.runs||[]).map(r=>r.timeframe).join(', ');
    return `<div class=lens><h3>${L.lens.toUpperCase()}</h3><div class=q>${L.question}</div>${ins}
      ${tfs?`<div class=lensrow>runs: ${tfs}</div>`:''}</div>`}).join('');
}
async function loadJourney(strat){
  if(!strat){$('#verdict').innerHTML='';$('#lenses').innerHTML='<div class=muted>No strategy yet.</div>';return}
  const j=await (await fetch('/api/journey?strategy='+encodeURIComponent(strat))).json();renderJourney(j);
}
$('#jStrat').addEventListener('change',e=>loadJourney(e.target.value));
async function load(){
  const j=await (await fetch('/api/runs')).json();RUNS=j.runs||[];STATS=j.stats||{};
  opt($('#fAsset'),STATS.assets||[]);opt($('#fStrat'),STATS.strategies||[]);
  opt($('#fTf'),[...new Set(RUNS.map(r=>r.timeframe).filter(Boolean))]);
  opt($('#fLens'),[...new Set(RUNS.map(r=>r.lens).filter(Boolean))]);
  fillKpis();render();
  // Journey strategy picker
  const strats=STATS.strategies||[];const js=$('#jStrat');const cur=js.value;
  js.innerHTML=strats.map(s=>`<option>${s}</option>`).join('');
  const pick=cur&&strats.includes(cur)?cur:strats[0];if(pick){js.value=pick;loadJourney(pick);} else loadJourney(null);
  $('#sub').textContent='LAB_DIR '+(j.status.lab_dir||'')+(j.status.auth?' · secured':' · open');
  $('#foot').textContent='uptime '+Math.round((j.status.uptime_s||0)/60)+'m · reads index.json';
}
['#fAsset','#fStrat','#fTf','#fLens'].forEach(s=>$(s).addEventListener('change',render));
document.querySelectorAll('#tbl th').forEach(th=>th.addEventListener('click',()=>{
  const key=th.dataset.k,map={trades:'trades',win:'win_rate_pct',pf:'profit_factor',exp:'expectancy',net:'net_profit',dd:'max_drawdown'};
  if(map[key])RUNS.sort((a,b)=>((b.kpis||{})[map[key]]||-1e9)-((a.kpis||{})[map[key]]||-1e9));
  else RUNS.sort((a,b)=>String(b[key]||'').localeCompare(String(a[key]||'')));render();}));
// upload
$('#drop').addEventListener('click',()=>$('#file').click());
$('#file').addEventListener('change',e=>{const f=e.target.files[0];if(f){$('#drop').textContent=f.name+' ('+(f.size/1e6).toFixed(1)+' MB)';
  if(!$('#dsname').value)$('#dsname').value=f.name.replace(/\.[^.]+$/,'')}});
$('#upbtn').addEventListener('click',async()=>{
  const f=$('#file').files[0];if(!f){$('#msg').textContent='Choose a file first.';return}
  const name=encodeURIComponent($('#dsname').value||'dataset'),sym=encodeURIComponent($('#dssym').value||'');
  $('#msg').textContent='Uploading '+(f.size/1e6).toFixed(1)+' MB…';
  try{const r=await fetch('/api/upload?name='+name+'&symbol='+sym,{method:'POST',body:f});
    const j=await r.json();
    if(j.ok){$('#msg').innerHTML='<span class=pos>✓ '+j.dataset+': '+j.rows.toLocaleString()+' rows, cataloged.</span>';load();}
    else{$('#msg').innerHTML='<span class=neg>'+(j.error||'failed')+'</span>';}
  }catch(e){$('#msg').innerHTML='<span class=neg>'+e+'</span>';}
});
load();
"""

LOGIN_HTML = f"""<!doctype html><html><head>{_HEAD}
<title>MEX Traders · Lab</title><style>{_CSS}</style></head><body><div class=wrap>
<div style="display:flex;align-items:center">{_BRAND}<span class=tag-lab>Backtest Lab</span></div>
<div class=panel style="max-width:340px">
<form method=post action=/login><div class=muted style="margin-bottom:8px">Owner login</div>
<div style="color:var(--rose);font-size:12px;margin-bottom:6px"><!--ERR--></div>
<input type=password name=password placeholder=Password autofocus style="width:100%">
<button class=go style="width:100%;margin-top:8px">Enter</button></form></div>
<div class=foot>Set LAB_PASSWORD to enable the gate.</div></div></body></html>"""

PAGE_HTML = f"""<!doctype html><html><head>{_HEAD}
<title>MEX Traders · Lab</title><style>{_CSS}</style></head><body><div class=wrap>
<div style="display:flex;justify-content:space-between;align-items:center">
  <div style="display:flex;align-items:center">{_BRAND}<span class=tag-lab>Backtest Lab</span></div>
  <span class=muted id=sub></span></div>
<div class=kpis id=kpis></div>

<div class=panel><div style="display:flex;justify-content:space-between;align-items:center">
  <b>Upload dataset</b><span class=muted style="font-size:12px">raw export → normalized → cataloged</span></div>
  <div class=up style="margin-top:10px">
    <input id=dsname placeholder="dataset name (e.g. NQ_1m)" style="width:180px">
    <input id=dssym placeholder="symbol (NQ)" style="width:110px">
    <label id=drop>Click to choose a .csv export<input id=file type=file accept=.csv class=hidden></label>
    <button class=go id=upbtn>Upload</button>
  </div><div id=msg class=muted style="margin-top:8px"></div>
</div>

<div class=panel id=journey>
  <div style="display:flex;justify-content:space-between;align-items:center">
    <b>Journey</b>
    <select id=jStrat style="min-width:200px"></select>
  </div>
  <div id=verdict style="margin:10px 0"></div>
  <div id=lenses></div>
</div>

<div class=bar>
  <select id=fAsset><option value="">All assets</option></select>
  <select id=fStrat><option value="">All strategies</option></select>
  <select id=fTf><option value="">All timeframes</option></select>
  <select id=fLens><option value="">All lenses</option></select>
  <span class=muted id=count></span>
</div>
<table id=tbl><thead><tr>
  <th data-k=run_id>Run</th><th data-k=asset>Asset</th><th data-k=strategy>Strategy</th>
  <th data-k=timeframe>TF</th><th data-k=lens>Lens</th><th data-k=trades>Trades</th>
  <th data-k=win>Win%</th><th data-k=pf>PF</th><th data-k=exp>Exp</th>
  <th data-k=net>Net</th><th data-k=dd>MaxDD</th><th data-k=created>When</th>
</tr></thead><tbody id=rows></tbody></table>

<div class=foot id=foot></div></div>
<script>{_JS}</script></body></html>"""

if __name__ == "__main__":
    main()
