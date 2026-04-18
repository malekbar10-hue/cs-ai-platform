"""
draft_fix.py — one-element AI fix helper

Called when an agent clicks "Fix with AI" next to a missing-element warning.
Asks the AI to add the missing element to the draft without rewriting the rest.
"""

import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from main import client, CONFIG


def fix_draft_element(draft: str, label: str, context: dict) -> str:
    """
    Returns an improved draft that includes the previously missing element.
    Raises on AI failure — caller is responsible for catching.
    """
    items = CONFIG.get("draft_checklist", {}).get("items", [])
    description = next(
        (i["description"] for i in items if i["label"] == label),
        label,
    )

    language = context.get("language", "")
    emotion  = context.get("emotion", "")
    intent   = context.get("intent", "")

    system = (
        "You are a B2B customer service writing assistant. "
        "You will receive a draft email and one element that is missing from it. "
        "Naturally integrate the missing element into the draft. "
        "Do NOT rewrite the whole email — only add what is missing, keep everything else intact. "
        "Return only the complete improved draft, no explanations, no commentary."
    )

    user_msg = (
        f"Draft to improve:\n---\n{draft}\n---\n\n"
        f"Missing element: [{label}]\n"
        f"Definition: {description}\n\n"
        f"Customer context — emotion: {emotion}, intent: {intent}, language: {language}\n\n"
        "Return the complete improved draft with the missing element added."
    )

    ai_cfg   = CONFIG.get("ai", {})
    models   = ai_cfg.get("models", {})
    model_id = (
        models.get("simple", {}).get("model")
        or ai_cfg.get("model", "gpt-4.1-mini")
    )

    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=900,
        temperature=0.4,
    )
    return response.choices[0].message.content
