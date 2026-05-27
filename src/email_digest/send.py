"""SMTP send for the digest. Credentials read from the environment only."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Iterable

from src.config import get_settings
from src.email_digest.render import RenderedDigest

logger = logging.getLogger(__name__)


def send_digest(digest: RenderedDigest, recipients: Iterable[str] | None = None) -> bool:
    settings = get_settings()
    to_list = list(recipients) if recipients is not None else settings.digest_recipient_list

    if not to_list:
        logger.warning("No digest recipients configured; skipping send")
        return False
    if not settings.smtp_host or not settings.smtp_user:
        logger.warning("SMTP not configured; printing digest to stdout instead")
        print(f"Subject: {digest.subject}\nRecipients: {to_list}\n")
        print(digest.html[:1500] + ("..." if len(digest.html) > 1500 else ""))
        return False

    msg = EmailMessage()
    msg["Subject"] = digest.subject
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(to_list)
    msg.set_content(
        "This email requires an HTML capable client. "
        "Open the dashboard for the full digest: " + settings.dashboard_url
    )
    msg.add_alternative(digest.html, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
        s.starttls()
        s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)
    logger.info("Sent digest to %s", to_list)
    return True
