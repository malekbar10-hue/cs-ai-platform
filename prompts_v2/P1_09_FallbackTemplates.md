# P1-09 — Fallback Templates

## What This Does

Right now when the decision engine blocks a draft (policy violation, failed validation,
low confidence), the ticket is routed to human review — but nothing is sent to the
customer. In high-volume scenarios, this means the customer gets no response at all
until a human picks it up.

For certain predictable failure modes, a pre-written safe template is better than
silence. "We have received your message and are investigating — we will respond within
24 hours" is always better than nothing, and it does not require an LLM.

This improvement adds a `FallbackTemplateEngine` that selects the right Jinja2
template based on the reason for the block, renders it with safe variables, and
sends it in place of the AI-generated response when the LLM output is not trusted.

**Where the change lives:**
New file `cs_ai/engine/fallback_engine.py` + new folder `cs_ai/templates/fallback/`
with one `.j2` file per scenario + update orchestrator to invoke fallbacks.

**Impact:** Blocked or low-confidence tickets still send a safe acknowledgement.
Customers never experience complete silence. No LLM is involved in red-zone responses.

---

## Prompt — Paste into Claude Code

```
Add a Jinja2-based fallback template engine for blocked and low-confidence decisions.

TASK:

1. Create cs_ai/templates/fallback/ folder with these Jinja2 template files:

   missing_info.j2:
   ---
   Bonjour {{ customer_name | default("") }},

   Merci pour votre message. Afin de traiter votre demande dans les meilleurs délais,
   pourriez-vous nous communiquer {{ missing_fields | join(", ") }} ?

   Notre équipe reviendra vers vous dès réception de ces informations.

   Cordialement,
   {{ agent_signature }}
   ---

   system_unavailable.j2:
   ---
   Bonjour {{ customer_name | default("") }},

   Nous avons bien reçu votre message et nous en accusons bonne réception.
   En raison d'une indisponibilité temporaire de nos systèmes, notre traitement
   est légèrement retardé.

   Nous reviendrons vers vous dans les plus brefs délais (délai habituel : {{ sla_hours }} heures).

   Cordialement,
   {{ agent_signature }}
   ---

   high_risk.j2:
   ---
   Bonjour {{ customer_name | default("") }},

   Nous avons bien reçu votre demande et la traitons en priorité.
   Un membre de notre équipe vous contactera sous {{ sla_hours }} heures.

   Cordialement,
   {{ agent_signature }}
   ---

   ambiguous_request.j2:
   ---
   Bonjour {{ customer_name | default("") }},

   Merci pour votre message. Nous souhaitons nous assurer de bien comprendre
   votre demande afin de vous apporter la meilleure réponse possible.

   Pourriez-vous préciser l'objet de votre demande et votre numéro de commande
   si disponible ?

   Cordialement,
   {{ agent_signature }}
   ---

   Also create English versions: missing_info_en.j2, system_unavailable_en.j2,
   high_risk_en.j2, ambiguous_request_en.j2 with equivalent content in English.

2. Create cs_ai/engine/fallback_engine.py:

   import os
   from jinja2 import Environment, FileSystemLoader, select_autoescape
   from typing import Literal

   FallbackReason = Literal[
       "missing_info",
       "system_unavailable",
       "high_risk",
       "ambiguous_request",
   ]

   TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates", "fallback")

   class FallbackTemplateEngine:
       def __init__(self):
           self._env = Environment(
               loader=FileSystemLoader(os.path.abspath(TEMPLATES_DIR)),
               autoescape=select_autoescape(["html"]),
           )

       def render(self, reason: FallbackReason, ctx: dict) -> str:
           """
           Select and render the appropriate fallback template.
           ctx must contain at minimum: customer_name, agent_signature, sla_hours.
           Optionally: missing_fields (list[str]), language ("fr" | "en").
           """
           language = ctx.get("language", "fr")
           suffix   = "" if language == "fr" else f"_{language}"
           template_name = f"{reason}{suffix}.j2"
           try:
               tmpl = self._env.get_template(template_name)
           except Exception:
               # Fall back to French if language variant not found
               tmpl = self._env.get_template(f"{reason}.j2")
           return tmpl.render(
               customer_name  = ctx.get("customer_name", ""),
               agent_signature= ctx.get("agent_signature", "L'équipe Support"),
               sla_hours      = ctx.get("sla_hours", 24),
               missing_fields = ctx.get("missing_fields", ["votre numéro de commande"]),
           )

       def reason_for(self, ctx: dict) -> FallbackReason:
           """Determine the appropriate fallback reason from context."""
           if ctx.get("connector_fatal"):
               return "system_unavailable"
           if ctx.get("triage_result") and ctx["triage_result"].missing_fields:
               return "missing_info"
           policy = ctx.get("policy_decision")
           if policy and "no_autosend_angry_low_confidence" in getattr(policy, "violations", []):
               return "high_risk"
           if ctx.get("triage_result") and ctx["triage_result"].intent == "unknown":
               return "ambiguous_request"
           return "high_risk"   # safe default

3. Update cs_ai/engine/agents/orchestrator.py:
   - Import FallbackTemplateEngine and install: self._fallback = FallbackTemplateEngine()
   - After the decision engine: if final decision is "block" AND the policy reason
     is NOT "no_unsupported_claims" (i.e., not a factual hallucination block):
       fallback_reason = self._fallback.reason_for(ctx)
       fallback_body   = self._fallback.render(fallback_reason, ctx)
       ctx["fallback_draft"] = fallback_body
       ctx["used_fallback"]  = True
   - The email sender should check ctx.get("used_fallback") and use ctx["fallback_draft"]
     only if the ticket is configured to auto-send fallbacks (config.json flag
     "fallback.auto_send": true/false, default false = agent must approve).

4. Add to config.json template (do not change existing config.json files):
   In the example/template config, add:
   "fallback": {
     "auto_send": false,
     "default_language": "fr"
   }

5. Create tests/unit/test_fallback_engine.py:
   - Test that render("missing_info", ctx) with language="fr" returns a string
     containing "numéro" (French content).
   - Test that render("missing_info", ctx) with language="en" returns English content.
   - Test that render("high_risk", ctx) returns a string with the sla_hours value.
   - Test that reason_for() returns "system_unavailable" when connector_fatal=True.

If jinja2 is not installed: pip install jinja2, then add to requirements.txt.
Do NOT change nlp.py, channels.py, tickets.py, app.py, app_inbox.py, or any JSON data files.
Do NOT use the LLM to generate fallback content — the whole point is deterministic output.
```
