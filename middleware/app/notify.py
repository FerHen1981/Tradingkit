"""Notify channel — the human-facing side of the fan-out.

Two streams, both best-effort (they may never break the request path):
  - `notify_trade(...)`  live per-trade message, one per notify channel the trade
    touched (Funded and Eval accounts can land in different Discord channels).
  - `alert_failures(...)` failure ping with a severity, rate-limited so a burst of
    broken dispatches does not spam the alert channel into uselessness.

Transport is picked from the webhook URL: an `api.telegram.org` URL gets a Telegram
`sendMessage` body (text + chat_id), anything else gets a Discord webhook body
(rich embed + a plain-text `content` fallback so the message is still readable in
clients/relays that ignore embeds).
"""
from __future__ import annotations

import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

# ------------------------------------------------------------------ palette
COLOR_LONG = 0x2ECC71      # entry buy
COLOR_SHORT = 0xE74C3C     # entry sell
COLOR_FLAT = 0x95A5A6      # exit / close, result unknown
COLOR_WIN = 0x2ECC71       # exit, day P&L green
COLOR_LOSS = 0xE74C3C      # exit, day P&L red
COLOR_INFO = 0x3498DB
COLOR_WARNING = 0xE67E22
COLOR_CRITICAL = 0xC0392B

SEVERITY = {  # name -> (emoji, colour, rank)
    "info": ("ℹ️", COLOR_INFO, 0),
    "warning": ("⚠️", COLOR_WARNING, 1),
    "critical": ("🚨", COLOR_CRITICAL, 2),
}

OK_STATUS = ("sent", "dry_run")
_MAX_LISTED = 10          # accounts listed per embed field before "+N more"
_FIELD_LIMIT = 1000       # Discord's hard limit is 1024


# ------------------------------------------------------------------ transport
def _is_telegram(webhook: str) -> bool:
    return "api.telegram.org" in urlsplit(webhook).netloc


def _to_telegram_markdown(text: str) -> str:
    """Discord bold (**x**) -> Telegram legacy-Markdown bold (*x*)."""
    return text.replace("**", "*")


def _telegram_request(webhook: str, text: str, chat_id: str) -> tuple[str, dict]:
    """Split a `?chat_id=` out of the configured URL into the JSON body (either the URL
    or TELEGRAM_CHAT_ID may carry it; the URL wins)."""
    parts = urlsplit(webhook)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "chat_id"]
    url_chat = dict(parse_qsl(parts.query)).get("chat_id", "")
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    body = {"text": _to_telegram_markdown(text), "parse_mode": "Markdown",
            "disable_web_page_preview": True}
    chat = url_chat or chat_id
    if chat:
        body["chat_id"] = chat
    return url, body


async def _post(webhook: str, text: str, embed: dict | None = None, *,
                chat_id: str = "", client: httpx.AsyncClient | None = None) -> None:
    if not webhook:
        return
    if _is_telegram(webhook):
        url, payload = _telegram_request(webhook, text, chat_id)
    else:
        url = webhook
        # Discord reads `content` + `embeds`; a bare relay/Telegram-style sink reads `text`.
        # Sending all three is harmless — each service uses the keys it knows.
        payload = {"content": text, "text": text}
        if embed:
            payload["embeds"] = [embed]
    own = client is None
    client = client or httpx.AsyncClient(timeout=8.0)
    try:
        await client.post(url, json=payload)
    except Exception:
        pass  # notifications must never break the request path
    finally:
        if own:
            await client.aclose()


async def alert_failure(webhook: str, text: str, client: httpx.AsyncClient | None = None) -> None:
    """Plain failure ping (kept for callers that already have their own text)."""
    await _post(webhook, text, client=client)


# ------------------------------------------------------------------ trade message
def _split(results: list[dict]) -> tuple[list, list, list]:
    ok = [r for r in results if r.get("status") in OK_STATUS]
    blocked = [r for r in results if r.get("status") == "blocked"]
    failed = [r for r in results if r.get("status") == "error"]
    return ok, blocked, failed


def _why(r: dict) -> str:
    """Why this account did not get its order (reason, else the HTTP status)."""
    if r.get("reason"):
        return str(r["reason"])
    if r.get("http_status"):
        return f"HTTP {r['http_status']}"
    return "unknown"


def _names(rows: list[dict], with_reason: bool = False) -> str:
    parts = []
    for r in rows[:_MAX_LISTED]:
        name = r.get("account", "?")
        parts.append(f"`{name}` — {_why(r)}" if with_reason else f"`{name}`")
    if len(rows) > _MAX_LISTED:
        parts.append(f"+{len(rows) - _MAX_LISTED} more")
    return ("\n" if with_reason else " · ").join(parts)[:_FIELD_LIMIT] or "—"


