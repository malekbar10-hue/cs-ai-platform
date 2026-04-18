"""
escalation.py — Generic escalation rule engine.

Loads escalation_rules.json from the active company directory and decides
whether a ticket or message should be escalated, and to what tier.

Rules are 100% config-driven. No company-specific logic in this file.

escalation_rules.json shape:
{
  "rules": [
    {
      "id":        "rule_angry_high",
      "condition": {"emotion": "Angry", "intensity": ["High", "Very High"]},
      "action":    "escalate",
      "tier":      "supervisor",
      "reason":    "Angry customer with high intensity"
    },
    ...
  ],
  "default_action": "none"
}
"""

from __future__ import annotations

import json
import os
from typing import Optional

from paths import resolve_company_file


def load_rules(company: str | None = None) -> list[dict]:
    """Load escalation rules from the company config directory."""
    path = resolve_company_file("escalation_rules.json", company)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("rules", [])


def evaluate(
    emotion: str,
    intensity: str,
    intent: str,
    confidence: float,
    company: str | None = None,
) -> dict:
    """
    Evaluate escalation rules against the current message signal.

    Returns:
        {
          "escalate": bool,
          "tier":     str | None,   e.g. "supervisor", "team_lead", "none"
          "reason":   str | None,
          "rule_id":  str | None,
        }
    """
    rules = load_rules(company)

    for rule in rules:
        cond = rule.get("condition", {})

        # Emotion match
        if "emotion" in cond:
            expected = cond["emotion"]
            if isinstance(expected, list):
                if emotion not in expected:
                    continue
            elif emotion != expected:
                continue

        # Intensity match
        if "intensity" in cond:
            expected = cond["intensity"]
            if isinstance(expected, list):
                if intensity not in expected:
                    continue
            elif intensity != expected:
                continue

        # Intent match
        if "intent" in cond:
            expected = cond["intent"]
            if isinstance(expected, list):
                if intent not in expected:
                    continue
            elif intent != expected:
                continue

        # Confidence threshold
        if "confidence_below" in cond:
            if confidence >= cond["confidence_below"]:
                continue

        # Rule matched
        action = rule.get("action", "none")
        return {
            "escalate": action == "escalate",
            "tier":     rule.get("tier"),
            "reason":   rule.get("reason"),
            "rule_id":  rule.get("id"),
        }

    return {"escalate": False, "tier": None, "reason": None, "rule_id": None}


def preview_escalation(context: dict) -> list:
    """
    Return every rule that WOULD match the given context, without executing anything.
    Safe to call at triage time — confidence defaults to 0.0 when not yet scored.
    """
    emotion    = context.get("emotion", "")
    intensity  = context.get("intensity", "")
    intent     = context.get("intent", "")
    conf_raw   = context.get("confidence", 0.0)
    confidence = conf_raw.get("overall", 0.0) if isinstance(conf_raw, dict) else float(conf_raw or 0.0)

    company = os.environ.get("CS_AI_COMPANY")
    rules   = load_rules(company)
    matches = []

    for rule in rules:
        cond = rule.get("condition", {})

        if "emotion" in cond:
            expected = cond["emotion"]
            if isinstance(expected, list):
                if emotion not in expected:
                    continue
            elif emotion != expected:
                continue

        if "intensity" in cond:
            expected = cond["intensity"]
            if isinstance(expected, list):
                if intensity not in expected:
                    continue
            elif intensity != expected:
                continue

        if "intent" in cond:
            expected = cond["intent"]
            if isinstance(expected, list):
                if intent not in expected:
                    continue
            elif intent != expected:
                continue

        if "confidence_below" in cond:
            if confidence >= cond["confidence_below"]:
                continue

        matches.append({
            "rule_id":   rule.get("id", ""),
            "rule_name": rule.get("reason", rule.get("id", "Escalation rule")),
            "reason":    rule.get("reason", ""),
            "tier":      rule.get("tier", ""),
        })

    return matches
