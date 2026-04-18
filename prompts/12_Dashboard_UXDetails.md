# 12 — Dashboard: Small UX Details

## What This Does

A collection of small quality-of-life improvements to the dashboard
that individually seem minor but together make the difference between
a tool that feels polished and one that feels unfinished.

**Character count** — Agents can see instantly if a draft is too short
or too long without counting manually.

**Copy button** — One click to copy the full draft to clipboard,
useful when the agent wants to paste it somewhere else.

**Descriptive spinners** — Instead of a generic "Loading..." message,
the spinner tells the agent exactly what the AI is doing right now:
analyzing, generating, reviewing.

**Toast notifications** — Small non-blocking confirmation messages
that appear briefly after actions (sent, ERP executed, escalated)
without interrupting the workflow.

**Ticket count in browser tab** — The browser tab shows how many
open tickets are waiting so agents can glance at it without switching.

**Empty state messages** — When the inbox is empty or analytics has
no data, a friendly message appears instead of a confusing blank screen.

**Where the change lives:** `app.py`, `app_inbox.py`,
`pages/1_Analytics.py` only.

**Impact:** The platform feels professional and complete.
Reduces small friction points that accumulate during a busy day.

---

## Prompt — Paste into Claude Code

```
Add small UX quality-of-life improvements to the dashboard.
All changes are in app.py, app_inbox.py, and pages/1_Analytics.py only.

TASK:

1. Character count on draft editor:
   Below the draft text area, show:
   st.caption(f"{len(edited.split())} words · {len(edited)} chars")
   Color: use st.success caption if 50-400 words, st.warning if outside that range.

2. Copy draft button:
   Next to the character count, add a "📋 Copy" button.
   On click: display the draft text in a st.code() block inside a
   st.popover() so the agent can select and copy it easily.

3. Descriptive spinners during pipeline execution:
   Replace the single spinner with st.status() showing stage messages:
   with st.status("Processing...", expanded=True) as status:
     status.write("🔍 Analyzing message...")
     # after triage
     status.write("✍️ Generating response...")
     # after response agent
     status.write("✅ Reviewing draft...")
     # after QA
     status.update(label="Done", state="complete")
   If st.status is not available in the installed Streamlit version,
   fall back to st.spinner() with the most relevant single message.

4. Toast notifications for key actions:
   After response sent:        st.toast("Response sent ✅", icon="✅")
   After ERP action executed:  st.toast(f"ERP: {action_label} ✅", icon="⚡")
   After escalation fired:     st.toast(f"Escalated: {rule_name}", icon="📢")
   After auto-close runs:      st.toast(f"{count} stale tickets closed", icon="🔒")

5. Ticket count in page title:
   At the top of app_inbox.py, count open tickets and set:
   open_count = ticket_manager.count_open()
   st.set_page_config(
     page_title=f"CS Agent ({open_count} open)" if open_count > 0 else "CS Agent"
   )
   Add count_open() to TicketManager: returns count of tickets with
   status not in ("resolved", "closed").

6. Empty state messages:
   In app_inbox.py: if ticket list is empty after filtering, show:
   st.info("✅ All clear — no open tickets right now.")
   In pages/1_Analytics.py: if no log data, show:
   st.info("No interactions logged yet. Start a conversation to see analytics.")

Do NOT change any backend files — only app.py, app_inbox.py, and pages/1_Analytics.py.
```
