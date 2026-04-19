"""
tests/unit/test_triage_route.py — Unit tests for _determine_route() in triage.py

Tests the routing logic in complete isolation — no OpenAI, no ChromaDB, no pipeline.
"""

import sys
import os

# Make the agents module importable
_ROOT   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ENGINE = os.path.join(_ROOT, "cs_ai", "engine")
_AGENTS = os.path.join(_ENGINE, "agents")
sys.path.insert(0, _ENGINE)
sys.path.insert(0, _AGENTS)

import pytest

# Import only the pure helper — no agent instantiation, no external calls
from triage import _determine_route


class TestDetermineRoute:

    # ── Supervisor cases ───────────────────────────────────────────────────

    def test_escalate_intent_always_supervisor(self):
        assert _determine_route("Neutral", "Low", "escalate", "Normal", None, None) == "supervisor"

    def test_cancel_intent_always_supervisor(self):
        assert _determine_route("Neutral", "Low", "cancel", "Normal", None, None) == "supervisor"

    def test_angry_very_high_is_supervisor(self):
        assert _determine_route("Angry", "Very High", "tracking", "Normal", None, None) == "supervisor"

    def test_angry_high_is_supervisor(self):
        assert _determine_route("Angry", "High", "info", "Normal", None, None) == "supervisor"

    def test_urgent_high_is_supervisor(self):
        assert _determine_route("Urgent", "High", "general_inquiry", "Normal", None, None) == "supervisor"

    def test_escalating_trajectory_repeat_customer_is_supervisor(self):
        trajectory = {"trend": "Escalating"}
        profile    = {"total_interactions": 5}
        assert _determine_route("Frustrated", "Medium", "complaint", "Normal", trajectory, profile) == "supervisor"

    # ── Priority cases ─────────────────────────────────────────────────────

    def test_critical_priority_is_priority(self):
        assert _determine_route("Neutral", "Low", "tracking", "Critical", None, None) == "priority"

    def test_high_intensity_is_priority(self):
        assert _determine_route("Frustrated", "High", "info", "Normal", None, None) == "priority"

    def test_very_high_intensity_is_priority(self):
        assert _determine_route("Neutral", "Very High", "tracking", "Normal", None, None) == "priority"

    # ── Auto cases ─────────────────────────────────────────────────────────

    def test_tracking_neutral_is_auto(self):
        assert _determine_route("Neutral", "Low", "tracking", "Normal", None, None) == "auto"

    def test_info_neutral_is_auto(self):
        assert _determine_route("Neutral", "Low", "info", "Normal", None, None) == "auto"

    def test_document_request_satisfied_is_auto(self):
        assert _determine_route("Satisfied", "Low", "document_request", "Normal", None, None) == "auto"

    # ── Standard cases ─────────────────────────────────────────────────────

    def test_refund_neutral_is_standard(self):
        assert _determine_route("Neutral", "Low", "refund", "Normal", None, None) == "standard"

    def test_complaint_medium_is_standard(self):
        assert _determine_route("Frustrated", "Medium", "complaint", "Normal", None, None) == "standard"

    def test_general_inquiry_is_standard(self):
        assert _determine_route("Neutral", "Low", "general_inquiry", "Normal", None, None) == "standard"

    # ── Edge cases ─────────────────────────────────────────────────────────

    def test_escalating_trajectory_but_new_customer_not_supervisor(self):
        # Escalating trend BUT fewer than 3 interactions → not supervisor
        trajectory = {"trend": "Escalating"}
        profile    = {"total_interactions": 1}
        result = _determine_route("Neutral", "Low", "tracking", "Normal", trajectory, profile)
        assert result != "supervisor"

    def test_escalating_trajectory_no_profile_not_supervisor(self):
        trajectory = {"trend": "Escalating"}
        result = _determine_route("Neutral", "Low", "tracking", "Normal", trajectory, None)
        assert result != "supervisor"
