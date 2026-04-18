# Polish Prompts — Index
## 13 independent improvements, each in its own file.

Paste the prompt from each file into Claude Code in VS Code.
Each is independent — do them in any order.

---

| File | What it improves | Priority |
|------|-----------------|----------|
| 01_NLP_AutoReply_Filter | Stop processing junk emails | High |
| 02_NLP_MixedLanguage | Detect uncertain language, warn agent | Medium |
| 03_Agents_DraftQualityGuards | Warn on short/wrong-language/missing ID drafts | High |
| 04_Agents_PipelineTiming | Show how long each agent took | Low |
| 05_Tickets_InternalNotes | Agent notes not sent to customer | High |
| 06_Tickets_AutoClose | Auto-close tickets with no reply after N days | Medium |
| 07_Tickets_PriorityOverride | Supervisor can change ticket priority | Medium |
| 08_Escalation_Preview | Show which rules would fire before approving | High |
| 09_Learning_LessonEffectiveness | Track if lessons actually improve drafts | Low |
| 10_KB_UsageTracking | Track which KB entries are used and helpful | Low |
| 11_Channels_EmailNoise | Clean quoted replies, filter noise senders | High |
| 12_Dashboard_UXDetails | Character count, copy button, toasts, empty states | Medium |
| 13_Config_StartupValidation | Catch config errors before they crash the app | High |

---

## Suggested order for first deployment

1. 13 — Config validation (catch setup issues early)
2. 01 — Auto-reply filter (stop junk from hitting AI)
3. 11 — Email noise cleaning (clean content before NLP)
4. 03 — Draft quality guards (catch obvious AI mistakes)
5. 05 — Internal notes (agents need this from day one)
6. 08 — Escalation preview (no surprises for agents)
7. 12 — UX details (polish before showing to anyone)
8. 06 — Auto-close (inbox hygiene)
9. 07 — Priority override (supervisor control)
10. 02 — Mixed language (refinement)
11. 04 — Pipeline timing (debugging aid)
12. 09 — Lesson effectiveness (needs data first)
13. 10 — KB usage (needs data first)
