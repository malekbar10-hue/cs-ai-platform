"""
policy_engine.py — Code-first business rule enforcement.

Evaluates a set of PolicyRules against the pipeline context before any
auto-send action.  Rules are pure Python — no LLM calls.

Usage:
    engine = PolicyEngine()
    decision = engine.evaluate(ctx)
    if not decision.passed:
        if "block" in decision.required_actions:
            ctx["decision"] = "block"
        elif "review" in decision.required_actions:
            ctx["decision"] = "review"
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Callable

log = logging.getLogger(__name__)


@dataclass
class PolicyRule:
    name:        str
    description: str
    severity:    str          # "block" | "review" | "warn"
    check:       Callable[[dict], bool]   # True = rule VIOLATED


@dataclass
class PolicyDecision:
    passed:           bool
    violations:       list[str] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)


class PolicyEngine:

    def __init__(self):
        self._rules: list[PolicyRule] = []
        self._register_defaults()

    # ── Default rules ─────────────────────────────────────────────────────

    def _register_defaults(self) -> None:
        self.add_rule(PolicyRule(
            name="no_unverified_delivery_date",
            description="Draft must not promise a delivery date without a verified Fact",
            severity="block",
            check=self._check_unverified_date,
        ))
        self.add_rule(PolicyRule(
            name="no_autosend_angry_low_confidence",
            description="No auto-send if emotion=angry AND confidence.final < 0.7",
            severity="review",
            check=self._check_angry_low_confidence,
        ))
        self.add_rule(PolicyRule(
            name="no_unsupported_claims",
            description="No auto-send with any unsupported factual claims",
            severity="block",
            check=self._check_unsupported_claims,
        ))
        self.add_rule(PolicyRule(
            name="erp_action_requires_approval",
            description="Any cancel/refund/modify suggestion requires human approval",
            severity="review",
            check=self._check_erp_action,
        ))

    # ── Rule implementations ──────────────────────────────────────────────

    @staticmethod
    def _check_unverified_date(ctx: dict) -> bool:
        draft = ctx.get("draft", "")
        if not draft:
            dr = ctx.get("draft_result")
            draft = dr.body if dr else ""

        has_date = bool(re.search(
            r'\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}'
            r'|dans\s+\d+\s+jours?'
            r'|within\s+\d+\s+(?:business\s+)?days?)\b',
            draft, re.IGNORECASE,
        ))
        if not has_date:
            return False

        reg = ctx.get("fact_registry")
        if reg is None:
            return True

        # Date is mentioned — pass only if at least one date fact is registered
        has_verified_date = any(
            reg.get(k) is not None
            for k in ("order.delivery_date", "order.expected_delivery",
                      "order.ship_date", "order.estimated_delivery",
                      "delivery_date")
        )
        return not has_verified_date

    @staticmethod
    def _check_angry_low_confidence(ctx: dict) -> bool:
        triage = ctx.get("triage_result")
        if triage is not None:
            emotion = getattr(triage, "emotion", "")
            conf_obj = getattr(triage, "confidence", None)
            conf = getattr(conf_obj, "final", None) if conf_obj else None
        else:
            emotion = ctx.get("emotion", "")
            conf = None

        if conf is None:
            conf_dict = ctx.get("confidence")
            if isinstance(conf_dict, dict):
                conf = conf_dict.get("final", conf_dict.get("overall", 1.0))
            else:
                conf = ctx.get("confidence_score", 1.0)

        return emotion == "angry" and (conf or 1.0) < 0.7

    @staticmethod
    def _check_unsupported_claims(ctx: dict) -> bool:
        v = ctx.get("validation_result")
        return v is not None and len(v.unsupported_claims) > 0

    @staticmethod
    def _check_erp_action(ctx: dict) -> bool:
        action = ctx.get("suggested_action") or ctx.get("action", "")
        if not isinstance(action, str):
            action = str(action)
        return any(
            s in action.lower()
            for s in ["cancel", "refund", "modify", "annul", "rembours"]
        )

    # ── Public API ────────────────────────────────────────────────────────

    def add_rule(self, rule: PolicyRule) -> None:
        self._rules.append(rule)

    def evaluate(self, ctx: dict) -> PolicyDecision:
        violations: list[str] = []
        required:   set[str]  = set()

        for rule in self._rules:
            try:
                if rule.check(ctx):
                    violations.append(rule.name)
                    required.add(rule.severity)
                    log.warning(
                        "POLICY_VIOLATION rule=%s severity=%s ticket=%s",
                        rule.name, rule.severity, ctx.get("ticket_id", "?"),
                    )
            except Exception as exc:
                log.error("POLICY_RULE_ERROR rule=%s error=%s", rule.name, exc)

        return PolicyDecision(
            passed=           not violations,
            violations=       violations,
            required_actions= sorted(required),
        )
