import streamlit as st
from datetime import datetime
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
    select_model,
)
from confidence import ConfidenceScorer

_scorer = ConfidenceScorer()

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
# LOGGING
# ==============================================================================

LOG_FILE = "logs.json"

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
    text = user_input.lower()

    language = detect_language(text)
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
    }

# ==============================================================================
# HEADER
# ==============================================================================

from main import CONFIG
st.markdown(f"## {CONFIG['company']['name']} — Customer Service Agent Dashboard")

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

    for msg in st.session_state.conversation_history:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.write(msg["content"])
        else:
            with st.chat_message("assistant", avatar="🤖"):
                st.write(msg["content"])

    # Customer input form — hidden while reviewing a draft
    if st.session_state.state == "input":
        st.divider()
        with st.form("input_form", clear_on_submit=True):
            customer_msg = st.text_area(
                "Customer message",
                height=100,
                placeholder="Paste or type the customer message here..."
            )
            submitted = st.form_submit_button("Analyze & Generate Draft →", type="primary")

            if submitted and customer_msg.strip():
                with st.spinner("Analyzing and generating response..."):
                    st.session_state.turn += 1
                    analysis = analyze_and_generate(customer_msg.strip())
                    st.session_state.current_analysis = analysis
                    st.session_state.current_draft    = analysis["draft"]
                    st.session_state.original_draft   = analysis["draft"]
                    st.session_state.current_action   = analysis["action"]
                    st.session_state.pending_user_msg = customer_msg.strip()
                    st.session_state.state = "reviewing"
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

    edited = st.text_area(
        "Review and edit the draft before sending:",
        value=st.session_state.current_draft,
        height=380,
        key="draft_editor"
    )

    col_approve, col_reject, col_turn = st.columns([3, 2, 1])

    with col_approve:
        if st.button("✅  Approve & Send", type="primary", use_container_width=True):
            user_msg = st.session_state.pending_user_msg
            final    = edited.strip()
            action   = "modified" if final != st.session_state.original_draft.strip() else "approved"

            # Commit to conversation history
            st.session_state.conversation_history.append({"role": "user",      "content": user_msg})
            st.session_state.conversation_history.append({"role": "assistant", "content": final})

            c_name = order_database.get(
                st.session_state.session_order_id, {}
            ).get("customer", "") if st.session_state.session_order_id else ""

            _conf = a.get("confidence", {})
            save_log({
                "session_id":               st.session_state.session_id,
                "turn":                     st.session_state.turn,
                "timestamp":                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "action":                   action,
                "language":                 a["language"],
                "emotion":                  a["emotion"],
                "intensity":                a["intensity"],
                "intent":                   a["intent"],
                "topic":                    a["topic"],
                "order_id":                 st.session_state.session_order_id,
                "customer_name":            c_name,
                "priority":                 st.session_state.session_priority,
                "customer_msg":             user_msg,
                "original_draft":           st.session_state.original_draft,
                "final_reply":              final,
                "confidence_score":         _conf.get("overall"),
                "confidence_recommendation":_conf.get("recommendation"),
                "model_used":               a.get("model_used"),
            })

            # Update persistent customer profile
            if c_name:
                update_customer_profile(
                    c_name, a["language"], a["emotion"],
                    a["intent"], a["topic"], resolved=True
                )

            st.session_state.state         = "input"
            st.session_state.current_draft = ""
            st.rerun()

    with col_reject:
        if st.button("❌  Reject", use_container_width=True):
            user_msg = st.session_state.pending_user_msg

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
# ERP ACTION PANEL — apparaît si une action est suggérée
# ==============================================================================

if st.session_state.state == "reviewing" and st.session_state.current_action:
    action = st.session_state.current_action

    risk_icons = {"Low": "🟢", "Medium": "🟡", "High": "🔴"}
    risk_icon  = risk_icons.get(action["risk"], "⚪")

    st.divider()
    st.subheader("⚡ Action ERP suggérée")

    col_info, col_btn = st.columns([3, 2])

    with col_info:
        st.markdown(f"**{action['label']}**")
        st.caption(action["description"])
        st.caption(f"Risque : {risk_icon} {action['risk']}")

        # Champ de saisie si l'action nécessite une input (ex: nouvelle date)
        extra_input = None
        if action.get("requires_input"):
            extra_input = st.text_input(action["input_label"], placeholder="ex: April 20")

    with col_btn:
        st.write("")  # espacement vertical

        if st.button("✅  Exécuter l'action", type="primary", use_container_width=True):
            changes = action["changes"].copy()

            # Si l'action attend une saisie agent, injecter la valeur
            if action.get("requires_input") and extra_input:
                for key in changes:
                    if changes[key] is None:
                        changes[key] = extra_input

            success = execute_action(st.session_state.session_order_id, changes)

            if success:
                # Mettre à jour le résumé de commande en session
                order_id = st.session_state.session_order_id
                order    = order_database[order_id]
                st.session_state.session_priority = order.get("priority", "Normal")

                # Journaliser l'action ERP
                erp_entry = {
                    "session_id": st.session_state.session_id,
                    "turn":       st.session_state.turn,
                    "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "order_id":   order_id,
                    "action":     action["type"],
                    "label":      action["label"],
                    "changes":    changes,
                    "risk":       action["risk"],
                }
                st.session_state.erp_log.append(erp_entry)

                # Sauvegarder dans logs.json
                save_log({**erp_entry, "log_type": "erp_action"})

                st.session_state.current_action = None
                st.success(f"✅ Action exécutée : {action['label']}")
                st.rerun()
            else:
                st.error("Erreur lors de l'exécution de l'action.")

        if st.button("❌  Ignorer", use_container_width=True):
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
