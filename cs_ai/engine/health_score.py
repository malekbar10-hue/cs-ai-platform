"""
health_score.py — CustomerHealthScore computed from ticket history.

Score formula (weighted average, 0.0 = critical, 1.0 = healthy):
  (1 - escalation_rate) * 0.30
  + avg_confidence      * 0.25
  + sla_compliance_rate * 0.25
  + avg_emotion_score   * 0.20

Emotion scores: Satisfied/Calm=1.0, Neutral=0.75, Anxious=0.5,
                Frustrated=0.4, Urgent=0.2, Angry=0.0

Labels: >= 0.75 → "healthy", >= 0.45 → "at_risk", < 0.45 → "critical"
Missing columns (emotion, confidence, escalated) → graceful defaults.
Read-only: never writes to the tickets DB.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC

from paths import tickets_db_path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EMOTION_SCORE: dict[str, float] = {
    "satisfied":  1.0,
    "calm":       1.0,
    "neutral":    0.75,
    "anxious":    0.5,
    "frustrated": 0.4,
    "urgent":     0.2,
    "angry":      0.0,
}
_DEFAULT_EMOTION_SCORE = 0.75   # unknown emotion → treat as neutral
_DEFAULT_CONFIDENCE    = 0.8    # missing or zero confidence → use this

_OPEN_STATUSES = frozenset({
    "new", "triaged", "drafting", "pending_approval",
    "review", "blocked", "fallback_draft",
})


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _emotion_to_score(emotion: str) -> float:
    return _EMOTION_SCORE.get(emotion.lower().strip(), _DEFAULT_EMOTION_SCORE)


def _compute_label(score: float) -> str:
    if score >= 0.75:
        return "healthy"
    if score >= 0.45:
        return "at_risk"
    return "critical"


def _compute_trend(emotion_scores: list[float]) -> str:
    """Compare first half vs second half average emotion score."""
    if len(emotion_scores) < 2:
        return "stable"
    mid        = len(emotion_scores) // 2
    first_avg  = sum(emotion_scores[:mid]) / mid
    second_avg = sum(emotion_scores[mid:]) / len(emotion_scores[mid:])
    diff = second_avg - first_avg
    if diff > 0.1:
        return "improving"
    if diff < -0.1:
        return "worsening"
    return "stable"


# ---------------------------------------------------------------------------
# HealthScore dataclass
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# HealthScoreComputer
# ---------------------------------------------------------------------------

class HealthScoreComputer:

    def __init__(self, company: str | None = None) -> None:
        self._db_path = tickets_db_path(company)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _existing_columns(self, conn: sqlite3.Connection) -> set[str]:
        return {r[1] for r in conn.execute("PRAGMA table_info(tickets)").fetchall()}

    # ── Public API ────────────────────────────────────────────────────────

    def compute(self, customer_email: str, lookback_days: int = 30) -> HealthScore:
        """
        Query tickets DB for the last N days for this customer and return a
        HealthScore.  Missing columns fall back to safe defaults.
        """
        cutoff = (_now() - timedelta(days=lookback_days)).isoformat()

        try:
            with self._connect() as conn:
                present = self._existing_columns(conn)

                # Build SELECT list from only the columns that exist
                select = ["ticket_id", "status", "created_at", "updated_at", "sla_deadline"]
                for col in ("emotion", "confidence", "state"):
                    if col in present:
                        select.append(col)

                rows = conn.execute(
                    f"SELECT {', '.join(select)} FROM tickets "
                    "WHERE customer_email = ? AND created_at >= ? "
                    "ORDER BY created_at ASC",
                    (customer_email, cutoff),
                ).fetchall()
        except Exception:
            rows = []

        if not rows:
            return HealthScore(
                customer_email=      customer_email,
                score=               1.0,
                label=               "healthy",
                escalation_rate=     0.0,
                avg_confidence=      1.0,
                emotion_trend=       "stable",
                sla_compliance_rate= 1.0,
                open_tickets=        0,
                computed_at=         _now().isoformat(),
            )

        total            = len(rows)
        escalated_count  = 0
        sla_met_count    = 0
        confidence_vals  : list[float] = []
        emotion_scores   : list[float] = []
        open_count       = 0

        for r in rows:
            d = dict(r)
            status = (d.get("status") or "").lower()
            state  = (d.get("state")  or "").lower()

            # Escalation
            if state == "escalated" or status == "escalated":
                escalated_count += 1

            # SLA compliance
            try:
                sla_dl  = datetime.fromisoformat(d["sla_deadline"])
                updated = datetime.fromisoformat(d["updated_at"])
                if status in ("resolved", "closed", "sent"):
                    if updated <= sla_dl:
                        sla_met_count += 1
                else:
                    if _now() <= sla_dl:
                        sla_met_count += 1
            except (ValueError, KeyError, TypeError):
                sla_met_count += 1  # can't determine → benefit of the doubt

            # Confidence — treat missing/zero as default
            raw_conf = d.get("confidence")
            conf = float(raw_conf) if raw_conf is not None else 0.0
            confidence_vals.append(conf if conf > 0.0 else _DEFAULT_CONFIDENCE)

            # Emotion
            emo = d.get("emotion") or "Neutral"
            emotion_scores.append(_emotion_to_score(emo))

            # Open
            if status in _OPEN_STATUSES or state in _OPEN_STATUSES:
                open_count += 1

        escalation_rate     = escalated_count / total
        avg_confidence      = sum(confidence_vals)  / len(confidence_vals)
        sla_compliance_rate = sla_met_count / total
        avg_emotion_score   = sum(emotion_scores)   / len(emotion_scores)

        raw_score = (
            (1.0 - escalation_rate)  * 0.30
            + avg_confidence         * 0.25
            + sla_compliance_rate    * 0.25
            + avg_emotion_score      * 0.20
        )
        score = round(max(0.0, min(1.0, raw_score)), 4)

        return HealthScore(
            customer_email=      customer_email,
            score=               score,
            label=               _compute_label(score),
            escalation_rate=     round(escalation_rate, 4),
            avg_confidence=      round(avg_confidence, 4),
            emotion_trend=       _compute_trend(emotion_scores),
            sla_compliance_rate= round(sla_compliance_rate, 4),
            open_tickets=        open_count,
            computed_at=         _now().isoformat(),
        )

    def at_risk_customers(self, account_id: str, top_n: int = 10) -> list[HealthScore]:
        """Return top N at-risk or critical customers for the account, sorted by score ascending."""
        try:
            db_path = tickets_db_path(account_id)
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    "SELECT DISTINCT customer_email FROM tickets "
                    "WHERE customer_email != ''"
                ).fetchall()
            emails = [r[0] for r in rows]
        except Exception:
            return []

        computer = HealthScoreComputer(account_id)
        scores = [
            hs for hs in (computer.compute(email) for email in emails)
            if hs.label in ("at_risk", "critical")
        ]
        scores.sort(key=lambda h: h.score)
        return scores[:top_n]
