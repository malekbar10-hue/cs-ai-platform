"""
channels.py — Generic communication channel abstraction layer.

Supports inbound message reading and outbound message sending.
100% config-driven. No company-specific logic.

Currently implemented:
  - EmailReader  : IMAP inbound (SSL)
  - EmailSender  : SMTP/TLS outbound

Factory functions pick the right class from config.json["communication"].
"""

from __future__ import annotations

import imaplib
import re
import smtplib
import email
import json
import os
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from paths import config_path as _config_path, data_dir as _data_dir
from datetime import datetime, UTC
from typing import List, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class InboundMessage:
    """Normalised representation of any inbound message regardless of channel."""
    message_id: str
    channel: str                    # "email", "api", …
    sender: str
    sender_name: str
    recipients: List[str]
    subject: str
    body: str
    timestamp: datetime
    raw: object = field(default=None, repr=False)   # original channel object

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "channel": self.channel,
            "sender": self.sender,
            "sender_name": self.sender_name,
            "recipients": self.recipients,
            "subject": self.subject,
            "body": self.body,
            "timestamp": self.timestamp.isoformat(),
        }


# ---------------------------------------------------------------------------
# Base classes
# ---------------------------------------------------------------------------

class BaseChannelReader:
    """Abstract base for all inbound channel readers."""

    def connect(self) -> None:
        raise NotImplementedError

    def fetch_unread(self, max_messages: int = 10) -> List[InboundMessage]:
        raise NotImplementedError

    def fetch_recent(self, max_messages: int = 10) -> List[InboundMessage]:
        raise NotImplementedError

    def mark_read(self, message_id: str) -> None:
        raise NotImplementedError

    def disconnect(self) -> None:
        pass

    # Context manager support
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()


class BaseChannelSender:
    """Abstract base for all outbound channel senders."""

    def connect(self) -> None:
        raise NotImplementedError

    def send(self, to: str, subject: str, body: str,
             reply_to_message: Optional[InboundMessage] = None) -> bool:
        raise NotImplementedError

    def disconnect(self) -> None:
        pass

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()


# ---------------------------------------------------------------------------
# Email — IMAP reader
# ---------------------------------------------------------------------------

