# 02 — NLP: Mixed Language Detection

## What This Does

Your current language detector returns either "French" or "English" with
no indication of how confident it is. This creates a silent problem:
a customer writing a mix of both languages (common in bilingual B2B contexts
like Belgium, Switzerland, or Canada) gets classified with full confidence
when the classification is actually uncertain.

This improvement adds a confidence score to language detection. If confidence
is below a threshold (e.g. a message is half French, half English), the
dashboard shows a small warning so the agent can verify the response is
in the right language before sending.

**Where the change lives:** `nlp.py` (detection returns confidence) +
`agents/triage.py` (unpacking updated) + `app.py` / `app_inbox.py`
(warning display).

**Impact:** Agents never accidentally send a French response to an
English-speaking customer or vice versa. Especially important in
multinational B2B accounts.

---

## Prompt — Paste into Claude Code

```
Improve language detection in nlp.py to handle mixed-language messages
and low-confidence cases.

Currently: detect_language() returns "French" or "English" with no confidence.

TASK:

1. Update detect_language() in nlp.py to return (language: str, confidence: float):
   - If French keyword score >= 5 matches: confidence = 0.95
   - If French keyword score is 2-4 matches: confidence = 0.70
   - If French keyword score is 1 match: confidence = 0.50
   - If no matches: return "English", confidence = 0.90
   - If message contains roughly equal FR and EN keywords (both >= 2):
     return the dominant one but set confidence = 0.55

2. Add a "lang_confidence" field to the analysis context dict.

3. In app.py and app_inbox.py: if lang_confidence < 0.65, show a small warning
   in the Analysis panel:
   "⚠ Language uncertain — verify the response is in the right language"

4. Update all callers of detect_language() to unpack the new tuple return value
   (language, confidence) — check triage.py and anywhere else it is called.

Do NOT change connector.py, main.py logic beyond detect_language, or JSON data files.
```
