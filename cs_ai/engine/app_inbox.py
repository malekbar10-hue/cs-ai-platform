"""
app_inbox.py — Multi-ticket inbox dashboard for the CS AI platform.

Run with:  streamlit run app_inbox.py
app.py remains untouched as a standalone single-conversation fallback.

Two modes:
  INBOX      — sortable ticket table with SLA colour coding
  CONVERSATION — full thread + AI analysis + draft review for one ticket
"""

import streamlit as st
from datetime import datetime, timezone, UTC

def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
import json
import os
from auth_guard import require_login, ticket_visible_to_current_user

from main import (
    detect_language, detect_emotion, detect_intent, detect_topic,
    find_order, build_system_prompt, client,
    detect_suggested_action, execute_action, order_database,
    search_history, format_history_context,
    get_customer_profile, update_customer_profile, format_customer_profile_context,
    get_emotion_trajectory, format_trajectory_context,
    search_knowledge_base, format_kb_context,
    select_model, CONFIG,
)
from confidence import ConfidenceScorer
from tickets import TicketManager, Ticket, TICKET_STATUSES, TICKET_PRIORITIES
from agents.orchestrator import Orchestrator as _Orchestrator
from status import check_connections as _check_connections, clear_cache as _clear_status_cache
from connector import get_action_label as _get_action_label, get_risk_label as _get_risk_label
from rbac import can
from ui_channel import (
    get_channel_label as _get_channel_label,
    render_message_header as _render_message_header,
    render_inbound_input as _render_inbound_input,
    render_send_controls as _render_send_controls,
)

_scorer = ConfidenceScorer()
_tm     = TicketManager()
_orch   = _Orchestrator()

# Pre-compute counts for page title (before set_page_config)
_all_loaded    = _tm.list_tickets()
_open_statuses = {"resolved", "closed", "sent"}
_open_count    = len([t for t in _all_loaded if t.status not in _open_statuses])
_breached_count = sum(
    1 for t in _all_loaded
    if t.status not in _open_statuses and t.sla_urgency() == "breached"
)
_sla_critical_count = sum(
    1 for t in _all_loaded
    if t.status not in _open_statuses and t.sla_urgency() == "critical"
)

# ==============================================================================
# PAGE CONFIG
# ==============================================================================

if _breached_count:
    _page_title = f"CS Agent 🔴 {_breached_count} BREACHED"
elif _sla_critical_count:
    _page_title = f"CS Agent 🟠 {_sla_critical_count} critical"
elif _open_count:
    _page_title = f"CS Inbox ({_open_count})"
else:
    _page_title = "CS Inbox"

