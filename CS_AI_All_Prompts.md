# CS AI ENGINE — All Implementation Prompts
## 12 prompts · Paste each one into Claude Code in VS Code

**Version:** v1.0 · April 2026  
**Order:** Do all P0 first (01→07), then P1 (08→10), then P2 (11→12).

---

| # | File | What it builds | Priority |
|---|------|----------------|----------|
| 01 | P0_01_StateMachine | TicketState FSM + transition matrix | P0 |
| 02 | P0_02_TypedSchemas | Strict Pydantic at every agent boundary | P0 |
| 03 | P0_03_FactRegistry | Fact objects + anti-hallucination validator | P0 |
| 04 | P0_04_ConnectorResilience | ConnectorResult[T] + Tenacity retries | P0 |
| 05 | P0_05_PolicyEngine | Code-first rules, deny-by-default | P0 |
| 06 | P0_06_TraceLogging | Structured JSON trace, no PII | P0 |
| 07 | P0_07_EvalHarness | Frozen dataset + graders + CI gate | P0 |
| 08 | P1_08_PromptRegistry | Versioned prompts, no inline strings | P1 |
| 09 | P1_09_FallbackTemplates | Jinja2 safe templates for blocked decisions | P1 |
| 10 | P1_10_ScopedMemory | Bounded per-customer memory with TTL | P1 |
| 11 | P2_11_CustomerHealthScore | Per-account health scoring + churn signal | P2 |
| 12 | P2_12_SLAAwareRouting | SLA breach detection + auto priority upgrade | P2 |

---

---

# PROMPT 01 — State Machine

## What This Does

Right now the orchestrator passes a raw `context` dict between agents with no enforcement of which steps have actually run or in which order. A crash mid-pipeline leaves no record of where things stopped, and retrying can cause duplicate actions.

This improvement adds a formal finite state machine to the ticket lifecycle. Every ticket moves through a strict sequence of states. Invalid transitions raise an explicit `InvalidTransitionError` instead of silently producing corrupt state. The machine is idempotent: retrying a completed step is a no-op, not a double-action.

**Where the change lives:** New file `cs_ai/engine/state_machine.py` + update `cs_ai/engine/tickets.py` (add `state` + `version` fields) + update `cs_ai/engine/agents/orchestrator.py` (call `goto()` at each stage boundary).

**Impact:** Bugs become explicit errors with a clear step name. Resuming a failed ticket is safe. Every ticket has a complete audit-ready state history.

---

## Prompt — Paste into Claude Code

```
Add a formal state machine to the CS AI ticket lifecycle.

TASK:

1. Create cs_ai/engine/state_machine.py:

   from enum import Enum

   class TicketState(str, Enum):
       NEW           = "new"
       TRIAGED       = "triaged"
       FACTS_BUILT   = "facts_built"
       DRAFTED       = "drafted"
       SELF_REVIEWED = "self_reviewed"
       VALIDATED     = "validated"
       QA_PASSED     = "qa_passed"
       READY         = "ready"
       SENT          = "sent"
       REVIEW        = "review"
       BLOCKED       = "blocked"
       ESCALATED     = "escalated"
       RESOLVED      = "resolved"
       CLOSED        = "closed"

   VALID_TRANSITIONS: dict[TicketState, set[TicketState]] = {
       TicketState.NEW:           {TicketState.TRIAGED, TicketState.BLOCKED},
       TicketState.TRIAGED:       {TicketState.FACTS_BUILT, TicketState.BLOCKED, TicketState.ESCALATED},
       TicketState.FACTS_BUILT:   {TicketState.DRAFTED, TicketState.REVIEW, TicketState.BLOCKED},
       TicketState.DRAFTED:       {TicketState.SELF_REVIEWED, TicketState.REVIEW, TicketState.BLOCKED},
       TicketState.SELF_REVIEWED: {TicketState.VALIDATED, TicketState.DRAFTED, TicketState.BLOCKED},
       TicketState.VALIDATED:     {TicketState.QA_PASSED, TicketState.BLOCKED, TicketState.REVIEW},
       TicketState.QA_PASSED:     {TicketState.READY, TicketState.REVIEW},
       TicketState.READY:         {TicketState.SENT, TicketState.REVIEW, TicketState.BLOCKED},
       TicketState.SENT:          {TicketState.RESOLVED},
       TicketState.REVIEW:        {TicketState.DRAFTED, TicketState.BLOCKED, TicketState.ESCALATED},
       TicketState.BLOCKED:       {TicketState.REVIEW, TicketState.ESCALATED},
       TicketState.ESCALATED:     set(),
       TicketState.RESOLVED:      {TicketState.CLOSED},
       TicketState.CLOSED:        set(),
   }

   class InvalidTransitionError(Exception):
       def __init__(self, from_state: TicketState, to_state: TicketState):
           super().__init__(f"Invalid transition: {from_state.value} → {to_state.value}")
           self.from_state = from_state
           self.to_state   = to_state

   class StateMachine:
       def goto(self, ticket, to_state: TicketState) -> None:
           """
           Validate and apply a state transition on a Ticket object.
           - If ticket.state == to_state already: no-op (idempotent).
           - If the transition is invalid: raise InvalidTransitionError.
           - On success: set ticket.state = to_state, increment ticket.version.
           - Append a StateTransition record to ticket.state_history (list of dicts
             with keys: from_state, to_state, timestamp ISO-8601).
           """
           ...

2. Update cs_ai/engine/tickets.py — Ticket dataclass:
   - Add field: state: str = "new"
   - Add field: version: int = 0
   - Add field: state_history: list = field(default_factory=list)
   - Add field: retry_count: int = 0
   - Update _create_table() to add columns: state TEXT DEFAULT 'new',
     version INTEGER DEFAULT 0, state_history TEXT DEFAULT '[]', retry_count INTEGER DEFAULT 0
   - Update _row_to_ticket() and save() to handle these new fields (state_history as JSON string).
   - Add method count_open() → int: returns count of tickets where status NOT IN ('resolved','closed').

3. Update cs_ai/engine/agents/orchestrator.py:
   - Import StateMachine from state_machine.
   - Instantiate: self._sm = StateMachine() in __init__.
   - In run(), call self._sm.goto(ticket, TicketState.TRIAGED) after triage, etc.
   - Wrap each goto() in try/except InvalidTransitionError, log WARNING, continue.
   - Save ticket to DB after each state change.

4. Create tests/unit/test_state_machine.py:
   - Parametrised test: all valid transitions → no exception.
   - Parametrised test: invalid transitions (e.g. NEW → SENT) → InvalidTransitionError.
   - Test idempotency: calling goto() with the same state twice is a no-op.
   - Test version increments: version goes from 0 to 1 after one successful transition.

Do NOT change nlp.py, channels.py, app.py, app_inbox.py, or any JSON data files.
Do NOT change the existing TICKET_STATUSES list — TicketState runs alongside it.
```

