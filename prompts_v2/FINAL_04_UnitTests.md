Create the unit test suite at `tests/unit/`. Tests must be fast (no real API calls),
isolated (no live DB or connector), and run with `pytest tests/unit/ -v`.

---

## Step 1 — Create directory structure

```
tests/__init__.py
tests/unit/__init__.py
tests/unit/conftest.py
tests/unit/test_state_machine.py
tests/unit/test_schemas.py
tests/unit/test_fact_registry.py
tests/unit/test_connector_resilience.py
tests/unit/test_policy_engine.py
tests/unit/test_trace_logger.py
tests/unit/test_memory.py
tests/unit/test_health_score.py
tests/unit/test_sla_routing.py
```

---

## Step 2 — conftest.py

```python
import sys, os, pytest
_ENGINE = os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine")
sys.path.insert(0, _ENGINE)
sys.path.insert(0, os.path.join(_ENGINE, "agents"))

@pytest.fixture
def base_ctx():
    return {
        "user_input": "Where is my order ORD-2024-001?",
        "customer_email": "test@example.com",
        "company": "default",
        "ticket": None,
        "session_id": "test-session-001",
    }

@pytest.fixture
def dummy_ticket():
    class FakeTicket:
        ticket_id = "TKT-001"; customer_name = "Test User"
        customer_email = "test@example.com"; order_id = "ORD-2024-001"
        priority = "Normal"; subject = "Order enquiry"; messages = []
        state = "new"; state_history = []; version = 0; retry_count = 0
        sla_deadline = None
        def sla_urgency(self): return "normal"
    return FakeTicket()
```

---

## Step 3 — test_state_machine.py

Test the TicketState FSM. Cover:
- Valid transition new → triaged (assert state changes)
- Invalid transition new → qa_passed (assert `InvalidTransitionError` raised)
- Idempotent: going to the same state again does not raise
- `can_goto()` returns True for valid, False for invalid
- `state_history` gets appended after each transition
- Noise transition from new → noise works
- Full happy path: new → triaged → facts_built → drafted → self_reviewed → validated → qa_passed → ready

---

## Step 4 — test_schemas.py

Test all Pydantic schemas. Cover:
- `TriageResult` valid construction
- `TriageResult` raises on invalid route value
- `DraftResponse` valid construction
- `QAResult` with result="pass"
- `QAResult` with result="needs_revision"
- `ValidationResult` verified=True
- `DecisionResult` action="block" with required_human_review=True
- `normalise_intent()` with known intent returns same value
- `normalise_intent()` with unknown intent doesn't raise (returns string)
- `normalise_emotion()` with known and unknown values

---

## Step 5 — test_fact_registry.py

Test `FactRegistry`. Cover:
- `register()` + `get()` returns the stored fact
- `get()` on missing key returns None
- `all_verified()` filters out unverified facts
- `to_context_string()` contains the key and value
- Registering same key twice overwrites with the latest value

Use a helper `_make_fact(**kwargs)` that builds a `Fact` with sensible defaults
(`key="delivery_date"`, `value="2024-12-25"`, `source_type="erp"`,
`source_ref="order/ORD-001"`, `verified=True`).

---

## Step 6 — test_connector_resilience.py

Test `ConnectorResult`, `ConnectorError`, `make_ok`, `make_error`. Cover:
- `make_ok(data)` → `.ok is True`, `.value == data`, `.error is None`
- `make_error(ConnectorError(kind="timeout", retryable=True))` → `.ok is False`, `.error.retryable is True`
- `make_error(ConnectorError(kind="fatal", retryable=False))` → `.ok is False`, `.error.retryable is False`
- All valid `kind` values work: "retryable", "fatal", "auth", "rate_limit", "policy", "timeout"
- `make_ok` result has `.error is None`
- `make_error` result has `.value is None`

---

## Step 7 — test_policy_engine.py

Test `PolicyEngine`. Cover:
- Clean context (no action, high confidence, calm emotion) → `decision.passed is True`
- Context with `action={"type": "issue_refund"}` → `decision.passed is False` (ERP action requires approval)
- Context with `emotion="Angry"`, `confidence={"overall": 0.50}` → not passed or flagged for review
- When not passed, `decision.violations` is a non-empty list
- `decision.required_actions` contains "block" or "review" when not passed

Use a `_ctx(**kwargs)` helper with sensible defaults:
```python
def _ctx(**kwargs):
    d = {"draft": "Dear Customer...", "emotion": "Neutral", "intensity": "Low",
         "intent": "tracking", "confidence": {"overall": 0.85}, "action": None,
         "validation_result": None}
    d.update(kwargs)
    return d
```

---

## Step 8 — test_trace_logger.py

Test `TraceLogger`, `StepTrace`, `redact`. Cover:
- `redact("john@example.com")` → email not present in output, `[REDACTED_EMAIL]` present
- `redact("+33 6 12 34 56 78")` → phone not present in output
- `redact("Order ORD-2024-001")` → non-PII text unchanged
- `StepTrace(...)` constructs without error with all required fields
- `TraceLogger().emit(trace)` prints valid JSON (capture stdout with `capsys`, parse with `json.loads`)

---

## Step 9 — test_memory.py

Test `ScopedMemory`. Use `tmp_path` fixture to give each test its own DB file:
```python
@pytest.fixture
def mem(tmp_path):
    return ScopedMemory("test_company", db_path=str(tmp_path / "mem.db"))
```

Cover:
- `store()` + `recall()` finds the stored item by key
- `recall_as_context()` returns a non-empty string
- Item with `ttl_hours=-1` is purged by `purge_expired()` and not recalled after
- Storing 25 items for the same scope → `recall()` returns ≤ 20 items (MAX_ITEMS cap)
- PII in value is redacted before storage (email in value → `[REDACTED_EMAIL]` stored)

---

## Step 10 — test_health_score.py

Test `HealthScore` and `HealthScoreComputer`. Cover:
- `HealthScore(score=0.90, label="healthy", ...)` → `label == "healthy"`
- `HealthScore(score=0.50, label="at_risk", ...)` → `label == "at_risk"`
- `HealthScore(score=0.20, label="critical", ...)` → `score < 0.40`
- `HealthScoreComputer("default").compute("nonexistent@example.com")` → returns `None` or `HealthScore` without raising

---

## Step 11 — test_sla_routing.py

Test SLA urgency logic. Create a helper ticket with a configurable deadline:
```python
from datetime import datetime, timezone, timedelta

def _ticket(minutes):
    class T:
        sla_deadline = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        def sla_urgency(self):
            mins = (self.sla_deadline - datetime.now(timezone.utc)).total_seconds() / 60
            if mins <= 0:   return "breached"
            if mins <= 30:  return "critical"
            if mins <= 120: return "high"
            return "normal"
    return T()
```

Cover:
- 240 min remaining → "normal"
- 60 min remaining → "high"
- 15 min remaining → "critical"
- -10 min (past deadline) → "breached"
- Import `_determine_route` from `triage` and verify baseline route for calm/neutral is "auto" or "standard"
- Simulate SLA upgrade: breached → route forced to "supervisor"
- Simulate SLA upgrade: critical + non-supervisor route → forced to "priority"

---

## Step 12 — Verify everything

```bash
pytest tests/unit/ -v
```

Expected: all tests pass, zero import errors.
If any test fails due to missing attribute or changed interface, fix the test to match
the actual implementation — do not change engine code to satisfy tests.

Also run with coverage:
```bash
pip install pytest-cov
pytest tests/unit/ -v --cov=cs_ai/engine --cov-report=term-missing
```
