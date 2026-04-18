"""
auth_guard.py — Login gate for CS AI Streamlit dashboards.

Usage (add after st.set_page_config() in each app):

    import os
    from auth_guard import require_login
    username, role = require_login(os.environ.get("CS_AI_COMPANY", "default"))
    st.session_state["username"] = username
    st.session_state["role"]     = role

Returns (username, role) when authenticated.
Calls st.stop() for unauthenticated users — nothing below the call renders.

Roles
-----
  agent      — sees only unassigned + their own tickets; can approve/reject drafts
  supervisor — all tickets, escalation alerts, can reassign
  admin      — everything + connection status + read-only config summary in sidebar
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

import streamlit as st
import yaml
import streamlit_authenticator as stauth

from paths import company_dir, resolve_data_file


# ==============================================================================
# LOGIN LOG
# ==============================================================================

def _log_login(username: str, status: str) -> None:
    """Append one login event to login_log.json (never raises)."""
    try:
        log_path = resolve_data_file("login_log.json")
        logs: list = []
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                try:
                    logs = json.load(f)
                except Exception:
                    logs = []
        logs.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "username":  username,
            "status":    status,
        })
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)
    except Exception:
        pass


# ==============================================================================
# SIDEBAR HELPERS
# ==============================================================================

_ROLE_ICON = {"admin": "🔑", "supervisor": "👁", "agent": "👤"}


def _render_sidebar(
    username: str,
    role: str,
    usernames_cfg: dict,
    authenticator: stauth.Authenticate,
) -> None:
    """
    Add to the sidebar (always visible once authenticated):
      - Logged-in user badge + logout button
      - Admin: system status expander (connection health + config summary)
      - Supervisor: escalation alert summary
    """
    with st.sidebar:
        st.divider()
        icon = _ROLE_ICON.get(role, "👤")
        display_name = usernames_cfg.get(username, {}).get("name", username)
        st.markdown(
            f"{icon} **{display_name}**  "
            f"<span style='color:grey;font-size:11px'>{role}</span>",
            unsafe_allow_html=True,
        )
        authenticator.logout(
            button_name="Logout",
            location="sidebar",
            key="cs_ai_logout",
        )
        st.divider()

        # ── Admin: system status panel ─────────────────────────────────────
        if role == "admin":
            with st.expander("Admin — System status", expanded=False):
                try:
                    from main import CONFIG  # noqa: PLC0415
                    openai_ok = bool(os.environ.get("OPENAI_API_KEY"))
                    c = CONFIG.get("company", {})
                    a = CONFIG.get("ai", {})
                    st.caption(f"**Company:** {c.get('name','—')}")
                    st.caption(f"**AI model:** {a.get('model','—')}")
                    st.caption(
                        f"**ERP:** {CONFIG.get('erp',{}).get('type','—')}  "
                        f"| **CRM:** {CONFIG.get('crm',{}).get('type','—')}"
                    )
                    st.caption(
                        f"**OpenAI key:** "
                        f"{'🟢 set' if openai_ok else '🔴 missing'}"
                    )
                    auto_send = CONFIG.get("confidence", {}).get("auto_send_enabled", False)
                    st.caption(
                        f"**Auto-send:** "
                        f"{'🟢 enabled' if auto_send else '⚪ disabled'}"
                    )
                except Exception as exc:
                    st.caption(f"Config unavailable: {exc}")

        # ── Supervisor: note ───────────────────────────────────────────────
        if role == "supervisor":
            st.caption("👁 Supervisor view — all tickets visible")


# ==============================================================================
# MAIN GUARD
# ==============================================================================

def require_login(company: str) -> tuple[str, str]:
    """
    Render the login screen if the user is not authenticated.

    Parameters
    ----------
    company : str
        Active company name (used to locate users.yaml and write login_log).

    Returns
    -------
    (username, role) : tuple[str, str]
        Only returned when the user is authenticated.
        Calls st.stop() otherwise — nothing below this call will render.

    Notes
    -----
    Must be called AFTER st.set_page_config().
    """
    cdir       = company_dir(company)
    users_path = os.path.join(cdir, "users.yaml")

    # ── Guard: users.yaml must exist ─────────────────────────────────────
    if not os.path.isfile(users_path):
        st.error(
            f"Authentication not configured for company **{company}**.  \n"
            f"Run: `python setup.py --company {company}` to create users."
        )
        st.stop()

    with open(users_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    cookie_cfg    = config.get("cookie", {})
    credentials   = config.get("credentials", {})
    usernames_cfg = credentials.get("usernames", {})

    # ── Guard: cookie key must be set ─────────────────────────────────────
    if not cookie_cfg.get("key"):
        st.error(
            f"Cookie secret not configured for company **{company}**.  \n"
            f"Run: `python setup.py --company {company}` to complete setup."
        )
        st.stop()

    # ── Warn about unconfigured passwords ────────────────────────────────
    unconfigured = [u for u, d in usernames_cfg.items() if not d.get("password")]
    if unconfigured:
        st.warning(
            f"Passwords not set for: **{', '.join(unconfigured)}**.  \n"
            f"Run `python setup.py --company {company}` to set them."
        )

    # ── Authenticate ──────────────────────────────────────────────────────
    authenticator = stauth.Authenticate(
        credentials=credentials,
        cookie_name=cookie_cfg.get("name", "cs_ai_session"),
        cookie_key=cookie_cfg["key"],
        cookie_expiry_days=float(cookie_cfg.get("expiry_days", 1)),
        auto_hash=False,   # passwords are pre-hashed by setup.py
    )

    authenticator.login(location="main", key="cs_ai_login")

    auth_status: bool | None = st.session_state.get("authentication_status")
    username: str             = st.session_state.get("username") or ""

    # ── Unauthenticated: wrong credentials ───────────────────────────────
    if auth_status is False:
        if not st.session_state.get("_cs_ai_fail_logged"):
            _log_login(username or "unknown", "failed")
            st.session_state["_cs_ai_fail_logged"] = True
        st.error("Incorrect username or password.")
        st.stop()

    # ── Unauthenticated: form not yet submitted ───────────────────────────
    if auth_status is None:
        st.stop()

    # ── Authenticated ─────────────────────────────────────────────────────
    if not st.session_state.get("_cs_ai_auth_logged"):
        _log_login(username, "success")
        st.session_state["_cs_ai_auth_logged"] = True
        st.session_state.pop("_cs_ai_fail_logged", None)

    role = usernames_cfg.get(username, {}).get("role", "agent")

    _render_sidebar(username, role, usernames_cfg, authenticator)

    return username, role


# ==============================================================================
# HELPERS (usable in other modules after require_login has run)
# ==============================================================================

def current_username() -> str:
    """Return the authenticated username from session state."""
    return st.session_state.get("username", "")


def current_role() -> str:
    """Return the authenticated user's role from session state."""
    return st.session_state.get("role", "agent")


def ticket_visible_to_current_user(ticket) -> bool:
    """
    Return True if the current user (agent) should see this ticket.
    Supervisors and admins always see all tickets.
    Agents see: unassigned tickets + tickets assigned to them.
    """
    role     = current_role()
    username = current_username()
    if role in ("supervisor", "admin"):
        return True
    assigned_to = (ticket.metadata or {}).get("assigned_to", "")
    return assigned_to in ("", username)
