"""
agents/response.py — ResponseAgent

Responsibilities:
  - Format all context blocks (profile, trajectory, KB, history)
  - Build system prompt (with optional QA revision feedback)
  - Detect ERP action suggestion
  - Score confidence
  - Select model tier
  - Call OpenAI and return draft
"""

import os
import re
import sys

_DIR    = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.dirname(_DIR)
for _p in (_ENGINE, _DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from base import BaseAgent
from main import (
    client,
    detect_suggested_action,
    format_customer_profile_context, format_trajectory_context,
    search_knowledge_base, format_kb_context,
    search_history, format_history_context,
    select_model,
    get_emotion_instruction,
    COMPANY, ROLE, SIGNATURE,
)
from confidence import ConfidenceScorer
from learning import get_analyzer as _get_analyzer
from tickets import log_kb_usage as _log_kb_usage
from schemas import DraftResponse
from prompt_registry import get_registry

_scorer = ConfidenceScorer()

_FRENCH_SAMPLE = [
    "commande", "livraison", "retard", "facture", "bonjour", "merci",
    "problème", "bloquée", "votre", "notre", "nous", "pouvez", "pouvons",
    "avons", "avez", "sont", "être", "colis", "cordialement",
]


def _check_draft_quality(draft: str, context: dict) -> list:
    warnings = []
    words = draft.split()

    if len(words) < 40:
        warnings.append("Draft too short")
    if len(words) > 600:
        warnings.append("Draft too long")

    opening = draft[:30].lower()
    greetings = ("dear", "hello", "bonjour", "madame", "monsieur")
    if not any(opening.startswith(g) for g in greetings):
        warnings.append("No greeting detected")

    closing = draft[-100:].lower()
    closings = ("regards", "cordialement", "sincerely")
    if not any(c in closing for c in closings):
        warnings.append("No signature detected")

    order_id = context.get("order_id")
    if order_id and order_id not in draft:
        warnings.append("Order ID missing")

    language = context.get("language", "")
    draft_lower = draft.lower()
    if language == "French":
        fr_hits = sum(
            1 for w in _FRENCH_SAMPLE
            if re.search(r'\b' + re.escape(w) + r'\b', draft_lower)
        )
        if fr_hits < 3:
            warnings.append("Wrong language")
    elif language == "English":
        fr_hits = sum(
            1 for w in _FRENCH_SAMPLE
            if re.search(r'\b' + re.escape(w) + r'\b', draft_lower)
        )
        if fr_hits >= 3:
            warnings.append("Wrong language")

    return warnings


class ResponseAgent(BaseAgent):
    name = "response"

    def run(self, context: dict) -> dict:
        ctx = dict(context)

        user_input    = ctx["user_input"]
        emotion       = ctx["emotion"]
        intensity     = ctx["intensity"]
        secondary     = ctx.get("secondary", [])
        intent        = ctx["intent"]
        topic         = ctx["topic"]
        language      = ctx["language"]
        order_id      = ctx.get("order_id")
        order_info    = ctx.get("order_info", "")
        priority      = ctx.get("priority", "Normal")
        customer_name = ctx.get("customer_name", "")
        profile       = ctx.get("profile")
        trajectory    = ctx.get("trajectory")
        emo_conf      = ctx.get("emo_conf", 0)
        ticket        = ctx.get("ticket")

        # QA revision feedback from a previous attempt
        qa_feedback = ctx.get("qa_feedback", "")

        # ── Context blocks ─────────────────────────────────────────────────
        profile_context    = format_customer_profile_context(customer_name)
        trajectory_context = format_trajectory_context(trajectory, customer_name)
        kb_entries         = search_knowledge_base(intent, topic, user_input.lower())
        kb_context         = format_kb_context(kb_entries)

        current_session_id = (
            getattr(ticket, "ticket_id", None) if ticket
            else ctx.get("session_id")
        )

        # Log each KB entry retrieved so analytics can track usage
        for _kb in kb_entries:
            _kb_id = _kb.get("id")
            if _kb_id:
                _log_kb_usage(_kb_id, current_session_id, _kb.get("relevance", 0.0))
        history = search_history(
            order_id=order_id,
            customer_name=customer_name,
            intent=intent,
            topic=topic,
            current_session_id=current_session_id,
        )
        history_context = format_history_context(history)

        # ── Lessons from past corrections ──────────────────────────────────
        try:
            _lesson_dicts = _get_analyzer().get_lessons(
                emotion=emotion,
                intent=intent,
                topic=topic,
                customer_name=customer_name,
            )
        except Exception:
            _lesson_dicts = []

        lesson_strings = [d["lesson"] for d in _lesson_dicts]
        applied_lesson_ids = [d["id"] for d in _lesson_dicts]

        # ── System prompt ──────────────────────────────────────────────────
        _secondary_label = (
            f" (secondary signals: {', '.join(secondary)})" if secondary else ""
        )
        _customer_profile = (
            f"CUSTOMER ANALYSIS (this turn):\n"
            f"- Language:        {language}\n"
            f"- Emotional state: {emotion} — Intensity: {intensity}{_secondary_label}\n"
            f"- Primary intent:  {intent}\n"
            f"- Topic area:      {topic}"
        )
        _order_block = (
            order_info if order_info
            else "ORDER DATA: No order number found yet. If the customer hasn't provided one, politely ask for it."
        )
        _lessons_block = ""
        if lesson_strings:
            _lines = "\n".join(f"- {l}" for l in lesson_strings)
            _lessons_block = (
                "\nLEARNED FROM PAST CORRECTIONS — apply to this response:\n"
                f"{_lines}\n"
            )

        _spec         = get_registry().get("response_system")
        system_prompt = _spec.render(
            role=               ROLE,
            company=            COMPANY,
            signature=          SIGNATURE,
            customer_profile=   _customer_profile,
            order_block=        _order_block,
            profile_context=    profile_context    if profile_context    else "",
            trajectory_context= trajectory_context if trajectory_context else "",
            kb_context=         kb_context         if kb_context         else "",
            history_context=    history_context    if history_context    else "",
            emotion_instruction=get_emotion_instruction(emotion, intensity),
            priority=           priority,
            language=           language,
            lessons_block=      _lessons_block,
        )
        ctx["prompt_version"] = f"{_spec.prompt_id}@{_spec.version}@{_spec.checksum}"

        # Inject verified facts block when available
        _vf = ctx.get("verified_facts_context", "")
        if _vf and _vf != "(no verified facts)":
            system_prompt += (
                "\n\n## Verified Facts\n"
                "The following facts have been verified against live order and "
                "customer data. Only state things that are consistent with them:\n"
                f"{_vf}"
            )

        # Inject cross-ticket customer memory (emotion/intent from prior contacts)
        _mem_ctx = ctx.get("client_memory_context", "")
        if _mem_ctx:
            system_prompt += (
                "\n\n## Customer History\n"
                "The following context was remembered from previous interactions "
                "with this customer. Use it to personalise your response:\n"
                f"{_mem_ctx}"
            )

        if qa_feedback:
            system_prompt += (
                "\n\nQA REVISION REQUIRED — the previous draft was reviewed and "
                "needs improvement:\n"
                f"{qa_feedback}\n"
                "Please revise the response to address all feedback above."
            )

        # ── ERP action suggestion ──────────────────────────────────────────
        action = detect_suggested_action(
            order_id, intent, emotion, intensity, text=user_input.lower()
        )

        # ── Confidence scoring ─────────────────────────────────────────────
        confidence = _scorer.score(
            nlp_confidence=emo_conf,
            emotion=emotion,
            intensity=intensity,
            intent=intent,
            profile=profile,
            trajectory=trajectory,
            action=action,
        )

        # ── Model selection ────────────────────────────────────────────────
        model_cfg = select_model(
            emotion, intensity, intent,
            confidence_score=confidence["overall"],
        )

        # ── Conversation history ───────────────────────────────────────────
        if ticket:
            conv_history = [
                {
                    "role": "user" if m["role"] == "customer" else "assistant",
                    "content": m["content"],
                }
                for m in ticket.messages[-10:]
            ]
        else:
            conv_history = ctx.get("conversation_history", [])

        messages = (
            [{"role": "system", "content": system_prompt}]
            + conv_history
            + [{"role": "user", "content": user_input}]
        )

        # ── AI call ────────────────────────────────────────────────────────
        response = client.chat.completions.create(
            model=model_cfg["model"],
            messages=messages,
            max_tokens=model_cfg["max_tokens"],
            temperature=model_cfg["temperature"],
        )
        draft          = response.choices[0].message.content
        draft_warnings = _check_draft_quality(draft, ctx)

        # Token usage dict (empty if not available)
        _usage = {}
        if hasattr(response, "usage") and response.usage:
            _usage = {
                "prompt_tokens":     getattr(response.usage, "prompt_tokens", 0),
                "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                "total_tokens":      getattr(response.usage, "total_tokens", 0),
            }

        ctx.update({
            "system_prompt":      system_prompt,
            "profile_context":    profile_context,
            "trajectory_context": trajectory_context,
            "kb_entries":         kb_entries,
            "kb_context":         kb_context,
            "history":            history,
            "history_context":    history_context,
            "action":             action,
            "confidence":         confidence,
            "model_used":         model_cfg["model"],
            "model_cfg":          model_cfg,
            "draft":               draft,
            "draft_warnings":      draft_warnings,
            "applied_lesson_ids":  applied_lesson_ids,
        })

        # ── Typed draft result (alongside existing keys) ───────────────────
        _ticket_id = (
            getattr(ctx.get("ticket"), "ticket_id", None)
            or ctx.get("session_id", "")
        )
        _facts_used = [
            str(e.get("title", e.get("id", "")))
            for e in kb_entries
            if e.get("title") or e.get("id")
        ]
        try:
            ctx["draft_result"] = DraftResponse(
                ticket_id=   _ticket_id,
                body=        draft,
                language=    language,
                prompt_ref=  "unversioned",
                facts_used=  _facts_used,
                model_used=  model_cfg["model"],
                token_usage= _usage,
            )
        except Exception as _exc:
            ctx["draft_result"] = None
            ctx.setdefault("pipeline_warnings", []).append(
                f"DraftResponse build failed: {_exc}"
            )

        return ctx
