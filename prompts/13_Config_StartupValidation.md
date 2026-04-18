# 13 — Config: Startup Validation

## What This Does

Right now if a required field is missing from `config.json`, the system
crashes mid-session with a cryptic Python error like `KeyError: 'endpoint'`
or `TypeError: unsupported type`. The agent has no idea what went wrong
or how to fix it.

This is especially problematic when onboarding a new company — you copy
the template, fill in most fields, miss one, and only find out when
something breaks during a real customer interaction.

This improvement adds a startup validator that checks the config file
before the app launches. Required fields produce errors that stop startup
with a clear message: "Missing required field: company.name — add it to
config.json". Optional fields produce warnings that let the app start
but inform the operator what is not configured: "ERP not configured —
using mock data."

**Where the change lives:** New file `cs_ai/engine/config_validator.py` +
`run.py` (validates before launching) + `setup.py` (validates during setup).

**Impact:** Setup errors are caught early with clear guidance instead of
mid-session crashes. Onboarding a new company becomes more reliable.
Operators always know exactly what is and is not configured.

---

## Prompt — Paste into Claude Code

```
Add friendly config validation that catches missing or wrong values
at startup before anything breaks mid-conversation.

TASK:

1. Create cs_ai/engine/config_validator.py:

class ConfigValidator:

  def validate(self, config: dict) -> dict:
    Returns {"ok": bool, "errors": list[str], "warnings": list[str]}

  Required fields — error if missing, null, or empty string:
  - company.name
  - company.agent_role
  - company.agent_signature
  - ai.models.standard.model
  - sla.Normal.response_hours
  - sla.High.response_hours
  - sla.Critical.response_hours

  Optional fields — warning if missing or null:
  - communication.inbound.host
    warning: "Email inbound not configured — manual mode only"
  - communication.outbound.host
    warning: "Email outbound not configured — responses cannot be sent automatically"
  - erp.endpoint
    warning: "ERP not configured — using mock data"
  - confidence.auto_send_enabled
    warning: "Auto-send not in config — defaulting to false (safe)"

  Type checks — error if wrong type:
  - sla.*.response_hours must be a number
  - sla.*.resolution_days must be a number
  - confidence.auto_send_threshold must be a float between 0 and 1
  - confidence.human_review_threshold must be a float between 0 and 1
  - company.supported_languages must be a non-empty list

  Value checks — error if invalid:
  - auto_send_threshold must be strictly greater than human_review_threshold
  - communication.polling_interval_seconds must be >= 10 if present

2. Update run.py — call validator before launching Streamlit:
  from config_validator import ConfigValidator
  result = ConfigValidator().validate(config)
  if result["errors"]:
    for e in result["errors"]:
      print(f"  ❌ {e}")
    print("\nFix these errors in config.json then run again.")
    sys.exit(1)
  for w in result["warnings"]:
    print(f"  ⚠  {w}")
  if not result["warnings"]:
    print("  ✅ Config valid")

3. Also call it in setup.py --company with the same output format.

4. Make ConfigValidator importable without requiring any optional packages
   (no sentence-transformers, no chromadb imports needed here).

Do NOT change any engine files beyond the imports in run.py and setup.py.
Do NOT change any JSON data files or company config files.
```
