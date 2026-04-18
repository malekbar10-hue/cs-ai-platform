import streamlit as st
import pandas as pd
import json
import os
import sys
from datetime import datetime
from collections import Counter

# pages/ is one level below engine/ — ensure engine/ is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import config_path, resolve_data_file
from learning import get_analyzer as _get_analyzer

# ── Config & data ─────────────────────────────────────────────────────────────
with open(config_path(), "r", encoding="utf-8") as f:
    CONFIG = json.load(f)
COMPANY = CONFIG["company"]["name"]

LOG_FILE      = resolve_data_file(CONFIG["crm"].get("logs_file",     "logs.json"))
PROFILES_FILE = resolve_data_file(CONFIG["crm"].get("profiles_file", "customer_profiles.json"))

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

# ── SLA Compliance (last 7 days) ──────────────────────────────────────────────
try:
    import sqlite3 as _sla_sqlite
    from tickets import DB_PATH as _TICKETS_DB_SLA
    from datetime import timedelta as _td7

    _cutoff_7d = (datetime.now() - _td7(days=7)).isoformat()

    with _sla_sqlite.connect(_TICKETS_DB_SLA) as _sc:
        _sc.row_factory = _sla_sqlite.Row
        _sla_rows = _sc.execute(
            "SELECT updated_at, sla_deadline FROM tickets "
            "WHERE created_at >= ? AND status IN ('resolved','closed','sent')",
            (_cutoff_7d,),
        ).fetchall()

    _n_resolved   = len(_sla_rows)
    _n_within     = 0
    _n_breached_r = 0
    _time_diffs_h = []

    for _sr in _sla_rows:
        try:
            _upd = datetime.fromisoformat(_sr["updated_at"]).replace(tzinfo=None)
            _dl  = datetime.fromisoformat(_sr["sla_deadline"]).replace(tzinfo=None)
            if _upd <= _dl:
                _n_within += 1
            else:
                _n_breached_r += 1
            _time_diffs_h.append((_upd - _dl).total_seconds() / 3600)
        except Exception:
            pass

    _pct_within   = round(_n_within     / _n_resolved * 100) if _n_resolved else 100
    _pct_breached = round(_n_breached_r / _n_resolved * 100) if _n_resolved else 0
    _avg_vs_dl    = round(sum(_time_diffs_h) / len(_time_diffs_h), 1) if _time_diffs_h else 0
    _avg_label    = (
        f"{_avg_vs_dl:+.1f}h vs deadline"
        if _time_diffs_h else "—"
    )

    st.subheader("SLA Compliance — last 7 days")
    _sc1, _sc2, _sc3 = st.columns(3)
    _sc1.metric(
        "Resolved within SLA",
        f"{_pct_within}%",
        delta=f"{_n_within}/{_n_resolved} tickets",
    )
    _sc2.metric(
        "Breached SLA",
        f"{_pct_breached}%",
        delta=f"{_n_breached_r} tickets",
        delta_color="inverse",
    )
    _sc3.metric(
        "Avg. resolution vs deadline",
        _avg_label,
        help="Negative = resolved before deadline; positive = resolved after",
    )
    st.divider()

except Exception as _sla_ex:
    st.caption(f"SLA metrics unavailable: {_sla_ex}")
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

# ── ROW 8 — Learning from corrections ────────────────────────────────────────
st.divider()
st.subheader("AI Learning — Feedback Loop")

try:
    _analyzer = _get_analyzer()
    _report   = _analyzer.get_report(days=30)
except Exception as _e:
    st.caption(f"Learning module unavailable: {_e}")
    _report = None

