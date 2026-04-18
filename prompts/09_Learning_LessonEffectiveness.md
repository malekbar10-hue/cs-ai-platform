# 09 — Learning: Lesson Effectiveness Tracking

## What This Does

Your self-learning system already stores lessons when agents correct
AI drafts. Those lessons get injected into future prompts for similar
cases. But right now there is no way to know if those lessons are
actually working — maybe a lesson gets injected 20 times but the draft
always gets modified anyway, meaning the lesson is not helping.

This improvement tracks two things for every lesson:
- How many times it was applied (injected into a prompt)
- How many times it was effective (the draft was approved without changes
  after the lesson was applied)

This gives you an effectiveness rate per lesson. Lessons with very low
effectiveness (say below 20% after 5+ applications) get a warning badge
— they may need to be reworded or removed. Lessons with high effectiveness
are sorted to the top so the best ones get used first.

**Where the change lives:** `learning.py` (tracking methods) +
`agents/response.py` (tracks which lessons were applied) +
`app.py` / `app_inbox.py` (marks effective/applied on approval) +
`pages/1_Analytics.py` (effectiveness column in learning report).

**Impact:** The learning system becomes self-improving. Bad lessons
get identified and can be cleaned up. Good lessons get prioritized.

---

## Prompt — Paste into Claude Code

```
Track whether injected lessons actually improved the draft.

TASK:

1. In learning.py, add columns to the lessons table:
   ALTER TABLE lessons ADD COLUMN times_applied INTEGER DEFAULT 0;
   ALTER TABLE lessons ADD COLUMN times_effective INTEGER DEFAULT 0;
   Guard both with an IF NOT EXISTS column check using PRAGMA table_info.

2. Add to FeedbackAnalyzer:

   def mark_applied(self, lesson_ids: list[int]):
     Increments times_applied by 1 for each lesson ID in the list.

   def mark_effective(self, lesson_ids: list[int]):
     Increments both times_applied AND times_effective by 1 for each ID.

3. In agents/response.py, when lessons are retrieved and injected into
   the prompt, store their IDs:
   ctx["applied_lesson_ids"] = [list of integer lesson IDs that were used]

4. In app.py and app_inbox.py:
   - On "approved unchanged": call analyzer.mark_effective(applied_lesson_ids)
   - On "approved modified" or "rejected": call analyzer.mark_applied(applied_lesson_ids)
   applied_lesson_ids comes from st.session_state or ctx.

5. In pages/1_Analytics.py, in the Learning section, add an
   "Effectiveness" column to the lessons table:
   effectiveness = times_effective / times_applied (as %) — show "—" if times_applied = 0
   Sort by effectiveness descending by default.
   Lessons with effectiveness < 20% AND times_applied >= 5 get a "⚠ Low effectiveness" badge.

Do NOT change connector.py, nlp.py, tickets.py, channels.py, or JSON data files.
```
