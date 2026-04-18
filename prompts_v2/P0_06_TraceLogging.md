# P0-06 — Structured Trace Logging

## What This Does

Right now log output is unstructured text. There is no `run_id` linking an entire
pipeline execution together, no per-stage latency, no token count, no prompt version
reference, and no guaranteed PII exclusion. Debugging a production issue means
grepping through raw text and manually correlating events.

This improvement introduces a `StepTrace` model that is emitted after every pipeline
stage, and a `TraceLogger` that writes JSON-structured logs with a consistent schema.
Every log line includes `run_id`, `ticket_id`, `step_name`, `latency_ms`,
`model`, `prompt_version`, `decision`, and `error_code`. PII is stripped
before anything is written.

**Where the change lives:**
New file `cs_ai/engine/trace_logger.py` + updates to
`cs_ai/engine/agents/orchestrator.py` (emit a trace after each stage).

**Impact:** Any production issue can be diagnosed from logs alone without reading
code. Token costs per ticket are tracked automatically. PII never appears in log files.

---

## Prompt — Paste into Claude Code

```
Add structured trace logging to the CS AI pipeline. Every pipeline stage must emit
a StepTrace log line. No raw PII may appear in any log.

TASK:

1. Create cs_ai/engine/trace_logger.py:

   import json
   import logging
   import re
   import time
   import uuid
   from datetime import datetime, UTC
   from pydantic import BaseModel, ConfigDict
   from typing import Literal

   # ── PII redaction ─────────────────────────────────────────────────────────
   _EMAIL_RE   = re.compile(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}')
   _PHONE_RE   = re.compile(r'\+?[\d\s\-\(\)]{7,15}')
   _NAME_WORDS = {"monsieur","madame","mr","mrs","ms","dear"}  # expand as needed

   def redact(text: str) -> str:
       """Strip email addresses and phone numbers from a string."""
       text = _EMAIL_RE.sub("[EMAIL]", text)
       text = _PHONE_RE.sub("[PHONE]", text)
       return text

   # ── StepTrace model ───────────────────────────────────────────────────────
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

       def to_log_dict(self) -> dict:
           d = self.model_dump()
           # ensure no PII fields sneak in
           return d

   # ── TraceLogger ───────────────────────────────────────────────────────────
   class TraceLogger:
       def __init__(self, logger_name: str = "cs_ai.trace"):
           self._log = logging.getLogger(logger_name)
           if not self._log.handlers:
               handler = logging.StreamHandler()
               handler.setFormatter(logging.Formatter("%(message)s"))
               self._log.addHandler(handler)
               self._log.setLevel(logging.INFO)

       def emit(self, trace: StepTrace) -> None:
           self._log.info(json.dumps(trace.to_log_dict()))

       def new_run_id(self) -> str:
           return str(uuid.uuid4())

   _tracer = TraceLogger()

   def get_tracer() -> TraceLogger:
       return _tracer

2. Create cs_ai/engine/agents/base.py (update, do not replace existing content):
   - Add a _trace_step() helper method to BaseAgent:
     def _trace_step(self, ctx: dict, step_name: str, t_start: float,
                     status: str = "ok", error_code: str = "") -> None:
         from trace_logger import StepTrace, get_tracer
         from datetime import datetime, UTC
         trace = StepTrace(
             run_id=ctx.get("run_id", ""),
             ticket_id=str(ctx.get("ticket_id", ctx.get("ticket", {}).get("id", "?"))),
             step_name=step_name,
             status=status,
             latency_ms=round((time.perf_counter() - t_start) * 1000, 1),
             model=ctx.get("model_used", ""),
             prompt_version=ctx.get("prompt_version", "unversioned"),
             input_tokens=ctx.get("token_usage", {}).get("prompt", 0),
             output_tokens=ctx.get("token_usage", {}).get("completion", 0),
             decision=ctx.get("final_decision", {}).get("action", "") if isinstance(ctx.get("final_decision"), dict) else "",
             error_code=error_code,
             timestamp=datetime.now(UTC).isoformat(),
         )
         get_tracer().emit(trace)

3. Update cs_ai/engine/agents/orchestrator.py:
   - Import get_tracer, TraceLogger, and uuid.
   - At the start of run(): generate a run_id with str(uuid.uuid4()) and store in ctx["run_id"].
   - Wrap each agent call with:
       t0 = time.perf_counter()
       ctx = self._triage(ctx)
       self._triage._trace_step(ctx, "triage", t0)
     (Repeat for response, qa, fact_builder, validator, policy evaluation.)
   - On any exception inside a stage: call _trace_step(..., status="error", error_code=type(e).__name__)
     then re-raise or route to review.

4. Add PII assertion to the log output:
   - In TraceLogger.emit(): call redact() on any string fields that could contain
     user-provided content before serialising. Use the redact() function from
     trace_logger.py.
   - Specifically: redact() the `decision` and `error_code` fields as a safety measure.

5. Create tests/unit/test_trace_logger.py:
   - Test that redact() replaces email addresses with "[EMAIL]".
   - Test that redact() replaces phone numbers with "[PHONE]".
   - Test that StepTrace serialises to a dict with all required keys.
   - Test that emit() outputs valid JSON (json.loads should not raise).

Do NOT change nlp.py, channels.py, tickets.py, app.py, app_inbox.py, or any JSON data.
Do NOT log any field that contains the raw email body, customer name, or email address.
Use Python stdlib logging only — no external logging framework required.
```