if _report:
    # ── Key learning metrics ───────────────────────────────────────────────
    lm1, lm2, lm3, lm4 = st.columns(4)

    _trend_icon = {"improving": "🟢", "stable": "🟡", "worsening": "🔴"}.get(
        _report["trend"], "⚪"
    )
    lm1.metric("Interactions (30d)",   _report["total_interactions"])
    lm2.metric("Corrections (30d)",    _report["total_corrections"])
    lm3.metric("Correction rate",      f"{_report['correction_rate']}%",
               help="% of approved drafts that were edited by the agent")
    lm4.metric(
        "AI trend",
        f"{_trend_icon} {_report['trend'].capitalize()}",
        help="Comparing severity of corrections: first half vs second half of period",
    )

    st.divider()

    col_chart, col_types = st.columns([2, 1])

    with col_chart:
        st.subheader("Corrections over time (30 days)")
        _daily = _report.get("daily_data", [])
        if _daily:
            _daily_df = pd.DataFrame(_daily).set_index("date")
            # Show both series if interactions data is present
            if _daily_df["interactions"].sum() > 0:
                _display_df = _daily_df[["interactions", "corrections"]]
                st.line_chart(_display_df, use_container_width=True)
            else:
                st.bar_chart(_daily_df["corrections"], use_container_width=True)
        else:
            st.caption("No corrections recorded yet.")

    with col_types:
        st.subheader("Correction types")
        _type_counts = _report.get("type_counts", {})
        if _type_counts:
            _type_icons = {
                "tone":         "🎭",
                "factual":      "📋",
                "added_info":   "➕",
                "removed_info": "➖",
                "policy":       "📜",
                "minor":        "✏️",
            }
            _tc_df = pd.Series(_type_counts).sort_values(ascending=False)
            for _ct, _cnt in _tc_df.items():
                _icon = _type_icons.get(_ct, "•")
                st.caption(f"{_icon} **{_ct}** — {_cnt}")
                st.progress(int(_cnt / max(_tc_df) * 100) / 100)
        else:
            st.caption("No correction type data yet.")

        if _report.get("most_common_type"):
            st.caption(f"Most common: **{_report['most_common_type']}**")

    st.divider()

    col_lessons, col_intents = st.columns([2, 1])

    with col_lessons:
        st.subheader("Lessons — effectiveness")
        try:
            import sqlite3 as _sqlite3
            from paths import resolve_data_file as _rdf
            _db = _rdf("lessons.db")
            if os.path.exists(_db):
                with _sqlite3.connect(_db) as _conn:
                    _conn.row_factory = _sqlite3.Row
                    _rows = _conn.execute(
                        "SELECT id, timestamp, correction_type, severity, lesson, "
                        "emotion, intent, "
                        "COALESCE(times_applied, 0)   AS times_applied, "
                        "COALESCE(times_effective, 0) AS times_effective "
                        "FROM lessons ORDER BY timestamp DESC LIMIT 100"
                    ).fetchall()
                if _rows:
                    _sev_icon = {"critical": "🔴", "significant": "🟡", "minor": "🟢"}
                    _lessons_data = []
                    for r in _rows:
                        _applied   = r["times_applied"]
                        _effective = r["times_effective"]
                        _rate      = round(_effective / _applied * 100) if _applied else None
                        _rate_str  = f"{_rate}%" if _rate is not None else "—"
                        _badge     = " ⚠" if (_applied >= 5 and _rate is not None and _rate < 20) else ""
                        _lessons_data.append({
                            "Severity":    f"{_sev_icon.get(r['severity'], '⚪')} {r['severity']}",
                            "Type":        r["correction_type"],
                            "Context":     f"{r['emotion']} / {r['intent']}",
                            "Lesson":      r["lesson"],
                            "Applied":     _applied,
                            "Effective":   _effective,
                            "Eff. rate":   _rate_str + _badge,
                            "_sort_rate":  _rate if _rate is not None else -1,
                        })
                    _les_df = (
                        pd.DataFrame(_lessons_data)
                        .sort_values("_sort_rate", ascending=False)
                        .drop(columns=["_sort_rate"])
                        .reset_index(drop=True)
                    )
                    st.dataframe(_les_df, use_container_width=True, hide_index=True)

                    _low_eff = [r for r in _lessons_data if "⚠" in r["Eff. rate"]]
                    if _low_eff:
                        st.warning(
                            f"⚠ {len(_low_eff)} lesson(s) with low effectiveness "
                            f"(< 20% after 5+ uses). Consider reviewing or removing them."
                        )
                else:
                    st.caption("No lessons recorded yet. Lessons are created when agents edit AI drafts.")
            else:
                st.caption("No lessons recorded yet.")
        except Exception as _ex:
            st.caption(f"Could not load lessons: {_ex}")

    with col_intents:
        st.subheader("Corrections by intent")
        _ic = _report.get("intent_corrections", {})
        if _ic:
            _ic_df = pd.Series(_ic).sort_values(ascending=False)
            st.bar_chart(_ic_df, use_container_width=True)
        else:
            st.caption("No intent data yet.")

    # ── AI improvement verdict ─────────────────────────────────────────────
    st.divider()
    _verdicts = {
        "improving": (
            "🟢 **The AI is improving.** "
            "Corrections in the second half of this period were less severe than in the first half."
        ),
        "stable": (
            "🟡 **Performance is stable.** "
            "No significant change in correction severity over the period."
        ),
        "worsening": (
            "🔴 **Performance may be declining.** "
            "Corrections in the second half were more severe. "
            "Review recent lessons to identify patterns."
        ),
    }
    if _report["total_corrections"] < 5:
        st.info(
            "Not enough correction data yet to assess trend. "
            f"Need at least 5 corrections ({_report['total_corrections']} so far)."
        )
    else:
        st.markdown(_verdicts.get(_report["trend"], ""))
