"""
agents/draft_guard.py — DraftGuardAgent

AI-powered content completeness check.

Reads draft_checklist.items from config.json and asks a small AI model
whether each required element is present in the draft.

Returns in context:
  draft_ai_flags : list[str] — labels of elements missing from the draft
                               (empty list = all elements present)

Non-blocking: if the AI call fails or the checklist is disabled / empty,
the agent logs a note and returns without modifying draft_ai_flags.
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


_SYSTEM = """You are a quality-assurance reviewer for B2B customer service email drafts.

You will receive:
1. The customer's original message
2. A draft reply
3. A checklist of required elements

For each checklist item, decide whether it is clearly present in the draft.
Be lenient: if the element is implied or present in spirit, mark it as present.
Only flag it as missing if it is genuinely absent.

Return ONLY a valid JSON object with no extra text:
{
  "missing": ["Label of missing element", ...]
}
Return an empty array if all elements are present.
"""


class DraftGuardAgent(BaseAgent):
    name = "draft_guard"

    def run(self, context: dict) -> dict:
        ctx = dict(context)

        checklist_cfg = CONFIG.get("draft_checklist", {})
        if not checklist_cfg.get("enabled", True):
            ctx.setdefault("draft_ai_flags", [])
            return ctx

        items = checklist_cfg.get("items", [])
        if not items:
            ctx.setdefault("draft_ai_flags", [])
            return ctx

        draft = ctx.get("draft", "")
        if not draft:
            ctx.setdefault("draft_ai_flags", [])
            return ctx

        user_input = ctx.get("user_input", "")

        checklist_text = "\n".join(
            f"{i+1}. [{item['label']}] — {item['description']}"
            for i, item in enumerate(items)
        )

        user_msg = (
            f"Customer message:\n{user_input}\n\n"
            f"Draft reply:\n---\n{draft}\n---\n\n"
            f"Required elements checklist:\n{checklist_text}\n\n"
            "Which elements from the checklist are missing from the draft? "
            "Return the JSON result."
        )

        try:
            ai_cfg   = CONFIG.get("ai", {})
            models   = ai_cfg.get("models", {})
            model_id = (
                models.get("simple", {}).get("model")
                or ai_cfg.get("model", "gpt-4.1-mini")
            )

            response = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user",   "content": user_msg},
                ],
                max_tokens=200,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            raw    = response.choices[0].message.content
            result = json.loads(raw)
            ctx["draft_ai_flags"] = result.get("missing", [])

        except Exception as exc:
            ctx["draft_ai_flags"] = [f"Content check unavailable: {exc}"]

        return ctx
