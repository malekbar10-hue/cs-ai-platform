# 07 — Tickets: Manual Priority Override

## What This Does

The AI detects ticket priority automatically based on emotion, order data,
and customer profile. But it is not always right. A supervisor may know
something the AI does not — for example, that a "Normal" priority customer
is actually a strategic account that needs Critical treatment, or that
a "Critical" order has already been resolved by phone and can be downgraded.

This improvement lets supervisors and admins manually override the AI-detected
priority of any ticket directly from the dashboard. When overridden, the SLA
deadline is recalculated to match the new priority. A visual badge
"⚡ Manual override" appears next to the priority in the inbox so it is
clear the priority was changed by a human.

**Where the change lives:** `app_inbox.py` (override UI) +
`tickets.py` (SLA recalculation) + audit trail logging.

**Impact:** Supervisors have full control over prioritization.
SLA tracking stays accurate even after manual changes.

---

## Prompt — Paste into Claude Code

```
Allow supervisors to manually override a ticket's priority.

TASK:

1. In app_inbox.py, in the ticket detail view, add a priority selector
   visible to supervisors and admins only
   (check st.session_state.get("role") in ("supervisor", "admin")):

   new_priority = st.selectbox(
     "Priority override",
     ["Normal", "High", "Critical"],
     index=["Normal", "High", "Critical"].index(ticket.priority)
   )
   if new_priority != ticket.priority:
     if st.button("Apply"):
       ticket_manager.override_priority(ticket.ticket_id, new_priority, username)
       st.success(f"Priority updated to {new_priority}")
       st.rerun()

2. Add override_priority(ticket_id, new_priority, agent) to TicketManager:
   - Updates ticket.priority to new_priority
   - Recalculates sla_deadline:
     new_hours = config["sla"][new_priority]["response_hours"]
     new_deadline = ticket.created_at + timedelta(hours=new_hours)
   - Stores original_priority in ticket.metadata if not already stored
     (so we always know what the AI originally detected)
   - Logs to audit trail: action="priority_override",
     before_value=old_priority, after_value=new_priority, agent=agent

3. In the inbox list view: if ticket.metadata.get("original_priority") exists
   and differs from ticket.priority, show a small "⚡" badge next to
   the priority indicator for that ticket row.

Do NOT change nlp.py, main.py, connector.py, channels.py, or JSON data files.
```
