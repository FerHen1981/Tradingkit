"""Notice events — everything a strategy reports that is NOT an order.

The Pine scripts emit two kinds of alert:
  - the lean order Signal (`useMiddleware`) -> fan-out + the trade card, and
  - `f_sendDiscord(title, desc)` messages for LIMIT EXPIRED, AUTO FLAT, SIGNAL BLOCKED,
    CONFIG, DAY HALT, PAYOUT ... which historically went STRAIGHT to a Discord webhook
    as a flat blue embed and therefore never reached this renderer.

Point those alerts at `POST /notice` instead and they land here. Two input shapes are
accepted, so nothing in Pine has to change first:
  1. the Pine Discord body — {"embeds":[{"title": "⏳ ES1! LIMIT EXPIRED", "description": ...}]}
     which `notice_from_payload` parses back into a typed Notice, and
  2. a structured {"kind": "limit_expired", "symbol": "ES1!", "data": {...}} body for
     senders that can emit it directly (richer: no text parsing at all).

Each kind gets its own card: emoji, colour and parsed fields.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from .notify import (COLOR_CRITICAL, COLOR_FLAT, COLOR_INFO, COLOR_LONG, COLOR_LOSS,
                     COLOR_SHORT, COLOR_WARNING, COLOR_WIN)

_FIELD_LIMIT = 1000       # Discord's hard limit is 1024
_MAX_FIELDS = 24          # Discord allows 25


class Notice(BaseModel):
    """A non-order event from a strategy."""
    kind: str = "notice"
    strategy: str = ""
    symbol: str = ""
    title: str = ""          # original title (kept for the plain-text fallback)
    text: str = ""           # original description
    data: dict = {}          # parsed/structured extras, rendered as embed fields


# Pine title phrase -> kind. Ordered: the first match wins, so "LIMIT EXPIRED" must be
# tested before the "LIMIT" of an entry-intent title.
_TITLE_KINDS: list[tuple[str, str]] = [
    ("SIGNAL BLOCKED", "signal_blocked"),
    ("LIMIT EXPIRED", "limit_expired"),
    ("AUTO FLAT", "auto_flat"),
    ("CONFIG", "config"),
    ("DAY HALT", "day_halt"),
    ("CAP LOCK", "cap_lock"),
    ("PA DERISK", "derisk"),
    ("DERISK", "derisk"),
    ("PAYOUT", "payout_ready"),
    ("ACCOUNT STARTED", "account_started"),
    ("RISK OFF", "risk_off"),
    ("TRAIL ACTIVE", "trail_active"),
    ("REGIME", "regime_shift"),
    ("FILL", "fill"),
    ("EXIT", "exit"),
    ("LIMIT", "entry_intent"),
    ("MARKET", "entry_intent"),
]

# kind -> (emoji, human label, colour)
KIND_CARDS: dict[str, tuple[str, str, int]] = {
    "signal_blocked": ("⛔", "Signal blocked", COLOR_WARNING),
    "limit_expired": ("⏳", "Limit expired", COLOR_FLAT),
    "auto_flat": ("🕔", "Auto flat", COLOR_FLAT),
    "config": ("⚙️", "Config", COLOR_INFO),
    "day_halt": ("🔒", "Day halt", COLOR_CRITICAL),
    "cap_lock": ("🔐", "Cap lock", COLOR_WIN),
    "payout_ready": ("💰", "Payout ready", COLOR_WIN),
    "derisk": ("🪜", "Derisk", COLOR_WARNING),
    "account_started": ("🚀", "Account started", COLOR_INFO),
    "risk_off": ("🛡️", "Risk off", COLOR_INFO),
    "trail_active": ("🎯", "Trail active", COLOR_INFO),
    "regime_shift": ("🌦️", "Regime shift", COLOR_INFO),
    "fill": ("📥", "Fill", COLOR_INFO),
    "exit": ("📤", "Exit", COLOR_FLAT),
    "entry_intent": ("📈", "Entry", COLOR_INFO),
    "notice": ("📣", "Notice", COLOR_INFO),
}

# CONFIG keys worth surfacing as their own field, in this order. Everything else is
# dumped into a compact "rest" block so nothing is lost.
_CFG_HEADLINE = [
    ("ver", "Version"), ("acct", "Account"), ("phase", "Phase"), ("qty", "Size"),
    ("entry", "Entry"), ("stop", "Stop"), ("tp", "TP"), ("R", "R multiple"),
    ("DLL", "Daily loss limit"), ("guard", "DD guard"), ("tz", "Timezone"),
]


def _clip(text: str) -> str:
    return text[:_FIELD_LIMIT] if text else "—"


# Futures month codes, so a dated contract (ESZ2025) reduces to the same root as the
# continuous one (ES1!).
_DATED_RE = re.compile(r"^([A-Z]{1,4})[FGHJKMNQUVXZ]\d{1,4}$")
# A ticker-ish token: letters followed by a digit or '!' (ES1!, MNQ1!, ESZ2025).
_TICKER_RE = re.compile(r"^[A-Za-z]{1,6}[0-9!]\S*$")
_NOT_A_TICKER = {"LONG", "SHORT", "PENDING", "FORCED"}


def strategy_from_symbol(symbol: str) -> str:
    """'ES1!' / 'ESZ2025' -> 'ES' — the strategy key used in accounts.yaml."""
    sym = (symbol or "").strip().upper()
    dated = _DATED_RE.match(sym)
    if dated:
        return dated.group(1)
    return re.split(r"[0-9!]", sym, maxsplit=1)[0].strip()


def parse_title(title: str) -> tuple[str, str]:
    """Pine title '⏳ ES1! LIMIT EXPIRED' -> (kind, symbol)."""
    upper = (title or "").upper()
    for phrase, kind in _TITLE_KINDS:
        idx = upper.find(phrase)
        if idx < 0:
            continue
        # The symbol sits between the emoji and the event phrase — but an entry title
        # reads "📈 ES1! LONG LIMIT", so prefer a ticker-shaped token over the last one.
        tokens = [t for t in (title or "")[:idx].split() if any(ch.isalnum() for ch in t)]
        tickers = [t for t in tokens if _TICKER_RE.match(t)]
        if tickers:
            return kind, tickers[-1]
        plain = [t for t in tokens if t.upper() not in _NOT_A_TICKER]
        return kind, (plain[-1] if plain else "")
    return "notice", ""


def _direction(text: str) -> str:
    low = (text or "").lower()
    if "long" in low:
        return "Long"
    if "short" in low:
        return "Short"
    return ""


def _price_after(text: str, marker: str = "@") -> str:
    """Pull the price out of '... cancelled @ 5312.25' / 'Forced flat @ ~5312.25'."""
    _, _, tail = (text or "").partition(marker)
    match = re.search(r"-?\d[\d,]*\.?\d*", tail)
    return match.group(0) if match else ""


def parse_config(text: str) -> dict:
    """cfgStr 'ver=6.9.1;acct=Apex-1;qty=2;...' -> an ordered dict of settings."""
    out: dict[str, str] = {}
    for chunk in (text or "").split(";"):
        key, sep, value = chunk.partition("=")
        if sep and key.strip():
            out[key.strip()] = value.strip()
    return out


def _fields_for(kind: str, text: str, data: dict) -> list[dict]:
    """Per-kind embed fields. `data` (structured senders) always wins over parsed text."""
    def pick(key: str, parsed: str) -> str:
        return str(data.get(key, "") or parsed or "")

    if kind == "signal_blocked":
        reasons = data.get("reasons") or (text or "").split("blocked by:")[-1].strip()
        if isinstance(reasons, str):
            reasons = [r.strip() for r in reasons.split(",") if r.strip()]
        fields = []
        direction = pick("direction", _direction(text))
        if direction:
            fields.append({"name": "Direction", "value": direction, "inline": True})
        fields.append({"name": f"Blocked by ({len(reasons)})",
                       "value": _clip("\n".join(f"• {r}" for r in reasons)), "inline": False})
        return fields

    if kind == "limit_expired":
        fields = []
        direction = pick("direction", _direction(text))
        price = pick("price", _price_after(text))
        if direction:
            fields.append({"name": "Direction", "value": direction, "inline": True})
        if price:
            fields.append({"name": "Limit price", "value": price, "inline": True})
        fields.append({"name": "Outcome", "value": "Pending order cancelled — never filled",
                       "inline": False})
        return fields

    if kind == "auto_flat":
        fields = []
        price = pick("price", _price_after(text))
        if price:
            fields.append({"name": "Flat at", "value": f"~{price}", "inline": True})
        fields.append({"name": "Reason", "value": pick("reason", "Force-flat window — position closed"),
                       "inline": False})
        return fields

    if kind == "config":
        cfg = data.get("config") if isinstance(data.get("config"), dict) else parse_config(text)
        fields, seen = [], set()
        for key, label in _CFG_HEADLINE:
            if cfg.get(key):
                fields.append({"name": label, "value": _clip(str(cfg[key])), "inline": True})
                seen.add(key)
        rest = {k: v for k, v in cfg.items() if k not in seen}
        if rest:
            body = " · ".join(f"{k}={v}" for k, v in rest.items())
            fields.append({"name": f"Other settings ({len(rest)})",
                           "value": _clip(f"```{body}```"), "inline": False})
        return fields[:_MAX_FIELDS]

    return [{"name": "Detail", "value": _clip(text), "inline": False}] if text else []


def build_notice_embed(notice: Notice) -> dict:
    """Discord embed for one notice."""
    emoji, label, color = KIND_CARDS.get(notice.kind, KIND_CARDS["notice"])
    if notice.kind == "exit" and "🔴" in (notice.title or ""):
        color = COLOR_LOSS
    elif notice.kind == "exit" and "🟢" in (notice.title or ""):
        color = COLOR_WIN
    elif notice.kind in ("fill", "entry_intent"):
        direction = _direction(notice.title) or _direction(notice.text)
        color = COLOR_SHORT if direction == "Short" else COLOR_LONG
    symbol = notice.symbol or notice.strategy
    return {
        "title": f"{emoji} {symbol} · {label}".strip(),
        "color": color,
        "fields": _fields_for(notice.kind, notice.text, notice.data or {})[:_MAX_FIELDS],
        "footer": {"text": f"MEX middleware · {notice.strategy or 'notice'}"},
    }


def format_notice(notice: Notice) -> str:
    """Plain-text fallback (Telegram, and clients that ignore embeds)."""
    emoji, label, _ = KIND_CARDS.get(notice.kind, KIND_CARDS["notice"])
    symbol = notice.symbol or notice.strategy
    head = f"{emoji} **{symbol} {label.upper()}**".replace("  ", " ")
    return f"{head} — {notice.text}" if notice.text else head


def notice_from_payload(payload: dict, strategy: str = "") -> Notice:
    """Build a Notice from either input shape (structured body, or the Pine embed body)."""
    if not isinstance(payload, dict):
        payload = {}

    embeds = payload.get("embeds") or []
    embed = embeds[0] if isinstance(embeds, list) and embeds and isinstance(embeds[0], dict) else {}
    title = str(payload.get("title") or embed.get("title") or "")
    text = str(payload.get("text") or payload.get("description") or embed.get("description")
               or payload.get("content") or "")

    kind = str(payload.get("kind") or "")
    symbol = str(payload.get("symbol") or "")
    if not kind or not symbol:
        parsed_kind, parsed_symbol = parse_title(title)
        kind = kind or parsed_kind
        symbol = symbol or parsed_symbol or str((embed.get("footer") or {}).get("text") or "")
    return Notice(
        kind=kind,
        strategy=strategy or str(payload.get("strategy") or "") or strategy_from_symbol(symbol),
        symbol=symbol,
        title=title,
        text=text,
        data=payload.get("data") if isinstance(payload.get("data"), dict) else {},
    )
