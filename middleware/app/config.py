"""Settings (from env) + the account map (from accounts.yaml).

Nothing secret is committed: real tokens live in environment variables or an
un-tracked accounts.yaml. `accounts.example.yaml` shows the shape.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand(value):
    """Replace ${VAR} in strings with the environment value (empty if unset)."""
    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


@dataclass
class Settings:
    secret: str = os.environ.get("MIDDLEWARE_SECRET", "")
    dry_run: bool = os.environ.get("DRY_RUN", "true").lower() != "false"
    pmt_url: str = os.environ.get("PMT_URL", "")  # your PickMyTrade webhook URL
    pc_url: str = os.environ.get("PC_URL", "")    # your PineConnector webhook URL
    accounts_file: str = os.environ.get("ACCOUNTS_FILE", "accounts.yaml")
    journal_db: str = os.environ.get("JOURNAL_DB", "journal.db")
    # Phase 4 — reliability
    idem_ttl: float = float(os.environ.get("IDEM_TTL_SECONDS", "3"))       # dedupe identical signals within N s
    retry_max: int = int(os.environ.get("RETRY_MAX", "3"))                 # PMT POST attempts on network/5xx
    retry_backoff: float = float(os.environ.get("RETRY_BACKOFF_SECONDS", "0.5"))
    alert_webhook: str = os.environ.get("ALERT_WEBHOOK", "")              # Discord/Telegram webhook for FAILURES
    notify_webhook: str = os.environ.get("NOTIFY_WEBHOOK", "")            # Discord webhook for EVERY trade (live notify)
    # Notify channel — routing, rate-limiting, Telegram
    notify_funded_webhook: str = os.environ.get("NOTIFY_FUNDED_WEBHOOK", "")  # funded accounts stream
    notify_eval_webhook: str = os.environ.get("NOTIFY_EVAL_WEBHOOK", "")      # eval accounts stream
    telegram_chat_id: str = os.environ.get("TELEGRAM_CHAT_ID", "")        # only for api.telegram.org webhooks
    alert_max_per_window: int = int(os.environ.get("ALERT_MAX_PER_WINDOW", "5"))
    alert_window_seconds: float = float(os.environ.get("ALERT_WINDOW_SECONDS", "60"))
    notify_pnl_on_exit: bool = os.environ.get("NOTIFY_PNL_ON_EXIT", "true").lower() != "false"
    # Notice events (/notice): kinds to drop. Entry intents duplicate the trade card the
    # order route already posts, so they are suppressed unless you ask for them.
    notice_suppress_raw: str = os.environ.get("NOTICE_SUPPRESS", "entry_intent")
    # Phase 5 — risk overlay
    max_entries_default: int = int(os.environ.get("MAX_ENTRIES_PER_DAY", "0"))  # 0 = unlimited (per-account yaml overrides)
    # Live fleet tracking — Tradovate read API
    tradovate_base: str = os.environ.get("TRADOVATE_BASE", "https://live.tradovateapi.com/v1")
    tradovate_mock: bool = os.environ.get("TRADOVATE_MOCK", "false").lower() == "true"
    perf_poll_seconds: float = float(os.environ.get("PERF_POLL_SECONDS", "60"))
    # LifeOS / Notion fleet dashboard + trade journal
    notion_token: str = os.environ.get("NOTION_TOKEN", "")
    notion_db_id: str = os.environ.get("NOTION_DB_ID", "")               # fleet performance DB
    notion_journal_db: str = os.environ.get("NOTION_JOURNAL_DB", "")     # trade journal DB (one row per trade)
    notion_recon_db: str = os.environ.get("NOTION_RECON_DB", "")         # reconciliation DB (trade x venue)
    # Phase 6 — MetaAPI (MT5 fills)
    metaapi_base: str = os.environ.get("METAAPI_BASE", "https://mt-client-api-v1.new-york.agiliumtrade.ai")
    metaapi_token: str = os.environ.get("METAAPI_TOKEN", "")
    metaapi_account: str = os.environ.get("METAAPI_ACCOUNT_ID", "")
    metaapi_mock: bool = os.environ.get("METAAPI_MOCK", "false").lower() == "true"

    def tradovate_creds(self) -> dict:
        return {
            "name": os.environ.get("TRADOVATE_NAME", ""),
            "password": os.environ.get("TRADOVATE_PASSWORD", ""),
            "appId": os.environ.get("TRADOVATE_APPID", ""),
            "appVersion": os.environ.get("TRADOVATE_APPVERSION", "1.0"),
            "cid": os.environ.get("TRADOVATE_CID", ""),
            "sec": os.environ.get("TRADOVATE_SEC", ""),
            "deviceId": os.environ.get("TRADOVATE_DEVICE_ID", ""),
        }

    def tradovate_enabled(self) -> bool:
        return self.tradovate_mock or bool(os.environ.get("TRADOVATE_NAME"))

    def notice_suppress(self) -> set[str]:
        return {k.strip() for k in self.notice_suppress_raw.split(",") if k.strip()}


@dataclass
class AccountMap:
    strategies: dict = field(default_factory=dict)  # {strategy: {"accounts": [ids]}}
    accounts: dict = field(default_factory=dict)     # {id: {broker, token, account_id, ...}}
    notify_channels: dict = field(default_factory=dict)  # {"funded"|"eval"|firm|"default": webhook}

    def notify_for(self, strategy: str) -> str:
        """Optional per-strategy Discord webhook override (falls back to the global one)."""
        return (self.strategies.get(strategy) or {}).get("notify", "")

    def notify_channel(self, account_id: str, strategy: str, defaults: dict) -> tuple[str, str]:
        """Which notify channel does this account's leg of the trade belong in?

        Most specific wins: the account's own webhook, then the per-strategy override
        (pre-existing behaviour, so old configs keep routing exactly as before), then the
        group channel for its `kind` (funded/eval) or `firm`, then the global default.
        Returns (webhook, label) — the label is what the embed footer shows.
        """
        acct = self.accounts.get(account_id) or {}
        if acct.get("notify"):
            return acct["notify"], account_id
        if self.notify_for(strategy):
            return self.notify_for(strategy), strategy
        for key in (acct.get("kind"), acct.get("firm")):
            if not key:
                continue
            hook = self.notify_channels.get(key) or defaults.get(key, "")
            if hook:
                return hook, str(key)
        return self.notify_channels.get("default") or defaults.get("default", ""), "default"

    def notify_routes(self, strategy: str, results: list[dict],
                      defaults: dict) -> list[tuple[str, str, list[dict]]]:
        """Split one fan-out's results into (webhook, label, subset) routes, so a signal
        that hit Funded and Eval accounts posts one message per stream instead of one
        mixed message. Legs whose channel is unconfigured are dropped (nothing to post to).
        """
        grouped: dict[str, tuple[str, list[dict]]] = {}
        for r in results:
            hook, label = self.notify_channel(r.get("account", ""), strategy, defaults)
            if not hook:
                continue
            grouped.setdefault(hook, (label, []))[1].append(r)
        return [(hook, label, subset) for hook, (label, subset) in grouped.items()]

    def notify_webhooks_for_strategy(self, strategy: str, defaults: dict) -> list[str]:
        """Channels a strategy-level message (a notice: config, auto-flat, blocked signal)
        belongs in. A notice has no per-account results, so it goes to every distinct
        channel that strategy's accounts route to — a funded/eval split still gets both.
        With no accounts mapped it falls back to the strategy override or the default.
        """
        hooks = [self.notify_channel(aid, strategy, defaults)[0]
                 for aid in (self.strategies.get(strategy) or {}).get("accounts", [])]
        hooks = [h for h in dict.fromkeys(hooks) if h]
        if hooks:
            return hooks
        fallback = self.notify_for(strategy) or self.notify_channels.get("default") or defaults.get("default", "")
        return [fallback] if fallback else []

    def accounts_for(self, strategy: str) -> list[dict]:
        ids = (self.strategies.get(strategy) or {}).get("accounts", [])
        out = []
        for aid in ids:
            acct = self.accounts.get(aid)
            if acct:
                out.append({"id": aid, **acct})
        return out


def _parse_accounts(text: str) -> AccountMap:
    raw = _expand(yaml.safe_load(text) or {})
    return AccountMap(strategies=raw.get("strategies", {}), accounts=raw.get("accounts", {}),
                      notify_channels=raw.get("notify", {}) or {})


def load_accounts(path: str) -> AccountMap:
    p = Path(path)
    if not p.exists():
        return AccountMap()
    return _parse_accounts(p.read_text())


def load_accounts_source(settings: "Settings") -> AccountMap:
    """Prefer the ACCOUNTS_YAML env var (paste the whole map into one field — ideal for
    managed hosts like Render where there is no file to upload). Fall back to the file."""
    inline = os.environ.get("ACCOUNTS_YAML", "")
    if inline.strip():
        return _parse_accounts(inline)
    return load_accounts(settings.accounts_file)
