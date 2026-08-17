"""MEX trade middleware — the switchboard between TradingView and your broker accounts.

Endpoints
  GET  /health        liveness probe
  POST /webhook       receive a Signal from TradingView, fan out to accounts
  POST /notice        receive a NON-order strategy event (config, auto flat, ...) -> card
  GET  /journal       last N journalled events (debug; secret-gated)
  POST /killswitch    enable/disable dispatching fleet-wide (secret-gated)

Phase 0 = receive + journal. Phase 1 = PMT (Tradovate) dispatch in DRY_RUN.
"""
from __future__ import annotations

import json
import logging

from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError

from .config import Settings, load_accounts_source
from .dedupe import Deduper
from .journal import Journal
from .models import Signal
import asyncio

from .metaapi import MetaApiClient
from .notices import build_notice_embed, format_notice, notice_from_payload
from .notify import AlertLimiter, alert_failures, notify_card_routes, notify_trade_routes
from .notion_sync import NotionJournal, NotionRecon, NotionSync
from .reconciler import Reconciler
from .risk import RiskState, trading_day_start_ts
from .router import dispatch
from .tradovate import TradovateClient, poll_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mex.middleware")

app = FastAPI(title="MEX trade middleware", version="0.1.0")

settings = Settings()
accounts = load_accounts_source(settings)
journal = Journal(settings.journal_db)
deduper = Deduper(settings.idem_ttl)
risk = RiskState(settings.max_entries_default)
trade_journal = NotionJournal(settings.notion_token, settings.notion_journal_db)
alert_limiter = AlertLimiter(settings.alert_max_per_window, settings.alert_window_seconds)
RECON: dict = {"engine": None}   # populated at startup

# Runtime kill-switch (in addition to DRY_RUN). True = orders may dispatch.
STATE = {"armed": True}


def _notify_defaults() -> dict:
    """Env-level fallbacks for the notify channel groups (accounts.yaml `notify:` wins)."""
    return {"default": settings.notify_webhook,
            "funded": settings.notify_funded_webhook,
            "eval": settings.notify_eval_webhook}


@app.on_event("startup")
async def _start_poller() -> None:
    tv_client = None
    if settings.tradovate_enabled():
        tv_client = TradovateClient(settings.tradovate_base, settings.tradovate_creds(), mock=settings.tradovate_mock)
        notion = NotionSync(settings.notion_token, settings.notion_db_id)
        asyncio.create_task(poll_loop(tv_client, journal, settings.perf_poll_seconds,
                                      on_snapshot=notion.upsert_fleet))
    else:
        log.info("Tradovate tracking off (set TRADOVATE_NAME/... or TRADOVATE_MOCK=true)")

    # Phase 6 — reconciliation engine (Tradovate + MetaAPI fills vs intended signals)
    meta = MetaApiClient(settings.metaapi_base, settings.metaapi_token, settings.metaapi_account,
                         mock=settings.metaapi_mock)
    RECON["engine"] = Reconciler(journal, tv_client, meta,
                                 NotionRecon(settings.notion_token, settings.notion_recon_db))


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
async def webhook(request: Request, secret: str = "", strategy: str = "") -> dict:
    """The single door TradingView posts to. A body that validates as a `Signal` is an
    order and gets fanned out; anything else on the same alert is a NON-order event
    (Pine's f_sendDiscord bodies: limit expired, auto flat, signal blocked, config...)
    and is rendered as a notice card instead of being rejected. Notices carry no secret
    in their body, so they authenticate on `?secret=` in the alert URL."""
    raw = await request.body()
    try:
        sig = Signal.model_validate_json(raw)
    except ValidationError as exc:
        payload = _as_notice_payload(raw)
        if payload is not None:
            # A structured notice carries the secret in its body (same as an order); the raw
            # Pine Discord body has no room for one, so that falls back to ?secret= on the URL.
            _check_secret(payload.get("secret") or secret)
            return await _render_notice(payload, strategy)
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

    # Notify + journal channels (best-effort; never block the trade path)
    is_exit = sig.event == "EXIT" or sig.action == "close"
    pnl = journal.day_pnl(trading_day_start_ts()) if (is_exit and settings.notify_pnl_on_exit) else None
    routes = accounts.notify_routes(sig.strategy, results, _notify_defaults())
    await notify_trade_routes(routes, sig, pnl=pnl, chat_id=settings.telegram_chat_id)
    await trade_journal.append_trade(sig, results)
    if failures:
        alerted = await alert_failures(settings.alert_webhook, sig, results,
                                       limiter=alert_limiter, chat_id=settings.telegram_chat_id)
        journal.write("alert", alerted, strategy=sig.strategy)
    return {"accepted": True, "dispatched": True, "dry_run": settings.dry_run,
            "failures": len(failures), "results": results}


