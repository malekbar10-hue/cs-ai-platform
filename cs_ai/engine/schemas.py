"""
schemas.py — Pydantic v2 schemas for every agent boundary in the CS AI engine.

All models use strict=True so implicit type coercion is rejected at construction
time rather than silently producing wrong values.

Usage:
    from schemas import TriageResult, DraftResponse, QAResult, ...
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class ConfidenceScores(BaseModel):
    model_config = ConfigDict(strict=True)

    intent:            float = Field(ge=0.0, le=1.0)
    emotion:           float = Field(ge=0.0, le=1.0)
    data_completeness: float = Field(ge=0.0, le=1.0)
    factual_support:   float = Field(ge=0.0, le=1.0)
    tone_quality:      float = Field(ge=0.0, le=1.0)
    final:             float = Field(ge=0.0, le=1.0)


class TriageResult(BaseModel):
    model_config = ConfigDict(strict=True)

    intent: Literal[
        "order_status", "complaint", "delay", "invoice",
        "cancellation", "modification", "unknown"
    ]
    emotion:        Literal["calm", "neutral", "frustrated", "angry"]
    language:       str
    risk_flags:     list[str] = []
    missing_fields: list[str] = []
    route:          Literal["auto", "standard", "priority", "supervisor"] = "standard"
    confidence:     ConfidenceScores | None = None
    is_noise:       bool = False
    noise_reason:   str  = ""


class DraftResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    ticket_id:   str
    body:        str
    language:    str
    prompt_ref:  str       = "unversioned"
    facts_used:  list[str] = []
    model_used:  str       = ""
    token_usage: dict      = {}


class QAResult(BaseModel):
    model_config = ConfigDict(strict=True)

    verdict:  Literal["pass", "needs_revision"]
    feedback: str       = ""
    issues:   list[str] = []


class ValidationResult(BaseModel):
    model_config = ConfigDict(strict=True)

    verified:               bool
    unsupported_claims:     list[str] = []
    contradictions:         list[str] = []
    policy_violations:      list[str] = []
    supported_claims_ratio: float     = Field(ge=0.0, le=1.0, default=1.0)


class DecisionResult(BaseModel):
    model_config = ConfigDict(strict=True)

    action:                Literal["send", "review", "block", "escalate"]
    reason:                str
    required_human_review: bool      = False
    blocked_by:            list[str] = []


# ---------------------------------------------------------------------------
# Normalisation helpers used by agents to map internal values to Literal sets
# ---------------------------------------------------------------------------

_INTENT_MAP: dict[str, str] = {
    "tracking":        "order_status",
    "order_status":    "order_status",
    "complaint":       "complaint",
    "delay":           "delay",
    "invoice":         "invoice",
    "cancel":          "cancellation",
    "cancellation":    "cancellation",
    "modification":    "modification",
    "modify":          "modification",
    "document_request":"unknown",
    "info":            "unknown",
    "escalate":        "unknown",
    "general inquiry": "unknown",
    "general":         "unknown",
}

_EMOTION_MAP: dict[str, str] = {
    "Neutral":    "neutral",
    "Satisfied":  "calm",
    "Frustrated": "frustrated",
    "Angry":      "angry",
    "Urgent":     "frustrated",
    "Anxious":    "frustrated",
}


def normalise_intent(raw: str) -> str:
    """Map a raw detect_intent() value to a TriageResult-compatible literal."""
    return _INTENT_MAP.get(raw, "unknown")


def normalise_emotion(raw: str) -> str:
    """Map a raw detect_emotion() value to a TriageResult-compatible literal."""
    return _EMOTION_MAP.get(raw, "neutral")
