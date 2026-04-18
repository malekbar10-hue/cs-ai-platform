# 08 — Escalation: Escalation Preview

## What This Does

Right now the escalation engine fires silently: a rule matches, an
action executes (email sent to supervisor, webhook called), and the
agent finds out after the fact — if at all.

This creates two problems. First, agents are surprised when an escalation
fires and they did not expect it. Second, agents sometimes approve a draft
not realizing it will trigger a supervisor notification, which might be
premature or unnecessary.

This improvement adds a preview step: after NLP analysis but before
the draft is shown, the dashboard displays which escalation rules
WOULD fire if the agent approves. The agent can see this, decide if
it is appropriate, and proceed with full awareness.

When the agent does approve and the escalation fires, a toast
notification confirms it: "📢 Escalated: Critical angry customer."

**Where the change lives:** `escalation.py` (new preview function) +
`agents/triage.py` (calls preview, stores results) +
`app.py` / `app_inbox.py` (preview banner + toast).

**Impact:** No surprises. Agents understand why tickets are flagged.
Unnecessary escalations can be caught before they fire.

---

## Prompt — Paste into Claude Code

```
Show agents which escalation rules WOULD fire before they actually fire.

TASK:

1. Add a function preview_escalation(context: dict) -> list[dict] to escalation.py:
   - Same matching logic as evaluate() but does NOT execute any actions
   - Returns list of matching rules:
     [{"rule_id": str, "rule_name": str, "reason": str, "tier": str}, ...]
   - Returns empty list if no rules match

2. Call preview_escalation() in agents/triage.py after NLP detection.
   Store result as ctx["escalation_preview"] = list of matching rules.

3. In app.py and app_inbox.py: if escalation_preview is non-empty, show
   a collapsible warning panel near the Analysis section (expanded by default):

   with st.expander("⚠ Escalation rules matched", expanded=True):
     for rule in ctx["escalation_preview"]:
       st.warning(f"**{rule['rule_name']}** → {rule['tier']} | {rule['reason']}")

   This appears BEFORE the agent approves so they know in advance.

4. When the agent approves and the escalation actually fires, show:
   st.toast(f"Escalation triggered: {rule_name}", icon="📢")

Do NOT change connector.py, learning.py, tickets.py, channels.py, or JSON data files.
```
