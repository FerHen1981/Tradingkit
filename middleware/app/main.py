"""MEX trade middleware — the switchboard between TradingView and your broker accounts.

Endpoints
  GET  /health        liveness probe
  POST /webhook       receive a Signal from TradingView, fan out to accounts
  POST /pmt           passthrough: ready-made PMT payload in, forwarded 1:1 to PMT
  POST /discord       DISC-embed in -> trade-card (render-signal.js) -> Discord
  POST /signal/{secret}  UNIVERSELE TRECHTER: herkent PMT-JSON / Discord-embed /
                      lean signal / PineConnector-tekst en routeert elk naar zijn doel
  GET  /journal       last N journalled events (debug; secret-gated)
  POST /killswitch    enable/disable dispatching fleet-wide (secret-gated)

Phase 0 = receive + journal. Phase 1 = PMT (Tradovate) dispatch in DRY_RUN.
"""
from __future__ import annotations

import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from pydantic import ValidationError

from .config import Settings, load_accounts
from .dedupe import Deduper
from .journal import Journal
from .models import Signal
from .notify import alert_failure
from .risk import RiskState
from .router import dispatch
from .brokers import pmt as pmt_broker
from .render import render_card

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mex.middleware")

app = FastAPI(title="MEX trade middleware", version="0.1.0")

settings = Settings()
accounts = load_accounts(settings.accounts_file)
journal = Journal(settings.journal_db)
deduper = Deduper(settings.idem_ttl)
risk = RiskState(settings.max_entries_default)

# Runtime kill-switch (in addition to DRY_RUN). True = orders may dispatch.
STATE = {"armed": True}


def _check_secret(supplied: str) -> None:
    if not settings.secret:
        raise HTTPException(500, "MIDDLEWARE_SECRET not configured on the server")
    if supplied != settings.secret:
        raise HTTPException(401, "bad secret")


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "dry_run": settings.dry_run,
        "armed": STATE["armed"],
        "strategies": list(accounts.strategies.keys()),
        "accounts": len(accounts.accounts),
    }


@app.post("/webhook")
async def webhook(request: Request) -> dict:
    raw = await request.body()
    try:
        sig = Signal.model_validate_json(raw)
    except ValidationError as exc:
        journal.write("error", {"reason": "validation", "errors": exc.errors(), "raw": raw.decode("utf-8", "replace")[:1000]})
        raise HTTPException(422, "invalid signal")

    _check_secret(sig.secret)
    journal.write("signal", sig.redacted(), strategy=sig.strategy)
    log.info("signal %s %s %s qty=%s", sig.strategy, sig.event, sig.action, sig.qty)

    if not STATE["armed"]:
        return {"accepted": True, "dispatched": False, "reason": "kill-switch: disarmed"}

    if deduper.seen_recently(sig):
        journal.write("dedupe", {"skipped": sig.redacted()}, strategy=sig.strategy)
        log.warning("duplicate signal within %ss — skipped", settings.idem_ttl)
        return {"accepted": True, "dispatched": False, "reason": "duplicate (idempotency)"}

    results = await dispatch(sig, accounts, settings, risk)
    failures = [r for r in results if r.get("status") == "error"]
    for r in results:
        journal.write("dispatch", r, strategy=sig.strategy, account=r.get("account", ""))
    if failures:
        summary = ", ".join(f"{r.get('account', '?')}: {r.get('reason') or r.get('http_status')}" for r in failures)
        await alert_failure(settings.alert_webhook,
                            f"⚠️ MEX middleware: {len(failures)} dispatch failure(s) on {sig.strategy} {sig.action} — {summary}")
    return {"accepted": True, "dispatched": True, "dry_run": settings.dry_run,
            "failures": len(failures), "results": results}


def _redact_pmt(p: dict) -> dict:
    """Mask tokens before journalling a raw PMT payload."""
    out = dict(p)
    if "token" in out:
        out["token"] = "***"
    if isinstance(out.get("multiple_accounts"), list):
        out["multiple_accounts"] = [
            {**a, "token": "***"} if isinstance(a, dict) and "token" in a else a
            for a in out["multiple_accounts"]
        ]
    return out


