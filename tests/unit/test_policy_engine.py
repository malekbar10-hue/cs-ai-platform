"""
tests/unit/test_policy_engine.py — Unit tests for PolicyEngine.

No database, network, or LLM required.
Run with:  pytest tests/unit/test_policy_engine.py -v
"""

import sys
import os
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine", "agents"))

import pytest
from policy_engine import PolicyEngine, PolicyRule, PolicyDecision
from fact_registry import Fact, FactRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def _registry_with_delivery_date(date_str: str = "2024-05-15") -> FactRegistry:
    reg = FactRegistry()
    reg.register(Fact(
        key="order.delivery_date", value=date_str,
        source_type="erp", source_ref="ORD-1",
        verified=True, observed_at=_now(),
    ))
    return reg


def _engine() -> PolicyEngine:
    return PolicyEngine()


# ---------------------------------------------------------------------------
# Clean context — no violations
# ---------------------------------------------------------------------------

class TestCleanContext:
    def test_empty_ctx_passes(self):
        decision = _engine().evaluate({})
        assert decision.passed is True
        assert decision.violations == []
        assert decision.required_actions == []

    def test_calm_high_confidence_passes(self):
        decision = _engine().evaluate({
            "emotion": "calm",
            "confidence": {"final": 0.9, "overall": 0.9},
            "draft": "Thank you for contacting us.",
        })
        assert decision.passed is True

    def test_neutral_emotion_no_action_passes(self):
        decision = _engine().evaluate({
            "emotion": "neutral",
            "confidence": {"final": 0.8},
        })
        assert decision.passed is True


# ---------------------------------------------------------------------------
# no_autosend_angry_low_confidence
# ---------------------------------------------------------------------------

class TestAngryLowConfidence:
    def test_angry_conf_0_5_triggers(self):
        decision = _engine().evaluate({
            "emotion": "angry",
            "confidence": {"final": 0.5},
        })
        assert "no_autosend_angry_low_confidence" in decision.violations
        assert "review" in decision.required_actions

    def test_angry_conf_0_69_triggers(self):
        decision = _engine().evaluate({
            "emotion": "angry",
            "confidence": {"final": 0.69},
        })
        assert "no_autosend_angry_low_confidence" in decision.violations

    def test_angry_conf_0_7_no_trigger(self):
        decision = _engine().evaluate({
            "emotion": "angry",
            "confidence": {"final": 0.7},
        })
        assert "no_autosend_angry_low_confidence" not in decision.violations

    def test_angry_conf_0_9_no_trigger(self):
        decision = _engine().evaluate({
            "emotion": "angry",
            "confidence": {"final": 0.9},
        })
        assert "no_autosend_angry_low_confidence" not in decision.violations

    def test_calm_conf_0_5_no_trigger(self):
        decision = _engine().evaluate({
            "emotion": "calm",
            "confidence": {"final": 0.5},
        })
        assert "no_autosend_angry_low_confidence" not in decision.violations

    def test_frustrated_conf_0_3_no_trigger(self):
        # Rule is specific to "angry" only
        decision = _engine().evaluate({
            "emotion": "frustrated",
            "confidence": {"final": 0.3},
        })
        assert "no_autosend_angry_low_confidence" not in decision.violations

    def test_triage_result_emotion_used(self):
        """Reads emotion from triage_result when present."""
        class _FakeTriage:
            emotion    = "angry"
            confidence = None

        decision = _engine().evaluate({
            "triage_result": _FakeTriage(),
            "confidence":    {"final": 0.4},
        })
        assert "no_autosend_angry_low_confidence" in decision.violations


# ---------------------------------------------------------------------------
# no_unsupported_claims
# ---------------------------------------------------------------------------

class TestUnsupportedClaims:
    def _make_vr(self, unsupported: list[str]):
        from schemas import ValidationResult
        return ValidationResult(verified=True, unsupported_claims=unsupported)

    def test_non_empty_unsupported_triggers(self):
        decision = _engine().evaluate({
            "validation_result": self._make_vr(["Status claim 'in_transit' not verified"]),
        })
        assert "no_unsupported_claims" in decision.violations
        assert "block" in decision.required_actions

    def test_empty_unsupported_no_trigger(self):
        decision = _engine().evaluate({
            "validation_result": self._make_vr([]),
        })
        assert "no_unsupported_claims" not in decision.violations

    def test_no_validation_result_no_trigger(self):
        decision = _engine().evaluate({})
        assert "no_unsupported_claims" not in decision.violations


# ---------------------------------------------------------------------------
# erp_action_requires_approval
# ---------------------------------------------------------------------------