else:
    st.caption("No learning data available yet. Lessons are built when agents edit AI drafts.")

# ── ROW 9 — Knowledge Base usage ─────────────────────────────────────────────
st.divider()
st.subheader("📚 Knowledge Base Usage")

try:
    import sqlite3 as _sqlite3
    from paths import resolve_data_file as _rdf, resolve_company_file as _rcf
    from datetime import timedelta as _td

    _db_path = _rdf("../../../data/" + os.environ.get("CS_AI_COMPANY", "default") + "/tickets.db")
    # Resolve via tickets module for correct path
    from tickets import DB_PATH as _TICKETS_DB
    _cutoff_30 = (datetime.now() - _td(days=30)).strftime("%Y-%m-%d %H:%M:%S")

    # Load KB entry titles
    _kb_titles: dict = {}
    try:
        import json as _json
        _kb_file = _rcf("knowledge_base.json")
        with open(_kb_file, encoding="utf-8") as _kf:
            _kb_raw = _json.load(_kf)
            _kb_entries_all = _kb_raw if isinstance(_kb_raw, list) else _kb_raw.get("entries", [])
            _kb_titles = {e["id"]: e.get("title", e["id"]) for e in _kb_entries_all}
    except Exception:
        pass

    with _sqlite3.connect(_TICKETS_DB) as _conn:
        _conn.row_factory = _sqlite3.Row

        # All-time retrieval stats per KB entry
        _usage_rows = _conn.execute("""
            SELECT
                kb_entry_id,
                COUNT(*)                                   AS times_retrieved,
                ROUND(AVG(relevance), 3)                   AS avg_relevance,
                SUM(draft_approved)                        AS approved_count
            FROM kb_usage
            GROUP BY kb_entry_id
            ORDER BY times_retrieved DESC
        """).fetchall()

        # KB entries retrieved in the last 30 days
        _recent_ids = {
            r[0] for r in _conn.execute(
                "SELECT DISTINCT kb_entry_id FROM kb_usage WHERE timestamp >= ?",
                (_cutoff_30,),
            ).fetchall()
        }

    if _usage_rows:
        _kb_data = []
        for _r in _usage_rows:
            _eid       = _r["kb_entry_id"]
            _retrieved = _r["times_retrieved"]
            _approved  = _r["approved_count"] or 0
            _approval_rate = round(_approved / _retrieved * 100) if _retrieved else 0
            _unused    = "📦 Unused" if _eid not in _recent_ids else ""
            _kb_data.append({
                "Entry":          _kb_titles.get(_eid, _eid),
                "Times retrieved": _retrieved,
                "Approval rate":  f"{_approval_rate}%",
                "Avg relevance":  f"{_r['avg_relevance']:.2f}" if _r["avg_relevance"] else "—",
                "Status":         _unused,
            })

        st.dataframe(pd.DataFrame(_kb_data), use_container_width=True, hide_index=True)

        _unused_count = sum(1 for r in _kb_data if r["Status"])
        if _unused_count:
            st.caption(
                f"📦 {_unused_count} entry/entries not retrieved in the last 30 days. "
                "Consider reviewing or updating them."
            )

        # Also show KB entries that exist but were NEVER retrieved
        _never_retrieved = [
            _kb_titles.get(eid, eid)
            for eid in _kb_titles
            if eid not in {r["kb_entry_id"] for r in _usage_rows}
        ]
        if _never_retrieved:
            with st.expander(f"📦 {len(_never_retrieved)} entries never retrieved", expanded=False):
                for _title in _never_retrieved:
                    st.caption(f"• {_title}")
    else:
        st.caption("No KB usage data yet. Entries are tracked when the agent pipeline retrieves them.")