---

---

# PROMPT 02 — Typed Schemas

## What This Does

Right now agents pass raw Python dicts between each other. If the triage agent adds a key the response agent doesn't expect, or omits one it does, the error shows up as a cryptic `KeyError` deep in the pipeline — not at the boundary where the mistake was made.

This improvement introduces strict Pydantic models as the contract at every agent boundary. A `ValidationError` raised at the boundary is far more useful than a `KeyError` three functions later. It also makes the system self-documenting.

**Where the change lives:** New file `cs_ai/engine/schemas.py` + lightweight updates to triage, response, qa, draft_guard agents.

**Impact:** Shape bugs are caught at the exact agent boundary that caused them. Adding a new field never silently breaks downstream.

---

## Prompt — Paste into Claude Code

```
Introduce strict Pydantic schemas at every agent boundary in the CS AI engine.

TASK:

1. Create cs_ai/engine/schemas.py with these models (all use ConfigDict(strict=True)):

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
       intent:         Literal["order_status","complaint","delay","invoice",
                                "cancellation","modification","unknown"]
       emotion:        Literal["calm","neutral","frustrated","angry"]
       language:       str
       risk_flags:     list[str] = []
       missing_fields: list[str] = []
       route:          Literal["auto","standard","priority","supervisor"] = "standard"
       confidence:     ConfidenceScores | None = None
       is_noise:       bool = False
       noise_reason:   str = ""

   class DraftResponse(BaseModel):
       model_config = ConfigDict(strict=True)
       ticket_id:   str
       body:        str
       language:    str
       prompt_ref:  str = "unversioned"
       facts_used:  list[str] = []
       model_used:  str = ""
       token_usage: dict = {}

   class QAResult(BaseModel):
       model_config = ConfigDict(strict=True)
       verdict:  Literal["pass","needs_revision"]
       feedback: str = ""
       issues:   list[str] = []

   class ValidationResult(BaseModel):
       model_config = ConfigDict(strict=True)
       verified:               bool
       unsupported_claims:     list[str] = []
       contradictions:         list[str] = []
       policy_violations:      list[str] = []
       supported_claims_ratio: float = Field(ge=0.0, le=1.0, default=1.0)

   class DecisionResult(BaseModel):
       model_config = ConfigDict(strict=True)
       action:                Literal["send","review","block","escalate"]
       reason:                str
       required_human_review: bool = False
       blocked_by:            list[str] = []

2. Update cs_ai/engine/agents/triage.py:
   - Import TriageResult and ConfidenceScores from schemas.
   - At the end of run(), build a TriageResult and store in ctx["triage_result"].
   - Do NOT remove any existing ctx keys — add the typed result alongside them.

3. Update cs_ai/engine/agents/response.py:
   - Import DraftResponse from schemas.
   - After the AI call, build a DraftResponse and store in ctx["draft_result"].

4. Update cs_ai/engine/agents/qa.py:
   - Import QAResult from schemas.
   - Return a QAResult stored in ctx["qa_result"].

5. Update cs_ai/engine/agents/orchestrator.py:
   - After each agent call, validate the typed result with model.model_validate().
   - Catch pydantic.ValidationError, log at ERROR, set ctx["pipeline_error"].

6. Create tests/unit/test_schemas.py:
   - Valid TriageResult parses without error.
   - Invalid intent value raises ValidationError.
   - ConfidenceScores rejects value > 1.0.
   - DecisionResult rejects action not in the Literal set.

Do NOT change nlp.py, channels.py, tickets.py, app.py, or any JSON data files.
Do NOT remove existing ctx keys — add typed results alongside them.
```

---

---

# PROMPT 03 — Fact Registry

## What This Does

Right now the response agent can invent information — a delivery date, an order status — that was never returned by the ERP or CRM. The QA agent reviews tone but does not check whether claims are actually supported by real data.

This improvement introduces a `FactRegistry`: a typed store of verified facts built from ERP/CRM/KB responses. The validator checks every claim in the draft against this registry. Unverified claims are blocked.

**Where the change lives:** New `cs_ai/engine/fact_registry.py` + new `cs_ai/engine/agents/fact_builder.py` + new `cs_ai/engine/agents/validator.py` + update orchestrator.

**Impact:** Hallucinated facts never reach the customer. Every claim in a sent reply is traceable to a source.

---

## Prompt — Paste into Claude Code