@app.post("/pmt")
async def pmt_passthrough(request: Request, secret: str) -> dict:
    """One-alert flow: the TradingView alert carries the ready-made PMT JSON (the
    Pine "PMT Tradovate" route) but points at THIS url. We journal, dedupe, apply
    the risk overlay, then forward the body verbatim to PMT. Exits are never
    blocked; entries respect kill-switch, halts and the per-account entry cap."""
    import hashlib
    import json as _json

    _check_secret(secret)
    raw = await request.body()
    try:
        payload = _json.loads(raw)
        assert isinstance(payload, dict)
    except Exception:
        journal.write("error", {"reason": "pmt_pass: invalid json", "raw": raw.decode("utf-8", "replace")[:500]})
        raise HTTPException(422, "invalid PMT payload")

    action = str(payload.get("data", "")).lower()
    is_entry = action in ("buy", "sell")
    accounts_in = payload.get("multiple_accounts") or []
    account_id = ""
    if accounts_in and isinstance(accounts_in[0], dict):
        account_id = str(accounts_in[0].get("account_id", ""))

    journal.write("pmt_pass", _redact_pmt(payload), account=account_id)
    log.info("pmt_pass %s %s acct=%s qty=%s", payload.get("symbol"), action, account_id, payload.get("quantity"))

    if is_entry and not STATE["armed"]:
        return {"accepted": True, "forwarded": False, "reason": "kill-switch: disarmed"}

    if deduper.seen_key(hashlib.sha1(raw).hexdigest()):
        journal.write("dedupe", {"skipped": "pmt_pass"}, account=account_id)
        return {"accepted": True, "forwarded": False, "reason": "duplicate (idempotency)"}

    if is_entry and account_id:
        allowed, why = risk.allow(account_id, accounts.accounts.get(account_id, {}), True)
        if not allowed:
            journal.write("risk_block", {"account": account_id, "reason": why}, account=account_id)
            return {"accepted": True, "forwarded": False, "reason": f"risk: {why}"}

    result = await pmt_broker.forward(payload, pmt_url=_pmt_url_for(account_id), dry_run=settings.dry_run,
                                      retry_max=settings.retry_max, retry_backoff=settings.retry_backoff)
    if is_entry and account_id and result.get("status") == "sent":
        risk.record_entry(account_id)
    journal.write("dispatch", {**result, "route": "pmt_pass", "account": account_id}, account=account_id)
    if result.get("status") == "error":
        await alert_failure(settings.alert_webhook,
                            f"\u26a0\ufe0f MEX middleware /pmt: forward failed for {account_id or '?'} \u2014 "
                            f"{result.get('reason') or result.get('http_status')}")
    return {"accepted": True, "forwarded": result.get("status") == "sent",
            "dry_run": settings.dry_run, "result": {k: v for k, v in result.items() if k != "payload"}}


def _pmt_url_for(account_id: str) -> str:
    """Pine stuurt voor PMT-Tradovate én PMT-Rithmic exact dezelfde JSON, dus de
    broker is niet uit het bericht af te leiden. We kiezen de endpoint op basis van
    het account: per-account `pmt_url:` in accounts.yaml wint, anders `broker:`
    (pmt_rithmic -> PMT_RITHMIC_URL), anders de globale PMT_URL."""
    acc = accounts.accounts.get(account_id, {}) or {}
    if acc.get("pmt_url"):
        return str(acc["pmt_url"])
    if "rithmic" in str(acc.get("broker", "")).lower() and settings.pmt_rithmic_url:
        return settings.pmt_rithmic_url
    return settings.pmt_url


async def _render_and_post(payload: dict) -> None:
    """Achtergrondtaak: kaart renderen + posten, uitkomst in het journaal."""
    res = await _post_discord_card(payload)
    journal.write("dispatch", {"route": "discord_card", **res})


