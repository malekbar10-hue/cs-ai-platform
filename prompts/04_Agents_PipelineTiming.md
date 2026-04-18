# 04 — Agents: Pipeline Timing Display

## What This Does

Right now the dashboard shows a spinner while the AI works, then the draft
appears. Agents have no idea how long each step took, which model was used,
or whether the QA agent flagged anything.

This improvement adds a collapsible "Pipeline details" panel below the
Analysis section that shows exactly what happened behind the scenes:
how long Triage took, how long Response generation took, how long QA took,
which AI model was selected, and what the QA result was.

It also adds a small "Generated in 2.3s · gpt-4.1-mini" caption near
the draft so agents have instant visibility.

**Where the change lives:** `agents/orchestrator.py` (timing recording) +
`app.py` / `app_inbox.py` (display).

**Impact:** Full transparency into the AI pipeline. Makes it easy to spot
when something is slow (e.g. QA is taking 5 seconds) and helps with
debugging during early deployment.

---

## Prompt — Paste into Claude Code

```
Show how long each agent took in the dashboard so agents can see
the AI processing time and spot slow calls.

TASK:

1. In agents/orchestrator.py, verify that pipeline_timings records time for:
   "triage", "response", "qa", and any retry steps.
   If missing, add time.time() before and after each agent.run() call.
   Also add "total" = sum of all agent timings.

2. In app.py and app_inbox.py, add a collapsible "Pipeline details" section
   below the Analysis panel (collapsed by default):

   with st.expander("⚙ Pipeline details", expanded=False):
     for agent_name, seconds in ctx.get("pipeline_timings", {}).items():
       st.caption(f"{agent_name}: {seconds:.2f}s")
     st.caption(f"Model used: {ctx.get('model_used', '—')}")
     st.caption(f"QA result: {ctx.get('qa_result', '—')}")
     if ctx.get("qa_flags"):
       st.caption(f"QA flags: {', '.join(ctx['qa_flags'])}")

3. Show total generation time as a small caption near the draft:
   "Generated in {total:.1f}s · {model_used}"

Do NOT change nlp.py, connector.py, learning.py, tickets.py, or JSON data files.
```
