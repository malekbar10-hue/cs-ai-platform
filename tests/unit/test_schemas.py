"""
tests/unit/test_schemas.py — Unit tests for Pydantic schemas.

Run with:  pytest tests/unit/test_schemas.py -v

No database, network, or config required.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine"))

import pytest
from pydantic import ValidationError
from schemas import (
    ConfidenceScores,
    TriageResult,
    DraftResponse,
    QAResult,
    ValidationResult,
    DecisionResult,
    normalise_intent,
    normalise_emotion,
)


# ---------------------------------------------------------------------------
# ConfidenceScores
# ---------------------------------------------------------------------------

class TestConfidenceScores:
    def _valid(self, **overrides):
        defaults = dict(
            intent=0.8, emotion=0.7, data_completeness=0.9,
            factual_support=0.85, tone_quality=0.75, final=0.8,
        )
        defaults.update(overrides)
        return ConfidenceScores(**defaults)

    def test_valid_construction(self):
        s = self._valid()
        assert s.final == 0.8

    def test_rejects_value_above_1(self):
        with pytest.raises(ValidationError):
            self._valid(intent=1.1)

    def test_rejects_negative_value(self):
        with pytest.raises(ValidationError):
            self._valid(emotion=-0.1)

    def test_boundary_zero_and_one(self):
        s = self._valid(intent=0.0, final=1.0)
        assert s.intent == 0.0
        assert s.final  == 1.0

    def test_strict_rejects_string_coercion(self):
        """strict=True means "0.8" (string) must be rejected."""
        with pytest.raises(ValidationError):
            self._valid(intent="0.8")   # type: ignore


# ---------------------------------------------------------------------------
# TriageResult
# ---------------------------------------------------------------------------

class TestTriageResult:
    def _valid(self, **overrides):
        defaults = dict(intent="complaint", emotion="frustrated", language="English")
        defaults.update(overrides)
        return TriageResult(**defaults)

    def test_valid_construction(self):
        t = self._valid()
        assert t.intent   == "complaint"
        assert t.emotion  == "frustrated"
        assert t.route    == "standard"   # default
        assert t.is_noise is False

    def test_invalid_intent_raises(self):
        with pytest.raises(ValidationError):
            self._valid(intent="gibberish")

    def test_invalid_emotion_raises(self):
        with pytest.raises(ValidationError):
            self._valid(emotion="ecstatic")

    def test_invalid_route_raises(self):
        with pytest.raises(ValidationError):
            self._valid(route="manual")

    def test_all_valid_intents(self):
        valid = [
            "order_status", "complaint", "delay", "invoice",
            "cancellation", "modification", "unknown",
        ]
        for intent in valid:
            t = self._valid(intent=intent)
            assert t.intent == intent

    def test_all_valid_routes(self):
        for route in ("auto", "standard", "priority", "supervisor"):
            t = self._valid(route=route)
            assert t.route == route

    def test_risk_flags_and_missing_fields_default_empty(self):
        t = self._valid()
        assert t.risk_flags     == []
        assert t.missing_fields == []

    def test_confidence_defaults_none(self):
        t = self._valid()
        assert t.confidence is None

    def test_with_confidence_scores(self):
        conf = ConfidenceScores(
            intent=0.9, emotion=0.8, data_completeness=0.85,
            factual_support=0.9, tone_quality=0.8, final=0.87,
        )
        t = self._valid(confidence=conf)
        assert t.confidence.final == 0.87


# ---------------------------------------------------------------------------
# DraftResponse
# ---------------------------------------------------------------------------

class TestDraftResponse:
    def test_valid_construction(self):
        d = DraftResponse(
            ticket_id="abc-123",
            body="Dear customer, your order is on the way.",
            language="English",
        )
        assert d.ticket_id   == "abc-123"
        assert d.prompt_ref  == "unversioned"
        assert d.facts_used  == []
        assert d.token_usage == {}

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            DraftResponse(body="hi", language="English")   # missing ticket_id

    def test_token_usage_accepts_dict(self):
        d = DraftResponse(
            ticket_id="t1", body="hi", language="French",
            token_usage={"prompt_tokens": 50, "completion_tokens": 120},
        )
        assert d.token_usage["completion_tokens"] == 120


# ---------------------------------------------------------------------------
# QAResult
# ---------------------------------------------------------------------------

class TestQAResult:
    def test_pass_verdict(self):
        r = QAResult(verdict="pass")
        assert r.verdict  == "pass"
        assert r.feedback == ""
        assert r.issues   == []

    def test_needs_revision_verdict(self):
        r = QAResult(verdict="needs_revision", feedback="Add order ID", issues=["Missing ID"])
        assert r.verdict == "needs_revision"
        assert len(r.issues) == 1

    def test_invalid_verdict_raises(self):
        with pytest.raises(ValidationError):
            QAResult(verdict="rejected")

    def test_invalid_verdict_raises_partial(self):
        with pytest.raises(ValidationError):
            QAResult(verdict="PASS")    # case-sensitive


# ---------------------------------------------------------------------------
# DecisionResult
# ---------------------------------------------------------------------------

class TestDecisionResult:
    def test_valid_actions(self):
        for action in ("send", "review", "block", "escalate"):
            d = DecisionResult(action=action, reason="test")
            assert d.action == action

    def test_invalid_action_raises(self):
        with pytest.raises(ValidationError):
            DecisionResult(action="approve", reason="test")

    def test_invalid_action_unknown_raises(self):
        with pytest.raises(ValidationError):
            DecisionResult(action="unknown", reason="test")

    def test_defaults(self):
        d = DecisionResult(action="send", reason="all good")
        assert d.required_human_review is False
        assert d.blocked_by == []


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------

class TestValidationResult:
    def test_valid(self):
        v = ValidationResult(verified=True, supported_claims_ratio=0.95)
        assert v.verified is True

    def test_ratio_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            ValidationResult(verified=True, supported_claims_ratio=1.5)

    def test_ratio_boundary(self):
        ValidationResult(verified=False, supported_claims_ratio=0.0)
        ValidationResult(verified=True,  supported_claims_ratio=1.0)


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

class TestNormaliseHelpers:
    def test_intent_known(self):
        assert normalise_intent("tracking")  == "order_status"
        assert normalise_intent("cancel")    == "cancellation"
        assert normalise_intent("complaint") == "complaint"

    def test_intent_unknown_fallback(self):
        assert normalise_intent("gibberish") == "unknown"
        assert normalise_intent("escalate")  == "unknown"

    def test_emotion_known(self):
        assert normalise_emotion("Angry")      == "angry"
        assert normalise_emotion("Satisfied")  == "calm"
        assert normalise_emotion("Frustrated") == "frustrated"
        assert normalise_emotion("Neutral")    == "neutral"

    def test_emotion_fallback(self):
        assert normalise_emotion("Confused") == "neutral"