async def _post_discord_card(payload: dict) -> dict:
    """Render the embed to a card and post it; fall back to the original embed."""
    import json as _json
    import os as _os

    import httpx

    png = await render_card(payload, render_cmd=settings.render_cmd, render_dir=settings.render_dir,
                            timeout=settings.render_timeout)
    if settings.dry_run:
        return {"status": "dry_run", "rendered": bool(png), "png": png}
    if not settings.discord_webhook:
        return {"status": "error", "reason": "DISCORD_WEBHOOK_URL not configured"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            if png and settings.charts_base_url:
                url = settings.charts_base_url.rstrip("/") + "/" + _os.path.basename(png)
                emb = (payload.get("embeds") or [{}])[0]
                body = {"username": payload.get("username", "MEX"),
                        "embeds": [{"title": emb.get("title", ""), "color": emb.get("color", 0),
                                    "image": {"url": url}}]}
                r = await client.post(settings.discord_webhook, json=body)
            elif png:
                with open(png, "rb") as fh:
                    r = await client.post(settings.discord_webhook,
                                          data={"payload_json": _json.dumps({"username": payload.get("username", "MEX")})},
                                          files={"file": (_os.path.basename(png), fh, "image/png")})
            else:
                r = await client.post(settings.discord_webhook, json=payload)
            ok = r.status_code < 400
        except Exception as exc:
            journal.write("error", {"reason": f"discord post: {exc!r}"})
            ok = False
    if not ok:
        await alert_failure(settings.alert_webhook, "\u26a0\ufe0f MEX middleware: Discord-post faalde")
    return {"status": "sent" if ok else "error", "rendered": bool(png)}


@app.post("/discord")
async def discord_card(request: Request, secret: str, background: BackgroundTasks) -> dict:
    """Losse Discord-route (embed in -> kaart uit). Zie ook /signal/{secret},
    dat hetzelfde doet maar ook PMT/lean-signalen herkent."""
    import json as _json

    _check_secret(secret)
    raw = await request.body()
    try:
        payload = _json.loads(raw)
        assert isinstance(payload, dict)
    except Exception:
        raise HTTPException(422, "invalid embed payload")
    journal.write("discord_in", {k: payload.get(k) for k in ("username", "embeds") if k in payload})
    background.add_task(_render_and_post, payload)
    return {"accepted": True, "queued": True, "dry_run": settings.dry_run}


# ---------------------------------------------------------------------------
# Universele ingest — één alert-URL per chart, ongeacht welke routes je in het
# Pine-script aanvinkt. Elke aangevinkte route stuurt zijn eigen alert() naar
# DEZELFDE webhook-URL; hier bepalen we per bericht welk soort het is.
# ---------------------------------------------------------------------------
def _classify(body: bytes):
    """-> (kind, payload). kind: pmt | discord | signal | pineconnector | unknown"""
    import json as _json
    text = body.decode("utf-8", "replace").strip()
    try:
        obj = _json.loads(text)
    except Exception:
        obj = None
    if isinstance(obj, dict):
        if "multiple_accounts" in obj or ("token" in obj and "data" in obj):
            return "pmt", obj
        if "embeds" in obj or "content" in obj:
            return "discord", obj
        if obj.get("type") == "journal" or "csv" in obj:
            return "journal", obj
        if {"secret", "strategy", "event"} <= set(obj):
            return "signal", obj
        return "unknown", obj
    parts = [p.strip() for p in text.split(",")]
    if len(parts) >= 3 and parts[1].lower() in ("buy", "sell", "exit"):
        return "pineconnector", text
    # CSV-journalregel: "<ts>,<accountID>,<jrnlAcct>,<ticker>,<EVENT>,..."
    if len(parts) >= 10 and parts[4].upper() in (
            "ENTRY", "EXIT", "FILL", "CONFIG", "HALT", "DERISK", "PAYOUT", "EVAL"):
        return "journal", text
    return "unknown", text


@app.post("/signal/{secret}")
async def signal_ingest(secret: str, request: Request, background: BackgroundTasks) -> dict:
    """Alle Pine-routes op één URL: https://<host>/signal/<MIDDLEWARE_SECRET>.

    Vink in het script aan wat je wilt (PMT / Discord / Journal / Middleware) —
    elk stuurt zijn eigen formaat naar deze ene URL en wij zetten het in de
    juiste trechter:
      PMT-JSON         -> 1:1 door naar PMT_URL (dedupe, kill-switch, risk-overlay)
      Discord-embed    -> trade-card renderen -> DISCORD_WEBHOOK_URL
      lean signal      -> fan-out naar alle accounts van die strategie
      PC-tekstcommando -> door naar PC_URL
      overig           -> alleen journaal (bv. CSV-journalregels)
    """
    import hashlib

    import httpx

    _check_secret(secret)
    raw = await request.body()
    kind, payload = _classify(raw)
    journal.write("ingest", {"kind": kind, "bytes": len(raw)})

    if deduper.seen_key(hashlib.sha1(raw).hexdigest()):
        return {"accepted": True, "kind": kind, "handled": False, "reason": "duplicate (idempotency)"}

    if kind == "pmt":
        action = str(payload.get("data", "")).lower()
        is_entry = action in ("buy", "sell")
        accs = payload.get("multiple_accounts") or []
        acct = str(accs[0].get("account_id", "")) if accs and isinstance(accs[0], dict) else ""
        if is_entry and not STATE["armed"]:
            return {"accepted": True, "kind": kind, "handled": False, "reason": "kill-switch: disarmed"}
        if is_entry and acct:
            allowed, why = risk.allow(acct, accounts.accounts.get(acct, {}), True)
            if not allowed:
                journal.write("risk_block", {"account": acct, "reason": why}, account=acct)
                return {"accepted": True, "kind": kind, "handled": False, "reason": f"risk: {why}"}
        res = await pmt_broker.forward(payload, pmt_url=_pmt_url_for(acct), dry_run=settings.dry_run,
                                       retry_max=settings.retry_max, retry_backoff=settings.retry_backoff)
        if is_entry and acct and res.get("status") == "sent":
            risk.record_entry(acct)
        journal.write("dispatch", {**res, "route": "pmt_pass", "account": acct}, account=acct)
        return {"accepted": True, "kind": kind, "handled": res.get("status") in ("sent", "dry_run"), "result": res}

    if kind == "discord":
        # Renderen duurt seconden (headless browser); TradingView mag daar niet op
        # wachten (timeout -> retry -> dubbele berichten). Dus: direct 200, kaart
        # rendert en post op de achtergrond.
        background.add_task(_render_and_post, payload)
        return {"accepted": True, "kind": kind, "handled": True, "queued": True}

    if kind == "signal":
        try:
            sig = Signal.model_validate(payload)
        except ValidationError as exc:
            journal.write("error", {"reason": "signal validation", "errors": exc.errors()})
            raise HTTPException(422, "invalid signal")
        if not STATE["armed"]:
            return {"accepted": True, "kind": kind, "handled": False, "reason": "kill-switch: disarmed"}
        results = await dispatch(sig, accounts, settings, risk)
        for r in results:
            journal.write("dispatch", r, strategy=sig.strategy, account=r.get("account", ""))
        return {"accepted": True, "kind": kind, "handled": True, "results": results}

    if kind == "pineconnector":
        if settings.dry_run or not settings.pc_url:
            journal.write("dispatch", {"route": "pineconnector", "status": "dry_run", "cmd": payload})
            return {"accepted": True, "kind": kind, "handled": False, "dry_run": True}
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(settings.pc_url, content=payload, headers={"Content-Type": "text/plain"})
        journal.write("dispatch", {"route": "pineconnector", "http_status": r.status_code})
        return {"accepted": True, "kind": kind, "handled": r.status_code < 400}

    if kind == "journal":
        csv_row = payload.get("csv") if isinstance(payload, dict) else payload
        journal.write("journal_row", {"csv": str(csv_row)[:2000]})
        return {"accepted": True, "kind": kind, "handled": True, "note": "journal row stored"}

    journal.write("unknown", {"raw": (payload if isinstance(payload, str) else str(payload))[:1000]})
    return {"accepted": True, "kind": "unknown", "handled": True, "note": "journalled only"}


@app.get("/journal")
def get_journal(secret: str, limit: int = 50) -> dict:
    _check_secret(secret)
    return {"events": journal.recent(limit)}


@app.post("/killswitch")
def killswitch(secret: str, armed: bool) -> dict:
    _check_secret(secret)
    STATE["armed"] = armed
    log.warning("kill-switch set armed=%s", armed)
    return {"armed": STATE["armed"]}


@app.get("/risk")
def risk_state(secret: str) -> dict:
    _check_secret(secret)
    return risk.snapshot()


@app.post("/halt")
def halt(secret: str, account: str, halted: bool = True) -> dict:
    """Halt (or resume) new entries for one account — e.g. when it hits its daily-loss
    limit. Exits are never blocked. Halts auto-clear at the next trading-day rollover."""
    _check_secret(secret)
    (risk.halt if halted else risk.resume)(account)
    log.warning("risk halt account=%s halted=%s", account, halted)
    return risk.snapshot()
