"""
tests/unit/test_sla_routing.py — Unit tests for SLA-aware routing.

Tests Ticket.time_to_breach_minutes(), Ticket.sla_urgency(), and the
route-upgrade logic that runs in the triage agent.

Run with:  pytest tests/unit/test_sla_routing.py -v
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine"))

import pytest
from tickets import Ticket


# ---------------------------------------------------------------------------
# Minimal Ticket factory — only the fields we care about for SLA logic
# ---------------------------------------------------------------------------

def _make_ticket(sla_offset_minutes: float) -> Ticket:
    """
    Create a Ticket whose sla_deadline is `sla_offset_minutes` from now.
    Positive = deadline in the future; negative = already breached.
    """
    now = datetime.now().replace(tzinfo=None)
    return Ticket(
        ticket_id=      "test-tid",
        status=         "new",
        priority=       "Normal",
        customer_email= "test@example.com",
        customer_name=  "Test User",
        subject=        "Test subject",
        channel=        "manual",
        created_at=     now - timedelta(hours=1),
        updated_at=     now,
        sla_deadline=   now + timedelta(minutes=sla_offset_minutes),
    )


# ---------------------------------------------------------------------------
# time_to_breach_minutes()
# ---------------------------------------------------------------------------

class TestTimeToBreach:
    def test_deadline_one_hour_future_approx_60(self):
        ticket = _make_ticket(60)
        ttb = ticket.time_to_breach_minutes()
        assert ttb is not None
        assert 58 < ttb < 62        # allow 2 min tolerance for execution time

    def test_deadline_in_past_is_negative(self):
        ticket = _make_ticket(-30)
        ttb = ticket.time_to_breach_minutes()
        assert ttb is not None
        assert ttb < 0

    def test_no_deadline_returns_none(self):
        ticket = _make_ticket(60)
        ticket.sla_deadline = None  # type: ignore[assignment]
        assert ticket.time_to_breach_minutes() is None

    def test_value_scales_with_offset(self):
        t30  = _make_ticket(30)
        t120 = _make_ticket(120)
        assert t30.time_to_breach_minutes() < t120.time_to_breach_minutes()


# ---------------------------------------------------------------------------
# sla_urgency()
# ---------------------------------------------------------------------------

class TestSlaUrgency:
    def test_negative_ttb_is_breached(self):
        assert _make_ticket(-5).sla_urgency() == "breached"

    def test_zero_ttb_is_breached(self):
        assert _make_ticket(0).sla_urgency() == "breached"

    def test_20_min_is_critical(self):
        assert _make_ticket(20).sla_urgency() == "critical"

    def test_29_min_is_critical(self):
        assert _make_ticket(29).sla_urgency() == "critical"

    def test_31_min_is_high(self):
        # 31 minutes is safely above the < 30 threshold
        assert _make_ticket(31).sla_urgency() == "high"

    def test_90_min_is_high(self):
        assert _make_ticket(90).sla_urgency() == "high"

    def test_119_min_is_high(self):
        assert _make_ticket(119).sla_urgency() == "high"

    def test_121_min_is_normal(self):
        # 121 minutes is safely above the < 120 threshold
        assert _make_ticket(121).sla_urgency() == "normal"

    def test_300_min_is_normal(self):
        assert _make_ticket(300).sla_urgency() == "normal"

    def test_no_deadline_is_normal(self):
        t = _make_ticket(60)
        t.sla_deadline = None  # type: ignore[assignment]
        assert t.sla_urgency() == "normal"


# ---------------------------------------------------------------------------
# Route upgrade logic (mirrors triage.py SLA block, tested in isolation)
# ---------------------------------------------------------------------------

def _apply_sla_route_logic(sla_urgency: str, current_route: str) -> str:
    """Replica of the triage.py SLA route-override block for isolated testing."""
    route = current_route
    if sla_urgency == "breached":
        route = "supervisor"
    elif sla_urgency == "critical" and route not in ("supervisor", "priority"):
        route = "priority"
    elif sla_urgency == "high" and route == "auto":
        route = "standard"
    return route


class TestSlaRouteUpgrade:
    # breached always forces supervisor
    def test_breached_sets_supervisor_from_standard(self):
        assert _apply_sla_route_logic("breached", "standard") == "supervisor"

    def test_breached_sets_supervisor_from_auto(self):
        assert _apply_sla_route_logic("breached", "auto") == "supervisor"

    def test_breached_sets_supervisor_from_priority(self):
        assert _apply_sla_route_logic("breached", "priority") == "supervisor"

    def test_breached_keeps_supervisor(self):
        assert _apply_sla_route_logic("breached", "supervisor") == "supervisor"

    # critical upgrades to priority unless already supervisor/priority
    def test_critical_upgrades_standard_to_priority(self):
        assert _apply_sla_route_logic("critical", "standard") == "priority"

    def test_critical_upgrades_auto_to_priority(self):
        assert _apply_sla_route_logic("critical", "auto") == "priority"

    def test_critical_does_not_downgrade_supervisor(self):
        assert _apply_sla_route_logic("critical", "supervisor") == "supervisor"

    def test_critical_keeps_priority(self):
        assert _apply_sla_route_logic("critical", "priority") == "priority"

    # high upgrades auto → standard only
    def test_high_upgrades_auto_to_standard(self):
        assert _apply_sla_route_logic("high", "auto") == "standard"

    def test_high_keeps_standard(self):
        assert _apply_sla_route_logic("high", "standard") == "standard"

    def test_high_keeps_priority(self):
        assert _apply_sla_route_logic("high", "priority") == "priority"

    def test_high_keeps_supervisor(self):
        assert _apply_sla_route_logic("high", "supervisor") == "supervisor"

    # normal never changes route
    def test_normal_leaves_auto(self):
        assert _apply_sla_route_logic("normal", "auto") == "auto"

    def test_normal_leaves_supervisor(self):
        assert _apply_sla_route_logic("normal", "supervisor") == "supervisor"


# ---------------------------------------------------------------------------
# End-to-end: urgency computed from ticket → route correctly upgraded
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_breached_ticket_route_is_supervisor(self):
        ticket = _make_ticket(-5)
        assert ticket.sla_urgency() == "breached"
        route = _apply_sla_route_logic(ticket.sla_urgency(), "standard")
        assert route == "supervisor"

    def test_critical_ticket_upgrades_auto_to_priority(self):
        ticket = _make_ticket(20)
        assert ticket.sla_urgency() == "critical"
        route = _apply_sla_route_logic(ticket.sla_urgency(), "auto")
        assert route == "priority"

    def test_healthy_ticket_does_not_change_route(self):
        ticket = _make_ticket(300)
        assert ticket.sla_urgency() == "normal"
        route = _apply_sla_route_logic(ticket.sla_urgency(), "auto")
        assert route == "auto"
