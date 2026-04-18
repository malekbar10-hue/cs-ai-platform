# P0-04 — Connector Resilience

## What This Does

Right now if the ERP or CRM is slow or returns an error, the engine either silently
gets `None` back, crashes with an unhandled exception, or returns stale mock data
with no indication that anything went wrong. There is no retry logic, no circuit
breaker, and no classification of whether an error is recoverable or permanent.

This improvement wraps every connector call in a `ConnectorResult[T]` envelope and
classifies every error as `retryable`, `fatal`, `auth`, `rate_limit`, `policy`, or
`timeout`. Retryable errors are retried with exponential backoff and jitter.
Fatal errors go straight to human review. The orchestrator never crashes because
a connector returned a 500.

**Where the change lives:**
New file `cs_ai/engine/connector_base.py` + update
`cs_ai/engine/connector.py` (wrap existing methods with the new envelope + Tenacity).

**Impact:** Connector outages route tickets to human review instead of crashing.
Every error is classified and logged. Retry behaviour is bounded and auditable.

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
       code:    str      # e.g. "ERP_TIMEOUT", "CRM_404", "AUTH_EXPIRED"
       message: str
       retry_after_s:        int | None = None
       upstream_request_id:  str | None = None

   class ConnectorResult(BaseModel, Generic[T]):
       model_config = ConfigDict(strict=True)
       status:     Literal["ok","error"]
       request_id: str           # uuid4, generated at call time
       data:       T | None = None
       error:      ConnectorError | None = None
       freshness_expires_at: str | None = None  # ISO-8601

       @property
       def ok(self) -> bool:
           return self.status == "ok" and self.data is not None

   def make_ok(data: T, request_id: str, expires_at: str | None = None) -> ConnectorResult:
       return ConnectorResult(status="ok", request_id=request_id, data=data,
                              freshness_expires_at=expires_at)

   def make_error(kind: str, code: str, message: str, request_id: str,
                  retry_after_s: int | None = None) -> ConnectorResult:
       return ConnectorResult(
           status="error", request_id=request_id,
           error=ConnectorError(kind=kind, code=code, message=message,
                                retry_after_s=retry_after_s)
       )

2. Update cs_ai/engine/connector.py:
   - Import ConnectorResult, ConnectorError, make_ok, make_error from connector_base.
   - Import uuid, tenacity.
   - Wrap the existing get_order(), get_customer(), and any other external-calling
     methods in BaseConnector with:

     from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
     import uuid as _uuid

     @retry(
         stop=stop_after_attempt(3),
         wait=wait_exponential_jitter(initial=1, max=10),
         retry=retry_if_exception_type((TimeoutError, ConnectionError)),
         reraise=False,
     )
     def get_order_safe(self, order_id: str) -> ConnectorResult[dict]:
         request_id = str(_uuid.uuid4())
         try:
             data = self.get_order(order_id)   # calls existing method
             if data is None:
                 return make_error("fatal", "ORDER_NOT_FOUND",
                                   f"Order {order_id} not found", request_id)
             return make_ok(data, request_id)
         except TimeoutError as e:
             return make_error("timeout", "ERP_TIMEOUT", str(e), request_id, retry_after_s=5)
         except ConnectionError as e:
             return make_error("retryable", "ERP_CONNECTION", str(e), request_id)
         except PermissionError as e:
             return make_error("auth", "ERP_AUTH", str(e), request_id)
         except Exception as e:
             return make_error("fatal", "ERP_UNKNOWN", str(e), request_id)

   - Add equivalent get_customer_safe(), search_kb_safe() wrappers for CRM/KB calls.
   - Add install tenacity to requirements.txt if not already present (pip install tenacity).

3. Update cs_ai/engine/agents/fact_builder.py (from P0-03):
   - Use get_order_safe() instead of get_order() when calling the connector.
   - If result.ok is False and result.error.kind == "fatal": set ctx["connector_fatal"] = True.
   - If result.ok is False and result.error.kind in ("retryable","timeout"):
     set ctx["connector_degraded"] = True.
   - Log every ConnectorResult.error at WARNING (retryable) or ERROR (fatal) level.

4. Update cs_ai/engine/agents/orchestrator.py:
   - After fact_builder: if ctx.get("connector_fatal") is True, route to "review"
     and skip the rest of the pipeline. DecisionResult(action="review",
     reason="connector_fatal: " + connector error code, required_human_review=True).
   - If ctx.get("connector_degraded") is True: continue pipeline but reduce
     confidence.data_completeness to 0.4 to reflect incomplete data.

5. Create tests/unit/test_connector_resilience.py:
   - Test: get_order_safe() with a mock that raises TimeoutError returns
     ConnectorResult with status="error" and error.kind="timeout".
   - Test: get_order_safe() with a mock that returns valid data returns
     ConnectorResult with status="ok" and result.ok == True.
   - Test: get_order_safe() with a mock that raises Exception returns
     ConnectorResult with error.kind="fatal".

Do NOT change nlp.py, channels.py, tickets.py, app.py, app_inbox.py, or any JSON data files.
Do NOT change the mock data files — the mock connectors still work as before.
If tenacity is not installed: pip install tenacity, then add to requirements.txt.
```