def _decode_header_value(raw_value: str) -> str:
    """Decode MIME-encoded header value to plain string."""
    if not raw_value:
        return ""
    parts = decode_header(raw_value)
    result = []
    for part, encoding in parts:
        if isinstance(part, bytes):
            result.append(part.decode(encoding or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


def _extract_body(msg: email.message.Message) -> str:
    """Extract plain-text body from a (possibly multipart) email."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="replace")
        # Fallback to HTML if no plain part
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="replace")
    else:
        charset = msg.get_content_charset() or "utf-8"
        return msg.get_payload(decode=True).decode(charset, errors="replace")
    return ""


class EmailReader(BaseChannelReader):
    """
    IMAP email reader.

    Config keys expected (config["communication"]["inbound"]):
        host, port, username, password, mailbox, use_ssl
    """

    def __init__(self, cfg: dict):
        self._host = cfg["host"]
        self._port = int(cfg.get("port", 993))
        self._username = cfg["username"]
        self._password = cfg.get("password") or os.getenv(cfg.get("password_env", "EMAIL_PASSWORD"), "")
        self._mailbox = cfg.get("mailbox", "INBOX")
        self._use_ssl = cfg.get("use_ssl", True)
        self._imap: Optional[imaplib.IMAP4_SSL] = None

    def connect(self) -> None:
        if self._use_ssl:
            self._imap = imaplib.IMAP4_SSL(self._host, self._port)
        else:
            self._imap = imaplib.IMAP4(self._host, self._port)
        self._imap.login(self._username, self._password)
        self._imap.select(self._mailbox)

    def disconnect(self) -> None:
        if self._imap:
            try:
                self._imap.close()
                self._imap.logout()
            except Exception:
                pass
            self._imap = None

    def _parse_message(self, uid: bytes, raw_data: bytes) -> InboundMessage:
        msg = email.message_from_bytes(raw_data)
        sender_full = _decode_header_value(msg.get("From", ""))
        # Split "Name <addr>" or just "addr"
        if "<" in sender_full:
            sender_name, sender_addr = sender_full.rsplit("<", 1)
            sender_addr = sender_addr.rstrip(">").strip()
            sender_name = sender_name.strip().strip('"')
        else:
            sender_addr = sender_full.strip()
            sender_name = ""

        recipients_raw = msg.get("To", "")
        recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

        date_str = msg.get("Date", "")
        try:
            from email.utils import parsedate_to_datetime
            timestamp = parsedate_to_datetime(date_str)
        except Exception:
            timestamp = datetime.now(UTC).replace(tzinfo=None)

        return InboundMessage(
            message_id=uid.decode("utf-8"),
            channel="email",
            sender=sender_addr,
            sender_name=sender_name,
            recipients=recipients,
            subject=_decode_header_value(msg.get("Subject", "")),
            body=_extract_body(msg).strip(),
            timestamp=timestamp,
            raw=msg,
        )

    def fetch_unread(self, max_messages: int = 10) -> List[InboundMessage]:
        """Fetch up to max_messages unseen messages (oldest first)."""
        _, data = self._imap.uid("search", None, "UNSEEN")
        uids = data[0].split()
        uids = uids[-max_messages:]   # most recent N
        return self._fetch_uids(uids)

    def fetch_recent(self, max_messages: int = 10) -> List[InboundMessage]:
        """Fetch the most recent N messages regardless of read status."""
        _, data = self._imap.uid("search", None, "ALL")
        uids = data[0].split()
        uids = uids[-max_messages:]
        return self._fetch_uids(uids)

    def _fetch_uids(self, uids: list) -> List[InboundMessage]:
        messages = []
        for uid in uids:
            _, msg_data = self._imap.uid("fetch", uid, "(RFC822)")
            if not (msg_data and msg_data[0]):
                continue
            raw = msg_data[0][1]
            msg = self._parse_message(uid, raw)

            # Noise check — skip and log without returning
            is_noise, reason = self.is_noise_email(msg)
            if is_noise:
                self._write_skip_log(msg.sender, msg.subject, reason)
                continue

            # Clean subject and body before passing downstream
            msg.subject = self.clean_subject(msg.subject)
            msg.body    = self.clean_body(msg.body)

            messages.append(msg)
        return messages

    def mark_read(self, message_id: str) -> None:
        self._imap.uid("store", message_id.encode(), "+FLAGS", "\\Seen")

    # ── Noise filtering ──────────────────────────────────────────────────────

    _NOISE_SENDERS = re.compile(
        r"(mailer-daemon@|postmaster@|noreply@|no-reply@|donotreply@)",
        re.IGNORECASE,
    )

    # Patterns that mark the start of a quoted reply chain
    _QUOTE_PATTERNS = re.compile(
        r"^(on .{5,80}wrote:|le .{5,80}a écrit\s*:|"
        r"-{4,}\s*original message\s*-{4,}|"
        r"de\s*:.*\nà\s*:)",
        re.IGNORECASE | re.MULTILINE,
    )

    # HTML tag stripper
    _HTML_TAG = re.compile(r"<[^>]+>")

    @staticmethod
    def _strip_html(text: str) -> str:
        return EmailReader._HTML_TAG.sub("", text)

    def clean_subject(self, subject: str) -> str:
        """Strip leading Re/Fwd/TR/Réf/Rép prefixes and normalise whitespace."""
        _prefix = re.compile(
            r"^\s*(re|fwd?|tr|réf|rép)\s*:\s*", re.IGNORECASE
        )
        result = subject
        while True:
            cleaned = _prefix.sub("", result).strip()
            if cleaned == result:
                break
            result = cleaned
        return " ".join(result.split())

    def clean_body(self, body: str) -> str:
        """Return only the new content, stripping the quoted reply chain."""
        match = self._QUOTE_PATTERNS.search(body)
        if match:
            body = body[: match.start()].rstrip()
        return body.strip()

    def is_noise_email(self, msg: "InboundMessage") -> tuple:
        """
        Returns (True, reason) if the message should be silently skipped,
        (False, "") otherwise.
        """
        subject = msg.subject or ""
        sender  = msg.sender  or ""
        body    = msg.body    or ""

        # More than 2 Re: prefixes → reply loop risk
        re_count = len(re.findall(r"(?i)\bre\s*:", subject))
        if re_count > 2:
            return True, f"Reply loop risk ({re_count} Re: prefixes)"

        # Known automated sender
        if self._NOISE_SENDERS.search(sender):
            return True, f"Automated sender: {sender}"

        # Empty body (after stripping HTML and whitespace)
        plain = self._strip_html(body).strip()
        if not plain:
            return True, "Empty body"

        return False, ""

    def _write_skip_log(self, sender: str, subject: str, reason: str) -> None:
        """Append one entry to skip_log.json in the company data folder."""
        try:
            skip_path = os.path.join(_data_dir(), "skip_log.json")
            entry = {
                "timestamp": datetime.now(UTC).replace(tzinfo=None).isoformat(),
                "sender":    sender,
                "subject":   subject,
                "reason":    reason,
            }
            existing: list = []
            if os.path.exists(skip_path):
                try:
                    with open(skip_path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    existing = []
            existing.append(entry)
            with open(skip_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Email — SMTP sender
# ---------------------------------------------------------------------------

class EmailSender(BaseChannelSender):
    """
    SMTP email sender with STARTTLS.

    Config keys expected (config["communication"]["outbound"]):
        host, port, username, password, from_address, from_name, use_tls
    """

    def __init__(self, cfg: dict):
        self._host = cfg["host"]
        self._port = int(cfg.get("port", 587))
        self._username = cfg["username"]
        self._password = cfg.get("password") or os.getenv(cfg.get("password_env", "EMAIL_PASSWORD"), "")
        self._from_address = cfg.get("from_address", cfg["username"])
        self._from_name = cfg.get("from_name", "")
        self._use_tls = cfg.get("use_tls", True)
        self._smtp: Optional[smtplib.SMTP] = None

    def connect(self) -> None:
        self._smtp = smtplib.SMTP(self._host, self._port)
        self._smtp.ehlo()
        if self._use_tls:
            self._smtp.starttls()
            self._smtp.ehlo()
        self._smtp.login(self._username, self._password)

    def disconnect(self) -> None:
        if self._smtp:
            try:
                self._smtp.quit()
            except Exception:
                pass
            self._smtp = None

    def send(self, to: str, subject: str, body: str,
             reply_to_message: Optional[InboundMessage] = None) -> bool:
        """
        Send a plain-text email.
        If reply_to_message is provided, threading headers are added automatically.
        Returns True on success, False on failure.
        """
        mime = MIMEMultipart("alternative")
        from_header = (
            f"{self._from_name} <{self._from_address}>"
            if self._from_name else self._from_address
        )
        mime["From"] = from_header
        mime["To"] = to
        mime["Subject"] = subject

        if reply_to_message:
            orig_id = reply_to_message.raw.get("Message-ID", "") if reply_to_message.raw else ""
            if orig_id:
                mime["In-Reply-To"] = orig_id
                mime["References"] = orig_id

        mime.attach(MIMEText(body, "plain", "utf-8"))

        try:
            self._smtp.sendmail(self._from_address, [to], mime.as_string())
            return True
        except smtplib.SMTPException as exc:
            print(f"[EmailSender] Send failed: {exc}")
            return False


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def _load_comm_config() -> dict:
    with open(_config_path(), "r", encoding="utf-8") as f:
        return json.load(f).get("communication", {})


def get_channel_reader(cfg: Optional[dict] = None) -> BaseChannelReader:
    """
    Return the appropriate inbound reader based on config.

    cfg: optional override dict (config["communication"]).
         If None, loads from config.json automatically.

    Supported types: "email" (default)
    """
    comm = cfg or _load_comm_config()
    inbound = comm.get("inbound", {})
    channel_type = inbound.get("type", "email")

    if channel_type == "email":
        return EmailReader(inbound)
    else:
        raise ValueError(f"[channels] Unknown inbound channel type: '{channel_type}'")


def get_channel_sender(cfg: Optional[dict] = None) -> BaseChannelSender:
    """
    Return the appropriate outbound sender based on config.

    cfg: optional override dict (config["communication"]).
         If None, loads from config.json automatically.

    Supported types: "email" (default)
    """
    comm = cfg or _load_comm_config()
    outbound = comm.get("outbound", {})
    channel_type = outbound.get("type", "email")

    if channel_type == "email":
        return EmailSender(outbound)
    else:
        raise ValueError(f"[channels] Unknown outbound channel type: '{channel_type}'")
