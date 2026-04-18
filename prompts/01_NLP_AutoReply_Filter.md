# 01 — NLP: Auto-Reply & Spam Filter

## What This Does

Right now your pipeline processes every single email that arrives — including
machine-generated ones like out-of-office replies, delivery failure notifications,
and automated system emails. That wastes an AI call, creates a useless draft,
and clutters the agent's inbox.

This improvement adds a noise detector that runs at the very start of the
Triage Agent, before any NLP or AI call happens. If the message is noise,
it is flagged and skipped entirely. The agent sees it greyed out in the inbox
with a label like "🤖 Auto-reply detected — skipped" so they know it arrived
but chose not to process it.

**Where the change lives:** `nlp.py` (detection logic) + `agents/triage.py`
(early exit) + `app_inbox.py` (display).

**Impact:** Cleaner inbox, lower API costs, no wasted drafts on junk emails.

---

## Prompt — Paste into Claude Code

```
Add auto-reply and spam detection to nlp.py so the pipeline
never wastes an AI call on machine-generated emails.

TASK: Add a function detect_noise(text: str, subject: str = "") -> dict to nlp.py:

Returns:
{
  "is_noise": bool,
  "noise_type": "auto_reply" | "out_of_office" | "delivery_failure" | "spam" | None,
  "reason": str
}

Detection rules:
- Auto-reply: subject starts with "Auto:" or "Automatic reply" or "Réponse automatique"
  OR body contains "this is an automated message" / "ceci est un message automatique"
- Out of office: subject or body contains "out of office" / "absent du bureau" /
  "on holiday" / "en congé" / "will be back" / "de retour le"
- Delivery failure: subject contains "Undeliverable" / "Mail delivery failed" /
  "Échec de remise" OR sender contains "mailer-daemon" / "postmaster"
- Spam: body is less than 10 words OR contains more than 5 URLs

Call this function at the very start of TriageAgent.run() in agents/triage.py.
If is_noise is True: set ctx["route"] = "noise", ctx["noise_type"] = noise_type
and return immediately without running any NLP or AI calls.

In app_inbox.py: if a ticket has route="noise", show it greyed out with a
"🤖 Auto-reply detected — skipped" label. Do not open it automatically.

Do NOT change connector.py, learning.py, confidence.py, or any JSON data files.
```
