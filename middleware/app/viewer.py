"""MEX owner cockpit — a read-only live fleet dashboard (app.mex-traders.com).

Zero third-party deps (stdlib http.server only) so it runs on the VPS's Python 3.14 where
FastAPI/pydantic won't build. Reads the SAME routed-log the journal uses, so it shows the
live truth per account: open positions, today's closed trades, realized P&L, and the day's
recap numbers — refreshed every few seconds. Owner-only behind a password + signed cookie.

This is the "Viewer API" seam from ARCHITECTURE.md: a later Next.js face can consume the same
/api/state JSON without rework. Control actions (halt/kill/close) come later.

Env:
  VIEWER_PASSWORD   owner login password (required to enable auth; unset = open, dev only)
  VIEWER_SECRET     secret for signing the session cookie (default derived from password)
  ROUTED_DIR        routed-log dir (default /root/intent-store)
  VIEWER_PORT       listen port (default 8080)
  ROUTED_DAYS       how many routed files back to read (default 2)
"""
from __future__ import annotations

import base64
import glob
import hashlib
import hmac
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .routed_journal import parse_routed_lines, pair_events
from .journal_sync import FRAMEWORK, _ASSET, _phase, _sym_root

log = logging.getLogger("mex.viewer")

_ROUTED_DIR = os.environ.get("ROUTED_DIR", os.environ.get("INTENT_DIR", "/root/intent-store"))
_DAYS = int(os.environ.get("ROUTED_DAYS", "2"))
_PASSWORD = os.environ.get("VIEWER_PASSWORD", "")
_SECRET = (os.environ.get("VIEWER_SECRET") or _PASSWORD or "mex-dev-secret").encode()
_API_TOKEN = os.environ.get("VIEWER_API_TOKEN", "")   # read-only token for the iPhone widget etc.


# ---- state from the routed-log -------------------------------------------------------

def _recent_files() -> list[str]:
    files = sorted(glob.glob(os.path.join(_ROUTED_DIR, "routed_*.jsonl")))
    return files[-_DAYS:] if _DAYS > 0 else files


def _framework(account: str, product: str) -> str:
    return FRAMEWORK.get((_ASSET.get(product, ""), _phase(account)), "")


def build_state() -> dict:
    """Assemble the live cockpit view from the routed-log."""
    lines: list[str] = []
    for path in _recent_files():
        try:
            with open(path, encoding="utf-8") as f:
                lines.extend(f)
        except OSError:
            pass
    events, amap = parse_routed_lines(lines)
    trades = pair_events(events, amap)

    as_of = max((e.ts for e in events), default=None)
    today = as_of.date() if as_of else None

    accounts: dict[str, dict] = {}

    def acct(a: str) -> dict:
        return accounts.setdefault(a, {
            "account": a, "phase": _phase(a),
            "realized_today": 0.0, "wins": 0, "losses": 0,
            "open": [], "closed_today": [], "last_ts": None,
        })

    for t in trades:
        product = _sym_root(t.symbol)
        a = acct(t.account)
        ts = t.exit_ts or t.entry_ts
        if ts and (a["last_ts"] is None or ts > a["last_ts"]):
            a["last_ts"] = ts
        if not t.closed:
            a["open"].append({
                "symbol": t.symbol, "direction": t.direction, "qty": t.qty,
                "entry_price": t.entry_price, "entry_ts": t.entry_ts.isoformat() if t.entry_ts else None,
                "sl": t.sl, "tp": t.tp, "signal_price": t.signal_price,
                "framework": _framework(t.account, product),
            })
        elif today and t.exit_ts and t.exit_ts.date() == today:
            pnl = t.pnl or 0.0
            a["realized_today"] += pnl
            a["wins" if pnl >= 0 else "losses"] += 1
            a["closed_today"].append({
                "symbol": t.symbol, "direction": t.direction, "qty": t.qty,
                "entry_price": t.entry_price, "exit_price": t.exit_price,
                "pnl": round(pnl, 2), "reason": t.reason, "mfe": t.mfe, "mae": t.mae,
                "exit_ts": t.exit_ts.isoformat(),
                "framework": _framework(t.account, product),
            })

    rows = []
    for a in accounts.values():
        a["closed_today"].sort(key=lambda x: x["exit_ts"], reverse=True)
        a["status"] = "In trade" if a["open"] else "Flat"
        a["realized_today"] = round(a["realized_today"], 2)
        a["last_ts"] = a["last_ts"].isoformat() if a["last_ts"] else None
        rows.append(a)
    rows.sort(key=lambda r: (r["phase"] != "funded", -r["realized_today"]))

    wins = sum(r["wins"] for r in rows)
    losses = sum(r["losses"] for r in rows)
    gross_win = sum(c["pnl"] for r in rows for c in r["closed_today"] if c["pnl"] >= 0)
    gross_loss = -sum(c["pnl"] for r in rows for c in r["closed_today"] if c["pnl"] < 0)
    fleet = {
        "realized_today": round(sum(r["realized_today"] for r in rows), 2),
        "open_positions": sum(len(r["open"]) for r in rows),
        "accounts": len(rows),
        "trades_today": wins + losses,
        "win_rate": round(100 * wins / (wins + losses), 1) if (wins + losses) else None,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else (None if not gross_win else 99.99),
    }
    return {
        "as_of": as_of.isoformat() if as_of else None,
        "today": today.isoformat() if today else None,
        "fleet": fleet,
        "accounts": rows,
    }


