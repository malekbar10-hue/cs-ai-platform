"""
memory.py — Bounded, scoped customer memory persisted in SQLite.

Stores lightweight derived facts (emotion, intent, preferences) per customer
across tickets.  Raw email bodies and PII are never stored — only summaries.

Scopes:
  "ticket"  — ephemeral, single interaction
  "client"  — one customer identity (hashed e-mail used as scope_id)
  "account" — company/account level (account name as scope_id)

Usage:
    mem       = ScopedMemory("default")
    client_id = hashlib.sha256(email.encode()).hexdigest()[:16]
    mem.store(make_item("client", client_id, "last_emotion", "frustrated"))
    ctx_str   = mem.recall_as_context("client", client_id)
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
from typing import Literal

from paths import resolve_data_file

# ---------------------------------------------------------------------------
# PII redaction (email only — phone not stored in memory values)
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}')


def _redact(text: str) -> str:
    return _EMAIL_RE.sub("[EMAIL]", str(text))


# ---------------------------------------------------------------------------
# MemoryItem
# ---------------------------------------------------------------------------

@dataclass
class MemoryItem:
    scope:      Literal["ticket", "client", "account"]
    scope_id:   str
    key:        str
    value:      str
    created_at: str
    expires_at: str
    checksum:   str = ""

    def __post_init__(self) -> None:
        self.value    = _redact(self.value)
        self.checksum = hashlib.sha256(
            (self.scope_id + self.key + self.value).encode()
        ).hexdigest()[:8]

    def is_expired(self) -> bool:
        try:
            exp = datetime.fromisoformat(self.expires_at)
            now = datetime.now(UTC).replace(tzinfo=None)
            return exp < now
        except (ValueError, TypeError):
            return True


# ---------------------------------------------------------------------------
# ScopedMemory
# ---------------------------------------------------------------------------

class ScopedMemory:
    MAX_ITEMS_PER_SCOPE = 20

    def __init__(self, company: str = "default") -> None:
        db_path       = resolve_data_file("memory.db", company)
        self._conn    = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_table()

    # ── Schema ────────────────────────────────────────────────────────────

    def _create_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                scope      TEXT NOT NULL,
                scope_id   TEXT NOT NULL,
                key        TEXT NOT NULL,
                value      TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                checksum   TEXT NOT NULL,
                UNIQUE(scope, scope_id, key)
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_scope "
            "ON memory(scope, scope_id, expires_at)"
        )
        self._conn.commit()

    # ── Write ─────────────────────────────────────────────────────────────

    def store(self, item: MemoryItem) -> None:
        """Upsert a MemoryItem, then enforce the per-scope cap."""
        self._conn.execute(
            """
            INSERT INTO memory(scope, scope_id, key, value, created_at, expires_at, checksum)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope, scope_id, key) DO UPDATE SET
                value      = excluded.value,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at,
                checksum   = excluded.checksum
            """,
            (
                item.scope, item.scope_id, item.key, item.value,
                item.created_at, item.expires_at, item.checksum,
            ),
        )
        self._conn.commit()
        self._enforce_cap(item.scope, item.scope_id)

    def _enforce_cap(self, scope: str, scope_id: str) -> None:
        """Delete oldest items if the per-scope count exceeds MAX_ITEMS_PER_SCOPE."""
        rows = self._conn.execute(
            "SELECT id FROM memory WHERE scope = ? AND scope_id = ? "
            "ORDER BY created_at DESC",
            (scope, scope_id),
        ).fetchall()

        if len(rows) > self.MAX_ITEMS_PER_SCOPE:
            overflow_ids = [r["id"] for r in rows[self.MAX_ITEMS_PER_SCOPE:]]
            placeholders = ",".join("?" * len(overflow_ids))
            self._conn.execute(
                f"DELETE FROM memory WHERE id IN ({placeholders})", overflow_ids
            )
            self._conn.commit()

    # ── Read ──────────────────────────────────────────────────────────────

    def recall(self, scope: str, scope_id: str) -> list[MemoryItem]:
        """Return all non-expired items for this scope, newest first."""
        now = datetime.now(UTC).replace(tzinfo=None).isoformat()
        rows = self._conn.execute(
            """
            SELECT scope, scope_id, key, value, created_at, expires_at, checksum
            FROM   memory
            WHERE  scope = ? AND scope_id = ? AND expires_at > ?
            ORDER  BY created_at DESC
            """,
            (scope, scope_id, now),
        ).fetchall()
        return [MemoryItem(*tuple(r)) for r in rows]

    def recall_as_context(self, scope: str, scope_id: str) -> str:
        """Return a compact text block suitable for injection into a system prompt."""
        items = self.recall(scope, scope_id)
        if not items:
            return ""
        return "\n".join(f"[MEMORY:{i.key}] {i.value}" for i in items)

    # ── Maintenance ───────────────────────────────────────────────────────

    def purge_expired(self) -> int:
        """Delete all expired items across all scopes. Returns count deleted."""
        now = datetime.now(UTC).replace(tzinfo=None).isoformat()
        cur = self._conn.execute(
            "DELETE FROM memory WHERE expires_at <= ?", (now,)
        )
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def make_item(
    scope:     str,
    scope_id:  str,
    key:       str,
    value:     str,
    ttl_hours: int = 24,
) -> MemoryItem:
    """Create a MemoryItem with computed timestamps."""
    now = datetime.now(UTC).replace(tzinfo=None)
    return MemoryItem(
        scope=      scope,
        scope_id=   scope_id,
        key=        key,
        value=      str(value),
        created_at= now.isoformat(),
        expires_at= (now + timedelta(hours=ttl_hours)).isoformat(),
    )
