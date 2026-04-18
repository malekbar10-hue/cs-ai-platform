"""
fallback_engine.py — Deterministic Jinja2 fallback drafts.

Used when the pipeline blocks (hallucination, low confidence, connector error)
to produce a safe, pre-written reply that never invents facts.

Usage:
    engine = FallbackTemplateEngine()
    reason = engine.reason_for(ctx)
    ctx["fallback_draft"] = engine.render(reason, ctx)
    ctx["used_fallback"]  = True
"""

from __future__ import annotations

import os
from typing import Literal

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

FallbackReason = Literal[
    "missing_info",
    "system_unavailable",
    "high_risk",
    "ambiguous_request",
]

_LANG_SUFFIX: dict[str, str] = {
    "en":      "_en",
    "english": "_en",
    "fr":      "",
    "french":  "",
}


class FallbackTemplateEngine:

    def __init__(self) -> None:
        templates_dir = os.path.join(
            os.path.dirname(__file__), "..", "templates", "fallback"
        )
        self._env = Environment(
            loader=FileSystemLoader(os.path.abspath(templates_dir)),
            autoescape=select_autoescape(["html"]),
            keep_trailing_newline=True,
        )

    def render(self, reason: FallbackReason, ctx: dict) -> str:
        """Render the fallback template for *reason* in the appropriate language."""
        lang   = (ctx.get("language") or "fr").lower()
        suffix = _LANG_SUFFIX.get(lang, "")
        primary_name = f"{reason}{suffix}.j2"

        try:
            tmpl = self._env.get_template(primary_name)
        except TemplateNotFound:
            # Language variant not found — fall back to French (default)
            tmpl = self._env.get_template(f"{reason}.j2")

        priority   = ctx.get("priority", "Normal")
        sla_hours  = self._sla_hours(ctx, priority)

        return tmpl.render(
            customer_name=   ctx.get("customer_name",   ""),
            agent_signature= ctx.get("agent_signature") or ctx.get(
                "company_signature", "L'équipe Support"
            ),
            sla_hours=       sla_hours,
            missing_fields=  ctx.get("missing_fields", ["votre numéro de commande"]),
        )

    def reason_for(self, ctx: dict) -> FallbackReason:
        """Determine the best fallback reason from pipeline context."""
        if ctx.get("connector_fatal"):
            return "system_unavailable"

        triage = ctx.get("triage_result")
        if triage and getattr(triage, "missing_fields", None):
            return "missing_info"

        policy = ctx.get("policy_decision")
        if policy and "no_autosend_angry_low_confidence" in getattr(policy, "violations", []):
            return "high_risk"

        if triage and getattr(triage, "intent", None) == "unknown":
            return "ambiguous_request"

        return "high_risk"

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _sla_hours(ctx: dict, priority: str) -> int:
        """Return response SLA hours from config or a safe default."""
        config = ctx.get("config") or {}
        sla    = config.get("sla", {})
        tier   = sla.get(priority, sla.get("Normal", {}))
        return int(tier.get("response_hours", ctx.get("sla_hours", 24)))
