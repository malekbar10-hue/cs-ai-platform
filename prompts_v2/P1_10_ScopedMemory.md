# P1-10 — Scoped Memory

## What This Does

Right now the system has no persistent memory between separate conversations with
the same customer. Every ticket starts cold. The agent cannot recall that this
customer already complained about the same issue last week, or that they have a
premium SLA, or that their previous tone was frustrated.

This improvement adds a `ScopedMemory` system that stores lightweight, bounded
memory items per ticket, per client, and per account. Memory is always bounded
(max items + TTL), PII is redacted before persistence, and memory is never shared
across accounts.

**Where the change lives:**
New file `cs_ai/engine/memory.py` + SQLite table `cs_ai/data/{company}/memory.db`
+ update `cs_ai/engine/agents/triage.py` to load client memory context.

**Impact:** The agent becomes more context-aware across sessions without any
cross-customer contamination. Memory degrades naturally via TTL — no stale data.

---

## Prompt — Paste into Claude Code

```
Add a bounded, scoped memory system that persists lightweight context between tickets
for the same customer.

TASK:

1. Create cs_ai/engine/memory.py:

   import hashlib
   import json
   import re
   import sqlite3
   from dataclasses import dataclass, field
   from datetime import datetime, UTC, timedelta
   from typing import Literal
   from paths import resolve_data_file

   _EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}')

   def _redact(text: str) -> str:
       return _EMAIL_RE.sub("[EMAIL]", str(text))

   @dataclass
   class MemoryItem:
       scope:       Literal["ticket","client","account"]
       scope_id:    str     # ticket_id, client email hash, or account_id
       key:         str     # e.g. "last_emotion", "last_intent", "sla_tier"
       value:       str     # always stored as string (JSON-serialise if needed)
       created_at:  str     # ISO-8601
       expires_at:  str     # ISO-8601
       checksum:    str = ""

       def __post_init__(self):
           self.value    = _redact(self.value)
           self.checksum = hashlib.sha256(
               (self.scope_id + self.key + self.value).encode()
           ).hexdigest()[:8]

       def is_expired(self) -> bool:
           return datetime.fromisoformat(self.expires_at) < datetime.now(UTC).replace(tzinfo=None)

   class ScopedMemory:
       """SQLite-backed memory store, isolated per company/account."""

       MAX_ITEMS_PER_SCOPE = 20   # hard cap to prevent unbounded growth

       def __init__(self, company: str):
           db_path = resolve_data_file(company, "memory.db")
           self._conn = sqlite3.connect(db_path, check_same_thread=False)
           self._create_table()

       def _create_table(self):
           self._conn.execute("""
               CREATE TABLE IF NOT EXISTS memory (
                   id          INTEGER PRIMARY KEY AUTOINCREMENT,
                   scope       TEXT NOT NULL,
                   scope_id    TEXT NOT NULL,
                   key         TEXT NOT NULL,
                   value       TEXT NOT NULL,
                   created_at  TEXT NOT NULL,
                   expires_at  TEXT NOT NULL,
                   checksum    TEXT NOT NULL,
                   UNIQUE(scope, scope_id, key)
               )
           """)
           self._conn.commit()

       def store(self, item: MemoryItem) -> None:
           """Upsert a memory item. Enforce per-scope item cap."""
           now = datetime.now(UTC).replace(tzinfo=None).isoformat()
           self._conn.execute("""
               INSERT INTO memory (scope, scope_id, key, value, created_at, expires_at, checksum)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(scope, scope_id, key) DO UPDATE SET
                   value=excluded.value, created_at=excluded.created_at,
                   expires_at=excluded.expires_at, checksum=excluded.checksum
           """, (item.scope, item.scope_id, item.key, item.value,
                 item.created_at, item.expires_at, item.checksum))
           self._conn.commit()
           self._enforce_cap(item.scope, item.scope_id)

       def _enforce_cap(self, scope: str, scope_id: str):
           rows = self._conn.execute("""
               SELECT id FROM memory WHERE scope=? AND scope_id=?
               ORDER BY created_at DESC
           """, (scope, scope_id)).fetchall()
           if len(rows) > self.MAX_ITEMS_PER_SCOPE:
               excess_ids = [r[0] for r in rows[self.MAX_ITEMS_PER_SCOPE:]]
               self._conn.execute(f"DELETE FROM memory WHERE id IN ({','.join('?'*len(excess_ids))})", excess_ids)
               self._conn.commit()

       def recall(self, scope: str, scope_id: str) -> list[MemoryItem]:
           """Return all non-expired memory items for a given scope."""
           now = datetime.now(UTC).replace(tzinfo=None).isoformat()
           rows = self._conn.execute("""
               SELECT scope, scope_id, key, value, created_at, expires_at, checksum
               FROM memory
               WHERE scope=? AND scope_id=? AND expires_at > ?
               ORDER BY created_at DESC
           """, (scope, scope_id, now)).fetchall()
           items = []
           for r in rows:
               items.append(MemoryItem(
                   scope=r[0], scope_id=r[1], key=r[2], value=r[3],
                   created_at=r[4], expires_at=r[5], checksum=r[6]
               ))
           return items

       def recall_as_context(self, scope: str, scope_id: str) -> str:
           """Format memory as a string for injection into an LLM prompt."""
           items = self.recall(scope, scope_id)
           if not items:
               return ""
           lines = [f"[MEMORY:{item.key}] {item.value}" for item in items]
           return "\n".join(lines)

       def purge_expired(self) -> int:
           """Delete all expired items. Call periodically."""
           now = datetime.now(UTC).replace(tzinfo=None).isoformat()
           c = self._conn.execute("DELETE FROM memory WHERE expires_at <= ?", (now,))
           self._conn.commit()
           return c.rowcount

   def make_item(scope, scope_id, key, value, ttl_hours=24) -> MemoryItem:
       now = datetime.now(UTC).replace(tzinfo=None)
       return MemoryItem(
           scope=scope, scope_id=scope_id, key=key, value=str(value),
           created_at=now.isoformat(),
           expires_at=(now + timedelta(hours=ttl_hours)).isoformat(),
       )

2. Update cs_ai/engine/agents/triage.py:
   - Import ScopedMemory, make_item from memory.
   - At the start of TriageAgent.run(), after loading ticket:
       company = ctx.get("company", "default")
       mem = ScopedMemory(company)
       client_id = hashlib.sha256(ctx.get("customer_email","").encode()).hexdigest()[:16]
       memory_context = mem.recall_as_context("client", client_id)
       ctx["client_memory_context"] = memory_context
   - At the end of run(), after triage is complete, persist new items:
       mem.store(make_item("client", client_id, "last_emotion", triage_emotion, ttl_hours=168))
       mem.store(make_item("client", client_id, "last_intent",  triage_intent,  ttl_hours=168))
       mem.store(make_item("ticket", ctx.get("ticket_id",""), "triage_summary",
                           f"{triage_intent}/{triage_emotion}", ttl_hours=24))

3. Update cs_ai/engine/agents/response.py:
   - If ctx.get("client_memory_context") is non-empty, include it in the system
     prompt under a "## Customer History (from memory)" section.
   - This section must be placed AFTER the verified facts section.

4. Create tests/unit/test_memory.py:
   - Test that store() + recall() returns the same item.
   - Test that an expired item is not returned by recall().
   - Test that the item cap is enforced (store 25 items, recall returns max 20).
   - Test that redaction removes email addresses from stored values.
   - Test that purge_expired() removes expired items.

Do NOT change nlp.py, channels.py, tickets.py, app.py, app_inbox.py, or any JSON data.
Do NOT store raw email body content in memory — only derived summaries (emotion, intent, etc.).
Do NOT share memory between different companies/accounts — the ScopedMemory is initialised
with a company identifier that determines the DB file path.
```
