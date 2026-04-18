# P2-12 — SLA-Aware Routing

## What This Does

Right now tickets are prioritised by intent and emotion, but not by how close they
are to breaching their SLA deadline. A "calm" order status enquiry with 20 minutes
left before SLA breach is treated the same as one that arrived 5 minutes ago.

This improvement adds SLA-aware routing: the decision engine calculates
`time_to_sla_breach` for every ticket and automatically upgrades the routing priority
if the breach is imminent. Tickets within 30 minutes of breach go to `priority` route.
Tickets that have already breached go to `supervisor` and trigger an alert.

**Where the change lives:**
Update `cs_ai/engine/tickets.py` (add `sla_deadline` field + `time_to_breach()`)
+ update `cs_ai/engine/agents/triage.py` (inject SLA urgency into routing)
+ update `cs_ai/engine/app_inbox.py` (show SLA countdown in ticket list).

**Impact:** No ticket silently misses its SLA because it looked low-priority.
Supervisors see breached tickets in red immediately. The system earns enterprise trust.

---

## Prompt — Paste into Claude Code

```
Add SLA-aware routing that automatically upgrades ticket priority based on time
remaining before the SLA deadline.

TASK:

1. Update cs_ai/engine/tickets.py:

   In the Ticket dataclass:
   - Add field: sla_deadline: str | None = None   # ISO-8601 datetime string

   Add method to Ticket:
   def time_to_breach_minutes(self) -> float | None:
       """
       Returns minutes remaining before SLA breach.
       Negative = already breached.
       Returns None if sla_deadline is not set.
       """
       if not self.sla_deadline:
           return None
       from datetime import datetime
       deadline = datetime.fromisoformat(self.sla_deadline)
       now = datetime.now().replace(tzinfo=None)
       deadline = deadline.replace(tzinfo=None)
       return (deadline - now).total_seconds() / 60

   def sla_urgency(self) -> str:
       """
       Returns: "breached" | "critical" | "high" | "normal"
       breached  = already past deadline
       critical  = < 30 minutes remaining
       high      = < 2 hours remaining
       normal    = > 2 hours or no deadline
       """
       ttb = self.time_to_breach_minutes()
       if ttb is None:
           return "normal"
       if ttb < 0:
           return "breached"
       if ttb < 30:
           return "critical"
       if ttb < 120:
           return "high"
       return "normal"

   In TicketManager._create_table():
   - Add column: sla_deadline TEXT DEFAULT NULL

   In TicketManager._row_to_ticket() and save():
   - Handle sla_deadline field (store as ISO string, load as string).

   In TicketManager.create_ticket() (or equivalent):
   - Compute sla_deadline from the SLA config:
       sla_hours = config["sla"][priority]["response_hours"]
       sla_deadline = (datetime.now() + timedelta(hours=sla_hours)).isoformat()

2. Update cs_ai/engine/agents/triage.py:
   - After loading ticket from ctx, compute urgency:
       ticket = ctx.get("ticket")
       if ticket:
           urgency = ticket.sla_urgency()
           ctx["sla_urgency"] = urgency
           if urgency == "breached":
               ctx["route"] = "supervisor"
               ctx.setdefault("risk_flags", []).append("sla_breached")
           elif urgency == "critical":
               # Force priority route unless already supervisor
               if ctx.get("route") not in ("supervisor", "priority"):
                   ctx["route"] = "priority"
               ctx.setdefault("risk_flags", []).append("sla_critical")
           elif urgency == "high":
               if ctx.get("route") == "auto":
                   ctx["route"] = "standard"   # don't auto-send high-urgency
               ctx.setdefault("risk_flags", []).append("sla_high")

3. Update cs_ai/engine/app_inbox.py:
   - In the ticket list display, add a "SLA" column that shows:
       - "🔴 BREACHED" in red if urgency == "breached"
       - "🟠 < 30 min" in orange if urgency == "critical"
       - "🟡 < 2 h" in yellow if urgency == "high"
       - "🟢 OK" in green if urgency == "normal"
   - Sort the ticket list by SLA urgency: breached first, then critical, high, normal.
   - If a ticket is breached, show a st.warning() banner:
     "⚠️ {count} ticket(s) have breached their SLA — immediate action required."

4. Add SLA breach counter to the page title:
   At the top of app_inbox.py, after computing ticket list:
   breached_count = sum(1 for t in tickets if t.sla_urgency() == "breached")
   critical_count = sum(1 for t in tickets if t.sla_urgency() == "critical")
   title = "CS Agent"
   if breached_count:
       title = f"CS Agent 🔴 {breached_count} BREACHED"
   elif critical_count:
       title = f"CS Agent 🟠 {critical_count} critical"
   st.set_page_config(page_title=title)

5. Update cs_ai/engine/pages/1_Analytics.py:
   Add a "SLA Compliance" metric card showing:
   - % tickets resolved within SLA (last 7 days)
   - % tickets breached SLA (last 7 days)
   - Average time to resolution vs SLA deadline

6. Create tests/unit/test_sla_routing.py:
   - Test time_to_breach_minutes() with a deadline 1 hour from now → returns ~60.
   - Test time_to_breach_minutes() with a past deadline → returns negative.
   - Test sla_urgency() with ttb = -5 → "breached".
   - Test sla_urgency() with ttb = 20 → "critical".
   - Test sla_urgency() with ttb = 90 → "high".
   - Test sla_urgency() with ttb = 300 → "normal".
   - Test that route is set to "supervisor" when urgency == "breached".

Do NOT change nlp.py, channels.py, connector.py, or any JSON data files.
Do NOT change the existing TICKET_PRIORITIES list or SLA config keys.
The sla_deadline field is nullable — all existing tickets without it work as before.
```