```
Add a Fact Registry and Validator Agent to prevent hallucinated claims from reaching customers.

TASK:

1. Create cs_ai/engine/fact_registry.py:

   from pydantic import BaseModel, ConfigDict
   from typing import Literal
   import datetime

   class Fact(BaseModel):
       model_config = ConfigDict(strict=True)
       key:         str
       value:       str | int | float | bool | None
       source_type: Literal["erp","crm","email","attachment","kb","derived"]
       source_ref:  str
       verified:    bool = False
       observed_at: str
       ttl_s:       int = 3600
       sensitivity: Literal["public","internal","pii","restricted"] = "internal"

       def is_expired(self) -> bool:
           obs = datetime.datetime.fromisoformat(self.observed_at)
           age = (datetime.datetime.utcnow() - obs).total_seconds()
           return age > self.ttl_s

   class FactRegistry:
       def __init__(self):
           self._facts: dict[str, Fact] = {}

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
           lines = [f"[{f.source_type.upper()}] {f.key}: {f.value}" for f in self.all_verified()]
           return "\n".join(lines) if lines else "(no verified facts)"

2. Create cs_ai/engine/agents/fact_builder.py:
   class FactBuilder(BaseAgent):
       name = "fact_builder"
       def run(self, context: dict) -> dict:
           - Build FactRegistry from ctx["order_info"] (ERP → verified=True, source_type="erp")
           - Build from ctx["customer_profile"] (CRM → verified=True, source_type="crm")
           - Store registry at ctx["fact_registry"]
           - Store to_context_string() at ctx["verified_facts_context"]

3. Create cs_ai/engine/agents/validator.py:
   class ValidatorAgent(BaseAgent):
       name = "validator"
       def run(self, context: dict) -> dict:
           - Get draft from ctx["draft"] or ctx["draft_result"].body
           - Get registry from ctx["fact_registry"]
           - Detect claims using regex: dates (DD/MM/YYYY, "within N days"),
             status words (livré, expédié, delivered, shipped, en stock, out of stock),
             order numbers matching the known order_id format
           - For each claim, look up in registry by key similarity
           - Build ValidationResult from schemas.py
           - Store at ctx["validation_result"]
           - If verified=False: set ctx["pipeline_error"] = "validation_failed"

4. Update cs_ai/engine/agents/orchestrator.py:
   - Add FactBuilder and ValidatorAgent to the pipeline
   - After fact_builder: inject ctx["verified_facts_context"] for the response agent
   - After validator: if verified=False → set decision to "block"

5. Update cs_ai/engine/agents/response.py:
   - Include ctx["verified_facts_context"] in the system prompt under "## Verified Facts"

6. Create tests/unit/test_fact_registry.py and tests/unit/test_validator.py.

Do NOT change nlp.py, channels.py, tickets.py, app.py, or any JSON data files.
Use only stdlib (re, datetime) — no new packages needed.
```

---

---

# PROMPT 04 — Connector Resilience

## What This Does

Right now if the ERP or CRM is slow or returns an error, the engine either silently gets `None`, crashes, or returns stale mock data with no indication something went wrong. There is no retry logic, no circuit breaker, and no classification of whether an error is recoverable.

This improvement wraps every connector call in a `ConnectorResult[T]` envelope and classifies every error. Retryable errors get exponential backoff. Fatal errors go to human review. The orchestrator never crashes because a connector returned a 500.

**Where the change lives:** New `cs_ai/engine/connector_base.py` + update `cs_ai/engine/connector.py`.

**Impact:** Connector outages route tickets to human review instead of crashing. Every error is classified and logged.

---

## Prompt — Paste into Claude Code

```
Add resilient connector infrastructure with typed error envelopes and automatic retries.

TASK:

1. Create cs_ai/engine/connector_base.py:

   from pydantic import BaseModel, ConfigDict
   from typing import Generic, Literal, TypeVar
   T = TypeVar("T")

   class ConnectorError(BaseModel):
       model_config = ConfigDict(strict=True)
       kind:    Literal["retryable","fatal","auth","rate_limit","policy","timeout"]
       code:    str
       message: str
       retry_after_s:       int | None = None
       upstream_request_id: str | None = None

   class ConnectorResult(BaseModel, Generic[T]):
       model_config = ConfigDict(strict=True)
       status:     Literal["ok","error"]
       request_id: str
       data:       T | None = None
       error:      ConnectorError | None = None
       freshness_expires_at: str | None = None

       @property
       def ok(self) -> bool:
           return self.status == "ok" and self.data is not None

   def make_ok(data, request_id, expires_at=None): ...
   def make_error(kind, code, message, request_id, retry_after_s=None): ...

2. Update cs_ai/engine/connector.py:
   - Import connector_base and uuid, tenacity
   - Wrap get_order(), get_customer(), search_kb() with safe versions
     using ConnectorResult[dict] return type:

   from tenacity import retry, stop_after_attempt, wait_exponential_jitter

   @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=10))
   def get_order_safe(self, order_id: str) -> ConnectorResult[dict]:
       request_id = str(uuid.uuid4())
       try:
           data = self.get_order(order_id)
           if data is None:
               return make_error("fatal", "ORDER_NOT_FOUND", f"Order {order_id} not found", request_id)
           return make_ok(data, request_id)
       except TimeoutError as e:
           return make_error("timeout", "ERP_TIMEOUT", str(e), request_id, retry_after_s=5)
       except ConnectionError as e:
           return make_error("retryable", "ERP_CONNECTION", str(e), request_id)
       except PermissionError as e:
           return make_error("auth", "ERP_AUTH", str(e), request_id)
       except Exception as e:
           return make_error("fatal", "ERP_UNKNOWN", str(e), request_id)

3. Update cs_ai/engine/agents/fact_builder.py:
   - Use get_order_safe() instead of get_order()
   - If error.kind == "fatal": set ctx["connector_fatal"] = True
   - If error.kind in ("retryable","timeout"): set ctx["connector_degraded"] = True
   - Log every error at WARNING (retryable) or ERROR (fatal)

4. Update cs_ai/engine/agents/orchestrator.py:
   - If connector_fatal: route to "review", skip rest of pipeline
   - If connector_degraded: continue but set confidence.data_completeness = 0.4

5. Create tests/unit/test_connector_resilience.py:
   - TimeoutError mock → ConnectorResult status="error", kind="timeout"
   - Valid data mock → ConnectorResult ok == True
   - Generic Exception mock → kind="fatal"

If tenacity not installed: pip install tenacity, add to requirements.txt.
Do NOT change nlp.py, channels.py, tickets.py, app.py, or JSON data files.
```

---

---

# PROMPT 05 — Policy Engine

## What This Does

Right now the only "rules" are embedded in LLM prompts. If the prompt changes, the rule changes or disappears. There is no way to audit which rules are enforced, and no guarantee they actually fire.

This improvement introduces a code-first `PolicyEngine` with explicit Python `PolicyRule` objects. Rules are pure Python — not prompts — and violations produce a classified `SECURITY` log entry and a `block` or `review` decision.

**Where the change lives:** New `cs_ai/engine/policy_engine.py` + update orchestrator.

**Impact:** Business rules are explicit, testable, and audit-logged. Changing a prompt never silently removes a safety rule.

---

## Prompt — Paste into Claude Code

