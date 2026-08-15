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
:root{--bg:#06171a;--panel:#0b2428;--edge:#123;--txt:#eaf4f1;--sub:#84a8a3;
--gold:#f0b64d;--aqua:#3fd0bd;--ok:#35c88a;--crit:#ef6b53;--watch:#f2a03a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);
font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
a{color:var(--aqua)}.wrap{max-width:1180px;margin:0 auto;padding:20px}
h1{font-size:18px;margin:0;color:var(--aqua);letter-spacing:.5px}
.muted{color:var(--sub)}.kpis{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}
.kpi{background:var(--panel);border:1px solid #16343a;border-radius:12px;padding:12px 16px;min-width:130px}
.kpi .v{font-size:22px;font-weight:700}.kpi .l{font-size:11px;color:var(--sub);text-transform:uppercase;letter-spacing:.6px}
.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:14px 0}
select,input,button{background:var(--panel);color:var(--txt);border:1px solid #1c3d43;
border-radius:8px;padding:7px 10px;font-size:13px}button{cursor:pointer}
button.go{background:var(--aqua);color:#04222; border:none;font-weight:700}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{padding:8px 10px;text-align:right;border-bottom:1px solid #122c31;white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:var(--sub);font-size:11px;
text-transform:uppercase;letter-spacing:.5px;cursor:pointer}tr:hover td{background:#0e2a2f}
.pill{padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700}
.pos{color:var(--ok)}.neg{color:var(--crit)}.tag{background:#123;color:var(--sub);padding:2px 8px;border-radius:6px;font-size:11px}
.panel{background:var(--panel);border:1px solid #16343a;border-radius:12px;padding:16px;margin-top:16px}
.up{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.foot{color:var(--sub);font-size:12px;margin-top:20px;border-top:1px solid #12262b;padding-top:10px}
#drop{border:1px dashed #1c3d43;border-radius:10px;padding:14px;text-align:center;color:var(--sub);flex:1;min-width:220px}
.hidden{display:none}#msg{font-size:12px}
"""

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
async function load(){
  const j=await (await fetch('/api/runs')).json();RUNS=j.runs||[];STATS=j.stats||{};
  opt($('#fAsset'),STATS.assets||[]);opt($('#fStrat'),STATS.strategies||[]);
  opt($('#fTf'),[...new Set(RUNS.map(r=>r.timeframe).filter(Boolean))]);
  opt($('#fLens'),[...new Set(RUNS.map(r=>r.lens).filter(Boolean))]);
  fillKpis();render();
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

LOGIN_HTML = f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>MEX Lab</title><style>{_CSS}</style></head><body><div class=wrap>
<h1>MEX · Backtest Lab</h1><div class=panel style="max-width:340px">
<form method=post action=/login><div class=muted style="margin-bottom:8px">Owner login</div>
<div style="color:var(--crit);font-size:12px;margin-bottom:6px"><!--ERR--></div>
<input type=password name=password placeholder=Password autofocus style="width:100%">
<button class=go style="width:100%;margin-top:8px">Enter</button></form></div>
<div class=foot>Set LAB_PASSWORD to enable the gate.</div></div></body></html>"""

PAGE_HTML = f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>MEX Lab</title><style>{_CSS}</style></head><body><div class=wrap>
<div style="display:flex;justify-content:space-between;align-items:baseline">
  <h1>MEX · Backtest Lab</h1><span class=muted id=sub></span></div>
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
