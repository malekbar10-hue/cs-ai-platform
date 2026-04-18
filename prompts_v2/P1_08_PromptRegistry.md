# P1-08 — Prompt Registry + Versioning

## What This Does

Right now prompts are inline strings scattered across multiple files. When a prompt
is changed and something breaks, there is no way to know which change caused the
regression, which version was running when an issue occurred, or how to roll back
quickly.

This improvement introduces a `PromptRegistry` that versions every prompt with a
semantic version, a checksum, and a changelog entry. Every LLM call references a
`prompt_id` and `version`. The `StepTrace` (from P0-06) automatically records the
prompt version used. Rolling back to the previous version is a one-line config change.

**Where the change lives:**
New file `cs_ai/engine/prompt_registry.py` + a `prompts/` folder with versioned
prompt files + update `cs_ai/engine/agents/response.py` and
`cs_ai/engine/agents/triage.py` to load prompts from the registry.

**Impact:** Every LLM regression is attributable to a specific prompt version and PR.
Rollback is a config change, not a code deployment.

---

## Prompt — Paste into Claude Code

```
Add a PromptRegistry that versions every LLM prompt and makes them independently
loadable, auditable, and rollback-able.

TASK:

1. Create cs_ai/engine/prompt_registry.py:

   import hashlib
   import json
   import os
   from dataclasses import dataclass, field
   from typing import Optional

   @dataclass
   class PromptSpec:
       prompt_id:   str     # e.g. "triage_system", "response_system", "qa_review"
       version:     str     # semver e.g. "1.0.0"
       content:     str     # the actual prompt template string
       variables:   list[str] = field(default_factory=list)  # e.g. ["customer_name", "order_id"]
       changelog:   str = ""
       checksum:    str = ""

       def __post_init__(self):
           self.checksum = hashlib.sha256(self.content.encode()).hexdigest()[:12]

       def render(self, **kwargs) -> str:
           """Substitute {variable} placeholders with provided kwargs."""
           try:
               return self.content.format(**kwargs)
           except KeyError as e:
               raise ValueError(f"Missing variable {e} for prompt {self.prompt_id}@{self.version}")

   class PromptRegistry:
       def __init__(self, prompts_dir: str):
           self._prompts: dict[str, PromptSpec] = {}
           self._dir = prompts_dir
           self._load_all()

       def _load_all(self):
           """Load all .json prompt files from the prompts directory."""
           if not os.path.isdir(self._dir):
               return
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

       def register(self, spec: PromptSpec) -> None:
           self._prompts[spec.prompt_id] = spec

   # Singleton — loaded once at startup
   _PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")
   _registry: Optional[PromptRegistry] = None

   def get_registry() -> PromptRegistry:
       global _registry
       if _registry is None:
           _registry = PromptRegistry(os.path.abspath(_PROMPTS_DIR))
       return _registry

2. Create cs_ai/prompts/ folder and extract the main system prompts into JSON files:

   cs_ai/prompts/triage_system.json:
   {
     "prompt_id": "triage_system",
     "version": "1.0.0",
     "changelog": "Initial extraction from inline string in triage.py",
     "variables": ["company_name", "agent_role", "supported_languages"],
     "content": "< extract the actual system prompt string from cs_ai/engine/agents/triage.py >"
   }

   cs_ai/prompts/response_system.json:
   {
     "prompt_id": "response_system",
     "version": "1.0.0",
     "changelog": "Initial extraction from inline string in response.py",
     "variables": ["company_name", "agent_role", "agent_signature",
                   "customer_name", "order_info", "kb_context",
                   "verified_facts_context", "history_context"],
     "content": "< extract the actual system prompt string from cs_ai/engine/agents/response.py >"
   }

   cs_ai/prompts/qa_review.json:
   {
     "prompt_id": "qa_review",
     "version": "1.0.0",
     "changelog": "Initial extraction from inline string in qa.py",
     "variables": ["draft", "triage_summary"],
     "content": "< extract the actual system prompt string from cs_ai/engine/agents/qa.py >"
   }

3. Update cs_ai/engine/agents/response.py:
   - Import get_registry from prompt_registry.
   - Replace the inline system prompt string with:
       spec = get_registry().get("response_system")
       system_prompt = spec.render(
           company_name=..., agent_role=..., agent_signature=...,
           customer_name=..., order_info=..., kb_context=...,
           verified_facts_context=ctx.get("verified_facts_context",""),
           history_context=...,
       )
       ctx["prompt_version"] = f"{spec.prompt_id}@{spec.version}"
   - Remove the raw prompt string from the agent file.

4. Update cs_ai/engine/agents/triage.py:
   - Same pattern: load "triage_system" from registry, render with variables,
     set ctx["prompt_version"] for the triage step.

5. Update cs_ai/engine/agents/qa.py:
   - Same pattern: load "qa_review" from registry, render with draft and triage_summary.

6. Create tests/unit/test_prompt_registry.py:
   - Test that get_registry().get("response_system") returns a PromptSpec.
   - Test that PromptSpec.render() with all variables filled returns a string.
   - Test that PromptSpec.render() with a missing variable raises ValueError.
   - Test that PromptSpec.checksum is a 12-character hex string.
   - Test that loading the same prompt twice returns the same checksum.

Do NOT change nlp.py, channels.py, tickets.py, app.py, app_inbox.py, or any JSON data.
Do NOT change the prompt content — only extract it into the JSON format.
If the inline prompt uses f-strings with local variables, convert them to
{variable_name} format placeholders compatible with str.format().
```
