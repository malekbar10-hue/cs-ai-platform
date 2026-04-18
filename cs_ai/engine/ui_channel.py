"""
ui_channel.py — Channel-aware UI rendering for CS AI dashboards.

Replaces hardcoded email widgets with channel-adaptive ones.
Read channel_config from CONFIG["communication"]["outbound"].

Public API
----------
get_channel_label(channel_config)          → str label for the header bar
render_message_header(msg, channel_config) → caption row above each chat bubble
render_inbound_input(channel_config, form_key) → text on submit or None
render_send_controls(ticket, draft, channel_config,
                     on_approve_callback, button_key)  → approve button + send
"""

from __future__ import annotations

import streamlit as st

# ── Channel type → display label ─────────────────────────────────────────────

_CHANNEL_LABELS: dict[str, str] = {
    "email":        "Email",
    "ticketing_api":"Ticketing API",
    "manual":       "Manual Entry",
}

_CHANNEL_ICONS: dict[str, str] = {
    "email":        "📧",
    "ticketing_api":"🎫",
    "manual":       "✍️",
}


def get_channel_label(channel_config: dict) -> str:
    """Return a human-readable label for the configured outbound channel."""
    ch = channel_config.get("type", "email")
    return _CHANNEL_LABELS.get(ch, ch.replace("_", " ").title())


# ── Message header ────────────────────────────────────────────────────────────

def render_message_header(
    msg: dict,
    channel_config: dict,
    message_index: int | None = None,
    ticket=None,
) -> None:
    """
    Render a compact metadata caption above each chat bubble.
    Adapts the fields shown to the configured channel.

    Parameters
    ----------
    msg           : message dict {role, content, timestamp, ...}
    channel_config: config["communication"]["outbound"]
    message_index : 0-based position in the thread (used for reply indicator)
    ticket        : optional Ticket object for subject/email metadata
    """
    ch   = channel_config.get("type", "email")
    icon = _CHANNEL_ICONS.get(ch, "💬")
    role = msg.get("role", "customer")
    ts   = msg.get("timestamp", "")[:16].replace("T", " ")

    if ch == "email":
        if role == "customer":
            parts = [f"{icon} Received: {ts}"]
            if ticket and ticket.customer_email:
                parts.append(f"From: {ticket.customer_email}")
            if ticket and ticket.subject and message_index == 0:
                parts.append(f"Subject: {ticket.subject}")
            if message_index is not None and message_index > 0:
                parts.append(f"Reply #{message_index}")
            st.caption("  ·  ".join(parts))
        else:
            st.caption(f"{icon} Sent: {ts}")

    elif ch == "ticketing_api":
        if role == "customer":
            parts = [f"{icon} Requester: {ts}"]
            if ticket:
                parts.append(f"Ticket: {ticket.ticket_id[:8] if ticket.ticket_id else '—'}")
            if ticket and ticket.subject and message_index == 0:
                parts.append(ticket.subject)
            st.caption("  ·  ".join(parts))
        else:
            st.caption(f"{icon} Agent response: {ts}")

    else:  # manual
        label = "Customer" if role == "customer" else "Agent"
        name  = (ticket.customer_name if ticket and ticket.customer_name else "") or label
        st.caption(f"✍️ {name}: {ts}")


# ── Inbound input form ────────────────────────────────────────────────────────

def render_inbound_input(
    channel_config: dict,
    form_key: str = "inbound_input",
) -> str | None:
    """
    Render the customer message input area, adapted to the channel.

    - email / ticketing_api: show an info notice (messages arrive via poller)
                             and return None.
    - manual: show a text area form; return the submitted text or None.

    Parameters
    ----------
    channel_config: config["communication"]["outbound"]
    form_key      : unique Streamlit form key (use different keys per page)

    Returns
    -------
    str  — the submitted customer message (manual channel only)
    None — no input this render cycle
    """
    ch = channel_config.get("type", "email")

    if ch in ("email", "ticketing_api"):
        icon = _CHANNEL_ICONS.get(ch, "💬")
        st.info(
            f"{icon} New messages arrive automatically via the email poller.  \n"
            "Use **CS Inbox** (`app_inbox.py`) to process incoming messages."
        )
        return None

    # Manual channel — show text area
    with st.form(form_key, clear_on_submit=True):
        customer_msg = st.text_area(
            "Paste customer message here",
            height=100,
            placeholder="Paste or type the customer message here…",
        )
        submitted = st.form_submit_button(
            "Analyze & Generate Draft →", type="primary"
        )
        if submitted and customer_msg.strip():
            return customer_msg.strip()

    return None


# ── Send controls (approve button) ───────────────────────────────────────────

def render_send_controls(
    ticket,
    draft: str,
    channel_config: dict,
    on_approve_callback,
    button_key: str = "send_ctrl",
) -> None:
    """
    Render the channel-appropriate approve button.
    Attempts to send the draft via the configured channel, then calls the callback.

    Parameters
    ----------
    ticket             : Ticket object (for to/subject) or None (app.py single-conv)
    draft              : the final reply text to send
    channel_config     : config["communication"]["outbound"]
    on_approve_callback: callable(sent_ok: bool) — receives True if the message
                         was actually delivered, False if send was skipped/failed
    button_key         : unique Streamlit widget key
    """
    ch = channel_config.get("type", "email")

    _BTN_LABELS = {
        "email":        "✅  Approve & Send via Email",
        "ticketing_api":"✅  Approve & Post to Ticket",
        "manual":       "✅  Mark as Sent",
    }
    btn_label = _BTN_LABELS.get(ch, "✅  Approve & Send")

    if ch == "manual":
        st.info("Send this response manually via your communication tool.")

    if st.button(btn_label, type="primary", use_container_width=True, key=button_key):
        sent_ok = _attempt_send(ticket, draft, channel_config)
        on_approve_callback(sent_ok)


# ── Internal send dispatcher ──────────────────────────────────────────────────

def _attempt_send(ticket, draft: str, channel_config: dict) -> bool:
    """
    Attempt to deliver the draft via the configured channel.
    Returns True on success, False if skipped or failed (never raises).
    """
    ch = channel_config.get("type", "email")

    if ch == "manual":
        return True  # agent handles delivery externally

    if ch in ("email", "ticketing_api"):
        to      = getattr(ticket, "customer_email", "") or ""
        subject = f"Re: {getattr(ticket, 'subject', '')}" if ticket else "Response"

        if not to:
            st.warning(
                "No recipient address — draft saved but not sent.  \n"
                "In single-conversation mode, email is sent from the Inbox."
            )
            return False

        try:
            from channels import get_channel_sender
            sender = get_channel_sender({"outbound": channel_config})
            sender.connect()
            ok = sender.send(to=to, subject=subject, body=draft)
            sender.disconnect()
            if not ok:
                st.warning("Send reported failure — draft saved to ticket.")
            return ok
        except Exception as exc:
            st.warning(f"Send skipped: {exc}. Draft saved.")
            return False

    # Unknown channel type — treat as manual
    return True
