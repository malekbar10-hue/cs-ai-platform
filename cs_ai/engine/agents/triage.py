"""
agents/triage.py — TriageAgent

Responsibilities:
  - Run NLP: language, emotion, intent, topic
  - Detect / recover order info
  - Load customer profile + emotional trajectory
  - Determine pipeline route: "auto" | "standard" | "priority" | "supervisor"

Signals set in context:
  _new_order_id   / _new_order_info / _new_priority
      → set only when a NEW order is found in the user message (non-ticket mode)
      → caller (app.py) must copy these to st.session_state
"""

import json
import os
import sys

# Ensure engine dir and agents dir are on sys.path
_DIR    = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.dirname(_DIR)
for _p in (_ENGINE, _DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import hashlib

from base import BaseAgent
from main import (
    detect_language, detect_emotion, detect_intent, detect_topic,
    find_order, get_customer_profile, get_emotion_trajectory,
    order_database, client as _openai_client, CONFIG as _CONFIG,
)
from nlp import detect_noise
from escalation import preview_escalation
from schemas import TriageResult, normalise_intent, normalise_emotion
from prompt_registry import get_registry
from memory import ScopedMemory, make_item
from health_score import HealthScoreComputer

_VALID_INTENTS = {
    "tracking", "refund", "cancel", "complaint", "escalate", "replace",
    "info", "payment", "document_request", "ncmr", "modification", "general_inquiry",
}



_INTENT_SYSTEM_PROMPT = """\
You are an intent classifier for B2B customer service messages.
Return ONLY a JSON object — no explanation, no markdown fences.

Format: {"intent": "<value>", "confidence": <0.0 to 1.0>}

Valid intents:
- "tracking"         : customer asks where their order is, mentions delay, late delivery, waiting, no update on shipment
- "refund"           : wants money back, credit note, reimbursement
- "cancel"           : wants to cancel or stop an order
- "complaint"        : formal complaint about service, product, or treatment
- "escalate"         : asks for a manager, supervisor, or higher authority
- "replace"          : wants a replacement or resend of goods
- "info"             : asks why something happened, wants an explanation or root cause
- "payment"          : question about an invoice, billing amount, or payment
- "document_request" : explicitly asks for a named document — delivery note, POD, certificate, CMR, COA, waybill, etc.
- "ncmr"             : non-conformance, quality deviation, derogation, out-of-spec material
- "modification"     : wants to change order details (quantity, address, date)
- "general_inquiry"  : none of the above

Critical rules:
- If the customer mentions delay, late, 3 weeks, waiting, where is my order, no news, still not received → "tracking"
- Use "document_request" ONLY if the customer explicitly names a document type they want sent
- Pick the intent that requires the most urgent action when ambiguous\
"""


def _gpt_classify_intent(user_input: str) -> tuple[str, float]:
    """
    Ask GPT to classify the customer's intent using system/user message split.
    Returns (intent, confidence). Falls back to local NLP on any error.
    """
    try:
        ai_cfg = _CONFIG.get("ai", {})
        models = ai_cfg.get("models", {})
        model  = models.get("simple", {}).get("model") or ai_cfg.get("model", "gpt-4.1-mini")

        response = _openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _INTENT_SYSTEM_PROMPT},
                {"role": "user",   "content": user_input},
            ],
            temperature=0.0,
            max_tokens=80,
        )
        raw = response.choices[0].message.content.strip()
        # Strip accidental markdown fences
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:].strip()
        data       = json.loads(raw)
        intent     = data.get("intent", "general_inquiry")
        confidence = float(data.get("confidence", 0.5))
        if intent not in _VALID_INTENTS:
            intent = "general_inquiry"
        return intent, round(confidence, 3)
    except Exception as exc:
        import traceback
        _tb = traceback.format_exc()
        print(f"[TriageAgent] GPT intent classification failed: {exc}\n{_tb}")
        # Store the error so the UI can display it
        _gpt_classify_intent._last_error = str(exc)
        return "general_inquiry", 0.0

_gpt_classify_intent._last_error = ""


