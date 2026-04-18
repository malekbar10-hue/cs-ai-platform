# 06 — Tickets: Auto-Close Stale Tickets

## What This Does

After an agent sends a response, the ticket moves to "sent" status
and waits for the customer to reply. If the customer never replies
(they were satisfied, solved it themselves, or simply moved on),
the ticket stays open forever and clutters the inbox.

This improvement automatically closes tickets that have been in
"sent" status for longer than a configurable number of days
without receiving a new customer message. The default is 7 days.

Auto-closed tickets are clearly labeled in the inbox so supervisors
can see them. Any supervisor can reopen a ticket if needed.

**Where the change lives:** `tickets.py` (auto-close logic) +
`email_poller.py` (triggers the check each polling cycle) +
`app_inbox.py` (display + reopen button) +
`cs_ai/companies/default/config.json` (new config field).

**Impact:** Inbox stays clean automatically. Resolution rate metrics
become accurate. Agents are not distracted by tickets that are
effectively done but technically still open.

---

## Prompt — Paste into Claude Code

```
Automatically close tickets that have been waiting for a customer
reply for too long, based on a configurable number of days.

TASK:

1. Add to cs_ai/companies/default/config.json under "sla":
   "auto_close_days": 7
   Also add it to cs_ai/companies/_template/config.json.

2. Add to TicketManager in tickets.py:

   def auto_close_stale(self, days: int = None) -> int:
     - Reads days from config["sla"]["auto_close_days"] if not provided
     - Finds all tickets with status="sent" where updated_at < now - days
     - Updates their status to "closed"
     - Adds a system note: "Auto-closed after {days} days without customer reply"
     - Logs each closure to the audit trail with agent="system",
       action="auto_closed"
     - Returns count of closed tickets

3. Call auto_close_stale() in email_poller.py at the start of each
   polling cycle (once per cycle, not once per email). Log the count
   if > 0: "Auto-closed {count} stale tickets."

4. In app_inbox.py:
   - Auto-closed tickets show with a "🔒 Auto-closed" grey badge
   - Supervisors and admins see a "Reopen" button on these tickets
   - Reopen sets status back to "new" and logs action="reopened" in audit trail

Do NOT change nlp.py, main.py, connector.py, channels.py, or JSON data files.
```
