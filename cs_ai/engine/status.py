"""
status.py — Live connection health checks for CS AI dashboards.

Usage:
    from status import check_connections, clear_cache, ConnectionStatus
    status = check_connections(CONFIG)   # cached for 60s

Designed to be called on every Streamlit render — the 60-second cache
ensures we never hit external services on every page load.
"""

from __future__ import annotations

import imaplib
import os
import socket
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from urllib.parse import urlparse


# ── Cache ─────────────────────────────────────────────────────────────────────

_CACHE_TTL = 60  # seconds

_cache: dict = {
    "result":     None,
    "company":    None,
    "expires_at": 0.0,
}


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class ConnectionStatus:
    erp:          str  # "connected" | "disconnected" | "not_configured"
    crm:          str  # "connected" | "disconnected" | "not_configured"
    email:        str  # "connected" | "disconnected" | "not_configured"
    ai:           str  # "connected" | "disconnected"
    erp_label:    str  # e.g. "ERP REST API (erp.company.com)"
    crm_label:    str  # e.g. "JSON Mock (demo)"
    email_label:  str  # e.g. "IMAP (mail.company.com)"
    ai_model:     str  # e.g. "gpt-4o-mini"
    last_checked: datetime


# ── Public API ────────────────────────────────────────────────────────────────

def check_connections(config: dict) -> ConnectionStatus:
    """
    Return a ConnectionStatus for the current company.
    Result is cached for 60 seconds — safe to call on every Streamlit render.
    """
    company = os.environ.get("CS_AI_COMPANY", "default")
    now = time.monotonic()

    if (
        _cache["result"] is not None
        and _cache["company"] == company
        and now < _cache["expires_at"]
    ):
        return _cache["result"]

    result = _run_checks(config)
    _cache["result"]     = result
    _cache["company"]    = company
    _cache["expires_at"] = now + _CACHE_TTL
    return result


def clear_cache() -> None:
    """Force the next check_connections() call to re-run all checks."""
    _cache["expires_at"] = 0.0
    _cache["result"]     = None


# ── Internal checks ───────────────────────────────────────────────────────────

def _run_checks(config: dict) -> ConnectionStatus:
    erp_status,   erp_label   = _check_erp(config)
    crm_status,   crm_label   = _check_crm(config)
    email_status, email_label = _check_email(config)
    ai_status,    ai_model    = _check_ai(config)

    return ConnectionStatus(
        erp=erp_status,
        crm=crm_status,
        email=email_status,
        ai=ai_status,
        erp_label=erp_label,
        crm_label=crm_label,
        email_label=email_label,
        ai_model=ai_model,
        last_checked=datetime.now(UTC).replace(tzinfo=None),
    )


def _check_erp(config: dict) -> tuple[str, str]:
    erp_cfg  = config.get("erp", {})
    erp_type = erp_cfg.get("type", "json_mock")
    endpoint = erp_cfg.get("endpoint", "") or ""

    if erp_type == "json_mock":
        return "not_configured", "JSON Mock (demo)"

    if erp_type == "mock_erp":
        try:
            from connector import MockERPConnector
            conn   = MockERPConnector(config)
            result = conn.test_connection()
            return ("connected" if result["ok"] else "disconnected"), "Mock ERP (dev)"
        except Exception as exc:
            return "disconnected", f"Mock ERP (dev) — {_short(exc)}"

    if erp_type == "erp_api":
        if not endpoint:
            return "not_configured", "ERP REST API (endpoint not set)"
        try:
            from connector import ERPConnector
            conn   = ERPConnector(config)
            result = conn.test_connection()
            label  = f"ERP REST API ({_domain(endpoint)})"
            return ("connected" if result["ok"] else "disconnected"), label
        except Exception as exc:
            return "disconnected", f"ERP REST API — {_short(exc)}"

    # Unknown type
    return "not_configured", erp_type


def _check_crm(config: dict) -> tuple[str, str]:
    crm_cfg  = config.get("crm", {})
    crm_type = crm_cfg.get("type", "json_mock")
    endpoint = crm_cfg.get("endpoint", "") or ""

    if crm_type == "json_mock":
        return "not_configured", "JSON Mock (demo)"

    if crm_type == "crm_api":
        if not endpoint:
            return "not_configured", "CRM REST API (endpoint not set)"
        try:
            import requests as _req
            from auth import AuthManager
            session = _req.Session()
            AuthManager.apply_to_session(session, crm_cfg.get("auth", {}))
            resp  = session.get(endpoint.rstrip("/") + "/", timeout=5)
            label = f"CRM REST API ({_domain(endpoint)})"
            return ("connected" if resp.status_code < 500 else "disconnected"), label
        except Exception as exc:
            return "disconnected", f"CRM REST API — {_short(exc)}"

    return "not_configured", crm_type


def _check_email(config: dict) -> tuple[str, str]:
    comm    = config.get("communication", {})
    inbound = comm.get("inbound", {})
    host    = inbound.get("host", "") or inbound.get("server", "") or ""

    if not host:
        return "not_configured", "Not configured"

    port     = int(inbound.get("port", 993))
    username = inbound.get("username", "")
    password = (
        inbound.get("password", "")
        or os.environ.get(inbound.get("password_env", "EMAIL_PASSWORD"), "")
    )
    use_ssl  = inbound.get("use_ssl", True)
    label    = f"IMAP ({host})"

    if not username or not password:
        return "not_configured", f"{label} — credentials missing"

    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(5)
    try:
        imap = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
        imap.login(username, password)
        imap.logout()
        return "connected", label
    except imaplib.IMAP4.error as exc:
        return "disconnected", f"{label} — {_short(exc)}"
    except Exception as exc:
        return "disconnected", f"{label} — {_short(exc)}"
    finally:
        socket.setdefaulttimeout(old_timeout)


def _check_ai(config: dict) -> tuple[str, str]:
    ai_cfg = config.get("ai", {})
    model  = ai_cfg.get("model", "gpt-4o-mini")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return "disconnected", f"{model} (no API key)"

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, timeout=5.0)
        client.models.list()
        return "connected", model
    except Exception as exc:
        return "disconnected", f"{model} — {_short(exc)}"


# ── Utilities ─────────────────────────────────────────────────────────────────

def _domain(url: str) -> str:
    """Extract hostname from a URL for display."""
    try:
        return urlparse(url).netloc or url[:40]
    except Exception:
        return url[:40]


def _short(exc: Exception) -> str:
    """Trim an exception message to a display-safe length."""
    return str(exc)[:60]
