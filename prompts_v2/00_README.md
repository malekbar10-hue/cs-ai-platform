# Startup Roadmap Prompts — Phase 0 & 1
## 12 prompts. Each one is independent and paste-ready into Claude Code in VS Code.

These prompts implement the startup roadmap (CS_AI_Engine_Startup_Roadmap.md).
Do them in order — each P0 prompt unblocks the next.

---

| File | What it builds | Phase | Priority |
|------|----------------|-------|----------|
| P0_01_StateMachine | TicketState FSM + transition matrix + InvalidTransitionError | Phase 0 | P0 |
| P0_02_TypedSchemas | Strict Pydantic models at every agent boundary | Phase 0 | P0 |
| P0_03_FactRegistry | Fact objects + FactRegistry + ValidatorAgent claim-check | Phase 0 | P0 |
| P0_04_ConnectorResilience | ConnectorResult[T] + ConnectorError + Tenacity retries | Phase 0 | P0 |
| P0_05_PolicyEngine | Code-first PolicyEngine, deny-by-default | Phase 0 | P0 |
| P0_06_TraceLogging | Structured StepTrace logging, no raw PII | Phase 0 | P0 |
| P0_07_EvalHarness | Eval dataset + graders + CI gate | Phase 0 | P0 |
| P1_08_PromptRegistry | PromptSpec versioning, no inline prompts | Phase 1 | P1 |
| P1_09_FallbackTemplates | Jinja2 safe templates for red-zone decisions | Phase 1 | P1 |
| P1_10_ScopedMemory | Bounded memory per ticket/client/account | Phase 1 | P1 |
| P2_11_CustomerHealthScore | Per-account health scoring + churn signal | Phase 2 | P2 |
| P2_12_SLAAwareRouting | SLA-aware ticket priority + queue routing | Phase 2 | P2 |

---

## Suggested order

Do all P0 prompts before any P1. Do all P1 before P2.
Within P0: 01 → 02 → 03 → 04 → 05 → 06 → 07 (strict order — each one builds on the previous).
