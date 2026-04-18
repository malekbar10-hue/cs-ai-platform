import streamlit as st
from datetime import datetime
import json
import os
from paths import resolve_data_file
from auth_guard import require_login

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
from status import check_connections as _check_connections, clear_cache as _clear_status_cache
from ui_channel import (
    get_channel_label as _get_channel_label,
    render_message_header as _render_message_header,
    render_inbound_input as _render_inbound_input,
    render_send_controls as _render_send_controls,
)
from connector import get_action_label as _get_action_label, get_risk_label as _get_risk_label
from rbac import can
from confidence import ConfidenceScorer
from agents.orchestrator import Orchestrator as _Orchestrator
from learning import get_analyzer as _get_analyzer
from tickets import TicketManager as _TicketManager

_scorer   = ConfidenceScorer()
_orch     = _Orchestrator()
_analyzer = _get_analyzer()
_tm_audit = _TicketManager()


def _feedback_bg(original: str, final: str, context: dict) -> None:
    """Classify a correction in a background thread — must never raise."""
    try:
        _analyzer.analyze_correction(original, final, context)
    except Exception:
        pass

# ==============================================================================
# PAGE CONFIG
# ==============================================================================

st.set_page_config(
    page_title="CS Agent Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .stTextArea textarea { font-size: 14px; }
    .stMetric label { font-size: 12px; }
    div[data-testid="stChatMessage"] { padding: 8px 0; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# AUTHENTICATION — must run before any dashboard content
# ==============================================================================

_username, _role = require_login(os.environ.get("CS_AI_COMPANY", "default"))
st.session_state["username"] = _username
st.session_state["role"]     = _role

# ==============================================================================
# SESSION STATE INIT
# ==============================================================================

defaults = {
    "conversation_history":  [],
    "session_order_info":    "",
    "session_priority":      "Normal",
    "session_order_id":      None,
    "session_id":            datetime.now().strftime("%Y%m%d_%H%M%S"),
    "turn":                  0,
    "state":                 "input",
    "current_draft":         "",
    "original_draft":        "",
    "current_analysis":      {},
    "pending_user_msg":      "",
    "current_action":        None,
    "erp_log":               [],
    "current_trajectory":    None,
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ==============================================================================
# CONNECTION STATUS (cached 60s)
# ==============================================================================

_status      = _check_connections(CONFIG)
_channel_cfg = CONFIG.get("communication", {}).get("outbound", {})

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

_STATUS_ICONS = {"connected": "🟢", "disconnected": "🔴", "not_configured": "⚪"}

with st.sidebar:
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
            if st.button("↻ Refresh", key="status_refresh_app"):
                _clear_status_cache()
                st.rerun()

        st.divider()

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

# ==============================================================================
# LOGGING
# ==============================================================================

LOG_FILE = resolve_data_file("logs.json")

def save_log(entry):
    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
    logs.append(entry)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

# ==============================================================================
# ANALYSIS + AI GENERATION
# ==============================================================================

def analyze_and_generate(user_input):
    """
    Run the full agent pipeline (Triage → Response → QA).
    Returns the enriched context dict which is a superset of the old analysis dict.
    Falls back to the legacy function if the pipeline raises an exception.
    """
    try:
        ctx = _orch.run({
            "user_input":           user_input,
            "conversation_history": st.session_state.conversation_history,
            "session_order_id":     st.session_state.session_order_id,
            "session_order_info":   st.session_state.session_order_info,
            "session_priority":     st.session_state.session_priority,
            "session_id":           st.session_state.session_id,
        })

        # Apply new order discovery to session state
        if ctx.get("_new_order_id"):
            st.session_state.session_order_id   = ctx["_new_order_id"]
            st.session_state.session_order_info = ctx["_new_order_info"]
            st.session_state.session_priority   = ctx["_new_priority"]

        # Persist trajectory for the analysis panel
        st.session_state.current_trajectory = ctx.get("trajectory")

        return ctx

    except Exception as _exc:
        # Pipeline failed — use legacy function as safety net
        import traceback
        traceback.print_exc()
        return _analyze_and_generate_legacy(user_input)


def _analyze_and_generate_legacy(user_input):
    text = user_input.lower()

    language, lang_confidence, lang_mixed = detect_language(text)
    emotion, intensity, all_scores, emo_conf = detect_emotion(text)
    top_score = max(all_scores.values()) if all_scores else 0
    secondary = [e for e, s in all_scores.items() if s >= top_score * 0.30 and e != emotion]
    intent, int_conf = detect_intent(text)
    topic,  top_conf = detect_topic(text)

    new_order_info, new_priority, new_order_id = find_order(user_input)
    if new_order_id:
        st.session_state.session_order_info = new_order_info
        st.session_state.session_priority   = new_priority
        st.session_state.session_order_id   = new_order_id

    # Retrieve customer name for L2 search
    customer_name = ""
    if st.session_state.session_order_id:
        customer_name = order_database.get(
            st.session_state.session_order_id, {}
        ).get("customer", "")

    # 1 — Customer profile
    profile_context    = format_customer_profile_context(customer_name)

    # 2 — Emotional trajectory
    trajectory         = get_emotion_trajectory(customer_name)
    trajectory_context = format_trajectory_context(trajectory, customer_name)

    # 3 — Knowledge base (relevant policies/procedures)
    kb_entries  = search_knowledge_base(intent, topic, user_input.lower())
    kb_context  = format_kb_context(kb_entries)

    # 4 — History search (same client resolved cases)
    history         = search_history(
        order_id=st.session_state.session_order_id,
        customer_name=customer_name,
        intent=intent,
        topic=topic,
        current_session_id=st.session_state.session_id,
    )
    history_context = format_history_context(history)

    system_prompt = build_system_prompt(
        language, emotion, intensity, secondary, intent, topic,
        st.session_state.session_order_info,
        st.session_state.session_priority,
        history_context=history_context,
        profile_context=profile_context,
        trajectory_context=trajectory_context,
        kb_context=kb_context,
    )

    # Store trajectory for display
    st.session_state.current_trajectory = trajectory

    # Detect ERP action early — needed for confidence + model selection
    action = detect_suggested_action(
        st.session_state.session_order_id,
        intent, emotion, intensity,
        text=user_input.lower()
    )

    # Confidence scoring (done before API call — feeds model selection)
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

    # Model selection based on complexity + confidence
    model_cfg = select_model(
        emotion, intensity, intent,
        confidence_score=confidence["overall"],
    )

    messages = (
        [{"role": "system", "content": system_prompt}]
        + st.session_state.conversation_history
        + [{"role": "user", "content": user_input}]
    )

    response = client.chat.completions.create(
        model=model_cfg["model"],
        messages=messages,
        max_tokens=model_cfg["max_tokens"],
        temperature=model_cfg["temperature"],
    )
    draft = response.choices[0].message.content

    return {
        "language":         language,
        "lang_confidence":  lang_confidence,
        "lang_mixed":       lang_mixed,
        "emotion":          emotion,
        "intensity":        intensity,
        "secondary":        secondary,
        "intent":           intent,
        "topic":            topic,
        "draft":      draft,
        "action":     action,
        "emo_conf":   emo_conf,
        "int_conf":   int_conf,
        "top_conf":   top_conf,
        "confidence": confidence,
        "model_used": model_cfg["model"],
    }

# ==============================================================================
# HEADER
# ==============================================================================

st.markdown(
    f"## {CONFIG['company']['name']} — Customer Service Agent Dashboard"
    f" · {_get_channel_label(_channel_cfg)}"
)

col_title, col_session = st.columns([4, 1])
with col_session:
    st.caption(f"Session `{st.session_state.session_id}`")
    st.caption(f"Turn **{st.session_state.turn}** | Msgs: **{len(st.session_state.conversation_history)}**")

st.divider()

# ==============================================================================
# MAIN LAYOUT — left: conversation | right: analysis
# ==============================================================================

col_left, col_right = st.columns([3, 2])

# ── LEFT: conversation history ─────────────────────────────────────────────
with col_left:
    st.subheader("Conversation")

    for i, msg in enumerate(st.session_state.conversation_history):
        if msg["role"] == "user":
            with st.chat_message("user"):
                _render_message_header(msg, _channel_cfg, message_index=i)
                st.write(msg["content"])
        else:
            with st.chat_message("assistant", avatar="🤖"):
                _render_message_header(msg, _channel_cfg, message_index=i)
                st.write(msg["content"])

    # Customer input form — hidden while reviewing a draft
    if st.session_state.state == "input":
        st.divider()
        customer_msg = _render_inbound_input(_channel_cfg, form_key="app_inbound_form")
        if customer_msg:
            with st.status("Analyzing message...", expanded=False) as _status:
                _status.update(label="Analyzing message...")
                st.session_state.turn += 1
                _status.update(label="Generating response...")
                analysis = analyze_and_generate(customer_msg)
                _status.update(label="Reviewing draft...", state="complete")
                st.session_state.current_analysis = analysis
                st.session_state.current_draft    = analysis["draft"]
                st.session_state.original_draft   = analysis["draft"]
                st.session_state.current_action   = analysis["action"]
                st.session_state.pending_user_msg = customer_msg
                st.session_state.state = "reviewing"
                _tm_audit.log_action(
                    ticket_id=st.session_state.session_id,
                    agent=st.session_state.get("username", "system"),
                    action="draft_generated",
                    detail=(
                        f"intent={analysis.get('intent','')} "
                        f"emotion={analysis.get('emotion','')} "
                        f"model={analysis.get('model_used','')}"
                    ),
                )
            st.rerun()

# ── RIGHT: analysis panel ──────────────────────────────────────────────────
with col_right:
    st.subheader("Analysis")

    emotion_icons = {
        "Angry":      "🔴",
        "Frustrated": "🟠",
        "Urgent":     "🟡",
        "Anxious":    "🔵",
        "Satisfied":  "🟢",
        "Neutral":    "⚪",
    }

    if st.session_state.current_analysis:
        a = st.session_state.current_analysis
        icon = emotion_icons.get(a["emotion"], "⚪")

        c1, c2 = st.columns(2)
        with c1:
            st.metric("Emotion", f"{icon} {a['emotion']}")
            st.metric("Intent",  a["intent"])
        with c2:
            st.metric("Intensity", a["intensity"])
            st.metric("Topic",     a["topic"])

        st.metric("Language", a["language"])
        if a.get("lang_confidence", 1.0) < 0.65:
            st.warning("⚠ Language uncertain — verify the response is in the right language")

        if a.get("model_used"):
            st.caption(f"Model: `{a['model_used']}`")

        if a.get("secondary"):
            st.caption(f"Secondary signals: {', '.join(a['secondary'])}")

        # NLP model confidence (per-signal)
        emo_c = a.get("emo_conf", 0)
        int_c = a.get("int_conf", 0)
        top_c = a.get("top_conf", 0)
        if emo_c > 0 or int_c > 0 or top_c > 0:
            def _conf_label(v):
                if v >= 0.50: return f"🟢 {int(v*100)}%"
                if v >= 0.35: return f"🟡 {int(v*100)}%"
                return f"🔴 {int(v*100)}%"
            st.caption(
                f"Model confidence — emotion: {_conf_label(emo_c)} · "
                f"intent: {_conf_label(int_c)} · "
                f"topic: {_conf_label(top_c)}"
            )

        # Overall confidence score + routing recommendation
        conf = a.get("confidence")
        if conf:
            overall = conf["overall"]
            rec     = conf["recommendation"]
            pct     = int(overall * 100)

            if overall >= 0.85:
                conf_color = "🟢"
            elif overall >= 0.50:
                conf_color = "🟡"
            else:
                conf_color = "🔴"

            rec_labels = {
                "auto_send":        "Auto-send eligible",
                "human_review":     "Human review recommended",
                "supervisor_review":"Supervisor review required",
            }
            st.divider()
            st.markdown(
                f"**Draft confidence:** {conf_color} **{pct}%** — "
                f"{rec_labels.get(rec, rec)}"
            )
            # Factor breakdown as expander
            with st.expander("Confidence breakdown", expanded=False):
                factor_labels = {
                    "nlp":               "NLP detection",
                    "emotion_risk":      "Emotion risk",
                    "customer_risk":     "Customer risk",
                    "action_risk":       "ERP action risk",
                    "intent_complexity": "Intent complexity",
                }
                for k, v in conf["factors"].items():
                    bar_pct = int(v * 100)
                    label   = factor_labels.get(k, k)
                    icon    = "🟢" if v >= 0.65 else "🟡" if v >= 0.40 else "🔴"
                    st.caption(f"{icon} {label}: {bar_pct}%")
                    st.progress(v)

        # ── QA review result ───────────────────────────────────────────────
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

        # ── Escalation preview ─────────────────────────────────────────────
        esc_preview = a.get("escalation_preview", [])
        if esc_preview:
            st.divider()
            with st.expander("⚠ Escalation rules matched", expanded=True):
                for _er in esc_preview:
                    st.warning(f"**{_er['rule_name']}** → {_er['tier']} | {_er['reason']}")

        # ── Pipeline details ───────────────────────────────────────────────
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

    else:
        st.info("Analysis will appear here after the first message.")

    if st.session_state.session_order_id:
        st.divider()
        priority_colors = {
            "Critical": "🔴", "High": "🟠", "Normal": "🟢", "Low": "⚪"
        }
        p_icon = priority_colors.get(st.session_state.session_priority, "⚪")
        st.markdown(f"**Order** `{st.session_state.session_order_id}` — {p_icon} **{st.session_state.session_priority}**")
        st.code(st.session_state.session_order_info.strip(), language=None)

    # Emotional trajectory
    traj = st.session_state.get("current_trajectory")
    if traj:
        st.divider()
        trend_icons = {"Escalating": "🔴", "Stable": "🟡", "Improving": "🟢"}
        icon  = trend_icons.get(traj["trend"], "⚪")
        st.markdown(f"**Trajectoire émotionnelle** {icon} {traj['trend']}")
        sessions_str = " → ".join(s["emotion"] for s in traj["sessions"])
        st.caption(sessions_str)
        if traj.get("alert"):
            st.warning("⚠ Client en escalade — empathie maximale")

    # Customer profile summary
    if st.session_state.session_order_id:
        c_name = order_database.get(st.session_state.session_order_id, {}).get("customer", "")
        profile = get_customer_profile(c_name) if c_name else None
        if profile:
            st.divider()
            st.markdown(f"**Profil client** — {c_name}")
            st.caption(
                f"Interactions: {profile.get('total_interactions',0)} | "
                f"Résolutions: {profile.get('resolved_cases',0)} | "
                f"Émotion dominante: {profile.get('dominant_emotion','?')}"
            )

# ==============================================================================
# DRAFT REVIEW PANEL — appears below when state == "reviewing"
# ==============================================================================

if st.session_state.state == "reviewing":
    st.divider()
    st.subheader("AI Draft — Awaiting Agent Approval")

    a = st.session_state.current_analysis
    st.caption(
        f"Emotion: **{a['emotion']}** ({a['intensity']}) · "
        f"Intent: **{a['intent']}** · Topic: **{a['topic']}**"
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
            if _fc2.button("✏ Fix", key=f"fix_{_flag}", help=f"Ask AI to add: {_flag}"):
                try:
                    from draft_fix import fix_draft_element
                    _current = st.session_state.get("draft_editor", st.session_state.current_draft)
                    _fixed   = fix_draft_element(_current, _flag, a)
                    st.session_state.current_draft = _fixed
                    a.get("draft_ai_flags", []).remove(_flag)
                except Exception as _e:
                    st.error(f"Fix failed: {_e}")
                st.rerun()

    edited = st.text_area(
        "Review and edit the draft before sending:",
        value=st.session_state.current_draft,
        height=380,
        key="draft_editor"
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

    col_approve, col_reject, col_turn = st.columns([3, 2, 1])

    def _on_approve_app(sent_ok: bool) -> None:
        """Shared approve callback — called by render_send_controls."""
        _final    = edited.strip()
        _user_msg = st.session_state.pending_user_msg
        _action   = "modified" if _final != st.session_state.original_draft.strip() else "approved"

        # Commit to conversation history
        st.session_state.conversation_history.append({"role": "user",      "content": _user_msg})
        st.session_state.conversation_history.append({"role": "assistant", "content": _final})

        _c_name = order_database.get(
            st.session_state.session_order_id, {}
        ).get("customer", "") if st.session_state.session_order_id else ""

        # Audit log
        _agent_name = st.session_state.get("username", "system")
        if _action == "modified":
            _tm_audit.log_action(
                ticket_id=st.session_state.session_id,
                agent=_agent_name,
                action="draft_modified",
                before_value=st.session_state.original_draft,
                after_value=_final,
            )
        else:
            _tm_audit.log_action(
                ticket_id=st.session_state.session_id,
                agent=_agent_name,
                action="draft_approved",
            )

        # KB usage — mark rows for this ticket as draft approved
        _tm_audit.mark_kb_approved(st.session_state.session_id)

        # Lesson effectiveness tracking
        _lesson_ids = a.get("applied_lesson_ids", [])
        if _lesson_ids:
            try:
                from learning import get_analyzer as _ga
                if _action == "approved":
                    _ga().mark_effective(_lesson_ids)
                else:
                    _ga().mark_applied(_lesson_ids)
            except Exception:
                pass

        # Learning — classify correction in background if draft was edited
        if _action == "modified":
            import threading as _threading
            _fb_ctx = {
                "company":       CONFIG.get("company", {}).get("name", ""),
                "customer_name": _c_name,
                "emotion":       a.get("emotion", ""),
                "intensity":     a.get("intensity", ""),
                "intent":        a.get("intent", ""),
                "topic":         a.get("topic", ""),
            }
            _threading.Thread(
                target=_feedback_bg,
                args=(st.session_state.original_draft, _final, _fb_ctx),
                daemon=True,
            ).start()

        _conf = a.get("confidence", {})
        save_log({
            "session_id":               st.session_state.session_id,
            "turn":                     st.session_state.turn,
            "timestamp":                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action":                   _action,
            "language":                 a["language"],
            "emotion":                  a["emotion"],
            "intensity":                a["intensity"],
            "intent":                   a["intent"],
            "topic":                    a["topic"],
            "order_id":                 st.session_state.session_order_id,
            "customer_name":            _c_name,
            "priority":                 st.session_state.session_priority,
            "customer_msg":             _user_msg,
            "original_draft":           st.session_state.original_draft,
            "final_reply":              _final,
            "confidence_score":         _conf.get("overall"),
            "confidence_recommendation":_conf.get("recommendation"),
            "model_used":               a.get("model_used"),
        })

        if _c_name:
            update_customer_profile(
                _c_name, a["language"], a["emotion"],
                a["intent"], a["topic"], resolved=True
            )

        st.session_state.state         = "input"
        st.session_state.current_draft = ""
        if sent_ok:
            st.toast("Response sent ✅", icon="✅")
        for _esc in a.get("escalation_preview", []):
            st.toast(f"Escalation triggered: {_esc['rule_name']}", icon="📢")
        st.rerun()

    with col_approve:
        _render_send_controls(
            None, edited.strip(), _channel_cfg,
            _on_approve_app, button_key="app_approve_btn",
        )
        st.caption("Tip: you can edit the draft above before approving")

    with col_reject:
        if st.button("❌  Reject", use_container_width=True):
            user_msg = st.session_state.pending_user_msg

            _tm_audit.log_action(
                ticket_id=st.session_state.session_id,
                agent=st.session_state.get("username", "system"),
                action="draft_rejected",
            )

            try:
                from learning import get_analyzer as _ga
                _ga().mark_applied(a.get("applied_lesson_ids", []))
            except Exception:
                pass

            _conf = a.get("confidence", {})
            save_log({
                "session_id":               st.session_state.session_id,
                "turn":                     st.session_state.turn,
                "timestamp":                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "action":                   "rejected",
                "language":                 a["language"],
                "emotion":                  a["emotion"],
                "intensity":                a["intensity"],
                "intent":                   a["intent"],
                "topic":                    a["topic"],
                "order_id":                 st.session_state.session_order_id,
                "priority":                 st.session_state.session_priority,
                "customer_msg":             user_msg,
                "original_draft":           st.session_state.original_draft,
                "final_reply":              None,
                "confidence_score":         _conf.get("overall"),
                "confidence_recommendation":_conf.get("recommendation"),
                "model_used":               a.get("model_used"),
            })

            st.session_state.state         = "input"
            st.session_state.current_draft = ""
            st.warning("Draft rejected — not added to conversation.")
            st.rerun()

    with col_turn:
        st.caption(f"Turn #{st.session_state.turn}")

# ==============================================================================
# ERP ACTION PANEL — appears when state == "reviewing" and action is suggested
# ==============================================================================

if st.session_state.state == "reviewing" and st.session_state.current_action:
    action = st.session_state.current_action

    st.divider()

    if _status.erp in ("disconnected", "not_configured"):
        st.caption("⚪ ERP actions unavailable — ERP not configured")
    else:
        _risk_icons   = {"Low": "🟢", "Medium": "🟡", "High": "🔴"}
        _risk_icon    = _risk_icons.get(action["risk"], "⚪")
        _action_label = _get_action_label(action["type"], _ERP_MAPPING)
        _risk_label   = _get_risk_label(action["risk"], _ERP_MAPPING)

        st.subheader("⚡ Suggested ERP Action")

        col_info, col_btn = st.columns([3, 2])

        with col_info:
            st.markdown(f"**{_action_label}**")
            st.caption(action.get("description", ""))
            st.caption(f"Risk: {_risk_icon} {_risk_label}")

            extra_input = None
            if action.get("requires_input"):
                extra_input = st.text_input(action["input_label"], placeholder="ex: April 20")

        with col_btn:
            st.write("")
            _erp_perm = f"erp_{action['risk'].lower()}_risk"
            if can(_role, _erp_perm):
                if st.button("✅  Execute action", type="primary", use_container_width=True):
                    changes = action["changes"].copy()
                    if action.get("requires_input") and extra_input:
                        for key in changes:
                            if changes[key] is None:
                                changes[key] = extra_input

                    success = execute_action(st.session_state.session_order_id, changes)

                    if success:
                        order_id = st.session_state.session_order_id
                        order    = order_database[order_id]
                        st.session_state.session_priority = order.get("priority", "Normal")

                        erp_entry = {
                            "session_id": st.session_state.session_id,
                            "turn":       st.session_state.turn,
                            "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "order_id":   order_id,
                            "action":     action["type"],
                            "label":      _action_label,
                            "changes":    changes,
                            "risk":       action["risk"],
                        }
                        st.session_state.erp_log.append(erp_entry)
                        save_log({**erp_entry, "log_type": "erp_action"})
                        _tm_audit.log_action(
                            ticket_id=st.session_state.session_id,
                            agent=st.session_state.get("username", "system"),
                            action="erp_action_executed",
                            detail=f"{action['type']} order_id={order_id}",
                        )
                        st.session_state.current_action = None
                        st.success(f"Action executed: {_action_label}")
                        st.rerun()
                    else:
                        st.error("ERP action failed.")
            else:
                st.caption(f"🔒 {action['risk']}-risk actions require supervisor approval")

            if st.button("❌  Ignore", use_container_width=True):
                _tm_audit.log_action(
                    ticket_id=st.session_state.session_id,
                    agent=st.session_state.get("username", "system"),
                    action="erp_action_rejected",
                    detail=action.get("type", ""),
                )
                st.session_state.current_action = None
                st.rerun()

# ==============================================================================
# ERP ACTION HISTORY (sidebar)
# ==============================================================================

if st.session_state.erp_log:
    with st.sidebar:
        st.subheader("⚡ Actions ERP exécutées")
        for entry in reversed(st.session_state.erp_log):
            st.markdown(f"**Turn {entry['turn']}** — {entry['label']}")
            st.caption(entry["timestamp"])
            st.divider()