def format_trade(sig, results: list[dict]) -> str:
    """Human-readable one-liner — the plain-text form of the live notify message."""
    ok, blocked, failed = _split(results)
    arrow = "🟢" if sig.action == "buy" else ("🔴" if sig.action == "sell" else "⚪")
    head = (f"{arrow} **{sig.strategy} {sig.action.upper()}** {sig.symbol} @ {sig.price} · "
            f"{sig.qty}ct · SL {sig.dollar_sl}/TP {sig.dollar_tp}")
    tail = f"→ {len(ok)} account(s)"
    if blocked:
        tail += f", {len(blocked)} blocked"
    if failed:
        tail += f", ⚠️ {len(failed)} failed"
    return f"{head}  {tail}"


def _trade_color(sig, results: list[dict], pnl: dict | None) -> int:
    ok, _, failed = _split(results)
    if failed and not ok:
        return COLOR_CRITICAL           # nothing got through — treat as an alarm
    if sig.event == "EXIT" or sig.action == "close":
        if pnl and pnl.get("realized") is not None:
            return COLOR_WIN if pnl["realized"] >= 0 else COLOR_LOSS
        return COLOR_FLAT
    return COLOR_LONG if sig.action == "buy" else COLOR_SHORT


def _money(v: float) -> str:
    return f"{'+' if v >= 0 else '−'}${abs(v):,.2f}"


