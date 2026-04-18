# P0-03 — Fact Registry

## What This Does

Right now when the response agent writes a reply, it can invent information —
a delivery date, an order status, a stock level — that was never actually returned
by the ERP or CRM. The QA agent reviews tone and style but does not check whether
the claims in the draft are actually supported by real retrieved data.

This improvement introduces a `FactRegistry`: a typed store of verified facts built
from ERP/CRM/KB responses during the pipeline. The validator agent then checks every
factual claim in the draft against this registry. If a claim cannot be traced to a
verified fact, it is flagged as `unsupported_claim` and the decision engine blocks
the draft from auto-sending.

**Where the change lives:**
New file `cs_ai/engine/fact_registry.py` + update
`cs_ai/engine/agents/fact_builder.py` (new file) + update
`cs_ai/engine/agents/validator.py` (new file) + update orchestrator to include
FactBuilder and Validator steps.

**Impact:** Hallucinated facts never reach the customer. Every claim in a sent
reply is traceable to a source (ERP, CRM, KB, or email content).

---

## Prompt — Paste into Claude Code

```
Add a Fact Registry and a Validator Agent to prevent hallucinated claims from
reaching the customer.

TASK:

1. Create cs_ai/engine/fact_registry.py:

   from pydantic import BaseModel, ConfigDict
   from typing import Literal
   import time

   class Fact(BaseModel):
       model_config = ConfigDict(strict=True)
       key:          str           # e.g. "order_status", "delivery_date"
       value:        str | int | float | bool | None
       source_type:  Literal["erp","crm","email","attachment","kb","derived"]
       source_ref:   str           # e.g. "ERP:order/ORD-123" or "KB:article-42"
       verified:     bool = False  # True = came from an external system call
       observed_at:  str           # ISO-8601 timestamp
       ttl_s:        int = 3600    # how long this fact is valid
       sensitivity:  Literal["public","internal","pii","restricted"] = "internal"

       def is_expired(self) -> bool:
           import datetime
           obs = datetime.datetime.fromisoformat(self.observed_at)
           age = (datetime.datetime.utcnow() - obs).total_seconds()
           return age > self.ttl_s

   class FactRegistry:
       def __init__(self):
           self._facts: dict[str, Fact] = {}   # keyed by fact.key

       def register(self, fact: Fact) -> None:
           self._facts[fact.key] = fact

       def get(self, key: str) -> Fact | None:
           f = self._facts.get(key)
           if f and f.is_expired():
               return None
           return f

       def all_verified(self) -> list[Fact]:
           return [f for f in self._facts.values() if f.verified and not f.is_expired()]

       def to_context_string(self) -> str:
           """Human-readable summary of verified facts for inclusion in prompts."""
           lines = []
           for f in self.all_verified():
               lines.append(f"[{f.source_type.upper()}] {f.key}: {f.value}")
           return "\n".join(lines) if lines else "(no verified facts)"

2. Create cs_ai/engine/agents/fact_builder.py:
   class FactBuilder(BaseAgent):
       name = "fact_builder"
       def run(self, context: dict) -> dict:
           """
           Build a FactRegistry from what the triage agent already retrieved.
           - Look at ctx["order_info"] (from ERP) and register each field as a Fact
             with source_type="erp", verified=True, source_ref="ERP:order/<id>".
           - Look at ctx["customer_profile"] and register relevant fields as
             source_type="crm", verified=True.
           - Store the registry at ctx["fact_registry"] = FactRegistry instance.
           - Also store a context string at ctx["verified_facts_context"] for use
             in the response agent's system prompt.
           - Use datetime.utcnow().isoformat() for observed_at.
           """
           ...

3. Create cs_ai/engine/agents/validator.py:
   class ValidatorAgent(BaseAgent):
       name = "validator"
       def run(self, context: dict) -> dict:
           """
           Check the draft body for factual claims and verify them against the FactRegistry.
           - Get draft from ctx["draft"] (str) or ctx.get("draft_result").body.
           - Get registry from ctx.get("fact_registry").
           - For each claim detected in the draft (dates, order numbers, quantities,
             statuses), check if a matching verified Fact exists in the registry.
           - Produce a ValidationResult (from schemas.py):
               verified=True only if unsupported_claims is empty AND contradictions is empty.
               unsupported_claims: list of detected claims with no fact backing.
               supported_claims_ratio: supported / (supported + unsupported).
           - Store ValidationResult at ctx["validation_result"].
           - If verified=False, also set ctx["pipeline_error"] = "validation_failed".

           Detection strategy (simple, no external NLP):
           - Dates: regex for DD/MM/YYYY, YYYY-MM-DD, "le \d+", "within \d+ days"
           - Status keywords: "livré", "expédié", "delivered", "shipped", "en stock",
             "in stock", "rupture", "out of stock"
           - Order numbers: any pattern matching the order id format already in ctx
           For each detected claim, look it up in the registry by key similarity.
           If not found, add to unsupported_claims.
           """
           ...

4. Update cs_ai/engine/agents/orchestrator.py:
   - Import FactBuilder and ValidatorAgent.
   - Add self._fact_builder = FactBuilder() and self._validator = ValidatorAgent()
     to __init__.
   - In run(), after triage: call fact_builder, store registry in ctx.
   - In run(), after QA: call validator, then check ctx["validation_result"].
   - If validation_result.verified is False: set decision to "block" unless
     ctx["route"] == "supervisor" (which already implies human review).
   - Inject ctx["verified_facts_context"] into the system prompt for the response
     agent (add it to ctx before calling ResponseAgent).

5. Update cs_ai/engine/agents/response.py:
   - If ctx.get("verified_facts_context") is not empty, include it in the system
     prompt under a "## Verified Facts" section. The model must only use facts
     listed in this section for specific claims.

6. Create tests/unit/test_fact_registry.py:
   - Test that an expired fact returns None from get().
   - Test that a verified fact is included in all_verified().
   - Test that to_context_string() formats correctly.

7. Create tests/unit/test_validator.py:
   - Test: draft containing a date claim with no matching Fact → unsupported_claims not empty.
   - Test: draft containing a status that matches a verified Fact → supported.
   - Test: ValidationResult.verified is False when unsupported_claims > 0.

Do NOT change nlp.py, channels.py, tickets.py, app.py, app_inbox.py, config files, or JSON data.
Install no new packages — use only stdlib (re, datetime) and existing dependencies.
```
