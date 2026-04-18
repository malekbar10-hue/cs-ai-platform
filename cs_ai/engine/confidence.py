"""
confidence.py — Overall confidence scorer for AI-generated customer service drafts.

Combines five independent risk signals into a single score and recommendation.
Thresholds and auto-send behaviour are controlled via config.json → "confidence".
"""

import json
import os
from paths import config_path as _config_path


# ==============================================================================
# SCORING TABLES
# ==============================================================================

# emotion_risk: how risky is it to send without review based on emotion + intensity
_EMOTION_RISK: dict[str, dict[str, float]] = {
    "Angry":      {"Very High": 0.00, "High": 0.10, "Medium": 0.25, "Low": 0.40},
    "Frustrated": {"Very High": 0.10, "High": 0.20, "Medium": 0.40, "Low": 0.55},
    "Urgent":     {"Very High": 0.15, "High": 0.25, "Medium": 0.50, "Low": 0.65},
    "Anxious":    {"Very High": 0.30, "High": 0.45, "Medium": 0.60, "Low": 0.75},
    "Neutral":    {"Very High": 0.80, "High": 0.80, "Medium": 0.80, "Low": 0.80},
    "Satisfied":  {"Very High": 1.00, "High": 1.00, "Medium": 1.00, "Low": 1.00},
}

# intent_complexity: how complex / sensitive is the intent to handle automatically
_INTENT_COMPLEXITY: dict[str, float] = {
    "escalate":         0.10,
    "complaint":        0.10,
    "cancel":           0.30,
    "ncmr":             0.35,
    "refund":           0.45,
    "replace":          0.50,
    "document_request": 0.65,
    "payment":          0.60,
    "tracking":         0.90,
    "info":             0.90,
    "general inquiry":  0.85,
}

# action_risk: confidence penalty from suggested ERP action risk level
_ACTION_RISK: dict[str | None, float] = {
    "High":   0.00,
    "Medium": 0.40,
    "Low":    0.80,
    None:     1.00,   # no action suggested
}

# Scoring weights — must sum to 1.0
_WEIGHTS = {
    "nlp":              0.30,
    "emotion_risk":     0.25,
    "customer_risk":    0.25,
    "action_risk":      0.15,
    "intent_complexity":0.10,
}


# ==============================================================================
# CONFIG DEFAULTS
# ==============================================================================

_DEFAULT_CONF_CONFIG = {
    "auto_send_threshold":    0.85,
    "human_review_threshold": 0.50,
    "auto_send_enabled":      False,
}


def _load_conf_config() -> dict:
    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            return json.load(f).get("confidence", _DEFAULT_CONF_CONFIG)
    except Exception:
        return _DEFAULT_CONF_CONFIG


# ==============================================================================
# CONFIDENCE SCORER
# ==============================================================================

