# CS AI ENGINE
## Startup Product & Engineering Roadmap
### From Prototype to Production-Grade Platform

**Version:** v1.0 · April 2026  
**Based on:** Deep Architecture Research · OpenAI & Anthropic Agent Guides · McKinsey AI Adoption · CNIL Compliance  
**Classification:** CONFIDENTIAL — Internal Use Only

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Strategic Context & Market Position](#2-strategic-context--market-position)
3. [Target Architecture](#3-target-architecture)
4. [Roadmap — Four Phases](#4-roadmap--four-phases)
5. [Full Priority Matrix](#5-full-priority-matrix)
6. [The 7 Immediate Actions](#6-the-7-immediate-actions)
7. [Engineering Standards & CI Pipeline](#7-engineering-standards--ci-pipeline)
8. [Observability & Business Metrics](#8-observability--business-metrics)
9. [Security & Compliance Checklist](#9-security--compliance-checklist)
10. [Risk Register](#10-risk-register)
11. [Bonus: High-Value Additions](#11-bonus-high-value-additions)
12. [Success Milestones](#12-success-milestones)

---

## 1. Executive Summary

This document is the definitive product and engineering roadmap for the CS AI Engine as it transitions from a working prototype to a serious startup-grade platform. It is grounded in deep research synthesizing recommendations from OpenAI, Anthropic, McKinsey, NVIDIA, CNIL, OWASP, and NIST, as well as foundational AI agent papers (ReAct, Toolformer, Self-Refine, Reflexion).

**The central finding is this:** the real competitive moat for a customer service AI product is not a cleverer prompt — it is a reliable workflow, robust connectors, proprietary evaluation datasets, and a control layer that transforms a variable LLM into a deterministic system at critical decision points.

78% of organizations now use AI in at least one function, yet more than 80% report no tangible EBIT impact at scale. The bottleneck is always the same: data quality, governance, interoperability, and inability to prove ROI. This is the exact gap our product must close — not by adding more agents, but by building the infrastructure that makes every agent trustworthy, auditable, and measurable.

| Dimension | Our Answer |
|---|---|
| **Core product** | Customer decision orchestration layer — not just a chat agent |
| **Architecture** | 3 planes: Control (state + policies), Truth (facts + validation), Experience (drafting + tone + memory) |
| **Wedge** | One high-value workflow mastered end-to-end, then expanded — not a feature sprawl |
| **Moat** | Proprietary eval datasets, connector reliability, policy engine, audit trail |
| **Compliance** | CNIL-ready from day one: PII redaction, structured logging, human oversight, justified retention |
| **Timeline** | 4 phases over 28 weeks: Foundation → Reliability → Intelligence → Scale |

---

## 2. Strategic Context & Market Position

### 2.1 The Market Signal

The data is clear: the market for agentic customer service AI is large and accelerating, but the conversion from experimentation to real value is extremely low.

- Nearly **two thirds of enterprises** have piloted AI agents
- Fewer than **10% have reached tangible value at scale**
- **8 in 10** cite data limitations as the primary blocker
- **30%** of respondents in NVIDIA's 2026 survey lack clarity on ROI

This is not a technology gap — it is an **execution and trust gap**. The companies that will win are those that can prove the system works, prove it is safe, and prove it is worth the investment. That proof must live in the product itself, not in sales decks.

### 2.2 What the Research Tells Us to Build

| SOTA Finding | Product Implication for CS AI Engine |
|---|---|
| Start simple: mono-agent + tools before multi-agent | One central orchestrator; each new agent must justify a measurable gain |
| Context is a finite, degradable resource | Bounded memory, scoped per ticket/client, aggressive input cleaning, fact registry |
| Agents die at scale on data quality | Fact registry with provenance, TTL, validation — no claim without a verified fact |
| Tools define overall quality | Narrow APIs, explicit names, token-efficient responses, minimal permissions |
| Enterprises pay for governance | Policy engine, audit trail, human approval on sensitive actions, controlled retention |
| Real gains come from workflow integration | ERP + CRM + Email connectors are not optional — they are the product |

### 2.3 Our Competitive Positioning

The defensible position for a startup in this space is not to out-model OpenAI or Anthropic. It is to **out-operate them in the narrow domain of B2B customer service**. That means:

- **Deep workflow knowledge** baked into the policy engine — rules a generic LLM cannot know
- **Connector reliability** no horizontal platform bothers with (ERP-specific retries, schema validation, deduplication)
- A **proprietary eval corpus** that gets better every week as real tickets flow through the system
- An **audit trail** that satisfies a CNIL audit, a SOC 2 reviewer, and an enterprise procurement officer

---

## 3. Target Architecture

### 3.1 The Three-Plane Model

The architecture must be structured around three distinct planes. This separation is the foundation that makes the system controllable, auditable, and scalable.

| Plane | Responsibility | Key Components |
|---|---|---|
| 🔴 **CONTROL PLANE** | State machine, policies, decisions, routing | TicketState FSM · PolicyEngine · DecisionEngine · IdempotencyGuard |
| 🟡 **TRUTH PLANE** | Verified facts, provenance, validation, anti-hallucination | FactRegistry · ValidatorAgent · ClaimChecker · ConnectorResults |
| 🟢 **EXPERIENCE PLANE** | Drafting, tone, memory, role-aware behaviour | ResponseAgent · QAAgent · SelfCritiqueAgent · ScopedMemory · FallbackTemplates |

### 3.2 Pipeline Flow

Every message follows a deterministic path through eight stages. No stage can be skipped. Each stage emits a trace.

| # | Stage | What it does | Output contract |
|---|---|---|---|
| 1 | **Input Cleaning** | Strip quoted chains, HTML, signatures, injections, noise senders | CleanMessage + SanitizationReport |
| 2 | **Triage** | Classify intent, emotion, language, risk flags, missing fields, confidence scores | TriageResult (strict Pydantic) |
| 3 | **Fact Builder** | Query ERP, CRM, KB — build verified fact objects with source + TTL | list[Fact] in FactRegistry |
| 4 | **Response Agent** | Draft reply using only verified facts; reference prompt version | DraftResponse with facts_used refs |
| 5 | **Self-Critique** | Agent reviews its own draft for accuracy, tone, completeness | SelfCritiqueResult |
| 6 | **Validator + Policy** | Check every claim against FactRegistry; evaluate policy rules | ValidationResult + PolicyDecision |
| 7 | **QA Rewriter** | Fix tone, language, length per role/segment/SLA tier | Final draft string |
| 8 | **Decision Engine** | Route: send / human review / block / escalate — deterministic rules only | DecisionResult: action + reason + human_required |

### 3.3 File Structure (Target State)

```
src/
  core/         → config, logging, tracing, policies, state_machine, ids
  schemas/      → core, messages, facts, connectors, decisions
  agents/       → triage, fact_builder, responder, self_critique,
                    validator, qa, decision
  connectors/   → base, email, erp, crm, kb, attachments
  storage/      → repo, audit, prompt_registry
  orchestrator/ → service (the single entry point), tasks
  templates/    → fallback/ (Jinja2, never LLM in red zones)
  evals/        → dataset/, simulator, graders, reports

tests/
  unit/         → state machine, policies, validators, dedup
  integration/  → full pipeline on nominal cases
  contract/     → frozen ERP/CRM/email mocks
  synthetic/    → adversarial, multilingual, conflict, injection
  regressions/  → frozen eval dataset + CI gate
```

### 3.4 Key Schema Contracts

```python
# The minimum set of strict Pydantic models — these ARE the product contracts

class TicketState(str, Enum):
    NEW = "new"
    TRIAGED = "triaged"
    FACTS_BUILT = "facts_built"
    DRAFTED = "drafted"
    SELF_REVIEWED = "self_reviewed"
    VALIDATED = "validated"
    QA_PASSED = "qa_passed"
    READY = "ready"
    SENT = "sent"
    REVIEW = "review"
    BLOCKED = "blocked"
    ESCALATED = "escalated"

class ConfidenceScores(BaseModel):
    intent: float = Field(ge=0.0, le=1.0)
    emotion: float = Field(ge=0.0, le=1.0)
    data_completeness: float = Field(ge=0.0, le=1.0)
    factual_support: float = Field(ge=0.0, le=1.0)
    tone_quality: float = Field(ge=0.0, le=1.0)
    final: float = Field(ge=0.0, le=1.0)

class TriageResult(BaseModel):
    model_config = ConfigDict(strict=True)
    intent: Literal["order_status","complaint","delay","invoice","cancellation","modification","unknown"]
    emotion: Literal["calm","neutral","frustrated","angry"]
    risk_flags: list[str]
    missing_fields: list[str]
    language: str
    confidence: ConfidenceScores

class Fact(BaseModel):
    model_config = ConfigDict(strict=True)
    key: str
    value: str | int | float | bool | None
    source_type: Literal["erp","crm","email","attachment","kb","derived"]
    source_ref: str
    verified: bool
    observed_at: str   # ISO-8601
    ttl_s: int
    sensitivity: Literal["public","internal","pii","restricted"]

class DecisionResult(BaseModel):
    action: Literal["send", "review", "block", "escalate"]
    reason: str
    required_human_review: bool
    blocked_by: list[str] = []
    confidence_floor_used: float | None = None
```

---

## 4. Roadmap — Four Phases

> Each phase has a clear exit gate. No phase starts until the previous one passes its gate.

---

### 🔴 PHASE 0 — FOUNDATION (Weeks 1–4): "Make It Unbreakable"

**Goal:** The system never crashes, never halts mysteriously, never sends incorrect information. Every action is traceable. The foundation for everything else.

| Deliverable | Technical spec | Done when… |
|---|---|---|
| **State Machine** | TicketState Enum + transition matrix + InvalidTransitionError + idempotent retry_count + logical lock per ticket | Parametrised tests cover ALL valid and invalid transitions |
| **Typed Schemas** | Pydantic strict models at every agent boundary: TriageResult, Fact, DraftResponse, ValidationResult, DecisionResult | Zero dict passing between agents; ValidationError stops execution |
| **Fact Registry** | Fact(key, value, source_type, source_ref, verified, observed_at, ttl_s, sensitivity). ValidatorAgent checks every claim against registry. Unverified claim = unsupported_claim + block. | Unit test: unverified date claim → block. Verified claim → send. |
| **Connector Resilience** | ConnectorResult[T] envelope, ConnectorError(kind: retryable\|fatal\|auth\|rate_limit), exponential backoff + jitter + circuit breaker via Tenacity | Connector failure never crashes the orchestrator |
| **Policy Engine** | Code-first PolicyRule objects (Python, not prompts), deny-by-default, human approval on: sensitive writes, angry + low confidence, unverified date promises | All policy violations → SECURITY log + block. Zero rules expressed only in a prompt. |
| **Idempotency** | IdempotencyKey per message/thread/action; hash-based dedup; DuplicateSuppressed event | Sending same email twice → one ticket, one reply |
| **Trace Logging** | StepTrace per stage: run_id, ticket_id, step, latency_ms, tokens, model, prompt_version, error_code. Zero raw PII. | Every ticket produces a complete queryable trace |

**Phase 0 Exit Gate:** All unit tests pass. All P0 schemas validated. Zero unclassified exceptions in a 100-ticket smoke test. State machine has 100% transition coverage.

---

### 🟠 PHASE 1 — RELIABILITY (Weeks 5–10): "Make It Production-Worthy"

**Goal:** The system is safe to show to a first paying customer. It handles messy real-world input, has a CI gate, and every regression is caught before it ships.

| Deliverable | Technical spec | Done when… |
|---|---|---|
| **Prompt Registry + Versioning** | PromptSpec: prompt_id, semver, checksum, variables, changelog. No inline prompts in production. | Git blame on any prompt regression — traceable to exact version + PR |
| **Eval Harness + CI Gate** | Frozen dataset of 50+ cases (nominal, ambiguous, adversarial, ERP conflict). Graders: intent accuracy, claim support, decision correctness. Blocks merge if score < baseline. | CI fails on regression. Eval report as build artefact on every PR. |
| **Adversarial Input Cleaning** | Strip: quoted reply chains, HTML, signatures, prompt injections, noise senders (mailer-daemon, noreply, postmaster), Re: Re: Re: loops | Injection attempts never reach the LLM. Noise emails never become tickets. |
| **Fallback Templates** | Jinja2 templates per case: missing_info, system_down, high_risk, ambiguous. Applied when LLM output is blocked or confidence below floor. | No ticket goes unanswered even when LLM is blocked. |
| **OpenTelemetry Integration** | Spans + metrics + logs correlated by run_id. Dashboard: p95 latency, error rates, token costs, review rate. | Ops can diagnose any issue from the dashboard without reading code. |
| **Config Startup Validation** | ConfigValidator checks all required fields before launch. Clear error messages with fix instructions. | New company onboarding never crashes mid-session due to missing config. |

**Phase 1 Exit Gate:** Eval harness runs in CI. Adversarial test suite passes. First customer demo environment is stable for 48h without manual intervention.

---

### 🟢 PHASE 2 — INTELLIGENCE (Weeks 11–18): "Make It Smart"

**Goal:** The system handles real B2B complexity: attachments, memory, multiple languages, multiple customer profiles. It learns from its own history.

| Deliverable | Technical spec | Done when… |
|---|---|---|
| **Scoped Memory** | MemoryItem(scope: ticket\|client\|account, ttl, size_limit, checksum). PII redacted before persistence. No global unfiltered memory. | Agent recalls previous interactions in same thread. No cross-customer data bleed. |
| **Attachment Module** | Classify doc type, extract structured fields with confidence per field. Isolated from main text pipeline. Extracted fields fed into FactRegistry. | Invoice PDF produces verified Fact objects. Extraction failure does not block ticket. |
| **Role-Aware Behaviour** | ResponsePolicy per role + customer segment + language + severity. Tone rules in QA agent AND policy engine, not only in the prompt. | Tone audit on 20 real tickets shows correct register for segment in 90%+ cases. |
| **KB Usage Tracking** | Log every KB entry retrieved. Mark helpful on draft approval. Flag unused entries (30 days). Flag low-approval entries (<40%) for review. | Analytics dashboard shows KB health. Dead entries identified within 30 days. |
| **Lesson Effectiveness Tracking** | Track whether lessons injected into prompts actually improve draft quality. A/B at prompt version level. | Each lesson has a measured effect score. Ineffective lessons are retired. |
| **Pipeline Timing Dashboards** | Per-stage latency visible in UI. SLO breach alerts. Cost per ticket per account. | Ops can identify the bottleneck stage for any slow ticket in under 2 minutes. |

**Phase 2 Exit Gate:** 3 real B2B customers in production. Attachment handling live. KB usage dashboard showing data. p95 latency under 3s end-to-end.

---

### 🔵 PHASE 3 — SCALE (Weeks 19–28): "Make It a Platform"

**Goal:** The system is a platform: multi-tenant, self-service onboarding, connector marketplace, enterprise audit capabilities. Ready for Series A narrative.

| Deliverable | Technical spec | Done when… |
|---|---|---|
| **Multi-Tenant Account Isolation** | Complete data isolation per account: separate fact registries, memory scopes, policy rule sets, prompt versions, audit trails. | Penetration test confirms zero cross-account data access. |
| **Self-Service Onboarding** | Guided config wizard + ConfigValidator + connector health check + template playground. New account live in under 1 hour. | 5 new accounts onboarded by a non-engineer in under 1 hour each. |
| **Connector Marketplace** | Standardised ConnectorResult[T] interface allows third-party connectors. SDK + docs + sandbox. | 2 partner connectors built by external developers using the SDK. |
| **Enterprise Audit Export** | Full AuditEvent export per account, date range, event type. CNIL-compliant retention policy enforced automatically. | Enterprise customer passes internal compliance review using our audit export. |
| **Cost Optimisation Layer** | Route simple/high-confidence tickets to smaller/cheaper models. Complex/low-confidence to premium model. Governed by account config. | Token cost per ticket reduced by 30%+ vs Phase 0 baseline with no quality regression. |
| **Synthetic Data Generator** | Generate eval cases from real tickets (PII stripped). Auto-grow dataset. Keeps CI gate relevant as product evolves. | Eval dataset grows automatically. No manual curation required for >80% of new cases. |

**Phase 3 Exit Gate:** 10+ active accounts. Series A deck can cite measurable EBIT impact per customer. SOC 2 / CNIL audit passed or in progress.

---

## 5. Full Priority Matrix

| Pri | Item | Why it matters | Phase | Effort | Impact |
|---|---|---|---|---|---|
| **P0** | State Machine | Prevents step-skipping; makes resumption deterministic | Phase 0 | M | Critical |
| **P0** | Typed Pydantic Schemas | Eliminates shape bugs between agents and connectors | Phase 0 | M | Critical |
| **P0** | Fact Registry | Strongly reduces hallucinations | Phase 0 | M | Critical |
| **P0** | Connector Resilience | Upstream failures must not crash the engine | Phase 0 | M | Critical |
| **P0** | Policy Engine (code-first) | Business rules must not depend on prompts | Phase 0 | M | Critical |
| **P0** | Confidence Decomposition | One global score hides real weaknesses | Phase 0 | S | Critical |
| **P0** | Idempotency | Prevents duplicate tickets, replies, escalations | Phase 0 | M | Critical |
| **P0** | Trace Logging (structured) | Bugs and regressions must be diagnosable | Phase 0 | M | Critical |
| **P1** | Prompt Registry + Versioning | Regressions must be attributable to a specific change | Phase 1 | M | High |
| **P1** | Eval Harness + CI Gate | Without evals, every prompt change breaks something else | Phase 1 | M | High |
| **P1** | Adversarial Input Cleaning | Email is an attack surface; injections must not reach LLM | Phase 1 | S | High |
| **P1** | Fallback Templates | In doubt, a safe template beats a risky LLM response | Phase 1 | S | High |
| **P1** | OpenTelemetry Integration | Ops team needs visibility without reading code | Phase 1 | M | High |
| **P1** | Config Startup Validation | Setup errors must surface before a customer interaction | Phase 1 | S | High |
| **P1** | Scoped Memory | Agent memory must be bounded, isolated, expirable | Phase 2 | M | Med/High |
| **P1** | Attachment Module | B2B tickets live in PDFs and images | Phase 2 | L | High (B2B) |
| **P1** | KB Usage Tracking | Unused or harmful KB entries degrade quality silently | Phase 2 | M | Medium |
| **P2** | Role-Aware Behaviour | Tone and style must adapt to customer segment | Phase 2 | M | Medium |
| **P2** | Lesson Effectiveness Tracking | Learning system needs data before it can improve | Phase 2 | M | Medium |
| **P2** | Pipeline Timing UI | Debugging aid and latency SLO visibility | Phase 2 | S | Low/Med |
| **P2** | Multi-Tenant Isolation | Required before scaling to multiple enterprise accounts | Phase 3 | L | Strategic |
| **P2** | Cost Optimisation Layer | Unit economics must improve as volume scales | Phase 3 | M | Medium |
| **P2** | Connector Marketplace SDK | Third-party connectors multiply addressable market | Phase 3 | L | Strategic |

---

## 6. The 7 Immediate Actions

> These are the seven tasks to implement right now, in this exact order. Each one unblocks the next.

### Task 1 — State Machine
**Build:** Create `TicketState` Enum, `StateTransition` model, transition matrix (dict of valid from→to pairs), `InvalidTransitionError`. Add `retry_count` and logical lock per ticket.  
**Accept when:** Parametrised pytest covers all 20+ transitions. Invalid transitions raise, not silently pass.

### Task 2 — Strict Pydantic Schemas
**Build:** Replace every dict passed between agents with strict Pydantic models. Start with `TriageResult`, then `DraftResponse`, `ValidationResult`, `DecisionResult`. `ValidationError` must stop execution.  
**Accept when:** Grep confirms zero raw `dict()` returns at agent boundaries. CI passes with strict mode.

### Task 3 — Fact Registry
**Build:** Implement `Fact(key, value, source_type, source_ref, verified, observed_at, ttl_s, sensitivity)`. `FactRegistry` stores facts by ticket_id. `ValidatorAgent` must compare every draft claim against the registry. Unverified claim = `unsupported_claim` flag + block.  
**Accept when:** Unit test — draft with unverified date claim → block decision. Verified claim → send.

### Task 4 — Unified Connector Interface
**Build:** All connectors return `ConnectorResult[T]`. All errors are `ConnectorError(kind: retryable|fatal|auth|rate_limit|policy|timeout)`. Apply Tenacity retry with exponential backoff + jitter + `stop_after_attempt(3)`. Circuit breaker on fatal.  
**Accept when:** Mock returning `retryable` error triggers 3 attempts then routes to review. Fatal error triggers immediate review with no retry.

### Task 5 — Policy Engine
**Build:** Code-first `PolicyRule` objects (Python, not prompt text). Minimum rules: (a) no promised delivery date without verified ERP fact, (b) no auto-send if `emotion=angry` AND `confidence.final < 0.7`, (c) no sensitive write without human approval. Deny-by-default.  
**Accept when:** Each rule has a dedicated unit test. Violation always produces SECURITY log + block. No rule is expressed only in a prompt.

### Task 6 — OpenTelemetry + Structured Logs
**Build:** Wire OTel spans per agent stage. Structured log fields: `run_id`, `ticket_id`, `step_name`, `latency_ms`, `model`, `prompt_version`, `token_usage`, `decision`, `error_code`. Zero raw PII in any log line.  
**Accept when:** Any ticket can be reconstructed from its trace without reading source code. PII audit confirms no email/name in logs.

### Task 7 — Eval Harness + CI Gate
**Build:** `evals/simulator.py` + frozen dataset of 50+ cases: 15 nominal, 10 ambiguous/missing-data, 10 emotional/risk, 10 ERP-conflict, 5 adversarial-injection. Graders: intent accuracy, decision correctness, claim support rate. Block merge if score regresses beyond threshold.  
**Accept when:** Eval report generated on every PR. Intentionally broken prompt fails CI. Fixed prompt passes CI.

---

## 7. Engineering Standards & CI Pipeline

### 7.1 CI Stages (in order — all blocking)

| Stage | What runs | Blocking condition |
|---|---|---|
| 1. Lint + sanity | ruff, mypy strict, import checks, config schema validation | Any import error or config invalid |
| 2. Unit tests | State machine, policies, validators, dedup, connector error classification | Any single failure |
| 3. Contract tests | Frozen ERP/CRM/email mocks — schema and error code contracts | Schema breakage or unexpected error code |
| 4. Integration tests | Full pipeline on nominal + edge cases | Unexpected decision result |
| 5. Synthetic simulator | Adversarial, multilingual, ERP conflict, attachment, injection | Hallucination or unjustified block/review rate increase |
| 6. Prompt evals | Frozen dataset + graders; nightly run is larger | Score < baseline minus threshold |
| 7. Build + secrets scan | Packaging, .env.example check, gitleaks scan | Secret detected in codebase or build broken |

### 7.2 Non-Negotiable Engineering Rules

- **No raw dict passed between agents** — Pydantic strict models only
- **No prompt written inline** — every LLM call references a versioned `PromptSpec`
- **No secret in code** — environment variables or secret manager only; never committed
- **No write action without an idempotency key** — `DuplicateSuppressed` is always safe
- **No LLM response in a red zone** — fallback templates for `high_risk`, `system_down`, `ambiguous`
- **No PII in logs** — redact before any `log.write()` or `trace.set()`
- **No unclassified exception in production** — every exception produces a classified error + action

---

## 8. Observability & Business Metrics

| Metric | Why it matters | Initial SLO / Target |
|---|---|---|
| `triage_latency_ms` | Speed of understanding | p95 < 1200 ms |
| `e2e_pipeline_latency_ms` | Customer-perceived responsiveness | p95 < 5000 ms (Phase 0) → < 3000 ms (Phase 2) |
| `connector_error_rate` | Integration health per backend | < 1% per connector |
| `schema_validation_fail_rate` | Shape bugs between agents | < 0.2% |
| `unsupported_claim_rate` | Hallucination detection proxy | Downward trend every release |
| `review_rate` | Engine calibration signal | Stable by ticket type; no unexplained spikes |
| `escalation_rate` | Operational quality per account | Weekly review per account |
| `fallback_rate` | True resilience under load/failure | Alert if > 5% in 1h window |
| `token_cost_per_ticket` | Unit economics visibility | Dashboard per account + per workflow type |
| `prompt_regression_score` | Safety of LLM changes | Block merge on any regression beyond threshold |
| `duplicate_suppression_rate` | Email ingestion hygiene | Measured; not targeted to zero |
| `kb_approval_rate` | Knowledge base quality signal | Flag entries < 40% with >= 5 retrievals |

---

## 9. Security & Compliance Checklist

### 9.1 Non-Negotiable Security Controls

- ✅ **API keys server-side only** — Injected via environment variables or secret manager. Never committed to git. Rotate on any suspicion of leak.
- ✅ **PII redacted before logs and memory** — Email addresses, names, order references stripped or pseudonymised before any `log.write()`, `trace.set()`, or `memory.persist()`.
- ✅ **Structured + protected logging** — JSON logs only. Log levels: DEBUG/INFO/WARN/ERROR/SECURITY. SECURITY level for policy violations and auth failures.
- ✅ **Least privilege on all connectors** — Each connector has its own service account with exactly the permissions it needs. Read-only where possible.
- ✅ **Human approval on sensitive actions** — Any action tagged `sensitive` in `PolicyRule` requires `DecisionResult.required_human_review = True`.
- ✅ **Memory isolation per account/client** — `MemoryItem` scope enforced at storage level. No query crosses account boundary. TTL enforced by the storage layer, not caller.
- ✅ **Adversarial input sanitisation** — All external content (email body, attachment text, subject lines) treated as untrusted. Injection patterns stripped before NLP pipeline.
- ✅ **Secrets scan in CI** — gitleaks or equivalent runs on every PR. Any detected secret blocks the merge.

### 9.2 CNIL Compliance Requirements (France)

- **Data minimisation** — collect only what is needed for the specific processing purpose
- **Explainable logging** — logs must contain enough context to explain why a decision was made
- **Human supervision** — every automated decision above a defined risk threshold requires human review
- **Justified retention** — 3-tier retention policy (see below)
- **Purpose separation** — logs for security auditing must not be mixed with logs for product analytics
- **Continuous quality control** — AI output quality must be monitored and documented on an ongoing basis

### 9.3 Data Retention Policy

| Tier | Content | Retention | PII handling |
|---|---|---|---|
| 🔴 Security logs | Policy violations, auth failures, injection attempts | 6–12 months | Redacted, protected |
| 🟡 Operational traces | StepTrace, latency, tokens, decisions, model versions | 30–90 days | No raw PII; metadata only |
| 🟢 Conversational content | Email bodies, drafts, attachment extracts | Short default; business-justified | PII pseudonymised or deleted |

---

## 10. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Hallucination reaches customer | Medium | 🔴 Critical | Fact registry + validator blocks unsupported claims. Fallback template on block. Human review on low confidence. |
| Prompt injection via email body | Medium | 🟠 High | Adversarial input cleaning strips injection patterns before NLP. All external content treated as untrusted. |
| ERP/CRM connector outage | Medium | 🟠 High | Retry + circuit breaker + fallback template. Ticket routes to human review if connector exhausted. No crash. |
| Prompt regression in production | High | 🟠 High | Eval harness in CI blocks merge on regression. Prompt registry traces every change to a PR. |
| PII leak in logs | Low | 🔴 Critical | Redaction layer runs before every log.write() and trace.set(). PII audit in CI. CNIL notification procedure documented. |
| Duplicate tickets or double-send | High | Medium | Idempotency keys on all inbound messages and all write actions. DuplicateSuppressed event logged. |
| Customer data cross-contamination | Low | 🔴 Critical | Memory and fact registry scoped at account level enforced by storage layer. Penetration test before multi-tenant go-live. |
| Config missing crashes at onboarding | High | Medium | ConfigValidator runs before launch with clear human-readable error messages. Setup wizard validates in real time. |

---

## 11. Bonus: High-Value Additions

> These are improvements beyond the research document that will make the product significantly stronger as a startup. Each one is battle-tested in real SaaS products.

### 11.1 Customer Health Scoring

Build a `CustomerHealthScore` that tracks, per customer account: escalation frequency, average response time, draft rejection rate, satisfaction proxies (tone of messages over time). This gives your sales team a real signal for upsell and churn risk — and gives your AI a richer context for prioritisation.

### 11.2 SLA-Aware Routing

Instead of routing by intent alone, route by **SLA urgency**. A customer with a 4-hour SLA and a ticket open for 3.5 hours should jump the queue automatically. The decision engine should factor in `time_to_sla_breach` as an input alongside confidence scores.

### 11.3 Draft Explainability Cards

Every AI draft should be accompanied by a machine-readable explanation card: which facts were used, what the intent was, which KB entries contributed, and what confidence scores drove the decision. This serves two purposes: agents can review decisions faster, and your compliance log is automatically meaningful.

### 11.4 Smart Ticket Grouping

When the same issue affects multiple customers (e.g., a shipping delay on a supplier batch), automatically group related tickets and draft a single master response that gets personalised per customer. This multiplies agent productivity during incidents and reduces LLM costs dramatically.

### 11.5 Proactive Outreach Module

Instead of only reacting to incoming tickets, build a light proactive module: when the ERP detects a delay, stock issue, or billing anomaly that affects a known customer, automatically draft a proactive notification for agent review. Turning reactive service into proactive service is a major differentiator.

### 11.6 Supervisor Dashboard

A dedicated view for supervisors (separate from the agent inbox) showing: team performance, SLA compliance rate, AI auto-send rate vs. human-edited rate, ticket type breakdown, and top escalation reasons. This is the "management layer" that enterprise buyers often require before signing.

### 11.7 Integration Health Monitor

A live dashboard (not just CI tests) showing the health of every connector: last successful fetch, error rate in last 24h, average latency, data freshness. When ERP data is stale, the system should automatically increase the review threshold — not trust stale facts.

### 11.8 Confidence Trend Analysis

Track how agent confidence evolves over time per ticket type. If confidence on "invoice disputes" has dropped 10 points over 3 weeks, that's a signal the prompt is drifting or the KB entries are outdated. This is the canary in the coal mine for quality degradation.

### 11.9 White-Label & Multi-Brand Support

Each account can have its own brand voice, signature, colour theme in the agent dashboard, and email templates. This opens the door to reseller partners — an agency managing customer service for 10 brands pays you once per brand, not once per company.

### 11.10 One-Click Rollback for Prompts

In the prompt registry, add a "rollback" button in the admin UI that redeploys the previous prompt version and adds the current version to a quarantine list. When a prompt regression is detected in production, the fix should be one click, not a git revert + deployment.

---

## 12. Success Milestones

These are the concrete checkpoints that signal readiness to move to the next stage. Each one is observable and verifiable, not a feeling.

| Milestone | When | Observable evidence | Opens door to |
|---|---|---|---|
| **M0 — Unbreakable base** | End of Phase 0 (Wk 4) | 100-ticket smoke test completes with zero unclassified exceptions. All transitions tested. Zero dict at agent boundaries. | First internal demo |
| **M1 — Production-ready** | End of Phase 1 (Wk 10) | CI pipeline green. Eval harness running. 48h stable demo environment. Injection tests all blocked. | First paying customer |
| **M2 — First B2B revenue** | Wk 12–14 | Contract signed. Real tickets flowing. p95 < 5s. Human review rate below 30%. Zero critical incidents. | Case study, pricing model |
| **M3 — Smart platform** | End of Phase 2 (Wk 18) | 3 active accounts. Attachment handling live. KB dashboard showing data. Memory system stable. p95 < 3s. | Series A narrative |
| **M4 — Series A ready** | End of Phase 3 (Wk 28) | 10+ accounts. Measurable EBIT impact per customer documented. SOC 2 or CNIL audit in progress. Token cost down 30%. | Scale fundraising |

---

*CS AI Engine — Product & Engineering Roadmap · v1.0 · April 2026*  
*CONFIDENTIAL — Do not distribute outside the founding team*