def build_embed(sig, results: list[dict], *, channel: str = "", pnl: dict | None = None) -> dict:
    """Discord embed for one trade on one notify channel."""
    ok, blocked, failed = _split(results)
    icon = "🟢" if sig.action == "buy" else ("🔴" if sig.action == "sell" else "⚪")
    verb = "CLOSE" if sig.action == "close" else sig.action.upper()

    fields = [
        {"name": "Price", "value": f"{sig.price}", "inline": True},
        {"name": "Qty", "value": f"{sig.qty} ct", "inline": True},
        {"name": "SL / TP", "value": f"{sig.dollar_sl} / {sig.dollar_tp}", "inline": True},
        {"name": f"Routed ({len(ok)})", "value": _names(ok), "inline": False},
    ]
    if blocked:
        fields.append({"name": f"⛔ Blocked ({len(blocked)})", "value": _names(blocked, True), "inline": False})
    if failed:
        fields.append({"name": f"⚠️ Failed ({len(failed)})", "value": _names(failed, True), "inline": False})
    if pnl and pnl.get("realized") is not None:
        day = f"{_money(pnl['realized'])} realized"
        if pnl.get("open_pnl"):
            day += f" · {_money(pnl['open_pnl'])} open"
        if pnl.get("accounts"):
            day += f" · {pnl['accounts']} acct(s)"
        fields.append({"name": "Day P&L (fleet)", "value": day, "inline": False})

    footer = channel or "notify"
    if ok and all(r.get("status") == "dry_run" for r in ok):
        footer += " · DRY RUN (no live orders)"
    embed = {
        "title": f"{icon} {sig.strategy} {verb} · {sig.symbol}",
        "color": _trade_color(sig, results, pnl),
        "fields": fields,
        "footer": {"text": f"MEX middleware · {footer}"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    chart = getattr(sig, "chart_url", "") or ""
    if chart.startswith("http"):
        embed["image"] = {"url": chart}
    return embed


async def notify_trade(webhook: str, sig, results: list[dict], *, channel: str = "",
                       pnl: dict | None = None, chat_id: str = "",
                       client: httpx.AsyncClient | None = None) -> None:
    """Live per-trade notification for ONE channel (distinct from failure alerts)."""
    if not webhook or not results:
        return
    await _post(webhook, format_trade(sig, results),
                build_embed(sig, results, channel=channel, pnl=pnl),
                chat_id=chat_id, client=client)


async def notify_trade_routes(routes: list[tuple[str, str, list[dict]]], sig, *,
                              pnl: dict | None = None, chat_id: str = "",
                              client: httpx.AsyncClient | None = None) -> None:
    """Send one message per (webhook, channel-label, results-subset) route, so Funded and
    Eval streams stay separate. `routes` comes from `AccountMap.notify_routes(...)`."""
    if not routes:
        return
    own = client is None
    client = client or httpx.AsyncClient(timeout=8.0)
    try:
        for webhook, label, subset in routes:
            await notify_trade(webhook, sig, subset, channel=label, pnl=pnl,
                               chat_id=chat_id, client=client)
    finally:
        if own:
            await client.aclose()


async def notify_card_routes(webhooks: list[str], text: str, embed: dict | None = None, *,
                             chat_id: str = "", client: httpx.AsyncClient | None = None) -> int:
    """Post one already-built card to each webhook (used by the notice renderer, which
    has no per-account split). Returns how many went out."""
    targets = [w for w in dict.fromkeys(webhooks) if w]
    if not targets:
        return 0
    own = client is None
    client = client or httpx.AsyncClient(timeout=8.0)
    try:
        for webhook in targets:
            await _post(webhook, text, embed, chat_id=chat_id, client=client)
    finally:
        if own:
            await client.aclose()
    return len(targets)


# ------------------------------------------------------------------ failure alerts
def classify_failure(r: dict) -> str:
    """How loud should this one failure be?

    critical — the order will NOT go through until you change something (auth/config
               rejected, 4xx, missing URL, unknown broker).
    warning  — transient: network error or 5xx after the retries were exhausted.
    """
    http = r.get("http_status")
    if isinstance(http, int) and 400 <= http < 500:
        return "critical"
    if isinstance(http, int) and http >= 500:
        return "warning"
    reason = (r.get("reason") or "").lower()
    if "not configured" in reason or "unknown broker" in reason:
        return "critical"
    return "warning"  # network/timeout exceptions


def severity_of(sig, results: list[dict]) -> str:
    """Fleet-level severity: any critical single failure is critical, and so is a trade
    where nothing at all got through — that is a missed trade, not a degraded one."""
    ok, _, failed = _split(results)
    if not failed:
        return "info"
    if not ok:
        return "critical"
    return max((classify_failure(r) for r in failed), key=lambda s: SEVERITY[s][2])


class AlertLimiter:
    """Collapse alert bursts. Up to `max_per_window` alerts per key per window go out;
    the rest are counted and reported on the next alert that IS admitted, so nothing is
    silently dropped ("+7 suppressed in the last 60s")."""

    def __init__(self, max_per_window: int = 5, window_s: float = 60.0):
        self.max_per_window = max(1, max_per_window)
        self.window_s = window_s
        self._stamps: dict[str, list[float]] = {}
        self._suppressed: dict[str, int] = {}

    def admit(self, key: str, now: float | None = None) -> tuple[bool, int]:
        now = time.time() if now is None else now
        stamps = [t for t in self._stamps.get(key, []) if now - t < self.window_s]
        if len(stamps) >= self.max_per_window:
            self._suppressed[key] = self._suppressed.get(key, 0) + 1
            self._stamps[key] = stamps
            return False, 0
        stamps.append(now)
        self._stamps[key] = stamps
        return True, self._suppressed.pop(key, 0)


def build_failure(sig, results: list[dict], *, suppressed: int = 0,
                  window_s: float = 60.0) -> tuple[str, str, dict]:
    """(severity, plain text, embed) for the failure channel."""
    ok, _, failed = _split(results)
    sev = severity_of(sig, results)
    emoji, color, _ = SEVERITY[sev]
    scope = "ALL accounts" if not ok else f"{len(failed)}/{len(failed) + len(ok)} accounts"
    head = (f"{emoji} **{sev.upper()}** — {sig.strategy} {sig.action.upper()} {sig.symbol}: "
            f"dispatch failed on {scope}")
    detail = "; ".join(f"{r.get('account', '?')}: {_why(r)}" for r in failed)
    text = f"{head} — {detail}"
    if suppressed:
        text += f"  (+{suppressed} similar suppressed in the last {int(window_s)}s)"
    fields = [{"name": f"Failed ({len(failed)})", "value": _names(failed, True), "inline": False}]
    if ok:
        fields.append({"name": f"Still routed ({len(ok)})", "value": _names(ok), "inline": False})
    if suppressed:
        fields.append({"name": "Suppressed", "value": f"+{suppressed} similar in the last {int(window_s)}s",
                       "inline": False})
    embed = {
        "title": f"{emoji} {sev.upper()} · {sig.strategy} {sig.action.upper()} {sig.symbol}",
        "description": f"Dispatch failed on {scope}.",
        "color": color,
        "fields": fields,
        "footer": {"text": "MEX middleware · alerts"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return sev, text, embed


async def alert_failures(webhook: str, sig, results: list[dict], *, limiter: AlertLimiter | None = None,
                         chat_id: str = "", client: httpx.AsyncClient | None = None) -> dict:
    """Severity-tagged failure alert, rate-limited per (strategy, severity).

    Returns what it did, so the caller can journal it: {"sent": bool, "severity": ...}.
    """
    _, _, failed = _split(results)
    if not webhook or not failed:
        return {"sent": False, "severity": "info", "failures": 0}
    sev = severity_of(sig, results)
    suppressed = 0
    if limiter is not None:
        allowed, suppressed = limiter.admit(f"{sig.strategy}:{sev}")
        if not allowed:
            return {"sent": False, "severity": sev, "failures": len(failed), "rate_limited": True}
    _, text, embed = build_failure(sig, results, suppressed=suppressed,
                                   window_s=limiter.window_s if limiter else 60.0)
    await _post(webhook, text, embed, chat_id=chat_id, client=client)
    return {"sent": True, "severity": sev, "failures": len(failed), "suppressed": suppressed}
