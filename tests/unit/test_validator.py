"""
tests/unit/test_validator.py — Unit tests for ValidatorAgent.

No database, network, or config required.
Run with:  pytest tests/unit/test_validator.py -v
"""

import sys
import os
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine", "agents"))

import pytest
from fact_registry import Fact, FactRegistry
from validator import ValidatorAgent, _is_status_contradiction, _normalise_date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def _registry(**kwargs) -> FactRegistry:
    """Build a registry with order.* facts from kwargs."""
    reg = FactRegistry()
    for k, v in kwargs.items():
        reg.register(Fact(
            key=f"order.{k}", value=v, source_type="erp",
            source_ref="ORD-001", verified=True, observed_at=_now(),
        ))
    return reg


def _run(draft: str, registry: FactRegistry = None, order_id: str = None) -> dict:
    agent = ValidatorAgent()
    ctx   = {"draft": draft, "fact_registry": registry or FactRegistry()}
    if order_id:
        ctx["order_id"] = order_id
    return agent.run(ctx)


# ---------------------------------------------------------------------------
# No-op cases
# ---------------------------------------------------------------------------

class TestValidatorNoOp:
    def test_empty_draft_verified(self):
        ctx = _run("")
        assert ctx["validation_result"].verified is True

    def test_empty_registry_verified(self):
        ctx = _run("Dear customer, your order has been shipped.", FactRegistry())
        assert ctx["validation_result"].verified is True

    def test_no_fact_registry_key_verified(self):
        agent  = ValidatorAgent()
        result = agent.run({"draft": "hello"})
        assert result["validation_result"].verified is True

    def test_validator_never_raises_on_bad_input(self):
        agent = ValidatorAgent()
        # Pass garbage context — should not raise
        result = agent.run({"draft": None, "fact_registry": "not_a_registry"})
        assert "validation_result" in result


# ---------------------------------------------------------------------------
# Order ID checks
# ---------------------------------------------------------------------------

class TestOrderIdValidation:
    def test_correct_order_id_no_contradiction(self):
        reg = _registry(order_id="ORD-001")
        ctx = _run("Please refer to order ORD-001.", reg, order_id="ORD-001")
        assert ctx["validation_result"].verified is True
        assert ctx["validation_result"].contradictions == []

    def test_wrong_order_id_adds_contradiction(self):
        reg = _registry(order_id="ORD-001")
        ctx = _run("Your order ORD-999 has been processed.", reg, order_id="ORD-001")
        vr  = ctx["validation_result"]
        assert len(vr.contradictions) >= 1
        assert any("ORD-999" in c for c in vr.contradictions)

    def test_no_order_id_in_draft_passes(self):
        reg = _registry(order_id="ORD-001")
        ctx = _run("Thank you for contacting us. We are looking into this.", reg)
        assert ctx["validation_result"].verified is True

    def test_pipeline_error_set_on_contradiction(self):
        reg = _registry(order_id="ORD-001")
        ctx = _run("Order ORD-999 is confirmed.", reg, order_id="ORD-001")
        if not ctx["validation_result"].verified:
            assert ctx.get("pipeline_error") == "validation_failed"


# ---------------------------------------------------------------------------
# Status-word checks
# ---------------------------------------------------------------------------

class TestStatusValidation:
    def test_matching_status_passes(self):
        reg = _registry(status="shipped")
        ctx = _run("Your order has been shipped and is on its way.", reg)
        assert ctx["validation_result"].verified is True

    def test_contradicting_status_delivered_vs_shipped(self):
        reg = _registry(status="shipped")
        ctx = _run("Your order has been delivered successfully.", reg)
        vr  = ctx["validation_result"]
        # "delivered" contradicts "shipped"
        assert len(vr.contradictions) >= 1

    def test_status_in_transit_vs_processing_contradiction(self):
        reg = _registry(status="processing")
        ctx = _run("Your parcel is currently in transit.", reg)
        vr  = ctx["validation_result"]
        assert len(vr.contradictions) >= 1

    def test_in_stock_vs_out_of_stock_contradiction(self):
        reg = _registry(status="out_of_stock")
        ctx = _run("The item is en stock and ready to ship.", reg)
        vr  = ctx["validation_result"]
        assert len(vr.contradictions) >= 1

    def test_french_status_delivered_vs_shipped(self):
        reg = _registry(status="shipped")
        ctx = _run("Votre commande a été livrée hier.", reg)
        vr  = ctx["validation_result"]
        assert len(vr.contradictions) >= 1

    def test_no_status_in_draft_passes(self):
        reg = _registry(status="shipped")
        ctx = _run("Thank you for your patience. Our team is reviewing your request.", reg)
        assert ctx["validation_result"].verified is True


# ---------------------------------------------------------------------------
# Date checks
# ---------------------------------------------------------------------------

class TestDateValidation:
    def test_correct_date_passes(self):
        reg = _registry(delivery_date="2024-05-15")
        ctx = _run("Your delivery is scheduled for 15/05/2024.", reg)
        assert ctx["validation_result"].verified is True

    def test_wrong_date_goes_to_unsupported(self):
        reg = _registry(delivery_date="2024-05-15")
        ctx = _run("Expected delivery: 20/06/2024.", reg)
        vr  = ctx["validation_result"]
        # Wrong date — unsupported (not a direct contradiction)
        assert len(vr.unsupported_claims) >= 1

    def test_no_date_in_draft_passes(self):
        reg = _registry(delivery_date="2024-05-15")
        ctx = _run("We will update you shortly.", reg)
        assert ctx["validation_result"].verified is True


# ---------------------------------------------------------------------------
# ValidationResult fields
# ---------------------------------------------------------------------------

class TestValidationResultFields:
    def test_supported_claims_ratio_one_when_verified(self):
        ctx = _run("", FactRegistry())
        assert ctx["validation_result"].supported_claims_ratio == 1.0

    def test_verified_false_sets_pipeline_error(self):
        reg = _registry(order_id="ORD-001", status="shipped")
        # Draft has both a wrong order ID and a contradicting status
        ctx = _run(
            "Your order ORD-999 has been delivered.",
            reg, order_id="ORD-001",
        )
        vr = ctx["validation_result"]
        if not vr.verified:
            assert ctx.get("pipeline_error") == "validation_failed"

    def test_verified_true_no_pipeline_error(self):
        ctx = _run("Thank you for contacting us.", _registry())
        assert ctx.get("pipeline_error") != "validation_failed"


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestPureHelpers:
    def test_status_contradiction_delivered_vs_shipped(self):
        result = _is_status_contradiction("delivered", {"shipped"})
        assert result == "shipped"

    def test_status_contradiction_no_match(self):
        result = _is_status_contradiction("delivered", {"delivered"})
        assert result is None

    def test_status_contradiction_in_stock_vs_out_of_stock(self):
        result = _is_status_contradiction("in_stock", {"out_of_stock"})
        assert result == "out_of_stock"

    def test_normalise_date_iso(self):
        assert _normalise_date("2024-05-15") == "15052024"

    def test_normalise_date_slash(self):
        assert _normalise_date("15/05/2024") == "15052024"

    def test_normalise_date_same_result_both_formats(self):
        assert _normalise_date("2024-05-15") == _normalise_date("15/05/2024")

    def test_normalise_date_invalid_returns_none(self):
        assert _normalise_date("yesterday") is None
        assert _normalise_date("soon")      is None