class ConfidenceScorer:
    """
    Aggregates five risk signals into an overall confidence score and
    a routing recommendation (auto_send / human_review / supervisor_review).

    Hard override rules always apply regardless of the numeric score:
      - ERP action risk == "High"              → force supervisor_review
      - Angry AND intensity High/Very High     → minimum human_review
      - Customer trajectory == "Escalating"   → minimum human_review
      - First contact (no profile)             → minimum human_review
    """

    def __init__(self):
        self._cfg = _load_conf_config()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _emotion_risk_score(self, emotion: str, intensity: str) -> float:
        row = _EMOTION_RISK.get(emotion, _EMOTION_RISK["Neutral"])
        return row.get(intensity, row.get("Low", 0.80))

    def _customer_risk_score(self, profile: dict | None, trajectory: dict | None) -> float:
        if profile is None:
            return 0.50   # first contact — unknown risk

        if trajectory and trajectory.get("trend") == "Escalating":
            return 0.10   # actively escalating — high risk

        total    = profile.get("total_interactions", 0)
        resolved = profile.get("resolved_cases", 0)
        dom_emo  = profile.get("dominant_emotion", "Neutral")

        if dom_emo in ("Satisfied", "Neutral") and total >= 3 and resolved >= 2:
            return 0.90   # happy repeat customer — low risk

        if dom_emo in ("Angry", "Frustrated") and total >= 3:
            return 0.25   # historically difficult client

        if total == 0:
            return 0.50   # no history yet

        # General score: resolution rate as proxy for relationship health
        resolution_rate = resolved / total if total > 0 else 0.5
        base = 0.40 + resolution_rate * 0.40   # 0.40 – 0.80
        if trajectory and trajectory.get("trend") == "Improving":
            base = min(1.0, base + 0.10)
        return round(base, 3)

    def _intent_complexity_score(self, intent: str) -> float:
        return _INTENT_COMPLEXITY.get(intent, 0.70)

    def _action_risk_score(self, action: dict | None) -> float:
        risk_level = action.get("risk") if action else None
        return _ACTION_RISK.get(risk_level, 1.00)

    def _apply_overrides(
        self,
        recommendation: str,
        emotion: str,
        intensity: str,
        action: dict | None,
        trajectory: dict | None,
        profile: dict | None,
    ) -> str:
        """Apply hard override rules — these can only escalate, never downgrade."""

        # Rule 1: High-risk ERP action → always supervisor
        if action and action.get("risk") == "High":
            return "supervisor_review"

        # Rule 2: Very angry customer → at least human review
        if emotion == "Angry" and intensity in ("High", "Very High"):
            if recommendation == "auto_send":
                return "human_review"

        # Rule 3: Escalating trajectory → at least human review
        if trajectory and trajectory.get("trend") == "Escalating":
            if recommendation == "auto_send":
                return "human_review"

        # Rule 4: First contact (no profile) → at least human review
        if profile is None:
            if recommendation == "auto_send":
                return "human_review"

        return recommendation

    # ── Public API ────────────────────────────────────────────────────────────

    def score(
        self,
        nlp_confidence: float,
        emotion: str,
        intensity: str,
        intent: str,
        profile: dict | None,
        trajectory: dict | None,
        action: dict | None,
    ) -> dict:
        """
        Parameters
        ----------
        nlp_confidence  : top cosine similarity from nlp.py (0–1)
        emotion         : detected emotion string
        intensity       : "Low" | "Medium" | "High" | "Very High"
        intent          : detected intent string
        profile         : customer profile dict or None (first contact)
        trajectory      : emotional trajectory dict or None
        action          : suggested ERP action dict or None

        Returns
        -------
        {
          "overall":        float 0.0–1.0,
          "recommendation": "auto_send" | "human_review" | "supervisor_review",
          "factors": {
            "nlp":              float,
            "emotion_risk":     float,
            "customer_risk":    float,
            "action_risk":      float,
            "intent_complexity":float,
          }
        }
        """
        # ── Factor scores (all 0–1, higher = more confident / lower risk) ────
        factors = {
            "nlp":               round(float(nlp_confidence), 3),
            "emotion_risk":      self._emotion_risk_score(emotion, intensity),
            "customer_risk":     self._customer_risk_score(profile, trajectory),
            "action_risk":       self._action_risk_score(action),
            "intent_complexity": self._intent_complexity_score(intent),
        }

        # ── Weighted overall score ────────────────────────────────────────────
        overall = sum(_WEIGHTS[k] * v for k, v in factors.items())
        overall = round(overall, 3)

        # ── Base recommendation from thresholds ───────────────────────────────
        auto_t   = self._cfg.get("auto_send_threshold",    0.85)
        human_t  = self._cfg.get("human_review_threshold", 0.50)

        if overall >= auto_t:
            recommendation = "auto_send"
        elif overall >= human_t:
            recommendation = "human_review"
        else:
            recommendation = "supervisor_review"

        # ── Hard overrides ────────────────────────────────────────────────────
        recommendation = self._apply_overrides(
            recommendation, emotion, intensity, action, trajectory, profile
        )

        # ── auto_send_enabled guard — never auto-send if disabled in config ──
        if recommendation == "auto_send" and not self._cfg.get("auto_send_enabled", False):
            recommendation = "human_review"

        return {
            "overall":        overall,
            "recommendation": recommendation,
            "factors":        factors,
        }
