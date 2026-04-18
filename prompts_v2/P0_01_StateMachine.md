# P0-01 — State Machine

## What This Does

Right now the orchestrator passes a raw `context` dict between agents with no
enforcement of which steps have actually run or in which order. A crash mid-pipeline
leaves no record of where things stopped, and retrying can cause duplicate actions.

This improvement adds a formal finite state machine to the ticket lifecycle.
Every ticket moves through a strict sequence of states. Invalid transitions raise
an explicit `InvalidTransitionError` instead of silently producing corrupt state.
The machine is idempotent: retrying a completed step is a no-op, not a double-action.

**Where the change lives:**
New file `cs_ai/engine/state_machine.py` + update `cs_ai/engine/tickets.py`
(add `state` field + `version` field to `Ticket`) + update
`cs_ai/engine/agents/orchestrator.py` (call `goto()` at each stage boundary).

**Impact:** Bugs become explicit errors with a clear step name. Resuming a failed
ticket is safe. Every ticket has a complete audit-ready state history.

---

## Prompt — Paste into Claude Code

```
Add a formal state machine to the CS AI ticket lifecycle.

TASK:

1. Create cs_ai/engine/state_machine.py:

   from enum import Enum

   class TicketState(str, Enum):
       NEW           = "new"
       TRIAGED       = "triaged"
       FACTS_BUILT   = "facts_built"
       DRAFTED       = "drafted"
       SELF_REVIEWED = "self_reviewed"
       VALIDATED     = "validated"
       QA_PASSED     = "qa_passed"
       READY         = "ready"
       SENT          = "sent"
       REVIEW        = "review"
       BLOCKED       = "blocked"
       ESCALATED     = "escalated"

   VALID_TRANSITIONS: dict[TicketState, set[TicketState]] = {
       TicketState.NEW:           {TicketState.TRIAGED, TicketState.BLOCKED},
       TicketState.TRIAGED:       {TicketState.FACTS_BUILT, TicketState.BLOCKED, TicketState.ESCALATED},
       TicketState.FACTS_BUILT:   {TicketState.DRAFTED, TicketState.REVIEW, TicketState.BLOCKED},
       TicketState.DRAFTED:       {TicketState.SELF_REVIEWED, TicketState.REVIEW, TicketState.BLOCKED},
       TicketState.SELF_REVIEWED: {TicketState.VALIDATED, TicketState.DRAFTED, TicketState.BLOCKED},
       TicketState.VALIDATED:     {TicketState.QA_PASSED, TicketState.BLOCKED, TicketState.REVIEW},
       TicketState.QA_PASSED:     {TicketState.READY, TicketState.REVIEW},
       TicketState.READY:         {TicketState.SENT, TicketState.REVIEW, TicketState.BLOCKED},
       TicketState.SENT:          {TicketState.RESOLVED},
       TicketState.REVIEW:        {TicketState.DRAFTED, TicketState.BLOCKED, TicketState.ESCALATED},
       TicketState.BLOCKED:       {TicketState.REVIEW, TicketState.ESCALATED},
       TicketState.ESCALATED:     set(),
   }
   # Add RESOLVED = "resolved" and CLOSED = "closed" to the Enum and transitions as well.

   class InvalidTransitionError(Exception):
       def __init__(self, from_state: TicketState, to_state: TicketState):
           super().__init__(f"Invalid transition: {from_state.value} → {to_state.value}")
           self.from_state = from_state
           self.to_state   = to_state

   class StateMachine:
       def goto(self, ticket, to_state: TicketState) -> None:
           """
           Validate and apply a state transition on a Ticket object.
           - If ticket.state == to_state already: no-op (idempotent).
           - If the transition is invalid: raise InvalidTransitionError.
           - On success: set ticket.state = to_state, increment ticket.version.
           - Append a StateTransition record to ticket.state_history (list of dicts
             with keys: from_state, to_state, timestamp ISO-8601).
           """
           ...

2. Update cs_ai/engine/tickets.py — Ticket dataclass:
   - Add field: state: str = "new"
   - Add field: version: int = 0
   - Add field: state_history: list = field(default_factory=list)
   - Add field: retry_count: int = 0
   - Update _create_table() to add columns: state TEXT DEFAULT 'new',
     version INTEGER DEFAULT 0, state_history TEXT DEFAULT '[]', retry_count INTEGER DEFAULT 0
   - Update _row_to_ticket() and save() to handle these new fields (state_history serialised as JSON string).
   - Add method count_open() → int: returns count of tickets where status NOT IN ('resolved','closed').

3. Update cs_ai/engine/agents/orchestrator.py:
   - Import StateMachine from state_machine
   - Instantiate: self._sm = StateMachine()
   - In run(), call self._sm.goto(ticket, TicketState.TRIAGED) after triage completes,
     self._sm.goto(ticket, TicketState.DRAFTED) after response, etc.
   - Wrap each goto() call in try/except InvalidTransitionError and log the error
     at WARNING level then continue (do not crash the pipeline).
   - The ticket object must be saved back to DB after each state change.

4. Create tests/unit/test_state_machine.py:
   - Parametrised test covering all valid transitions: assert no exception raised.
   - Parametrised test covering invalid transitions (e.g. NEW → SENT): assert InvalidTransitionError raised.
   - Test idempotency: calling goto() with the same state twice is a no-op.
   - Test version increments: version goes from 0 to 1 after one successful transition.

Do NOT change nlp.py, channels.py, app.py, app_inbox.py, or any JSON data files.
Do NOT change the existing TICKET_STATUSES list — the new TicketState Enum runs
alongside it until full migration.
```