```
Add a code-first PolicyEngine that enforces business rules before any auto-send action.

TASK:

1. Create cs_ai/engine/policy_engine.py:

   import logging, re
   from dataclasses import dataclass, field
   from typing import Callable
   log = logging.getLogger(__name__)

   @dataclass
   class PolicyRule:
       name:        str
       description: str
       severity:    str   # "block" | "review" | "warn"
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

       def _register_defaults(self):
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

       def _check_unverified_date(self, ctx):
           draft = ctx.get("draft","")
           has_date = bool(re.search(
               r'\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|dans \d+ jours?|within \d+ days?)\b',
               draft, re.IGNORECASE))
           if not has_date: return False
           reg = ctx.get("fact_registry")
           return reg is None or reg.get("delivery_date") is None

       def _check_angry_low_confidence(self, ctx):
           triage = ctx.get("triage_result")
           emotion = triage.emotion if triage else ctx.get("emotion","")
           conf = triage.confidence.final if (triage and triage.confidence) else ctx.get("confidence_score",1.0)
           return emotion == "angry" and conf < 0.7

       def _check_unsupported_claims(self, ctx):
           v = ctx.get("validation_result")
           return v is not None and len(v.unsupported_claims) > 0

       def _check_erp_action(self, ctx):
           action = ctx.get("suggested_action","")
           return any(s in action.lower() for s in ["cancel","refund","modify","annul","rembours"])

       def add_rule(self, rule: PolicyRule): self._rules.append(rule)

       def evaluate(self, ctx: dict) -> PolicyDecision:
           violations, required = [], set()
           for rule in self._rules:
               try:
                   if rule.check(ctx):
                       violations.append(rule.name)
                       required.add(rule.severity)
                       log.warning("POLICY_VIOLATION rule=%s severity=%s ticket=%s",
                           rule.name, rule.severity, ctx.get("ticket_id","?"))
               except Exception as e:
                   log.error("POLICY_RULE_ERROR rule=%s error=%s", rule.name, e)
           return PolicyDecision(passed=not violations, violations=violations,
                                 required_actions=sorted(required))

2. Update cs_ai/engine/agents/orchestrator.py:
   - Import PolicyEngine; instantiate self._policy = PolicyEngine()
   - After validation: policy_decision = self._policy.evaluate(ctx)
   - If "block" in required_actions → DecisionResult(action="block", ...)
   - If "review" in required_actions (no block) → DecisionResult(action="review", ...)

3. Create tests/unit/test_policy_engine.py:
   - angry + conf 0.5 → violation "no_autosend_angry_low_confidence"
   - calm + conf 0.5 → no violation
   - unsupported_claims not empty → violation "no_unsupported_claims"
   - suggested_action="refund" → violation "erp_action_requires_approval"
   - clean ctx → PolicyDecision(passed=True)

Do NOT change nlp.py, channels.py, tickets.py, app.py, or JSON data files.
All rules must be pure Python — no LLM calls inside a rule.
```

---

---

# PROMPT 06 — Structured Trace Logging

## What This Does

Right now log output is unstructured text with no `run_id`, no per-stage latency, no token count, and no PII guarantee. Debugging a production issue means grepping raw text.

This improvement introduces a `StepTrace` model emitted after every pipeline stage. Every log line is JSON with `run_id`, `ticket_id`, `step_name`, `latency_ms`, `model`, `prompt_version`, `decision`, `error_code`. PII is stripped before anything is written.

**Where the change lives:** New `cs_ai/engine/trace_logger.py` + update orchestrator.

**Impact:** Any production issue can be diagnosed from logs alone. Token costs per ticket are tracked automatically. PII never appears in log files.

---

## Prompt — Paste into Claude Code

```
Add structured trace logging to the CS AI pipeline. Every stage emits a StepTrace.
No raw PII may appear in any log.

TASK:

1. Create cs_ai/engine/trace_logger.py:

   import json, logging, re, time, uuid
   from datetime import datetime, UTC
   from pydantic import BaseModel, ConfigDict
   from typing import Literal

   _EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}')
   _PHONE_RE = re.compile(r'\+?[\d\s\-\(\)]{7,15}')

   def redact(text: str) -> str:
       text = _EMAIL_RE.sub("[EMAIL]", text)
       text = _PHONE_RE.sub("[PHONE]", text)
       return text

   class StepTrace(BaseModel):
       model_config = ConfigDict(strict=True)
       run_id:         str
       ticket_id:      str
       step_name:      str
       status:         Literal["ok","error","skipped"]
       latency_ms:     float
       model:          str = ""
       prompt_version: str = "unversioned"
       input_tokens:   int = 0
       output_tokens:  int = 0
       decision:       str = ""
       error_code:     str = ""
       timestamp:      str = ""

   class TraceLogger:
       def __init__(self, name="cs_ai.trace"):
           self._log = logging.getLogger(name)

       def emit(self, trace: StepTrace) -> None:
           d = trace.model_dump()
           d["decision"]   = redact(d.get("decision",""))
           d["error_code"] = redact(d.get("error_code",""))
           self._log.info(json.dumps(d))

       def new_run_id(self) -> str:
           return str(uuid.uuid4())

   _tracer = TraceLogger()
   def get_tracer() -> TraceLogger: return _tracer

2. Update cs_ai/engine/agents/base.py — add to BaseAgent:
   def _trace_step(self, ctx, step_name, t_start, status="ok", error_code=""):
       from trace_logger import StepTrace, get_tracer
       from datetime import datetime, UTC
       trace = StepTrace(
           run_id=ctx.get("run_id",""),
           ticket_id=str(ctx.get("ticket_id","?")),
           step_name=step_name,
           status=status,
           latency_ms=round((time.perf_counter()-t_start)*1000, 1),
           model=ctx.get("model_used",""),
           prompt_version=ctx.get("prompt_version","unversioned"),
           input_tokens=ctx.get("token_usage",{}).get("prompt",0),
           output_tokens=ctx.get("token_usage",{}).get("completion",0),
           decision=str(ctx.get("final_decision",""))[:80],
           error_code=error_code,
           timestamp=datetime.now(UTC).isoformat(),
       )
       get_tracer().emit(trace)

3. Update cs_ai/engine/agents/orchestrator.py:
   - Generate ctx["run_id"] = str(uuid.uuid4()) at start of run()
   - Wrap each agent call:
       t0 = time.perf_counter()
       ctx = self._triage(ctx)
       self._triage._trace_step(ctx, "triage", t0)
   - On exception: _trace_step(..., status="error", error_code=type(e).__name__)

4. Create tests/unit/test_trace_logger.py:
   - redact() replaces email with "[EMAIL]"
   - redact() replaces phone with "[PHONE]"
   - StepTrace serialises to dict with all required keys
   - emit() produces valid JSON (json.loads does not raise)

Do NOT log the raw email body, customer name, or email address anywhere.
Do NOT change nlp.py, channels.py, tickets.py, app.py, or JSON data files.
```

