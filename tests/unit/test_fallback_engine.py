"""
tests/unit/test_fallback_engine.py — Unit tests for FallbackTemplateEngine.

No database, network, or LLM required — output is purely deterministic.
Run with:  pytest tests/unit/test_fallback_engine.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine", "agents"))

import pytest
from fallback_engine import FallbackTemplateEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine() -> FallbackTemplateEngine:
    return FallbackTemplateEngine()


def _fr_ctx(**kwargs) -> dict:
    base = {"language": "French", "customer_name": "Dupont SAS",
            "agent_signature": "L'équipe CS", "sla_hours": 24}
    base.update(kwargs)
    return base


def _en_ctx(**kwargs) -> dict:
    base = {"language": "English", "customer_name": "Acme Ltd",
            "agent_signature": "CS Team", "sla_hours": 8}
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# render() — language selection
# ---------------------------------------------------------------------------

class TestRenderLanguage:
    def test_french_missing_info_contains_french(self):
        result = _engine().render("missing_info", _fr_ctx(
            missing_fields=["votre numéro de commande"]
        ))
        assert "Bonjour" in result
        assert "Cordialement" in result

    def test_english_missing_info_contains_english(self):
        result = _engine().render("missing_info", _en_ctx(
            missing_fields=["your order number"]
        ))
        assert "Dear" in result
        assert "Best regards" in result

    def test_french_system_unavailable_is_french(self):
        result = _engine().render("system_unavailable", _fr_ctx())
        assert "Bonjour" in result
        assert "indisponibilité" in result

    def test_english_system_unavailable_is_english(self):
        result = _engine().render("system_unavailable", _en_ctx())
        assert "Dear" in result
        assert "system" in result.lower()

    def test_french_high_risk_is_french(self):
        result = _engine().render("high_risk", _fr_ctx())
        assert "Bonjour" in result
        assert "priorité" in result

    def test_english_high_risk_is_english(self):
        result = _engine().render("high_risk", _en_ctx())
        assert "Dear" in result
        assert "priority" in result.lower()

    def test_french_ambiguous_is_french(self):
        result = _engine().render("ambiguous_request", _fr_ctx())
        assert "Bonjour" in result
        assert "préciser" in result

    def test_english_ambiguous_is_english(self):
        result = _engine().render("ambiguous_request", _en_ctx())
        assert "Dear" in result
        assert "clarify" in result.lower()

    def test_unknown_language_falls_back_to_french(self):
        ctx = _fr_ctx()
        ctx["language"] = "Spanish"
        result = _engine().render("high_risk", ctx)
        assert "Bonjour" in result

    def test_language_case_insensitive_en(self):
        result = _engine().render("missing_info", _en_ctx())
        assert "Dear" in result

    def test_language_case_insensitive_fr(self):
        result = _engine().render("missing_info", {
            "language": "fr", "customer_name": "Test",
            "agent_signature": "Sig", "sla_hours": 24,
        })
        assert "Bonjour" in result


# ---------------------------------------------------------------------------
# render() — variable injection
# ---------------------------------------------------------------------------

class TestRenderVariables:
    def test_customer_name_injected(self):
        result = _engine().render("high_risk", _fr_ctx(customer_name="Dupont SAS"))
        assert "Dupont SAS" in result

    def test_agent_signature_injected(self):
        result = _engine().render("high_risk", _fr_ctx(agent_signature="Marie Durand"))
        assert "Marie Durand" in result

    def test_sla_hours_injected_french(self):
        result = _engine().render("high_risk", _fr_ctx(sla_hours=4))
        assert "4" in result

    def test_sla_hours_injected_english(self):
        result = _engine().render("high_risk", _en_ctx(sla_hours=2))
        assert "2" in result

    def test_missing_fields_joined_in_output(self):
        result = _engine().render("missing_info", _fr_ctx(
            missing_fields=["numéro de commande", "date de livraison"]
        ))
        assert "numéro de commande" in result
        assert "date de livraison" in result

    def test_missing_fields_default_when_absent(self):
        ctx = _fr_ctx()
        ctx.pop("missing_fields", None)
        result = _engine().render("missing_info", ctx)
        assert len(result) > 0  # renders without raising

    def test_customer_name_default_empty_when_absent(self):
        ctx = _fr_ctx()
        ctx.pop("customer_name", None)
        result = _engine().render("high_risk", ctx)
        assert len(result) > 0

    def test_sla_from_config_priority_normal(self):
        ctx = _fr_ctx()
        ctx["priority"] = "Normal"
        ctx["config"]   = {"sla": {"Normal": {"response_hours": 24}}}
        result = _engine().render("high_risk", ctx)
        assert "24" in result

    def test_sla_from_config_priority_high(self):
        ctx = _fr_ctx()
        ctx["priority"] = "High"
        ctx["config"]   = {"sla": {"High": {"response_hours": 4}}}
        result = _engine().render("high_risk", ctx)
        assert "4" in result

    def test_all_templates_render_non_empty(self):
        engine = _engine()
        for reason in ("missing_info", "system_unavailable", "high_risk", "ambiguous_request"):
            for ctx in (_fr_ctx(), _en_ctx()):
                result = engine.render(reason, ctx)
                assert len(result.strip()) > 20, f"{reason} rendered empty for {ctx['language']}"


# ---------------------------------------------------------------------------
# reason_for()
# ---------------------------------------------------------------------------

class TestReasonFor:
    def test_connector_fatal_returns_system_unavailable(self):
        assert _engine().reason_for({"connector_fatal": True}) == "system_unavailable"

    def test_connector_fatal_overrides_everything(self):
        class _FakeTriage:
            missing_fields = ["order_id"]
            intent         = "unknown"
        assert _engine().reason_for({
            "connector_fatal": True,
            "triage_result":   _FakeTriage(),
        }) == "system_unavailable"

    def test_missing_fields_returns_missing_info(self):
        class _FakeTriage:
            missing_fields = ["order_id"]
            intent         = "order_status"
        assert _engine().reason_for({"triage_result": _FakeTriage()}) == "missing_info"

    def test_angry_low_confidence_returns_high_risk(self):
        from policy_engine import PolicyDecision
        policy = PolicyDecision(
            passed=False,
            violations=["no_autosend_angry_low_confidence"],
            required_actions=["review"],
        )
        assert _engine().reason_for({"policy_decision": policy}) == "high_risk"

    def test_unknown_intent_returns_ambiguous(self):
        class _FakeTriage:
            missing_fields = []
            intent         = "unknown"
        assert _engine().reason_for({"triage_result": _FakeTriage()}) == "ambiguous_request"

    def test_no_signals_defaults_to_high_risk(self):
        assert _engine().reason_for({}) == "high_risk"

    def test_empty_missing_fields_does_not_trigger_missing_info(self):
        class _FakeTriage:
            missing_fields = []
            intent         = "order_status"
        result = _engine().reason_for({"triage_result": _FakeTriage()})
        assert result != "missing_info"

    def test_policy_without_angry_rule_does_not_trigger_high_risk_via_policy(self):
        from policy_engine import PolicyDecision
        policy = PolicyDecision(
            passed=False,
            violations=["erp_action_requires_approval"],
            required_actions=["review"],
        )
        result = _engine().reason_for({"policy_decision": policy})
        assert result == "high_risk"  # default fallback


# ---------------------------------------------------------------------------
# Output is deterministic (no LLM)
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_ctx_same_output(self):
        engine = _engine()
        ctx    = _fr_ctx(customer_name="Acme", sla_hours=24)
        assert engine.render("high_risk", ctx) == engine.render("high_risk", ctx)

    def test_different_customer_names_give_different_output(self):
        engine = _engine()
        r1 = engine.render("high_risk", _fr_ctx(customer_name="Alpha SA"))
        r2 = engine.render("high_risk", _fr_ctx(customer_name="Beta Corp"))
        assert r1 != r2
