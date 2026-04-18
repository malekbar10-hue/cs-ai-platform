import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from collections import Counter

# ── Config & data ─────────────────────────────────────────────────────────────
with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)
COMPANY = CONFIG["company"]["name"]

LOG_FILE      = CONFIG["crm"].get("logs_file",     "logs.json")
PROFILES_FILE = CONFIG["crm"].get("profiles_file", "customer_profiles.json")

st.set_page_config(page_title=f"{COMPANY} — Analytics", layout="wide")

def load_logs():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        try:    return json.load(f)
        except: return []

def load_profiles():
    if not os.path.exists(PROFILES_FILE):
        return {}
    with open(PROFILES_FILE, "r", encoding="utf-8") as f:
        try:    return json.load(f)
        except: return {}

all_logs  = load_logs()
profiles  = load_profiles()

# Separate conversations from ERP actions
conv_logs = [e for e in all_logs if e.get("log_type") != "erp_action" and e.get("customer_msg")]
erp_logs  = [e for e in all_logs if e.get("log_type") == "erp_action"]

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"## {COMPANY} — Customer Service Analytics")
st.caption(f"Based on {len(conv_logs)} logged interactions · Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
st.divider()

if not conv_logs:
    st.info("No interactions logged yet. Start a conversation in the Agent Dashboard.")
    st.stop()

# ── Build dataframe ────────────────────────────────────────────────────────────
df = pd.DataFrame(conv_logs)
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df["date"]      = df["timestamp"].dt.date
df["action"]    = df["action"].fillna("unknown")

# ── ROW 1 — Key metrics ───────────────────────────────────────────────────────
total        = len(df)
resolved     = len(df[df["action"].isin(["approved", "modified"])])
rejected     = len(df[df["action"] == "rejected"])
modified     = len(df[df["action"] == "modified"])
resolution_r = f"{int(resolved/total*100)}%" if total else "—"
modification_r = f"{int(modified/resolved*100)}%" if resolved else "—"

top_emotion = df["emotion"].mode()[0] if not df["emotion"].isna().all() else "—"
top_intent  = df["intent"].mode()[0]  if "intent" in df.columns else "—"

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total interactions",   total)
c2.metric("Resolution rate",      resolution_r)
c3.metric("Drafts modified",      modification_r, help="% of approved drafts that were edited by the agent")
c4.metric("Dominant emotion",     top_emotion)
c5.metric("Top intent",           top_intent)

st.divider()

# ── ROW 2 — Distributions ─────────────────────────────────────────────────────
col_emo, col_int, col_top = st.columns(3)

with col_emo:
    st.subheader("Emotion distribution")
    emotion_counts = df["emotion"].value_counts()
    emotion_colors = {
        "Angry": "🔴", "Frustrated": "🟠", "Urgent": "🟡",
        "Anxious": "🔵", "Satisfied": "🟢", "Neutral": "⚪"
    }
    for emo, count in emotion_counts.items():
        icon = emotion_colors.get(emo, "⚪")
        pct  = int(count / total * 100)
        st.markdown(f"{icon} **{emo}** — {count} ({pct}%)")
        st.progress(pct / 100)

with col_int:
    st.subheader("Intent distribution")
    if "intent" in df.columns:
        intent_counts = df["intent"].value_counts()
        st.bar_chart(intent_counts, use_container_width=True)

with col_top:
    st.subheader("Topic distribution")
    if "topic" in df.columns:
        topic_counts = df["topic"].value_counts()
        st.bar_chart(topic_counts, use_container_width=True)

st.divider()

# ── ROW 3 — Draft quality ─────────────────────────────────────────────────────
col_qual, col_time = st.columns([1, 2])

with col_qual:
    st.subheader("Agent decisions")
    action_counts = df["action"].value_counts()
    action_icons  = {"approved": "✅", "modified": "✏️", "rejected": "❌", "unknown": "❓"}
    for action, count in action_counts.items():
        icon = action_icons.get(action, "•")
        pct  = int(count / total * 100)
        st.markdown(f"{icon} **{action.capitalize()}** — {count} ({pct}%)")
        st.progress(pct / 100)

with col_time:
    st.subheader("Interactions over time")
    if "date" in df.columns:
        daily = df.groupby("date").size().reset_index(name="count")
        daily["date"] = daily["date"].astype(str)
        daily = daily.set_index("date")
        st.bar_chart(daily["count"], use_container_width=True)

st.divider()

# ── ROW 4 — Priority & intensity ─────────────────────────────────────────────
col_pri, col_int2 = st.columns(2)

with col_pri:
    st.subheader("Order priority breakdown")
    if "priority" in df.columns:
        pri_counts = df["priority"].value_counts()
        priority_icons = {"Critical": "🔴", "High": "🟠", "Normal": "🟢", "Low": "⚪"}
        for pri, count in pri_counts.items():
            icon = priority_icons.get(pri, "•")
            pct  = int(count / total * 100)
            st.markdown(f"{icon} **{pri}** — {count} ({pct}%)")
            st.progress(pct / 100)

with col_int2:
    st.subheader("Emotion intensity breakdown")
    if "intensity" in df.columns:
        int_counts = df["intensity"].value_counts()
        st.bar_chart(int_counts, use_container_width=True)

st.divider()

# ── ROW 5 — Client activity ───────────────────────────────────────────────────
st.subheader("Client activity")

col_cli, col_prof = st.columns(2)

with col_cli:
    if "customer_name" in df.columns:
        client_df = df[df["customer_name"].notna() & (df["customer_name"] != "")]
        if not client_df.empty:
            client_counts = client_df["customer_name"].value_counts().head(10)
            st.bar_chart(client_counts, use_container_width=True)
        else:
            st.caption("No client name data yet.")
    else:
        st.caption("No client name data yet.")

with col_prof:
    st.subheader("Client profiles summary")
    if profiles:
        rows = []
        for name, p in profiles.items():
            rows.append({
                "Client":        name,
                "Interactions":  p.get("total_interactions", 0),
                "Resolved":      p.get("resolved_cases", 0),
                "Top emotion":   p.get("dominant_emotion", "—"),
                "Top intent":    p.get("dominant_intent", "—"),
                "Last contact":  p.get("last_contact", "—")[:10],
            })
        profiles_df = pd.DataFrame(rows).sort_values("Interactions", ascending=False)
        st.dataframe(profiles_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No profiles built yet. Profiles are created after approved interactions.")

st.divider()

# ── ROW 6 — ERP actions ───────────────────────────────────────────────────────
st.subheader("ERP actions executed")

if erp_logs:
    col_erp1, col_erp2 = st.columns([1, 2])

    with col_erp1:
        erp_df      = pd.DataFrame(erp_logs)
        action_dist = erp_df["action"].value_counts()
        st.bar_chart(action_dist, use_container_width=True)

    with col_erp2:
        st.markdown("**Recent ERP actions**")
        recent_erp = erp_df[["timestamp", "order_id", "label", "risk"]].tail(10).sort_values(
            "timestamp", ascending=False
        )
        risk_icons = {"Low": "🟢", "Medium": "🟡", "High": "🔴"}
        recent_erp["risk"] = recent_erp["risk"].apply(lambda r: f"{risk_icons.get(r,'⚪')} {r}")
        st.dataframe(recent_erp, use_container_width=True, hide_index=True)
else:
    st.caption("No ERP actions executed yet.")

st.divider()

# ── ROW 7 — Escalating clients ────────────────────────────────────────────────
st.subheader("⚠ Clients to watch")

EMOTION_SEVERITY = {
    "Satisfied": 0, "Neutral": 1, "Anxious": 2,
    "Frustrated": 3, "Urgent": 4, "Angry": 5
}

escalating = []
for name, p in profiles.items():
    client_logs = sorted(
        [e for e in conv_logs if e.get("customer_name","") == name],
        key=lambda x: x.get("timestamp","")
    )
    if len(client_logs) >= 3:
        severities = [EMOTION_SEVERITY.get(e.get("emotion","Neutral"), 1) for e in client_logs[-5:]]
        trend = severities[-1] - severities[0]
        if trend >= 2:
            escalating.append({
                "Client":         name,
                "Trend":          "🔴 Escalating",
                "Last emotion":   client_logs[-1].get("emotion","—"),
                "Interactions":   p.get("total_interactions", 0),
                "Last contact":   p.get("last_contact","—")[:10],
            })

if escalating:
    esc_df = pd.DataFrame(escalating)
    st.dataframe(esc_df, use_container_width=True, hide_index=True)
else:
    st.success("No escalating clients detected.")

# ── Refresh button ────────────────────────────────────────────────────────────
st.divider()
if st.button("🔄 Refresh data"):
    st.rerun()
