"""MEX trade middleware — the switchboard between TradingView and your broker accounts.

Endpoints
  GET  /health        liveness probe
  POST /webhook       receive a Signal from TradingView, fan out to accounts
  POST /pmt           passthrough: ready-made PMT payload in, forwarded 1:1 to PMT
  GET  /journal       last N journalled events (debug; secret-gated)
  POST /killswitch    enable/disable dispatching fleet-wide (secret-gated)

Phase 0 = receive + journal. Phase 1 = PMT (Tradovate) dispatch in DRY_RUN.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError

from .config import Settings, load_accounts
from .dedupe import Deduper
from .journal import Journal
from .models import Signal
from .notify import alert_failure
from .risk import RiskState
from .router import dispatch
from .brokers import pmt as pmt_broker

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

    result = await pmt_broker.forward(payload, pmt_url=settings.pmt_url, dry_run=settings.dry_run,
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
