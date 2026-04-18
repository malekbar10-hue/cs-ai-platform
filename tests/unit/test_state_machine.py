"""
tests/unit/test_state_machine.py — Unit tests for the ticket state machine.

No database, no network, no config required.
A minimal stub replaces the Ticket dataclass so this file has zero
dependencies on the rest of the engine.

Run with:  pytest tests/unit/test_state_machine.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine"))

import pytest
from state_machine import (
    StateMachine,
    TicketState,
    VALID_TRANSITIONS,
    TERMINAL_STATES,
    ACTIONABLE_STATES,
    InvalidTransitionError,
)


# ---------------------------------------------------------------------------
# Minimal Ticket stub — no DB, no engine imports
# ---------------------------------------------------------------------------

class _Ticket:
    def __init__(self, state: str = "new"):
        self.state         = state
        self.version       = 0
        self.state_history = []


# ---------------------------------------------------------------------------
# Parametrised edge sets derived from the transition table
# ---------------------------------------------------------------------------

_VALID_PAIRS = [
    (from_s, to_s)
    for from_s, targets in VALID_TRANSITIONS.items()
    for to_s in targets
]

_INVALID_PAIRS = [
    (TicketState.NEW,           TicketState.SENT),
    (TicketState.NEW,           TicketState.RESOLVED),
    (TicketState.NEW,           TicketState.CLOSED),
    (TicketState.TRIAGED,       TicketState.SENT),
    (TicketState.DRAFTED,       TicketState.NEW),
    (TicketState.CLOSED,        TicketState.NEW),
    (TicketState.NOISE,         TicketState.TRIAGED),   # terminal
    (TicketState.RESOLVED,      TicketState.DRAFTED),
    (TicketState.FALLBACK_DRAFT,TicketState.NEW),
]


# ---------------------------------------------------------------------------
# All valid transitions pass without exception
# ---------------------------------------------------------------------------

class TestValidTransitions:
    @pytest.mark.parametrize("from_s,to_s", _VALID_PAIRS)
    def test_valid_transition(self, from_s, to_s):
        sm     = StateMachine()
        ticket = _Ticket(state=from_s.value)
        sm.goto(ticket, to_s)
        assert ticket.state == to_s.value


# ---------------------------------------------------------------------------
# Invalid transitions raise
# ---------------------------------------------------------------------------

class TestInvalidTransitions:
    @pytest.mark.parametrize("from_s,to_s", _INVALID_PAIRS)
    def test_invalid_transition_raises(self, from_s, to_s):
        sm     = StateMachine()
        ticket = _Ticket(state=from_s.value)
        with pytest.raises(InvalidTransitionError) as exc_info:
            sm.goto(ticket, to_s)
        assert exc_info.value.from_state == from_s
        assert exc_info.value.to_state   == to_s

    def test_error_message_contains_both_state_names(self):
        sm     = StateMachine()
        ticket = _Ticket(state="new")
        with pytest.raises(InvalidTransitionError) as exc_info:
            sm.goto(ticket, TicketState.SENT)
        msg = str(exc_info.value)
        assert "new"  in msg
        assert "sent" in msg
        assert "->"   in msg


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_goto_same_state_is_noop(self):
        sm     = StateMachine()
        ticket = _Ticket(state="triaged")
        sm.goto(ticket, TicketState.TRIAGED)
        assert ticket.version       == 0
        assert ticket.state_history == []

    def test_goto_same_state_twice_no_version_bump(self):
        sm     = StateMachine()
        ticket = _Ticket(state="new")
        sm.goto(ticket, TicketState.TRIAGED)
        v = ticket.version
        sm.goto(ticket, TicketState.TRIAGED)   # no-op
        assert ticket.version == v


# ---------------------------------------------------------------------------
# Version increment
# ---------------------------------------------------------------------------

class TestVersion:
    def test_version_starts_at_zero(self):
        assert _Ticket().version == 0

    def test_increments_on_each_transition(self):
        sm     = StateMachine()
        ticket = _Ticket(state="new")
        sm.goto(ticket, TicketState.TRIAGED)
        sm.goto(ticket, TicketState.FACTS_BUILT)
        sm.goto(ticket, TicketState.DRAFTED)
        assert ticket.version == 3

    def test_not_incremented_on_invalid(self):
        sm     = StateMachine()
        ticket = _Ticket(state="new")
        with pytest.raises(InvalidTransitionError):
            sm.goto(ticket, TicketState.SENT)
        assert ticket.version == 0


# ---------------------------------------------------------------------------
# State history
# ---------------------------------------------------------------------------

class TestStateHistory:
    def test_entry_appended_with_correct_fields(self):
        sm     = StateMachine()
        ticket = _Ticket(state="new")
        sm.goto(ticket, TicketState.TRIAGED)
        entry = ticket.state_history[0]
        assert entry["from_state"] == "new"
        assert entry["to_state"]   == "triaged"
        assert "timestamp"         in entry

    def test_history_grows_with_transitions(self):
        sm     = StateMachine()
        ticket = _Ticket(state="new")
        sm.goto(ticket, TicketState.TRIAGED)
        sm.goto(ticket, TicketState.FACTS_BUILT)
        assert len(ticket.state_history) == 2

    def test_history_not_appended_on_noop(self):
        sm     = StateMachine()
        ticket = _Ticket(state="triaged")
        sm.goto(ticket, TicketState.TRIAGED)
        assert ticket.state_history == []

    def test_history_order_is_chronological(self):
        sm     = StateMachine()
        ticket = _Ticket(state="new")
        sm.goto(ticket, TicketState.TRIAGED)
        sm.goto(ticket, TicketState.FACTS_BUILT)
        assert ticket.state_history[0]["to_state"] == "triaged"
        assert ticket.state_history[1]["to_state"] == "facts_built"


# ---------------------------------------------------------------------------
# can_goto() — non-throwing check
# ---------------------------------------------------------------------------

class TestCanGoto:
    def test_valid_returns_true(self):
        sm     = StateMachine()
        ticket = _Ticket(state="new")
        assert sm.can_goto(ticket, TicketState.TRIAGED) is True

    def test_invalid_returns_false(self):
        sm     = StateMachine()
        ticket = _Ticket(state="new")
        assert sm.can_goto(ticket, TicketState.SENT) is False

    def test_same_state_returns_true(self):
        sm     = StateMachine()
        ticket = _Ticket(state="triaged")
        assert sm.can_goto(ticket, TicketState.TRIAGED) is True

    def test_terminal_state_returns_false(self):
        sm     = StateMachine()
        ticket = _Ticket(state="closed")
        assert sm.can_goto(ticket, TicketState.REVIEW) is False

    def test_can_goto_does_not_mutate_ticket(self):
        sm     = StateMachine()
        ticket = _Ticket(state="new")
        sm.can_goto(ticket, TicketState.TRIAGED)
        assert ticket.state   == "new"
        assert ticket.version == 0


# ---------------------------------------------------------------------------
# TERMINAL_STATES and ACTIONABLE_STATES derived sets
# ---------------------------------------------------------------------------

class TestDerivedSets:
    def test_noise_is_terminal(self):
        assert TicketState.NOISE in TERMINAL_STATES

    def test_closed_is_terminal(self):
        assert TicketState.CLOSED in TERMINAL_STATES

    def test_new_is_not_terminal(self):
        assert TicketState.NEW not in TERMINAL_STATES

    def test_escalated_is_not_terminal(self):
        # ESCALATED can still go to RESOLVED
        assert TicketState.ESCALATED not in TERMINAL_STATES

    def test_terminal_states_have_no_outbound(self):
        for s in TERMINAL_STATES:
            assert VALID_TRANSITIONS[s] == set(), \
                f"{s.value} is in TERMINAL_STATES but has outbound transitions"

    def test_review_is_actionable(self):
        assert TicketState.REVIEW in ACTIONABLE_STATES

    def test_fallback_draft_is_actionable(self):
        assert TicketState.FALLBACK_DRAFT in ACTIONABLE_STATES

    def test_new_is_not_actionable(self):
        assert TicketState.NEW not in ACTIONABLE_STATES


# ---------------------------------------------------------------------------
# TicketState properties
# ---------------------------------------------------------------------------

class TestTicketStateProperties:
    def test_is_terminal_true_for_noise(self):
        assert TicketState.NOISE.is_terminal is True

    def test_is_terminal_true_for_closed(self):
        assert TicketState.CLOSED.is_terminal is True

    def test_is_terminal_false_for_new(self):
        assert TicketState.NEW.is_terminal is False

    def test_is_actionable_true_for_review(self):
        assert TicketState.REVIEW.is_actionable is True

    def test_is_actionable_false_for_sent(self):
        assert TicketState.SENT.is_actionable is False


# ---------------------------------------------------------------------------
# New states — NOISE
# ---------------------------------------------------------------------------

class TestNoiseState:
    def test_new_can_transition_to_noise(self):
        sm     = StateMachine()
        ticket = _Ticket(state="new")
        sm.goto(ticket, TicketState.NOISE)
        assert ticket.state == "noise"

    def test_noise_is_terminal_no_outbound(self):
        sm     = StateMachine()
        ticket = _Ticket(state="noise")
        with pytest.raises(InvalidTransitionError):
            sm.goto(ticket, TicketState.TRIAGED)

    def test_noise_cannot_go_to_review(self):
        sm     = StateMachine()
        ticket = _Ticket(state="noise")
        assert sm.can_goto(ticket, TicketState.REVIEW) is False


# ---------------------------------------------------------------------------
# New states — FALLBACK_DRAFT
# ---------------------------------------------------------------------------

class TestFallbackDraftState:
    def test_qa_passed_can_go_to_fallback_draft(self):
        sm     = StateMachine()
        ticket = _Ticket(state="qa_passed")
        sm.goto(ticket, TicketState.FALLBACK_DRAFT)
        assert ticket.state == "fallback_draft"

    def test_blocked_can_go_to_fallback_draft(self):
        sm     = StateMachine()
        ticket = _Ticket(state="blocked")
        sm.goto(ticket, TicketState.FALLBACK_DRAFT)
        assert ticket.state == "fallback_draft"

    def test_review_can_go_to_fallback_draft(self):
        sm     = StateMachine()
        ticket = _Ticket(state="review")
        sm.goto(ticket, TicketState.FALLBACK_DRAFT)
        assert ticket.state == "fallback_draft"

    def test_fallback_draft_can_go_to_review(self):
        sm     = StateMachine()
        ticket = _Ticket(state="fallback_draft")
        sm.goto(ticket, TicketState.REVIEW)
        assert ticket.state == "review"

    def test_fallback_draft_can_be_sent(self):
        sm     = StateMachine()
        ticket = _Ticket(state="fallback_draft")
        sm.goto(ticket, TicketState.SENT)
        assert ticket.state == "sent"

    def test_fallback_draft_can_be_blocked(self):
        sm     = StateMachine()
        ticket = _Ticket(state="fallback_draft")
        sm.goto(ticket, TicketState.BLOCKED)
        assert ticket.state == "blocked"

    def test_fallback_draft_cannot_go_to_new(self):
        sm     = StateMachine()
        ticket = _Ticket(state="fallback_draft")
        assert sm.can_goto(ticket, TicketState.NEW) is False


# ---------------------------------------------------------------------------
# ESCALATED is no longer terminal
# ---------------------------------------------------------------------------

class TestEscalatedState:
    def test_escalated_can_resolve(self):
        sm     = StateMachine()
        ticket = _Ticket(state="escalated")
        sm.goto(ticket, TicketState.RESOLVED)
        assert ticket.state == "resolved"

    def test_escalated_can_return_to_review(self):
        sm     = StateMachine()
        ticket = _Ticket(state="escalated")
        sm.goto(ticket, TicketState.REVIEW)
        assert ticket.state == "review"

    def test_escalated_is_not_terminal(self):
        assert TicketState.ESCALATED not in TERMINAL_STATES


# ---------------------------------------------------------------------------
# Unknown / uninitialised ticket state recovery
# ---------------------------------------------------------------------------

class TestUnknownStateRecovery:
    def test_unknown_state_treated_as_new(self):
        sm     = StateMachine()
        ticket = _Ticket(state="corrupted_value")
        sm.goto(ticket, TicketState.TRIAGED)   # NEW → TRIAGED is valid
        assert ticket.state == "triaged"

    def test_missing_state_attribute(self):
        sm     = StateMachine()

        class _Bare:
            version = 0
            state_history = []
            # no .state attribute

        ticket = _Bare()
        sm.goto(ticket, TicketState.TRIAGED)   # must not raise
        assert ticket.state == "triaged"
