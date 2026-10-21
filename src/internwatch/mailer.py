"""Send email over SMTP (Gmail app password) and keep a copy of every message in data/outbox/."""
from __future__ import annotations

import logging
import re
import smtplib
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from .config import PLACEHOLDER_RE, Config
from .http import ssl_context

log = logging.getLogger(__name__)


class Mailer:
    def __init__(self, cfg: Config, db=None, dry_run: bool = False):
        self.cfg = cfg
        self.db = db
        self.dry_run = dry_run
        self.outbox = cfg.settings.path("outbox")
        self.outbox.mkdir(parents=True, exist_ok=True)

    @property
    def recipient(self) -> str:
        return self.cfg.settings.recipient

    def ready(self) -> tuple[bool, str]:
        if not self.recipient or PLACEHOLDER_RE.match(self.recipient):
            return False, "recipient not set (email.to in config/settings.yaml)"
        if not self.cfg.secrets.email_ready:
            return False, "SMTP_USER / SMTP_PASSWORD not set in .env"
        return True, ""

    def send(self, kind: str, subject: str, text: str, html: str,
             attachments: list[tuple[str, bytes, str]] | None = None) -> tuple[bool, str | None, Path]:
        """Always writes the message to the outbox; sends it if credentials are configured.

        attachments: [(filename, data, "type/subtype")]
        """
        msg = EmailMessage()
        sender = self.cfg.secrets.email_from or self.cfg.secrets.smtp_user or "internwatch@localhost"
        msg["From"] = f"InternWatch <{sender}>" if "@" in sender else sender
        msg["To"] = self.recipient
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="internwatch")
        msg["X-InternWatch-Kind"] = kind
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        for name, data, mime in attachments or []:
            maintype, subtype = mime.split("/", 1)
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        slug = re.sub(r"[^a-z0-9]+", "-", kind.lower()).strip("-")
        path = self.outbox / f"{stamp}-{slug}.eml"
        n = 1
        while path.exists():
            path = self.outbox / f"{stamp}-{slug}-{n}.eml"
            n += 1
        path.write_bytes(bytes(msg))
        path.with_suffix(".html").write_text(html)

        ok, why = self.ready()
        sent, error = False, None
        if self.dry_run:
            error = "dry run (not sent)"
        elif not ok:
            error = f"not sent: {why}"
        else:
            for attempt in range(3):
                try:
                    self._smtp_send(msg)
                    sent, error = True, None
                    break
                except (smtplib.SMTPException, OSError) as e:
                    error = f"{type(e).__name__}: {e}"
                    log.warning("SMTP send failed (attempt %d): %s", attempt + 1, error)
                    time.sleep(5 * (attempt + 1))
        if self.db is not None:
            self.db.log_email(kind, subject, str(path), sent, error)
        log.info("email %s %r -> %s (%s)", kind, subject, path.name, "sent" if sent else error)
        return sent, error, path

    def _smtp_send(self, msg: EmailMessage) -> None:
        sec = self.cfg.secrets
        # certifi's CA bundle, not the system default: python.org builds on macOS ship without CA certificates
        # until "Install Certificates.command" is run, which makes STARTTLS to Gmail fail certificate checks.
        ctx = ssl_context()
        if sec.smtp_port == 465:
            with smtplib.SMTP_SSL(sec.smtp_host, sec.smtp_port, timeout=30, context=ctx) as s:
                s.login(sec.smtp_user, sec.smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(sec.smtp_host, sec.smtp_port, timeout=30) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.ehlo()
                s.login(sec.smtp_user, sec.smtp_password)
                s.send_message(msg)