def _smart_intent_fallback(text: str) -> tuple[str, float] | None:
    """
    Catches the cases where local NLP reliably gives wrong answers.
    Returns (intent, confidence) when confident, else None.
    Called AFTER GPT fails — replaces dumb ChromaDB result for known patterns.
    """
    t = text.lower()
    # Order tracking / delay — local NLP confuses these with document_request
    if any(s in t for s in [
        "delayed", "delay", "late", "3 weeks", "two weeks", "several weeks",
        "not received", "not delivered", "not arrived", "still not",
        "where is my order", "where is my", "where is it",
        "been waiting", "no update", "no news", "overdue",
        "delivery date", "when will", "status of my order",
    ]):
        return "tracking", 0.90
    if any(s in t for s in ["refund", "reimburse", "money back", "credit note",
                              "remboursement", "avoir"]):
        return "refund", 0.90
    if any(s in t for s in ["cancel", "annuler", "annulation"]):
        return "cancel", 0.90
    if any(s in t for s in ["manager", "supervisor", "escalate", "responsable"]):
        return "escalate", 0.90
    return None


class TriageAgent(BaseAgent):
    name = "triage"

    def run(self, context: dict) -> dict:
        ctx        = dict(context)
        user_input = ctx["user_input"]
        text       = user_input.lower()
        ticket     = ctx.get("ticket")

        # ── Customer memory — recall prior context for this client ─────────
        _company   = ctx.get("company", "default")
        _mem       = ScopedMemory(_company)
        _raw_email = (
            getattr(ticket, "customer_email", None) or ctx.get("customer_email", "")
        )
        _client_id = hashlib.sha256(_raw_email.encode()).hexdigest()[:16]
        ctx["client_id"]             = _client_id
        ctx["client_memory_context"] = _mem.recall_as_context("client", _client_id)

        # ── Customer health score ─────────────────────────────────────────
        try:
            _hs = HealthScoreComputer(_company).compute(_raw_email)
        except Exception:
            _hs = None
        ctx["customer_health"] = _hs

        # ── SLA urgency (computed from ticket deadline before NLP) ────────
        _sla_urgency = ticket.sla_urgency() if ticket else "normal"
        ctx["sla_urgency"] = _sla_urgency

        # ── Noise detection — skip AI for auto-replies, OOO, delivery failures, spam ──
        _subject = getattr(ticket, "subject", "") or "" if ticket else ""
        _sender  = getattr(ticket, "customer_email", "") or "" if ticket else ""
        _noise   = detect_noise(user_input, subject=_subject, sender=_sender)
        if _noise["is_noise"]:
            ctx["route"]        = "noise"
            ctx["noise_type"]   = _noise["noise_type"]
            ctx["noise_reason"] = _noise["reason"]
            return ctx

        # ── NLP ───────────────────────────────────────────────────────────────
        language, lang_confidence, lang_mixed = detect_language(text)
        emotion, intensity, all_scores, emo_conf = detect_emotion(text)
        top_score = max(all_scores.values()) if all_scores else 0
        secondary = [
            e for e, s in all_scores.items()
            if s >= top_score * 0.30 and e != emotion
        ]
        # Intent: GPT first, smart fallback second, local NLP last resort
        intent, int_conf = _gpt_classify_intent(user_input)
        if intent == "general_inquiry" and int_conf == 0.0:
            # GPT failed — try smart pattern fallback before local NLP
            _fb = _smart_intent_fallback(text)
            if _fb:
                intent, int_conf = _fb
                ctx["gpt_intent_error"] = f"GPT failed ({_gpt_classify_intent._last_error}), smart fallback used"
            else:
                intent, int_conf = detect_intent(text)
                ctx["gpt_intent_error"] = _gpt_classify_intent._last_error or "unknown error"
        else:
            ctx["gpt_intent_error"] = ""
        topic, top_conf = detect_topic(text)

        # ── Order detection ───────────────────────────────────────────────────
        order_info, priority, order_id = find_order(user_input)

        if order_id:
            # New order found in the message
            if not ticket:
                ctx["_new_order_id"]   = order_id
                ctx["_new_order_info"] = order_info
                ctx["_new_priority"]   = priority
        elif ticket and getattr(ticket, "order_id", None):
            # Use ticket's existing order
            order_id   = ticket.order_id
            order      = order_database.get(order_id, {})
            priority   = order.get("priority", getattr(ticket, "priority", "Normal"))
            order_info = json.dumps(order, indent=2) if order else ""
        else:
            # Fall back to whatever is already in session (passed from app.py)
            order_id   = ctx.get("session_order_id")
            order_info = ctx.get("session_order_info", "")
            priority   = ctx.get("session_priority", "Normal")

        # ── Customer context ──────────────────────────────────────────────────
        customer_name = (
            getattr(ticket, "customer_name", None) if ticket else None
        ) or ""

        profile    = get_customer_profile(customer_name) if customer_name else None
        trajectory = get_emotion_trajectory(customer_name)

        # ── Route ─────────────────────────────────────────────────────────────
        route = _determine_route(emotion, intensity, intent, priority, trajectory, profile)

        # Health-based route upgrade (critical health → at least priority)
        if _hs and _hs.label == "critical" and route not in ("supervisor",):
            route = "priority"

        # SLA-based route upgrade
        if _sla_urgency == "breached":
            route = "supervisor"
        elif _sla_urgency == "critical" and route not in ("supervisor", "priority"):
            route = "priority"
        elif _sla_urgency == "high" and route == "auto":
            route = "standard"

        # Build partial context for escalation preview (confidence not yet scored)
        _esc_ctx = {
            "emotion":   emotion,
            "intensity": intensity,
            "intent":    intent,
        }
        escalation_preview = preview_escalation(_esc_ctx)

        ctx.update({
            "language":            language,
            "lang_confidence":     lang_confidence,
            "lang_mixed":          lang_mixed,
            "emotion":             emotion,
            "intensity":           intensity,
            "secondary":           secondary,
            "intent":              intent,
            "topic":               topic,
            "emo_conf":            emo_conf,
            "int_conf":            int_conf,
            "top_conf":            top_conf,
            "order_id":            order_id,
            "order_info":          order_info,
            "priority":            priority,
            "customer_name":       customer_name,
            "profile":             profile,
            "trajectory":          trajectory,
            "route":               route,
            "escalation_preview":  escalation_preview,
        })

        # ── Typed triage result (alongside existing keys) ─────────────────
        _risk_flags = [r["rule_name"] for r in escalation_preview]
        if _hs:
            if _hs.label == "critical":
                _risk_flags.append("customer_critical_health")
            elif _hs.label == "at_risk":
                _risk_flags.append("customer_at_risk")
        if _sla_urgency == "breached":
            _risk_flags.append("sla_breached")
        elif _sla_urgency == "critical":
            _risk_flags.append("sla_critical")
        elif _sla_urgency == "high":
            _risk_flags.append("sla_high")
        _missing    = []
        if not order_id and intent in ("order_status", "delay", "modification", "cancellation"):
            _missing.append("order_id")

        try:
            ctx["triage_result"] = TriageResult(
                intent=         normalise_intent(intent),
                emotion=        normalise_emotion(emotion),
                language=       language,
                risk_flags=     _risk_flags,
                missing_fields= _missing,
                route=          route if route in ("auto","standard","priority","supervisor") else "standard",
            )
        except Exception as _exc:
            ctx["triage_result"] = None
            ctx.setdefault("pipeline_warnings", []).append(
                f"TriageResult build failed: {_exc}"
            )

        try:
            _spec = get_registry().get("triage_system")
            ctx["prompt_version"] = f"{_spec.prompt_id}@{_spec.version}@{_spec.checksum}"
        except Exception:
            pass

        # ── Persist derived facts — never raw message content ─────────────
        try:
            _mem.store(make_item("client", _client_id, "last_emotion", emotion,  ttl_hours=168))
            _mem.store(make_item("client", _client_id, "last_intent",  intent,   ttl_hours=168))
        except Exception:
            pass  # memory failure must never block the pipeline

        return ctx


# ---------------------------------------------------------------------------
# Route helper (module-level so it can be unit-tested)
# ---------------------------------------------------------------------------

def _determine_route(emotion, intensity, intent, priority, trajectory, profile):
    """
    Highest priority wins (checked top → bottom):
      supervisor — needs human escalation path
      priority   — high-stakes but AI can draft
      auto       — simple, calm, high-confidence scenarios
      standard   — everything else
    """
    # Supervisor: explicit escalation/cancel request
    if intent in ("escalate", "cancel"):
        return "supervisor"

    # Supervisor: very angry or urgent customer
    if emotion in ("Angry", "Urgent") and intensity in ("Very High", "High"):
        return "supervisor"

    # Supervisor: escalating trend + repeat customer (≥3 contacts)
    if (
        trajectory and trajectory.get("trend") == "Escalating"
        and (profile or {}).get("total_interactions", 0) >= 3
    ):
        return "supervisor"

    # Priority: critical order or significant emotion intensity
    if priority == "Critical":
        return "priority"
    if intensity in ("High", "Very High"):
        return "priority"

    # Auto: simple routine request with calm emotion
    if intent in ("tracking", "info", "document_request") and emotion in ("Neutral", "Satisfied"):
        return "auto"

    return "standard"