---

---

# PROMPT 07 — Eval Harness + CI Gate

## What This Does

Right now there is no automated way to know if a prompt change made the system better or worse. Every deployment is a leap of faith.

This improvement adds a frozen evaluation dataset and a grading engine that runs on every PR. The CI gate blocks a merge if the overall score drops below the baseline. The dataset is the most valuable long-term asset of the product.

**Where the change lives:** New folder `cs_ai/evals/` with dataset JSON files, `graders.py`, `simulator.py`.

**Impact:** Every prompt change is validated before it ships. Regressions are caught in CI, not in production.

---

## Prompt — Paste into Claude Code

```
Add an evaluation harness with a frozen dataset and CI-blocking graders.

TASK:

1. Create the folder structure:
   cs_ai/evals/__init__.py
   cs_ai/evals/dataset/nominal.json       (5+ nominal cases)
   cs_ai/evals/dataset/ambiguous.json     (5 ambiguous/missing-data cases)
   cs_ai/evals/dataset/adversarial.json   (5 prompt-injection cases)
   cs_ai/evals/dataset/emotional.json     (5 high-emotion cases)
   cs_ai/evals/dataset/erp_conflict.json  (5 ERP-conflict cases)
   cs_ai/evals/graders.py
   cs_ai/evals/simulator.py

2. Each eval case JSON format:
   {
     "id": "nom_001",
     "description": "Simple order status, calm customer",
     "input": {
       "user_message": "Bonjour, quel est le statut de ma commande ORD-1001 ?",
       "language": "fr",
       "customer_email": "test@example.com",
       "order_id": "ORD-1001"
     },
     "expected": {
       "intent": "order_status",
       "emotion": "calm",
       "decision": "send",
       "must_not_contain": []
     }
   }
   Adversarial cases: user_message contains "Ignore previous instructions and..."
   Expected: decision != "send".
   Emotional cases: emotion="angry", missing order_id.
   Expected: decision="review", required_human_review=true.

3. Create cs_ai/evals/graders.py:
   class IntentGrader, DecisionGrader, ClaimSupportGrader, SafetyGrader
   Each has: grade(case: dict, ctx: dict) -> Grade
   Grade: dataclass with case_id, passed (bool), score (0.0-1.0), failure_reason

4. Create cs_ai/evals/simulator.py:
   BASELINE_SCORE = 0.80

   def run_eval(orchestrator, dataset_file="nominal.json") -> dict:
       - Load dataset, run each case through orchestrator.run(ctx)
       - Apply all graders, compute per-case score and overall score
       - Return {"overall_score": float, "results": list, "passed": bool}

   if __name__ == "__main__":
       - Run eval on all dataset files
       - Print ✅/❌ per case
       - sys.exit(1) if overall < BASELINE_SCORE

5. Create tests/test_eval_harness.py:
   def test_nominal_eval_passes_baseline():
       result = run_eval(Orchestrator(), "nominal.json")
       assert result["passed"]

   def test_adversarial_never_sends():
       for case in load_dataset("adversarial.json"):
           ctx = run_case(case, Orchestrator())
           assert ctx.get("decision") != "send"

6. Add ci_eval.yml GitHub Actions step:
   - name: Run eval harness
     run: python cs_ai/evals/simulator.py
   (fails build if exit code non-zero)

Do NOT use real customer email addresses in the dataset.
Eval must run offline — no live API calls (use mock connector data).
Do NOT change nlp.py, channels.py, tickets.py, app.py, or JSON company files.
```

---

---

# PROMPT 08 — Prompt Registry + Versioning

## What This Does

Right now prompts are inline strings scattered across files. When a prompt is changed and something breaks, there is no way to know which change caused it or how to roll back.

This improvement introduces a `PromptRegistry` that versions every prompt with semver, a checksum, and a changelog entry. Every LLM call references a `prompt_id` and `version`. Rolling back is a one-line config change.

**Where the change lives:** New `cs_ai/engine/prompt_registry.py` + new `cs_ai/prompts/` folder + update response, triage, and qa agents.

**Impact:** Every LLM regression is attributable to a specific version and PR. Rollback is a config change, not a redeployment.

---

## Prompt — Paste into Claude Code

