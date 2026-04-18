# 05 — Tickets: Internal Agent Notes

## What This Does

Agents often need to leave notes for themselves or their colleagues
about a ticket — context that should NOT be sent to the customer.
For example: "Waiting for logistics team to confirm the new date",
or "Customer is a VIP — handle carefully", or "This is the third
time they've had this issue."

Right now there is no place to store this. Agents would need to
use a separate tool or keep notes in their head.

This improvement adds an internal notes section to every ticket.
Notes are visible only to the team, clearly labeled as internal,
append-only (no editing or deleting), and every note is attributed
to the agent who wrote it with a timestamp. They also appear in
the audit trail.

**Where the change lives:** `tickets.py` (storage) +
`app_inbox.py` (display and input).

**Impact:** Team collaboration on tickets, context preservation
across shifts, no more lost information between agents.

---

## Prompt — Paste into Claude Code

```
Add an internal notes field to tickets so agents can leave
comments visible only to the team — never sent to the customer.

TASK:

1. In tickets.py, add a "notes" column to the tickets table:
   Add the column to CREATE TABLE IF NOT EXISTS for new DBs.
   For existing DBs, run ALTER TABLE tickets ADD COLUMN notes TEXT DEFAULT ''
   only if the column does not already exist (check with PRAGMA table_info).

2. Add to TicketManager:

   def add_note(self, ticket_id: str, agent: str, note: str):
     Loads existing notes JSON from the notes column (default empty list []).
     Appends: {"agent": agent, "timestamp": now_iso, "text": note}
     Saves back to the notes column.
     Notes are append-only — no editing or deleting methods.

   def get_notes(self, ticket_id: str) -> list[dict]:
     Returns the list of note dicts for a ticket. Returns [] if none.

3. In app_inbox.py, in the conversation detail view, add an
   "Internal Notes" section below the draft panel:
   - Shows existing notes in a light yellow background box
   - Each note shows: agent name · timestamp · note text
   - A text input + "Add Note" button to add a new note
   - Section header clearly says: "🔒 Internal — not sent to customer"
   - Visible to all roles (agent, supervisor, admin)

4. Log note additions to the audit trail:
   log_action(ticket_id, agent, "note_added", detail=note[:100])

Do NOT change nlp.py, main.py, connector.py, channels.py, or JSON data files.
```
