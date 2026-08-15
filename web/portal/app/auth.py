"""Magic-link authentication, sessions and roles.

Design notes worth knowing before changing anything here:

* **No passwords.** There is nothing to leak, reset or reuse. The cost is that
  login depends on mail delivery, which is why `mail.py` fails loudly.
* **Links are single-use and short-lived.** A signed token alone is not enough:
  it lives in an inbox and in server logs, so every token is burned on first
  use, tracked in the database until it expires.
* **Sessions live in SQLite, not in a signed cookie.** A stateless cookie
  cannot be revoked. Being able to cut off a viewer immediately matters more
  here than saving a database read.
* **Constant-time comparison everywhere**, and unknown addresses take the same
  path and the same time as known ones, so the login form is not an oracle for
  who has access.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

log = logging.getLogger("mex.portal.auth")

Role = Literal["owner", "partner", "viewer"]
VALID_ROLES: frozenset[str] = frozenset({"owner", "partner", "viewer"})

SESSION_COOKIE = "mex_session"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    sid        TEXT PRIMARY KEY,
    email      TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    user_agent TEXT,
    ip         TEXT
);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);

-- Burned magic-link tokens. Rows are kept until the token would have expired
-- anyway; after that the signature check rejects them on its own.
CREATE TABLE IF NOT EXISTS used_tokens (
    jti        TEXT PRIMARY KEY,
    used_at    REAL NOT NULL,
    expires_at REAL NOT NULL
);

-- Append-only audit trail. Every login attempt, grant and logout lands here.
CREATE TABLE IF NOT EXISTS audit (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     REAL NOT NULL,
    event  TEXT NOT NULL,
    email  TEXT,
    ip     TEXT,
    detail TEXT
);

-- Login-request throttle, per email and per IP.
CREATE TABLE IF NOT EXISTS throttle (
    key      TEXT PRIMARY KEY,
    count    INTEGER NOT NULL,
    window_start REAL NOT NULL
);
"""


@dataclass(frozen=True)
class User:
    email: str
    role: Role
    name: str = ""

    @property
    def sees_money(self) -> bool:
        return self.role in {"owner", "partner"}

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"


def load_users(path: str) -> dict[str, User]:
    """Read the invite list.

    An entry with an unrecognised role is demoted to `viewer` rather than
    rejected, so a typo degrades access instead of widening it.
    """
    file = Path(path)
    if not file.exists():
        log.warning("users file %s not found — nobody can log in", path)
        return {}

    raw = yaml.safe_load(file.read_text()) or {}
    entries = raw.get("users", raw if isinstance(raw, list) else [])

    users: dict[str, User] = {}
    for entry in entries:
        email = str(entry.get("email", "")).strip().lower()
        if not email:
            continue
        role = str(entry.get("role", "viewer")).strip().lower()
        if role not in VALID_ROLES:
            log.warning("user %s has unknown role %r — demoted to viewer", email, role)
            role = "viewer"
        users[email] = User(email=email, role=role, name=str(entry.get("name", "")))

    log.info("loaded %d user(s)", len(users))
    return users


