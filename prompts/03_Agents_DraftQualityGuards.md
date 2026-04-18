# 03 — Agents: Draft Quality Guards

## What This Does

The AI sometimes produces drafts with obvious problems that the QA agent
misses: a response that is only 20 words long, a response missing the
customer's order number, or a draft in English when the customer wrote in French.

These are mechanical checks — not judgment calls — and they should happen
automatically before the human ever sees the draft. This improvement adds
a set of rule-based quality checks that run after the AI generates a draft
and before it reaches the dashboard.

If issues are found, a yellow advisory banner appears above the draft editor
telling the agent exactly what was flagged. Approval is still possible —
these are warnings, not blockers — but the agent is informed.

**Where the change lives:** `agents/response.py` (checks run after draft)
+ `agents/qa.py` (warnings passed to QA agent as hints) +
`app.py` / `app_inbox.py` (warning banner display).

**Impact:** Catches obvious AI mistakes before human review. Reduces
the number of bad drafts that get sent because the agent was in a hurry.

---

## Prompt — Paste into Claude Code

```
Add quality guards to ResponseAgent and QAAgent that catch obvious
draft problems before the human sees them.

TASK:

1. In agents/response.py, after the AI call returns the draft, add:

  def _check_draft_quality(draft: str, context: dict) -> list[str]:
    Returns a list of warning strings (empty list = all good):
    - "Draft too short" if len(draft.split()) < 40
    - "Draft too long" if len(draft.split()) > 600
    - "No greeting detected" if draft does not start with "Dear", "Hello",
      "Bonjour", "Madame", "Monsieur" (check first 30 characters)
    - "No signature detected" if "regards" / "cordialement" / "sincerely"
      not found in last 100 characters (case-insensitive)
    - "Order ID missing" if context has an order_id but that ID does not
      appear anywhere in the draft
    - "Wrong language" if context["language"] is "French" but fewer than
      3 French words found in draft, or vice versa

  Store warnings as ctx["draft_warnings"] = list of strings.

2. In agents/qa.py: if draft_warnings is non-empty, add them as a hint
   to the QA prompt: "Note: automated checks flagged: {warnings}"

3. In app.py and app_inbox.py: if ctx["draft_warnings"] is non-empty,
   show a yellow warning box above the draft editor:
   "⚠ Automated checks: {warning1} · {warning2}"
   This does not block approval — advisory only.

Do NOT change connector.py, nlp.py, learning.py, tickets.py, or JSON data files.
```
