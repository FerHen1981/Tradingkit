"""Portal settings, all from the environment.

Nothing here has a working default that would let the portal come up insecure:
`PORTAL_SECRET` has no default at all, and `validate()` is called at startup so
a misconfiguration fails immediately rather than at the first login.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # ---- identity ----
    base_url: str = os.environ.get("PORTAL_BASE_URL", "http://localhost:8080")
    secret: str = os.environ.get("PORTAL_SECRET", "")

    # ---- data ----
    #: The middleware's live journal. Only ever read, and only to snapshot it.
    journal_db: str = os.environ.get("JOURNAL_DB", "/opt/mex/middleware/journal.db")
    #: Where the consistent copy is kept. Must be on the portal's own disk.
    snapshot_db: str = os.environ.get("PORTAL_SNAPSHOT_DB", "/var/lib/mex-portal/snapshot.db")
    snapshot_interval: int = int(os.environ.get("PORTAL_SNAPSHOT_SECONDS", "300"))

    # ---- auth ----
    portal_db: str = os.environ.get("PORTAL_DB", "/var/lib/mex-portal/portal.db")
    users_file: str = os.environ.get("PORTAL_USERS", "/etc/mex-portal/users.yaml")
    link_ttl: int = int(os.environ.get("PORTAL_LINK_TTL", "900"))
    session_ttl: int = int(os.environ.get("PORTAL_SESSION_TTL", str(30 * 86400)))
    #: Off only for local development over plain HTTP.
    secure_cookies: bool = _bool("PORTAL_SECURE_COOKIES", True)

    # ---- mail ----
    smtp_host: str = os.environ.get("SMTP_HOST", "")
    smtp_port: int = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user: str = os.environ.get("SMTP_USER", "")
    smtp_password: str = os.environ.get("SMTP_PASSWORD", "")
    smtp_from: str = os.environ.get("SMTP_FROM", "portal@mex-traders.com")
    smtp_from_name: str = os.environ.get("SMTP_FROM_NAME", "MEX Traders")
    #: Print the link to the log instead of sending it. Development only —
    #: `validate()` refuses to let this run alongside a public base URL.
    mail_console: bool = _bool("PORTAL_MAIL_CONSOLE", False)

    # ---- publishing ----
    public_out: str = os.environ.get(
        "PORTAL_PUBLIC_OUT", "/opt/mex/web/sites/mex/src/data/public-stats.json"
    )
    public_delay: str = os.environ.get("PORTAL_PUBLIC_DELAY", "T+1")
    #: Trades newer than this are withheld from the public snapshot, so the
    #: public page can never be read as a live feed of open activity.
    public_lag_hours: int = int(os.environ.get("PORTAL_PUBLIC_LAG_HOURS", "24"))

    errors: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        errs: list[str] = []

        if len(self.secret) < 32:
            errs.append(
                "PORTAL_SECRET is missing or too short (need >= 32 chars). "
                "Generate one with: python -m app.auth"
            )

        public = not self.base_url.startswith(("http://localhost", "http://127.0.0.1"))

        if public and not self.secure_cookies:
            errs.append(
                "PORTAL_SECURE_COOKIES is off while PORTAL_BASE_URL is public — "
                "session cookies would be sent over plain HTTP."
            )

        if public and self.mail_console:
            errs.append(
                "PORTAL_MAIL_CONSOLE is on while PORTAL_BASE_URL is public — "
                "login links would be written to the log instead of sent."
            )

        if not self.mail_console and not self.smtp_host:
            errs.append(
                "SMTP_HOST is not set and console mail is off — no login link "
                "could ever be delivered."
            )

        self.errors = errs
        return errs