# ---- auth ----------------------------------------------------------------------------

def _token() -> str:
    return base64.urlsafe_b64encode(hmac.new(_SECRET, b"owner", hashlib.sha256).digest()).decode()


def _authed(headers) -> bool:
    if not _PASSWORD:
        return True   # no password set → open (dev)
    cookie = headers.get("Cookie", "")
    for part in cookie.split(";"):
        if part.strip().startswith("mexsession="):
            return hmac.compare_digest(part.strip()[len("mexsession="):], _token())
    return False


def _api_authorized(path: str, headers) -> bool:
    """/api/state is reachable by the logged-in owner (cookie) OR a read-only token
    (query ?token= or X-Token header) — the latter for the iPhone widget."""
    if _authed(headers):
        return True
    if not _API_TOKEN:
        return False
    q = parse_qs(urlparse(path).query)
    tok = (q.get("token", [None])[0]) or headers.get("X-Token")
    return bool(tok) and hmac.compare_digest(tok, _API_TOKEN)


# ---- HTTP ----------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet default logging
        pass

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            if not _authed(self.headers):
                return self._send(200, LOGIN_HTML.encode(), "text/html; charset=utf-8")
            return self._send(200, DASH_HTML.encode(), "text/html; charset=utf-8")
        if path == "/api/state":
            if not _api_authorized(self.path, self.headers):
                return self._send(401, b'{"error":"auth"}', "application/json")
            try:
                body = json.dumps(build_state()).encode()
            except Exception as exc:
                log.warning("state build failed: %r", exc)
                body = json.dumps({"error": str(exc)}).encode()
            return self._send(200, body, "application/json", {"Cache-Control": "no-store"})
        if path == "/healthz":
            return self._send(200, b"ok", "text/plain")
        return self._send(404, b"not found", "text/plain")

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/login":
            length = int(self.headers.get("Content-Length", 0) or 0)
            data = parse_qs(self.rfile.read(length).decode())
            if _PASSWORD and data.get("password", [""])[0] == _PASSWORD:
                cookie = f"mexsession={_token()}; HttpOnly; Path=/; Max-Age=604800; SameSite=Lax"
                return self._send(303, b"", "text/plain", {"Location": "/", "Set-Cookie": cookie})
            return self._send(200, LOGIN_HTML.replace("<!--ERR-->",
                              '<p class="err">Onjuist wachtwoord</p>').encode(), "text/html; charset=utf-8")
        return self._send(404, b"not found", "text/plain")