def _as_notice_payload(raw: bytes) -> dict | None:
    """Is this non-Signal body something we can render as a notice? Returns the decoded
    payload, or None when there is nothing recognisable to show (then it is a real error).

    Accepts the Pine f_sendDiscord body ({"embeds":[{"title","description"}]}), a
    structured {"kind": ...} body, and a plain-text alert line.
    """
    text = raw.decode("utf-8", "replace").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except ValueError:
        return {"text": text[:2000]}          # plain-text alert body
    if not isinstance(payload, dict):
        return None
    if payload.get("kind"):
        return payload   # structured notice from Pine — carries its own secret, like an order
    if {"secret", "action", "dollar_sl", "qty"} & set(payload):
        return None   # a BROKEN order, not a notice — must surface as an error, not a card
    if payload.get("embeds") or payload.get("title") or payload.get("text") or payload.get("content"):
        return payload
    return None


async def _render_notice(payload: dict, strategy: str = "") -> dict:
    """Journal a notice and post its card. Never dispatches an order."""
    note = notice_from_payload(payload, strategy)
    # Keep the original title: when a kind comes out as the generic "notice" it is the
    # only thing that tells you why the classifier did not recognise the event.
    journal.write("notice", {"kind": note.kind, "symbol": note.symbol,
                             "title": note.title[:200], "text": note.text[:500]},
                  strategy=note.strategy)
    log.info("notice %s %s %s", note.strategy, note.symbol, note.kind)
    if note.kind in settings.notice_suppress():
        return {"accepted": True, "kind": note.kind, "posted": 0, "reason": "kind suppressed"}

    webhooks = accounts.notify_webhooks_for_strategy(note.strategy, _notify_defaults())
    posted = await notify_card_routes(webhooks, format_notice(note), build_notice_embed(note),
                                      chat_id=settings.telegram_chat_id)
    return {"accepted": True, "kind": note.kind, "strategy": note.strategy, "posted": posted}


@app.post("/notice")
async def notice(request: Request, secret: str = "", strategy: str = "") -> dict:
    """Explicit door for non-order events, for when they come in on their own alert
    rather than sharing the order alert. Same rendering as the `/webhook` fallback."""
    payload = _as_notice_payload(await request.body())
    if payload is None:
        raise HTTPException(422, "nothing to render")
    _check_secret(payload.get("secret") or secret)
    return await _render_notice(payload, strategy)


@app.get("/journal")
def get_journal(secret: str, limit: int = 50, kind: str = "", strategy: str = "",
                contains: str = "") -> dict:
    """Recent events, newest first. Filter with `kind` (signal|dispatch|notice|alert|
    dedupe|error, comma-separated), `strategy`, and `contains` (substring of the detail).
    E.g. `?kind=notice,error&contains=BLOCKED` answers whether an alert arrived at all
    and what the renderer made of it."""
    _check_secret(secret)
    return {"events": journal.recent(limit, kind=kind, strategy=strategy, contains=contains)}


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


@app.post("/reconcile")
async def reconcile(secret: str, lookback_s: float = 900.0) -> dict:
    """Run one reconciliation pass: match recent intended trades to actual venue fills,
    compute slippage/latency/qty discrepancies, store + push to LifeOS."""
    _check_secret(secret)
    engine = RECON["engine"]
    if engine is None:
        return {"error": "reconciler not initialised"}
    return await engine.run(lookback_s)


@app.get("/performance")
def performance(secret: str) -> dict:
    """Latest live P&L snapshot per account + fleet totals (from the Tradovate poller)."""
    _check_secret(secret)
    rows = journal.latest_perf()
    fleet = {
        "realized": round(sum(r["realized"] or 0 for r in rows), 2),
        "open_pnl": round(sum(r["open_pnl"] or 0 for r in rows), 2),
        "total_val": round(sum(r["total_val"] or 0 for r in rows), 2),
        "accounts": len(rows),
    }
    return {"fleet": fleet, "accounts": rows}


@app.post("/halt")
def halt(secret: str, account: str, halted: bool = True) -> dict:
    """Halt (or resume) new entries for one account — e.g. when it hits its daily-loss
    limit. Exits are never blocked. Halts auto-clear at the next trading-day rollover."""
    _check_secret(secret)
    (risk.halt if halted else risk.resume)(account)
    log.warning("risk halt account=%s halted=%s", account, halted)
    return risk.snapshot()
