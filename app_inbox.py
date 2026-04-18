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

_scorer = ConfidenceScorer()
_tm     = TicketManager()

# ==============================================================================
# PAGE CONFIG
# ==============================================================================

st.set_page_config(
    page_title="CS Inbox",
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

    # Total open
    all_open = _tm.list_tickets()
    open_tickets = [t for t in all_open
                    if t.status not in ("resolved", "closed", "sent")]
    st.caption(f"Open tickets: **{len(open_tickets)}**")

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
                st.success(f"Ticket created: {new_t.ticket_id[:8]}…")
                st.rerun()
            else:
                st.warning("Email and message body are required.")

# ==============================================================================
# INBOX MODE
# ==============================================================================

if st.session_state.inbox_mode == "inbox":

    st.markdown(f"## Inbox — {CONFIG['company']['name']}")

    # Build filtered ticket list
    status_filter   = st.session_state.filter_status   or None
    priority_filter = st.session_state.filter_priority or None

    # Fetch all and filter client-side (allows multi-value filter)
    all_tickets = _tm.list_tickets()
    if status_filter:
        all_tickets = [t for t in all_tickets if t.status in status_filter]
    if priority_filter:
        all_tickets = [t for t in all_tickets if t.priority in priority_filter]

    # Sort order: breached first, then warning, then on_track; within group by created_at desc
    _sla_order = {"breached": 0, "warning": 1, "on_track": 2}
    all_tickets.sort(key=lambda t: (_sla_order[_tm.get_sla_status(t)], t.created_at))

    if not all_tickets:
        st.info("No tickets found. Use 'New Manual Ticket' in the sidebar to create one, or start the email poller.")
    else:
        # Header row
        hcols = st.columns([0.5, 0.5, 2, 3, 1.2, 1, 1.2, 1.5, 1])
        for col, label in zip(hcols, ["SLA", "Prio", "Customer", "Subject",
                                       "Status", "Emotion", "Intent",
                                       "SLA Time", "Open"]):
            col.markdown(f"**{label}**")

        st.divider()

        for ticket in all_tickets:
            sla_status = _tm.get_sla_status(ticket)
            cols = st.columns([0.5, 0.5, 2, 3, 1.2, 1, 1.2, 1.5, 1])

            cols[0].write(_SLA_ICON[sla_status])
            cols[1].write(_PRIORITY_ICON.get(ticket.priority, "⚪"))
            cols[2].write(ticket.customer_name or ticket.customer_email)
            cols[3].write(ticket.subject[:50] + ("…" if len(ticket.subject) > 50 else ""))
            cols[4].write(_STATUS_LABEL.get(ticket.status, ticket.status))
            cols[5].write(_EMOTION_ICON.get(ticket.emotion, "⚪"))
            cols[6].write(ticket.intent[:12])
            cols[7].write(_sla_countdown(ticket))

            if cols[8].button("Open", key=f"open_{ticket.ticket_id}"):
                _open_ticket(ticket.ticket_id)
                st.rerun()

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

    st.divider()

    # ── Main layout ─────────────────────────────────────────────────────────
    col_left, col_right = st.columns([3, 2])

    # ── LEFT: message thread ────────────────────────────────────────────────
    with col_left:
        st.subheader("Thread")

        for msg in ticket.messages:
            role = msg.get("role", "customer")
            ts   = msg.get("timestamp", "")[:16].replace("T", " ")

            if role == "customer":
                with st.chat_message("user"):
                    st.caption(ts)
                    st.write(msg.get("content", ""))
            else:
                with st.chat_message("assistant", avatar="🤖"):
                    st.caption(ts)
                    st.write(msg.get("content", ""))

        # Input form — shown only in "input" state
        if st.session_state.conv_state == "input":
            st.divider()
            with st.form("conv_input_form", clear_on_submit=True):
                customer_msg = st.text_area(
                    "Customer reply",
                    height=100,
                    placeholder="Paste or type the customer message here…",
                )
                submitted = st.form_submit_button(
                    "Analyze & Generate Draft →", type="primary"
                )

                if submitted and customer_msg.strip():
                    with st.spinner("Analyzing and generating response…"):
                        analysis = _analyze_ticket(ticket, customer_msg.strip())
                        st.session_state.conv_analysis     = analysis
                        st.session_state.conv_draft        = analysis["draft"]
                        st.session_state.conv_original_draft = analysis["draft"]
                        st.session_state.conv_action       = analysis["action"]
                        st.session_state.conv_pending_msg  = customer_msg.strip()
                        st.session_state.conv_trajectory   = analysis.get("trajectory")
                        st.session_state.conv_state        = "reviewing"
                        # Update ticket status
                        _tm.update_ticket(ticket.ticket_id, status="drafting")
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

        edited = st.text_area(
            "Review and edit before sending:",
            value=st.session_state.conv_draft,
            height=320,
            key="conv_draft_editor",
        )

        col_approve, col_reject, col_info = st.columns([3, 2, 1])

        with col_approve:
            if st.button("✅  Approve & Send", type="primary", use_container_width=True):
                _handle_approve(ticket, edited.strip(), a)
                st.rerun()

        with col_reject:
            if st.button("❌  Reject", use_container_width=True):
                _handle_reject(ticket, a)
                st.rerun()

        with col_info:
            st.caption(f"Msgs: {len(ticket.messages)}")

    # ── ERP ACTION PANEL ────────────────────────────────────────────────────
    if st.session_state.conv_state == "reviewing" and st.session_state.conv_action:
        action    = st.session_state.conv_action
        risk_icon = {"Low": "🟢", "Medium": "🟡", "High": "🔴"}.get(action["risk"], "⚪")

        st.divider()
        st.subheader("Suggested ERP Action")
        c_info, c_btn = st.columns([3, 2])

        with c_info:
            st.markdown(f"**{action['label']}**")
            st.caption(action["description"])
            st.caption(f"Risk: {risk_icon} {action['risk']}")
            extra_input = None
            if action.get("requires_input"):
                extra_input = st.text_input(action["input_label"], placeholder="e.g. April 20")

        with c_btn:
            st.write("")
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
                        "label":     action["label"],
                        "changes":   changes,
                        "risk":      action["risk"],
                    }
                    _tm.add_erp_action(ticket.ticket_id, erp_entry)
                    st.session_state.conv_action = None
                    st.success(f"Action executed: {action['label']}")
                    st.rerun()
                else:
                    st.error("ERP action failed.")

            if st.button("❌ Ignore", use_container_width=True):
                st.session_state.conv_action = None
                st.rerun()


