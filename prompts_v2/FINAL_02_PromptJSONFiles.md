Create the three prompt JSON files that `PromptRegistry` loads at runtime.
Without these files the pipeline crashes on startup with a `KeyError`.

The registry loads from `cs_ai/prompts/*.json`. Each file must have:
`prompt_id`, `version`, `checksum` (first 16 chars of sha256 of template), `template`.

---

## Step 1 — Read qa.py first

Before creating the files, read `cs_ai/engine/agents/qa.py` and note the exact
keyword arguments passed to `_spec.render(...)`. Use those exact names as `{variable}`
placeholders in `qa_review.json`.

---

## Step 2 — Create `cs_ai/prompts/` directory if it doesn't exist

---

## Step 3 — Create `cs_ai/prompts/triage_system.json`

Triage does NOT call `render()` — it only reads the spec to log `prompt_version`.
Template is informational only.

```json
{
  "prompt_id": "triage_system",
  "version": "1.0.0",
  "checksum": "a3f1b2c4d5e6f7a8",
  "template": "TRIAGE SYSTEM v1.0.0\n\nTriage is implemented deterministically in Python (NLP classifiers + rule-based routing). No LLM call at this stage. This spec is tracked for audit/versioning purposes only."
}
```

---

## Step 4 — Create `cs_ai/prompts/response_system.json`

`response.py` calls `_spec.render()` with these exact keyword arguments:
`role`, `company`, `signature`, `customer_profile`, `order_block`,
`profile_context`, `trajectory_context`, `kb_context`, `history_context`,
`emotion_instruction`, `priority`, `language`, `lessons_block`

```json
{
  "prompt_id": "response_system",
  "version": "1.2.0",
  "checksum": "b7c3d9e2f1a04b5c",
  "template": "You are {role}, a customer service agent for {company}.\n\nWrite a professional, empathetic, and accurate email response to the customer message.\n\n---\n\n{customer_profile}\n\n---\n\nORDER INFORMATION:\n{order_block}\n\n---\n\n{profile_context}\n\n{trajectory_context}\n\n{kb_context}\n\n{history_context}\n\n---\n\nEMOTION GUIDANCE:\n{emotion_instruction}\n\nORDER PRIORITY: {priority}\nRESPONSE LANGUAGE: {language}\n{lessons_block}\n\n---\n\nRULES:\n1. Begin with a proper greeting (Dear / Bonjour if French).\n2. Acknowledge the customer's concern with empathy.\n3. Use ONLY facts present in the order data and knowledge base above — never invent delivery dates, prices, or statuses.\n4. If order data is missing, politely ask for the order number.\n5. End with a professional closing and your signature.\n6. Write exclusively in {language}.\n\nSignature:\n{signature}"
}
```

---

## Step 5 — Create `cs_ai/prompts/qa_review.json`

Read `qa.py` to confirm variable names, then create the file.
The template must return a JSON object — escape literal braces with `{{` and `}}`.

Common variable names (verify against qa.py): `user_input`, `intent`, `emotion`,
`intensity`, `language`, `order_id`, `draft`

```json
{
  "prompt_id": "qa_review",
  "version": "1.1.0",
  "checksum": "c9d4e8f0a2b3c5d1",
  "template": "You are a QA reviewer for a customer service AI system.\n\nReview the draft email below and decide if it meets quality standards.\n\n---\n\nCUSTOMER MESSAGE:\n{user_input}\n\nCONTEXT:\n- Intent: {intent}\n- Emotion: {emotion} (Intensity: {intensity})\n- Language: {language}\n- Order ID: {order_id}\n\nDRAFT:\n{draft}\n\n---\n\nEVALUATE on:\n1. ACCURACY — only facts from order/KB data, no invented dates or prices\n2. EMPATHY — tone matches customer emotional state\n3. COMPLETENESS — addresses the customer's intent ({intent})\n4. LANGUAGE — written entirely in {language}\n5. FORMAT — proper greeting and professional closing\n6. SAFETY — no promises the company cannot keep\n\nRespond in this exact JSON format:\n{{\n  \"result\": \"pass\" or \"needs_revision\",\n  \"score\": 0.0 to 1.0,\n  \"issues\": [\"list specific issues if needs_revision, else empty array\"],\n  \"feedback\": \"one paragraph of actionable feedback for the writer\"\n}}"
}
```

**Important:** If `qa.py` uses different variable names than listed above, update
the template placeholders to match exactly what `qa.py` passes to `render()`.

---

## Step 6 — Verify

Run this in Python from the repo root:

```python
import sys
sys.path.insert(0, "cs_ai/engine")
from prompt_registry import get_registry
reg = get_registry()
print(reg.get("triage_system").prompt_id)   # triage_system
print(reg.get("response_system").version)   # 1.2.0
print(reg.get("qa_review").version)         # 1.1.0
print("All prompt specs loaded OK")
```

All three must load without error. If any raises `KeyError`, check that the
`prompt_id` field in the JSON matches exactly what the agent passes to `get()`.
