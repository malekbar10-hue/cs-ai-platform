"""
agents/qa.py — QAAgent

Performs a second AI pass to review the draft response for:
  1. Factual accuracy vs. order data
  2. Tone appropriateness for the customer's emotional state
  3. Policy compliance (no over-promising, no internal system leakage)
  4. Red flags (wrong IDs, contradictions, offensive content)
  5. Completeness (does it actually address the customer's request?)

Returns in context:
  qa_result   : "pass" | "needs_revision"
  qa_feedback : revision instructions (empty string if "pass")
  qa_flags    : list of specific issues (empty list if none)

QA failures are non-blocking — if the AI call fails, we log a warning flag
and mark the result as "pass" so the pipeline can continue.
"""

import json
import os
import sys

_DIR    = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.dirname(_DIR)
for _p in (_ENGINE, _DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from base import BaseAgent
from main import client, CONFIG
from schemas import QAResult
from prompt_registry import get_registry

def _qa_system_prompt() -> str:
    """Load the QA system prompt from the registry (cached after first call)."""
    return get_registry().get("qa_review").render()


class QAAgent(BaseAgent):
    name = "qa"

    def run(self, context: dict) -> dict:
        ctx   = dict(context)
        draft = ctx.get("draft", "")

        if not draft:
            ctx.update({"qa_result": "pass", "qa_feedback": "", "qa_flags": []})
            ctx["qa_result_typed"] = QAResult(verdict="pass")
            return ctx

        user_input = ctx.get("user_input", "")
        emotion    = ctx.get("emotion", "")
        intensity  = ctx.get("intensity", "")
        intent     = ctx.get("intent", "")
        order_info = ctx.get("order_info", "")
        confidence = ctx.get("confidence", {})

        draft_warnings = ctx.get("draft_warnings", [])
        warnings_hint = (
            f"\nNote: automated checks flagged: {' · '.join(draft_warnings)}\n"
            if draft_warnings else ""
        )

        qa_user_msg = (
            f"Customer message:\n{user_input}\n\n"
            f"Customer state: {emotion} ({intensity}), intent: {intent}\n\n"
            f"Order data:\n{order_info or '(no order found)'}\n\n"
            f"Confidence score: {int(confidence.get('overall', 0) * 100)}%\n\n"
            f"Draft response to review:\n---\n{draft}\n---\n"
            f"{warnings_hint}\n"
            "Review this draft and return the JSON result."
        )

        try:
            _qa_spec = get_registry().get("qa_review")
            ctx["prompt_version"] = f"{_qa_spec.prompt_id}@{_qa_spec.version}@{_qa_spec.checksum}"

            ai_cfg   = CONFIG.get("ai", {})
            models   = ai_cfg.get("models", {})
            qa_model = (
                models.get("simple", {}).get("model")
                or ai_cfg.get("model", "gpt-4.1-mini")
            )

            response = client.chat.completions.create(
                model=qa_model,
                messages=[
                    {"role": "system", "content": _qa_system_prompt()},
                    {"role": "user",   "content": qa_user_msg},
                ],
                max_tokens=400,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            raw    = response.choices[0].message.content
            result = json.loads(raw)

            _verdict  = result.get("qa_result", "pass")
            _feedback = result.get("qa_feedback", "")
            _flags    = result.get("qa_flags", [])

            # Normalise verdict to valid Literal value
            if _verdict not in ("pass", "needs_revision"):
                _verdict = "pass"

            ctx.update({
                "qa_result":   _verdict,
                "qa_feedback": _feedback,
                "qa_flags":    _flags,
            })

            # Typed result alongside existing keys
            try:
                ctx["qa_result_typed"] = QAResult(
                    verdict=  _verdict,
                    feedback= _feedback,
                    issues=   _flags,
                )
            except Exception:
                ctx["qa_result_typed"] = None

        except Exception as exc:
            # QA failure must not block the pipeline
            _flags = [f"QA check unavailable: {exc}"]
            ctx.update({
                "qa_result":   "pass",
                "qa_feedback": "",
                "qa_flags":    _flags,
            })
            ctx["qa_result_typed"] = QAResult(verdict="pass", issues=_flags)

        return ctx
