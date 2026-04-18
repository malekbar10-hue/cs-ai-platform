# P2-11 — Customer Health Score

## What This Does

Right now there is no way to know which customers are at risk of churning or
escalating. Supervisors have no visibility into whether a customer's experience
is deteriorating over time. Sales has no signal for when to reach out.

This improvement adds a `CustomerHealthScore` computed per account from ticket
data already in the database: escalation rate, average confidence of responses,
emotion trend, draft rejection frequency, and SLA compliance. The score appears
in the supervisor dashboard and is available as a context signal for the triage
agent (high-risk customers get priority routing automatically).

**Where the change lives:**
New file `cs_ai/engine/health_score.py` + update
`cs_ai/engine/pages/1_Analytics.py` (new "Customer Health" tab) + update
`cs_ai/engine/agents/triage.py` (use health score for priority routing).

**Impact:** Supervisors see at-risk customers before they escalate.
Sales sees churn signals. High-risk customers automatically get priority handling.

---

## Prompt — Paste into Claude Code

```
Add a CustomerHealthScore that is computed from ticket history and used for
priority routing and supervisor visibility.

TASK:

1. Create cs_ai/engine/health_score.py:

   import sqlite3
   from dataclasses import dataclass
   from paths import tickets_db_path

   @dataclass
   class HealthScore:
       customer_email:      str
       score:               float   # 0.0 (critical) to 1.0 (healthy)
       label:               str     # "healthy" | "at_risk" | "critical"
       escalation_rate:     float
       avg_confidence:      float
       emotion_trend:       str     # "improving" | "stable" | "worsening"
       sla_compliance_rate: float
       open_tickets:        int
       computed_at:         str

   class HealthScoreComputer:

       def __init__(self):
           self._db = tickets_db_path()

       def compute(self, customer_email: str, lookback_days: int = 30) -> HealthScore:
           """
           Compute health score for a customer using the last N days of ticket data.

           Score formula (each component 0.0–1.0, weighted average):
             - escalation_rate:     0.0 = always escalated, 1.0 = never escalated (weight 0.3)
             - avg_confidence:      raw confidence score from tickets (weight 0.25)
             - sla_compliance_rate: fraction of tickets resolved within SLA (weight 0.25)
             - emotion_score:       1.0=calm, 0.75=neutral, 0.4=frustrated, 0.0=angry (weight 0.2)

           Label:
             score >= 0.75 → "healthy"
             score >= 0.45 → "at_risk"
             score  < 0.45 → "critical"
           """
           from datetime import datetime, UTC, timedelta
           import json

           cutoff = (datetime.now(UTC).replace(tzinfo=None) -
                     timedelta(days=lookback_days)).isoformat()

           conn = sqlite3.connect(self._db)
           try:
               rows = conn.execute("""
                   SELECT status, priority, created_at, resolved_at,
                          confidence_score, emotion, escalated
                   FROM tickets
                   WHERE customer_email = ? AND created_at >= ?
               """, (customer_email, cutoff)).fetchall()
           except Exception:
               rows = []
           finally:
               conn.close()

           if not rows:
               return HealthScore(
                   customer_email=customer_email, score=1.0, label="healthy",
                   escalation_rate=0.0, avg_confidence=1.0, emotion_trend="stable",
                   sla_compliance_rate=1.0, open_tickets=0,
                   computed_at=datetime.now(UTC).replace(tzinfo=None).isoformat()
               )

           total = len(rows)
           escalated    = sum(1 for r in rows if r[6])
           avg_conf     = sum(float(r[4] or 0.8) for r in rows) / total
           emotions     = [r[5] or "neutral" for r in rows]
           emotion_map  = {"calm":1.0,"neutral":0.75,"frustrated":0.4,"angry":0.0}
           avg_emotion  = sum(emotion_map.get(e,0.75) for e in emotions) / total

           # SLA compliance: check if resolved within expected hours
           # (simplified: resolved_at not None counts as compliant for now)
           resolved     = sum(1 for r in rows if r[3])
           open_count   = total - resolved

           esc_rate     = escalated / total
           sla_rate     = resolved / total

           score = (
               (1.0 - esc_rate) * 0.30 +
               avg_conf         * 0.25 +
               sla_rate         * 0.25 +
               avg_emotion      * 0.20
           )
           score = max(0.0, min(1.0, score))

           # Emotion trend: compare first half vs second half
           half = total // 2
           if half > 0:
               first_half_avg  = sum(emotion_map.get(emotions[i], 0.75) for i in range(half)) / half
               second_half_avg = sum(emotion_map.get(emotions[i], 0.75) for i in range(half, total)) / (total - half)
               if second_half_avg > first_half_avg + 0.1:
                   trend = "improving"
               elif second_half_avg < first_half_avg - 0.1:
                   trend = "worsening"
               else:
                   trend = "stable"
           else:
               trend = "stable"

           label = "healthy" if score >= 0.75 else ("at_risk" if score >= 0.45 else "critical")
           return HealthScore(
               customer_email=customer_email, score=round(score, 3),
               label=label, escalation_rate=round(esc_rate, 3),
               avg_confidence=round(avg_conf, 3), emotion_trend=trend,
               sla_compliance_rate=round(sla_rate, 3), open_tickets=open_count,
               computed_at=datetime.now(UTC).replace(tzinfo=None).isoformat()
           )

       def at_risk_customers(self, account_id: str, top_n: int = 10) -> list[HealthScore]:
           """Return the top N at-risk or critical customers for a given account."""
           conn = sqlite3.connect(self._db)
           try:
               emails = conn.execute("""
                   SELECT DISTINCT customer_email FROM tickets
                   WHERE account_id = ?
               """, (account_id,)).fetchall()
           except Exception:
               emails = []
           finally:
               conn.close()
           scores = [self.compute(row[0]) for row in emails]
           at_risk = [s for s in scores if s.label in ("at_risk","critical")]
           at_risk.sort(key=lambda s: s.score)
           return at_risk[:top_n]

2. Update cs_ai/engine/agents/triage.py:
   - Import HealthScoreComputer from health_score.
   - After loading ticket, compute:
       hs = HealthScoreComputer().compute(ctx.get("customer_email",""))
       ctx["customer_health"] = hs
   - If hs.label == "critical": force ctx["route"] = "priority" and add
     "customer_critical_health" to ctx["risk_flags"].
   - If hs.label == "at_risk": add "customer_at_risk" to ctx["risk_flags"].

3. Update cs_ai/engine/pages/1_Analytics.py:
   - Add a "Customer Health" tab alongside the existing analytics tabs.
   - In the tab:
       from health_score import HealthScoreComputer
       computer = HealthScoreComputer()
       at_risk  = computer.at_risk_customers(account_id, top_n=20)
       Show a table with columns: Customer | Score | Label | Escalation Rate |
       SLA Compliance | Emotion Trend | Open Tickets
       Colour-code rows: critical=red, at_risk=orange, healthy=green.
       If no at-risk customers: st.success("✅ All customers are healthy.")

4. Create tests/unit/test_health_score.py:
   - Test that compute() with no tickets returns a HealthScore with label="healthy".
   - Test that 100% escalation rate produces a low score and label="critical".
   - Test that label is "at_risk" for score between 0.45 and 0.75.
   - Test that emotion_trend is "worsening" when the last half has more angry emotions.

Do NOT change nlp.py, channels.py, tickets.py data model, app.py, or JSON company config files.
The health score computation must be read-only — no writes to the tickets database.
If the tickets table does not yet have emotion, confidence_score, or escalated columns,
the compute() method must handle their absence gracefully (use defaults).
```