class TestErpActionApproval:
    def test_refund_triggers_review(self):
        decision = _engine().evaluate({"suggested_action": "refund"})
        assert "erp_action_requires_approval" in decision.violations
        assert "review" in decision.required_actions

    def test_cancel_triggers_review(self):
        decision = _engine().evaluate({"suggested_action": "cancel_order"})
        assert "erp_action_requires_approval" in decision.violations

    def test_modify_triggers_review(self):
        decision = _engine().evaluate({"suggested_action": "modify_address"})
        assert "erp_action_requires_approval" in decision.violations

    def test_annul_triggers(self):
        decision = _engine().evaluate({"suggested_action": "annuler la commande"})
        assert "erp_action_requires_approval" in decision.violations

    def test_rembours_triggers(self):
        decision = _engine().evaluate({"suggested_action": "rembourser"})
        assert "erp_action_requires_approval" in decision.violations

    def test_status_check_no_trigger(self):
        decision = _engine().evaluate({"suggested_action": "check_status"})
        assert "erp_action_requires_approval" not in decision.violations

    def test_empty_action_no_trigger(self):
        decision = _engine().evaluate({"suggested_action": ""})
        assert "erp_action_requires_approval" not in decision.violations

    def test_action_key_fallback(self):
        # Also reads ctx["action"] when suggested_action absent
        decision = _engine().evaluate({"action": "refund_order"})
        assert "erp_action_requires_approval" in decision.violations


# ---------------------------------------------------------------------------
# no_unverified_delivery_date
# ---------------------------------------------------------------------------

class TestUnverifiedDeliveryDate:
    def test_date_in_draft_no_registry_triggers(self):
        decision = _engine().evaluate({
            "draft": "Your delivery is scheduled for 15/05/2024.",
        })
        assert "no_unverified_delivery_date" in decision.violations
        assert "block" in decision.required_actions

    def test_date_in_draft_with_verified_fact_passes(self):
        reg = _registry_with_delivery_date("2024-05-15")
        decision = _engine().evaluate({
            "draft":         "Your delivery is scheduled for 15/05/2024.",
            "fact_registry": reg,
        })
        assert "no_unverified_delivery_date" not in decision.violations

    def test_no_date_in_draft_passes(self):
        decision = _engine().evaluate({
            "draft": "Thank you for contacting us. We are reviewing your request.",
        })
        assert "no_unverified_delivery_date" not in decision.violations

    def test_within_n_days_triggers_without_registry(self):
        decision = _engine().evaluate({
            "draft": "Your order will arrive within 3 days.",
        })
        assert "no_unverified_delivery_date" in decision.violations

    def test_dans_n_jours_triggers_without_registry(self):
        decision = _engine().evaluate({
            "draft": "Votre commande arrivera dans 2 jours.",
        })
        assert "no_unverified_delivery_date" in decision.violations

    def test_empty_draft_no_trigger(self):
        decision = _engine().evaluate({"draft": ""})
        assert "no_unverified_delivery_date" not in decision.violations


# ---------------------------------------------------------------------------
# PolicyDecision shape
# ---------------------------------------------------------------------------

class TestPolicyDecisionShape:
    def test_multiple_violations_all_listed(self):
        decision = _engine().evaluate({
            "emotion":          "angry",
            "confidence":       {"final": 0.4},
            "suggested_action": "refund",
        })
        assert "no_autosend_angry_low_confidence" in decision.violations
        assert "erp_action_requires_approval"     in decision.violations
        assert decision.passed is False

    def test_block_takes_precedence_over_review(self):
        from schemas import ValidationResult
        vr = ValidationResult(verified=True, unsupported_claims=["some claim"])
        decision = _engine().evaluate({
            "validation_result": vr,
            "suggested_action":  "refund",
        })
        assert "block"  in decision.required_actions
        assert "review" in decision.required_actions

    def test_required_actions_sorted(self):
        from schemas import ValidationResult
        vr = ValidationResult(verified=True, unsupported_claims=["c"])
        decision = _engine().evaluate({
            "validation_result": vr,
            "suggested_action":  "cancel",
        })
        # sorted() → ["block", "review"]
        assert decision.required_actions == sorted(decision.required_actions)


# ---------------------------------------------------------------------------
# add_rule — custom rule injection
# ---------------------------------------------------------------------------

class TestCustomRule:
    def test_custom_rule_fires(self):
        engine = PolicyEngine()
        engine.add_rule(PolicyRule(
            name="no_hello_draft",
            description="Draft must not start with 'hello'",
            severity="warn",
            check=lambda ctx: ctx.get("draft", "").lower().startswith("hello"),
        ))
        decision = engine.evaluate({"draft": "Hello, dear customer."})
        assert "no_hello_draft" in decision.violations
        assert "warn" in decision.required_actions

    def test_rule_exception_does_not_crash(self):
        engine = PolicyEngine()
        engine.add_rule(PolicyRule(
            name="buggy_rule",
            description="Always raises",
            severity="block",
            check=lambda ctx: 1 / 0,
        ))
        decision = engine.evaluate({})
        # Engine must not raise; buggy rule is silently skipped
        assert "buggy_rule" not in decision.violations