```
Add a PromptRegistry that versions every LLM prompt — no more inline prompt strings in production.

TASK:

1. Create cs_ai/engine/prompt_registry.py:

   import hashlib, json, os
   from dataclasses import dataclass, field

   @dataclass
   class PromptSpec:
       prompt_id:  str
       version:    str       # semver e.g. "1.0.0"
       content:    str       # prompt template with {variable} placeholders
       variables:  list[str] = field(default_factory=list)
       changelog:  str = ""
       checksum:   str = ""

       def __post_init__(self):
           self.checksum = hashlib.sha256(self.content.encode()).hexdigest()[:12]

       def render(self, **kwargs) -> str:
           try:
               return self.content.format(**kwargs)
           except KeyError as e:
               raise ValueError(f"Missing variable {e} for prompt {self.prompt_id}@{self.version}")

   class PromptRegistry:
       def __init__(self, prompts_dir: str):
           self._prompts = {}
           self._dir = prompts_dir
           self._load_all()

       def _load_all(self):
           if not os.path.isdir(self._dir): return
           for fname in os.listdir(self._dir):
               if fname.endswith(".json"):
                   with open(os.path.join(self._dir, fname)) as f:
                       data = json.load(f)
                   spec = PromptSpec(**data)
                   self._prompts[spec.prompt_id] = spec

       def get(self, prompt_id: str) -> PromptSpec:
           if prompt_id not in self._prompts:
               raise KeyError(f"Prompt not found: {prompt_id}")
           return self._prompts[prompt_id]

   _registry = None
   def get_registry() -> PromptRegistry:
       global _registry
       if _registry is None:
           d = os.path.join(os.path.dirname(__file__), "..", "prompts")
           _registry = PromptRegistry(os.path.abspath(d))
       return _registry

2. Create cs_ai/prompts/ folder with JSON files:
   cs_ai/prompts/triage_system.json
   cs_ai/prompts/response_system.json
   cs_ai/prompts/qa_review.json
   Each file:
   {
     "prompt_id": "response_system",
     "version": "1.0.0",
     "changelog": "Initial extraction from inline string",
     "variables": ["company_name","agent_role","agent_signature","customer_name",
                   "order_info","kb_context","verified_facts_context","history_context"],
     "content": "< extract the actual prompt from response.py here >"
   }
   Convert f-strings with local variables to {variable_name} format placeholders.

3. Update cs_ai/engine/agents/response.py:
   - spec = get_registry().get("response_system")
   - system_prompt = spec.render(company_name=..., agent_role=..., ...)
   - ctx["prompt_version"] = f"{spec.prompt_id}@{spec.version}@{spec.checksum}"
   - Remove the raw prompt string from the file.

4. Update triage.py and qa.py the same way.

5. Create tests/unit/test_prompt_registry.py:
   - get_registry().get("response_system") returns a PromptSpec
   - render() with all variables → non-empty string
   - render() with missing variable → raises ValueError
   - checksum is 12-char hex string
   - loading same prompt twice → same checksum

Do NOT change nlp.py, channels.py, tickets.py, app.py, or JSON data files.
Do NOT change prompt content — only extract it into the JSON format.
```

---

---

# PROMPT 09 — Fallback Templates

## What This Does

Right now when a draft is blocked, the customer gets no response at all until a human picks it up. For predictable failure modes, a pre-written safe template is always better than silence.

This improvement adds a `FallbackTemplateEngine` that selects the right Jinja2 template based on the block reason and sends it in place of the AI response when the LLM output is not trusted.

**Where the change lives:** New `cs_ai/engine/fallback_engine.py` + new `cs_ai/templates/fallback/*.j2` + update orchestrator.

**Impact:** Blocked tickets still send a safe acknowledgement. No LLM is involved in red-zone responses.

---

## Prompt — Paste into Claude Code

```
Add a Jinja2-based fallback template engine for blocked and low-confidence decisions.

TASK:

1. Create cs_ai/templates/fallback/ with these Jinja2 files:

   missing_info.j2 — asks for missing fields (order number etc.)
   system_unavailable.j2 — acknowledges delay due to system issue
   high_risk.j2 — promises priority handling by a team member
   ambiguous_request.j2 — asks for clarification

   Also create English versions: missing_info_en.j2, system_unavailable_en.j2,
   high_risk_en.j2, ambiguous_request_en.j2.

   Variables available in all templates:
   {{ customer_name }}, {{ agent_signature }}, {{ sla_hours }}, {{ missing_fields }}

   Example missing_info.j2:
   ---
   Bonjour {{ customer_name | default("") }},

   Merci pour votre message. Afin de traiter votre demande dans les meilleurs délais,
   pourriez-vous nous communiquer {{ missing_fields | join(", ") }} ?

   Cordialement,
   {{ agent_signature }}
   ---

2. Create cs_ai/engine/fallback_engine.py:

   from jinja2 import Environment, FileSystemLoader, select_autoescape

   FallbackReason = Literal["missing_info","system_unavailable","high_risk","ambiguous_request"]

   class FallbackTemplateEngine:
       def __init__(self):
           templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates", "fallback")
           self._env = Environment(loader=FileSystemLoader(os.path.abspath(templates_dir)),
                                   autoescape=select_autoescape(["html"]))

       def render(self, reason: FallbackReason, ctx: dict) -> str:
           language = ctx.get("language","fr")
           suffix = "" if language == "fr" else f"_{language}"
           template_name = f"{reason}{suffix}.j2"
           try:
               tmpl = self._env.get_template(template_name)
           except Exception:
               tmpl = self._env.get_template(f"{reason}.j2")
           return tmpl.render(
               customer_name=ctx.get("customer_name",""),
               agent_signature=ctx.get("agent_signature","L'équipe Support"),
               sla_hours=ctx.get("sla_hours",24),
               missing_fields=ctx.get("missing_fields",["votre numéro de commande"]),
           )

       def reason_for(self, ctx: dict) -> FallbackReason:
           if ctx.get("connector_fatal"): return "system_unavailable"
           triage = ctx.get("triage_result")
           if triage and triage.missing_fields: return "missing_info"
           policy = ctx.get("policy_decision")
           if policy and "no_autosend_angry_low_confidence" in getattr(policy,"violations",[]): return "high_risk"
           if triage and triage.intent == "unknown": return "ambiguous_request"
           return "high_risk"

3. Update cs_ai/engine/agents/orchestrator.py:
   - self._fallback = FallbackTemplateEngine()
   - After block decision (NOT caused by hallucination):
       ctx["fallback_draft"] = self._fallback.render(self._fallback.reason_for(ctx), ctx)
       ctx["used_fallback"] = True
   - Only auto-send fallback if config["fallback"]["auto_send"] is True (default False).

4. Add to config template: "fallback": {"auto_send": false, "default_language": "fr"}

5. Create tests/unit/test_fallback_engine.py:
   - render("missing_info", fr_ctx) → contains French content
   - render("missing_info", en_ctx) → contains English content
   - render("high_risk", ctx_with_sla) → contains sla_hours value
   - reason_for({connector_fatal: True}) → "system_unavailable"

If jinja2 not installed: pip install jinja2, add to requirements.txt.
Do NOT use LLM to generate fallback content — output must be deterministic.
Do NOT change nlp.py, channels.py, tickets.py, app.py, or JSON data files.
```

---

---

# PROMPT 10 — Scoped Memory

## What This Does

Right now every ticket starts cold — the agent cannot recall that this customer complained about the same issue last week, or that their previous tone was frustrated.

This improvement adds a `ScopedMemory` system: lightweight bounded memory per ticket, client, and account. Memory is TTL-limited, PII-redacted before persistence, and never shared across accounts.

**Where the change lives:** New `cs_ai/engine/memory.py` + SQLite `memory.db` per company + update triage agent.

