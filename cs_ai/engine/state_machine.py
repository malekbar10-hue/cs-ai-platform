"""
state_machine.py — Formal state machine for the CS AI ticket lifecycle.

TicketState defines all possible states a ticket can occupy.
VALID_TRANSITIONS maps each state to the set of states it may move to.
StateMachine.goto()     validates and applies a single transition on a Ticket.
StateMachine.can_goto() non-throwing check before attempting a transition.

State categories:
  TERMINAL_STATES    — no outbound transitions; ticket lifecycle is over.
  ACTIONABLE_STATES  — ticket needs human attention (review, edit, send).
"""

from __future__ import annotations

from datetime import datetime, UTC
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tickets import Ticket


def _now_iso() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat()


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------

class TicketState(str, Enum):
    # ── Happy path ─────────────────────────────────────────────────────────
    NEW           = "new"
    TRIAGED       = "triaged"
    FACTS_BUILT   = "facts_built"
    DRAFTED       = "drafted"
    SELF_REVIEWED = "self_reviewed"
    VALIDATED     = "validated"
    QA_PASSED     = "qa_passed"
    READY         = "ready"
    SENT          = "sent"

    # ── Off-path / intervention ────────────────────────────────────────────
    REVIEW         = "review"          # human must inspect/edit before sending
    BLOCKED        = "blocked"         # hard stop; needs explicit unblock
    FALLBACK_DRAFT = "fallback_draft"  # deterministic template used; awaits review/send
    ESCALATED      = "escalated"       # handed to senior agent / external team
    NOISE          = "noise"           # auto-reply / OOO / spam — no reply needed

    # ── Terminal ───────────────────────────────────────────────────────────
    RESOLVED = "resolved"
    CLOSED   = "closed"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_STATES

    @property
    def is_actionable(self) -> bool:
        return self in ACTIONABLE_STATES


# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[TicketState, set[TicketState]] = {
    TicketState.NEW: {
        TicketState.TRIAGED,
        TicketState.NOISE,        # noise detected during triage → close silently
        TicketState.BLOCKED,
    },
    TicketState.TRIAGED: {
        TicketState.FACTS_BUILT,
        TicketState.BLOCKED,
        TicketState.ESCALATED,
    },
    TicketState.FACTS_BUILT: {
        TicketState.DRAFTED,
        TicketState.REVIEW,
        TicketState.BLOCKED,
        TicketState.FALLBACK_DRAFT,  # connector fatal short-circuits to fallback
    },
    TicketState.DRAFTED: {
        TicketState.SELF_REVIEWED,
        TicketState.REVIEW,
        TicketState.BLOCKED,
    },
    TicketState.SELF_REVIEWED: {
        TicketState.VALIDATED,
        TicketState.DRAFTED,         # QA revision loop
        TicketState.BLOCKED,
    },
    TicketState.VALIDATED: {
        TicketState.QA_PASSED,
        TicketState.BLOCKED,
        TicketState.REVIEW,
    },
    TicketState.QA_PASSED: {
        TicketState.READY,
        TicketState.REVIEW,
        TicketState.FALLBACK_DRAFT,  # policy block → use deterministic template
    },
    TicketState.READY: {
        TicketState.SENT,
        TicketState.REVIEW,
        TicketState.BLOCKED,
    },
    TicketState.SENT: {
        TicketState.RESOLVED,
    },
    TicketState.REVIEW: {
        TicketState.DRAFTED,
        TicketState.FALLBACK_DRAFT,
        TicketState.BLOCKED,
        TicketState.ESCALATED,
    },
    TicketState.BLOCKED: {
        TicketState.REVIEW,
        TicketState.FALLBACK_DRAFT,
        TicketState.ESCALATED,
    },
    TicketState.FALLBACK_DRAFT: {
        TicketState.REVIEW,          # human inspects before sending
        TicketState.SENT,            # auto_send=True path
        TicketState.BLOCKED,         # human decides to suppress entirely
        TicketState.ESCALATED,
    },
    TicketState.ESCALATED: {
        TicketState.RESOLVED,        # escalations do eventually resolve
        TicketState.REVIEW,          # de-escalated back to agent queue
    },
    TicketState.NOISE: set(),        # terminal — no reply, no action
    TicketState.RESOLVED: {
        TicketState.CLOSED,
    },
    TicketState.CLOSED: set(),       # terminal
}

# Derived sets — computed once from the transition table
TERMINAL_STATES: frozenset[TicketState] = frozenset(
    s for s, targets in VALID_TRANSITIONS.items() if not targets
)

ACTIONABLE_STATES: frozenset[TicketState] = frozenset({
    TicketState.REVIEW,
    TicketState.BLOCKED,
    TicketState.FALLBACK_DRAFT,
    TicketState.ESCALATED,
    TicketState.READY,
})


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class InvalidTransitionError(Exception):
    def __init__(self, from_state: TicketState, to_state: TicketState):
        super().__init__(
            f"Invalid transition: {from_state.value} -> {to_state.value}"
        )
        self.from_state = from_state
        self.to_state   = to_state


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

class StateMachine:
    """Validates and applies state transitions on Ticket objects."""

    def goto(self, ticket: "Ticket", to_state: TicketState) -> None:
        """
        Validate and apply a state transition.

        - Already in target state → no-op (idempotent).
        - Invalid transition → raises InvalidTransitionError.
        - Success → ticket.state, .version, .state_history updated.
        """
        from_state = self._current_state(ticket)

        if from_state == to_state:
            return

        allowed = VALID_TRANSITIONS.get(from_state, set())
        if to_state not in allowed:
            raise InvalidTransitionError(from_state, to_state)

        self._apply(ticket, from_state, to_state)

    def can_goto(self, ticket: "Ticket", to_state: TicketState) -> bool:
        """Return True if the transition is valid (non-raising check)."""
        from_state = self._current_state(ticket)
        if from_state == to_state:
            return True
        return to_state in VALID_TRANSITIONS.get(from_state, set())

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _current_state(ticket: "Ticket") -> TicketState:
        try:
            return TicketState(ticket.state)
        except (ValueError, AttributeError):
            return TicketState.NEW   # safe fallback for uninitialised tickets

    @staticmethod
    def _apply(
        ticket:     "Ticket",
        from_state: TicketState,
        to_state:   TicketState,
    ) -> None:
        ticket.state   = to_state.value
        ticket.version = getattr(ticket, "version", 0) + 1

        if not hasattr(ticket, "state_history") or ticket.state_history is None:
            ticket.state_history = []

        ticket.state_history.append({
            "from_state": from_state.value,
            "to_state":   to_state.value,
            "timestamp":  _now_iso(),
        })
