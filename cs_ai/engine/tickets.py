"""
tickets.py — Ticket lifecycle management backed by SQLite (tickets.db).

Each ticket represents one customer conversation thread across any channel.
SLA deadlines are computed from config.json["sla"][priority]["response_hours"].
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone, UTC
from typing import List, Optional
from paths import config_path as _config_path, tickets_db_path


def _now() -> datetime:
    """Return current UTC time as a naive datetime (timezone info stripped)."""
    return datetime.now(UTC).replace(tzinfo=None)

# ---------------------------------------------------------------------------
# Config helper
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    with open(_config_path(), "r", encoding="utf-8") as f:
        return json.load(f)


_CONFIG: Optional[dict] = None

def _cfg() -> dict:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = _load_config()
    return _CONFIG


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TICKET_STATUSES = [
    "new", "triaged", "drafting", "pending_approval",
    "sent", "resolved", "closed",
]
TICKET_PRIORITIES = ["Normal", "High", "Critical"]

DB_PATH = tickets_db_path()


# ---------------------------------------------------------------------------
# Ticket dataclass
# ---------------------------------------------------------------------------

@dataclass
class Ticket:
    ticket_id:      str
    status:         str           # one of TICKET_STATUSES
    priority:       str           # one of TICKET_PRIORITIES
    customer_email: str
    customer_name:  str
    subject:        str
    channel:        str           # "email", "manual", …
    created_at:     datetime
    updated_at:     datetime
    sla_deadline:   datetime
    emotion:        str = "Neutral"
    intent:         str = "general inquiry"
    confidence:     float = 0.0
    order_id:       Optional[str] = None
    thread_id:      Optional[str] = None
    messages:       List[dict] = field(default_factory=list)
    erp_actions:    List[dict] = field(default_factory=list)
    metadata:       dict = field(default_factory=dict)
    notes:          List[dict] = field(default_factory=list)
    state:          str  = "new"
    version:        int  = 0
    state_history:  List[dict] = field(default_factory=list)
    retry_count:    int  = 0

    # ------------------------------------------------------------------
    def time_to_breach_minutes(self) -> float | None:
        """Return minutes until SLA deadline (negative = already breached)."""
        if not self.sla_deadline:
            return None
        deadline = self.sla_deadline.replace(tzinfo=None)
        return (deadline - datetime.now().replace(tzinfo=None)).total_seconds() / 60

    def sla_urgency(self) -> str:
        """Classify urgency based on minutes remaining to SLA deadline."""
        ttb = self.time_to_breach_minutes()
        if ttb is None: return "normal"
        if ttb < 0:     return "breached"
        if ttb < 30:    return "critical"
        if ttb < 120:   return "high"
        return "normal"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"]   = self.created_at.isoformat()
        d["updated_at"]   = self.updated_at.isoformat()
        d["sla_deadline"] = self.sla_deadline.isoformat()
        return d

    @staticmethod
    def from_row(row: dict) -> "Ticket":
        """Reconstruct a Ticket from a SQLite row dict."""
        return Ticket(
            ticket_id=      row["ticket_id"],
            status=         row["status"],
            priority=       row["priority"],
            customer_email= row["customer_email"],
            customer_name=  row["customer_name"],
            subject=        row["subject"],
            channel=        row["channel"],
            created_at=     _parse_dt(row["created_at"]),
            updated_at=     _parse_dt(row["updated_at"]),
            sla_deadline=   _parse_dt(row["sla_deadline"]),
            emotion=        row.get("emotion", "Neutral"),
            intent=         row.get("intent", "general inquiry"),
            confidence=     float(row.get("confidence", 0.0)),
            order_id=       row.get("order_id"),
            thread_id=      row.get("thread_id"),
            messages=       json.loads(row.get("messages", "[]")),
            erp_actions=    json.loads(row.get("erp_actions", "[]")),
            metadata=       json.loads(row.get("metadata", "{}")),
            notes=          json.loads(row.get("notes", "[]")),
            state=          row.get("state", "new"),
            version=        int(row.get("version") or 0),
            state_history=  json.loads(row.get("state_history", "[]")),
            retry_count=    int(row.get("retry_count") or 0),
        )


def _parse_dt(value: str) -> datetime:
    """Parse ISO datetime string, return UTC-naive datetime."""
    if not value:
        return _now()
    try:
        dt = datetime.fromisoformat(value)
        # Strip timezone info for uniform naive UTC storage
        if dt.tzinfo is not None:
            dt = dt.utctimetuple()
            dt = datetime(*dt[:6])
        return dt
    except ValueError:
        return _now()


# ---------------------------------------------------------------------------
# TicketManager
# ---------------------------------------------------------------------------

class TicketManager:
    """
    Persist and query tickets in SQLite.

    All datetimes are stored as ISO strings in UTC.
    List/dict fields (messages, erp_actions, metadata) are stored as JSON text.
    """

    def __init__(self, db_path: str = DB_PATH):
        self._db_path = db_path
        self._init_db()

    # ---- DB setup ---------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id      TEXT PRIMARY KEY,
                    status         TEXT NOT NULL DEFAULT 'new',
                    priority       TEXT NOT NULL DEFAULT 'Normal',
                    customer_email TEXT NOT NULL DEFAULT '',
                    customer_name  TEXT NOT NULL DEFAULT '',
                    subject        TEXT NOT NULL DEFAULT '',
                    channel        TEXT NOT NULL DEFAULT 'manual',
                    created_at     TEXT NOT NULL,
                    updated_at     TEXT NOT NULL,
                    sla_deadline   TEXT NOT NULL,
                    emotion        TEXT DEFAULT 'Neutral',
                    intent         TEXT DEFAULT 'general inquiry',
                    confidence     REAL DEFAULT 0.0,
                    order_id       TEXT,
                    thread_id      TEXT,
                    messages       TEXT DEFAULT '[]',
                    erp_actions    TEXT DEFAULT '[]',
                    metadata       TEXT DEFAULT '{}',
                    notes          TEXT DEFAULT '[]',
                    state          TEXT DEFAULT 'new',
                    version        INTEGER DEFAULT 0,
                    state_history  TEXT DEFAULT '[]',
                    retry_count    INTEGER DEFAULT 0
                )
            """)
            # Migrate existing DBs that predate newer columns
            existing_cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(tickets)").fetchall()
            }
            _migrations = [
                ("notes",          "TEXT DEFAULT '[]'"),
                ("state",          "TEXT DEFAULT 'new'"),
                ("version",        "INTEGER DEFAULT 0"),
                ("state_history",  "TEXT DEFAULT '[]'"),
                ("retry_count",    "INTEGER DEFAULT 0"),
            ]
            for _col, _defn in _migrations:
                if _col not in existing_cols:
                    conn.execute(
                        f"ALTER TABLE tickets ADD COLUMN {_col} {_defn}"
                    )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp     TEXT NOT NULL,
                    company       TEXT NOT NULL,
                    ticket_id     TEXT,
                    agent         TEXT NOT NULL,
                    action        TEXT NOT NULL,
                    detail        TEXT,
                    before_value  TEXT,
                    after_value   TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kb_usage (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp      TEXT NOT NULL,
                    kb_entry_id    TEXT NOT NULL,
                    ticket_id      TEXT,
                    relevance      REAL DEFAULT 0.0,
                    draft_approved INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    # ---- SLA helpers ------------------------------------------------------

    @staticmethod
    def compute_sla_deadline(priority: str, created_at: datetime) -> datetime:
        """
        Compute the response SLA deadline for the given priority.
        Uses config.json["sla"][priority]["response_hours"].
        Falls back to 24 hours if not found.
        """
        sla_cfg = _cfg().get("sla", {})
        hours = sla_cfg.get(priority, {}).get("response_hours", 24)
        return created_at + timedelta(hours=hours)

    @staticmethod
    def get_sla_status(ticket: Ticket) -> str:
        """
        Returns:
          "breached" — deadline has passed
          "warning"  — less than 25% of total SLA time remaining
          "on_track" — plenty of time left
        """
        now = _now()
        total = (ticket.sla_deadline - ticket.created_at).total_seconds()
        remaining = (ticket.sla_deadline - now).total_seconds()

        if remaining <= 0:
            return "breached"
        if total > 0 and remaining <= total * 0.25:
            return "warning"
        return "on_track"

    # ---- CRUD -------------------------------------------------------------

    def create_ticket(self, inbound_message=None, **kwargs) -> Ticket:
        """
        Create a new ticket.

        Pass either an InboundMessage (from channels.py) as first arg,
        or keyword args directly:
            customer_email, customer_name, subject, channel, body,
            priority, thread_id, metadata
        """
        now = _now()
        ticket_id = str(uuid.uuid4())

        if inbound_message is not None:
            # Build from InboundMessage
            from channels import InboundMessage as _IM
            msg: _IM = inbound_message
            customer_email = msg.sender
            customer_name  = msg.sender_name or msg.sender
            subject        = msg.subject or "(no subject)"
            channel        = msg.channel
            thread_id      = kwargs.get("thread_id", msg.message_id)
            priority       = kwargs.get("priority", "Normal")
            metadata       = kwargs.get("metadata", {})
            initial_body   = msg.body
        else:
            customer_email = kwargs.get("customer_email", "")
            customer_name  = kwargs.get("customer_name", customer_email)
            subject        = kwargs.get("subject", "(no subject)")
            channel        = kwargs.get("channel", "manual")
            thread_id      = kwargs.get("thread_id")
            priority       = kwargs.get("priority", "Normal")
            metadata       = kwargs.get("metadata", {})
            initial_body   = kwargs.get("body", "")

        sla_deadline = self.compute_sla_deadline(priority, now)

        # Stamp original priority so manual overrides can be detected later
        if "original_priority" not in metadata:
            metadata = {**metadata, "original_priority": priority}

        first_message = {
            "role":      "customer",
            "content":   initial_body,
            "timestamp": now.isoformat(),
        }

        ticket = Ticket(
            ticket_id=      ticket_id,
            status=         "new",
            priority=       priority,
            customer_email= customer_email,
            customer_name=  customer_name,
            subject=        subject,
            channel=        channel,
            created_at=     now,
            updated_at=     now,
            sla_deadline=   sla_deadline,
            thread_id=      thread_id,
            messages=       [first_message] if initial_body else [],
            metadata=       metadata,
        )

        with self._connect() as conn:
            conn.execute("""
                INSERT INTO tickets VALUES (
                    :ticket_id, :status, :priority,
                    :customer_email, :customer_name, :subject, :channel,
                    :created_at, :updated_at, :sla_deadline,
                    :emotion, :intent, :confidence,
                    :order_id, :thread_id,
                    :messages, :erp_actions, :metadata, :notes,
                    :state, :version, :state_history, :retry_count
                )
            """, {
                "ticket_id":      ticket.ticket_id,
                "status":         ticket.status,
                "priority":       ticket.priority,
                "customer_email": ticket.customer_email,
                "customer_name":  ticket.customer_name,
                "subject":        ticket.subject,
                "channel":        ticket.channel,
                "created_at":     ticket.created_at.isoformat(),
                "updated_at":     ticket.updated_at.isoformat(),
                "sla_deadline":   ticket.sla_deadline.isoformat(),
                "emotion":        ticket.emotion,
                "intent":         ticket.intent,
                "confidence":     ticket.confidence,
                "order_id":       ticket.order_id,
                "thread_id":      ticket.thread_id,
                "messages":       json.dumps(ticket.messages),
                "erp_actions":    json.dumps(ticket.erp_actions),
                "metadata":       json.dumps(ticket.metadata),
                "notes":          json.dumps(ticket.notes),
                "state":          ticket.state,
                "version":        ticket.version,
                "state_history":  json.dumps(ticket.state_history),
                "retry_count":    ticket.retry_count,
            })
            conn.commit()

        return ticket

    def get_ticket(self, ticket_id: str) -> Optional[Ticket]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
        if row is None:
            return None
        return Ticket.from_row(dict(row))

    def update_ticket(self, ticket_id: str, **changes) -> Optional[Ticket]:
        """
        Update any scalar or JSON field of a ticket by keyword.
        updated_at is always refreshed automatically.
        List/dict values (messages, erp_actions, metadata) are accepted as Python objects.
        """
        if not changes:
            return self.get_ticket(ticket_id)

        changes["updated_at"] = _now().isoformat()

        # Serialize list/dict fields
        for key in ("messages", "erp_actions", "metadata", "notes", "state_history"):
            if key in changes and not isinstance(changes[key], str):
                changes[key] = json.dumps(changes[key])

        # Serialize datetimes
        for key in ("created_at", "sla_deadline"):
            if key in changes and isinstance(changes[key], datetime):
                changes[key] = changes[key].isoformat()

        set_clause = ", ".join(f"{k} = :{k}" for k in changes)
        changes["ticket_id"] = ticket_id

        with self._connect() as conn:
            conn.execute(
                f"UPDATE tickets SET {set_clause} WHERE ticket_id = :ticket_id",
                changes,
            )
            conn.commit()

        return self.get_ticket(ticket_id)

    def add_message(self, ticket_id: str, message: dict) -> Optional[Ticket]:
        """Append a message dict {role, content, timestamp} to a ticket's thread."""
        ticket = self.get_ticket(ticket_id)
        if ticket is None:
            return None
        ticket.messages.append(message)
        return self.update_ticket(ticket_id, messages=ticket.messages)

    def add_erp_action(self, ticket_id: str, action: dict) -> Optional[Ticket]:
        """Append an ERP action record to the ticket."""
        ticket = self.get_ticket(ticket_id)
        if ticket is None:
            return None
        ticket.erp_actions.append(action)
        return self.update_ticket(ticket_id, erp_actions=ticket.erp_actions)

    def add_note(self, ticket_id: str, agent: str, note: str) -> Optional[Ticket]:
        """Append an internal note (never sent to customer). Notes are append-only."""
        ticket = self.get_ticket(ticket_id)
        if ticket is None:
            return None
        ticket.notes.append({
            "agent":     agent,
            "timestamp": _now().isoformat(),
            "text":      note,
        })
        return self.update_ticket(ticket_id, notes=ticket.notes)

    def get_notes(self, ticket_id: str) -> list:
        """Return the list of internal note dicts for a ticket."""
        ticket = self.get_ticket(ticket_id)
        if ticket is None:
            return []
        return ticket.notes

    def list_tickets(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> List[Ticket]:
        """Return tickets, optionally filtered by status and/or priority."""
        query  = "SELECT * FROM tickets WHERE 1=1"
        params: list = []

        if status:
            query  += " AND status = ?"
            params.append(status)
        if priority:
            query  += " AND priority = ?"
            params.append(priority)

        query += " ORDER BY created_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [Ticket.from_row(dict(r)) for r in rows]

    def find_by_thread(self, thread_id: str) -> Optional[Ticket]:
        """
        Return the most recent open ticket with the given thread_id, or None.
        Ignores closed/resolved tickets so reopened threads start fresh.
        """
        if not thread_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM tickets
                WHERE thread_id = ?
                  AND status NOT IN ('resolved', 'closed')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
        if row is None:
            return None
        return Ticket.from_row(dict(row))

    # ---- Audit log --------------------------------------------------------

    def log_action(
        self,
        ticket_id: Optional[str],
        agent: str,
        action: str,
        detail: Optional[str] = None,
        before_value: Optional[str] = None,
        after_value: Optional[str] = None,
    ) -> None:
        """
        Append one row to audit_log.  Never raises — silently swallows all errors
        so a logging failure never interrupts the user-facing flow.

        Action types:
            draft_generated, draft_modified, draft_approved, draft_rejected,
            response_sent, erp_action_executed, erp_action_rejected,
            escalation_fired, ticket_created, ticket_resolved, ticket_reassigned
        """
        try:
            company = os.environ.get("CS_AI_COMPANY", "default")
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO audit_log
                        (timestamp, company, ticket_id, agent, action,
                         detail, before_value, after_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _now().isoformat(),
                        company,
                        ticket_id,
                        agent or "system",
                        action,
                        detail,
                        before_value,
                        after_value,
                    ),
                )
                conn.commit()
        except Exception:
            pass

    def get_audit_trail(self, ticket_id: str) -> list[dict]:
        """Return all audit_log rows for a ticket, newest first."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM audit_log WHERE ticket_id = ? ORDER BY id DESC",
                    (ticket_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def export_audit_csv(self, output_path: str, days: int = 30) -> None:
        """Export recent audit_log rows (last N days) to a CSV file."""
        import csv
        from datetime import timedelta

        cutoff = (_now() - timedelta(days=days)).isoformat()
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM audit_log WHERE timestamp >= ? ORDER BY id DESC",
                    (cutoff,),
                ).fetchall()
        except Exception:
            rows = []

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=dict(rows[0]).keys())
                writer.writeheader()
                for row in rows:
                    writer.writerow(dict(row))

    def auto_close_stale(self, days: int = None) -> int:
        """
        Close tickets that have been in 'sent' status without a customer
        reply for longer than `days` days.
        Returns the number of tickets closed.
        """
        if days is None:
            days = int(_cfg().get("sla", {}).get("auto_close_days", 7))

        cutoff = (_now() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE status = 'sent' AND updated_at < ?",
                (cutoff,),
            ).fetchall()

        stale = [Ticket.from_row(dict(r)) for r in rows]
        reason = f"Auto-closed after {days} days without customer reply"

        for ticket in stale:
            new_meta = {**(ticket.metadata or {}), "auto_closed": True}
            self.update_ticket(ticket.ticket_id, status="closed", metadata=new_meta)
            self.add_note(ticket.ticket_id, "system", reason)
            self.log_action(
                ticket_id=ticket.ticket_id,
                agent="system",
                action="auto_closed",
                detail=reason,
            )

        return len(stale)

    # ---- KB usage tracking ------------------------------------------------

    def log_kb_usage(
        self, entry_id: str, ticket_id: Optional[str], relevance: float
    ) -> None:
        """Record that a KB entry was retrieved for a ticket. Never raises."""
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO kb_usage (timestamp, kb_entry_id, ticket_id, relevance) "
                    "VALUES (?, ?, ?, ?)",
                    (_now().isoformat(), entry_id, ticket_id, float(relevance)),
                )
                conn.commit()
        except Exception:
            pass

    def mark_kb_approved(self, ticket_id: str) -> None:
        """Mark all KB usage rows for ticket_id as draft_approved=1."""
        if not ticket_id:
            return
        try:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE kb_usage SET draft_approved = 1 WHERE ticket_id = ?",
                    (ticket_id,),
                )
                conn.commit()
        except Exception:
            pass

    # ---- Aggregate helpers ------------------------------------------------

    def sla_summary(self) -> dict:
        """
        Return counts of open tickets by SLA status.
        {"on_track": N, "warning": N, "breached": N}
        """
        open_statuses = ("new", "triaged", "drafting", "pending_approval")
        tickets = []
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM tickets WHERE status IN ({','.join('?'*len(open_statuses))})",
                open_statuses,
            ).fetchall()
        tickets = [Ticket.from_row(dict(r)) for r in rows]

        summary = {"on_track": 0, "warning": 0, "breached": 0}
        for t in tickets:
            summary[self.get_sla_status(t)] += 1
        return summary


    def count_open(self) -> int:
        """Return the count of tickets not in resolved or closed status."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM tickets "
                "WHERE status NOT IN ('resolved', 'closed')"
            ).fetchone()
        return row[0] if row else 0


# ---------------------------------------------------------------------------
# Module-level KB usage helper — usable without a TicketManager instance
# ---------------------------------------------------------------------------

def log_kb_usage(entry_id: str, ticket_id: Optional[str], relevance: float) -> None:
    """Log a KB entry retrieval. Connects directly to the DB; never raises."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO kb_usage (timestamp, kb_entry_id, ticket_id, relevance) "
                "VALUES (?, ?, ?, ?)",
                (_now().isoformat(), entry_id, ticket_id, float(relevance)),
            )
            conn.commit()
    except Exception:
        pass