# ==============================================================================
# CORE ANALYSIS FUNCTION (ticket-aware version of app.py's analyze_and_generate)
# ==============================================================================

def _analyze_ticket(ticket: Ticket, user_input: str) -> dict:
    """
    Run full NLP + AI generation for one new customer message on a ticket.
    Updates the ticket's order_id and priority if an order is found.
    """
    text = user_input.lower()

    language                          = detect_language(text)
    emotion, intensity, all_scores, emo_conf = detect_emotion(text)
    top_score  = max(all_scores.values()) if all_scores else 0
    secondary  = [e for e, s in all_scores.items() if s >= top_score * 0.30 and e != emotion]
    intent, int_conf = detect_intent(text)
    topic,  top_conf = detect_topic(text)

    # Order detection — use ticket's existing order_id first, then re-detect
    order_info, priority, order_id = find_order(user_input)
    if not order_id and ticket.order_id:
        order_id   = ticket.order_id
        order      = order_database.get(order_id, {})
        priority   = order.get("priority", ticket.priority)
        order_info = json.dumps(order, indent=2) if order else ""

    # Persist any new order discovery on the ticket
    if order_id and order_id != ticket.order_id:
        _tm.update_ticket(ticket.ticket_id, order_id=order_id, priority=priority)
        ticket = _tm.get_ticket(ticket.ticket_id)

    customer_name = ticket.customer_name

    # Contexts
    profile_context    = format_customer_profile_context(customer_name)
    trajectory         = get_emotion_trajectory(customer_name)
    trajectory_context = format_trajectory_context(trajectory, customer_name)
    kb_entries         = search_knowledge_base(intent, topic, text)
    kb_context         = format_kb_context(kb_entries)
    history            = search_history(
        order_id=order_id,
        customer_name=customer_name,
        intent=intent,
        topic=topic,
        current_session_id=ticket.ticket_id,
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

    # ERP action detection
    action = detect_suggested_action(
        order_id, intent, emotion, intensity, text=text
    )

    # Confidence scoring
    profile    = get_customer_profile(customer_name) if customer_name else None
    confidence = _scorer.score(
        nlp_confidence=emo_conf,
        emotion=emotion,
        intensity=intensity,
        intent=intent,
        profile=profile,
        trajectory=trajectory,
        action=action,
    )

    model_cfg = select_model(emotion, intensity, intent,
                             confidence_score=confidence["overall"])

    # Build conversation history for context (last 10 messages)
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
        model=model_cfg["model"],
        messages=messages,
        max_tokens=model_cfg["max_tokens"],
        temperature=model_cfg["temperature"],
    )
    draft = response.choices[0].message.content

    # Update ticket NLP fields
    _tm.update_ticket(
        ticket.ticket_id,
        emotion=emotion,
        intent=intent,
        confidence=confidence["overall"],
        status="pending_approval",
    )

    return {
        "language":   language,
        "emotion":    emotion,
        "intensity":  intensity,
        "secondary":  secondary,
        "intent":     intent,
        "topic":      topic,
        "draft":      draft,
        "action":     action,
        "emo_conf":   emo_conf,
        "int_conf":   int_conf,
        "top_conf":   top_conf,
        "confidence": confidence,
        "model_used": model_cfg["model"],
        "order_id":   order_id,
        "priority":   priority,
        "trajectory": trajectory,
    }


def _handle_approve(ticket: Ticket, final_reply: str, analysis: dict) -> None:
    """Persist approved reply, attempt email send, update ticket status."""
    user_msg   = st.session_state.conv_pending_msg
    action_str = (
        "modified"
        if final_reply != st.session_state.conv_original_draft.strip()
        else "approved"
    )
    now = _now().isoformat()

    # Add both messages to ticket thread
    _tm.add_message(ticket.ticket_id, {"role": "customer",   "content": user_msg,    "timestamp": now})
    _tm.add_message(ticket.ticket_id, {"role": "assistant",  "content": final_reply, "timestamp": now})

    # Attempt email send
    sent_ok = False
    try:
        from channels import get_channel_sender
        sender = get_channel_sender()
        sender.connect()
        sent_ok = sender.send(
            to=ticket.customer_email,
            subject=f"Re: {ticket.subject}",
            body=final_reply,
        )
        sender.disconnect()
    except Exception as exc:
        st.warning(f"Email send skipped: {exc}. Draft saved to ticket.")

    # Update ticket
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

    if sent_ok:
        st.success("Reply sent and ticket updated.")
    else:
        st.info("Draft saved. Configure email credentials in config.json to enable sending.")


def _handle_reject(ticket: Ticket, analysis: dict) -> None:
    """Discard draft, keep ticket open."""
    _tm.update_ticket(ticket.ticket_id, status="triaged")
    st.session_state.conv_state  = "input"
    st.session_state.conv_draft  = ""
    st.session_state.conv_action = None
    st.warning("Draft rejected.")
