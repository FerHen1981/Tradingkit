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
    alert_webhook: str = os.environ.get("ALERT_WEBHOOK", "")              # Discord/Telegram webhook for failures
    # Phase 5 — risk overlay
    max_entries_default: int = int(os.environ.get("MAX_ENTRIES_PER_DAY", "0"))  # 0 = unlimited (per-account yaml overrides)


@dataclass
class AccountMap:
    strategies: dict = field(default_factory=dict)  # {strategy: {"accounts": [ids]}}
    accounts: dict = field(default_factory=dict)     # {id: {broker, token, account_id, ...}}

    def accounts_for(self, strategy: str) -> list[dict]:
        ids = (self.strategies.get(strategy) or {}).get("accounts", [])
        out = []
        for aid in ids:
            acct = self.accounts.get(aid)
            if acct:
                out.append({"id": aid, **acct})
        return out


def load_accounts(path: str) -> AccountMap:
    p = Path(path)
    if not p.exists():
        return AccountMap()
    raw = _expand(yaml.safe_load(p.read_text()) or {})
    return AccountMap(strategies=raw.get("strategies", {}), accounts=raw.get("accounts", {}))