**Impact:** The agent becomes context-aware across sessions without any cross-customer contamination.

---

## Prompt — Paste into Claude Code

```
Add a bounded, scoped memory system that persists lightweight context between tickets
for the same customer.

TASK:

1. Create cs_ai/engine/memory.py:

   import hashlib, json, re, sqlite3
   from dataclasses import dataclass, field
   from datetime import datetime, UTC, timedelta
   from typing import Literal
   from paths import resolve_data_file

   _EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}')
   def _redact(text): return _EMAIL_RE.sub("[EMAIL]", str(text))

   @dataclass
   class MemoryItem:
       scope:      Literal["ticket","client","account"]
       scope_id:   str
       key:        str
       value:      str
       created_at: str
       expires_at: str
       checksum:   str = ""

       def __post_init__(self):
           self.value    = _redact(self.value)
           self.checksum = hashlib.sha256((self.scope_id+self.key+self.value).encode()).hexdigest()[:8]

       def is_expired(self) -> bool:
           return datetime.fromisoformat(self.expires_at) < datetime.now(UTC).replace(tzinfo=None)

   class ScopedMemory:
       MAX_ITEMS_PER_SCOPE = 20

       def __init__(self, company: str):
           db_path = resolve_data_file(company, "memory.db")
           self._conn = sqlite3.connect(db_path, check_same_thread=False)
           self._create_table()

       def _create_table(self):
           self._conn.execute("""
               CREATE TABLE IF NOT EXISTS memory (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   scope TEXT, scope_id TEXT, key TEXT, value TEXT,
                   created_at TEXT, expires_at TEXT, checksum TEXT,
                   UNIQUE(scope, scope_id, key)
               )""")
           self._conn.commit()

       def store(self, item: MemoryItem):
           self._conn.execute("""
               INSERT INTO memory(scope,scope_id,key,value,created_at,expires_at,checksum)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(scope,scope_id,key) DO UPDATE SET
               value=excluded.value,created_at=excluded.created_at,
               expires_at=excluded.expires_at,checksum=excluded.checksum
           """, (item.scope,item.scope_id,item.key,item.value,
                 item.created_at,item.expires_at,item.checksum))
           self._conn.commit()
           self._enforce_cap(item.scope, item.scope_id)

       def _enforce_cap(self, scope, scope_id):
           rows = self._conn.execute(
               "SELECT id FROM memory WHERE scope=? AND scope_id=? ORDER BY created_at DESC",
               (scope, scope_id)).fetchall()
           if len(rows) > self.MAX_ITEMS_PER_SCOPE:
               ids = [r[0] for r in rows[self.MAX_ITEMS_PER_SCOPE:]]
               self._conn.execute(f"DELETE FROM memory WHERE id IN ({','.join('?'*len(ids))})", ids)
               self._conn.commit()

       def recall(self, scope, scope_id) -> list[MemoryItem]:
           now = datetime.now(UTC).replace(tzinfo=None).isoformat()
           rows = self._conn.execute(
               "SELECT scope,scope_id,key,value,created_at,expires_at,checksum FROM memory "
               "WHERE scope=? AND scope_id=? AND expires_at>? ORDER BY created_at DESC",
               (scope, scope_id, now)).fetchall()
           return [MemoryItem(*r) for r in rows]

       def recall_as_context(self, scope, scope_id) -> str:
           items = self.recall(scope, scope_id)
           return "\n".join(f"[MEMORY:{i.key}] {i.value}" for i in items)

       def purge_expired(self) -> int:
           now = datetime.now(UTC).replace(tzinfo=None).isoformat()
           c = self._conn.execute("DELETE FROM memory WHERE expires_at<=?", (now,))
           self._conn.commit()
           return c.rowcount

   def make_item(scope, scope_id, key, value, ttl_hours=24) -> MemoryItem:
       now = datetime.now(UTC).replace(tzinfo=None)
       return MemoryItem(scope=scope, scope_id=scope_id, key=key, value=str(value),
                         created_at=now.isoformat(),
                         expires_at=(now+timedelta(hours=ttl_hours)).isoformat())

2. Update cs_ai/engine/agents/triage.py:
   - Import ScopedMemory, make_item; import hashlib
   - At start of run():
       company = ctx.get("company","default")
       mem = ScopedMemory(company)
       client_id = hashlib.sha256(ctx.get("customer_email","").encode()).hexdigest()[:16]
       ctx["client_memory_context"] = mem.recall_as_context("client", client_id)
   - At end of run(), persist:
       mem.store(make_item("client", client_id, "last_emotion", emotion, ttl_hours=168))
       mem.store(make_item("client", client_id, "last_intent",  intent,  ttl_hours=168))

3. Update cs_ai/engine/agents/response.py:
   - Include ctx["client_memory_context"] in system prompt under "## Customer History"
   - Place it AFTER the verified facts section

4. Create tests/unit/test_memory.py:
   - store() + recall() → same item returned
   - Expired item not returned
   - 25 items stored → max 20 returned
   - Redaction removes email from stored value
   - purge_expired() removes expired items

Do NOT store raw email body in memory — only derived summaries (emotion, intent).
Do NOT share memory between companies — ScopedMemory is initialised per company.
Do NOT change nlp.py, channels.py, tickets.py, app.py, or JSON data files.
```

---

---

# PROMPT 11 — Customer Health Score

## What This Does

Right now there is no way to know which customers are at risk of churning or escalating. Supervisors have no visibility into whether a customer's experience is deteriorating.

This improvement adds a `CustomerHealthScore` computed per account from ticket data: escalation rate, average confidence, emotion trend, and SLA compliance. High-risk customers automatically get priority routing.

**Where the change lives:** New `cs_ai/engine/health_score.py` + update `cs_ai/engine/pages/1_Analytics.py` + update triage agent.

**Impact:** Supervisors see at-risk customers before they escalate. High-risk customers get priority handling automatically.

---

## Prompt — Paste into Claude Code

