# P0-05 — Policy Engine (Code-First)

## What This Does

Right now the only "rules" the system enforces are embedded in LLM prompts.
If the prompt changes, the rule changes or disappears. There is no way to audit
which rules are enforced, no way to test them, and no guarantee they actually fire.

This improvement introduces a code-first `PolicyEngine` that evaluates explicit
Python `PolicyRule` objects. Rules are expressed as pure Python functions —
not prompts — and are evaluated before any draft is auto-sent. Violations produce
a classified `SECURITY` log entry and a `block` or `review` decision.

Default rules implemented:
- No promised delivery date if no verified delivery_date Fact exists
- No auto-send if emotion is "angry" AND confidence.final < 0.7
- No sensitive write action without human approval
- No auto-send if ValidationResult has any unsupported_claims

**Where the change lives:**
New file `cs_ai/engine/policy_engine.py` + update orchestrator to call it
before the final decision.

**Impact:** Business rules are explicit, testable, and audit-logged. Changing a
prompt never silently removes a safety rule. Every violation is traceable.

---

## Prompt — Paste into Claude Code

```
Add a code-first PolicyEngine that enforces business rules before any auto-send action.

TASK:

1. Create cs_ai/engine/policy_engine.py:

   import logging
   from dataclasses import dataclass, field
   from typing import Callable
   log = logging.getLogger(__name__)

   @dataclass
   class PolicyRule:
       name:        str
       description: str
       severity:    str   # "block" | "review" | "warn"
       check:       Callable[[dict], bool]
       # check(ctx) returns True if the rule is VIOLATED (True = problem found)

   @dataclass
   class PolicyDecision:
       passed:    bool          # True = no violations
       violations: list[str] = field(default_factory=list)
       required_actions: list[str] = field(default_factory=list)   # "block" | "review"

   class PolicyEngine:

       def __init__(self):
           self._rules: list[PolicyRule] = []
           self._register_defaults()

       def _register_defaults(self):
           # Rule 1: no promised delivery date without verified fact
           self.add_rule(PolicyRule(
               name="no_unverified_delivery_date",
               description="Draft must not promise a delivery date unless delivery_date is a verified Fact",
               severity="block",
               check=self._check_unverified_date,
           ))
           # Rule 2: no auto-send on anger + low confidence
           self.add_rule(PolicyRule(
               name="no_autosend_angry_low_confidence",
               description="Do not auto-send if customer is angry and confidence.final < 0.7",
               severity="review",
               check=self._check_angry_low_confidence,
           ))
           # Rule 3: no auto-send with unsupported claims
           self.add_rule(PolicyRule(
               name="no_unsupported_claims",
               description="Do not auto-send a draft with any unsupported factual claims",
               severity="block",
               check=self._check_unsupported_claims,
           ))
           # Rule 4: sensitive ERP action requires human approval
           self.add_rule(PolicyRule(
               name="erp_action_requires_approval",
               description="Any suggested ERP action (cancel, refund, modify) requires human approval",
               severity="review",
               check=self._check_erp_action,
           ))

       def _check_unverified_date(self, ctx: dict) -> bool:
           draft = ctx.get("draft", "")
           import re
           has_date_claim = bool(re.search(
               r'\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|'
               r'dans \d+ jours?|within \d+ days?|'
               r'le \d{1,2}|by \w+ \d{1,2})\b',
               draft, re.IGNORECASE
           ))
           if not has_date_claim:
               return False
           registry = ctx.get("fact_registry")
           if registry is None:
               return True   # no registry = can't verify = violation
           return registry.get("delivery_date") is None

       def _check_angry_low_confidence(self, ctx: dict) -> bool:
           triage = ctx.get("triage_result")
           if triage is None:
               emotion = ctx.get("emotion", "")
               conf = ctx.get("confidence_score", 1.0)
           else:
               emotion = triage.emotion
               conf = triage.confidence.final if triage.confidence else 1.0
           return emotion == "angry" and conf < 0.7

       def _check_unsupported_claims(self, ctx: dict) -> bool:
           v = ctx.get("validation_result")
           if v is None:
               return False
           return len(v.unsupported_claims) > 0

       def _check_erp_action(self, ctx: dict) -> bool:
           action = ctx.get("suggested_action", "")
           sensitive = ["cancel", "refund", "modify", "annul", "rembours"]
           return any(s in action.lower() for s in sensitive)

       def add_rule(self, rule: PolicyRule) -> None:
           self._rules.append(rule)

       def evaluate(self, ctx: dict) -> PolicyDecision:
           violations = []
           required_actions = set()
           for rule in self._rules:
               try:
                   if rule.check(ctx):
                       violations.append(rule.name)
                       required_actions.add(rule.severity)
                       log.warning(
                           "POLICY_VIOLATION rule=%s severity=%s ticket_id=%s",
                           rule.name, rule.severity, ctx.get("ticket_id","?"),
                           extra={"event": "policy_violation"}
                       )
               except Exception as e:
                   log.error("POLICY_RULE_ERROR rule=%s error=%s", rule.name, e)
           return PolicyDecision(
               passed=len(violations) == 0,
               violations=violations,
               required_actions=sorted(required_actions),
           )

2. Update cs_ai/engine/agents/orchestrator.py:
   - Import PolicyEngine from policy_engine.
   - Instantiate: self._policy = PolicyEngine() in __init__.
   - In run(), after validation, call:
       policy_decision = self._policy.evaluate(ctx)
       ctx["policy_decision"] = policy_decision
   - If "block" in policy_decision.required_actions:
       set ctx["final_decision"] = DecisionResult(action="block",
           reason="policy_block: " + ", ".join(policy_decision.violations),
           required_human_review=True,
           blocked_by=policy_decision.violations)
       skip sending.
   - If "review" in policy_decision.required_actions (and no block):
       set ctx["final_decision"] = DecisionResult(action="review",
           reason="policy_review: " + ", ".join(policy_decision.violations),
           required_human_review=True)

3. Create tests/unit/test_policy_engine.py:
   - Test _check_angry_low_confidence: ctx with emotion="angry", confidence=0.5 → True (violation).
   - Test _check_angry_low_confidence: ctx with emotion="calm", confidence=0.5 → False (no violation).
   - Test _check_unsupported_claims: validation_result with unsupported_claims=["date"] → True.
   - Test _check_erp_action: suggested_action="refund order" → True (violation).
   - Test evaluate() with a clean context → PolicyDecision(passed=True, violations=[]).
   - Test evaluate() with angry + low confidence → violations includes "no_autosend_angry_low_confidence".

Do NOT change nlp.py, channels.py, tickets.py, app.py, app_inbox.py, or any JSON data files.
Do NOT add any rules that depend on LLM calls — all rules must be pure Python.
```