def serve() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    port = int(os.environ.get("VIEWER_PORT", "8080"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    log.info("MEX cockpit on :%d (routed=%s, auth=%s)", port, _ROUTED_DIR, "on" if _PASSWORD else "OFF")
    srv.serve_forever()


LOGIN_HTML = """<!doctype html><html lang=nl><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>MEX Traders — inloggen</title>
<style>
:root{color-scheme:dark}body{margin:0;height:100vh;display:grid;place-items:center;
background:#0a0e13;color:#e8eef4;font:16px/1.5 system-ui,sans-serif;
background-image:radial-gradient(900px 400px at 80% -10%,rgba(45,212,191,.08),transparent 60%)}
form{background:#111a22;padding:2rem;border-radius:16px;border:1px solid #1f2c38;width:min(90vw,340px)}
h1{font-size:1.05rem;margin:0 0 .3rem;letter-spacing:.01em}
.sub{color:#5b6b7a;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;margin-bottom:1.2rem}
input{width:100%;box-sizing:border-box;padding:.75rem;margin:.2rem 0 1rem;border-radius:10px;
border:1px solid #2a3646;background:#0a0e13;color:#e8eef4;font-size:1rem}
button{width:100%;padding:.75rem;border:0;border-radius:10px;background:#2dd4bf;color:#04231f;
font-weight:700;font-size:1rem;cursor:pointer}.err{color:#f7645a;font-size:.9rem;margin:.2rem 0 0}
.brand{opacity:.5;font-size:.8rem;margin-top:1.1rem;text-align:center}
</style>
<form method=post action=/login>
<h1>🌴 MEX Fleet Cockpit</h1><div class=sub>Owner login</div>
<!--ERR-->
<input type=password name=password placeholder=Wachtwoord autofocus>
<button>Inloggen</button>
<div class=brand>Pips &amp; Palm Trees Holding</div>
</form></html>"""

DASH_HTML = """<!doctype html><html lang=nl><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>MEX Fleet Cockpit</title>
<style>
:root{--ground:#0a0e13;--surface:#111a22;--raised:#16212c;--border:#1f2c38;--text:#e8eef4;
--muted:#8496a6;--faint:#5b6b7a;--accent:#2dd4bf;--profit:#46c96a;--loss:#f7645a;
--funded:#58a6ff;--eval:#bc8cff;--tab:"SF Mono",ui-monospace,Menlo,Consolas,monospace;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--text);
font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;
background-image:radial-gradient(1200px 500px at 85% -10%,rgba(45,212,191,.06),transparent 60%)}
.bar{display:flex;align-items:center;gap:.9rem;flex-wrap:wrap;padding:.95rem 1.3rem;
border-bottom:1px solid var(--border);background:linear-gradient(180deg,rgba(22,33,44,.6),transparent)}
.mark{display:flex;align-items:center;gap:.6rem;font-weight:700}
.mark .p{font-size:1.15rem}
.mark small{display:block;font-weight:500;color:var(--faint);font-size:.7rem;letter-spacing:.08em;text-transform:uppercase}
.live{display:inline-flex;align-items:center;gap:.4rem;color:var(--accent);font-size:.72rem;font-weight:600;
letter-spacing:.08em;text-transform:uppercase;border:1px solid rgba(45,212,191,.3);border-radius:999px;padding:.15rem .55rem}
.live .dot{width:7px;height:7px;border-radius:50%;background:var(--accent);animation:pulse 2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(45,212,191,.5)}70%{box-shadow:0 0 0 7px rgba(45,212,191,0)}100%{box-shadow:0 0 0 0 rgba(45,212,191,0)}}
@media (prefers-reduced-motion:reduce){.live .dot{animation:none}}
.asof{margin-left:auto;color:var(--muted);font-size:.8rem}
.wrap{max-width:1180px;margin:0 auto;padding:1.3rem}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.8rem;margin-bottom:1.5rem}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:.95rem 1.1rem}
.kpi.hero{grid-column:span 2}
.kpi .l{color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.07em}
.kpi .v{font-family:var(--tab);font-size:1.65rem;font-weight:700;margin-top:.25rem;font-variant-numeric:tabular-nums}
.kpi.hero .v{font-size:2.3rem}
.pos{color:var(--profit)}.neg{color:var(--loss)}
.eyebrow{color:var(--muted);font-size:.75rem;text-transform:uppercase;letter-spacing:.07em;margin:1.6rem 0 .7rem}
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;overflow:hidden}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.9rem;min-width:640px}
th,td{padding:.6rem .75rem;text-align:left;white-space:nowrap;border-bottom:1px solid var(--border)}
thead th{color:var(--muted);font-weight:600;font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;background:var(--raised)}
tbody tr:last-child td{border-bottom:0}
td.num,th.num{text-align:right;font-family:var(--tab);font-variant-numeric:tabular-nums}
.acct{cursor:pointer;transition:background .12s}.acct:hover{background:var(--raised)}
.acct .caret{color:var(--faint);display:inline-block;width:1em;transition:transform .15s}
.acct.open .caret{transform:rotate(90deg)}
.aid{font-family:var(--tab);font-size:.86rem}
.tag{display:inline-block;padding:.12rem .55rem;border-radius:999px;font-size:.7rem;font-weight:600}
.tag.funded{background:rgba(88,166,255,.14);color:var(--funded)}
.tag.eval{background:rgba(188,140,255,.14);color:var(--eval)}
.pill{display:inline-flex;align-items:center;gap:.35rem;padding:.12rem .55rem;border-radius:999px;font-size:.72rem;font-weight:600}
.pill::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.pill.trade{background:rgba(70,201,106,.12);color:var(--profit)}
.pill.flat{background:rgba(132,150,166,.12);color:var(--muted)}
.detail td{padding:0;background:var(--ground)}
.trades{padding:.3rem .75rem .6rem 2.1rem;display:flex;flex-direction:column;gap:.1rem}
.trow{display:grid;grid-template-columns:60px 1fr auto;gap:.8rem;align-items:center;padding:.28rem 0;font-size:.83rem}
.trow .dir{font-family:var(--tab);font-weight:600;font-size:.78rem}
.dir.BUY{color:var(--profit)}.dir.SELL{color:var(--loss)}
.trow .desc{color:var(--muted)}
.trow .px{font-family:var(--tab);font-variant-numeric:tabular-nums;color:var(--faint);font-size:.78rem}
.trow .pnl{font-family:var(--tab);font-variant-numeric:tabular-nums;font-weight:600;text-align:right}
.badge{font-size:.68rem;color:var(--faint);border:1px solid var(--border);border-radius:5px;padding:.02rem .35rem;margin-left:.4rem}
.foot{color:var(--faint);font-size:.78rem;margin:1.4rem .2rem 2rem;display:flex;gap:1rem;flex-wrap:wrap}
.foot .k{color:var(--muted)}.muted{color:var(--faint)}
</style>
<div class=bar>
  <div class=mark><span class=p>🌴</span><div>MEX Fleet Cockpit<small>Pips &amp; Palm Trees Holding</small></div></div>
  <span class=live><span class=dot></span>Live</span>
  <span id=asof class=asof>…</span>
</div>
<div class=wrap>
  <div class=kpis id=kpis></div>
  <div class=eyebrow>Accounts — funded eerst, dan eval · klik een rij open voor de trades</div>
  <div class="card scroll"><table><thead><tr>
    <th>Account</th><th>Type</th><th>Status</th><th class=num>Open</th>
    <th class=num>Trades</th><th class=num>Realized</th><th>Laatste</th>
  </tr></thead><tbody id=tb></tbody></table></div>
  <div class=foot>
    <span><span class=k>Bron:</span> routed-log (live)</span>
    <span><span class=k>Ververst:</span> elke 10s</span>
    <span><span class=k>Modus:</span> read-only</span>
  </div>
</div>
<script>
const $=s=>document.querySelector(s);
const money=n=>(n>=0?'+':'−')+'$'+Math.abs(n).toLocaleString('nl-NL',{minimumFractionDigits:2,maximumFractionDigits:2});
const cls=n=>n>0?'pos':n<0?'neg':'';
const time=s=>s?new Date(s).toLocaleTimeString('nl-NL',{hour:'2-digit',minute:'2-digit'}):'—';
function kpi(l,v,c){return `<div class="kpi ${c||''}"><div class=l>${l}</div><div class="v ${c==='hero'?cls(0):''}">${v}</div></div>`}
const open=new Set();
async function load(){
  let s; try{ s=await (await fetch('/api/state',{cache:'no-store'})).json() }catch(e){ return }
  if(!s||s.error){ $('#asof').textContent='geen data'; return }
  $('#asof').textContent = s.as_of? 'laatste activiteit · '+new Date(s.as_of).toLocaleString('nl-NL') : 'geen data';
  const f=s.fleet;
  $('#kpis').innerHTML =
    `<div class="kpi hero"><div class=l>Realized vandaag</div><div class="v ${cls(f.realized_today)}">${money(f.realized_today)}</div></div>`+
    kpi('Open posities', f.open_positions)+
    kpi('Trades vandaag', f.trades_today)+
    kpi('Win rate', f.win_rate==null?'—':f.win_rate+'%')+
    kpi('Profit factor', f.profit_factor==null?'—':f.profit_factor);
  $('#tb').innerHTML = s.accounts.map(a=>{
    const isopen=open.has(a.account);
    const opens=a.open.map(o=>`<div class=trow><span class="dir ${o.direction}">${o.direction}</span>
      <span class=desc>${o.qty}× ${o.symbol} @ ${o.entry_price}${o.framework?' · '+o.framework:''}</span>
      <span class="pnl muted">open</span></div>`).join('');
    const closed=a.closed_today.map(c=>`<div class=trow><span class="dir ${c.direction}">${c.direction}</span>
      <span class=desc>${c.qty}× ${c.symbol} <span class=px>${c.entry_price}→${c.exit_price}</span>${c.reason?`<span class=badge>${c.reason}</span>`:''}</span>
      <span class="pnl ${cls(c.pnl)}">${money(c.pnl)}</span></div>`).join('');
    const body=(opens+closed)||'<div class="trow muted"><span class=desc style="grid-column:1/-1">geen trades vandaag</span></div>';
    return `<tr class="acct${isopen?' open':''}" data-a="${a.account}">
      <td class=aid><span class=caret>›</span> ${a.account}</td>
      <td><span class="tag ${a.phase}">${a.phase==='funded'?'Funded':'Eval'}</span></td>
      <td><span class="pill ${a.open.length?'trade':'flat'}">${a.status}</span></td>
      <td class=num>${a.open.length||'—'}</td>
      <td class=num>${(a.wins+a.losses)||'—'}</td>
      <td class="num ${cls(a.realized_today)}">${a.realized_today?money(a.realized_today):'—'}</td>
      <td class=num style="text-align:left;color:var(--muted)">${time(a.last_ts)}</td></tr>
      <tr class=detail style="display:${isopen?'':'none'}"><td colspan=7><div class=trades>${body}</div></td></tr>`;
  }).join('') || '<tr><td colspan=7 class=muted>geen accounts actief</td></tr>';
  document.querySelectorAll('.acct').forEach(tr=>tr.onclick=()=>{
    const a=tr.dataset.a; open.has(a)?open.delete(a):open.add(a);
    const d=tr.nextElementSibling; d.style.display=d.style.display==='none'?'':'none'; tr.classList.toggle('open');
  });
}
load(); setInterval(load,10000);
</script></html>"""


if __name__ == "__main__":
    serve()