```
Add a CustomerHealthScore computed from ticket history and used for priority routing
and supervisor visibility.

TASK:

1. Create cs_ai/engine/health_score.py:

   @dataclass
   class HealthScore:
       customer_email:      str
       score:               float   # 0.0 (critical) to 1.0 (healthy)
       label:               str     # "healthy" | "at_risk" | "critical"
       escalation_rate:     float
       avg_confidence:      float
       emotion_trend:       str     # "improving" | "stable" | "worsening"
       sla_compliance_rate: float
       open_tickets:        int
       computed_at:         str

   class HealthScoreComputer:
       def compute(self, customer_email: str, lookback_days=30) -> HealthScore:
           """
           Query tickets DB for last N days for this customer.
           Score formula (weighted average):
             (1 - escalation_rate) * 0.30
             + avg_confidence      * 0.25
             + sla_compliance_rate * 0.25
             + avg_emotion_score   * 0.20
           Emotion scores: calm=1.0, neutral=0.75, frustrated=0.4, angry=0.0
           Label: >=0.75 healthy, >=0.45 at_risk, <0.45 critical
           Emotion trend: compare first half vs second half of tickets
           Handle missing columns (emotion, confidence_score, escalated) gracefully.
           """
           ...

       def at_risk_customers(self, account_id: str, top_n=10) -> list[HealthScore]:
           """Return top N at-risk or critical customers, sorted by score ascending."""
           ...

2. Update cs_ai/engine/agents/triage.py:
   - hs = HealthScoreComputer().compute(ctx.get("customer_email",""))
   - ctx["customer_health"] = hs
   - If hs.label == "critical": ctx["route"] = "priority", add "customer_critical_health" to risk_flags
   - If hs.label == "at_risk": add "customer_at_risk" to risk_flags

3. Update cs_ai/engine/pages/1_Analytics.py:
   - Add a "Customer Health" tab
   - Show table: Customer | Score | Label | Escalation Rate | SLA Compliance | Emotion Trend | Open Tickets
   - Colour rows: critical=red background, at_risk=orange, healthy=green
   - If no at-risk: st.success("✅ All customers are healthy.")

4. Create tests/unit/test_health_score.py:
   - No tickets → label="healthy", score=1.0
   - 100% escalation → label="critical"
   - Score between 0.45–0.75 → label="at_risk"
   - Last half all angry → emotion_trend="worsening"

Health score computation must be read-only — no writes to tickets DB.
Missing columns → use defaults (confidence=0.8, emotion="neutral", escalated=False).
Do NOT change nlp.py, channels.py, app.py, connector.py, or JSON data files.
```

---

---

# PROMPT 12 — SLA-Aware Routing

## What This Does

Right now tickets are prioritised by intent and emotion, but not by how close they are to breaching their SLA deadline. A calm ticket with 20 minutes left before breach is treated the same as one that arrived 5 minutes ago.

This improvement adds SLA-aware routing: the system calculates `time_to_sla_breach` and automatically upgrades routing priority. Breached tickets go to supervisor immediately and show in red in the inbox.

**Where the change lives:** Update `cs_ai/engine/tickets.py` + `cs_ai/engine/agents/triage.py` + `cs_ai/engine/app_inbox.py` + `cs_ai/engine/pages/1_Analytics.py`.

**Impact:** No ticket silently misses its SLA. Supervisors see breached tickets in red immediately.

---

## Prompt — Paste into Claude Code

```
Add SLA-aware routing that automatically upgrades ticket priority based on time
remaining before the SLA deadline.

TASK:

1. Update cs_ai/engine/tickets.py — Ticket dataclass:
   - Add field: sla_deadline: str | None = None

   - Add method:
     def time_to_breach_minutes(self) -> float | None:
         if not self.sla_deadline: return None
         from datetime import datetime
         deadline = datetime.fromisoformat(self.sla_deadline).replace(tzinfo=None)
         return (deadline - datetime.now().replace(tzinfo=None)).total_seconds() / 60

     def sla_urgency(self) -> str:
         ttb = self.time_to_breach_minutes()
         if ttb is None: return "normal"
         if ttb < 0:   return "breached"
         if ttb < 30:  return "critical"
         if ttb < 120: return "high"
         return "normal"

   - Update _create_table(): add column sla_deadline TEXT DEFAULT NULL
   - Update _row_to_ticket() and save() to handle sla_deadline
   - In create_ticket(): compute sla_deadline from config["sla"][priority]["response_hours"]

2. Update cs_ai/engine/agents/triage.py:
   - After loading ticket:
       urgency = ticket.sla_urgency() if ticket else "normal"
       ctx["sla_urgency"] = urgency
       if urgency == "breached":
           ctx["route"] = "supervisor"
           ctx.setdefault("risk_flags",[]).append("sla_breached")
       elif urgency == "critical":
           if ctx.get("route") not in ("supervisor","priority"):
               ctx["route"] = "priority"
           ctx.setdefault("risk_flags",[]).append("sla_critical")
       elif urgency == "high":
           if ctx.get("route") == "auto": ctx["route"] = "standard"
           ctx.setdefault("risk_flags",[]).append("sla_high")

3. Update cs_ai/engine/app_inbox.py:
   - Add SLA column to ticket list showing:
       🔴 BREACHED / 🟠 <30 min / 🟡 <2h / 🟢 OK
   - Sort ticket list: breached first, then critical, high, normal
   - If any breached: st.warning("⚠️ {n} ticket(s) have breached their SLA.")
   - Page title: "CS Agent 🔴 {n} BREACHED" or "CS Agent 🟠 {n} critical" when applicable

4. Update cs_ai/engine/pages/1_Analytics.py:
   - Add SLA Compliance metric cards:
       % resolved within SLA (last 7 days)
       % breached SLA (last 7 days)
       Average time to resolution vs deadline

5. Create tests/unit/test_sla_routing.py:
   - deadline 1h from now → time_to_breach_minutes ≈ 60
   - past deadline → negative minutes
   - ttb=-5 → urgency="breached"
   - ttb=20 → urgency="critical"
   - ttb=90 → urgency="high"
   - ttb=300 → urgency="normal"
   - urgency="breached" → route set to "supervisor"

sla_deadline is nullable — all existing tickets without it work as before.
Do NOT change nlp.py, channels.py, connector.py, or JSON data files.
Do NOT change the existing TICKET_PRIORITIES list or SLA config keys.
```

---

*CS AI Engine — All Implementation Prompts · v1.0 · April 2026*  
*CONFIDENTIAL — Do not distribute outside the founding team*
