"""MEX owner cockpit — a read-only live fleet dashboard (app.mex-traders.com).

Zero third-party deps for the live intraday view (stdlib http.server only) so it runs on the
VPS's Python 3.14 where FastAPI/pydantic won't build. Two data planes:

  /api/state    live intraday from the routed-log (open positions, today's closed trades) —
                fast, no external calls. Powers the "Live" tab.
  /api/command  the reconciled command center (fleet survival buffers + asset/strategy edge)
                from the Accounts DB + local Fills export. Cached. Powers the strategic tabs.

A later Next.js face can consume the same JSON without rework. Owner-only behind a password +
signed cookie; a read-only token (?token=) serves the iPhone widget.

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
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .routed_journal import parse_routed_lines, pair_events
from .journal_sync import FRAMEWORK, _ASSET, _phase, _sym_root
from .dashboard_state import command_state

log = logging.getLogger("mex.viewer")

_ROUTED_DIR = os.environ.get("ROUTED_DIR", os.environ.get("INTENT_DIR", "/root/intent-store"))
_DAYS = int(os.environ.get("ROUTED_DAYS", "2"))
_PASSWORD = os.environ.get("VIEWER_PASSWORD", "")
_SECRET = (os.environ.get("VIEWER_SECRET") or _PASSWORD or "mex-dev-secret").encode()
_API_TOKEN = os.environ.get("VIEWER_API_TOKEN", "")   # read-only token for the iPhone widget etc.
_STALE_OPEN_H = float(os.environ.get("STALE_OPEN_HOURS", "18"))   # hide "open" fills with a missed exit
_STARTED = time.monotonic()                                        # for the system-status uptime


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

    # last exit per account: any later close means an earlier still-"open" fill is a phantom
    # (its exit was missed/mismatched in the log). These strategies hold one position per
    # account at a time, so account-level is safe and catches contract-roll symbol changes.
    last_close: dict = {}
    for t in trades:
        if t.closed and t.exit_ts:
            if t.account not in last_close or t.exit_ts > last_close[t.account]:
                last_close[t.account] = t.exit_ts

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
            # hide a stale "open": a fill whose exit was never logged (would show a phantom
            # position while the account is actually flat). Genuine intraday opens are recent.
            lc = last_close.get(t.account)
            if lc and t.entry_ts and t.entry_ts < lc:
                continue     # account traded past this open → its exit was missed
            if as_of and t.entry_ts and (as_of - t.entry_ts).total_seconds() > _STALE_OPEN_H * 3600:
                continue
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
    """/api/* is reachable by the logged-in owner (cookie) OR a read-only token
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
        if path == "/api/command":
            if not _api_authorized(self.path, self.headers):
                return self._send(401, b'{"error":"auth"}', "application/json")
            q = parse_qs(urlparse(self.path).query)
            window = q.get("window", ["all"])[0]
            stage = q.get("stage", ["all"])[0]
            try:
                data = command_state(window, stage)
                data.setdefault("status", {})["uptime_s"] = round(time.monotonic() - _STARTED)
                body = json.dumps(data).encode()
            except Exception as exc:
                log.warning("command state build failed: %r", exc)
                body = json.dumps({"error": str(exc)}).encode()
            return self._send(200, body, "application/json", {"Cache-Control": "no-store"})
        if path == "/api/widget":
            if not _api_authorized(self.path, self.headers):
                return self._send(401, b'{"error":"auth"}', "application/json")
            try:
                def stack(stage):
                    f = command_state("all", stage)["fleet"]      # realized = ledger (matches dashboard)
                    wkf = command_state("week", stage)["fleet"]
                    dyf = command_state("day", stage)["fleet"]
                    return {
                        "realized": round(f.get("realized_net") or 0, 2),
                        "week": round(wkf.get("window_net") or 0, 2),
                        "today": round(dyf.get("window_net") or 0, 2),
                        "trades": f.get("trades") or 0,
                        "winrate": f.get("win_rate") or 0,
                        "pf": f.get("pf") or 0,
                        "accounts": f.get("accounts") or 0,
                        "breached": f.get("breached") or 0,
                        "buffer": round(f.get("survival_buffer") or 0, 2),
                    }
                allc = command_state("all")
                wkall = command_state("week")["fleet"]
                dyall = command_state("day")["fleet"]
                spark = [c["cum"] for c in allc["equity"]["curve"]][-12:] or [0]
                widget = {
                    "goal": float(os.environ.get("WIDGET_GOAL", "0")),
                    "dataThrough": allc.get("status", {}).get("data_through") or "",
                    "spark": spark,
                    "stacks": {"all": stack("all"), "funded": stack("funded"), "eval": stack("eval")},
                    "week": {"net": round(wkall.get("window_net") or 0, 2), "trades": wkall.get("trades") or 0,
                             "winrate": wkall.get("win_rate") or 0, "pf": wkall.get("pf") or 0},
                    "today": round(dyall.get("window_net") or 0, 2),
                }
                body = json.dumps(widget).encode()
            except Exception as exc:
                log.warning("widget build failed: %r", exc)
                body = json.dumps({"error": str(exc)}).encode()
            return self._send(200, body, "application/json", {"Cache-Control": "no-store"})
        if path == "/favicon.svg":
            return self._send(200, _FAVICON_SVG, "image/svg+xml",
                              {"Cache-Control": "public, max-age=86400"})
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
                              '<p class="err">Incorrect password</p>').encode(), "text/html; charset=utf-8")
        return self._send(404, b"not found", "text/plain")


def serve() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    port = int(os.environ.get("VIEWER_PORT", "8080"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    log.info("MEX cockpit on :%d (routed=%s, auth=%s)", port, _ROUTED_DIR, "on" if _PASSWORD else "OFF")
    srv.serve_forever()


# MEX brand assets (served/inlined by the cockpit).
_FAVICON_SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                b'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
                b'<stop offset="0" stop-color="#E8B54F"/><stop offset="1" stop-color="#B98526"/></linearGradient></defs>'
                b'<rect width="100" height="100" fill="#030F28"/>'
                b'<path d="M2,69.95 L98,69.95 L98,75.08 L2,75.08 Z" fill="#F2EBDA" opacity=".52"/>'
                b'<path d="M15.57,79 L20.56,41.48 L40.10,69.95 L51.24,69.95 L79.08,41.65 L84.37,79 L96.64,79 '
                b'L87.66,15.59 L46.15,57.80 L46.50,57.80 L12.69,8.52 L3.32,79 Z" fill="url(#g)"/></svg>')

_MARK = ('<svg viewBox="0 0 100 100" width="26" height="26" aria-hidden="true" style="flex:none">'
         '<defs><linearGradient id="mexg" x1="0" y1="0" x2="1" y2="1">'
         '<stop offset="0" stop-color="#E8B54F"/><stop offset="1" stop-color="#B98526"/></linearGradient></defs>'
         '<path d="M-10.55,69.29 L100.15,69.29 L100.15,72.93 L-10.55,72.93 Z" fill="#F2EBDA" opacity=".42"/>'
         '<path d="M16.85,78 L21.65,41.87 L40.46,69.29 L51.20,69.29 L78,42.03 L83.10,78 L94.92,78 '
         'L86.27,16.94 L46.29,57.59 L46.63,57.59 L14.07,10.13 L5.05,78 Z" fill="url(#mexg)"/></svg>')

_FONTS = ('<link rel="icon" type="image/svg+xml" href="/favicon.svg">'
          '<link rel=preconnect href="https://fonts.googleapis.com">'
          '<link rel=preconnect href="https://fonts.gstatic.com" crossorigin>'
          '<link rel=stylesheet href="https://fonts.googleapis.com/css2?'
          'family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&'
          'family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap">')

LOGIN_HTML = ("""<!doctype html><html lang=nl><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>MEX Traders — inloggen</title>""" + _FONTS + """
<style>
:root{color-scheme:dark}body{margin:0;height:100vh;display:grid;place-items:center;
background:#030F28;color:#F2EBDA;font:16px/1.6 'Instrument Sans',system-ui,sans-serif;
background-image:radial-gradient(1000px 560px at 82% -8%,rgba(232,181,79,.18),transparent 60%),radial-gradient(820px 620px at 2% 42%,rgba(90,162,255,.14),transparent 62%)}
form{background:rgba(14,42,94,.42);padding:2rem;border-radius:4px;border:1px solid rgba(242,235,218,.17);width:min(90vw,340px)}
.lg{display:flex;align-items:center;gap:9px;margin-bottom:1.1rem}
.lg .wm{font-family:'Bricolage Grotesque',sans-serif;font-weight:800;letter-spacing:-.03em;font-size:18px}
.lg .wm em{font-style:normal;font-weight:400;letter-spacing:.10em;margin-left:.35em;color:rgba(242,235,218,.6)}
h1{font-size:1rem;margin:0 0 .3rem;font-family:'Bricolage Grotesque',sans-serif;font-weight:600}
.sub{color:rgba(242,235,218,.6);font-family:'JetBrains Mono',monospace;font-size:.68rem;letter-spacing:.16em;text-transform:uppercase;margin-bottom:1.2rem}
input{width:100%;box-sizing:border-box;padding:.75rem;margin:.2rem 0 1rem;border-radius:2px;
border:1px solid rgba(242,235,218,.17);background:#081D46;color:#F2EBDA;font-size:1rem}
button{width:100%;padding:.75rem;border:0;border-radius:2px;background:linear-gradient(120deg,#E8B54F,#F3CE7C);color:#0B1428;
font-weight:700;font-size:1rem;cursor:pointer;font-family:'JetBrains Mono',monospace;text-transform:uppercase;letter-spacing:.08em}
.err{color:#E0796E;font-size:.9rem;margin:.2rem 0 0}
.brand{opacity:.5;font-size:.8rem;margin-top:1.1rem;text-align:center;font-family:'JetBrains Mono',monospace}
</style>
<form method=post action=/login>
<div class=lg>""" + _MARK + """<span class=wm>MEX<em>TRADERS</em></span></div>
<h1>Command Center</h1><div class=sub>Owner login</div>
<!--ERR-->
<input type=password name=password placeholder=Password autofocus>
<button>Sign in</button>
<div class=brand>Pips &amp; Palm Trees Holding</div>
</form></html>""")

DASH_HTML = r"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>MEX Command Center</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel=preconnect href="https://fonts.googleapis.com"><link rel=preconnect href="https://fonts.gstatic.com" crossorigin>
<link rel=stylesheet href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap">
<style>
:root{
  --bg:#030F28;--panel:#081D46;--panel-2:#0E2A5E;--line:rgba(242,235,218,.17);
  --ink:#F2EBDA;--muted:rgba(242,235,218,.60);--dim:rgba(242,235,218,.42);
  --gold:#E8B54F;--gold-dim:#B98526;--aqua:#5AA2FF;
  --ok:#5AA2FF;--watch:#E8B54F;--warn:#E8B54F;--crit:#E0796E;--dead:#E0796E;
  --mono:'JetBrains Mono',ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --sans:'Instrument Sans',system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --display:'Bricolage Grotesque',var(--sans);
  --radius:4px;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.5;
background-image:radial-gradient(1100px 620px at 82% -8%,rgba(232,181,79,.16),transparent 60%),
radial-gradient(900px 700px at 2% 42%,rgba(90,162,255,.13),transparent 62%);background-attachment:fixed}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px 64px}
header{position:sticky;top:0;z-index:20;background:linear-gradient(180deg,rgba(6,23,26,.97),rgba(6,23,26,.86));
backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.bar{max-width:1180px;margin:0 auto;padding:14px 20px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:10px;margin-right:auto}
.brand .name{font-family:var(--display);font-weight:800;letter-spacing:-.02em;font-size:18px;color:var(--ink)}
.brand .name em{font-style:normal;font-weight:400;letter-spacing:.10em;margin-left:.35em;color:var(--muted)}
.brand .sub{font-family:var(--mono);font-size:10px;letter-spacing:.18em;color:var(--gold);text-transform:uppercase;border:1px solid var(--line);padding:3px 8px;border-radius:2px}
.clock{font-family:var(--mono);font-size:12.5px;color:var(--dim);letter-spacing:1px;display:flex;align-items:center;gap:8px}
.live{width:7px;height:7px;border-radius:50%;background:var(--ok);animation:pulse 2.4s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(53,200,138,.55)}70%{box-shadow:0 0 0 7px rgba(53,200,138,0)}100%{box-shadow:0 0 0 0 rgba(53,200,138,0)}}
@media (prefers-reduced-motion:reduce){.live{animation:none}}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;margin:22px 0 8px}
.kpi{background:var(--panel);padding:15px 16px;min-width:0}
.kpi .lab{font-family:var(--mono);font-size:10.5px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted)}
.kpi .val{font-family:var(--mono);font-size:23px;font-weight:600;margin-top:6px;letter-spacing:.3px;font-variant-numeric:tabular-nums}
.kpi .note{font-family:var(--mono);font-size:11px;color:var(--dim);margin-top:3px}
.pos{color:var(--ok)}.neg{color:var(--crit)}.gold{color:var(--gold)}.aqua{color:var(--aqua)}
@media(max-width:860px){.kpis{grid-template-columns:repeat(2,1fr)}.kpi:last-child{grid-column:1/-1}}
.tf{display:flex;gap:6px;flex-wrap:wrap;margin:18px 0 -6px}
.tf button{appearance:none;border:1px solid var(--line);background:var(--panel);color:var(--muted);font-family:var(--mono);font-size:13px;letter-spacing:.8px;text-transform:uppercase;padding:9px 16px;border-radius:20px;cursor:pointer}
.tf button:hover{color:var(--ink);border-color:#26545a}
.tf button[aria-pressed="true"]{background:var(--gold);color:var(--bg);border-color:var(--gold);font-weight:600}
.tf.stage{margin-top:8px}
.tf.stage button[aria-pressed="true"]{background:var(--aqua);border-color:var(--aqua)}
.tf button:focus-visible{outline:2px solid var(--aqua);outline-offset:2px}
nav.tabs{display:flex;gap:4px;margin:20px 0 18px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.tab{appearance:none;border:0;background:transparent;cursor:pointer;font-family:var(--mono);font-size:13.5px;letter-spacing:1.2px;text-transform:uppercase;color:var(--muted);padding:13px 17px;border-bottom:2px solid transparent;margin-bottom:-1px}
.tab:hover{color:var(--ink)}
.tab[aria-selected="true"]{color:var(--gold);border-bottom-color:var(--gold)}
.tab:focus-visible{outline:2px solid var(--aqua);outline-offset:2px;border-radius:4px}
.tab .lv{color:var(--dim);font-size:10px;margin-right:6px}
section[role="tabpanel"]{animation:fade .25s ease}
@keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
section[hidden]{display:none}
h2.sec{font-size:15px;font-weight:600;margin:4px 0 2px;letter-spacing:.2px}
.sec-note{color:var(--muted);font-size:13px;margin:0 0 16px}
.grid{display:grid;gap:14px}.g3{grid-template-columns:repeat(3,1fr)}.g2{grid-template-columns:repeat(2,1fr)}
@media(max-width:820px){.g3,.g2{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px 17px}
.card .ey{font-family:var(--mono);font-size:10.5px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);display:flex;align-items:center;gap:8px}
.card .big{font-family:var(--mono);font-size:26px;font-weight:600;margin:9px 0 2px;font-variant-numeric:tabular-nums}
.card .row{display:flex;justify-content:space-between;font-family:var(--mono);font-size:12.5px;color:var(--muted);padding:3px 0;font-variant-numeric:tabular-nums}
.card .row b{color:var(--ink);font-weight:600}
.tag{font-family:var(--mono);font-size:10px;letter-spacing:.5px;padding:2px 7px;border-radius:20px;text-transform:uppercase}
.tag.gc{background:rgba(240,182,77,.14);color:var(--gold)}
.tag.es{background:rgba(63,208,189,.14);color:var(--aqua)}
.tag.nq{background:rgba(239,107,83,.14);color:var(--crit)}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:var(--radius)}
table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:13px;font-variant-numeric:tabular-nums;min-width:720px}
thead th{text-align:right;padding:11px 14px;background:var(--panel-2);color:var(--muted);font-weight:500;font-size:10.5px;letter-spacing:1px;text-transform:uppercase;border-bottom:1px solid var(--line);white-space:nowrap;cursor:pointer;user-select:none}
thead th:first-child,tbody td:first-child{text-align:left}
thead th:hover{color:var(--ink)}
thead th .ar{color:var(--gold);font-size:9px}
tbody td{padding:10px 14px;border-bottom:1px solid rgba(28,63,67,.55);white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:rgba(63,208,189,.045)}
td.acct{color:var(--ink);font-weight:600}
td .firmdot{color:var(--dim);font-size:11px}
.num{text-align:right}
.pill{display:inline-block;font-size:10px;letter-spacing:.6px;text-transform:uppercase;padding:3px 9px;border-radius:20px;font-weight:600}
.h-ok{background:rgba(53,200,138,.15);color:var(--ok)}
.h-watch{background:rgba(79,191,192,.15);color:var(--watch)}
.h-warn{background:rgba(240,165,58,.15);color:var(--warn)}
.h-crit{background:rgba(239,107,83,.15);color:var(--crit)}
.h-dead{background:rgba(192,69,90,.18);color:var(--dead)}
.h-idle{background:rgba(92,128,124,.15);color:var(--dim)}
.bufcell{display:flex;align-items:center;gap:9px;justify-content:flex-end}
.bufbar{width:66px;height:6px;border-radius:4px;background:rgba(28,63,67,.8);overflow:hidden;flex:none}
.bufbar i{display:block;height:100%;border-radius:4px}
.seed{color:var(--gold);font-size:10px}.calc{color:var(--dim);font-size:10px}
.stiles{display:flex;gap:1px;background:var(--line);border:1px solid var(--line);border-radius:8px;overflow:hidden;flex-wrap:wrap;margin:2px 0 16px}
.stile{background:var(--panel);padding:12px 17px;min-width:100px;flex:1}
.stile .sl{font-family:var(--mono);font-size:10.5px;letter-spacing:1px;text-transform:uppercase;color:var(--muted);white-space:nowrap}
.stile .sv{font-family:var(--mono);font-size:19px;font-weight:600;margin-top:4px;font-variant-numeric:tabular-nums}
.tag.micro{background:rgba(63,208,189,.14);color:var(--aqua)}
.tag.full{background:rgba(132,150,166,.14);color:var(--muted)}
.attn{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:11px 14px;margin-bottom:8px}
.attn-h{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:13.5px}
.attn-d{font-family:var(--mono);font-size:12.5px;color:var(--muted);margin-top:4px}
.healthbar{display:flex;height:34px;border-radius:8px;overflow:hidden;border:1px solid var(--line);margin:2px 0 10px}
.healthbar span{display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:12px;font-weight:600;color:var(--bg)}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-family:var(--mono);font-size:11.5px;color:var(--muted)}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px;vertical-align:middle}
.attr{display:flex;flex-direction:column;gap:9px;margin-top:4px}
.attr .a-row{display:grid;grid-template-columns:70px 1fr 96px;align-items:center;gap:12px;font-family:var(--mono);font-size:12.5px}
.attr .track{height:16px;background:rgba(28,63,67,.5);border-radius:4px;overflow:hidden}
.attr .track i{display:block;height:100%}
.attr .a-val{text-align:right;font-variant-numeric:tabular-nums}
.dir.BUY{color:var(--ok)}.dir.SELL{color:var(--crit)}
table.hm{border-collapse:collapse;font-family:var(--mono);font-size:12.5px;font-variant-numeric:tabular-nums;margin:2px}
table.hm th{color:var(--muted);font-weight:500;padding:7px 9px;text-align:center;font-size:11px;letter-spacing:.5px}
table.hm tbody th{text-align:right;color:var(--ink);position:sticky;left:0;background:var(--panel-2);z-index:1}
td.hm-cell{padding:9px 11px;text-align:center;color:var(--ink);border:1px solid var(--bg);white-space:nowrap;min-width:58px}
td.hm-empty{border:1px solid var(--bg);background:rgba(28,63,67,.22)}
select.calsel{font-family:var(--mono);font-size:12px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:7px 10px}
select.calsel:focus-visible{outline:2px solid var(--aqua);outline-offset:2px}
table.cal{border-collapse:collapse;font-family:var(--mono);font-size:12.5px;font-variant-numeric:tabular-nums;margin:2px}
table.cal th{color:var(--muted);font-weight:500;padding:7px 9px;font-size:11px;text-align:center;letter-spacing:.5px}
table.cal tbody th{text-align:right;color:var(--muted);min-width:40px}
td.cal-cell{border:1px solid var(--bg);min-width:66px;height:46px;text-align:center;vertical-align:top;padding:5px 8px;color:var(--ink);white-space:nowrap}
td.cal-empty{background:rgba(28,63,67,.16);color:var(--dim)}
.cal-d{display:block;font-size:10px;color:var(--muted);text-align:left;margin-bottom:2px}
footer{margin-top:30px;padding-top:18px;border-top:1px solid var(--line);color:var(--dim);font-family:var(--mono);font-size:11.5px;line-height:1.7}
.caption{color:var(--muted)}.caption b{color:var(--ink)}
.err-banner{background:rgba(239,107,83,.12);border:1px solid rgba(239,107,83,.4);color:var(--crit);padding:10px 14px;border-radius:8px;font-family:var(--mono);font-size:12.5px;margin:16px 0}
</style>
<header><div class=bar>
  <div class=brand><svg viewBox="0 0 100 100" width="26" height="26" aria-hidden="true" style="flex:none"><defs><linearGradient id="mexg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#E8B54F"/><stop offset="1" stop-color="#B98526"/></linearGradient></defs><path d="M-10.55,69.29 L100.15,69.29 L100.15,72.93 L-10.55,72.93 Z" fill="#F2EBDA" opacity=".42"/><path d="M16.85,78 L21.65,41.87 L40.46,69.29 L51.20,69.29 L78,42.03 L83.10,78 L94.92,78 L86.27,16.94 L46.29,57.59 L46.63,57.59 L14.07,10.13 L5.05,78 Z" fill="url(#mexg)"/></svg><span class=name>MEX<em>TRADERS</em></span><span class=sub>Command Center</span></div>
  <div class=clock><span class=live></span><span id=clock>—</span></div>
</div></header>
<div class=wrap>
  <div class=tf id=tf></div>
  <div class="tf stage" id=stagef></div>
  <div class=kpis id=kpis></div>
  <p class=sec-note style="margin-top:4px">Headline = ledger (all accounts, reconciles with Tradovate). Breakdowns below cover <b id=tflabel style="color:var(--ink)">all time</b>; buffers are live "now" state. <span id=asof></span></p>
  <div id=topStats></div>
  <nav class=tabs role=tablist aria-label="Command center levels">
    <button class=tab role=tab aria-selected=true  data-panel=fleet><span class=lv>L0</span>Fleet</button>
    <button class=tab role=tab aria-selected=false data-panel=attention><span class=lv>!</span>Attention</button>
    <button class=tab role=tab aria-selected=false data-panel=accounts><span class=lv>L2</span>Accounts</button>
    <button class=tab role=tab aria-selected=false data-panel=firms><span class=lv>L1</span>Firms</button>
    <button class=tab role=tab aria-selected=false data-panel=strategies><span class=lv>L3</span>Strategies</button>
    <button class=tab role=tab aria-selected=false data-panel=assets><span class=lv>L4</span>Assets</button>
    <button class=tab role=tab aria-selected=false data-panel=equity><span class=lv>L9</span>Equity</button>
    <button class=tab role=tab aria-selected=false data-panel=calendar><span class=lv>L8</span>Calendar</button>
    <button class=tab role=tab aria-selected=false data-panel=portfolio><span class=lv>L7</span>Portfolio</button>
    <button class=tab role=tab aria-selected=false data-panel=heatmap><span class=lv>L6</span>Heatmap</button>
    <button class=tab role=tab aria-selected=false data-panel=payout><span class=lv>L5</span>Payout</button>
    <button class=tab role=tab aria-selected=false data-panel=playbook><span class=lv>L10</span>Playbook</button>
    <button class=tab role=tab aria-selected=false data-panel=live><span class=lv>●</span>Live</button>
  </nav>
  <section role=tabpanel id=fleet>
    <h2 class=sec>Fleet health</h2>
    <p class=sec-note>Every account at a glance — split by survival status.</p>
    <div class=healthbar id=healthbar></div><div class=legend id=legend></div>
    <div class="grid g2" style="margin-top:22px">
      <div class=card><div class=ey>P&amp;L attribution · by asset</div><div class=attr id=attr></div>
        <div class=row id=feesRow style="margin-top:12px;padding-top:9px;border-top:1px solid var(--line)"><span>Total fees (window)</span><b></b></div></div>
      <div class=card><div class=ey>Watchlist · lowest buffer</div><div id=watch style="margin-top:10px"></div></div>
    </div>
  </section>
  <section role=tabpanel id=attention hidden>
    <h2 class=sec>Needs attention</h2>
    <p class=sec-note>Ranked live signals across the fleet — breach risk, thin buffers, consistency risk and payout-ready — for the selected window/stage.</p>
    <div id=attnList></div>
  </section>
  <section role=tabpanel id=accounts hidden>
    <h2 class=sec>Survival cockpit</h2>
    <p class=sec-note>Per account: where the floor sits, how much buffer to breach. <span class=seed>◆ gold</span> = exact Tradovate seed · <span class=calc>○ grey</span> = reconstructed. Net P&amp;L = ledger total (Notion). Click a header to sort.</p>
    <div class=tablewrap><table id=acctTable><thead><tr>
      <th data-k=id data-t=s>Account</th><th data-k=stage data-t=s>Type</th>
      <th data-k=current data-t=n>Current</th><th data-k=floor data-t=n>DD Floor</th>
      <th data-k=buffer data-t=n>Buffer $</th><th data-k=bufpct data-t=n>Buffer %</th>
      <th data-k=net data-t=n>Net P&amp;L</th><th data-k=win_pct data-t=n>Win %</th><th data-k=pf data-t=n>PF</th><th data-k=hrank data-t=n>Health</th>
    </tr></thead><tbody></tbody></table></div>
  </section>
  <section role=tabpanel id=firms hidden>
    <h2 class=sec>By prop firm</h2>
    <p class=sec-note>Rollup per firm — capital, buffer and result.</p>
    <div class="grid g3" id=firmCards></div>
  </section>
  <section role=tabpanel id=strategies hidden>
    <h2 class=sec>By strategy engine</h2>
    <p class=sec-note>One engine, tuned per asset with the "El ___" variants. Validated funded edges: GC + ES; NQ = variance lottery (eval-only).</p>
    <div id=evalPasses style="margin-bottom:16px"></div>
    <div class="grid g3" id=stratCards></div>
  </section>
  <section role=tabpanel id=assets hidden>
    <h2 class=sec>By asset · execution quality</h2>
    <p class=sec-note>The pips-and-ticks cut: net, ticks and hit-rate per market.</p>
    <div class=tablewrap><table id=assetTable><thead><tr>
      <th data-k=sym data-t=s>Asset</th><th data-k=engine data-t=s>Engine</th>
      <th data-k=n data-t=n>Trades</th><th data-k=win data-t=n>Win %</th>
      <th data-k=pf data-t=n>PF</th><th data-k=expectancy data-t=n>Exp.</th><th data-k=ticks data-t=n>Net ticks</th><th data-k=net data-t=n>Net P&amp;L</th>
      <th>Fees</th><th>MFE / MAE</th><th data-k=edge data-t=s>Edge</th>
    </tr></thead><tbody></tbody></table></div>
  </section>
  <section role=tabpanel id=equity hidden>
    <h2 class=sec>Equity &amp; drawdown</h2>
    <p class=sec-note>Cumulative net over the window (gold line) with drawdown from peak, and a forward <b style="color:var(--aqua)">risk/potential band</b> — projected 15 trading days out from daily expectancy ± volatility (the cone widens with √time). Dashed line = expected path.</p>
    <div id=eqStats></div>
    <div class=card style="padding:12px 14px"><div id=eqChart></div></div>
  </section>
  <section role=tabpanel id=calendar hidden>
    <h2 class=sec>Performance calendar</h2>
    <p class=sec-note>Daily net P&amp;L with weekly and total roll-up, over the selected window. <b style="color:var(--ink)">Colour = expectancy</b> (net per trade). Pick a level to drill into one strategy/asset or a single account.</p>
    <div style="display:flex;gap:12px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
      <select id=calDim class=calsel></select>
      <span id=calTotal class=calc></span>
    </div>
    <div id=calStats></div>
    <div class=tablewrap><div id=calGrid></div></div>
  </section>
  <section role=tabpanel id=portfolio hidden>
    <h2 class=sec>Portfolio &amp; correlation</h2>
    <p class=sec-note>Allocated capital and P&amp;L spread across the fleet, and how the asset edges move together. Correlation is over daily net (flat days = 0) for the selected window — high positive = edges rise/fall together (concentrated risk), low/negative = diversified.</p>
    <div class="grid g2">
      <div class=card><div class=ey>Capital by type</div><div id=allocStage style="margin-top:10px"></div></div>
      <div class=card><div class=ey>Capital by firm</div><div id=allocFirm style="margin-top:10px"></div></div>
    </div>
    <div class="grid g2" style="margin-top:14px">
      <div class=card><div class=ey>P&amp;L contribution by asset</div><div id=allocAsset style="margin-top:10px"></div></div>
      <div class=card><div class=ey>Asset correlation <span id=corrDays class=calc></span></div><div id=corrMatrix style="margin-top:10px;overflow-x:auto"></div></div>
    </div>
  </section>
  <section role=tabpanel id=heatmap hidden>
    <h2 class=sec>Day × hour heatmap</h2>
    <p class=sec-note>Weekday × hour of day (ET) over the selected window. Cell shows total net; <b style="color:var(--ink)">colour = expectancy</b> (net per trade) so quality reads apart from size. Hover for count + expectancy.</p>
    <div style="margin-bottom:12px"><select id=hmDim class=calsel></select></div>
    <div class=tablewrap><div id=hmGrid></div></div>
  </section>
  <section role=tabpanel id=payout hidden>
    <h2 class=sec>Payout &amp; rules</h2>
    <p class=sec-note>What's withdrawable now and what's left to satisfy — PA (funded) accounts only. Apex rules: ≥8 trading days (≥$50/day) · 30% consistency (best day ≤30% of profit) · safety-net balance. <span class=calc>Configurable — verify against Apex's current terms.</span></p>
    <div class="grid g2" id=payoutKpis style="margin-bottom:18px"></div>
    <div class="grid g3" id=payoutCards></div>
  </section>
  <section role=tabpanel id=playbook hidden>
    <h2 class=sec>Payout Playbook</h2>
    <p class=sec-note>Each account's route to the MAXIMUM payout this step, read from its OWN history against the firm rules. Withdrawable = min(profit − safety-net, rung cap); to pull the full cap you need profit = safety + cap, spread over the program's min trading days (reset each cycle) so its consistency ceiling (best day ≤ the program %) allows it. Funded runs only the edge on the real instrument (MGC · El Tesoro / MES · El Rey; NQ eval-only): <b style="color:var(--warn)">survival</b> 1 ct below the safety-net → <b style="color:var(--ok)">milking</b> 2 ct building to the full cap → <b style="color:var(--gold)">payout</b> pull the full cap, carry the excess, reset to the next rung; legacy <b style="color:var(--aqua)">compound</b>. The Route says what still has to happen and warns when banking early leaves money on the table. <span class=calc>Rules per account come from its <b>Account Type → Firm Program</b> in <b>data/propfirms.json</b> (the single source of truth: consistency, min-days, drawdown, target, ladder, max size). ⚠ = unverified program. Rung = "Payouts (0-6)".</span></p>
    <div class=tablewrap><table id=pbTable style="min-width:1040px"><thead><tr>
      <th data-k=id data-t=s>Account</th><th>Run</th><th data-k=playbook.phase data-t=s>Phase</th>
      <th style="text-align:left" data-k=playbook.profit data-t=n>Where it stands</th>
      <th style="text-align:left" data-k=playbook.day_cap data-t=n>Set: size · DLL · day-cap</th><th style="text-align:left">Route to payout</th>
    </tr></thead><tbody></tbody></table></div>
  </section>
  <section role=tabpanel id=live hidden>
    <h2 class=sec>Live · intraday</h2>
    <p class=sec-note id=livenote>Open positions and trades closed today — from the routed log, every 15s.</p>
    <div class="grid g2" id=liveKpis style="margin-bottom:18px"></div>
    <div class=tablewrap><table id=liveTable style="min-width:640px"><thead><tr>
      <th>Account</th><th>Type</th><th>Status</th><th class=num>Open</th>
      <th class=num>Trades</th><th class=num>Realized today</th>
    </tr></thead><tbody></tbody></table></div>
  </section>
  <footer>
    <div id=sysStatus style="margin-bottom:12px"></div>
    <div class=caption><b>Source:</b> Accounts DB (buffers) + local Fills export (asset edge), server-side. <span id=footnet></span></div>
    <div style="margin-top:8px">Live cockpit · <b style="color:var(--aqua)">app.mex-traders.com</b> — no browser scraper. Notion stays the records backend.</div>
  </footer>
</div>
<script>
const $=s=>document.querySelector(s);
const money=n=>(n<0?"−$":"$")+Math.abs(n).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
const money0=n=>(n<0?"−$":"$")+Math.abs(n).toLocaleString("en-US",{maximumFractionDigits:0});
const signed=n=>(n>=0?"+":"−")+Math.abs(n).toLocaleString("en-US",{maximumFractionDigits:0});
const moneyK=n=>{const a=Math.abs(n),s=n>=0?"+":"−";return a>=1000?s+(a/1000).toFixed(1)+"k":s+Math.round(a);};
const pfCls=pf=>pf==null?"":(pf>=1?"pos":"neg");
// colour by EXPECTANCY per cell (net ÷ trades) on a √-compressed scale — quality per trade,
// not just total size, so a busy cell and a one-lucky-trade cell read differently.
function heatColor(net,n,maxExp){
  const e=n?net/n:net;
  if(!e||!maxExp)return "transparent";
  const t=Math.min(1,Math.sqrt(Math.abs(e)/maxExp));
  const a=(0.14+0.62*t).toFixed(2);
  return e>=0?`rgba(53,200,138,${a})`:`rgba(239,107,83,${a})`;
}
function tiles(items){return '<div class=stiles>'+items.map(i=>`<div class=stile><div class=sl>${i.lab}</div><div class="sv ${i.cls||''}">${i.val}</div></div>`).join('')+'</div>';}
function statItems(s){s=s||{};const win=s.win_pct??s.win_rate??s.win,heat=s.heat??s.mae;
  return [
    {lab:"Trades",val:s.trades??s.n??0},
    {lab:"Win %",val:win!=null?win+"%":"—"},
    {lab:"Profit factor",val:s.pf==null?"—":s.pf,cls:pfCls(s.pf)},
    {lab:"Expectancy",val:s.expectancy!=null?money0(s.expectancy):"—",cls:cls(s.expectancy||0)},
    {lab:"Avg win",val:s.avg_win!=null?money0(s.avg_win):"—",cls:"pos"},
    {lab:"Avg loss",val:s.avg_loss!=null?money0(s.avg_loss):"—",cls:"neg"},
    {lab:"Heat (MAE)",val:heat!=null?heat+"t":"—"}];
}
function fleetTiles(f){f=f||{};return tiles(statItems(f).concat([
  {lab:"Best day",val:signed(f.best_day||0),cls:"pos"},
  {lab:"Worst day",val:signed(f.worst_day||0),cls:"neg"},
  {lab:"Up / Down",val:(f.up_days||0)+" / "+(f.down_days||0)}]));}
function fmtUptime(s){const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return d?`${d}d ${h}h`:(h?`${h}h ${m}m`:`${m}m`);}
function sdot(state){const c=state==="ok"?"var(--ok)":state==="warn"?"var(--warn)":"var(--crit)";return `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${c};margin-right:6px;vertical-align:middle"></span>`;}
function renderStatus(){
  const st=CMD.status||{},f=CMD.fleet||{},at=f.attention||{};
  const need=(at.critical||0)+(at.warning||0);
  const items=[
    sdot("ok")+"server up "+(st.uptime_s!=null?fmtUptime(st.uptime_s):"—"),
    sdot(st.data_through?"ok":"warn")+"data through "+(st.data_through||"—"),
    sdot(st.notion_ok?"ok":"warn")+"Notion "+(st.notion_ok?"connected":"check"),
    sdot((st.trades_total||0)>0?"ok":"warn")+"trade log "+((st.trades_total||0)>0?st.trades_total+" trades":"empty"),
    sdot((at.critical||0)>0?"crit":(at.warning||0)>0?"warn":"ok")+(need+" need attention"),
    sdot((f.breached||0)===0?"ok":"warn")+((f.breached||0)+" breached"),
  ];
  $("#sysStatus").innerHTML='<div style="display:flex;gap:20px;flex-wrap:wrap;align-items:center;font-family:var(--mono);font-size:12px;color:var(--muted)">'+items.map(i=>`<span>${i}</span>`).join("")+'</div>';
}
function renderAttention(){
  const items=CMD.attention||[];const box=$("#attnList");
  if(!items.length){box.innerHTML='<div class=card style="color:var(--ok);font-family:var(--mono);font-size:13px">✓ All clear — nothing needs attention right now.</div>';return;}
  const col={critical:"var(--crit)",warning:"var(--warn)",info:"var(--aqua)"},pill={critical:"h-crit",warning:"h-warn",info:"h-watch"};
  box.innerHTML=items.map(i=>`<div class=attn style="border-left:3px solid ${col[i.sev]||'var(--muted)'}">
    <div class=attn-h><b>${i.account}</b> <span style="color:var(--dim)">· ${i.firm}</span><span class="pill ${pill[i.sev]||'h-idle'}" style="margin-left:auto">${i.title}</span></div>
    <div class=attn-d>${i.detail}</div></div>`).join("");
}
const cls=n=>n>0?"pos":n<0?"neg":"";
const HEALTH={Healthy:{c:"var(--ok)",cls:"h-ok",r:5},Watch:{c:"var(--watch)",cls:"h-watch",r:4},Warning:{c:"var(--warn)",cls:"h-warn",r:3},Critical:{c:"var(--crit)",cls:"h-crit",r:2},Breached:{c:"var(--dead)",cls:"h-dead",r:1}};
const H=h=>HEALTH[h]||{c:"var(--dim)",cls:"h-idle",r:0};
let CMD={accounts:[],assets:[],firms:[],fleet:{}};
const WLAB={day:"Day",week:"Week",month:"Month",quarter:"Quarter",rolling:"Rolling",all:"All"};
let WIN="all";
function renderTf(){
  $("#tf").innerHTML=Object.keys(WLAB).map(w=>`<button data-w="${w}" aria-pressed="${w===WIN}">${WLAB[w]}</button>`).join("");
  $("#tf").querySelectorAll("button").forEach(b=>b.addEventListener("click",()=>{
    WIN=b.dataset.w;$("#tf").querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",x===b));loadCommand();}));
}
const SLAB={all:"All types",funded:"Funded",eval:"Eval"};
let STAGE="all";
function renderStage(){
  $("#stagef").innerHTML=Object.keys(SLAB).map(s=>`<button data-s="${s}" aria-pressed="${s===STAGE}">${SLAB[s]}</button>`).join("");
  $("#stagef").querySelectorAll("button").forEach(b=>b.addEventListener("click",()=>{
    STAGE=b.dataset.s;$("#stagef").querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",x===b));loadCommand();}));
}

function renderKpis(f){
  const k=[
    {lab:"Realized P&L",val:f.realized_net==null?"—":signed(f.realized_net),cls:cls(f.realized_net||0),note:"ledger · reconciles"},
    {lab:"Funded P&L",val:f.funded_net==null?"—":signed(f.funded_net),cls:cls(f.funded_net||0),note:"PA accounts (compounding)"},
    {lab:"Survival buffer",val:f.survival_buffer==null?"—":money0(f.survival_buffer),cls:"gold",note:"sum of live buffers"},
    {lab:"Accounts",val:(f.accounts||0),cls:"aqua",note:(f.breached||0)+" breached"},
    {lab:"Best asset",val:f.best_asset?f.best_asset+" "+signed(f.best_asset_net):"—",cls:"gold",note:"largest edge"},
  ];
  $("#kpis").innerHTML=k.map(x=>`<div class=kpi><div class=lab>${x.lab}</div><div class="val ${x.cls}">${x.val}</div><div class=note>${x.note}</div></div>`).join("");
}
function renderFleet(){
  const acc=CMD.accounts, order=["Healthy","Watch","Warning","Critical","Breached"];
  const dist={}; acc.forEach(a=>{if(HEALTH[a.health])dist[a.health]=(dist[a.health]||0)+1});
  const tot=Object.values(dist).reduce((x,y)=>x+y,0)||1;
  $("#healthbar").innerHTML=order.filter(h=>dist[h]).map(h=>`<span style="width:${100*dist[h]/tot}%;background:${H(h).c}">${dist[h]}</span>`).join("")||`<span style="width:100%;background:var(--dim)">—</span>`;
  $("#legend").innerHTML=order.filter(h=>dist[h]).map(h=>`<span><i style="background:${H(h).c}"></i>${h} · ${dist[h]}</span>`).join("");
  const mx=Math.max(1,...CMD.assets.map(a=>Math.abs(a.net)));
  $("#attr").innerHTML=CMD.assets.map(a=>{const w=100*Math.abs(a.net)/mx,col=a.net>=0?"var(--ok)":"var(--crit)";
    return `<div class=a-row><span class="tag ${a.cls}">${a.sym}</span><div class=track><i style="width:${w}%;background:${col}"></i></div><span class="a-val ${cls(a.net)}">${signed(a.net)}</span></div>`}).join("");
  const w=acc.filter(a=>a.bufpct!=null).sort((x,y)=>x.bufpct-y.bufpct).slice(0,5);
  $("#watch").innerHTML=w.map(a=>{const h=H(a.health),p=Math.max(0,Math.min(100,a.bufpct));
    return `<div style="display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid rgba(28,63,67,.5);font-family:var(--mono);font-size:12.5px">
      <b style="width:42px">${a.id}</b><div class=bufbar style="flex:1;width:auto"><i style="width:${p}%;background:${h.c}"></i></div>
      <span style="width:74px;text-align:right;color:${h.c}">${a.buffer==null?"—":money0(a.buffer)}</span>
      <span class="pill ${h.cls}" style="width:64px;text-align:center">${a.health}</span></div>`}).join("")||'<div class=calc>—</div>';
  const fb=document.querySelector("#feesRow b");if(fb)fb.textContent="−"+money0((CMD.fleet||{}).fees||0);
}
function renderAccts(rows){
  $("#acctTable tbody").innerHTML=rows.map(a=>{const h=H(a.health),p=a.bufpct==null?0:Math.max(0,Math.min(100,a.bufpct));
    return `<tr><td class=acct>${a.id} <span class=firmdot>· ${a.firm}</span></td><td>${a.stage}</td>
      <td class=num>${money(a.current)}</td>
      <td class=num>${a.floor==null?'<span class=calc>—</span>':money(a.floor)+" "+(a.seed?'<span class=seed>◆</span>':'<span class=calc>○</span>')}</td>
      <td class=num style="color:${a.buffer==null?'var(--dim)':(a.buffer<0?'var(--crit)':'var(--ink)')}">${a.buffer==null?"—":money(a.buffer)}</td>
      <td class=num><div class=bufcell>${a.bufpct==null?"—":a.bufpct.toFixed(1)+"%"}<span class=bufbar><i style="width:${p}%;background:${h.c}"></i></span></div></td>
      <td class="num ${cls(a.net||0)}">${a.net==null?"—":signed(a.net)}</td>
      <td class=num>${a.win_pct!=null?a.win_pct+'%':'—'}</td>
      <td class="num ${pfCls(a.pf)}">${a.pf==null?'—':a.pf}</td>
      <td class=num><span class="pill ${h.cls}">${a.health}</span></td></tr>`}).join("")||'<tr><td colspan=10 class=calc>no accounts</td></tr>';
}
let acctSort={k:"hrank",dir:1};
function sortAccts(k,t){
  acctSort=acctSort.k===k?{k,dir:-acctSort.dir}:{k,dir:t==="s"?1:-1};
  const rows=[...CMD.accounts].sort((a,b)=>{let x=a[k],y=b[k];if(x==null)x=-Infinity;if(y==null)y=-Infinity;
    return t==="s"?acctSort.dir*String(x).localeCompare(String(y)):acctSort.dir*(x-y)});
  renderAccts(rows);markSort("#acctTable",k,acctSort.dir);
}
function markSort(tbl,k,dir){document.querySelectorAll(tbl+" thead th").forEach(th=>{
  const base=th.textContent.replace(/[▲▼]\s*$/,"").trim();
  th.innerHTML=th.dataset.k===k?base+' <span class=ar>'+(dir>0?"▲":"▼")+'</span>':base})}
// generic: click a header (with data-k / data-t=s|n) to sort any table by that column.
function wireSort(tblId,getRows,render){
  const S=(wireSort._s=wireSort._s||{}), st=S[tblId]||(S[tblId]={k:null,dir:1});
  const get=(o,k)=>k.split('.').reduce((v,p)=>v==null?v:v[p],o);
  document.querySelectorAll('#'+tblId+' thead th[data-k]').forEach(th=>{th.style.cursor='pointer';
    th.onclick=()=>{const k=th.dataset.k,t=th.dataset.t||'n';
      st.dir=st.k===k?-st.dir:(t==='s'?1:-1); st.k=k;
      const rows=[...getRows()].sort((a,b)=>{let x=get(a,k),y=get(b,k);
        if(x==null)x=(t==='s'?'￿':-Infinity); if(y==null)y=(t==='s'?'￿':-Infinity);
        return t==='s'?st.dir*String(x).localeCompare(String(y)):st.dir*((+x)-(+y));});
      render(rows); markSort('#'+tblId,k,st.dir);};
  });
}
function renderFirms(){$("#firmCards").innerHTML=CMD.firms.map(f=>`<div class=card>
  <div class=ey>${f.name}</div><div class="big ${f.net>0?'pos':(f.net<0?'neg':'')}">${f.net?signed(f.net):"—"}</div>
  <div class=row><span>Accounts</span><b>${f.accts}</b></div>
  <div class=row><span>Survival buffer</span><b>${f.buffer?money0(f.buffer):"—"}</b></div></div>`).join("")||'<div class=calc>—</div>'}
// (strategy card labels below)
function renderStrats(){
  const ep=CMD.eval_passes||[], tot=ep.reduce((s,x)=>s+x.passes,0);
  $("#evalPasses").innerHTML = ep.length
    ? `<div class=card><div class=ey>Eval passes per strategy <span class=calc>· ${tot} total · registered in Notion</span></div>`
      + `<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:12px">`
      + ep.map(x=>`<span class=tag style="font-size:13px;padding:6px 11px"><b class=pos>${x.passes}</b> · <b>${x.asset}</b> ${x.strategy}</span>`).join('')
      + `</div></div>`
    : `<div class=calc>Set the <b>Strategy</b> field on your accounts (Accounts DB) — passed evals then show here and drive the eval recommendation.</div>`;
  $("#stratCards").innerHTML=CMD.assets.map(a=>`<div class=card>
  <div class=ey><span class="tag ${a.cls}">${a.sym}</span> <span class="tag ${a.micro?'micro':'full'}">${a.micro?'micro':'full'}</span> ${a.robust?'<span style="color:var(--ok)">funded edge</span>':'<span style="color:var(--warn)">eval</span>'}</div>
  <div class="big ${cls(a.net)}">${signed(a.net)}</div><div class=row><span>${a.engine}</span></div>
  <div class=row><span>Trades</span><b>${a.n}</b></div><div class=row><span>Win rate</span><b>${a.win.toFixed(1)}%</b></div>
  <div class=row><span>Profit factor</span><b class="${pfCls(a.pf)}">${a.pf==null?'—':a.pf}</b></div>
  <div class=row><span>Expectancy</span><b class="${cls(a.expectancy)}">${money0(a.expectancy)}</b></div>
  <div class=row><span>Avg win / loss</span><b>${money0(a.avg_win)} / ${money0(a.avg_loss)}</b></div>
  <div class=row><span>Net ticks</span><b>${signed(a.ticks)}</b></div>
  <div class=row><span>Fees</span><b style="color:var(--warn)">${a.comm?"−"+money0(a.comm):"—"}${a.fees_pct!=null?' ('+a.fees_pct+'%)':''}</b></div>
  <div class=row><span>MFE / MAE (heat)</span><b>${a.mfe!=null?a.mfe+"t / "+(a.mae!=null?a.mae+"t":"—"):"—"}</b></div></div>`).join("")||'<div class=calc>—</div>'}
function renderAssets(rows){$("#assetTable tbody").innerHTML=(rows||CMD.assets).map(a=>`<tr>
  <td class=acct><span class="tag ${a.cls}">${a.sym}</span> <span class="tag ${a.micro?'micro':'full'}">${a.micro?'micro':'full'}</span></td><td style="color:var(--muted)">${a.engine}</td>
  <td class=num>${a.n}</td><td class=num>${a.win.toFixed(1)}%</td>
  <td class="num ${pfCls(a.pf)}">${a.pf==null?'—':a.pf}</td><td class="num ${cls(a.expectancy)}">${money0(a.expectancy)}</td>
  <td class="num ${cls(a.ticks)}">${signed(a.ticks)}</td><td class="num ${cls(a.net)}">${signed(a.net)}</td>
  <td class=num style="color:var(--warn)">${a.comm?'−'+money0(a.comm):'—'}${a.fees_pct!=null?' <span class=calc>('+a.fees_pct+'%)</span>':''}</td>
  <td class=num>${a.mfe!=null?a.mfe+'t / '+(a.mae!=null?a.mae+'t':'—'):'<span class=calc>—</span>'}</td>
  <td class=num style="text-align:left;color:${a.robust?'var(--ok)':'var(--warn)'}">${a.edge}</td></tr>`).join("")||'<tr><td colspan=11 class=calc>no trades</td></tr>'}
function renderPayout(){
  const f=CMD.fleet||{};
  const funded=CMD.accounts.filter(a=>a.payout&&a.payout.stage==='Funded');   // PA accounts only
  const notElig=funded.filter(a=>!a.payout.eligible).length;
  $("#payoutKpis").innerHTML=
    `<div class=card><div class=ey>Withdrawable now</div><div class="big pos">${money0(f.withdrawable||0)}</div>
      <div class=row><span>Accounts eligible</span><b>${f.payout_eligible||0}</b></div></div>`+
    `<div class=card><div class=ey>Funded accounts</div><div class="big">${funded.length}</div>
      <div class=row><span>Not yet eligible</span><b>${notElig}</b></div>
      <div class=row><span>Funded P&amp;L (ledger)</span><b class="${cls(f.funded_net||0)}">${signed(f.funded_net||0)}</b></div></div>`;
  $("#payoutCards").innerHTML=funded.map(a=>{const p=a.payout;
    const chk=(p.rules||[]).map(r=>{const c=r.ok?'var(--ok)':'var(--warn)';
      return `<div class=row><span style="color:var(--muted)">${r.name}</span><b style="font-weight:500;color:var(--ink)"><span style="color:${c}">●</span> ${r.detail}</b></div>`}).join('');
    const capNote=p.cap?`rung ${(p.rung||0)+1} · cap ${money0(p.cap)}`+(p.above_safety>p.cap?` · ${money0(p.above_safety-p.cap)} above cap carries`:''):'';
    const head=p.eligible
      ? `<div class="big pos" style="font-size:23px">${money0(p.withdrawable)}</div><div class=ey style="color:var(--ok)">withdrawable · eligible</div><div class=calc>${capNote}</div>`
      : `<div style="font-family:var(--mono);font-size:15px;color:var(--muted);margin:8px 0 3px">Not yet eligible</div><div class=ey>${p.above_safety>0?'potential '+money0(Math.min(p.above_safety,p.cap||p.above_safety))+' at payout':'below safety net'}</div><div class=calc>${capNote}</div>`;
    return `<div class=card><div class=ey style="color:var(--ink);font-size:13px;letter-spacing:0;text-transform:none">${a.id} · <span style="color:var(--muted)">${a.firm}</span></div>
      ${head}<div style="margin-top:10px">${chk}</div></div>`}).join('')||'<div class=calc>no funded accounts</div>';
}
const PB_PHASE={survival:["var(--warn)","survival"],milking:["var(--ok)","milking"],
  "payout-ready":["var(--gold)","payout ✓"],compound:["var(--aqua)","compound"],
  "eval-sprint":["var(--muted)","eval sprint"],maxed:["var(--gold)","maxed"]};
function renderPlaybook(rows){
  const list=rows||CMD.accounts.filter(a=>a.playbook);
  $("#pbTable tbody").innerHTML=list.map(a=>{const p=a.playbook;
    const sw=p.switch?` <span style="color:${p.off_edge?'var(--crit)':'var(--warn)'}" title="currently ${p.cur_instrument||'—'}">↹ ${p.cur_instrument||'—'}</span>`:'';
    const run=`<b>${p.rec_instrument||p.rec_base||'—'}</b> <span style="color:var(--muted)">${p.rec_strategy}</span>${sw}`;
    const setCol=`<b style="color:var(--gold)">${p.contracts_label||'—'}</b>`
      +(p.day_cap!=null?`<br>day-cap <b>${money0(p.day_cap)}</b>`:'')
      +(p.dll!=null?`<br>DLL <b>${money0(p.dll)}</b>`:'')
      +(p.exp_pc!=null?`<br><span class=calc>edge ${money0(p.exp_pc)}/ct × ${p.tpd}/d</span>`:'<br><span class=calc>doctrine size (thin data)</span>');
    const ph=PB_PHASE[p.phase]||["var(--muted)",p.phase];
    const phase=`<span class=pill style="background:${ph[0]};color:#04121a">${ph[1]}</span>`;
    const consWarn=p.consistency_pct!=null&&p.consistency_pct>=20;
    const topWarn=p.best_day&&p.cons_cap&&p.best_day>p.cons_cap;
    const st=`<b class="${cls(p.profit||0)}">${p.profit!=null?signed(p.profit):'—'}</b> <span class=calc>P/L · ${p.trading_days}d</span>`
      +(p.buffer!=null?`<br><span style="color:${p.buffer<1000?'var(--crit)':'var(--muted)'}">buf ${money0(p.buffer)}</span>`:'')
      +(p.consistency_pct!=null?` <span style="color:${consWarn?'var(--warn)':'var(--muted)'}">· ${p.consistency_pct}% top day</span>`:'')
      +(p.withdrawable_now!=null?`<br><span class=calc>pull ${money0(p.withdrawable_now)}/${money0(p.cap)}${p.total_cap?' · paid '+money0(p.total_paid)+'/'+money0(p.total_cap):''}</span>`:'')
      +((p.best_day||p.cons_cap)?`<br><span style="color:${topWarn?'var(--crit)':'var(--muted)'}">top day ${money0(p.best_day)} · ${Math.round((p.consistency_limit||0.3)*100)}% max ${p.cons_cap?money0(p.cons_cap):'—'}</span>`:'');
    const flag=p.note?`<div style="color:var(--warn);font-size:11px;margin-bottom:3px">⚑ ${p.note}</div>`:'';
    const rcol=(p.quality==='payout'||p.phase==='maxed')?'var(--gold)':'var(--ink)';
    return `<tr>
      <td class=acct>${a.id} <span class=firmdot>· ${a.stage}</span>${p.program?`<br><span class=calc title="rules from data/propfirms.json — the single source of truth${p.firm_verified===false?' (unverified — VERIFY)':''}">${p.program}${p.firm_verified===false?' ⚠':''}</span>`:'<br><span class=calc style="color:var(--warn)">no Account Type set</span>'}</td>
      <td style="text-align:left">${run}</td>
      <td>${phase}</td>
      <td style="text-align:left;font-size:12px;font-family:var(--mono)">${st}</td>
      <td style="text-align:left;font-family:var(--mono);font-size:12px">${setCol}</td>
      <td style="text-align:left;white-space:normal;max-width:430px">${flag}<span style="color:${rcol}">${p.route}</span></td>
    </tr>`;
  }).join('')||'<tr><td colspan=6 class=calc>no accounts</td></tr>';
}
function bar(label,pct,right,color){
  return `<div style="margin:9px 0;font-family:var(--mono);font-size:12px">
    <div style="display:flex;justify-content:space-between;margin-bottom:3px;gap:10px"><span style="color:var(--muted)">${label}</span><b style="white-space:nowrap">${right}</b></div>
    <div style="height:8px;background:rgba(28,63,67,.6);border-radius:4px;overflow:hidden"><i style="display:block;height:100%;width:${Math.max(0,Math.min(100,pct))}%;background:${color}"></i></div></div>`;
}
function renderPortfolio(){
  const p=CMD.portfolio;if(!p)return;
  const sc={Funded:"var(--aqua)",Eval:"var(--gold)"};
  $("#allocStage").innerHTML=p.alloc_stage.map(s=>bar(s.name,s.pct,money0(s.capital)+" · "+s.pct+"%",sc[s.name]||"var(--muted)")).join('')||'<div class=calc>—</div>';
  $("#allocFirm").innerHTML=p.alloc_firm.map(f=>bar(f.name,f.pct,money0(f.capital)+" · "+f.pct+"%","var(--aqua)")).join('')||'<div class=calc>—</div>';
  $("#allocAsset").innerHTML=p.alloc_asset.map(a=>bar(a.sym,Math.max(0,a.pct),signed(a.net)+(a.pct>0?" · "+a.pct+"%":""),a.net>=0?"var(--ok)":"var(--crit)")).join('')||'<div class=calc>—</div>';
  const c=p.correlation||{labels:[],matrix:[]};
  $("#corrDays").textContent=c.days?"· "+c.days+" days":"";
  if(c.labels.length<2){$("#corrMatrix").innerHTML='<div class=calc>not enough overlapping data</div>';return;}
  const cell=v=>{if(v==null)return '<td class=hm-empty style="min-width:52px">—</td>';
    const a=Math.min(1,Math.abs(v));const col=v>=0?`rgba(53,200,138,${(0.1+0.6*a).toFixed(2)})`:`rgba(239,107,83,${(0.1+0.6*a).toFixed(2)})`;
    return `<td class=hm-cell style="background:${col};min-width:52px">${v.toFixed(2)}</td>`;};
  let h='<table class=hm><thead><tr><th></th>'+c.labels.map(l=>`<th>${l}</th>`).join('')+'</tr></thead><tbody>';
  h+=c.matrix.map((row,i)=>`<tr><th>${c.labels[i]}</th>`+row.map(cell).join('')+'</tr>').join('');
  $("#corrMatrix").innerHTML=h+'</tbody></table>';
}
function renderEquity(){
  const eq=CMD.equity;const box=$("#eqChart");if(!eq)return;
  const cur=eq.curve||[],proj=eq.proj||[];
  if(cur.length<2){box.innerHTML='<div class=calc style="padding:16px">not enough days in this window</div>';$("#eqStats").innerHTML='';return;}
  const W=900,H=300,pL=10,pR=10,pT=14,pB=14,nH=cur.length,nP=proj.length,total=nH+nP;
  const xs=i=>pL+(i/(total-1))*(W-pL-pR);
  const vals=[0,...cur.map(c=>c.cum),...proj.map(p=>p.lo),...proj.map(p=>p.hi)];
  let ymin=Math.min(...vals),ymax=Math.max(...vals);if(ymin===ymax){ymin-=1;ymax+=1;}
  const pd=(ymax-ymin)*0.08;ymin-=pd;ymax+=pd;
  const ys=v=>pT+(1-(v-ymin)/(ymax-ymin))*(H-pT-pB);
  const y0=ys(0).toFixed(1);
  const hp=cur.map((c,i)=>`${i?'L':'M'}${xs(i).toFixed(1)} ${ys(c.cum).toFixed(1)}`).join(' ');
  const areaH=`M${xs(0).toFixed(1)} ${y0} `+cur.map((c,i)=>`L${xs(i).toFixed(1)} ${ys(c.cum).toFixed(1)}`).join(' ')+` L${xs(nH-1).toFixed(1)} ${y0} Z`;
  const lastX=xs(nH-1),lastY=ys(cur[nH-1].cum);
  const hi=proj.map((p,i)=>`L${xs(nH+i).toFixed(1)} ${ys(p.hi).toFixed(1)}`).join(' ');
  const lo=proj.slice().reverse().map((p,i)=>`L${xs(total-1-i).toFixed(1)} ${ys(p.lo).toFixed(1)}`).join(' ');
  const cone=`M${lastX.toFixed(1)} ${lastY.toFixed(1)} ${hi} ${lo} Z`;
  const mid=`M${lastX.toFixed(1)} ${lastY.toFixed(1)} `+proj.map((p,i)=>`L${xs(nH+i).toFixed(1)} ${ys(p.mid).toFixed(1)}`).join(' ');
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block">
    <line x1="${pL}" y1="${y0}" x2="${W-pR}" y2="${y0}" stroke="#1c3f43" stroke-dasharray="3 4"/>
    <line x1="${lastX.toFixed(1)}" y1="${pT}" x2="${lastX.toFixed(1)}" y2="${H-pB}" stroke="#1c3f43" stroke-dasharray="2 4"/>
    <path d="${areaH}" fill="rgba(240,182,77,.12)"/>
    <path d="${cone}" fill="rgba(63,208,189,.12)"/>
    <path d="${mid}" fill="none" stroke="#3fd0bd" stroke-width="1.4" stroke-dasharray="5 3" opacity=".85"/>
    <path d="${hp}" fill="none" stroke="#f0b64d" stroke-width="2.2"/>
    <circle cx="${lastX.toFixed(1)}" cy="${lastY.toFixed(1)}" r="4" fill="#f0b64d"/></svg>`;
  const lastCum=cur[nH-1].cum,lp=proj[proj.length-1]||{mid:lastCum,lo:lastCum,hi:lastCum};
  $("#eqStats").innerHTML=tiles([
    {lab:"Equity (cum)",val:signed(lastCum),cls:cls(lastCum)},
    {lab:"Max drawdown",val:money0(eq.max_dd),cls:"neg"},
    {lab:"Exp / day",val:money0(eq.exp_day),cls:cls(eq.exp_day)},
    {lab:"Std / day",val:money0(eq.std_day)},
    {lab:"Proj +"+nP+"d",val:signed(lp.mid),cls:cls(lp.mid-lastCum)},
    {lab:"Range +"+nP+"d",val:money0(lp.lo)+" … "+money0(lp.hi)},
  ]);
}
const MON=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function calSeries(){
  const cal=CMD.calendar;if(!cal)return {};
  const v=$("#calDim").value||"all";
  if(v==="all"){const m={};(cal.by_day||[]).forEach(x=>m[x.d]={net:x.net,n:x.n});return m;}
  const i=v.indexOf(":"),k=v.slice(0,i),name=v.slice(i+1);
  return ((k==="asset"?cal.asset_day:k==="strat"?cal.strat_day:cal.acct_day)||{})[name]||{};
}
function calStatsFor(){
  const v=$("#calDim").value||"all";
  if(v==="all")return CMD.fleet||{};
  const i=v.indexOf(":"),k=v.slice(0,i),name=v.slice(i+1);
  if(k==="asset")return (CMD.assets||[]).find(a=>a.sym===name)||{};
  if(k==="strat")return (CMD.strat_stats||{})[name]||{};
  return (CMD.accounts||[]).find(a=>a.id===name)||{};
}
function renderCalendar(){
  const cal=CMD.calendar;if(!cal)return;const sel=$("#calDim");
  const st=Object.keys(cal.strat_day||{}).sort(),as=Object.keys(cal.asset_day||{}).sort(),ac=Object.keys(cal.acct_day||{}).sort();
  const sig="c|"+st.join(",")+"|"+as.join(",")+"|"+ac.join(",");
  if(sel.dataset.sig!==sig){dimOptions(sel,[["strat","Strategy",st],["asset","Asset",as],["acct","Account",ac]],sel.value);sel.dataset.sig=sig;sel.onchange=drawCalendar;}
  drawCalendar();
}
function drawCalendar(){
  $("#calStats").innerHTML=tiles(statItems(calStatsFor()));
  const series=calSeries();const dates=Object.keys(series).sort();const grid=$("#calGrid");
  if(!dates.length){grid.innerHTML='<div class=calc style="padding:16px">no trades in this window</div>';$("#calTotal").textContent='';return;}
  const parse=s=>{const p=s.split("-").map(Number);return new Date(Date.UTC(p[0],p[1]-1,p[2]));};
  const last=parse(dates[dates.length-1]);const cur=parse(dates[0]);
  cur.setUTCDate(cur.getUTCDate()-((cur.getUTCDay()+6)%7));           // back to Monday
  const mx=Math.max(1e-9,...Object.values(series).map(c=>Math.abs(c.n?c.net/c.n:c.net)));  // max |expectancy|
  let html='<table class=cal><thead><tr><th></th>'+["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map(d=>`<th>${d}</th>`).join('')+'<th>Week</th></tr></thead><tbody>';
  let total=0;
  while(cur<=last){
    const wkMonth=MON[cur.getUTCMonth()],wkDate=cur.getUTCDate();
    let wtot=0,row='',any=false;
    for(let i=0;i<7;i++){
      const iso=cur.toISOString().slice(0,10);
      if(iso in series){const c=series[iso],v=c.net;wtot+=v;total+=v;any=true;
        row+=`<td class=cal-cell style="background:${heatColor(c.net,c.n,mx)}" title="${iso} · ${signed(v)} · ${c.n} trade(s) · exp ${money0(c.n?v/c.n:v)}"><span class=cal-d>${cur.getUTCDate()}</span>${moneyK(v)}</td>`;
      } else {
        row+=`<td class="cal-cell cal-empty"><span class=cal-d>${cur.getUTCDate()}</span></td>`;
      }
      cur.setUTCDate(cur.getUTCDate()+1);
    }
    html+=`<tr><th>${wkDate<=7?wkMonth:''}</th>${row}<td class=num style="color:${wtot>=0?'var(--ok)':'var(--crit)'}">${any&&wtot?moneyK(wtot):'—'}</td></tr>`;
  }
  grid.innerHTML=html+'</tbody></table>';
  $("#calTotal").innerHTML='Total: <b class="'+(total>=0?'pos':'neg')+'">'+signed(total)+'</b>';
}
const DOW=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
function dimOptions(sel,dims,prev){          // dims: [[key,label,names[]],...]
  let o='<option value="all">All (fleet)</option>';
  dims.forEach(([k,lab,names])=>{if(names.length)o+=`<optgroup label="${lab}">`+names.map(n=>`<option value="${k}:${n}">${n}</option>`).join('')+'</optgroup>';});
  sel.innerHTML=o;
  if(prev&&[...sel.options].some(op=>op.value===prev))sel.value=prev;
}
function hmCells(){
  const hm=CMD.heatmap;if(!hm)return [];
  const v=$("#hmDim").value||"all";
  if(v==="all")return hm.all||[];
  const i=v.indexOf(":"),k=v.slice(0,i),name=v.slice(i+1);
  return ((k==="asset"?hm.asset:k==="strat"?hm.strat:hm.acct)||{})[name]||[];
}
function renderHeatmap(){
  const hm=CMD.heatmap;if(!hm||!hm.all)return;const sel=$("#hmDim");
  const st=Object.keys(hm.strat||{}).sort(),as=Object.keys(hm.asset||{}).sort(),ac=Object.keys(hm.acct||{}).sort();
  const sig="h|"+st.join(",")+"|"+as.join(",")+"|"+ac.join(",");
  if(sel.dataset.sig!==sig){dimOptions(sel,[["strat","Strategy",st],["asset","Asset",as],["acct","Account",ac]],sel.value);sel.dataset.sig=sig;sel.onchange=drawHeatmap;}
  drawHeatmap();
}
function drawHeatmap(){
  const cells=hmCells();const grid=$("#hmGrid");
  if(!cells.length){grid.innerHTML='<div class=calc style="padding:16px">no trades for this selection</div>';return;}
  const hours=[...new Set(cells.map(c=>c.hour))].sort((a,b)=>a-b);
  const dows=[...new Set(cells.map(c=>c.dow))].sort((a,b)=>a-b);
  const map={};cells.forEach(c=>map[c.dow+"_"+c.hour]=c);
  const mx=Math.max(1e-9,...cells.map(c=>Math.abs(c.n?c.net/c.n:c.net)));   // max |expectancy|
  const cell=(d,h)=>{const c=map[d+"_"+h];if(!c)return '<td class=hm-empty></td>';
    return `<td class=hm-cell style="background:${heatColor(c.net,c.n,mx)}" title="${DOW[d]} ${h}:00 ET · ${c.n} trade(s) · ${signed(c.net)} · exp ${money0(c.n?c.net/c.n:c.net)}">${moneyK(c.net)}</td>`;};
  let html='<table class=hm><thead><tr><th></th>'+hours.map(h=>`<th>${h}h</th>`).join('')+'</tr></thead><tbody>';
  html+=dows.map(d=>`<tr><th>${DOW[d]}</th>`+hours.map(h=>cell(d,h)).join('')+'</tr>').join('');
  grid.innerHTML=html+'</tbody></table>';
}

async function loadCommand(){
  let s;try{s=await(await fetch("/api/command?window="+encodeURIComponent(WIN)+"&stage="+encodeURIComponent(STAGE),{cache:"no-store"})).json()}catch(e){return}
  if(!s||s.error){renderKpis({});return}
  CMD=s;renderKpis(s.fleet);renderFleet();
  $("#topStats").innerHTML=fleetTiles(s.fleet);renderStatus();renderAttention();
  sortAccts("hrank","n");renderFirms();renderStrats();renderAssets();renderPayout();renderPlaybook();renderHeatmap();renderPortfolio();renderCalendar();renderEquity();
  wireSort('acctTable',()=>CMD.accounts,renderAccts);
  wireSort('assetTable',()=>CMD.assets,renderAssets);
  wireSort('pbTable',()=>CMD.accounts.filter(a=>a.playbook),renderPlaybook);
  if(s.window_label)$("#tflabel").textContent=s.window_label;
  $("#asof").textContent=s.as_of?"· updated "+new Date(s.as_of).toLocaleTimeString("en-GB",{hour:"2-digit",minute:"2-digit"}):"";
  const f=s.fleet;$("#footnet").innerHTML=f.trades?`${f.trades} trades · fleet realized <b>${signed(f.realized_net)}</b>`:"";
}
async function loadLive(){
  let s;try{s=await(await fetch("/api/state",{cache:"no-store"})).json()}catch(e){return}
  if(!s||s.error){$("#livenote").textContent="no live data";return}
  const f=s.fleet||{};
  $("#liveKpis").innerHTML=
    `<div class=card><div class=ey>Realized today</div><div class="big ${cls(f.realized_today||0)}">${money(f.realized_today||0)}</div>
      <div class=row><span>Open positions</span><b>${f.open_positions||0}</b></div>
      <div class=row><span>Trades today</span><b>${f.trades_today||0}</b></div></div>`+
    `<div class=card><div class=ey>Fleet today</div>
      <div class=row><span>Win rate</span><b>${f.win_rate==null?"—":f.win_rate+"%"}</b></div>
      <div class=row><span>Profit factor</span><b>${f.profit_factor==null?"—":f.profit_factor}</b></div>
      <div class=row><span>Accounts active</span><b>${f.accounts||0}</b></div></div>`;
  const rows=s.accounts||[];
  $("#liveTable tbody").innerHTML=rows.map(a=>`<tr><td class=acct>${a.account}</td>
    <td>${a.phase==="funded"?"Funded":"Eval"}</td>
    <td><span class="pill ${a.open.length?'h-ok':'h-idle'}">${a.status}</span></td>
    <td class=num>${a.open.length||"—"}</td><td class=num>${(a.wins+a.losses)||"—"}</td>
    <td class="num ${cls(a.realized_today)}">${a.realized_today?money(a.realized_today):"—"}</td></tr>`).join("")||'<tr><td colspan=6 class=calc>no activity today</td></tr>';
}
const tabs=[...document.querySelectorAll(".tab")];
tabs.forEach(t=>t.addEventListener("click",()=>{
  tabs.forEach(x=>x.setAttribute("aria-selected",x===t));
  document.querySelectorAll('section[role=tabpanel]').forEach(s=>s.hidden=s.id!==t.dataset.panel);
  if(t.dataset.panel==="live")loadLive();
}));
function tick(){const d=new Date();
  const t=d.toLocaleTimeString("en-GB",{hour12:false,timeZone:"America/New_York"});
  $("#clock").textContent=t+" ET · "+d.toLocaleDateString("en-GB",{day:"2-digit",month:"short",timeZone:"America/New_York"})}
tick();setInterval(tick,1000);
renderTf();renderStage();loadCommand();setInterval(loadCommand,60000);
setInterval(()=>{if(!$("#live").hidden)loadLive()},15000);
</script></html>"""


if __name__ == "__main__":
    serve()
