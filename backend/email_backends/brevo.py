import base64
import logging
import os
from email.utils import parseaddr
from typing import Iterable, Optional

import requests
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend
from email.mime.base import MIMEBase

logger = logging.getLogger(__name__)


class BrevoEmailBackend(BaseEmailBackend):
    """
    Django email backend that sends mail via Brevo HTTP API (Transactional).
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_key = getattr(settings, "BREVO_API_KEY", None) or os.environ.get("BREVO_API_KEY")
        self.api_url = getattr(settings, "BREVO_API_URL", "https://api.brevo.com/v3/smtp/email")
        self.timeout = int(getattr(settings, "BREVO_TIMEOUT", 10))
        self.default_sender_email = (
            getattr(settings, "BREVO_SENDER_EMAIL", None)
            or getattr(settings, "DEFAULT_FROM_EMAIL", None)
        )
        self.default_sender_name = getattr(settings, "BREVO_SENDER_NAME", None)

    def send_messages(self, email_messages: Optional[Iterable[EmailMessage]]):
        if not email_messages:
            return 0
        if not self.api_key:
            if self.fail_silently:
                logger.error("BREVO_API_KEY is not set; emails not sent.")
                return 0
            raise RuntimeError("BREVO_API_KEY is not set.")

        sent = 0
        for message in email_messages:
            if self._send(message):
                sent += 1
        return sent

    def _send(self, message: EmailMessage) -> bool:
        recipients = list(message.to or []) + list(message.cc or []) + list(message.bcc or [])
        if not recipients:
            return False

        payload = self._build_payload(message)
        headers = {
            "api-key": self.api_key,
            "accept": "application/json",
            "content-type": "application/json",
        }

        try:
            resp = requests.post(self.api_url, json=payload, headers=headers, timeout=self.timeout)
            if 200 <= resp.status_code < 300:
                return True

            msg = f"Brevo API error {resp.status_code}: {resp.text}"
            if self.fail_silently:
                logger.error(msg)
                return False
            raise RuntimeError(msg)
        except Exception as exc:
            if self.fail_silently:
                logger.exception("Brevo email send failed: %s", exc)
                return False
            raise

    def _build_payload(self, message: EmailMessage) -> dict:
        sender_name, sender_email = self._parse_addr(message.from_email or self.default_sender_email)
        if not sender_email:
            raise RuntimeError("Sender email is missing. Set DEFAULT_FROM_EMAIL or BREVO_SENDER_EMAIL.")

        payload = {
            "sender": self._format_sender(sender_name, sender_email),
            "to": self._format_recipients(message.to or []),
            "subject": message.subject or "",
        }

        if message.cc:
            payload["cc"] = self._format_recipients(message.cc)
        if message.bcc:
            payload["bcc"] = self._format_recipients(message.bcc)

        reply_to = (message.reply_to or [])[:1]
        if reply_to:
            r_name, r_email = self._parse_addr(reply_to[0])
            if r_email:
                payload["replyTo"] = self._format_sender(r_name, r_email)

        text_content = message.body or ""
        html_content = self._extract_html(message)
        if text_content:
            payload["textContent"] = text_content
        if html_content:
            payload["htmlContent"] = html_content

        headers = message.extra_headers or {}
        if headers:
            payload["headers"] = headers

        attachments = self._format_attachments(message)
        if attachments:
            payload["attachment"] = attachments

        return payload

    def _format_sender(self, name: str, email: str) -> dict:
        sender = {"email": email}
        if name:
            sender["name"] = name
        elif self.default_sender_name:
            sender["name"] = self.default_sender_name
        return sender

    def _format_recipients(self, addresses: Iterable[str]) -> list:
        formatted = []
        for addr in addresses:
            name, email = self._parse_addr(addr)
            if not email:
                continue
            item = {"email": email}
            if name:
                item["name"] = name
            formatted.append(item)
        return formatted

    def _parse_addr(self, value: str) -> tuple[str, str]:
        if not value:
            return "", ""
        name, email = parseaddr(value)
        return (name or ""), (email or "")

    def _extract_html(self, message: EmailMessage) -> str:
        alternatives = getattr(message, "alternatives", []) or []
        for content, mimetype in alternatives:
            if mimetype == "text/html":
                return content
        return ""

    def _format_attachments(self, message: EmailMessage) -> list:
        attachments = []
        for attachment in message.attachments or []:
            name = None
            content_bytes = None

            if isinstance(attachment, tuple):
                if len(attachment) >= 2:
                    name = attachment[0]
                    content = attachment[1]
                    content_bytes = self._to_bytes(content)
            elif isinstance(attachment, MIMEBase):
                name = attachment.get_filename()
                content_bytes = attachment.get_payload(decode=True)
            else:
                # Django EmailAttachment
                name = getattr(attachment, "filename", None) or attachment.get_filename()
                content = attachment.get_content() if hasattr(attachment, "get_content") else None
                content_bytes = self._to_bytes(content)

            if not name or not content_bytes:
                continue

            attachments.append(
                {
                    "name": name,
                    "content": base64.b64encode(content_bytes).decode("ascii"),
                }
            )

        return attachments

    def _to_bytes(self, content) -> Optional[bytes]:
        if content is None:
            return None
        if isinstance(content, bytes):
            return content
        if isinstance(content, str):
            return content.encode("utf-8")
        return None
