"""app.mex-traders.com — the members portal.

Runs beside the trading middleware but in its own process, on its own port,
with its own database. It reads a snapshot of the journal and never writes to
anything the middleware owns.

Routes
  GET  /                 → dashboard or login
  GET  /login            → request a link
  POST /login            → send the link (throttled, no account enumeration)
  GET  /auth             → redeem a link, start a session
  POST /logout           → end the session
  GET  /dashboard        → role-scoped HTML
  GET  /api/stats        → role-scoped JSON
  GET  /admin            → sessions + audit trail (owner only)
  GET  /health           → liveness
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import stats as stats_mod
from .auth import SESSION_COOKIE, Auth, User
from .chart import build_curve
from .config import Settings
from .mail import MailError, send_magic_link
from .store import Store, humanise_age, take_snapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mex.portal")

HERE = Path(__file__).parent

settings = Settings()
_errors = settings.validate()
if _errors:
    for err in _errors:
        log.error("configuration: %s", err)
    raise SystemExit("portal refuses to start with an unsafe configuration")

auth = Auth(
    db_path=settings.portal_db,
    secret=settings.secret,
    users_file=settings.users_file,
    link_ttl=settings.link_ttl,
    session_ttl=settings.session_ttl,
)
store = Store(settings.snapshot_db)
templates = Jinja2Templates(directory=str(HERE / "templates"))


# --- display filters ---------------------------------------------------------
# Dutch number formatting, and an em dash for every absent value so a missing
# metric reads as missing rather than as zero.

#: Narrow no-break space. Used as the thousands separator so a long amount
#: never wraps in the middle of the number, and so columns stay tight.
THIN_NBSP = " "


def _nl(value: float, digits: int = 0) -> str:
    text = f"{value:,.{digits}f}"
    return text.replace(",", THIN_NBSP).replace(".", ",")


def f_units(value, unit: str = "ticks") -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else "−" if value < 0 else ""
    return f"{sign}{_nl(abs(value))} {unit}".strip()


def f_r(value, digits: int = 1) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else "−" if value < 0 else ""
    return f"{sign}{_nl(abs(value), digits)}R"


def f_pct(value, digits: int = 1) -> str:
    return "—" if value is None else f"{_nl(value, digits)}%"


def f_ratio(value, digits: int = 2) -> str:
    return "—" if value is None else _nl(value, digits)


def f_count(value) -> str:
    return "—" if value is None else _nl(value)


def f_slip(value) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else "−" if value < 0 else ""
    return f"{sign}{_nl(abs(value), 2)} ticks"


def f_money(value, digits: int = 2, signed: bool = True) -> str:
    """Owner/partner only. Never reachable from a viewer render because the
    viewer payload carries no key this filter could be applied to.

    `signed=False` for balances: a plus in front of an account's total value
    reads as a gain, which it is not.
    """
    if value is None:
        return "—"
    if not signed:
        return f"${_nl(value, digits)}"
    sign = "+" if value > 0 else "−" if value < 0 else ""
    return f"{sign}${_nl(abs(value), digits)}"


def f_clock(value) -> str:
    if not value:
        return "—"
    return time.strftime("%d-%m-%Y %H:%M", time.localtime(value))


templates.env.filters.update(
    units=f_units, r=f_r, pct=f_pct, ratio=f_ratio,
    count=f_count, slip=f_slip, money=f_money, clock=f_clock,
)

app = FastAPI(title="MEX portal", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # The portal serves its own CSS and one inline script; nothing third-party
    # is ever loaded, so the policy can stay this tight.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    # Trading data must not sit in a shared cache or in the back/forward cache.
    response.headers["Cache-Control"] = "no-store, private"
    return response


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return (forwarded.split(",")[0] if forwarded else request.client.host if request.client else "").strip()


def current_user(request: Request) -> User | None:
    return auth.session_user(request.cookies.get(SESSION_COOKIE))


def require_user(request: Request) -> User:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="niet ingelogd")
    return user


def require_owner(request: Request) -> User:
    user = require_user(request)
    if not user.is_owner:
        raise HTTPException(status_code=403, detail="geen toegang")
    return user


async def _snapshot_loop() -> None:
    """Refresh the journal copy on a timer."""
    while True:
        try:
            take_snapshot(settings.journal_db, settings.snapshot_db)
        except FileNotFoundError:
            log.warning("journal %s not present yet — retrying", settings.journal_db)
        except Exception:  # noqa: BLE001 — a snapshot failure must not kill the loop
            log.exception("snapshot failed")
        await asyncio.sleep(settings.snapshot_interval)


@app.on_event("startup")
async def _startup() -> None:
    asyncio.create_task(_snapshot_loop())
    log.info("portal up at %s (users: %d)", settings.base_url, len(auth.users))


def _fleet() -> stats_mod.Fleet:
    fleet = stats_mod.build(store.trades(), store.accounts())
    fleet.generated_at = store.generated_at or time.time()
    return fleet


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return RedirectResponse("/dashboard" if current_user(request) else "/login", 302)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, sent: int = 0):
    if current_user(request):
        return RedirectResponse("/dashboard", 302)
    return templates.TemplateResponse(
        request, "login.html", {"sent": bool(sent), "error": None}
    )


@app.post("/login", response_class=HTMLResponse)
def login_request(request: Request, email: str = Form(...)):
    address = email.strip().lower()
    ip = client_ip(request)

    # Throttle on both axes before doing any work.
    if not auth.allow_request(f"ip:{ip}", limit=10) or not auth.allow_request(
        f"email:{address}", limit=5
    ):
        auth.audit("login.throttled", email=address, ip=ip)
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "sent": False,
                "error": "Te veel aanvragen. Probeer het over een kwartier opnieuw.",
            },
            status_code=429,
        )

    user = auth.user_for(address)
    if user is not None:
        link = f"{settings.base_url.rstrip('/')}/auth?token={auth.issue_token(address)}"
        try:
            send_magic_link(settings, address, link)
            auth.audit("login.requested", email=address, ip=ip)
        except MailError as exc:
            # Do not surface the delivery failure to the visitor — it would
            # reveal that the address exists. Operators see it in the log.
            log.error("magic link delivery failed for %s: %s", address, exc)
            auth.audit("login.mail_failed", email=address, ip=ip, detail=str(exc))
    else:
        auth.audit("login.unknown", email=address, ip=ip)

    # Identical response either way: the form is not an oracle for who has access.
    return RedirectResponse("/login?sent=1", 303)


@app.get("/auth")
def redeem(request: Request, token: str = ""):
    ip = client_ip(request)
    user = auth.redeem_token(token)
    if user is None:
        auth.audit("login.failed", ip=ip)
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "sent": False,
                "error": "Deze link is verlopen of al gebruikt. Vraag een nieuwe aan.",
            },
            status_code=400,
        )

    sid = auth.start_session(user, ip=ip, user_agent=request.headers.get("user-agent", ""))
    response = RedirectResponse("/dashboard", 303)
    response.set_cookie(
        SESSION_COOKIE,
        sid,
        max_age=settings.session_ttl,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    return response


@app.post("/logout")
def logout(request: Request):
    sid = request.cookies.get(SESSION_COOKIE)
    user = auth.session_user(sid)
    auth.end_session(sid)
    if user:
        auth.audit("logout", email=user.email, ip=client_ip(request))
    response = RedirectResponse("/login", 303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", 302)

    payload = stats_mod.serialise(_fleet(), user.role)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "data": payload,
            "unit_mode": not user.sees_money,
            "curve": build_curve(payload["equity"]),
            "freshness": humanise_age(store.generated_at),
            "has_data": store.available and bool(payload["markets"]),
        },
    )


@app.get("/api/stats")
def api_stats(request: Request, user: User = Depends(require_user)):
    """Role-scoped JSON. A viewer's response has no currency field in it —
    see stats.serialise, where each role builds its own payload."""
    return JSONResponse(stats_mod.serialise(_fleet(), user.role))


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, user: User = Depends(require_owner)):
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": user,
            "users": sorted(auth.users.values(), key=lambda u: (u.role, u.email)),
            "sessions": auth.active_sessions(),
            "audit": auth.recent_audit(60),
        },
    )


@app.post("/admin/revoke")
def admin_revoke(request: Request, email: str = Form(...), user: User = Depends(require_owner)):
    auth.revoke_all(email)
    return RedirectResponse("/admin", 303)


@app.post("/admin/reload-users")
def admin_reload(request: Request, user: User = Depends(require_owner)):
    count = auth.reload_users()
    auth.audit("users.reloaded", email=user.email, detail=str(count))
    return RedirectResponse("/admin", 303)


@app.get("/health")
def health():
    return {
        "ok": True,
        "snapshot": store.available,
        "snapshot_age_s": round(time.time() - store.generated_at) if store.generated_at else None,
        "users": len(auth.users),
    }


@app.exception_handler(401)
async def unauthorised(request: Request, exc: HTTPException) -> Response:
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "niet ingelogd"}, status_code=401)
    return RedirectResponse("/login", 302)