st.set_page_config(
    page_title=_page_title,
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .stTextArea textarea { font-size: 14px; }
    .stMetric label      { font-size: 12px; }
    div[data-testid="stChatMessage"] { padding: 8px 0; }
    .ticket-row { border-bottom: 1px solid #e0e0e0; padding: 6px 0; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# AUTHENTICATION — must run before any dashboard content
# ==============================================================================

_username, _role = require_login(os.environ.get("CS_AI_COMPANY", "default"))
st.session_state["username"] = _username
st.session_state["role"]     = _role

# Connection status — cached 60s, safe on every render
_status      = _check_connections(CONFIG)
_channel_cfg = CONFIG.get("communication", {}).get("outbound", {})
_STATUS_ICONS = {"connected": "🟢", "disconnected": "🔴", "not_configured": "⚪"}

# Load company ERP mapping for action/risk labels
def _load_erp_mapping() -> dict:
    try:
        from paths import resolve_company_file
        import json as _json
        _path = resolve_company_file("erp_mapping.json")
        if os.path.isfile(_path):
            with open(_path, "r", encoding="utf-8") as _f:
                return _json.load(_f)
    except Exception:
        pass
    return {}

_ERP_MAPPING = _load_erp_mapping()

# ==============================================================================
# SESSION STATE
# ==============================================================================

_inbox_defaults = {
    "inbox_mode":           "inbox",        # "inbox" | "conversation"
    "selected_ticket_id":   None,
    "conv_state":           "input",        # "input" | "reviewing"
    "conv_analysis":        {},
    "conv_draft":           "",
    "conv_original_draft":  "",
    "conv_pending_msg":     "",
    "conv_action":          None,
    "conv_trajectory":      None,
    "filter_status":        [],
    "filter_priority":      [],
    "manual_name":          "",
    "manual_email":         "",
    "manual_subject":       "",
}
for k, v in _inbox_defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Auto-close stale tickets once per session
if "auto_close_ran" not in st.session_state:
    _auto_closed = _tm.auto_close_stale()
    st.session_state.auto_close_ran = True
    if _auto_closed:
        st.toast(f"Auto-closed {_auto_closed} stale ticket(s)", icon="🔒")

# ==============================================================================
# HELPERS
# ==============================================================================

_PRIORITY_ICON  = {"Critical": "🔴", "High": "🟠", "Normal": "🟢"}
_EMOTION_ICON   = {
    "Angry": "🔴", "Frustrated": "🟠", "Urgent": "🟡",
    "Anxious": "🔵", "Satisfied": "🟢", "Neutral": "⚪",
}
_SLA_ICON       = {"breached": "🔴", "warning": "🟡", "on_track": "🟢"}
_STATUS_LABEL   = {
    "new":              "New",
    "triaged":          "Triaged",
    "drafting":         "Drafting",
    "pending_approval": "Pending",
    "sent":             "Sent",
    "resolved":         "Resolved",
    "closed":           "Closed",
}


_URGENCY_BADGE = {
    "breached": "🔴 BREACHED",
    "critical": "🟠 <30 min",
    "high":     "🟡 <2h",
    "normal":   "🟢 OK",
}
_URGENCY_ORDER = {"breached": 0, "critical": 1, "high": 2, "normal": 3}


def _sla_countdown(ticket: Ticket) -> str:
    """Return human-readable SLA remaining time."""
    remaining = (ticket.sla_deadline - _now()).total_seconds()
    if remaining <= 0:
        mins = int(abs(remaining) / 60)
        return f"Breached {mins}m ago"
    h = int(remaining // 3600)
    m = int((remaining % 3600) // 60)
    if h >= 24:
        return f"{h//24}d {h%24}h"
    return f"{h}h {m}m"


def _open_ticket(ticket_id: str) -> None:
    st.session_state.inbox_mode         = "conversation"
    st.session_state.selected_ticket_id = ticket_id
    st.session_state.conv_state         = "input"
    st.session_state.conv_analysis      = {}
    st.session_state.conv_draft         = ""
    st.session_state.conv_action        = None
    st.session_state.conv_trajectory    = None


def _back_to_inbox() -> None:
    st.session_state.inbox_mode         = "inbox"
    st.session_state.selected_ticket_id = None
    st.session_state.conv_state         = "input"


# ==============================================================================
# SIDEBAR
# ==============================================================================

with st.sidebar:
    st.markdown(f"### {CONFIG['company']['name']}")
    st.caption("CS Inbox")
    st.divider()

    # SLA summary
    sla = _tm.sla_summary()
    c1, c2, c3 = st.columns(3)
    c1.metric("On track",  sla["on_track"],  delta=None)
    c2.metric("Warning",   sla["warning"],   delta=None)
    c3.metric("Breached",  sla["breached"],  delta=None)

    # Total open (respects role-based visibility)
    all_open = _tm.list_tickets()
    open_tickets = [
        t for t in all_open
        if t.status not in ("resolved", "closed", "sent")
        and ticket_visible_to_current_user(t)
    ]
    st.caption(f"Open tickets: **{len(open_tickets)}**")

    st.divider()

    # ── System Status ──────────────────────────────────────────────────────
    if can(_role, "view_status_panel"):
        st.subheader("System Status")
        st.markdown(f"{_STATUS_ICONS[_status.erp]}  **ERP** — {_status.erp_label}")
        st.markdown(f"{_STATUS_ICONS[_status.crm]}  **Communication** — {_status.crm_label}")
        st.markdown(f"{_STATUS_ICONS[_status.email]}  **Email** — {_status.email_label}")
        st.markdown(f"{_STATUS_ICONS[_status.ai]}  **AI Model** — {_status.ai_model}")

        if _status.erp == "disconnected":
            st.error("ERP connection lost — ERP actions disabled")
        if _status.email == "disconnected":
            st.warning("Email offline — manual mode only")

        st.caption(f"Checked: {_status.last_checked.strftime('%H:%M:%S')}")
        if can(_role, "refresh_status"):
            if st.button("↻ Refresh", key="status_refresh_inbox"):
                _clear_status_cache()
                st.rerun()

        st.divider()

    # ── Config Summary (admin only) ─────────────────────────────────────────
    if can(_role, "view_config_summary"):
        with st.expander("Config Summary", expanded=False):
            _erp_type  = CONFIG.get("erp", {}).get("type", "—")
            _ch_type   = CONFIG.get("communication", {}).get("outbound", {}).get("type", "—")
            _esc_rules = CONFIG.get("escalation", {})
            _esc_count = (
                len(_esc_rules.get("rules", []))
                if isinstance(_esc_rules, dict) else 0
            )
            _kb_count = "?"
            try:
                from paths import resolve_company_file as _rcf
                import json as _jj
                _kb_path = _rcf("knowledge_base.json")
                if os.path.isfile(_kb_path):
                    with open(_kb_path, encoding="utf-8") as _kf:
                        _kb_raw = _jj.load(_kf)
                        _kb_count = (
                            len(_kb_raw) if isinstance(_kb_raw, list)
                            else len(_kb_raw.get("entries", _kb_raw))
                            if isinstance(_kb_raw, dict) else "?"
                        )
            except Exception:
                pass
            st.caption(f"**Company:** {CONFIG.get('company', {}).get('name', '—')}")
            st.caption(f"**ERP:** {_erp_type}")
            st.caption(f"**Channel:** {_ch_type}")
            st.caption(f"**Escalation rules:** {_esc_count}")
            st.caption(f"**KB entries:** {_kb_count}")
        st.divider()

    # Filters
    st.subheader("Filters")
    st.session_state.filter_status = st.multiselect(
        "Status",
        options=TICKET_STATUSES,
        default=st.session_state.filter_status,
    )
    st.session_state.filter_priority = st.multiselect(
        "Priority",
        options=TICKET_PRIORITIES,
        default=st.session_state.filter_priority,
    )

    st.divider()

    # Manual ticket creation
    with st.expander("+ New Manual Ticket"):
        st.session_state.manual_name    = st.text_input("Customer name",  key="mn_name")
        st.session_state.manual_email   = st.text_input("Customer email", key="mn_email")
        st.session_state.manual_subject = st.text_input("Subject",        key="mn_subj")
        manual_body = st.text_area("Message", height=80, key="mn_body")
        manual_prio = st.selectbox("Priority", TICKET_PRIORITIES, key="mn_prio")

        if st.button("Create ticket", type="primary", use_container_width=True):
            if st.session_state.manual_email and manual_body.strip():
                new_t = _tm.create_ticket(
                    customer_email=st.session_state.manual_email,
                    customer_name=st.session_state.manual_name or st.session_state.manual_email,
                    subject=st.session_state.manual_subject or "(manual)",
                    channel="manual",
                    body=manual_body.strip(),
                    priority=manual_prio,
                )
                _tm.log_action(
                    ticket_id=new_t.ticket_id,
                    agent=st.session_state.get("username", "system"),
                    action="ticket_created",
                    detail=f"channel=manual priority={manual_prio}",
                )
                st.success(f"Ticket created: {new_t.ticket_id[:8]}…")
                st.rerun()
            else:
                st.warning("Email and message body are required.")

# ==============================================================================
# INBOX MODE
# ==============================================================================

if st.session_state.inbox_mode == "inbox":

    if can(_role, "manage_users"):
        _tab_inbox, _tab_users = st.tabs(["📥 Inbox", "👥 Users"])
    else:
        _tab_inbox = st.container()
        _tab_users = None

    with _tab_inbox:
        st.markdown(f"## Inbox — {CONFIG['company']['name']} · {_get_channel_label(_channel_cfg)}")

        # Build filtered ticket list
        status_filter   = st.session_state.filter_status   or None
        priority_filter = st.session_state.filter_priority or None

        # Fetch all and filter client-side (allows multi-value filter)
        all_tickets = _tm.list_tickets()

        # Role-based filter: agents only see unassigned + their own tickets
        all_tickets = [t for t in all_tickets if ticket_visible_to_current_user(t)]

        if status_filter:
            all_tickets = [t for t in all_tickets if t.status in status_filter]
        if priority_filter:
            all_tickets = [t for t in all_tickets if t.priority in priority_filter]

        # Sort by SLA urgency: breached → critical → high → normal, then by created_at
        all_tickets.sort(
            key=lambda t: (_URGENCY_ORDER.get(t.sla_urgency(), 3), t.created_at)
        )

        if not all_tickets:
            st.info("✅ All clear — no open tickets right now.")
        else:
            # Breached SLA warning banner
            _n_breached = sum(1 for t in all_tickets if t.sla_urgency() == "breached")
            if _n_breached:
                st.warning(f"⚠️ {_n_breached} ticket(s) have breached their SLA.")

            # Header row
            hcols = st.columns([0.8, 0.5, 2, 3, 1.2, 1, 1.2, 1.5, 1])
            for col, label in zip(hcols, ["SLA", "Prio", "Customer", "Subject",
                                           "Status", "Emotion", "Intent",
                                           "SLA Time", "Open"]):
                col.markdown(f"**{label}**")

            st.divider()

            for ticket in all_tickets:
                _is_noise      = (ticket.metadata or {}).get("route") == "noise"
                _is_autoclosed = (ticket.metadata or {}).get("auto_closed") is True
                sla_status     = _tm.get_sla_status(ticket)
                _urgency       = ticket.sla_urgency()
                cols = st.columns([0.8, 0.5, 2, 3, 1.2, 1, 1.2, 1.5, 1])

                if _is_noise:
                    cols[0].caption("⚪")
                    cols[1].caption("")
                    cols[2].caption(ticket.customer_name or ticket.customer_email)
                    cols[3].caption(ticket.subject[:50] + ("…" if len(ticket.subject) > 50 else ""))
                    cols[4].caption("🤖 Auto-reply — skipped")
                    cols[5].caption("")
                    cols[6].caption("—")
                    cols[7].caption("—")
                    cols[8].caption("skipped")
                elif _is_autoclosed:
                    cols[0].caption("🔒")
                    cols[1].caption(_PRIORITY_ICON.get(ticket.priority, "⚪"))
                    cols[2].caption(ticket.customer_name or ticket.customer_email)
                    cols[3].caption(ticket.subject[:50] + ("…" if len(ticket.subject) > 50 else ""))
                    cols[4].caption("🔒 Auto-closed")
                    cols[5].caption(_EMOTION_ICON.get(ticket.emotion, "⚪"))
                    cols[6].caption(ticket.intent[:12])
                    cols[7].caption("—")
                    if can(_role, "reassign_ticket") and cols[8].button(
                        "Reopen", key=f"reopen_{ticket.ticket_id}"
                    ):
                        new_meta = {k: v for k, v in (ticket.metadata or {}).items() if k != "auto_closed"}
                        _tm.update_ticket(ticket.ticket_id, status="new", metadata=new_meta)
                        _tm.log_action(
                            ticket_id=ticket.ticket_id,
                            agent=st.session_state.get("username", "system"),
                            action="ticket_reopened",
                            detail="Manually reopened after auto-close",
                        )
                        st.rerun()
                else:
                    _orig_prio      = (ticket.metadata or {}).get("original_priority")
                    _prio_overridden = _orig_prio and _orig_prio != ticket.priority
                    _prio_label     = (
                        f"{_PRIORITY_ICON.get(ticket.priority, '⚪')} ⚡"
                        if _prio_overridden
                        else _PRIORITY_ICON.get(ticket.priority, "⚪")
                    )
                    cols[0].write(_URGENCY_BADGE.get(_urgency, "🟢 OK"))
                    cols[1].write(_prio_label)
                    cols[2].write(ticket.customer_name or ticket.customer_email)
                    cols[3].write(ticket.subject[:50] + ("…" if len(ticket.subject) > 50 else ""))
                    cols[4].write(_STATUS_LABEL.get(ticket.status, ticket.status))
                    cols[5].write(_EMOTION_ICON.get(ticket.emotion, "⚪"))
                    cols[6].write(ticket.intent[:12])
                    cols[7].write(_sla_countdown(ticket))

                    if cols[8].button("Open", key=f"open_{ticket.ticket_id}"):
                        _open_ticket(ticket.ticket_id)
                        st.rerun()

    if _tab_users is not None:
        with _tab_users:
            _render_admin_users_tab()

# ==============================================================================
# CONVERSATION MODE
# ==============================================================================

elif st.session_state.inbox_mode == "conversation":

    ticket = _tm.get_ticket(st.session_state.selected_ticket_id)
    if ticket is None:
        st.error("Ticket not found.")
        _back_to_inbox()
        st.rerun()

    # ── Ticket header ───────────────────────────────────────────────────────
    sla_status = _tm.get_sla_status(ticket)

    hcol1, hcol2, hcol3 = st.columns([0.8, 5, 1.5])
    with hcol1:
        if st.button("← Inbox"):
            _back_to_inbox()
            st.rerun()
    with hcol2:
        st.markdown(
            f"### {_PRIORITY_ICON.get(ticket.priority, '')} "
            f"{ticket.subject}  "
            f"<span style='font-size:14px;color:#888;'>"
            f"— {ticket.customer_name} &lt;{ticket.customer_email}&gt;"
            f"</span>",
            unsafe_allow_html=True,
        )
    with hcol3:
        st.markdown(
            f"{_SLA_ICON[sla_status]} **{_sla_countdown(ticket)}** — "
            f"`{_STATUS_LABEL.get(ticket.status, ticket.status)}`"
        )

    # ── Supervisor / admin: assign ticket ───────────────────────────────────
    if can(_role, "reassign_ticket"):
        try:
            import yaml as _yaml
            _cdir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "cs_ai", "companies", os.environ.get("CS_AI_COMPANY", "default"),
            )
            _upth = os.path.join(_cdir, "users.yaml")
            if os.path.isfile(_upth):
                with open(_upth) as _yf:
                    _ucfg = _yaml.safe_load(_yf) or {}
                _all_users = list(_ucfg.get("credentials", {}).get("usernames", {}).keys())
                _agents = [u for u in _all_users
                           if _ucfg["credentials"]["usernames"][u].get("role") == "agent"]
                if _agents:
                    _cur_assign = (ticket.metadata or {}).get("assigned_to", "")
                    _options    = ["(unassigned)"] + _agents
                    _default_i  = _options.index(_cur_assign) if _cur_assign in _options else 0
                    _acol1, _acol2 = st.columns([3, 1])
                    with _acol1:
                        _sel = st.selectbox(
                            "Assign to agent",
                            options=_options,
                            index=_default_i,
                            key=f"assign_{ticket.ticket_id}",
                            label_visibility="collapsed",
                        )
                    with _acol2:
                        if st.button("Assign", key=f"do_assign_{ticket.ticket_id}"):
                            new_meta  = dict(ticket.metadata or {})
                            old_agent = new_meta.get("assigned_to", "")
                            new_agent = "" if _sel == "(unassigned)" else _sel
                            new_meta["assigned_to"] = new_agent
                            _tm.update_ticket(ticket.ticket_id, metadata=new_meta)
                            _tm.log_action(
                                ticket_id=ticket.ticket_id,
                                agent=st.session_state.get("username", "system"),
                                action="ticket_reassigned",
                                before_value=old_agent or "(unassigned)",
                                after_value=new_agent or "(unassigned)",
                            )
                            st.success(f"Assigned to {_sel}")
                            st.rerun()
        except Exception:
            pass

    # ── Supervisor / admin: priority override ───────────────────────────────
    if can(_role, "reassign_ticket"):
        _prios     = ["Normal", "High", "Critical"]
        _pcol1, _pcol2 = st.columns([3, 1])
        with _pcol1:
            _new_prio = st.selectbox(
                "Priority override",
                _prios,
                index=_prios.index(ticket.priority) if ticket.priority in _prios else 0,
                key=f"prio_sel_{ticket.ticket_id}",
                label_visibility="collapsed",
            )
        with _pcol2:
            if _new_prio != ticket.priority:
                if st.button("Apply priority", key=f"prio_apply_{ticket.ticket_id}"):
                    from datetime import timedelta as _td
                    _sla_hours   = CONFIG.get("sla", {}).get(_new_prio, {}).get("response_hours", 24)
                    _new_sla     = ticket.created_at + _td(hours=_sla_hours)
                    _old_prio    = ticket.priority
                    _tm.update_ticket(
                        ticket.ticket_id,
                        priority=_new_prio,
                        sla_deadline=_new_sla,
                    )
                    _tm.log_action(
                        ticket_id=ticket.ticket_id,
                        agent=st.session_state.get("username", "system"),
                        action="priority_override",
                        before_value=_old_prio,
                        after_value=_new_prio,
                    )
                    st.success(f"Priority updated to {_new_prio}")
                    st.rerun()

    st.divider()

    # ── Main layout ─────────────────────────────────────────────────────────
    col_left, col_right = st.columns([3, 2])

    # ── LEFT: message thread ────────────────────────────────────────────────
    with col_left:
        st.subheader("Thread")

        for i, msg in enumerate(ticket.messages):
            role = msg.get("role", "customer")
            if role == "customer":
                with st.chat_message("user"):
                    _render_message_header(msg, _channel_cfg,
                                           message_index=i, ticket=ticket)
                    st.write(msg.get("content", ""))
            else:
                with st.chat_message("assistant", avatar="🤖"):
                    _render_message_header(msg, _channel_cfg,
                                           message_index=i, ticket=ticket)
                    st.write(msg.get("content", ""))

        # Input area — shown only in "input" state
        if st.session_state.conv_state == "input":
            st.divider()
            customer_msg = _render_inbound_input(
                _channel_cfg,
                form_key=f"inbox_inbound_{ticket.ticket_id}",
            )
            if customer_msg:
                with st.status("Analyzing message...", expanded=False) as _conv_status:
                    _conv_status.update(label="Analyzing message...")
                    _conv_status.update(label="Generating response...")
                    analysis = _analyze_ticket(ticket, customer_msg)
                    _conv_status.update(label="Reviewing draft...", state="complete")

                if analysis.get("route") == "noise":
                    _noise_label = {
                        "auto_reply":       "Auto-reply",
                        "out_of_office":    "Out-of-office",
                        "delivery_failure": "Delivery failure",
                        "spam":             "Spam",
                    }.get(analysis.get("noise_type", ""), "Noise")
                    st.info(
                        f"🤖 {_noise_label} detected — skipped. "
                        f"No AI response generated. "
                        f"({analysis.get('noise_reason', '')})"
                    )
                else:
                    st.session_state.conv_analysis       = analysis
                    st.session_state.conv_draft          = analysis["draft"]
                    st.session_state.conv_original_draft = analysis["draft"]
                    st.session_state.conv_action         = analysis["action"]
                    st.session_state.conv_pending_msg    = customer_msg
                    st.session_state.conv_trajectory     = analysis.get("trajectory")
                    st.session_state.conv_state          = "reviewing"
                    _tm.update_ticket(ticket.ticket_id, status="drafting")
                    _tm.log_action(
                        ticket_id=ticket.ticket_id,
                        agent=st.session_state.get("username", "system"),
                        action="draft_generated",
                        detail=(
                            f"intent={analysis.get('intent','')} "
                            f"emotion={analysis.get('emotion','')} "
                            f"model={analysis.get('model_used','')}"
                        ),
                    )
                    st.rerun()

    # ── RIGHT: analysis panel ───────────────────────────────────────────────
    with col_right:
        st.subheader("Analysis")

        a = st.session_state.conv_analysis
        if a:
            icon = _EMOTION_ICON.get(a.get("emotion", "Neutral"), "⚪")
            c1, c2 = st.columns(2)
            c1.metric("Emotion",   f"{icon} {a.get('emotion','')}")
            c1.metric("Intent",    a.get("intent", ""))
            c2.metric("Intensity", a.get("intensity", ""))
            c2.metric("Topic",     a.get("topic", ""))
            st.metric("Language",  a.get("language", ""))
            if a.get("lang_confidence", 1.0) < 0.65:
                st.warning("⚠ Language uncertain — verify the response is in the right language")

            if a.get("model_used"):
                st.caption(f"Model: `{a['model_used']}`")
            if a.get("secondary"):
                st.caption(f"Secondary: {', '.join(a['secondary'])}")

            # Confidence bar
            conf = a.get("confidence")
            if conf:
                overall = conf["overall"]
                pct     = int(overall * 100)
                icon_c  = "🟢" if overall >= 0.85 else "🟡" if overall >= 0.50 else "🔴"
                rec_labels = {
                    "auto_send":         "Auto-send eligible",
                    "human_review":      "Human review recommended",
                    "supervisor_review": "Supervisor review required",
                }
                st.divider()
                st.markdown(
                    f"**Confidence:** {icon_c} **{pct}%** — "
                    f"{rec_labels.get(conf['recommendation'], conf['recommendation'])}"
                )
                with st.expander("Confidence breakdown"):
                    factor_labels = {
                        "nlp":               "NLP detection",
                        "emotion_risk":      "Emotion risk",
                        "customer_risk":     "Customer risk",
                        "action_risk":       "ERP action risk",
                        "intent_complexity": "Intent complexity",
                    }
                    for k, v in conf["factors"].items():
                        lbl  = factor_labels.get(k, k)
                        ico2 = "🟢" if v >= 0.65 else "🟡" if v >= 0.40 else "🔴"
                        st.caption(f"{ico2} {lbl}: {int(v*100)}%")
                        st.progress(v)

            # ── QA review result ───────────────────────────────────────
            qa_result = a.get("qa_result")
            qa_flags  = a.get("qa_flags", [])
            if qa_result:
                st.divider()
                if qa_result == "pass" and not qa_flags:
                    st.caption("QA: passed")
                else:
                    qa_icon = "🟢" if qa_result == "pass" else "🟡"
                    st.markdown(f"**QA:** {qa_icon} {qa_result}")
                    if qa_flags:
                        with st.expander("QA flags", expanded=qa_result == "needs_revision"):
                            for flag in qa_flags:
                                st.caption(f"• {flag}")

            # ── Escalation preview ─────────────────────────────────────
            esc_preview = a.get("escalation_preview", [])
            if esc_preview:
                st.divider()
                with st.expander("⚠ Escalation rules matched", expanded=True):
                    for _er in esc_preview:
                        st.warning(f"**{_er['rule_name']}** → {_er['tier']} | {_er['reason']}")

            # ── Pipeline details ───────────────────────────────────────
            timings = a.get("pipeline_timings")
            if timings:
                with st.expander("⚙ Pipeline details", expanded=False):
                    route = a.get("route", "")
                    if route:
                        route_icons = {
                            "supervisor": "🔴", "priority": "🟠",
                            "standard": "🟡", "auto": "🟢",
                        }
                        st.caption(f"Route: {route_icons.get(route, '')} {route}")
                    retries = a.get("retry_count", 0)
                    if retries:
                        st.caption(f"QA retries: {retries}")
                    if a.get("model_used"):
                        st.caption(f"Model used: {a['model_used']}")
                    if a.get("qa_result"):
                        st.caption(f"QA result: {a['qa_result']}")
                    if a.get("qa_flags"):
                        st.caption(f"QA flags: {', '.join(a['qa_flags'])}")
                    st.divider()
                    for step, secs in timings.items():
                        if step == "total":
                            continue
                        st.caption(f"  {step}: {secs:.2f}s")
                    st.caption(f"  **Total: {timings.get('total', sum(v for k,v in timings.items() if k != 'total')):.2f}s**")

            # NLP per-signal confidence
            emo_c = a.get("emo_conf", 0)
            int_c = a.get("int_conf", 0)
            top_c = a.get("top_conf", 0)
            if emo_c or int_c or top_c:
                def _cl(v):
                    return f"🟢 {int(v*100)}%" if v >= 0.50 else f"🟡 {int(v*100)}%" if v >= 0.35 else f"🔴 {int(v*100)}%"
                st.caption(
                    f"NLP — emotion: {_cl(emo_c)} · intent: {_cl(int_c)} · topic: {_cl(top_c)}"
                )
        else:
            st.info("Analysis will appear after you submit a message.")

        # Order info (from ticket)
        if ticket.order_id:
            order = order_database.get(ticket.order_id, {})
            st.divider()
            p_icon = _PRIORITY_ICON.get(ticket.priority, "⚪")
            st.markdown(f"**Order** `{ticket.order_id}` — {p_icon} **{ticket.priority}**")
            if order:
                st.code(json.dumps(order, indent=2)[:400], language=None)

        # Emotional trajectory
        traj = st.session_state.conv_trajectory
        if traj:
            st.divider()
            t_icons = {"Escalating": "🔴", "Stable": "🟡", "Improving": "🟢"}
            st.markdown(f"**Trajectory** {t_icons.get(traj['trend'], '')} {traj['trend']}")
            st.caption(" → ".join(s["emotion"] for s in traj["sessions"]))
            if traj.get("alert"):
                st.warning("Client escalating — maximum empathy required")

        # Customer profile
        if ticket.customer_name:
            profile = get_customer_profile(ticket.customer_name)
            if profile:
                st.divider()
                st.markdown(f"**Profile** — {ticket.customer_name}")
                st.caption(
                    f"Interactions: {profile.get('total_interactions', 0)} | "
                    f"Resolved: {profile.get('resolved_cases', 0)} | "
                    f"Dominant: {profile.get('dominant_emotion', '?')}"
                )

    # ── DRAFT REVIEW PANEL ──────────────────────────────────────────────────
    if st.session_state.conv_state == "reviewing":
        st.divider()
        st.subheader("AI Draft — Awaiting Approval")

        a = st.session_state.conv_analysis
        st.caption(
            f"Emotion: **{a.get('emotion','')}** ({a.get('intensity','')}) · "
            f"Intent: **{a.get('intent','')}** · Topic: **{a.get('topic','')}**"
        )
        _total_s = (a.get("pipeline_timings") or {}).get("total")
        _gen_caption = (
            f"Generated in {_total_s:.1f}s · {a['model_used']}"
            if _total_s and a.get("model_used")
            else (f"Model: {a['model_used']}" if a.get("model_used") else "")
        )
        if _gen_caption:
            st.caption(_gen_caption)

        _dw  = a.get("draft_warnings", [])
        _aif = a.get("draft_ai_flags", [])
        if _dw or _aif:
            st.warning("⚠ Draft quality issues detected")
            for _w in _dw:
                st.caption(f"• {_w}")
            for _flag in _aif:
                _fc1, _fc2 = st.columns([6, 1])
                _fc1.caption(f"• Missing: **{_flag}**")
                _fix_key = f"fix_{ticket.ticket_id}_{_flag}"
                if _fc2.button("✏ Fix", key=_fix_key, help=f"Ask AI to add: {_flag}"):
                    try:
                        from draft_fix import fix_draft_element
                        _current = st.session_state.get("conv_draft_editor", st.session_state.conv_draft)
                        _fixed   = fix_draft_element(_current, _flag, a)
                        st.session_state.conv_draft = _fixed
                        a.get("draft_ai_flags", []).remove(_flag)
                    except Exception as _e:
                        st.error(f"Fix failed: {_e}")
                    st.rerun()

        edited = st.text_area(
            "Review and edit before sending:",
            value=st.session_state.conv_draft,
            height=320,
            key="conv_draft_editor",
        )

        _wc = len(edited.split())
        _cc = len(edited)
        _wc_color = (
            "green" if 50 <= _wc <= 400
            else "orange" if _wc < 50 or _wc <= 600
            else "red"
        )
        _wc_col, _copy_col = st.columns([5, 1])
        _wc_col.markdown(
            f"<span style='color:{_wc_color};font-size:12px'>{_wc} words · {_cc} characters</span>",
            unsafe_allow_html=True,
        )
        with _copy_col:
            with st.popover("📋", help="Copy draft"):
                st.code(edited, language=None)

        col_approve, col_reject, col_info = st.columns([3, 2, 1])

        with col_approve:
            def _on_approve_inbox(sent_ok: bool) -> None:
                _handle_approve(ticket, edited.strip(), a, sent_ok=sent_ok)
                st.rerun()

            _render_send_controls(
                ticket, edited.strip(), _channel_cfg,
                _on_approve_inbox,
                button_key=f"inbox_approve_{ticket.ticket_id}",
            )
            st.caption("Tip: you can edit the draft above before approving")

        with col_reject:
            if st.button("❌  Reject", use_container_width=True):
                _handle_reject(ticket, a)
                st.rerun()

        with col_info:
            st.caption(f"Msgs: {len(ticket.messages)}")

    # ── ERP ACTION PANEL ────────────────────────────────────────────────────
    if st.session_state.conv_state == "reviewing" and st.session_state.conv_action:
        action = st.session_state.conv_action
        st.divider()

        if _status.erp in ("disconnected", "not_configured"):
            st.caption("⚪ ERP actions unavailable — ERP not configured")
        else:
            _risk_icons   = {"Low": "🟢", "Medium": "🟡", "High": "🔴"}
            _risk_icon    = _risk_icons.get(action["risk"], "⚪")
            _action_label = _get_action_label(action["type"], _ERP_MAPPING)
            _risk_label   = _get_risk_label(action["risk"], _ERP_MAPPING)

            st.subheader("⚡ Suggested ERP Action")
            c_info, c_btn = st.columns([3, 2])

            with c_info:
                st.markdown(f"**{_action_label}**")
                st.caption(action.get("description", ""))
                st.caption(f"Risk: {_risk_icon} {_risk_label}")
                extra_input = None
                if action.get("requires_input"):
                    extra_input = st.text_input(action["input_label"], placeholder="e.g. April 20")

            with c_btn:
                st.write("")
                _erp_perm = f"erp_{action['risk'].lower()}_risk"
                if can(_role, _erp_perm):
                    if st.button("✅ Execute action", type="primary", use_container_width=True):
                        changes = action["changes"].copy()
                        if action.get("requires_input") and extra_input:
                            for key in changes:
                                if changes[key] is None:
                                    changes[key] = extra_input

                        success = execute_action(ticket.order_id, changes)
                        if success:
                            erp_entry = {
                                "timestamp": _now().isoformat(),
                                "ticket_id": ticket.ticket_id,
                                "order_id":  ticket.order_id,
                                "action":    action["type"],
                                "label":     _action_label,
                                "changes":   changes,
                                "risk":      action["risk"],
                            }
                            _tm.add_erp_action(ticket.ticket_id, erp_entry)
                            _tm.log_action(
                                ticket_id=ticket.ticket_id,
                                agent=st.session_state.get("username", "system"),
                                action="erp_action_executed",
                                detail=f"{action['type']} order_id={ticket.order_id}",
                            )
                            st.session_state.conv_action = None
                            st.success(f"Action executed: {_action_label}")
                            st.toast(f"ERP: {_action_label} ✅", icon="⚡")
                            st.rerun()
                        else:
                            st.error("ERP action failed.")
                else:
                    st.caption(f"🔒 {action['risk']}-risk actions require supervisor approval")

                if st.button("❌ Ignore", use_container_width=True):
                    _tm.log_action(
                        ticket_id=ticket.ticket_id,
                        agent=st.session_state.get("username", "system"),
                        action="erp_action_rejected",
                        detail=action.get("type", ""),
                    )
                    st.session_state.conv_action = None
                    st.rerun()

    # ── AUDIT TRAIL (supervisor / admin only) ────────────────────────────────
    if can(_role, "view_audit_trail"):
        st.divider()
        st.subheader("Audit Trail")

        trail = _tm.get_audit_trail(ticket.ticket_id)
        if not trail:
            st.caption("No audit events yet for this ticket.")
        else:
            import pandas as _pd

            _df = _pd.DataFrame(trail)[
                ["timestamp", "agent", "action", "detail", "before_value", "after_value"]
            ]
            _df.columns = ["Timestamp", "Agent", "Action", "Detail", "Before", "After"]
            st.dataframe(_df, use_container_width=True, hide_index=True)

            _export_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "cs_ai", "data",
                os.environ.get("CS_AI_COMPANY", "default"),
                f"audit_{ticket.ticket_id[:8]}.csv",
            )
            if can(_role, "export_audit_csv"):
                if st.button("Export CSV", key=f"audit_export_{ticket.ticket_id}"):
                    try:
                        _tm.export_audit_csv(_export_path, days=365)
                        st.success(f"Exported to {_export_path}")
                    except Exception as _e:
                        st.error(f"Export failed: {_e}")

    # ── INTERNAL NOTES ───────────────────────────────────────────────────────
    st.divider()
    st.subheader("🔒 Internal Notes")
    st.caption("Internal — not sent to customer")

    _notes = _tm.get_notes(ticket.ticket_id)
    if _notes:
        for _n in _notes:
            _ts = _n.get("timestamp", "")[:16].replace("T", " ")
            st.markdown(
                f"<div style='background:#fffde7;border-left:3px solid #f9a825;"
                f"padding:8px 12px;margin-bottom:6px;border-radius:4px;'>"
                f"<small><b>{_n.get('agent','?')}</b> · {_ts}</small><br>"
                f"{_n.get('text','')}</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No internal notes yet.")

    _note_col, _btn_col = st.columns([5, 1])
    _new_note = _note_col.text_input(
        "Add a note",
        placeholder="Visible to team only…",
        label_visibility="collapsed",
        key=f"note_input_{ticket.ticket_id}",
    )
    if _btn_col.button("Add", key=f"note_add_{ticket.ticket_id}", use_container_width=True):
        if _new_note.strip():
            _agent_name = st.session_state.get("username", "agent")
            _tm.add_note(ticket.ticket_id, _agent_name, _new_note.strip())
            _tm.log_action(
                ticket_id=ticket.ticket_id,
                agent=_agent_name,
                action="note_added",
                detail=_new_note.strip()[:100],
            )
            st.rerun()
        else:
            st.warning("Note cannot be empty.")


# ==============================================================================
# ADMIN: USER MANAGEMENT TAB
# ==============================================================================

def _render_admin_users_tab() -> None:
    """Admin-only: list, add, remove, and reset passwords for users in users.yaml."""
    import yaml as _yaml
    import bcrypt as _bcrypt

    _cdir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "cs_ai", "companies", os.environ.get("CS_AI_COMPANY", "default"),
    )
    _users_path = os.path.join(_cdir, "users.yaml")

    if not os.path.isfile(_users_path):
        st.error("users.yaml not found for this company.")
        return

    def _load_ucfg():
        with open(_users_path, "r", encoding="utf-8") as _f:
            return _yaml.safe_load(_f) or {}

    def _save_ucfg(cfg):
        with open(_users_path, "w", encoding="utf-8") as _f:
            _yaml.dump(cfg, _f, default_flow_style=False, allow_unicode=True)

    st.subheader("User Management")
    cfg           = _load_ucfg()
    usernames_cfg = cfg.get("credentials", {}).get("usernames", {})

    # ── Current users table ──────────────────────────────────────────────
    if usernames_cfg:
        import pandas as _pd
        _rows = [
            {
                "Username": u,
                "Name":     d.get("name", ""),
                "Email":    d.get("email", ""),
                "Role":     d.get("role", "agent"),
            }
            for u, d in usernames_cfg.items()
        ]
        st.dataframe(_pd.DataFrame(_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No users configured yet.")

    st.divider()
    col_add, col_rm = st.columns(2)

    # ── Add user ─────────────────────────────────────────────────────────
    with col_add:
        st.subheader("Add user")
        with st.form("admin_add_user"):
            _new_name  = st.text_input("Full name")
            _new_uname = st.text_input("Username (login)")
            _new_email = st.text_input("Email")
            _new_role  = st.selectbox("Role", ["agent", "supervisor", "admin"])
            _new_pw    = st.text_input("Temporary password", type="password")
            if st.form_submit_button("Add", type="primary"):
                if not _new_uname or not _new_pw:
                    st.error("Username and password are required.")
                elif _new_uname in usernames_cfg:
                    st.error(f"User '{_new_uname}' already exists.")
                else:
                    _hashed = _bcrypt.hashpw(_new_pw.encode(), _bcrypt.gensalt()).decode()
                    cfg.setdefault("credentials", {}).setdefault("usernames", {})[_new_uname] = {
                        "name":     _new_name,
                        "email":    _new_email,
                        "role":     _new_role,
                        "password": _hashed,
                    }
                    _save_ucfg(cfg)
                    st.success(f"User '{_new_uname}' added.")
                    st.rerun()

    # ── Remove / Reset password ───────────────────────────────────────────
    with col_rm:
        st.subheader("Remove / Reset password")
        if usernames_cfg:
            _target = st.selectbox(
                "Select user",
                list(usernames_cfg.keys()),
                key="admin_target_user",
            )
            _rc1, _rc2 = st.columns(2)

            with _rc1:
                if st.button("Remove user", use_container_width=True):
                    if _target == st.session_state.get("username"):
                        st.error("You cannot remove your own account.")
                    else:
                        del cfg["credentials"]["usernames"][_target]
                        _save_ucfg(cfg)
                        st.success(f"User '{_target}' removed.")
                        st.rerun()

            with _rc2:
                with st.form("admin_reset_pw"):
                    _reset_pw = st.text_input("New password", type="password")
                    if st.form_submit_button("Reset password"):
                        if not _reset_pw:
                            st.error("Password cannot be empty.")
                        else:
                            _hashed = _bcrypt.hashpw(_reset_pw.encode(), _bcrypt.gensalt()).decode()
                            cfg["credentials"]["usernames"][_target]["password"] = _hashed
                            _save_ucfg(cfg)
                            st.success(f"Password reset for '{_target}'.")
                            st.rerun()
        else:
            st.info("No users to manage.")


# ==============================================================================
# CORE ANALYSIS FUNCTION (ticket-aware version of app.py's analyze_and_generate)
# ==============================================================================

def _analyze_ticket(ticket: Ticket, user_input: str) -> dict:
    """
    Run the full agent pipeline (Triage → Response → QA) for one ticket turn.
    Returns the enriched context dict — a superset of the old analysis dict.
    """
    try:
        ctx = _orch.run({
            "user_input":           user_input,
            "ticket":               ticket,
            "session_id":           ticket.ticket_id,
            "conversation_history": [],          # not used; ticket.messages is used instead
            "session_order_id":     ticket.order_id,
            "session_order_info":   "",
            "session_priority":     ticket.priority,
        })

        # Noise detected — store flag in metadata and return immediately
        if ctx.get("route") == "noise":
            _tm.update_ticket(
                ticket.ticket_id,
                status="closed",
                metadata={
                    **(ticket.metadata or {}),
                    "route":        "noise",
                    "noise_type":   ctx.get("noise_type", ""),
                    "noise_reason": ctx.get("noise_reason", ""),
                },
            )
            _tm.log_action(
                ticket_id=ticket.ticket_id,
                agent="system",
                action="noise_detected",
                detail=f"type={ctx.get('noise_type','')} reason={ctx.get('noise_reason','')}",
            )
            return ctx

        # Persist new order discovery to ticket DB
        new_oid = ctx.get("_new_order_id")
        if new_oid and new_oid != ticket.order_id:
            _tm.update_ticket(ticket.ticket_id,
                              order_id=new_oid,
                              priority=ctx.get("_new_priority", ticket.priority))

        # Update ticket NLP fields
        _tm.update_ticket(
            ticket.ticket_id,
            emotion=ctx.get("emotion", ticket.emotion),
            intent=ctx.get("intent", ticket.intent),
            confidence=ctx.get("confidence", {}).get("overall", ticket.confidence),
            status="pending_approval",
        )

        return ctx

    except Exception:
        import traceback
        traceback.print_exc()
        return _analyze_ticket_legacy(ticket, user_input)


def _analyze_ticket_legacy(ticket: Ticket, user_input: str) -> dict:
    """Legacy fallback — direct NLP + AI call without agent pipeline."""
    text = user_input.lower()

    language, lang_confidence, lang_mixed    = detect_language(text)
    emotion, intensity, all_scores, emo_conf = detect_emotion(text)
    top_score = max(all_scores.values()) if all_scores else 0
    secondary = [e for e, s in all_scores.items() if s >= top_score * 0.30 and e != emotion]
    intent, int_conf = detect_intent(text)
    topic,  top_conf = detect_topic(text)

    order_info, priority, order_id = find_order(user_input)
    if not order_id and ticket.order_id:
        order_id   = ticket.order_id
        order      = order_database.get(order_id, {})
        priority   = order.get("priority", ticket.priority)
        order_info = json.dumps(order, indent=2) if order else ""

    if order_id and order_id != ticket.order_id:
        _tm.update_ticket(ticket.ticket_id, order_id=order_id, priority=priority)
        ticket = _tm.get_ticket(ticket.ticket_id)

    customer_name = ticket.customer_name

    profile_context    = format_customer_profile_context(customer_name)
    trajectory         = get_emotion_trajectory(customer_name)
    trajectory_context = format_trajectory_context(trajectory, customer_name)
    kb_entries         = search_knowledge_base(intent, topic, text)
    kb_context         = format_kb_context(kb_entries)
    history            = search_history(
        order_id=order_id, customer_name=customer_name,
        intent=intent, topic=topic, current_session_id=ticket.ticket_id,
    )
    history_context = format_history_context(history)

    system_prompt = build_system_prompt(
        language, emotion, intensity, secondary, intent, topic,
        order_info, priority,
        history_context=history_context,
        profile_context=profile_context,
        trajectory_context=trajectory_context,
        kb_context=kb_context,
    )

    action = detect_suggested_action(order_id, intent, emotion, intensity, text=text)

    profile    = get_customer_profile(customer_name) if customer_name else None
    confidence = _scorer.score(
        nlp_confidence=emo_conf, emotion=emotion, intensity=intensity,
        intent=intent, profile=profile, trajectory=trajectory, action=action,
    )
    model_cfg = select_model(emotion, intensity, intent,
                             confidence_score=confidence["overall"])

    conv_history = [
        {"role": "user" if m["role"] == "customer" else "assistant",
         "content": m["content"]}
        for m in ticket.messages[-10:]
    ]
    messages = (
        [{"role": "system", "content": system_prompt}]
        + conv_history
        + [{"role": "user", "content": user_input}]
    )

    response = client.chat.completions.create(
        model=model_cfg["model"], messages=messages,
        max_tokens=model_cfg["max_tokens"], temperature=model_cfg["temperature"],
    )
    draft = response.choices[0].message.content

    _tm.update_ticket(ticket.ticket_id, emotion=emotion, intent=intent,
                      confidence=confidence["overall"], status="pending_approval")

    return {
        "language": language, "lang_confidence": lang_confidence, "lang_mixed": lang_mixed,
        "emotion": emotion, "intensity": intensity,
        "secondary": secondary, "intent": intent, "topic": topic,
        "draft": draft, "action": action,
        "emo_conf": emo_conf, "int_conf": int_conf, "top_conf": top_conf,
        "confidence": confidence, "model_used": model_cfg["model"],
        "order_id": order_id, "priority": priority, "trajectory": trajectory,
    }


def _handle_approve(
    ticket: Ticket,
    final_reply: str,
    analysis: dict,
    sent_ok: bool = False,
) -> None:
    """
    Persist approved reply and update ticket state.
    send_ok is provided by render_send_controls — this function no longer sends.
    """
    user_msg   = st.session_state.conv_pending_msg
    action_str = (
        "modified"
        if final_reply != st.session_state.conv_original_draft.strip()
        else "approved"
    )
    now    = _now().isoformat()
    _agent = st.session_state.get("username", "system")

    # Audit: draft decision
    if action_str == "modified":
        _tm.log_action(
            ticket_id=ticket.ticket_id,
            agent=_agent,
            action="draft_modified",
            before_value=st.session_state.conv_original_draft,
            after_value=final_reply,
        )
    else:
        _tm.log_action(
            ticket_id=ticket.ticket_id,
            agent=_agent,
            action="draft_approved",
        )

    if sent_ok:
        _tm.log_action(
            ticket_id=ticket.ticket_id,
            agent=_agent,
            action="response_sent",
            detail=f"to={ticket.customer_email}",
        )

    # Add both messages to ticket thread
    _tm.add_message(ticket.ticket_id, {"role": "customer",   "content": user_msg,    "timestamp": now})
    _tm.add_message(ticket.ticket_id, {"role": "assistant",  "content": final_reply, "timestamp": now})

    # Update ticket status
    new_status = "sent" if sent_ok else "pending_approval"
    _tm.update_ticket(
        ticket.ticket_id,
        status=new_status,
        emotion=analysis.get("emotion", ticket.emotion),
        intent=analysis.get("intent", ticket.intent),
        confidence=analysis.get("confidence", {}).get("overall", ticket.confidence),
    )

    # Update customer profile
    c_name = ticket.customer_name
    if c_name:
        update_customer_profile(
            c_name,
            analysis.get("language", "English"),
            analysis.get("emotion", "Neutral"),
            analysis.get("intent", ""),
            analysis.get("topic", ""),
            resolved=True,
        )

    # Reset conversation state
    st.session_state.conv_state  = "input"
    st.session_state.conv_draft  = ""
    st.session_state.conv_action = None

    for _esc in analysis.get("escalation_preview", []):
        st.toast(f"Escalation triggered: {_esc['rule_name']}", icon="📢")

    # KB usage — mark rows for this ticket as draft approved
    _tm.mark_kb_approved(ticket.ticket_id)

    # Lesson effectiveness tracking
    _lesson_ids = analysis.get("applied_lesson_ids", [])
    if _lesson_ids:
        try:
            from learning import get_analyzer as _ga
            if action_str == "approved":
                _ga().mark_effective(_lesson_ids)
            else:
                _ga().mark_applied(_lesson_ids)
        except Exception:
            pass

    if sent_ok:
        st.toast("Response sent ✅", icon="✅")
    else:
        st.info("Draft saved. Configure the outbound channel in config.json to enable sending.")


def _handle_reject(ticket: Ticket, analysis: dict) -> None:
    """Discard draft, keep ticket open."""
    _tm.log_action(
        ticket_id=ticket.ticket_id,
        agent=st.session_state.get("username", "system"),
        action="draft_rejected",
    )
    try:
        from learning import get_analyzer as _ga
        _ga().mark_applied(analysis.get("applied_lesson_ids", []))
    except Exception:
        pass
    _tm.update_ticket(ticket.ticket_id, status="triaged")
    st.session_state.conv_state  = "input"
    st.session_state.conv_draft  = ""
    st.session_state.conv_action = None
    st.warning("Draft rejected.")
