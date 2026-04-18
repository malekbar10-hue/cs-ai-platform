# 10 — Knowledge Base: Usage Tracking

## What This Does

Your knowledge base entries are retrieved automatically by the system
and injected into AI prompts. But there is no visibility into which
entries are actually being retrieved, which ones lead to good outcomes,
and which ones have never been used.

This means two problems can go undetected:
- An outdated or wrong KB entry is being retrieved and misleading the AI
- A useful entry was added but is never matched because its keywords/embeddings
  are poorly written

This improvement adds usage tracking per KB entry. Every time an entry
is retrieved and used in a draft, it is counted. If the draft is approved,
the entry is marked as "helpful". Entries that are never retrieved in 30 days
get an "📦 Unused" badge in the analytics page so you know to review them.

**Where the change lives:** `tickets.py` (new kb_usage table) +
`agents/response.py` (logs retrievals) + `pages/1_Analytics.py`
(KB usage section).

**Impact:** You can see which KB entries are driving responses,
identify entries that are never used, and clean up or improve
entries with low approval rates.

---

## Prompt — Paste into Claude Code

```
Track which knowledge base entries are retrieved and whether they help.

TASK:

1. Add a kb_usage table to the SQLite database in tickets.py:
   CREATE TABLE IF NOT EXISTS kb_usage (
     id              INTEGER PRIMARY KEY AUTOINCREMENT,
     timestamp       TEXT NOT NULL,
     kb_entry_id     TEXT NOT NULL,
     kb_entry_title  TEXT,
     ticket_id       TEXT,
     relevance       REAL DEFAULT 0,
     draft_approved  INTEGER DEFAULT 0
   )

2. Add to TicketManager:

   def log_kb_usage(self, kb_entry_id: str, kb_entry_title: str,
                    ticket_id: str, relevance: float):
     Inserts one row per KB entry retrieved. draft_approved defaults to 0.

   def mark_kb_helpful(self, ticket_id: str):
     Updates all kb_usage rows for this ticket_id: set draft_approved = 1.

3. In agents/response.py, after KB entries are retrieved, call:
   for entry in kb_entries:
     ticket_manager.log_kb_usage(
       entry["id"], entry.get("title",""), ticket_id, entry.get("relevance", 0)
     )

4. In app.py and app_inbox.py: on any approval action (approved or modified),
   call ticket_manager.mark_kb_helpful(ticket_id).

5. Add a "Knowledge Base Usage" section to pages/1_Analytics.py:
   Query: SELECT kb_entry_id, kb_entry_title, COUNT(*) as retrievals,
          AVG(relevance) as avg_relevance,
          SUM(draft_approved)*100/COUNT(*) as approval_rate
          FROM kb_usage GROUP BY kb_entry_id ORDER BY retrievals DESC
   Display as a table with columns:
   Entry | Times Retrieved | Avg Relevance | Approval Rate
   Entries with 0 retrievals in last 30 days: show "📦 Unused" badge.
   Entries with approval_rate < 40% and retrievals >= 5: show "⚠ Review" badge.

Do NOT change nlp.py, connector.py, main.py, learning.py, or JSON data files.
```
