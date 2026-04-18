"""
tests/unit/test_health_score.py — Unit tests for HealthScoreComputer.

Uses an in-memory SQLite tickets DB (patched tickets_db_path) so no
real database is written during the test run.

Run with:  pytest tests/unit/test_health_score.py -v
"""

import sys
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine"))

import pytest
import health_score as _hs_module
from health_score import HealthScoreComputer, HealthScore, _compute_label, _compute_trend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _create_db(path: str) -> None:
    """Create a minimal tickets table."""
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE tickets (
                ticket_id      TEXT PRIMARY KEY,
                status         TEXT NOT NULL DEFAULT 'new',
                priority       TEXT NOT NULL DEFAULT 'Normal',
                customer_email TEXT NOT NULL DEFAULT '',
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                sla_deadline   TEXT NOT NULL,
                emotion        TEXT DEFAULT 'Neutral',
                confidence     REAL DEFAULT 0.0,
                state          TEXT DEFAULT 'new'
            )
        """)
        conn.commit()


def _insert(
    conn:           sqlite3.Connection,
    ticket_id:      str,
    email:          str,
    status:         str   = "sent",
    state:          str   = "sent",
    emotion:        str   = "Neutral",
    confidence:     float = 0.8,
    sla_ok:         bool  = True,
    created_offset: int   = 0,     # hours before now
) -> None:
    """Insert one ticket row.  sla_ok=False puts the deadline in the past."""
    now     = _utcnow()
    created = (now - timedelta(hours=max(created_offset, 1))).isoformat()
    updated = (now - timedelta(minutes=5)).isoformat()
    sla     = (
        (now + timedelta(hours=24)).isoformat()
        if sla_ok
        else (now - timedelta(hours=1)).isoformat()
    )
    conn.execute(
        "INSERT INTO tickets "
        "(ticket_id, status, priority, customer_email, "
        " created_at, updated_at, sla_deadline, emotion, confidence, state) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (ticket_id, status, "Normal", email, created, updated, sla, emotion, confidence, state),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "tickets.db")
    _create_db(db_path)
    return db_path


@pytest.fixture
def computer(db):
    with patch.object(_hs_module, "tickets_db_path", return_value=db):
        yield HealthScoreComputer(), db


# ---------------------------------------------------------------------------
# No tickets → healthy defaults
# ---------------------------------------------------------------------------

class TestNoTickets:
    def test_label_is_healthy(self, computer):
        hsc, _ = computer
        hs = hsc.compute("nobody@example.com")
        assert hs.label == "healthy"

    def test_score_is_one(self, computer):
        hsc, _ = computer
        hs = hsc.compute("nobody@example.com")
        assert hs.score == 1.0

    def test_open_tickets_zero(self, computer):
        hsc, _ = computer
        hs = hsc.compute("nobody@example.com")
        assert hs.open_tickets == 0

    def test_trend_is_stable(self, computer):
        hsc, _ = computer
        hs = hsc.compute("nobody@example.com")
        assert hs.emotion_trend == "stable"


# ---------------------------------------------------------------------------
# 100% escalation (+ bad SLA + angry) → critical
# ---------------------------------------------------------------------------

class TestCriticalHealth:
    def test_full_escalation_angry_sla_breach_is_critical(self, computer):
        hsc, db = computer
        with sqlite3.connect(db) as conn:
            for i in range(3):
                _insert(
                    conn, f"t{i}", "critical@example.com",
                    status="escalated", state="escalated",
                    emotion="Angry", confidence=0.5, sla_ok=False,
                )
        hs = hsc.compute("critical@example.com")
        assert hs.label == "critical"

    def test_critical_score_below_045(self, computer):
        hsc, db = computer
        with sqlite3.connect(db) as conn:
            for i in range(3):
                _insert(
                    conn, f"tc{i}", "crit2@example.com",
                    status="escalated", state="escalated",
                    emotion="Angry", confidence=0.5, sla_ok=False,
                )
        hs = hsc.compute("crit2@example.com")
        assert hs.score < 0.45

    def test_escalation_rate_is_one(self, computer):
        hsc, db = computer
        with sqlite3.connect(db) as conn:
            for i in range(2):
                _insert(
                    conn, f"te{i}", "esc@example.com",
                    status="escalated", state="escalated",
                    emotion="Angry", confidence=0.5, sla_ok=False,
                )
        hs = hsc.compute("esc@example.com")
        assert hs.escalation_rate == 1.0


# ---------------------------------------------------------------------------
# Score in [0.45, 0.75) → at_risk
# ---------------------------------------------------------------------------

class TestAtRiskHealth:
    def test_mixed_signals_produce_at_risk(self, computer):
        """
        0% escalation, frustrated emotion, 50% SLA, conf=0.8:
          1.0*0.30 + 0.8*0.25 + 0.5*0.25 + 0.4*0.20 = 0.705 → at_risk
        """
        hsc, db = computer
        with sqlite3.connect(db) as conn:
            _insert(conn, "ar1", "atrisk@example.com",
                    emotion="Frustrated", confidence=0.8, sla_ok=True)
            _insert(conn, "ar2", "atrisk@example.com",
                    emotion="Frustrated", confidence=0.8, sla_ok=False)
        hs = hsc.compute("atrisk@example.com")
        assert hs.label == "at_risk"
        assert 0.45 <= hs.score < 0.75

    def test_at_risk_label_boundaries(self):
        assert _compute_label(0.45) == "at_risk"
        assert _compute_label(0.74) == "at_risk"
        assert _compute_label(0.75) == "healthy"
        assert _compute_label(0.44) == "critical"


# ---------------------------------------------------------------------------
# Emotion trend
# ---------------------------------------------------------------------------

class TestEmotionTrend:
    def test_last_half_angry_is_worsening(self, computer):
        """
        4 tickets: 2 neutral first, 2 angry last → worsening
        """
        hsc, db = computer
        with sqlite3.connect(db) as conn:
            _insert(conn, "tr1", "trend@example.com",
                    emotion="Neutral", created_offset=10)
            _insert(conn, "tr2", "trend@example.com",
                    emotion="Neutral", created_offset=8)
            _insert(conn, "tr3", "trend@example.com",
                    emotion="Angry", created_offset=4)
            _insert(conn, "tr4", "trend@example.com",
                    emotion="Angry", created_offset=2)
        hs = hsc.compute("trend@example.com")
        assert hs.emotion_trend == "worsening"

    def test_last_half_calm_is_improving(self, computer):
        hsc, db = computer
        with sqlite3.connect(db) as conn:
            _insert(conn, "im1", "improve@example.com",
                    emotion="Angry", created_offset=10)
            _insert(conn, "im2", "improve@example.com",
                    emotion="Frustrated", created_offset=8)
            _insert(conn, "im3", "improve@example.com",
                    emotion="Neutral", created_offset=4)
            _insert(conn, "im4", "improve@example.com",
                    emotion="Satisfied", created_offset=2)
        hs = hsc.compute("improve@example.com")
        assert hs.emotion_trend == "improving"

    def test_stable_when_consistent_emotion(self, computer):
        hsc, db = computer
        with sqlite3.connect(db) as conn:
            for i in range(4):
                _insert(conn, f"st{i}", "stable@example.com",
                        emotion="Neutral", created_offset=10 - i * 2)
        hs = hsc.compute("stable@example.com")
        assert hs.emotion_trend == "stable"

    def test_single_ticket_is_stable(self, computer):
        hsc, db = computer
        with sqlite3.connect(db) as conn:
            _insert(conn, "s1", "solo@example.com", emotion="Angry")
        hs = hsc.compute("solo@example.com")
        assert hs.emotion_trend == "stable"

    def test_trend_helper_directly(self):
        assert _compute_trend([0.75, 0.75, 0.0, 0.0]) == "worsening"
        assert _compute_trend([0.0, 0.0, 0.75, 1.0])  == "improving"
        assert _compute_trend([0.75, 0.75, 0.75, 0.7]) == "stable"
        assert _compute_trend([0.5])                   == "stable"


# ---------------------------------------------------------------------------
# Defaults for missing values
# ---------------------------------------------------------------------------

class TestDefaults:
    def test_zero_confidence_replaced_by_default(self, computer):
        hsc, db = computer
        with sqlite3.connect(db) as conn:
            _insert(conn, "d1", "def@example.com", confidence=0.0)
        hs = hsc.compute("def@example.com")
        # avg_confidence should be 0.8 (the default), not 0.0
        assert hs.avg_confidence == 0.8

    def test_missing_emotion_treated_as_neutral(self, computer):
        hsc, db = computer
        with sqlite3.connect(db) as conn:
            # Insert without emotion (will default to empty string via the schema default)
            conn.execute(
                "INSERT INTO tickets "
                "(ticket_id, status, priority, customer_email, "
                " created_at, updated_at, sla_deadline, confidence, state) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                ("noemo", "sent", "Normal", "noemo@example.com",
                 (_utcnow() - timedelta(hours=1)).isoformat(),
                 _utcnow().isoformat(),
                 (_utcnow() + timedelta(hours=24)).isoformat(),
                 0.8, "sent"),
            )
            conn.commit()
        hs = hsc.compute("noemo@example.com")
        assert hs.label == "healthy"


# ---------------------------------------------------------------------------
# SLA compliance
# ---------------------------------------------------------------------------

class TestSLACompliance:
    def test_all_sla_met_gives_one(self, computer):
        hsc, db = computer
        with sqlite3.connect(db) as conn:
            for i in range(3):
                _insert(conn, f"sla{i}", "slagood@example.com",
                        status="sent", sla_ok=True)
        hs = hsc.compute("slagood@example.com")
        assert hs.sla_compliance_rate == 1.0

    def test_all_sla_breached_gives_zero(self, computer):
        hsc, db = computer
        with sqlite3.connect(db) as conn:
            for i in range(3):
                # status "new" (open) + sla in the past → breached
                _insert(conn, f"slabad{i}", "slabad@example.com",
                        status="new", state="new", sla_ok=False)
        hs = hsc.compute("slabad@example.com")
        assert hs.sla_compliance_rate == 0.0


# ---------------------------------------------------------------------------
# Open tickets count
# ---------------------------------------------------------------------------

class TestOpenTickets:
    def test_open_tickets_counted(self, computer):
        hsc, db = computer
        with sqlite3.connect(db) as conn:
            _insert(conn, "op1", "open@example.com", status="new",      state="new")
            _insert(conn, "op2", "open@example.com", status="triaged",  state="triaged")
            _insert(conn, "op3", "open@example.com", status="resolved", state="resolved")
        hs = hsc.compute("open@example.com")
        assert hs.open_tickets == 2

    def test_resolved_not_open(self, computer):
        hsc, db = computer
        with sqlite3.connect(db) as conn:
            _insert(conn, "cl1", "closed@example.com", status="closed", state="closed")
            _insert(conn, "cl2", "closed@example.com", status="resolved", state="resolved")
        hs = hsc.compute("closed@example.com")
        assert hs.open_tickets == 0


# ---------------------------------------------------------------------------
# Scope isolation — different emails don't bleed into each other
# ---------------------------------------------------------------------------

class TestScopeIsolation:
    def test_different_emails_isolated(self, computer):
        hsc, db = computer
        with sqlite3.connect(db) as conn:
            _insert(conn, "i1", "a@example.com", emotion="Satisfied", confidence=0.9, sla_ok=True)
            _insert(conn, "i2", "b@example.com",
                    emotion="Angry", confidence=0.5, sla_ok=False,
                    status="escalated", state="escalated")
        hs_a = hsc.compute("a@example.com")
        hs_b = hsc.compute("b@example.com")
        assert hs_a.score > hs_b.score
        assert hs_a.label == "healthy"