class Auth:
    def __init__(
        self,
        db_path: str,
        secret: str,
        users_file: str,
        link_ttl: int = 900,
        session_ttl: int = 30 * 86400,
    ):
        if not secret or len(secret) < 32:
            raise ValueError(
                "PORTAL_SECRET must be set to at least 32 random characters"
            )
        self.secret = secret.encode()
        self.link_ttl = link_ttl
        self.session_ttl = session_ttl
        self.users_file = users_file
        self.users = load_users(users_file)

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.executescript(_SCHEMA)
        self.db.commit()
        self._sweep()

    # ---- users -----------------------------------------------------------

    def reload_users(self) -> int:
        self.users = load_users(self.users_file)
        return len(self.users)

    def user_for(self, email: str) -> User | None:
        return self.users.get(email.strip().lower())

    # ---- magic link ------------------------------------------------------

    def issue_token(self, email: str) -> str:
        """Build a signed, single-use, expiring token for `email`."""
        payload = {
            "e": email.strip().lower(),
            "x": str(int(time.time()) + self.link_ttl),
            "j": secrets.token_urlsafe(12),
        }
        body = f"{payload['e']}|{payload['x']}|{payload['j']}"
        sig = hmac.new(self.secret, body.encode(), hashlib.sha256).digest()
        return (
            base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
            + "."
            + base64.urlsafe_b64encode(sig).decode().rstrip("=")
        )

    def redeem_token(self, token: str) -> User | None:
        """Validate, burn and resolve a token. Returns None for anything wrong."""
        try:
            body_b64, sig_b64 = token.split(".", 1)
            body = base64.urlsafe_b64decode(body_b64 + "=" * (-len(body_b64) % 4))
            sig = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
        except (ValueError, TypeError):
            return None

        expected = hmac.new(self.secret, body, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None

        try:
            email, expiry, jti = body.decode().split("|", 2)
            expires_at = float(expiry)
        except (ValueError, UnicodeDecodeError):
            return None

        if time.time() > expires_at:
            return None

        # Burn it. The INSERT is the check: a duplicate jti means the link has
        # already been followed, so a forwarded or replayed mail is inert.
        try:
            self.db.execute(
                "INSERT INTO used_tokens (jti, used_at, expires_at) VALUES (?,?,?)",
                (jti, time.time(), expires_at),
            )
            self.db.commit()
        except sqlite3.IntegrityError:
            self.audit("login.replay", email=email)
            return None

        return self.user_for(email)

    # ---- sessions --------------------------------------------------------

    def start_session(self, user: User, ip: str = "", user_agent: str = "") -> str:
        sid = secrets.token_urlsafe(32)
        now = time.time()
        self.db.execute(
            "INSERT INTO sessions (sid, email, created_at, expires_at, user_agent, ip)"
            " VALUES (?,?,?,?,?,?)",
            (sid, user.email, now, now + self.session_ttl, user_agent[:200], ip[:64]),
        )
        self.db.commit()
        self.audit("login.success", email=user.email, ip=ip, detail=user.role)
        return sid

    def session_user(self, sid: str | None) -> User | None:
        if not sid:
            return None
        row = self.db.execute(
            "SELECT email, expires_at FROM sessions WHERE sid = ?", (sid,)
        ).fetchone()
        if row is None:
            return None
        if row[1] < time.time():
            self.end_session(sid)
            return None
        # Resolve the role from the invite list on every request, so removing
        # somebody from users.yaml takes effect at once rather than whenever
        # their session happens to expire.
        return self.user_for(row[0])

    def end_session(self, sid: str | None) -> None:
        if not sid:
            return
        self.db.execute("DELETE FROM sessions WHERE sid = ?", (sid,))
        self.db.commit()

    def revoke_all(self, email: str) -> int:
        cur = self.db.execute("DELETE FROM sessions WHERE email = ?", (email.lower(),))
        self.db.commit()
        self.audit("session.revoked", email=email, detail=str(cur.rowcount))
        return cur.rowcount

    def active_sessions(self) -> list[dict]:
        cur = self.db.execute(
            "SELECT email, created_at, expires_at, ip FROM sessions"
            " WHERE expires_at > ? ORDER BY created_at DESC",
            (time.time(),),
        )
        return [
            {"email": r[0], "created_at": r[1], "expires_at": r[2], "ip": r[3]}
            for r in cur.fetchall()
        ]

    # ---- throttle --------------------------------------------------------

    def allow_request(self, key: str, limit: int = 5, window: int = 900) -> bool:
        """Sliding-ish window limiter for login requests.

        Applied to both the email and the client IP, so neither flooding one
        inbox nor spraying many addresses from one host gets far.
        """
        now = time.time()
        row = self.db.execute(
            "SELECT count, window_start FROM throttle WHERE key = ?", (key,)
        ).fetchone()

        if row is None or now - row[1] > window:
            self.db.execute(
                "INSERT INTO throttle (key, count, window_start) VALUES (?,1,?)"
                " ON CONFLICT(key) DO UPDATE SET count=1, window_start=excluded.window_start",
                (key, now),
            )
            self.db.commit()
            return True

        if row[0] >= limit:
            return False

        self.db.execute("UPDATE throttle SET count = count + 1 WHERE key = ?", (key,))
        self.db.commit()
        return True

    # ---- audit -----------------------------------------------------------

    def audit(self, event: str, email: str = "", ip: str = "", detail: str = "") -> None:
        self.db.execute(
            "INSERT INTO audit (ts, event, email, ip, detail) VALUES (?,?,?,?,?)",
            (time.time(), event, email.lower(), ip[:64], detail[:400]),
        )
        self.db.commit()

    def recent_audit(self, limit: int = 50) -> list[dict]:
        cur = self.db.execute(
            "SELECT ts, event, email, ip, detail FROM audit ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [
            {"ts": r[0], "event": r[1], "email": r[2], "ip": r[3], "detail": r[4]}
            for r in cur.fetchall()
        ]

    # ---- housekeeping ----------------------------------------------------

    def _sweep(self) -> None:
        now = time.time()
        self.db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        self.db.execute("DELETE FROM used_tokens WHERE expires_at < ?", (now,))
        self.db.execute("DELETE FROM throttle WHERE window_start < ?", (now - 86400,))
        self.db.commit()


def generate_secret() -> str:
    """Helper for `python -m app.auth` — prints a usable PORTAL_SECRET."""
    return secrets.token_urlsafe(48)


if __name__ == "__main__":  # pragma: no cover
    print(generate_secret())
