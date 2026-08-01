"""MEX trade middleware — the switchboard between TradingView and your broker accounts.

Endpoints
  GET  /health        liveness probe
  POST /webhook       receive a Signal from TradingView, fan out to accounts
  GET  /journal       last N journalled events (debug; secret-gated)
  POST /killswitch    enable/disable dispatching fleet-wide (secret-gated)

Phase 0 = receive + journal. Phase 1 = PMT (Tradovate) dispatch in DRY_RUN.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError

from .config import Settings, load_accounts
from .journal import Journal
from .models import Signal
from .router import dispatch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mex.middleware")

app = FastAPI(title="MEX trade middleware", version="0.1.0")

settings = Settings()
accounts = load_accounts(settings.accounts_file)
journal = Journal(settings.journal_db)

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

    results = await dispatch(sig, accounts, settings)
    for r in results:
        journal.write("dispatch", r, strategy=sig.strategy, account=r.get("account", ""))
    return {"accepted": True, "dispatched": True, "dry_run": settings.dry_run, "results": results}


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
