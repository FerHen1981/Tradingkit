"""Sending the login link.

Deliberately loud on failure. A magic-link portal where mail silently fails is a
portal nobody can enter, and the failure would otherwise only show up as users
reporting that "the link never arrived".
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

log = logging.getLogger("mex.portal.mail")


class MailError(RuntimeError):
    pass


def _body(link: str, ttl_minutes: int) -> tuple[str, str]:
    text = f"""Hallo,

Hier is uw toegangslink voor het MEX Traders portal:

{link}

De link werkt {ttl_minutes} minuten en kan één keer worden gebruikt.
Heeft u niet zelf om toegang gevraagd, dan hoeft u niets te doen — zonder
klik gebeurt er niets.

MEX Traders
"""

    html = f"""<!doctype html>
<html lang="nl"><body style="margin:0;padding:24px;background:#06171a;
  font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#eaf4f1">
  <div style="max-width:520px;margin:0 auto;background:#0b2428;
    border:1px solid #1c3f43;border-radius:10px;padding:28px">
    <p style="margin:0 0 4px;font-family:ui-monospace,monospace;font-size:11px;
      letter-spacing:.14em;text-transform:uppercase;color:#84a8a3">MEX Traders</p>
    <h1 style="margin:0 0 16px;font-size:20px;color:#eaf4f1">Uw toegangslink</h1>
    <p style="margin:0 0 24px;font-size:15px;line-height:1.6;color:#84a8a3">
      Klik op de knop om in te loggen. De link werkt {ttl_minutes} minuten en
      kan één keer worden gebruikt.
    </p>
    <p style="margin:0 0 24px">
      <a href="{link}" style="display:inline-block;background:#f0b64d;color:#06171a;
        text-decoration:none;font-weight:600;font-size:14px;padding:12px 20px;
        border-radius:6px">Inloggen op het portal</a>
    </p>
    <p style="margin:0;font-size:12px;line-height:1.6;color:#5c807c">
      Werkt de knop niet? Plak dan deze link in uw browser:<br>
      <span style="word-break:break-all">{link}</span>
    </p>
    <p style="margin:20px 0 0;font-size:12px;line-height:1.6;color:#5c807c">
      Heeft u niet om toegang gevraagd, dan hoeft u niets te doen.
    </p>
  </div>
</body></html>"""

    return text, html


def send_magic_link(settings, to_email: str, link: str) -> None:
    """Deliver a login link, or raise MailError."""
    ttl_minutes = max(1, settings.link_ttl // 60)
    text, html = _body(link, ttl_minutes)

    if settings.mail_console:
        # Development path. config.validate() refuses to allow this in
        # combination with a public base URL.
        log.warning("MAIL (console) to %s:\n%s", to_email, link)
        return

    if not settings.smtp_host:
        raise MailError("SMTP_HOST is not configured")

    message = EmailMessage()
    message["Subject"] = "Uw toegangslink voor het MEX Traders portal"
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from))
    message["To"] = to_email
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port,
                                  context=context, timeout=15) as smtp:
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                smtp.starttls(context=context)
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        log.error("could not send login link to %s: %s", to_email, exc)
        raise MailError(str(exc)) from exc

    log.info("login link sent to %s", to_email)
