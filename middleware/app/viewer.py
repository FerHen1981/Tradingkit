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
import datetime as dt
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
                "pnl": pnl, "reason": t.reason, "mfe": t.mfe, "mae": t.mae,
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
            if not _authed(self.headers):
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
background:#0b0f14;color:#e6edf3;font:16px/1.5 system-ui,sans-serif}
form{background:#111820;padding:2rem;border-radius:14px;border:1px solid #1f2a37;width:min(90vw,340px)}
h1{font-size:1.1rem;margin:0 0 1rem;letter-spacing:.02em}
input{width:100%;box-sizing:border-box;padding:.7rem;margin:.4rem 0 1rem;border-radius:8px;
border:1px solid #2a3646;background:#0b0f14;color:#e6edf3;font-size:1rem}
button{width:100%;padding:.7rem;border:0;border-radius:8px;background:#2f81f7;color:#fff;
font-weight:600;font-size:1rem;cursor:pointer}.err{color:#f85149;font-size:.9rem;margin:.2rem 0 0}
.brand{opacity:.6;font-size:.8rem;margin-top:1rem;text-align:center}
</style>
<form method=post action=/login>
<h1>🌴 MEX Traders — Fleet Cockpit</h1>
<!--ERR-->
<input type=password name=password placeholder=Wachtwoord autofocus>
<button>Inloggen</button>
<div class=brand>Pips &amp; Palm Trees Holding</div>
</form></html>"""

DASH_HTML = """<!doctype html><html lang=nl><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>MEX Fleet Cockpit</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#0b0f14;color:#e6edf3;font:15px/1.5 system-ui,-apple-system,sans-serif}
header{display:flex;align-items:baseline;gap:1rem;flex-wrap:wrap;padding:1rem 1.25rem;border-bottom:1px solid #1f2a37}
header h1{font-size:1.05rem;margin:0;letter-spacing:.02em}
header .as-of{opacity:.55;font-size:.8rem;margin-left:auto}
.wrap{padding:1.25rem;max-width:1200px;margin:0 auto}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.75rem;margin-bottom:1.25rem}
.kpi{background:#111820;border:1px solid #1f2a37;border-radius:12px;padding:.9rem 1rem}
.kpi .l{opacity:.6;font-size:.75rem;text-transform:uppercase;letter-spacing:.06em}
.kpi .v{font-size:1.5rem;font-weight:700;margin-top:.2rem}
.pos{color:#3fb950}.neg{color:#f85149}
h2{font-size:.85rem;text-transform:uppercase;letter-spacing:.06em;opacity:.6;margin:1.5rem 0 .6rem}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{text-align:left;padding:.5rem .6rem;border-bottom:1px solid #1a232e;white-space:nowrap}
th{opacity:.55;font-weight:600;font-size:.75rem;text-transform:uppercase;letter-spacing:.04em}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.tag{display:inline-block;padding:.1rem .5rem;border-radius:999px;font-size:.72rem;font-weight:600}
.tag.trade{background:#1f3a2a;color:#3fb950}.tag.flat{background:#222b36;color:#8b949e}
.tag.funded{background:#132f4c;color:#58a6ff}.tag.eval{background:#2b2536;color:#bc8cff}
.dir-BUY{color:#3fb950}.dir-SELL{color:#f85149}
.acct{cursor:pointer}.acct:hover{background:#0f1620}
.detail{background:#0d141c}.detail td{padding:.3rem .6rem;font-size:.82rem;opacity:.85}
.muted{opacity:.5}small{opacity:.5}
</style>
<header>
  <h1>🌴 MEX Fleet Cockpit</h1>
  <span id=asof class=as-of>…</span>
</header>
<div class=wrap>
  <div class=kpis id=kpis></div>
  <h2>Accounts</h2>
  <table><thead><tr>
    <th>Account</th><th>Type</th><th>Status</th><th class=num>Open</th>
    <th class=num>Trades vandaag</th><th class=num>Realized ($)</th><th>Laatste</th>
  </tr></thead><tbody id=rows></tbody></table>
  <p><small>Auto-ververst elke 10s · read-only · bron: routed-log</small></p>
</div>
<script>
const $=s=>document.querySelector(s);
const money=n=>(n>=0?'+':'')+n.toLocaleString('en-US',{style:'currency',currency:'USD'});
const cls=n=>n>0?'pos':n<0?'neg':'';
const time=s=>s?new Date(s).toLocaleTimeString('nl-NL',{hour:'2-digit',minute:'2-digit'}):'—';
function kpi(l,v,c){return `<div class=kpi><div class=l>${l}</div><div class="v ${c||''}">${v}</div></div>`}
async function load(){
  let s; try{ s=await (await fetch('/api/state',{cache:'no-store'})).json() }catch(e){ return }
  if(s.error){ return }
  $('#asof').textContent = s.as_of? 'laatste activiteit '+new Date(s.as_of).toLocaleString('nl-NL') : 'geen data';
  const f=s.fleet;
  $('#kpis').innerHTML =
    kpi('Realized vandaag', money(f.realized_today), cls(f.realized_today))+
    kpi('Open posities', f.open_positions)+
    kpi('Trades vandaag', f.trades_today)+
    kpi('Win rate', f.win_rate==null?'—':f.win_rate+'%')+
    kpi('Profit factor', f.profit_factor==null?'—':f.profit_factor)+
    kpi('Accounts', f.accounts);
  const rows=s.accounts.map((a,i)=>{
    const open=a.open.map(o=>`<tr class=detail><td></td><td colspan=6>
      <span class="dir-${o.direction}">${o.direction}</span> ${o.qty}× ${o.symbol}
      @ ${o.entry_price} ${o.framework?'· '+o.framework:''} <span class=muted>(open)</span></td></tr>`).join('');
    const closed=a.closed_today.map(c=>`<tr class=detail><td></td><td colspan=6>
      <span class="dir-${c.direction}">${c.direction}</span> ${c.qty}× ${c.symbol}
      ${c.entry_price}→${c.exit_price} · <span class="${cls(c.pnl)}">${money(c.pnl)}</span>
      ${c.reason?'· '+c.reason:''} <span class=muted>${time(c.exit_ts)}</span></td></tr>`).join('');
    return `<tr class=acct onclick="document.querySelectorAll('.d${i}').forEach(e=>e.style.display=e.style.display=='none'?'':'none')">
      <td>${a.account}</td>
      <td><span class="tag ${a.phase}">${a.phase==='funded'?'Funded':'Eval'}</span></td>
      <td><span class="tag ${a.open.length?'trade':'flat'}">${a.status}</span></td>
      <td class=num>${a.open.length||''}</td>
      <td class=num>${a.wins+a.losses||''}</td>
      <td class="num ${cls(a.realized_today)}">${a.realized_today?money(a.realized_today):'—'}</td>
      <td>${time(a.last_ts)}</td></tr>`
      + `<tbody class=d${i} style=display:none>${open}${closed||'<tr class=detail><td></td><td colspan=6 class=muted>geen trades vandaag</td></tr>'}</tbody>`;
  }).join('');
  $('#rows').innerHTML = rows || '<tr><td colspan=7 class=muted>geen accounts actief</td></tr>';
}
load(); setInterval(load, 10000);
</script></html>"""


if __name__ == "__main__":
    serve()
