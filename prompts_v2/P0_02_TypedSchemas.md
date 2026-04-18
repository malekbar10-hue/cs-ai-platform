# P0-02 — Typed Schemas (Pydantic at every agent boundary)

## What This Does

Right now agents pass raw Python dicts between each other. If the triage agent adds
a key the response agent doesn't expect, or omits one it does, the error shows up
as a cryptic KeyError deep in the pipeline — not at the boundary where the mistake
was made.

This improvement introduces strict Pydantic models as the contract at every agent
boundary. A `ValidationError` raised at the boundary is far more useful than a
`KeyError` three functions later. It also makes the system self-documenting: reading
the schema tells you exactly what each agent produces and consumes.

**Where the change lives:**
New file `cs_ai/engine/schemas.py` + lightweight updates to triage, response,
qa, draft_guard agents to produce and consume typed outputs.

**Impact:** Shape bugs are caught at the exact agent boundary that caused them.
The system is self-documented. Adding a new field never silently breaks downstream.

---

## Prompt — Paste into Claude Code

```
Introduce strict Pydantic schemas at every agent boundary in the CS AI engine.

TASK:

1. Create cs_ai/engine/schemas.py with the following models (all use ConfigDict(strict=True)):

   from pydantic import BaseModel, ConfigDict, Field
   from typing import Literal

   class ConfidenceScores(BaseModel):
       model_config = ConfigDict(strict=True)
       intent:          float = Field(ge=0.0, le=1.0)
       emotion:         float = Field(ge=0.0, le=1.0)
       data_completeness: float = Field(ge=0.0, le=1.0)
       factual_support: float = Field(ge=0.0, le=1.0)
       tone_quality:    float = Field(ge=0.0, le=1.0)
       final:           float = Field(ge=0.0, le=1.0)

   class TriageResult(BaseModel):
       model_config = ConfigDict(strict=True)
       intent:   Literal["order_status","complaint","delay","invoice",
                          "cancellation","modification","unknown"]
       emotion:  Literal["calm","neutral","frustrated","angry"]
       language: str
       risk_flags:     list[str] = []
       missing_fields: list[str] = []
       route:    Literal["auto","standard","priority","supervisor"] = "standard"
       confidence: ConfidenceScores | None = None
       is_noise: bool = False
       noise_reason: str = ""

   class DraftResponse(BaseModel):
       model_config = ConfigDict(strict=True)
       ticket_id:   str
       body:        str
       language:    str
       prompt_ref:  str = "unversioned"
       facts_used:  list[str] = []   # list of fact keys used in this draft
       model_used:  str = ""
       token_usage: dict = {}        # {"prompt": int, "completion": int}

   class QAResult(BaseModel):
       model_config = ConfigDict(strict=True)
       verdict:  Literal["pass","needs_revision"]
       feedback: str = ""
       issues:   list[str] = []

   class ValidationResult(BaseModel):
       model_config = ConfigDict(strict=True)
       verified:                bool
       unsupported_claims:      list[str] = []
       contradictions:          list[str] = []
       policy_violations:       list[str] = []
       supported_claims_ratio:  float = Field(ge=0.0, le=1.0, default=1.0)

   class DecisionResult(BaseModel):
       model_config = ConfigDict(strict=True)
       action:               Literal["send","review","block","escalate"]
       reason:               str
       required_human_review: bool = False
       blocked_by:           list[str] = []

2. Update cs_ai/engine/agents/triage.py:
   - Import TriageResult and ConfidenceScores from schemas
   - At the end of TriageAgent.run(), build and validate a TriageResult from the
     computed values and store it in ctx["triage_result"] (as a model instance).
   - Do NOT remove any existing keys from ctx — just add the typed result alongside them.

3. Update cs_ai/engine/agents/response.py:
   - Import DraftResponse from schemas
   - After the AI call, build a DraftResponse and store in ctx["draft_result"].

4. Update cs_ai/engine/agents/qa.py:
   - Import QAResult from schemas
   - Return a QAResult stored in ctx["qa_result"].

5. Update cs_ai/engine/agents/orchestrator.py:
   - After each agent call, if the typed result exists in ctx, validate it with
     model.model_validate(ctx["..."]) — catch pydantic.ValidationError, log at
     ERROR level with the field errors, and set ctx["pipeline_error"] = str(e).

6. Create tests/unit/test_schemas.py:
   - Test that a valid TriageResult parses without error.
   - Test that an invalid intent value (e.g. "gibberish") raises ValidationError.
   - Test that ConfidenceScores rejects a value > 1.0.
   - Test that DecisionResult rejects an action not in the Literal set.

Do NOT change nlp.py, channels.py, tickets.py, app.py, or any JSON data files.
Do NOT remove any existing dict keys from ctx — add typed results alongside them
for backward compatibility.
Pydantic must already be installed (it is used by the existing codebase).
```
