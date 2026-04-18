"""
tests/unit/conftest.py — Shared pytest fixtures for the CS AI unit test suite.

Adds cs_ai/engine (and its agents/ sub-package) to sys.path once, so every
test file can import engine modules without repeating the path manipulation.
Individual test files may still do their own sys.path.insert — that is safe
because duplicate entries in sys.path are harmless.
"""

import sys
import os
import pytest

# ---------------------------------------------------------------------------
# Path setup — runs once before any test module is imported
# ---------------------------------------------------------------------------

_ENGINE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine")
)
_AGENTS = os.path.join(_ENGINE, "agents")

for _p in (_ENGINE, _AGENTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_ctx():
    """Minimal pipeline context dict suitable as a starting point for most tests."""
    return {
        "user_input":     "Where is my order ORD-2024-001?",
        "customer_email": "test@example.com",
        "company":        "default",
        "ticket":         None,
        "session_id":     "test-session-001",
    }


@pytest.fixture
def dummy_ticket():
    """
    Lightweight stand-in for a Ticket object.
    Provides every attribute that triage / response agents read without
    touching the database or the real Ticket dataclass.
    """
    class FakeTicket:
        ticket_id      = "TKT-001"
        customer_name  = "Test User"
        customer_email = "test@example.com"
        order_id       = "ORD-2024-001"
        priority       = "Normal"
        subject        = "Order enquiry"
        messages       = []
        state          = "new"
        state_history  = []
        version        = 0
        retry_count    = 0
        sla_deadline   = None

        def sla_urgency(self) -> str:
            return "normal"

    return FakeTicket()