except Exception as _kb_ex:
    st.caption(f"KB usage unavailable: {_kb_ex}")

# ── Customer Health ───────────────────────────────────────────────────────────
st.divider()
st.subheader("Customer Health")

try:
    from health_score import HealthScoreComputer as _HSC
    from tickets import DB_PATH as _TICKETS_DB
    import sqlite3 as _hs_sqlite

    with _hs_sqlite.connect(_TICKETS_DB) as _hconn:
        _email_rows = _hconn.execute(
            "SELECT DISTINCT customer_email FROM tickets WHERE customer_email != ''"
        ).fetchall()
    _all_emails = [r[0] for r in _email_rows]

    if _all_emails:
        _hsc = _HSC()
        _health_data = []
        for _email in _all_emails:
            _hs = _hsc.compute(_email)
            _health_data.append({
                "Customer":        _email,
                "Score":           round(_hs.score, 3),
                "Label":           _hs.label,
                "Escalation Rate": f"{int(_hs.escalation_rate * 100)}%",
                "SLA Compliance":  f"{int(_hs.sla_compliance_rate * 100)}%",
                "Emotion Trend":   _hs.emotion_trend,
                "Open Tickets":    _hs.open_tickets,
                "_label":          _hs.label,
            })

        _health_df = (
            pd.DataFrame(_health_data)
            .sort_values("Score")
            .reset_index(drop=True)
        )
        _labels     = _health_df["_label"].values
        _disp_cols  = ["Customer", "Score", "Label", "Escalation Rate",
                        "SLA Compliance", "Emotion Trend", "Open Tickets"]
        _disp_df    = _health_df[_disp_cols].copy()

        _ROW_COLORS = {"critical": "#ffcccc", "at_risk": "#ffe0b2"}

        def _color_health_row(row):
            color = _ROW_COLORS.get(_labels[row.name], "#c8e6c9")
            return [f"background-color: {color}"] * len(row)

        st.dataframe(
            _disp_df.style.apply(_color_health_row, axis=1),
            use_container_width=True,
            hide_index=True,
        )

        _n_critical = int((_health_df["_label"] == "critical").sum())
        _n_at_risk  = int((_health_df["_label"] == "at_risk").sum())
        if _n_critical:
            st.error(f"🔴 {_n_critical} customer(s) in critical health state.")
        if _n_at_risk:
            st.warning(f"🟠 {_n_at_risk} customer(s) at risk.")
        if not _n_critical and not _n_at_risk:
            st.success("✅ All customers are healthy.")
    else:
        st.success("✅ All customers are healthy.")

except Exception as _health_ex:
    st.caption(f"Customer health unavailable: {_health_ex}")

# ── Refresh button ────────────────────────────────────────────────────────────
st.divider()
if st.button("🔄 Refresh data"):
    st.rerun()
